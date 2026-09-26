---
name: write
description: Draft evidence-bound paper sections and supplements from approved results while preserving claim and citation traceability.
argument-hint: <project-slug> <paper-id> [section]
disable-model-invocation: true
---

# Write

Require G4 approval for result-bearing prose. Read the paper contract, claim-evidence matrix, experiment registry and `references/research-integrity.md`.

Claude may provide only a semantic outline and internal critique. GPT/OpenAI must independently write and revise every manuscript, table, caption, supplement, disclosure and submission-material text. Prefer a schema-bound specification rendered through `scripts/publication_figures.py`; specialized GPT-written plotting code remains available when scientifically necessary. Every final chart must be rendered locally from recorded experiment data, include uncertainty and accessible redundant encodings, and pass figure provenance. Never copy wording from a Claude plan or audit.

Write a venue-neutral semantic manuscript first:

- every material claim maps to evidence or an analysis ID;
- distinguish prior evidence, present results and interpretation;
- report uncertainty, negative results, limitations and external-validity bounds;
- use citations only after source-level verification;
- do not alter methods after seeing results without disclosure;
- generate data/code availability, ethics, funding, conflict, author contribution and AI-use drafts for human confirmation.

Use claim-forward reporting rather than defensive prose. The abstract and
conclusion should prioritize the preregistered primary result and the strongest
supported contribution. Secondary, exploratory, null or unfavorable results do
not need headline treatment unless they change the main claim, validity, safety
or scope, but every registered result must remain locatable in the results,
supplement and evidence trail. Never delete, soften or demote an experiment
because it is unfavorable or contentious. Main-text versus supplement placement
must follow predeclared role, relevance and statistical adequacy, with a recorded
rationale and main-text cross-reference. State material limitations once,
specifically and without apology; remove only generic or repeated caveats.

Select the applicable reporting checklist from `references/reporting-guidelines.md` before methods drafting. Record item identifiers, exact manuscript locations and evidence artifacts in `reviews/reporting-guideline-input.json`; explain genuine non-applicability. Run `scripts/reporting_checklist.py` after the final revision so G5 can verify completeness and bind the checklist to the manuscript snapshot.

The checklist input needs `schema_version`, `study_design`, `guideline`, `guideline_version`, official HTTPS URL, named reviewer and timezone-aware review time. Each item has `item_id`, `status` (`present`, `not_applicable`, or `open`), `location`, `evidence_ids`, and `rationale`; any `open` item blocks G5.

Run `scripts/citation_audit.py` and require zero unresolved references. Then use the `citations` skill and `scripts/ref_verify_adapter.py` for DOI-bound abstract-level topline/numeric claims; use full text for deeper claims. Run `scripts/venue_compliance.py` after the official template is safely ingested. Complete two review rounds and the response matrix for the current `state.active_paper`; do not skip directly to another paper.

Keep title, abstract and conclusions within the evidence scope. Formatting belongs to the retarget skill.
