"""Render backends that turn formatted_material.v1 / page_content.v1 into real files.

Three targets:
- ppt.py   -> .pptx via the vendored McKinsey engine (mck_ppt)
- html.py  -> .html via a self-contained McKinsey-styled template
- docx.py  -> .docx via python-docx (optional dependency)

All renderers degrade gracefully: if the optional dependency is missing they
return a structured "skipped" result instead of crashing, so the harness still
runs end-to-end in environments without python-pptx / python-docx installed.
"""

from presentation_agent.renderers.base import RenderResult, render_material, resolve_output_format

__all__ = ["RenderResult", "render_material", "resolve_output_format"]
