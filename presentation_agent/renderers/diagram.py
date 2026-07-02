"""Deterministic visual assets for the formatted document renderer.

The module never fabricates values: labels, nodes, axes and relationships are
drawn exclusively from the formatted_material.v2 visual asset payload.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

COLORS = ("#006BA6", "#007A53", "#D46A00", "#7B61A8", "#64748B")


def _font(size: int):
    from PIL import ImageFont

    for candidate in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ):
        try:
            if Path(candidate).is_file():
                return ImageFont.truetype(candidate, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def _text(value: Any) -> str:
    return str(value) if value is not None else ""


def _labels(data: dict[str, Any]) -> list[str]:
    for key in ("nodes", "steps", "items", "categories", "labels"):
        values = data.get(key)
        if isinstance(values, list):
            labels = []
            for value in values:
                if isinstance(value, dict):
                    labels.append(_text(value.get("label") or value.get("name") or value.get("title")))
                else:
                    labels.append(_text(value))
            return [label for label in labels if label]
    return []


def _write_svg(asset: dict[str, Any], path: Path) -> None:
    data = asset.get("data") or {}
    labels = _labels(data)
    title = html.escape(_text(asset.get("title")))
    width, height = 1200, max(420, 170 + 105 * max(1, len(labels)))
    chunks = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        f'<text x="52" y="58" font-family="Arial,sans-serif" font-size="30" '
        f'font-weight="700" fill="#0B2545">{title}</text>',
    ]
    if labels:
        for index, label in enumerate(labels):
            y = 105 + index * 95
            chunks.append(
                f'<rect x="70" y="{y}" width="1060" height="64" rx="10" '
                f'fill="{COLORS[index % len(COLORS)]}" fill-opacity="0.10" '
                f'stroke="{COLORS[index % len(COLORS)]}" stroke-width="2"/>'
            )
            chunks.append(
                f'<text x="102" y="{y + 41}" font-family="Arial,sans-serif" font-size="23" '
                f'fill="#253746">{html.escape(label)}</text>'
            )
            if index < len(labels) - 1:
                chunks.append(
                    f'<path d="M600 {y + 64} L600 {y + 91}" stroke="#64748B" '
                    f'stroke-width="3" marker-end="url(#arrow)"/>'
                )
        chunks.insert(
            2,
            '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="5" '
            'refY="3" orient="auto"><path d="M0,0 L0,6 L6,3 z" fill="#64748B"/>'
            "</marker></defs>",
        )
    else:
        payload = html.escape(json.dumps(data, ensure_ascii=False, separators=(", ", ": ")))
        chunks.append(
            f'<text x="70" y="130" font-family="Arial,sans-serif" font-size="20" '
            f'fill="#475569">{payload}</text>'
        )
    chunks.append("</svg>")
    path.write_text("".join(chunks), encoding="utf-8")


def _write_png(asset: dict[str, Any], path: Path) -> None:
    from PIL import Image, ImageDraw

    data = asset.get("data") or {}
    labels = _labels(data)
    width, height = 1200, max(420, 170 + 105 * max(1, len(labels)))
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((52, 30), _text(asset.get("title")), fill="#0B2545", font=_font(30))
    if labels:
        for index, label in enumerate(labels):
            y = 105 + index * 95
            color = COLORS[index % len(COLORS)]
            draw.rounded_rectangle((70, y, 1130, y + 64), radius=10, fill="#F4F7FA", outline=color, width=3)
            draw.text((102, y + 17), label, fill="#253746", font=_font(23))
            if index < len(labels) - 1:
                draw.line((600, y + 64, 600, y + 91), fill="#64748B", width=3)
                draw.polygon(((592, y + 83), (608, y + 83), (600, y + 92)), fill="#64748B")
    else:
        draw.multiline_text(
            (70, 110),
            json.dumps(data, ensure_ascii=False, indent=2),
            fill="#475569",
            font=_font(20),
            spacing=8,
        )
    image.save(path, format="PNG")


def render_svg_with_png_fallback(asset: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    """Write an SVG source plus a deterministic PNG compatibility fallback."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = str(asset.get("asset_id") or "visual_asset")
    svg_path = output_dir / f"{stem}.svg"
    png_path = output_dir / f"{stem}.png"
    _write_svg(asset, svg_path)
    _write_png(asset, png_path)
    return svg_path, png_path
