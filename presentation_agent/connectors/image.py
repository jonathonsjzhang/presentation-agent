from __future__ import annotations

import io
import struct
from pathlib import Path
from typing import Any

from presentation_agent.connectors.base import ConnectorContext, SuffixConnector


class ImageConnector(SuffixConnector):
    """Handle standalone image files (PNG, JPEG, GIF, BMP, WebP).

    Don't extract content from the image — just read metadata and pass the
    path through so the downstream agent can use its multimodal ``Read`` tool
    to inspect chart data, trends, and structure visually.
    """

    name = "image_reader"
    suffixes = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")

    def load(self, path: Path, context: ConnectorContext) -> dict[str, Any]:
        w, h, fmt = _image_meta(path)
        result: dict[str, Any] = {
            "topic": f"图片材料：{path.name}",
            "source_path": str(path),
            "source_type": "image",
            "target_agent": context.agent_id,
            "raw_text": "",
            "paragraphs": [],
            "materials": [
                {
                    "claim": f"图片：{path.name}",
                    "key_question": "这张图表/图片包含了什么关键信息？",
                    "evidence": [],
                    "so_what": "",
                    "tag": "visual_input",
                }
            ],
            "images": [
                {
                    "index": 1,
                    "filename": path.name,
                    "extracted_path": str(path.resolve()),
                    "width_px": w,
                    "height_px": h,
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                    "format": fmt,
                    "paragraph_index": None,
                    "order_in_document": 1,
                }
            ],
            "images_note": (
                "输入包含一张图片。请使用 Read 工具查看图片内容，"
                "提取图表中的数据趋势、关键数字、结构和视觉线索，"
                "补充到分析中——不要仅依赖文件名。"
            ),
        }
        return result


# ---------------------------------------------------------------------------
# image metadata (Pillow with pure-Python fallback)
# ---------------------------------------------------------------------------


def _image_meta(path: Path) -> tuple[int | None, int | None, str | None]:
    """Read width, height, and format from an image file.

    Tries Pillow first; falls back to header parsing for PNG/JPEG/GIF/BMP.
    """
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size[0], img.size[1], (img.format or "").lower()
    except Exception:
        pass

    # Pure-Python fallback for common formats
    try:
        data = path.read_bytes()
        suffix = path.suffix.lower()

        if suffix == ".png" and len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
            w = struct.unpack(">I", data[16:20])[0]
            h = struct.unpack(">I", data[20:24])[0]
            return w, h, "png"

        if suffix in (".jpg", ".jpeg"):
            i = 2
            while i < len(data) - 9:
                if data[i] == 0xFF and data[i + 1] in (0xC0, 0xC1, 0xC2):
                    h = struct.unpack(">H", data[i + 5 : i + 7])[0]
                    w = struct.unpack(">H", data[i + 7 : i + 9])[0]
                    return w, h, "jpeg"
                i += 2 + struct.unpack(">H", data[i + 2 : i + 4])[0]

        if suffix == ".gif" and len(data) >= 10 and data[:6] in (b"GIF89a", b"GIF87a"):
            w = struct.unpack("<H", data[6:8])[0]
            h = struct.unpack("<H", data[8:10])[0]
            return w, h, "gif"

        if suffix == ".bmp" and len(data) >= 26 and data[:2] == b"BM":
            w = struct.unpack("<I", data[18:22])[0]
            h = struct.unpack("<I", data[22:26])[0]
            return w, h, "bmp"

        if suffix == ".webp" and len(data) >= 30 and data[:4] == b"RIFF":
            w = struct.unpack("<H", data[26:28])[0] + 1
            h = struct.unpack("<H", data[28:30])[0] + 1
            return w, h, "webp"
    except Exception:
        pass

    return None, None, None
