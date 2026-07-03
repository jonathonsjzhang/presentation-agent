"""Pure Analysis-stage helpers.

The v0.3 runtime is intentionally not activated here.  This package contains
only deterministic logic that can be wired into a later Analysis executor.
"""

from presentation_agent.analysis.evidence_decision import (
    EvidenceAction,
    EvidenceDecision,
    decide_evidence,
)

__all__ = ["EvidenceAction", "EvidenceDecision", "decide_evidence"]
