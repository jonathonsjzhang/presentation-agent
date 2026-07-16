"""Pure Analysis-stage helpers.

The active runtime performs Evidence Intake before the Brief gate. This package contains
only deterministic logic that can be wired into a later Analysis executor.
"""

from presentation_agent.analysis.evidence_decision import (
    EvidenceAction,
    EvidenceDecision,
    decide_evidence,
)

__all__ = ["EvidenceAction", "EvidenceDecision", "decide_evidence"]
