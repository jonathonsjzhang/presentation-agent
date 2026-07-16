---
name: document
description: Carry an approved strategy report into a formal document without giving content workers responsibility for pagination, typography, or file generation.
---

# Document carrier

Use only when `output_format=document`.

- The canonical report remains section-based continuous prose; do not turn it into pages, cards, or slide bullets.
- Preserve the approved title, Executive Summary, section order, wording, evidence, caveats, Q&A, and appendix hierarchy.
- Preserve one to three real list levels with stable markers, hanging indents, and wrapped-line alignment; never expose Markdown `-` markers as body text.
- Render reader-facing `Source:` / `来源：` lines as a distinct, smaller muted citation block adjacent to the claim they support. Machine `source_refs`, evidence IDs, section IDs and claim IDs remain in manifests and never enter the reader-visible carrier.
- Format only selects evidence-led visuals that materially improve comparison, precision, or comprehension.
- Captions and sources must remain readable and adjacent to the visual they support.
- Typography, spacing, pagination, headers, footers, overflow handling, and DOCX/PDF generation belong to the document renderer and runtime quality checks. Before delivery, structural QA must reject fake list markers, unstyled source lines, and reader-visible internal trace fields.
