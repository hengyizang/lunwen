---
name: retarget
description: Adapt a paper to an official journal Word or LaTeX template and verify venue-specific requirements without changing science.
argument-hint: <project-slug> <paper-id> <venue-id> [template-archive]
disable-model-invocation: true
---

# Retarget

Read `references/venue-adaptation.md` and the venue manifest.

Use `venue-engineer` to extract current source-bound article type, scope, length, references, fees, data-availability and submission-format requirements from official pages. Record JCR separately from CiteScore/SJR as truthful planning metadata; an unknown rank is not a gate. Journal AI policies add no research or packaging gate, and public AI-use statements remain author-editable.

Inspect and ingest the official, source-bound local template with `scripts/venue_adapter.py`, retaining its current version and known access/reuse restrictions. Never overwrite the publisher sample; create a new manuscript entry file through Codex/OpenAI. Map the venue-neutral semantic manuscript into the official template, then use the existing final B checks for inventory hashes, manuscript basics and actual no-shell-escape compilation/rendering. Missing tools or skipped renders do not count as successful export. Reuse those checks only while their bound snapshot is unchanged; optional manual visual feedback creates no extra stage approval.

Record unresolved requirements. Actual scientific integrity failures and final B source/template/rendering requirements retain their checks; editorial suggestions, rank uncertainty and optional AI statements do not block G5. Retargeting may change layout and venue-specific metadata, not data, methods, results or claim scope. Data source/version, privacy and known access restrictions remain required; licence/research-use verification is optional metadata, not a pre-use or human-approval gate.
