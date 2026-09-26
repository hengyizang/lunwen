---
name: review
description: Simulate rigorous peer review, audit statistics and claims, and produce itemized revisions and response matrices.
argument-hint: <project-slug> <paper-id> [round]
disable-model-invocation: true
---

# Review and revision

Use blinded actor-critic passes:

1. Give `reviewer-two` the manuscript, paper contract, venue scope and evidence package without the author’s preferred verdict.
2. Ask `statistical-auditor` to inspect design, leakage, multiplicity, uncertainty, effect sizes and robustness.
3. Ask Codex to reproduce critical calculations or inspect runnable code independently.
4. Classify findings as fatal, major, minor or editorial.
5. Create an itemized response matrix with stable `comment_id` and `commitment_id`, fulfillment status, exact manuscript location, promised revised text, and a rationale for anything partial or unfulfilled.
6. Revise scientific claims only when evidence supports the change; never polish away a substantive limitation.
7. Run a second clean review that cannot see the desired answer.

Audit result placement as well as wording. Compare the experiment registry,
claim-evidence matrix, manuscript and supplement for direction-dependent
omission or demotion. Block any missing primary outcome, falsification test,
required baseline, material robustness failure, or result that changes
interpretation. Accept supplement placement only when predeclared role,
relevance or statistical adequacy justifies it and the main text cross-references
it. Do not demand repeated apologetic caveats; require each material limitation
once in the location where it changes interpretation.

Claude review text is an internal control record only. Codex/OpenAI must independently write all persistent revision text and response materials; never copy sentences from the Claude audit.

Before revision, snapshot the canonical manuscript tree under `reviews/revision-base/`; API cycles do this automatically before the writer changes an existing manuscript. After revision, run `scripts/revision_trace.py` to prove that promised changes exist, and `scripts/revision_integrity.py` to detect numeric, citation and claim-strength drift. Any protected change must exactly match a named human authorization in `reviews/revision-authorizations.json`; the checker never silently approves a strengthened claim.

The authorization file uses `schema_version`, `approved_by`, timezone-aware `approved_at`, and the exact arrays emitted by a failed integrity run: `numeric_changes`, `citation_changes`, and `claim_language_changes`, each with `removed` and `added`. Add `claim_language_rationale` whenever claim-language tokens change. The human reviews those exact changes; do not ask a model to impersonate approval.

For G5, also run `scripts/citation_audit.py`, `scripts/ref_verify_adapter.py` and `scripts/venue_compliance.py`; preserve the reports under the active paper's `reviews/` directory.

Preserve rejected suggestions with reasons. A simulated pass does not predict journal acceptance.
