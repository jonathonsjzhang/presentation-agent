from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


_DRAWING_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
_WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass
class PreparedArtifact:
    artifact_path: str
    format: str
    extracted_text_path: str
    visual_paths: list[str] = field(default_factory=list)
    contact_sheet_path: str | None = None
    unit_count: int = 0
    file_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ArtifactPreparationError(RuntimeError):
    pass


def evaluation_runtime_status(repo_root: Path | None = None) -> dict[str, Any]:
    """Inspect format-specific visual evaluation dependencies without rendering."""
    repo_root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    soffice = _find_binary(
        "PRESENTATION_AGENT_SOFFICE",
        "soffice",
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/soffice",
    )
    pdftoppm = _find_binary(
        "PRESENTATION_AGENT_PDFTOPPM",
        "pdftoppm",
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pdftoppm",
    )
    try:
        pymupdf_available = importlib.util.find_spec("fitz") is not None
    except (ImportError, ValueError):
        pymupdf_available = False
    pdf_renderer = "PyMuPDF (fitz)" if pymupdf_available else pdftoppm

    node = _find_binary(
        "PRESENTATION_AGENT_NODE",
        "node",
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
    )
    html_runtime = _probe_html_runtime(node, repo_root)
    chromium_launchable = bool(html_runtime.get("chromium_launchable"))
    chromium_detail = str(
        html_runtime.get("chromium")
        or html_runtime.get("error")
        or "Chromium was not checked because Node.js is unavailable"
    )
    if not chromium_launchable and html_runtime.get("error"):
        executable = html_runtime.get("chromium") or "Chromium"
        chromium_detail = f"{executable}; launch failed: {html_runtime['error']}"

    dependencies = [
        _dependency_status(
            "soffice",
            bool(soffice),
            soffice or "LibreOffice/soffice not found",
        ),
        _dependency_status(
            "pdf_renderer",
            bool(pdf_renderer),
            str(pdf_renderer) if pdf_renderer else "Neither PyMuPDF nor pdftoppm is available",
        ),
        _dependency_status("node", bool(node), node or "Node.js not found"),
        _dependency_status(
            "playwright",
            bool(html_runtime.get("playwright")),
            str(
                html_runtime.get("playwright")
                or html_runtime.get("error")
                or "Playwright was not checked because Node.js is unavailable"
            ),
        ),
        _dependency_status(
            "chromium",
            chromium_launchable,
            chromium_detail,
            unavailable_status=(
                "unavailable"
                if html_runtime.get("chromium_exists")
                else "missing"
            ),
        ),
    ]
    office_ready = bool(soffice and pdf_renderer)
    html_ready = bool(
        node
        and html_runtime.get("playwright")
        and chromium_launchable
    )
    formats = {
        "ppt": {
            "ready": office_ready,
            "requires": ["soffice", "pdf_renderer"],
        },
        "document": {
            "ready": office_ready,
            "requires": ["soffice", "pdf_renderer"],
        },
        "html": {
            "ready": html_ready,
            "requires": ["node", "playwright", "chromium"],
        },
    }
    return {
        "ok": all(item["ready"] for item in formats.values()),
        "formats": formats,
        "dependencies": dependencies,
    }


def infer_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".pptx", ".ppt"}:
        return "ppt"
    if suffix in {".docx", ".doc"}:
        return "document"
    if suffix in {".html", ".htm"}:
        return "html"
    raise ArtifactPreparationError(
        f"Unsupported E2E artifact format {suffix!r}; expected PPTX, DOCX, or HTML"
    )


def prepare_artifact(
    artifact_path: Path,
    output_dir: Path,
    *,
    render_visuals: bool = True,
) -> PreparedArtifact:
    artifact_path = Path(artifact_path).expanduser().resolve()
    if not artifact_path.exists() or not artifact_path.is_file():
        raise ArtifactPreparationError(f"Artifact does not exist: {artifact_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fmt = infer_format(artifact_path)
    warnings: list[str] = []

    if fmt == "ppt":
        text, unit_count = _extract_ppt_text(artifact_path)
    elif fmt == "document":
        text, unit_count = _extract_docx_text(artifact_path)
    else:
        text, unit_count = _extract_html_text(artifact_path)

    text_path = output_dir / "artifact_text.txt"
    text_path.write_text(text, encoding="utf-8")

    visual_paths: list[Path] = []
    if render_visuals:
        try:
            if fmt in {"ppt", "document"}:
                pdf_path = _office_to_pdf(artifact_path, output_dir)
                visual_paths = _render_pdf_pages(pdf_path, output_dir / "pages")
            else:
                visual_paths = _render_html_pages(artifact_path, output_dir / "pages")
        except Exception as exc:
            warnings.append(f"visual rendering failed: {exc}")
    else:
        warnings.append("visual rendering disabled")

    contact_sheet = _build_contact_sheet(visual_paths, output_dir / "contact-sheet.png")
    if render_visuals and not visual_paths:
        warnings.append("no visual snapshots were produced")
    if not text.strip():
        warnings.append("no extractable artifact text; content judge must rely on visual snapshots")

    return PreparedArtifact(
        artifact_path=str(artifact_path),
        format=fmt,
        extracted_text_path=str(text_path.resolve()),
        visual_paths=[str(path.resolve()) for path in visual_paths],
        contact_sheet_path=str(contact_sheet.resolve()) if contact_sheet else None,
        unit_count=unit_count or len(visual_paths),
        file_bytes=artifact_path.stat().st_size,
        warnings=warnings,
        metadata={
            "suffix": artifact_path.suffix.lower(),
            "render_visuals_requested": render_visuals,
        },
    )


def extract_context_text(path: Path, limit: int = 30000) -> str:
    path = Path(path).expanduser().resolve()
    suffix = path.suffix.lower()
    try:
        if suffix in {".txt", ".md", ".csv", ".tsv", ".yaml", ".yml"}:
            return path.read_text(encoding="utf-8", errors="replace")[:limit]
        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(data, ensure_ascii=False, indent=2)[:limit]
        if suffix == ".docx":
            return _extract_docx_text(path)[0][:limit]
        if suffix == ".pptx":
            return _extract_ppt_text(path)[0][:limit]
        if suffix in {".html", ".htm"}:
            return _extract_html_text(path)[0][:limit]
        if suffix == ".pdf":
            return _extract_pdf_text(path)[:limit]
    except Exception as exc:
        return f"[context extraction failed for {path.name}: {exc}]"
    return f"[binary/source material: {path.name}; inspect the original file at {path}]"


def _extract_ppt_text(path: Path) -> tuple[str, int]:
    if path.suffix.lower() != ".pptx":
        return "", 0
    with zipfile.ZipFile(path) as archive:
        slide_names = [
            name
            for name in archive.namelist()
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
        ]
        slide_names.sort(key=lambda name: int(re.search(r"(\d+)", name.rsplit("/", 1)[-1]).group(1)))
        blocks: list[str] = []
        for index, name in enumerate(slide_names, start=1):
            root = ET.fromstring(archive.read(name))
            text = " ".join(
                (node.text or "").strip()
                for node in root.findall(".//a:t", _DRAWING_NS)
                if (node.text or "").strip()
            )
            blocks.append(f"[Slide {index}]\n{text}")
    return "\n\n".join(blocks), len(slide_names)


def _extract_docx_text(path: Path) -> tuple[str, int]:
    if path.suffix.lower() != ".docx":
        return "", 0
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", _WORD_NS):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", _WORD_NS))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs), len(paragraphs)


class _VisibleHTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            text = re.sub(r"\s+", " ", data).strip()
            if text:
                self.parts.append(text)


def _extract_html_text(path: Path) -> tuple[str, int]:
    parser = _VisibleHTMLText()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    text = "\n".join(parser.parts)
    unit_count = len(re.findall(r'class=["\'][^"\']*\bunit\b', path.read_text(encoding="utf-8", errors="replace")))
    return text, unit_count


def _extract_pdf_text(path: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        return f"[PDF source material: {path.name}; inspect original file at {path}]"
    with pdfplumber.open(path) as pdf:
        return "\n\n".join((page.extract_text() or "").strip() for page in pdf.pages)


def _office_to_pdf(path: Path, output_dir: Path) -> Path:
    soffice = _find_binary(
        "PRESENTATION_AGENT_SOFFICE",
        "soffice",
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/soffice",
    )
    if not soffice:
        raise ArtifactPreparationError("LibreOffice/soffice not found")

    pdf_dir = output_dir / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = output_dir / "libreoffice-profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["HOME"] = str(profile_dir)
    command = [
        soffice,
        f"-env:UserInstallation={profile_dir.resolve().as_uri()}",
        "--invisible",
        "--headless",
        "--norestore",
        "--convert-to",
        "pdf",
        "--outdir",
        str(pdf_dir),
        str(path),
    ]
    proc = subprocess.run(command, capture_output=True, text=True, env=env, timeout=120, check=False)
    expected = pdf_dir / f"{path.stem}.pdf"
    if proc.returncode != 0 or not expected.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ArtifactPreparationError(detail or f"soffice exited {proc.returncode}")
    return expected


def _render_pdf_pages(pdf_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import fitz

        result: list[Path] = []
        document = fitz.open(pdf_path)
        try:
            for index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                target = output_dir / f"page-{index:03d}.png"
                pixmap.save(target)
                result.append(target)
        finally:
            document.close()
        return result
    except ImportError:
        pass

    pdftoppm = _find_binary(
        "PRESENTATION_AGENT_PDFTOPPM",
        "pdftoppm",
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/pdftoppm",
    )
    if not pdftoppm:
        raise ArtifactPreparationError("Neither PyMuPDF nor pdftoppm is available")
    prefix = output_dir / "page"
    proc = subprocess.run(
        [pdftoppm, "-png", "-r", "144", str(pdf_path), str(prefix)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ArtifactPreparationError(detail[:2000])
    original = sorted(output_dir.glob("page-*.png"))
    result: list[Path] = []
    for index, source in enumerate(original, start=1):
        target = output_dir / f"page-{index:03d}.png"
        if source != target:
            source.replace(target)
        result.append(target)
    return result


def _render_html_pages(html_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    node = _find_binary(
        "PRESENTATION_AGENT_NODE",
        "node",
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node",
    )
    if not node:
        raise ArtifactPreparationError("Node.js not found for HTML screenshot rendering")
    script = Path(__file__).with_name("html_screenshot.js")
    proc = subprocess.run(
        [node, str(script), str(html_path), str(output_dir)],
        cwd=str(Path(__file__).resolve().parents[2]),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise ArtifactPreparationError(detail[:2000])
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ArtifactPreparationError(f"HTML screenshot manifest was invalid: {exc}") from exc
    return [Path(item).resolve() for item in payload.get("images", []) if Path(item).exists()]


def _build_contact_sheet(images: list[Path], target: Path) -> Path | None:
    if not images:
        return None
    try:
        from PIL import Image, ImageOps, ImageDraw
    except ImportError:
        return None

    thumb_width = 360
    padding = 18
    label_height = 28
    columns = 3 if len(images) >= 6 else 2
    prepared: list[Any] = []
    max_height = 0
    for index, path in enumerate(images, start=1):
        with Image.open(path) as source:
            rgb = source.convert("RGB")
            ratio = thumb_width / max(rgb.width, 1)
            thumb = rgb.resize((thumb_width, max(1, int(rgb.height * ratio))))
        canvas = Image.new("RGB", (thumb_width, thumb.height + label_height), "white")
        canvas.paste(thumb, (0, label_height))
        ImageDraw.Draw(canvas).text((8, 6), f"{index:02d} · {path.name}", fill="#333333")
        prepared.append(canvas)
        max_height = max(max_height, canvas.height)

    rows = (len(prepared) + columns - 1) // columns
    sheet = Image.new(
        "RGB",
        (
            columns * thumb_width + (columns + 1) * padding,
            rows * max_height + (rows + 1) * padding,
        ),
        "#E9ECEF",
    )
    for index, image in enumerate(prepared):
        col = index % columns
        row = index // columns
        frame = ImageOps.expand(image, border=1, fill="#AAB2B8")
        sheet.paste(
            frame,
            (padding + col * (thumb_width + padding), padding + row * (max_height + padding)),
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target)
    return target


def _find_binary(env_name: str, command: str, bundled: Path) -> str | None:
    explicit = os.environ.get(env_name)
    if explicit and Path(explicit).exists():
        return explicit
    if bundled.exists():
        return str(bundled)
    return shutil.which(command)


def _probe_html_runtime(node: str | None, repo_root: Path) -> dict[str, Any]:
    if not node:
        return {}
    script = Path(__file__).with_name("html_screenshot.js")
    try:
        proc = subprocess.run(
            [node, str(script), "--doctor"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"error": str(exc)[:1000]}
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or f"Node.js exited {proc.returncode}").strip()
        return {"error": detail[:1000]}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"error": f"HTML runtime probe returned invalid JSON: {exc}"}
    if not isinstance(payload, dict):
        return {"error": "HTML runtime probe returned non-object JSON"}
    if payload.get("error"):
        payload["error"] = _compact_runtime_error(str(payload["error"]))
    return payload


def _dependency_status(
    name: str,
    available: bool,
    detail: str,
    *,
    unavailable_status: str = "missing",
) -> dict[str, str]:
    return {
        "name": name,
        "status": "ok" if available else unavailable_status,
        "detail": detail,
    }


def _compact_runtime_error(error: str, limit: int = 1000) -> str:
    lines = [line.strip() for line in error.splitlines() if line.strip()]
    if not lines:
        return "unknown browser launch error"
    markers = ("FATAL", "Permission denied", "Operation not permitted", "[err]")
    selected = [lines[0]]
    selected.extend(
        line
        for line in lines[1:]
        if any(marker in line for marker in markers)
    )
    return " | ".join(dict.fromkeys(selected))[:limit]
