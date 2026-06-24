from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


class DocxConnector(SuffixConnector):
    name = "docx_reader"
    suffixes = (".docx",)

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        if context.agent_id == "storyline_design":
            return docx_to_storyline_input(path)
        paragraphs = extract_docx_paragraphs(path)
        if not paragraphs:
            raise ValueError(f"No readable text found in DOCX: {path}")
        return {
            "topic": paragraphs[0],
            "source_path": str(path),
            "source_type": "docx",
            "target_agent": context.agent_id,
            "raw_text": "\n".join(paragraphs),
            "paragraphs": paragraphs,
            "materials": group_paragraphs_into_materials(paragraphs[1:]),
        }


def docx_to_storyline_input(path: Path) -> dict[str, Any]:
    paragraphs = extract_docx_paragraphs(path)
    if not paragraphs:
        raise ValueError(f"No readable text found in DOCX: {path}")

    topic = paragraphs[0]
    body = paragraphs[1:]
    materials = group_paragraphs_into_materials(body)
    return {
        "topic": topic,
        "audience": "管理层",
        "objective": "将 Word 分析稿整理为可汇报的 storyline",
        "source_path": str(path),
        "source_type": "docx",
        "raw_text": "\n".join(paragraphs),
        "materials": materials,
    }


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
