---
name: systematic-review
description: Run a reproducible systematic literature screening ledger, PRISMA-style flow, contradiction/method comparison matrix and citation exports from executed search receipts.
---

# Systematic review

Read `references/stage-contracts.md` G1 and `skills/citations/SKILL.md`. Choose quick, standard, deep or audit scope before searching. Execute enough lawful provider searches with `scripts/literature_evidence.py`, saving query family, time, filters and receipt hashes. The mode is a scope setting, never proof that a review is comprehensive.

Run `scripts/systematic_review.py seed --project <slug> --receipt <id> --mode <mode> --criteria '<predeclared inclusion rules>' --actor '<person>'`. Deep/Audit must also pass `--protocol <project-relative-json>`; the protocol needs `registered` or `author-approved` status and a named authority. Have a named human mark title/abstract and full-text decisions, exclusion reasons, and exact included-report evidence locations in `evidence/systematic/screening.json`. Deep/Audit additionally require two independently named decisions at each decided stage; disagreement requires a third named adjudicator and rationale. For included reports, record `report_id`, a cross-report `study_group_id`, method/population/outcome/limitations and a named risk-of-bias tool with two assessors and domain-level support. Never auto-include pending records.

Run `report` to export PRISMA-style report/study counts and flow, search-strategy receipts, protocol binding, comparison and risk-of-bias CSVs, BibTeX, RIS, included JSON, HTML and a hash manifest. Fill comparisons from actual full text, not metadata. Complete the generated PRISMA 2020 and PRISMA-S template with manuscript locations, a named signature and date; run `validate --completed-checklist <json>` before treating the export as complete. The mechanical export does not certify methodological or reporting compliance.
