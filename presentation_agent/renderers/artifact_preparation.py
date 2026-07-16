"""Prepare real deliverable pages for renderer-owned visual quality checks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PreparedPages:
    artifact_path: str
    format: str
    visual_paths: list[str] = field(default_factory=list)
    contact_sheet_path: str | None = None
    warnings: list[str] = field(default_factory=list)


class PagePreparationError(RuntimeError):
    pass


def prepare_artifact_pages(artifact_path: Path, output_dir: Path) -> PreparedPages:
    artifact_path = Path(artifact_path).expanduser().resolve()
    if not artifact_path.is_file():
        raise PagePreparationError(f"Deliverable does not exist: {artifact_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    fmt = _infer_format(artifact_path)
    warnings: list[str] = []
    visual_paths: list[Path] = []
    try:
        if fmt in {"ppt", "document"}:
            pdf_path = _office_to_pdf(artifact_path, output_dir)
            visual_paths = _render_pdf_pages(pdf_path, output_dir / "pages")
        else:
            visual_paths = _render_html_pages(artifact_path, output_dir / "pages")
    except Exception as exc:
        warnings.append(f"page rendering failed: {exc}")

    contact_sheet = _build_contact_sheet(
        visual_paths,
        output_dir / "contact-sheet.png",
    )
    if not visual_paths:
        warnings.append("no real page snapshots were produced")
    return PreparedPages(
        artifact_path=str(artifact_path),
        format=fmt,
        visual_paths=[str(path.resolve()) for path in visual_paths],
        contact_sheet_path=str(contact_sheet.resolve()) if contact_sheet else None,
        warnings=warnings,
    )


def _infer_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".pptx", ".ppt"}:
        return "ppt"
    if suffix in {".docx", ".doc"}:
        return "document"
    if suffix in {".html", ".htm"}:
        return "html"
    raise PagePreparationError(
        f"Unsupported deliverable format {suffix!r}; expected PPTX, DOCX, or HTML"
    )


def _office_to_pdf(path: Path, output_dir: Path) -> Path:
    soffice = _find_binary(
        "PRESENTATION_AGENT_SOFFICE",
        "soffice",
        Path.home()
        / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/soffice",
    )
    if not soffice:
        raise PagePreparationError("LibreOffice/soffice not found")

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
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
        check=False,
    )
    expected = pdf_dir / f"{path.stem}.pdf"
    if proc.returncode != 0 or not expected.exists():
        detail = (proc.stderr or proc.stdout or "").strip()
        raise PagePreparationError(detail or f"soffice exited {proc.returncode}")
    return expected


def _render_pdf_pages(pdf_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        import fitz

        result: list[Path] = []
        document = fitz.open(pdf_path)
        try:
            for index, page in enumerate(document, start=1):
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(2.0, 2.0),
                    alpha=False,
                )
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
        raise PagePreparationError("Neither PyMuPDF nor pdftoppm is available")
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
        raise PagePreparationError(detail[:2000])
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
        raise PagePreparationError("Node.js not found for HTML screenshot rendering")
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
        raise PagePreparationError(detail[:2000])
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise PagePreparationError(
            f"HTML screenshot manifest was invalid: {exc}"
        ) from exc
    return [
        Path(item).resolve()
        for item in payload.get("images", [])
        if Path(item).exists()
    ]


def _build_contact_sheet(images: list[Path], target: Path) -> Path | None:
    if not images:
        return None
    try:
        from PIL import Image, ImageDraw, ImageOps
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
        canvas = Image.new(
            "RGB",
            (thumb_width, thumb.height + label_height),
            "white",
        )
        canvas.paste(thumb, (0, label_height))
        ImageDraw.Draw(canvas).text(
            (8, 6),
            f"{index:02d} · {path.name}",
            fill="#333333",
        )
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
    for index, prepared_image in enumerate(prepared):
        col = index % columns
        row = index // columns
        frame = ImageOps.expand(prepared_image, border=1, fill="#AAB2B8")
        sheet.paste(
            frame,
            (
                padding + col * (thumb_width + padding),
                padding + row * (max_height + padding),
            ),
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
