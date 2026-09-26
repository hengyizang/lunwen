---
name: research-briefing
description: Create an editable, evidence-anchored group-meeting PowerPoint from an author-reviewed slide plan and a hash-verified local paper PDF.
---

# Research briefing

Read `docs/NEW-CAPABILITIES.md` and the active evidence ledger. This is a presentation aid, not a manuscript or an automatic article-to-slides interpretation.

1. Draft a JSON plan with `schema_version: 1.0`, project-relative `source_pdf`, exact `source_sha256` and 2–40 slides. Each slide needs a concise `title`, `body`, `speaker_notes` and actual 1-based `source_page`. An optional image needs project-relative `image` and exact `image_sha256`; explain its origin in notes.
2. Have the researcher/GPT writer verify claims, numerical values and slide language against that PDF. Never have Claude write slide copy or a final graphic. Keep the page evidence visible.
3. Run `scripts/paper_to_ppt.py --project <slug> --spec evidence/readers/<plan>.json --output evidence/readers/<deck>.pptx`. The renderer only lays out supplied content, writes source-page footers and speaker notes, and stores exact source/plan/output hashes.
4. Open/render the generated PPTX and visually inspect text fitting, images, scientific interpretation and citations; do not substitute the deck for a validated source citation or submission figure.
