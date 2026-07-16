"""Deterministic Evidence readiness decision for one Analysis round."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class EvidenceAction(str, Enum):
    """The only three legal Evidence actions in an Analysis round."""

    REUSE_EXISTING_CATALOG = "reuse_existing_catalog"
    INVOKE_ONCE = "invoke_once"
    RECORD_EVIDENCE_GAP = "record_evidence_gap"


@dataclass(frozen=True)
class EvidenceDecision:
    """Auditable decision without performing any sub-agent call."""

    action: EvidenceAction
    invoked: bool
    invocation_reason: str
    evidence_catalog_ref: str | None
    evidence_gap: str | None
    max_invocations_this_round: int = 1

    @property
    def should_invoke(self) -> bool:
        return self.action is EvidenceAction.INVOKE_ONCE

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["action"] = self.action.value
        return result


def decide_evidence(
    *,
    evidence_catalog: Mapping[str, Any] | None,
    raw_materials: Sequence[Any] | None,
    evidence_catalog_ref: str | None = None,
) -> EvidenceDecision:
    """Choose the Evidence path solely from input presence.

    A supplied catalog always wins over raw materials.  Raw materials count as
    present only when the sequence is non-empty.  The function does not spawn,
    retry, mutate inputs, inspect complexity, or activate another runtime path.
    """

    _validate_inputs(evidence_catalog=evidence_catalog, raw_materials=raw_materials)

    if evidence_catalog is not None:
        return EvidenceDecision(
            action=EvidenceAction.REUSE_EXISTING_CATALOG,
            invoked=False,
            invocation_reason="reused_existing_catalog",
            evidence_catalog_ref=evidence_catalog_ref,
            evidence_gap=None,
        )

    if raw_materials:
        return EvidenceDecision(
            action=EvidenceAction.INVOKE_ONCE,
            invoked=True,
            invocation_reason="raw_materials_without_catalog",
            evidence_catalog_ref=None,
            evidence_gap=None,
        )

    return EvidenceDecision(
        action=EvidenceAction.RECORD_EVIDENCE_GAP,
        invoked=False,
        invocation_reason="no_raw_materials",
        evidence_catalog_ref=None,
        evidence_gap=(
            "No Evidence Catalog or Raw Materials were supplied; evidence-based "
            "findings are blocked until source material is provided."
        ),
    )


def _validate_inputs(
    *,
    evidence_catalog: Mapping[str, Any] | None,
    raw_materials: Sequence[Any] | None,
) -> None:
    if evidence_catalog is not None and not isinstance(evidence_catalog, Mapping):
        raise TypeError("evidence_catalog must be a mapping or None")
    if raw_materials is not None and (
        isinstance(raw_materials, (str, bytes, bytearray))
        or not isinstance(raw_materials, Sequence)
    ):
        raise TypeError("raw_materials must be a non-string sequence or None")
