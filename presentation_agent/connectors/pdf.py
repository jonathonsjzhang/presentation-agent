from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector


class PdfConnector(SuffixConnector):
    """Handle PDF input files.

    Extracts:
      - Full text via pdfplumber (page-by-page)
      - Each page rendered as a PNG image for visual analysis (PyMuPDF)
      - Page-level metadata (page number, text preview, image path)

    The downstream agent can ``Read`` the page images to analyze charts,
    tables, and layout that text extraction alone would miss.
    """

    name = "pdf_reader"
    suffixes = (".pdf",)

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        # -- text extraction --
        pages_text: list[str] = _extract_pdf_text(path)
        if not pages_text:
            raise ValueError(f"No readable text found in PDF: {path}")

        full_text = "\n".join(pages_text)
        first_line = pages_text[0].strip()[:120] if pages_text else path.name

        # -- page images --
        page_images = _render_pdf_pages(path)

        # -- build materials --
        materials: list[dict[str, Any]] = []
        for i, text in enumerate(pages_text):
            stripped = text.strip()
            if not stripped:
                continue
            materials.append({
                "claim": f"PDF 第 {i + 1} 页：{stripped[:80]}",
                "key_question": "这一页包含了什么关键信息？",
                "evidence": [stripped[:2000]],
                "so_what": "",
                "tag": f"pdf_page_{i + 1}",
            })

        result: dict[str, Any] = {
            "topic": first_line,
            "source_path": str(path),
            "source_type": "pdf",
            "target_agent": context.agent_id,
            "raw_text": full_text,
            "paragraphs": pages_text,
            "materials": materials,
        }

        if page_images:
            result["images"] = page_images
            result["images_note"] = (
                f"PDF 共 {len(pages_text)} 页，已渲染为 {len(page_images)} 张页面图片。"
                "每张图片的路径和页码见 images 字段。"
                "请使用 Read 工具逐页查看图片内容，提取图表、表格中的数据趋势、"
                "关键数字和结构关系，补充到分析中——不要仅依赖文字提取结果。"
            )

        return result


# ---------------------------------------------------------------------------
# PDF text extraction (pdfplumber)
# ---------------------------------------------------------------------------


def _extract_pdf_text(path: Path) -> list[str]:
    """Extract text from each page of a PDF using pdfplumber.

    Returns one string per page. Raises ImportError if pdfplumber is not
    installed.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "pdfplumber is required for PDF text extraction. "
            "Install it with: pip install pdfplumber"
        ) from None

    pages: list[str] = []
    skipped = 0
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(text)
            else:
                # Empty page — still count it (image-only pages)
                pages.append("")
                skipped += 1

    if not any(p for p in pages):
        raise ValueError(
            f"PDF 文本提取全部为空 ({path})。"
            "如果 PDF 是扫描件或纯图片，建议先将每个页面作为图片输入。"
        )

    return pages


# ---------------------------------------------------------------------------
# PDF page rendering (PyMuPDF)
# ---------------------------------------------------------------------------


def _render_pdf_pages(
    path: Path,
    output_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Render each PDF page as a PNG image using PyMuPDF (fitz).

    Returns a list of image metadata dicts (same shape as
    ``extract_docx_images`` output) so downstream agents see a unified
    ``images`` field.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        # Graceful degradation if PyMuPDF is not installed
        return []

    if output_dir is None:
        output_dir = path.parent / "pdf_pages"
    output_dir.mkdir(parents=True, exist_ok=True)

    images: list[dict[str, Any]] = []
    doc = fitz.open(path)

    for page_num in range(len(doc)):
        page = doc[page_num]
        # Render at 200 DPI for readability (standard screen is ~96-150)
        mat = fitz.Matrix(2.0, 2.0)  # 144 DPI equivalent
        pix = page.get_pixmap(matrix=mat)
        img_name = f"page_{page_num + 1:03d}.png"
        img_path = output_dir / img_name
        pix.save(img_path)

        images.append({
            "index": page_num + 1,
            "filename": img_name,
            "extracted_path": str(img_path.resolve()),
            "width_px": pix.width,
            "height_px": pix.height,
            "size_bytes": img_path.stat().st_size,
            "page_number": page_num + 1,
            "paragraph_index": page_num,
            "order_in_document": page_num + 1,
        })

    doc.close()
    return images
