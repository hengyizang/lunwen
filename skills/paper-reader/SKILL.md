---
name: paper-reader
description: Read an authorized local paper PDF with page anchors, optionally translate it into Chinese for personal reading, and keep it separate from verified citation evidence.
---

# Paper reader

Read `references/workflow.md` and `docs/NEW-CAPABILITIES.md`. Check local possession and use rights; do not fetch an unauthorized copy or upload a publisher PDF to an unapproved API.

1. Run `scripts/paper_reader.py --project <slug> --pdf '<authorized-local-pdf>' --output evidence/readers/<name>.md`. This makes a no-model, page-anchored English extraction and a hash receipt. `--include-page-images` adds local `pdftoppm` page images where installed.
2. `--translate` explicitly invokes the paid configured GPT API for a Chinese personal reading translation, preserving numbers, qualifications and citations. Preview costs and verify source handling before choosing it. The translation is not the paper's final writing or a source quotation.
3. If a page has no extractable text, stop for authorized OCR/visual verification. Confirm any quotation, result, image and bibliography against the original page; only then promote located evidence into the normal citation and `paper-facts` ledgers.
4. Keep generated reading aids and receipts in `evidence/readers/`. Do not redistribute source PDFs or present translated text as an independent source.

The reader also emits a source map with PDF-page block IDs and extracted-text hashes; extraction does not certify a completed reading. Read `references/research-methods/paper-cards.md`, independently create a card conforming to `schemas/paper-card.schema.json`, and run `scripts/research_candidates.py paper-card`. Keep author statements separate from analyst interpretations, declare the actual source scope, and record candidate ideas as untested hypotheses. Abstract/excerpt cards cannot assess unseen methods or experiments. Promote verified facts into the existing evidence ledger rather than creating a competing source of truth.
