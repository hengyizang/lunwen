---
name: systematic-review
description: Run a reproducible systematic literature screening ledger, PRISMA-style flow, contradiction/method comparison matrix and citation exports from executed search receipts.
---

# Systematic review

Read `references/stage-contracts.md` G1 and `skills/citations/SKILL.md`. Choose quick, standard, deep or audit scope before searching. Execute enough lawful provider searches with `scripts/literature_evidence.py`, saving query family, time, filters and receipt hashes. The mode is a scope setting, never proof that a review is comprehensive.

Run `scripts/systematic_review.py seed --project <slug> --receipt <id> --mode <mode> --criteria '<predeclared inclusion rules>' --actor '<person>'`. Have a named human mark title/abstract and full-text decisions, exclusion reasons, and exact included-study evidence locations in `evidence/systematic/screening.json`. Deep/Audit additionally require two independently named decisions at each decided stage; disagreement requires a third named adjudicator and rationale. Never auto-include pending records. Run `report` to export PRISMA-style counts/flow, search-strategy receipt JSON, comparison CSV, BibTeX, RIS, included JSON and HTML. Fill method, population, outcome, effect and contradiction groups from the actual full texts, not metadata. Check official PRISMA/PRISMA-S requirements and registration separately; the exported flow alone does not certify compliance.
