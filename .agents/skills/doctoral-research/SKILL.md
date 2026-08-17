---
name: doctoral-research
description: Orchestrate or independently audit a human-gated doctoral research program covering topic selection, paper architecture, public datasets, experiments, statistics, writing, journal templates, peer review and reproducibility. Use in this repository when starting, continuing, checking or retargeting a research project; never use it to guarantee publication or bypass human gates.
---

# Doctoral Research

Locate the repository root, then read `references/workflow.md`, `references/research-integrity.md`, and only the current section of `references/stage-contracts.md`.

Interpret the request as one of:

- `start <slug>`: initialize through `scripts/researchctl.py` and prepare G0;
- `continue <slug>`: complete only the current stage and stop at its gate;
- `topic <slug>`: attack topic novelty, feasibility and doctoral architecture;
- `experiment <slug> <design|run>`: design or audit reproducible experiments;
- `review <slug> [paper]`: audit code, statistics, claims and reproducibility;
- `retarget <slug> <paper> <venue>`: verify official requirements and template adaptation;
- `audit <slug>`: run a cross-stage integrity check.

Use deterministic scripts for state, manifests, downloads and archives. Never edit gate approvals by hand. Never approve a gate for the user.

When acting as the independent critic:

1. Do not read the author’s desired verdict.
2. Inspect runnable code, configs, datasets and raw result tables where available.
3. Recompute critical values and test leakage, seed sensitivity and alternative explanations.
4. Check each material claim against the claim-evidence matrix.
5. Report blockers, major and minor findings, residual uncertainty and a verdict.
6. Preserve findings under `projects/<slug>/reviews/codex/`.

Never invent missing data, citations or results, and never auto-submit.

