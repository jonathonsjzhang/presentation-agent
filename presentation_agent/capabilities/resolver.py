from __future__ import annotations

from presentation_agent.capabilities.models import CapabilitySelection
from presentation_agent.capabilities.profile import ReportProfile


def resolve_capabilities(agent_id: str, profile: ReportProfile) -> CapabilitySelection:
    return CapabilitySelection(
        agent_id=agent_id,
        audience=profile.audience,
        report_type=profile.report_type,
        output_format=profile.output_format,
        capability_ids=(
            f"core.{agent_id}",
            f"audience.{profile.audience}",
            f"report.{profile.report_type}",
            f"format.{profile.output_format}",
        ),
    )
