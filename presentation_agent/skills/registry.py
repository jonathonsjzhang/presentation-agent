from __future__ import annotations

from typing import Optional

from presentation_agent.llm.client import LLMClient
from presentation_agent.skills.generic import GenericSkill


def get_skill(skill_id: str, llm: Optional[LLMClient] = None) -> GenericSkill:
    """Return the package-driven skill for any agent.

    All seven agents share one implementation (GenericSkill); their behavior is
    defined by their own skill package (SKILL.md + schemas/). The
    loop injects an LLMClient so generation can run via mock / cli / inline.
    """
    return GenericSkill(skill_id, llm=llm)
