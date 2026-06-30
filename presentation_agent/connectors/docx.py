from __future__ import annotations

import io
import re
import struct
import zipfile
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DRAWING_NS = {
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}
IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp", ".svg")
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


class DocxConnector(SuffixConnector):
    name = "docx_reader"
    suffixes = (".docx",)

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        if context.agent_id == "storyline_design":
            return docx_to_storyline_input(path)
        paragraphs = extract_docx_paragraphs(path)
        if not paragraphs:
            raise ValueError(f"No readable text found in DOCX: {path}")

        images = extract_docx_images(path)
        result: dict[str, Any] = {
            "topic": paragraphs[0],
            "source_path": str(path),
            "source_type": "docx",
            "target_agent": context.agent_id,
            "raw_text": "\n".join(paragraphs),
            "paragraphs": paragraphs,
            "materials": group_paragraphs_into_materials(paragraphs[1:]),
        }
        if images:
            result["images"] = images
            result["images_note"] = (
                f"本文档包含 {len(images)} 张内嵌图片（图表/截图）。"
                "每张图片的路径、尺寸和所在段落位置见 images 字段。"
                "请使用 Read 工具逐张查看图片内容，提取图表中的数据趋势、"
                "关键数字、拐点和结构关系，补充到分析中——不要仅依赖文字描述。"
            )
        return result


def docx_to_storyline_input(path: Path) -> dict[str, Any]:
    paragraphs = extract_docx_paragraphs(path)
    if not paragraphs:
        raise ValueError(f"No readable text found in DOCX: {path}")

    topic = paragraphs[0]
    body = paragraphs[1:]
    materials = group_paragraphs_into_materials(body)
    images = extract_docx_images(path)
    result: dict[str, Any] = {
        "topic": topic,
        "audience": "管理层",
        "objective": "将 Word 分析稿整理为可汇报的 storyline",
        "source_path": str(path),
        "source_type": "docx",
        "raw_text": "\n".join(paragraphs),
        "materials": materials,
    }
    if images:
        result["images"] = images
        result["images_note"] = (
            f"本文档包含 {len(images)} 张内嵌图片（图表/截图）。"
            "请使用 Read 工具逐张查看图片内容。"
        )
    return result


def extract_docx_paragraphs(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as docx:
        xml = docx.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", WORD_NS):
        texts = [node.text or "" for node in para.findall(".//w:t", WORD_NS)]
        text = normalize_text("".join(texts))
        if text:
            paragraphs.append(text)
    return paragraphs


def group_paragraphs_into_materials(paragraphs: list[str]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for text in paragraphs:
        if is_noise_heading(text):
            continue
        if is_speaker_attribution(text):
            if current is not None:
                current.setdefault("evidence", []).append(text)
            continue

        if looks_like_heading(text):
            if current is not None:
                groups.append(finalize_group(current))
            current = {
                "claim": text,
                "key_question": infer_key_question(text),
                "evidence": [],
                "tag": "mainline",
            }
            continue

        if current is None:
            current = {
                "claim": text[:60],
                "key_question": infer_key_question(text[:60]),
                "evidence": [],
                "tag": "mainline",
            }
        current.setdefault("evidence", []).append(text)

    if current is not None:
        groups.append(finalize_group(current))

    groups = dedupe_groups(groups)
    return groups or [
        {
            "claim": paragraphs[0][:80],
            "key_question": infer_key_question(paragraphs[0][:80]),
            "evidence": paragraphs[1:],
            "so_what": "",
            "tag": "mainline",
            "open_questions": ["无法自动提炼管理层含义，需人工补充"],
        }
    ]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    evidence = list(group.get("evidence", []))
    so_what = infer_so_what(group["claim"], evidence)
    result = {
        "claim": group["claim"],
        "key_question": group.get("key_question") or infer_key_question(group["claim"]),
        "evidence": evidence,
        "so_what": so_what,
        "tag": group.get("tag", "mainline"),
    }
    open_questions: list[str] = []
    if not evidence:
        open_questions.append("缺少支撑论据，需补充来源和数据")
    if not so_what:
        open_questions.append("无法自动提炼管理层含义，需人工补充")
    if open_questions:
        result["open_questions"] = open_questions
    return result


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def looks_like_heading(text: str) -> bool:
    if len(text) > 45:
        return False
    if is_noise_heading(text):
        return False
    if "=" in text:
        return False
    if numeric_density(text) > 0.18:
        return False
    if text.startswith(("“", "\"", "'", "---")):
        return False
    if text.endswith(("。", "；", ";", ".", "，", ",")):
        return False
    if "：" in text and len(text) > 24:
        return False
    return True


def is_speaker_attribution(text: str) -> bool:
    return text.startswith("---") or bool(re.match(r"^[男女]\s*\d+岁", text))


def is_noise_heading(text: str) -> bool:
    stripped = text.strip()
    if stripped in {"Takeaway", "Takeaway：", "Takeaway:"}:
        return True
    if stripped.startswith(("Takeaway：", "Takeaway:")):
        return True
    return False


def numeric_density(text: str) -> float:
    if not text:
        return 0.0
    numeric_chars = sum(1 for char in text if char.isdigit() or char in ".%+-,，")
    return numeric_chars / len(text)


def dedupe_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for group in groups:
        key = canonical_claim(group["claim"])
        if not key:
            continue
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = group
            order.append(key)
            continue
        if len(group.get("evidence", [])) > len(existing.get("evidence", [])):
            by_key[key] = group
    return [by_key[key] for key in order]


def canonical_claim(claim: str) -> str:
    text = claim.replace("Takeaway：", "").replace("Takeaway:", "")
    text = re.sub(r"^[A-Za-z]{0,8}用户", "", text)
    text = re.sub(r"[：:，,。；;\s]+", "", text)
    return text[:32]


def infer_key_question(claim: str) -> str:
    if "时长" in claim:
        return "用户时长变化背后的核心驱动是什么？"
    if "场景" in claim:
        return "哪些场景在推动用户行为变化？"
    if "信任" in claim:
        return "用户信任如何影响后续使用和切换意愿？"
    return "这个判断如何支撑本次汇报目标？"


def infer_so_what(claim: str, evidence: list[str]) -> str:
    if "复杂" in claim or any("复杂" in item for item in evidence):
        return "应优先识别并服务长链路、高信任成本场景，把时长增长转化为稳定使用惯性。"
    if "信任" in claim or any("信任" in item for item in evidence):
        return "应把低风险试用场景作为入口，再引导用户迁移到高价值复杂任务。"
    if "时长" in claim:
        return "管理层应从人均时长、单次时长、使用次数和重度用户占比拆解增长质量。"
    return ""


# ---------------------------------------------------------------------------
# docx image extraction
# ---------------------------------------------------------------------------


def extract_docx_images(
    path: Path,
    output_dir: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Extract embedded images from a .docx file.

    Returns a list of dicts, one per image:
      - index: 1-based occurrence order in the document
      - filename: original file name inside the docx
      - extracted_path: absolute path to the extracted file
      - width_px / height_px: pixel dimensions (where detectable)
      - size_bytes: file size
      - paragraph_index: index of the paragraph *after* the image
      - order_in_document: 1-based position in document flow

    Images are written to ``output_dir`` (defaults to ``path.parent / "images"``).
    """
    if output_dir is None:
        output_dir = path.parent / "images"
    output_dir.mkdir(parents=True, exist_ok=True)

    images: list[dict[str, Any]] = []
    embedded_contents: dict[str, bytes] = {}
    media_paths: list[tuple[str, int]] = []

    with zipfile.ZipFile(path) as docx:
        media_names = sorted(
            n for n in docx.namelist()
            if n.startswith("word/media/") and n.lower().endswith(IMG_EXTS)
        )
        for idx, name in enumerate(media_names):
            embedded_contents[name] = docx.read(name)
            media_paths.append((name, idx))

        if not media_paths:
            return []

        xml_bytes = docx.read("word/document.xml")
    root = ET.fromstring(xml_bytes)

    # Build ordered list of paragraphs (same logic as extract_docx_paragraphs)
    para_elements = root.findall(".//w:p", WORD_NS)
    image_para_map: dict[int, int] = {}
    for pi, para in enumerate(para_elements):
        drawings = para.findall(".//wp:inline", DRAWING_NS)
        drawings += para.findall(".//wp:anchor", DRAWING_NS)
        for drawing in drawings:
            blip = drawing.find(".//a:blip", DRAWING_NS)
            if blip is not None:
                embed = blip.get(f"{{{DRAWING_NS['r']}}}embed")
                if embed:
                    rid_map = _get_image_rid_map(path, media_names)
                    media_name = rid_map.get(embed, "")
                    if media_name:
                        for mi, (mn, _) in enumerate(media_paths):
                            if mn == media_name:
                                image_para_map[mi] = pi

    for media_idx, (media_name, order) in enumerate(media_paths):
        data = embedded_contents.get(media_name)
        if data is None:
            continue

        basename = Path(media_name).name
        safe_name = f"image_{order + 1}_{basename}"
        dest = output_dir / safe_name
        dest.write_bytes(data)

        w, h = _image_dimensions(data, Path(media_name).suffix.lower())

        images.append({
            "index": order + 1,
            "filename": basename,
            "extracted_path": str(dest.resolve()),
            "width_px": w,
            "height_px": h,
            "size_bytes": len(data),
            "paragraph_index": image_para_map.get(media_idx),
        })

    images.sort(key=lambda item: (
        item["paragraph_index"] if item["paragraph_index"] is not None else 9999,
        item["index"],
    ))
    for i, img in enumerate(images):
        img["order_in_document"] = i + 1

    return images


def _get_image_rid_map(docx_path: Path, media_names: list[str]) -> dict[str, str]:
    try:
        with zipfile.ZipFile(docx_path) as docx:
            rels_xml = docx.read("word/_rels/document.xml.rels")
    except KeyError:
        return {}
    root = ET.fromstring(rels_xml)
    rid_map: dict[str, str] = {}
    for rel in root.findall(f"{{{REL_NS}}}Relationship"):
        target = rel.get("Target", "")
        rid = rel.get("Id", "")
        if target.startswith("media/"):
            full = f"word/{target}"
            if full in media_names:
                rid_map[rid] = full
    return rid_map


def _image_dimensions(data: bytes, suffix: str) -> tuple[Optional[int], Optional[int]]:
    try:
        if suffix == ".png":
            if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
                w = struct.unpack(">I", data[16:20])[0]
                h = struct.unpack(">I", data[20:24])[0]
                return w, h
        elif suffix in (".jpg", ".jpeg"):
            i = 2
            while i < len(data) - 9:
                if data[i] == 0xFF and data[i + 1] in (0xC0, 0xC1, 0xC2):
                    h = struct.unpack(">H", data[i + 5: i + 7])[0]
                    w = struct.unpack(">H", data[i + 7: i + 9])[0]
                    return w, h
                i += 2 + struct.unpack(">H", data[i + 2: i + 4])[0]
        elif suffix == ".gif":
            if len(data) >= 10 and data[:6] in (b"GIF89a", b"GIF87a"):
                w = struct.unpack("<H", data[6:8])[0]
                h = struct.unpack("<H", data[8:10])[0]
                return w, h
        elif suffix == ".bmp":
            if len(data) >= 26 and data[:2] == b"BM":
                w = struct.unpack("<I", data[18:22])[0]
                h = struct.unpack("<I", data[22:26])[0]
                return w, h
    except Exception:
        pass
    return None, None
