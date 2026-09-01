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
5. Create an itemized response matrix: finding, evidence, action, file/section, status and residual risk.
6. Revise scientific claims only when evidence supports the change; never polish away a substantive limitation.
7. Run a second clean review that cannot see the desired answer.

Claude review text is an internal control record only. Codex/OpenAI must independently write all persistent revision text and response materials; never copy sentences from the Claude audit.

For G5, also run `scripts/citation_audit.py` and `scripts/venue_compliance.py`; preserve both reports under the active paper's `reviews/` directory.

Preserve rejected suggestions with reasons. A simulated pass does not predict journal acceptance.
