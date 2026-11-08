---
name: review
description: Simulate rigorous peer review, audit statistics and claims, and produce itemized revisions and response matrices.
argument-hint: <project-slug> <paper-id> [round]
disable-model-invocation: true
---

# Review and revision

Use the existing native cycle and preserve independent views:

1. Ordinary G1+ research uses planner → writer → one independent critic with method, statistics and contribution perspectives. Administrative G0 intake uses only planner → writer. At final submission use the existing mutually blind domain/editorial/statistics panel with its distinct source views; add no parallel reviewer or paid loop.
2. Inspect design, leakage, multiplicity, uncertainty, effect sizes, robustness and source-bound calculations without the author’s preferred verdict.
3. Classify actual findings as fatal, major, minor or editorial. Keep stable issue IDs, evidence locations and evidence-based reasons for accepting or rejecting proposed changes.
4. For actual response commitments, retain the response matrix, fulfillment status, exact manuscript location and rationale for anything partial or unfulfilled. Revise scientific claims only when evidence supports the change; never polish away a substantive limitation.
5. A material repair triggers a fresh independent review. A clean observation or editorial preference does not require a second review or compulsory scorecard.

Audit result placement as well as wording. Compare the experiment registry,
claim-evidence matrix, manuscript and supplement for direction-dependent
omission or demotion. Block any missing primary outcome, falsification test,
required baseline, material robustness failure, or result that changes
interpretation. Accept supplement placement only when predeclared role,
relevance or statistical adequacy justifies it and the main text cross-references
it. Do not demand repeated apologetic caveats; require each material limitation
once in the location where it changes interpretation.

Claude review text is an internal control record only. Codex/OpenAI must independently write all persistent revision text and response materials; never copy sentences from the Claude audit.

Before revision, snapshot the canonical manuscript tree under `reviews/revision-base/`; API cycles do this automatically before the writer changes an existing manuscript. After revision, use `scripts/revision_integrity.py` to check actual numeric, citation and claim-strength drift against source-bound scientific justification. `scripts/revision_trace.py` and the revision ledger describe promised changes as C observations; completeness adds no G5 gate. Independent scientific audits assess whether a changed claim is justified; no model may invent a human authorization. Historical genuine human records remain readable. Public AI-use statements are optional and author-editable. See `docs/RESEARCH-IMPROVEMENTS.md` for the current change-record contract.

Use the existing G5 citation and claim-evidence controls; preserve their actual source-bound reports under the active paper's `reviews/` directory. Abstract or DOI checks alone do not verify claim support. At submission preparation reuse final B venue/package checks only for their unchanged bound snapshot.

Read `references/research-methods/submission-review.md` and the pinned ARS reviewer criteria in `third_party/ars-review/`. Use all seven universal dimensions plus the applicable article-type dimensions as adversarial questions. Independently write `reviews/pre-submission-checklist.json` with concrete manuscript and evidence locations, categorical judgements, uncertainties and resolution tests, then let `scripts/pre_submission_review.py` generate the protected audit. Do not calculate a total score or acceptance probability. Review failed native figure alignment/collision audits as well as the exported PDF; a mechanical pass does not complete visual inspection.

For an actual rebuttal task, `python3 -m scripts.reviewer_rounds` can map original comments into concern cards with stable `comment_id`, evidence need, response stance, action and manuscript location. Preserve source hashes and unfulfilled actions in any generated response package. Concern cards, simulated comments and response completeness are C observations; missing or stale cards do not block G5 or force extra model calls. Actual scientific failures and required final venue response materials retain their applicable A/B checks. Do not automatically truncate a response or invent an experiment.

Preserve rejected suggestions with reasons. A simulated pass does not predict journal acceptance.
