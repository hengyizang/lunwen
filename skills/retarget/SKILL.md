---
name: retarget
description: Adapt a paper to an official journal Word or LaTeX template and verify venue-specific requirements without changing science.
argument-hint: <project-slug> <paper-id> <venue-id> [template-archive]
disable-model-invocation: true
---

# Retarget

Read `references/venue-adaptation.md` and the venue manifest.

Use `venue-engineer` to extract current requirements from official pages. Re-check JCR separately from CiteScore/SJR, article type, scope, length, references, declarations, AI/data policies, fees and submission format.

Inspect and ingest the authorized local template with `scripts/venue_adapter.py`. Never overwrite the publisher sample; create a new manuscript entry file. Map the venue-neutral semantic manuscript into the official template, compile/render when possible, and inspect the resulting PDF/DOCX.

Record unresolved requirements and block G5 for any mandatory uncertainty. Retargeting may change layout and venue-specific metadata, not data, methods, results or claim scope.

