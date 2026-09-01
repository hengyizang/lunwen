---
name: doctoral-research
description: Orchestrate or independently audit a human-gated doctoral research program covering topic selection, paper architecture, public datasets, experiments, statistics, writing, journal templates, peer review and reproducibility. Use in this repository when starting, continuing, checking or retargeting a research project; never use it to guarantee publication or bypass human gates.
---

# Doctoral Research

Locate the repository root, then read `references/workflow.md`, `references/research-integrity.md`, and only the current section of `references/stage-contracts.md`.

Interpret the request as one of:

- `start <slug>`: initialize through `scripts/autopilot.py start` and prepare G0;
- `continue <slug>`: use `scripts/autopilot.py resume`, complete only the current stage and stop at its gate;
- `topic <slug>`: attack topic novelty, feasibility and doctoral architecture;
- `experiment <slug> <design|run>`: design or audit reproducible experiments;
- `review <slug> [paper]`: audit code, statistics, claims and reproducibility;
- `retarget <slug> <paper> <venue>`: verify official requirements and template adaptation;
- `package <slug> <paper>`: build a deterministic ZIP for human inspection and manual upload;
- `audit <slug>`: run a cross-stage integrity check.

Use deterministic scripts for state, discovery, manifests, downloads, approved experiments, citations and archives. Claude is restricted to read-only semantic planning and internal independent audits. Codex/OpenAI independently writes and remediates every persistent text artifact and plotting program; local deterministic tools render final charts from recorded data. Require initial and final independent model-family audits at G1–G5. Never edit gate approvals by hand. Never approve a gate for the user.

When acting as the independent critic:

1. Do not read the author’s desired verdict.
2. Inspect runnable code, configs, datasets and raw result tables where available.
3. Recompute critical values and test leakage, seed sensitivity and alternative explanations.
4. Check each material claim against the claim-evidence matrix.
5. Report blockers, major and minor findings, residual uncertainty and a verdict.
6. Preserve findings under `projects/<slug>/reviews/independent/`.

Before packaging, require current output-provenance hashes and reject any file whose current writer family is Anthropic/Claude.

Never invent missing data, citations or results. Packaging is local-only: never request portal credentials, upload files or auto-submit.
