from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Optional

from presentation_agent.agent_profiles import load_agent_profile
from presentation_agent.evidence_assets import evidence_runtime_fields
from presentation_agent.io import read_json


class ContextAssembler:
    """Build namespaced, traceable Worker inputs from Manager artifact refs."""

    def __init__(self, root: Path, contract_profile: Optional[str] = None) -> None:
        self.root = root
        config = read_json(root / "configs" / "context_requirements.json", default={})
        self.contract_profile = load_agent_profile(
            root, contract_profile
        ).contract_profile
        profile = (
            config.get("contract_profiles", {}).get(self.contract_profile, {})
        )
        profile_workers = dict(profile.get("workers", {}))
        if profile_workers:
            self.requirements = {
                worker: list(dict(spec).get("required_fields", []))
                + list(dict(spec).get("conditional_full_fields", []))
                + list(dict(spec).get("task_fields", []))
                for worker, spec in profile_workers.items()
            }
        else:
            self.requirements = dict(config.get("workers", {}))
        self.signal_fields = list(config.get("signal_fields", []))
        self.max_inline_chars = int(
            config.get("max_inline_chars_per_field", 12000)
        )
        self.preview_items = int(config.get("preview_items", 3))
        self.field_inline_limits = {
            str(worker): {
                str(field): int(limit)
                for field, limit in dict(fields).items()
            }
            for worker, fields in dict(
                config.get("field_inline_limits", {})
            ).items()
        }
        self.full_input_required_fields = {
            str(worker): {str(field) for field in fields}
            for worker, fields in dict(
                config.get("full_input_required_fields", {})
            ).items()
        }
        if profile_workers:
            self.full_input_required_fields.update(
                {
                    worker: {
                        str(field)
                        for field in dict(spec).get("conditional_full_fields", [])
                    }
                    for worker, spec in profile_workers.items()
                }
            )

    def assemble(
        self,
        *,
        worker_id: str,
        report_charter: dict[str, Any],
        manager_task: dict[str, Any],
        raw_brief: dict[str, Any],
        artifacts: Iterable[tuple[Path, dict[str, Any]]],
        raw_brief_path: Path | None = None,
    ) -> dict[str, Any]:
        required = set(self.requirements.get(worker_id, []))
        artifact_rows = list(artifacts)
        inputs: dict[str, Any] = {}
        upstream_signal: dict[str, Any] = {}
        material_refs: list[dict[str, Any]] = []
        projection_records: list[dict[str, Any]] = []
        projected_brief, brief_projected_fields = self._inline_projection(
            raw_brief, required, worker_id=worker_id
        )
        omitted_brief_fields = [
            key for key in raw_brief if required and key not in required
        ]
        if (omitted_brief_fields or brief_projected_fields) and raw_brief_path is not None:
            material_refs.append(
                {
                    "source_id": "raw_brief",
                    "artifact_path": str(raw_brief_path),
                    "omitted_fields": omitted_brief_fields,
                    "projected_fields": brief_projected_fields,
                    "instruction": "Read the raw brief only if the task needs omitted detail.",
                }
            )
        if brief_projected_fields:
            projection_records.append(
                {
                    "source_id": "raw_brief",
                    "projected_fields": brief_projected_fields,
                }
            )

        for index, (path, data) in enumerate(artifact_rows, start=1):
            source_id = self._unique_source_id(
                self._source_id(path, data, index), inputs
            )
            inline, projected_fields = self._inline_projection(
                data, required, worker_id=worker_id
            )
            inputs[source_id] = {
                "artifact_path": str(path),
                "agent_id": data.get("agent_id", ""),
                "schema": data.get("schema", ""),
                "inline_fields": inline,
            }
            for field in self.signal_fields:
                if field in data and data[field] not in ("", [], {}, None):
                    encoded = json.dumps(
                        data[field], ensure_ascii=False, default=str
                    )
                    upstream_signal[field] = (
                        data[field]
                        if len(encoded) <= self.max_inline_chars
                        else self._preview_value(data[field])
                    )
            omitted = [key for key in data if required and key not in required]
            if omitted or projected_fields:
                material_refs.append(
                    {
                        "source_id": source_id,
                        "artifact_path": str(path),
                        "omitted_fields": omitted,
                        "projected_fields": projected_fields,
                        "instruction": "Read the referenced artifact only if the task needs omitted detail.",
                    }
                )
            if projected_fields:
                projection_records.append(
                    {
                        "source_id": source_id,
                        "projected_fields": projected_fields,
                    }
                )

        full_required = self.full_input_required_fields.get(worker_id, set())
        blocking_issues = [
            {
                "source_id": row["source_id"],
                "field": field,
                "reason": "field requires full material but only a preview was projected",
            }
            for row in projection_records
            for field in row["projected_fields"]
            if field in full_required
        ]

        result = {
            "schema": "worker_context.v1",
            "contract_profile": self.contract_profile,
            "report_charter": report_charter,
            "manager_task": manager_task,
            "raw_brief": projected_brief,
            "inputs": inputs,
            "material_refs": material_refs,
            "upstream_signal": upstream_signal,
            "input_readiness": {
                "status": "blocked" if blocking_issues else "ready",
                "blocking_issues": blocking_issues,
                "projection_records": projection_records,
            },
        }
        if self.contract_profile == "v0_3":
            self._add_v03_canonical_inputs(
                result,
                worker_id=worker_id,
                raw_brief=raw_brief,
                artifacts=artifact_rows,
                manager_task=manager_task,
            )
        return result

    @staticmethod
    def _add_v03_canonical_inputs(
        result: dict[str, Any],
        *,
        worker_id: str,
        raw_brief: dict[str, Any],
        artifacts: Iterable[tuple[Path, dict[str, Any]]],
        manager_task: dict[str, Any],
    ) -> None:
        rows = list(artifacts)
        schema_aliases = {
            "evidence_catalog.v1": "evidence_catalog",
            "analysis.v1": "analysis",
            "storyline.v3": "storyline",
            "report.v1": "report",
            "formatted_material.v2": "formatted_material",
        }
        for _, data in rows:
            alias = schema_aliases.get(str(data.get("schema") or ""))
            if alias:
                result[alias] = data
        if worker_id == "analysis":
            catalog = raw_brief.get("evidence_catalog")
            if isinstance(catalog, dict):
                result["evidence_catalog"] = catalog
                result["evidence_catalog_ref"] = raw_brief.get(
                    "evidence_catalog_ref", "raw_brief:evidence_catalog"
                )
            materials = (
                raw_brief.get("raw_materials")
                or raw_brief.get("materials")
            )
            if not materials and raw_brief.get("source_units"):
                materials = [
                    {
                        "material_type": raw_brief.get("material_type", "source_units"),
                        "source_units": raw_brief.get("source_units"),
                        "known_limitations": raw_brief.get("known_limitations", []),
                    }
                ]
            if not materials and raw_brief.get("rows"):
                materials = [
                    {
                        "material_type": raw_brief.get("material_type", "table"),
                        "metric_definition": raw_brief.get("metric_definition", ""),
                        "time_window": raw_brief.get("time_window", ""),
                        "rows": raw_brief.get("rows"),
                        "known_limitations": raw_brief.get("known_limitations", []),
                    }
                ]
            if materials:
                result["raw_materials"] = materials
        if worker_id == "format":
            target = (
                manager_task.get("delivery_target")
                or manager_task.get("context", {}).get("delivery_target")
                or "document"
            )
            result["delivery_target"] = target
        evidence_fields = evidence_runtime_fields(raw_brief, *[data for _, data in rows])
        result.update(evidence_fields)

    @staticmethod
    def _source_id(path: Path, data: dict[str, Any], index: int) -> str:
        return str(
            data.get("agent_id")
            or data.get("schema")
            or path.stem
            or f"artifact_{index}"
        ).replace(".", "_")

    @staticmethod
    def _unique_source_id(source_id: str, inputs: dict[str, Any]) -> str:
        if source_id not in inputs:
            return source_id
        suffix = 2
        while f"{source_id}_{suffix}" in inputs:
            suffix += 1
        return f"{source_id}_{suffix}"

    def _inline_projection(
        self,
        data: dict[str, Any],
        required: set[str],
        *,
        worker_id: str = "",
    ) -> tuple[dict[str, Any], list[str]]:
        inline: dict[str, Any] = {}
        projected_fields: list[str] = []
        limits = self.field_inline_limits.get(worker_id, {})
        for key, value in data.items():
            if required and key not in required:
                continue
            encoded = json.dumps(value, ensure_ascii=False, default=str)
            inline_limit = limits.get(key, self.max_inline_chars)
            if len(encoded) <= inline_limit:
                inline[key] = value
                continue
            projected_fields.append(key)
            if isinstance(value, list):
                inline[key] = {
                    "_projection": "list_preview",
                    "item_count": len(value),
                    "preview": [
                        self._preview_value(item)
                        for item in value[: self.preview_items]
                    ],
                }
            elif isinstance(value, dict):
                inline[key] = {
                    "_projection": "object_index",
                    "keys": list(value)[:50],
                }
            else:
                inline[key] = {
                    "_projection": "text_preview",
                    "char_count": len(str(value)),
                    "preview": str(value)[:1000],
                }
        return inline, projected_fields

    def _preview_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return value if len(value) <= 1000 else value[:1000] + "…"
        if isinstance(value, list):
            return {
                "_projection": "nested_list_preview",
                "item_count": len(value),
                "preview": [
                    self._preview_value(item)
                    for item in value[: self.preview_items]
                ],
            }
        if isinstance(value, dict):
            return {
                key: self._preview_value(item)
                for key, item in list(value.items())[:20]
            }
        return value
