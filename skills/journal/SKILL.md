---
name: journal
description: Build a current JCR-bound challenge, target and safety journal shortlist with decomposed fit scoring and explicit risk evidence.
argument-hint: <project-slug>
disable-model-invocation: true
---

# Journal screening

Start from `program/venue-candidates.json`, which remains authoritative for current SCI/SCIE indexing, JCR quartile, impact factor and official policy URLs. Do not treat a recommender's similarity score as ranking evidence.

Create `program/journal-screening-input.json` with the actual `recorded_by` and timezone-aware `recorded_at`; legacy `reviewed_by`/`reviewed_at` names remain readable without proving a human reviewed them. For every candidate record 0–5 scores for scope fit, article-type fit, audience fit, impact/tier, practicality, access/cost and reputation/risk; attach dated official-source evidence for scope, article type, audience, practicality, access and reputation. Record risk flags rather than hiding unknown fees, timelines or policy ambiguity. Hard risks—scope mismatch, uncertain indexing, inactive submissions or integrity concerns—exclude a venue. This assessment and the source-bound venue registry add no human confirmation step, certify no science and do not replace the existing G1/G2 owner topic decisions or actual final venue/source checks.

The top level needs `reviewed_by`, timezone-aware `reviewed_at`, and a `papers` array. Each candidate needs `venue_id`, `strategy`, all seven score keys, `risk_flags`, and six evidence rows whose categories are `scope`, `article_type`, `audience`, `practicality`, `access`, and `reputation`; every evidence row needs an HTTPS `url`, `accessed_at`, and a concise `note`.

Use at least one challenge, target and safety venue per paper. Use actual scope, article type, audience and desk-rejection evidence for fit. Existing Q1/Q2/IF targets are planning observations rather than gates; lawful ranking evidence remains exact and missing values stay unknown. Do not silently change an already selected target. Run:

```bash
python3 scripts/journal_screening.py --project <project>
```

The deterministic output is bound to the screening input and the JCR registry. Human authors make the final venue decision after reading the current official scope and author instructions.
