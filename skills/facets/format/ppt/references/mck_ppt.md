# PPT renderer contract

Use `presentation_agent.renderers.ppt` as the runtime entry point. Prefer the
shape-native `presentation_agent.vendor.mck_ppt.DeckBuilder` path so text,
charts, and sources remain editable.

The format artifact must set `format=ppt`, use `unit_type=slide`, and provide a
supported `layout_or_structure.layout_type`. Chart layouts need a structured
`visual_object.chart_spec`; when evidence is incomplete, choose a non-chart
fallback and retain the gap in `open_design_tasks`.

The generation agent describes render intent. Only the renderer may stamp
`render_result.status=rendered`.
