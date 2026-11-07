---
name: write
description: Draft evidence-bound paper sections and supplements from approved results while preserving claim and citation traceability.
argument-hint: <project-slug> <paper-id> [section]
disable-model-invocation: true
---

# Write

Apply `docs/EVIDENCE-FIRST-WRITING.md` in the existing paragraph, paper-facts,
closest-work and review-issue records. Record takeaway/warrant and concrete
missing materials; bind each contribution to actual results and frozen
expectations. Use design-appropriate evidence for empirical, Meta, theoretical
or qualitative findings. Reuse existing writer/critic passes.

Require G4 approval for result-bearing prose. Read the paper contract, claim-evidence matrix, experiment registry and `references/research-integrity.md`.

Claude may provide only a semantic outline and internal critique. GPT/OpenAI must independently write and revise every manuscript, table, caption, supplement, disclosure and submission-material text. Use `skills/figures/SKILL.md` for data charts, research diagrams and separately disclosed conceptual illustrations. Every result-bearing chart must be rendered locally from recorded experiment data, include uncertainty and accessible redundant encodings, and pass figure provenance. Never copy wording from a Claude plan or audit.

Write a venue-neutral semantic manuscript first:

- every material claim maps to evidence or an analysis ID;
- distinguish prior evidence, present results and interpretation;
- report uncertainty, negative results, limitations and external-validity bounds;
- use citations only after source-level verification;
- do not alter methods after seeing results without disclosure;
- prepare data/code availability, ethics, funding, conflict and author-contribution statements from actual records; preserve any existing AI-use statement and unresolved external obligations without inventing consent or adding an AI-policy gate.

Follow [the evidence-led narrative guide](../../docs/EVIDENCE-LED-NARRATIVE.md).
Prioritize the strongest supported contribution, exact advantage, decisive
evidence and bounded value in the abstract and conclusion. Reframe the story
when a different contribution is better supported, retaining original hypotheses,
outcomes and actual exploratory/confirmatory phases. Secondary, null or unfavorable results do
not need headline treatment unless they change the main claim, validity, safety
or scope, but every registered result must remain locatable in the results,
supplement and evidence trail. Never delete, soften or demote an experiment
because it is unfavorable or contentious. Main-text versus supplement placement
must follow predeclared role, relevance and statistical adequacy, with a recorded
rationale and main-text cross-reference. State material limitations once,
specifically and without apology; remove only generic or repeated caveats.

Select the applicable reporting checklist from `references/reporting-guidelines.md` before methods drafting. Record item identifiers, exact manuscript locations and evidence artifacts in `reviews/reporting-guideline-input.json`; explain genuine non-applicability. Run `scripts/reporting_checklist.py` after the final revision so G5 can verify completeness and bind the checklist to the manuscript snapshot.

The checklist input needs `schema_version`, `study_design`, `guideline`, `guideline_version`, official HTTPS URL, named reviewer and timezone-aware review time. Each item has `item_id`, `status` (`present`, `not_applicable`, or `open`), `location`, `evidence_ids`, and `rationale`; any `open` item blocks G5.

Run citation identity and source/claim/numeric checks against the current manuscript. Use lawful full passages for material claims; retain supports/contradicts/insufficient and actual missing evidence. The current writing phase starts scientific, with one fresh independent critique; actual findings alone justify repair and re-review. Final submission uses the three-family blind panel and B checks defined in [workflow.md](../../references/workflow.md); C editorial observations never require a complete scorecard or two simulated review rounds. The controller stores phase changes without editing the frozen contract.

Keep title, abstract and conclusions within the evidence scope. LaTeX remains the preferred reproducible source when the venue supports it. If the venue requires Word, create English Markdown plus `schemas/docx-manuscript-metadata.schema.json`, record both with current non-Claude provenance, then run `scripts/manuscript_docx.py` to produce `papers/Pxx/manuscript/main.docx`. Use Pandoc/reference DOCX when available or the deterministic `python-docx` fallback. Before final G5, require current build/render receipts and an actual source-bound automated visual inspection of pagination, equations, citations, tables and figures. Historical genuine human inspections remain valid inputs; do not add a mandatory human stage approval. Never keep both `main.tex` and `main.docx` as competing canonical manuscripts.

Before the introduction, record the precise gap, supporting closest-work evidence and a 3–4-layer background map. Draft each paragraph with a clear role, bounded claim, allowed evidence and reason for the next paragraph; do not pad background with irrelevant history. Build `reviews/paper-facts.json` and run `scripts/manuscript_audit.py` to check claim alignment, construct→item→coding→analysis→evidence validity, argument roles, terminology/acronyms and mathematical symbols. For user-supplied AI-detector feedback, allow a bounded editorial pass as described in `skills/paper-audit/SKILL.md`; preserve the integrity and AI disclosure controls. Do not equate a detector score with authorship.
