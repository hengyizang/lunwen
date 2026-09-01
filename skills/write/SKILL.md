---
name: write
description: Draft evidence-bound paper sections and supplements from approved results while preserving claim and citation traceability.
argument-hint: <project-slug> <paper-id> [section]
disable-model-invocation: true
---

# Write

Require G4 approval for result-bearing prose. Read the paper contract, claim-evidence matrix, experiment registry and `references/research-integrity.md`.

Claude may provide only a semantic outline and internal critique. Codex/OpenAI must independently write and revise every manuscript, table, caption, supplement, disclosure and submission-material text. Codex may write plotting code, but deterministic local tools must render final charts from recorded experiment data. Never copy wording from a Claude plan or audit.

Write a venue-neutral semantic manuscript first:

- every material claim maps to evidence or an analysis ID;
- distinguish prior evidence, present results and interpretation;
- report uncertainty, negative results, limitations and external-validity bounds;
- use citations only after source-level verification;
- do not alter methods after seeing results without disclosure;
- generate data/code availability, ethics, funding, conflict, author contribution and AI-use drafts for human confirmation.

Run `scripts/citation_audit.py` and require zero unresolved references. Run `scripts/venue_compliance.py` after the official template is safely ingested. Complete two review rounds and the response matrix for the current `state.active_paper`; do not skip directly to another paper.

Keep title, abstract and conclusions within the evidence scope. Formatting belongs to the retarget skill.
