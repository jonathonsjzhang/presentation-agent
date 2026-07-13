from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector


class TextConnector(SuffixConnector):
    """Read plain text and Markdown as stable text blocks."""

    name = "text_reader"
    suffixes = (".txt", ".md")

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        text = _read_text(path)
        blocks = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]
        if not blocks and text.strip():
            blocks = [text.strip()]
        if not blocks:
            raise ValueError(f"No readable text found in {path.suffix.upper()}: {path}")
        return {
            "topic": _topic(path, blocks),
            "source_path": str(path),
            "source_type": path.suffix.lower().lstrip("."),
            "target_agent": context.agent_id,
            "raw_text": text,
            "paragraphs": blocks,
            "materials": [
                {
                    "claim": block.splitlines()[0][:80],
                    "key_question": "这段材料提供了什么可核验信息？",
                    "evidence": [block],
                    "so_what": "",
                    "tag": "source_text",
                }
                for block in blocks
            ],
        }


def _read_text(path: Path) -> str:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise IOError(f"无法以任何已知编码读取 {path}: {last_error}")


def _topic(path: Path, blocks: list[str]) -> str:
    first = blocks[0].splitlines()[0].strip()
    if path.suffix.lower() == ".md":
        first = re.sub(r"^#{1,6}\s+", "", first)
    return first[:120] or path.stem
