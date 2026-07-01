from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from presentation_agent.io import read_json


class ContextAssembler:
    """Build namespaced, traceable Worker inputs from Manager artifact refs."""

    def __init__(self, root: Path) -> None:
        self.root = root
        config = read_json(root / "configs" / "context_requirements.json", default={})
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
        inputs: dict[str, Any] = {}
        upstream_signal: dict[str, Any] = {}
        material_refs: list[dict[str, Any]] = []
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

        for index, (path, data) in enumerate(artifacts, start=1):
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

        return {
            "schema": "worker_context.v1",
            "report_charter": report_charter,
            "manager_task": manager_task,
            "raw_brief": projected_brief,
            "inputs": inputs,
            "material_refs": material_refs,
            "upstream_signal": upstream_signal,
        }

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
