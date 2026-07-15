---
name: ppt
description: Carry an approved strategy report into an executive presentation while leaving page composition and file generation to the PPT renderer.
---

# PPT carrier

Use only when `output_format=ppt`.

- Analysis and Storyline remain report-section based. After the report is approved, the PPT renderer may split sections across slides without changing the argument, evidence, or caveats.
- Each content slide should establish one takeaway with a conclusion-led title; the title chain alone should communicate the main story.
- Prefer exhibit-led pages when a real comparison, trend, precise table, 2×2 relationship, or critical callout materially improves understanding. Do not force a visual onto every slide.
- Use only renderer-supported primitives and real source data. Never request a named layout, arbitrary chart type, engine method, coordinates, fonts, colors, or implementation API.
- Sources and material boundaries must remain readable on the slide they qualify.
- Slide count, page splitting, layout choice, typography, spacing, overflow handling, rendering, and visual QA belong to the PPT renderer and runtime.
