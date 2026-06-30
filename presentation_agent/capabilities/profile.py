from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from presentation_agent.capabilities.models import CapabilityError
from presentation_agent.io import read_json


@dataclass(frozen=True)
class ReportProfile:
    audience: str
    report_type: str
    output_format: str
    version: str = "v1"

    def to_dict(self) -> dict[str, str]:
        return {
            "audience": self.audience,
            "report_type": self.report_type,
            "output_format": self.output_format,
            "version": self.version,
        }


def normalize_report_profile(
    data: Mapping[str, Any],
    *,
    root: Optional[Path] = None,
    strict: bool = True,
    allow_freeform_audience: bool = False,
) -> ReportProfile:
    config = _load_config(root)
    source = data.get("report_charter") if isinstance(data.get("report_charter"), Mapping) else data
    raw_audience = source.get("audience", "")
    if isinstance(raw_audience, Mapping):
        raw_audience = raw_audience.get("primary", "")
    values = {
        "audience": _normalize_value("audience", raw_audience, config),
        "report_type": _normalize_value("report_type", source.get("report_type", "deep_dive"), config),
        "output_format": _normalize_value(
            "output_format",
            source.get("output_format", source.get("material_format", "ppt")),
            config,
        ),
    }
    if strict:
        for dimension, value in values.items():
            allowed = set(config.get("dimensions", {}).get(dimension, []))
            if value not in allowed:
                if dimension == "audience" and allow_freeform_audience:
                    values["audience"] = str(raw_audience).strip()
                    continue
                raise CapabilityError(
                    f"Unsupported {dimension}={value!r}; allowed values: {sorted(allowed)}"
                )
    return ReportProfile(**values)


def _load_config(root: Optional[Path]) -> dict[str, Any]:
    defaults = {
        "dimensions": {
            "audience": ["board", "exec_office", "strategy_lead", "business_team", "external"],
            "report_type": ["deep_dive", "business_progress", "quick_sync"],
            "output_format": ["document", "ppt", "html"],
        },
        "aliases": {
            "audience": {
                "董事会": "board",
                "总办": "exec_office",
                "战略负责人": "strategy_lead",
                "业务团队": "business_team",
                "外部分享": "external",
            },
            "report_type": {
                "深度分析": "deep_dive",
                "业务进展汇报": "business_progress",
                "快速同步": "quick_sync",
            },
            "output_format": {
                "文档": "document",
                "word": "document",
                "docx": "document",
                "幻灯片": "ppt",
                "网页": "html",
            },
        },
    }
    if root is None:
        return defaults
    config = read_json(root / "configs" / "capabilities.json", default={})
    return config if config.get("dimensions") else defaults


def _normalize_value(dimension: str, value: Any, config: Mapping[str, Any]) -> str:
    normalized = str(value or "").strip()
    aliases = config.get("aliases", {}).get(dimension, {})
    if normalized in aliases:
        return str(aliases[normalized])
    lowered = normalized.lower()
    lowered_aliases = {str(k).lower(): str(v) for k, v in aliases.items()}
    return lowered_aliases.get(lowered, lowered)
