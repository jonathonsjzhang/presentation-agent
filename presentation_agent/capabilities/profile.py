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
        result = {
            "audience": self.audience,
            "report_type": self.report_type,
            "output_format": self.output_format,
            "version": self.version,
        }
        if self.version == "v0_3":
            result["delivery_target"] = self.output_format
        return result

    @property
    def delivery_target(self) -> str:
        """Canonical v0.3 name; output_format remains the v0.2 compatibility field."""
        return self.output_format


def normalize_report_profile(
    data: Mapping[str, Any],
    *,
    root: Optional[Path] = None,
    strict: bool = True,
    allow_freeform_audience: bool = False,
) -> ReportProfile:
    config = _load_config(root)
    report = data.get("report") if isinstance(data.get("report"), Mapping) else data
    is_report_v1 = report.get("schema") == "report.v1"
    if is_report_v1:
        metadata = report.get("report_metadata")
        if not isinstance(metadata, Mapping):
            charter = data.get("report_charter")
            metadata = charter if isinstance(charter, Mapping) else {}
        if "output_format" in data or "material_format" in data:
            raise CapabilityError(
                "report.v1 Format tasks must use delivery_target, not legacy output_format"
            )
        target = data.get("delivery_target", "document")
        if isinstance(target, (list, tuple, set)):
            raise CapabilityError(
                "Each report.v1 Format task requires exactly one delivery_target"
            )
        values = {
            "audience": _normalize_value(
                "audience", metadata.get("audience", "strategy_lead"), config
            ),
            "report_type": _normalize_value(
                "report_type", metadata.get("report_type", "deep_dive"), config
            ),
            "output_format": _normalize_delivery_target(target, config),
        }
        version = "v0_3"
    else:
        source = (
            data.get("report_charter")
            if isinstance(data.get("report_charter"), Mapping)
            else data
        )
        raw_audience = source.get("audience", "")
        if isinstance(raw_audience, Mapping):
            raw_audience = raw_audience.get("primary", "")
        requested_targets = source.get("requested_delivery_targets") or source.get(
            "delivery_targets"
        )
        if isinstance(requested_targets, (list, tuple)) and requested_targets:
            requested_target = requested_targets[0]
        elif isinstance(requested_targets, str):
            requested_target = requested_targets
        else:
            requested_target = None
        values = {
            "audience": _normalize_value("audience", raw_audience, config),
            "report_type": _normalize_value(
                "report_type", source.get("report_type", "deep_dive"), config
            ),
            "output_format": _normalize_value(
                "output_format",
                source.get(
                    "delivery_target",
                    source.get(
                        "output_format",
                        source.get(
                            "material_format",
                            requested_target or "document",
                        ),
                    ),
                ),
                config,
            ),
        }
        version = "v1"
    if strict:
        for dimension, value in values.items():
            allowed = set(config.get("dimensions", {}).get(dimension, []))
            if value not in allowed:
                if dimension == "audience" and allow_freeform_audience:
                    values["audience"] = str(
                        metadata.get("audience", "") if is_report_v1 else raw_audience
                    ).strip()
                    continue
                raise CapabilityError(
                    f"Unsupported {dimension}={value!r}; allowed values: {sorted(allowed)}"
                )
    return ReportProfile(**values, version=version)


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
                "分析类": "deep_dive",
                "深度分析": "deep_dive",
                "业务进展汇报": "business_progress",
                "梳理类": "quick_sync",
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
    # Exact lowered match
    if lowered in lowered_aliases:
        return lowered_aliases[lowered]
    # Substring match: "腾讯总办" contains "总办" → "exec_office"
    for alias_key, alias_val in lowered_aliases.items():
        if alias_key in lowered:
            return str(alias_val)
    return lowered


def _normalize_delivery_target(value: Any, config: Mapping[str, Any]) -> str:
    profile = config.get("contract_profiles", {}).get("v0_3", {})
    normalized = str(value or "").strip()
    aliases = profile.get("delivery_target_aliases", {})
    if normalized in aliases:
        return str(aliases[normalized])
    lowered = normalized.lower()
    lowered_aliases = {str(k).lower(): str(v) for k, v in aliases.items()}
    return lowered_aliases.get(lowered, lowered)
