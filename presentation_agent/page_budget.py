"""Deterministic body-page budget helpers for document reports.

The user-facing report keeps methods/limitations and Q&A, but the delivery
budget applies only to the title, Executive Summary, and main argument.  Page
counts are measured from an internal body-only shadow DOCX rendered with the
same document renderer and (at Format time) the same visual selections.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


_EXCLUDED_BODY_HEADINGS = {
    "方法与边界",
    "方法与限制",
    "研究方法与边界",
    "听众可能追问的问题",
    "听众可能提出的问题",
}


def _normalize_heading(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^[一二三四五六七八九十\d]+[、.．]\s*", "", text)
    return text.strip()


def is_excluded_body_heading(value: Any) -> bool:
    return _normalize_heading(value) in _EXCLUDED_BODY_HEADINGS


def extract_body_markdown(markdown: str) -> str:
    """Return title + ES + main sections, excluding methods and Q&A."""

    output: list[str] = []
    include = True
    for raw in str(markdown or "").splitlines():
        if raw.startswith("## "):
            include = not is_excluded_body_heading(raw[3:])
        if include:
            output.append(raw)
    return "\n".join(output).strip() + "\n"


def body_character_count(markdown: str) -> int:
    body = extract_body_markdown(markdown)
    meaningful: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\|?[\s|:-]+\|?", stripped):
            continue
        meaningful.append(re.sub(r"[#>*_`|\-]", "", stripped))
    return len(re.sub(r"\s+", "", "".join(meaningful)))


def executive_summary_character_count(markdown: str) -> int:
    """Count the Executive Summary only, excluding its Markdown heading."""

    lines: list[str] = []
    in_summary = False
    for raw in str(markdown or "").splitlines():
        if raw.startswith("## "):
            heading = _normalize_heading(raw[3:]).lower()
            if in_summary:
                break
            in_summary = heading == "executive summary"
            continue
        if in_summary:
            lines.append(raw)
    return body_character_count("\n".join(lines))


def parse_body_page_limit(report_charter: dict[str, Any]) -> int | None:
    """Parse a document page limit from the charter's user-facing wording."""

    targets = report_charter.get("requested_delivery_targets") or []
    if targets and "document" not in {str(item) for item in targets}:
        return None
    candidates = [str(report_charter.get("report_length") or "")]
    candidates.extend(str(item) for item in report_charter.get("constraints") or [])
    for text in candidates:
        if "PPT" in text.upper():
            continue
        match = re.search(r"(\d+)\s*页", text)
        if match:
            value = int(match.group(1))
            return value if value > 0 else None
    return None


def derive_delivery_budget(report_charter: dict[str, Any]) -> dict[str, Any]:
    explicit = report_charter.get("page_budget")
    explicit = explicit if isinstance(explicit, dict) else {}
    explicit_body_limit = explicit.get("body_page_limit")
    limit = (
        explicit_body_limit
        if isinstance(explicit_body_limit, int) and explicit_body_limit > 0
        else parse_body_page_limit(report_charter)
    )
    policy = {
        "appendix_policy": str(explicit.get("appendix_policy") or "allowed"),
        "qa_included": bool(explicit.get("qa_included", True)),
    }
    total_limit = explicit.get("total_page_limit")
    if isinstance(total_limit, int) and total_limit > 0:
        policy["total_page_limit"] = total_limit
    if limit is None:
        return policy if explicit else {}
    # Keep the writing budget linear and predictable: 800-900 characters per
    # requested body page, with the midpoint as the generation target.  The
    # Executive Summary is governed by semantic completeness, not a fixed
    # character band.
    report_char_min = limit * 800
    report_char_target = limit * 850
    automatic_page_tolerance = 1
    maximum_page_limit = limit + automatic_page_tolerance
    report_char_warning = limit * 900
    budget = {
        "requested_body_page_limit": limit,
        "body_page_limit": limit,
        "automatic_page_tolerance": automatic_page_tolerance,
        "automatic_body_page_limit": maximum_page_limit,
        "maximum_body_page_limit": maximum_page_limit,
        "counting_policy": "body_only",
        "excluded_section_roles": ["methods_and_limitations", "qa"],
        "body_char_min": report_char_min,
        "body_char_target": report_char_target,
        "body_char_warning": report_char_warning,
        # Character counts guide drafting and warn about likely overflow.  The
        # rendered page count remains authoritative, so a dense but readable
        # document is not rejected by this estimate alone.
        "report_body_char_limit": maximum_page_limit * 900,
        "body_char_enforcement": "advisory",
        "max_body_visuals": min(3, max(1, limit)),
    }
    budget.update(policy)
    return budget


def _filter_body_visuals(formatted: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(formatted)
    if isinstance(result.get("visuals"), list):
        result["visuals"] = [
            item
            for item in result["visuals"]
            if isinstance(item, dict)
            and not is_excluded_body_heading(item.get("section_heading"))
        ]
    if isinstance(result.get("visual_assets"), list):
        result["visual_assets"] = [
            item
            for item in result["visual_assets"]
            if isinstance(item, dict)
            and not any(
                is_excluded_body_heading(ref)
                for ref in item.get("source_section_ids") or []
            )
        ]
    return result


def _pdf_page_count(pdf_path: Path) -> int:
    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        completed = subprocess.run(
            [pdfinfo, str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        match = re.search(r"(?m)^Pages:\s*(\d+)\s*$", completed.stdout)
        if match:
            return int(match.group(1))
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf_path)).pages)
    except Exception as exc:  # pragma: no cover - dependency fallback
        raise RuntimeError("无法读取正文影子稿 PDF 页数；需要 pdfinfo 或 pypdf") from exc


def _find_soffice() -> str | None:
    executable = Path(sys.executable).resolve()
    if len(executable.parents) >= 3:
        bundled = executable.parents[2] / "bin" / "override" / "soffice"
        if bundled.is_file():
            return str(bundled)
    return shutil.which("soffice")


def count_docx_pages(docx_path: Path) -> int:
    """Render DOCX with LibreOffice and return its actual PDF page count."""

    soffice = _find_soffice()
    if not soffice:
        raise RuntimeError("正文页数硬约束需要 LibreOffice/soffice")
    temp_base = "/private/tmp" if sys.platform == "darwin" and Path("/private/tmp").is_dir() else None
    with tempfile.TemporaryDirectory(
        prefix="body_page_audit_", dir=temp_base
    ) as temp_dir:
        temp = Path(temp_dir)
        profile = temp / "profile"
        output = temp / "output"
        profile.mkdir()
        output.mkdir()
        env = dict(os.environ)
        env["HOME"] = str(temp)
        env["XDG_CONFIG_HOME"] = str(temp / "xdg_config")
        env["XDG_CACHE_HOME"] = str(temp / "xdg_cache")
        Path(env["XDG_CONFIG_HOME"]).mkdir()
        Path(env["XDG_CACHE_HOME"]).mkdir()
        if temp_base:
            env["TMPDIR"] = temp_base
            env["TEMP"] = temp_base
            env["TMP"] = temp_base
        completed = subprocess.run(
            [
                soffice,
                f"-env:UserInstallation={profile.resolve().as_uri()}",
                "--invisible",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(output),
                str(docx_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
        pdf_path = output / f"{docx_path.stem}.pdf"
        if completed.returncode != 0 or not pdf_path.is_file():
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"正文影子稿渲染失败: {detail or '未生成 PDF'}")
        return _pdf_page_count(pdf_path)


def audit_document_body_pages(
    *,
    report: dict[str, Any],
    formatted: dict[str, Any],
    out_dir: Path,
    body_page_limit: int,
    maximum_body_page_limit: int | None = None,
    user_approved_body_page_limit: int | None = None,
    stage: str,
    renderer: Callable[..., Any] | None = None,
    page_counter: Callable[[Path], int] | None = None,
) -> dict[str, Any]:
    """Render and measure an internal body-only shadow document."""

    from presentation_agent.renderers.formatted_document_v2 import (
        render_formatted_document_v2,
    )

    render = renderer or render_formatted_document_v2
    count_pages = page_counter or count_docx_pages
    shadow_report = copy.deepcopy(report)
    shadow_report["report_markdown"] = extract_body_markdown(
        str(report.get("report_markdown") or "")
    )
    shadow_formatted = _filter_body_visuals(formatted)
    shadow_formatted.update(
        {
            "agent_id": "format",
            "schema": "formatted_material.v2",
            "delivery_target": "document",
        }
    )
    audit_dir = Path(out_dir) / "body_budget_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    result = render(
        shadow_formatted,
        shadow_report,
        audit_dir,
        file_stem=f"body_shadow_{stage}",
    )
    requested_limit = int(body_page_limit)
    automatic_limit = requested_limit + 1
    maximum_limit = (
        int(maximum_body_page_limit)
        if isinstance(maximum_body_page_limit, int)
        and maximum_body_page_limit >= requested_limit
        else requested_limit + 1
    )
    audit: dict[str, Any] = {
        "stage": stage,
        "counting_policy": "body_only",
        "requested_body_page_limit": requested_limit,
        "body_page_limit": requested_limit,
        "automatic_page_tolerance": 1,
        "automatic_body_page_limit": automatic_limit,
        "maximum_body_page_limit": maximum_limit,
        "body_chars": body_character_count(shadow_report["report_markdown"]),
        "excluded_sections": ["方法与边界", "听众可能追问的问题"],
        "visual_count": len(shadow_formatted.get("visuals") or []),
        "available": False,
        "passed": False,
    }
    if getattr(result, "status", "") != "rendered" or not getattr(
        result, "output_path", None
    ):
        audit["detail"] = f"正文影子稿 DOCX 生成失败: {getattr(result, 'detail', '')}"
        return audit
    try:
        page_count = count_pages(Path(str(result.output_path)))
    except Exception as exc:
        audit["detail"] = str(exc)
        return audit
    audit.update(
        {
            "available": True,
            "body_page_count": page_count,
            "passed": page_count <= maximum_limit,
            "within_requested_limit": page_count <= requested_limit,
            "automatic_tolerance_used": (
                requested_limit < page_count <= automatic_limit
            ),
            "within_effective_limit": page_count <= maximum_limit,
            "requires_user_decision": page_count > maximum_limit,
        }
    )
    if (
        isinstance(user_approved_body_page_limit, int)
        and user_approved_body_page_limit > automatic_limit
    ):
        audit["user_approved_body_page_limit"] = user_approved_body_page_limit
        audit["detail"] = (
            f"正文实际渲染 {page_count} 页；目标 {requested_limit} 页，"
            f"自动容差上限 {automatic_limit} 页，"
            f"用户批准上限 {user_approved_body_page_limit} 页"
        )
    else:
        audit["detail"] = (
            f"正文实际渲染 {page_count} 页；目标 {requested_limit} 页，"
            f"自动容差上限 {automatic_limit} 页"
        )
    return audit
