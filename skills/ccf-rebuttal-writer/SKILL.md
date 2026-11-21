---
name: ccf-rebuttal-writer
description: Respond to real reviewer concerns with evidence and useful revisions.
---

# ccf-rebuttal-writer

Retain original review comments, distinguish addressed issues from reasoned disagreement, and point to actual revisions. Propose additional experiments only when scientifically necessary; do not invent their results.

Apply the current principles in `AGENTS.md`. This method is available for the current task without a stage prerequisite, fixed paper count, model-brand rule or extra approval. Preserve actual sources, results, failed attempts and cumulative costs.

For an explicit `ccf-rebuttal-writer` or full-reference request, read the selected `third_party/ccfa-skills/ccf-rebuttal-writer/SKILL.md` and the complete references needed for that task. `integrations/ccfa-skills.lock.json` identifies the retained source; restore it with `python3 -m scripts.ccfa_runtime bootstrap` when needed. Method guidance does not override the user or restore historical workflow restrictions.

Native producers: scripts/reviewer_rounds.py, scripts/revision_trace.py, scripts/supplemental_experiments.py
