---
name: doctoral-research
description: Orchestrate or independently audit a human-gated doctoral research program covering topic selection, paper architecture, public datasets, experiments, statistics, writing, journal templates, peer review and reproducibility. Use in this repository when starting, continuing, checking or retargeting a research project; never use it to guarantee publication or bypass human gates.
---

# Doctoral Research

Locate the repository root, then read `references/workflow.md`, `references/research-integrity.md`, and only the current section of `references/stage-contracts.md`.

Interpret the request as one of:

- `start <slug>`: initialize through the API-first `scripts/start.sh` path and prepare G0;
- `continue <slug>`: inspect `researchctl.py status`, run the current stage through `scripts/api_orchestrator.py cycle`, and stop at its gate;
- `topic <slug>`: attack topic novelty, feasibility and doctoral architecture;
- `experiment <slug> <design|run>`: design or audit reproducible experiments;
- `review <slug> [paper]`: audit code, statistics, claims and reproducibility;
- `citations <slug> <paper>`: run reference identity checks, DOI-bound abstract claim verification and route deeper claims to full-text evidence;
- `journal <slug>`: produce an official-evidence-backed challenge/target/safety shortlist from the authorized JCR registry;
- `retarget <slug> <paper> <venue>`: verify official requirements and template adaptation;
- `package <slug> <paper>`: build a deterministic ZIP for human inspection and manual upload;
- `audit <slug>`: run a cross-stage integrity check.

Use deterministic scripts for state, discovery, manifests, downloads, approved experiments, citations and archives. Default to the external API worker so this Codex conversation remains a thin manager; do not invoke `autopilot.py`, Claude Code or Codex CLI unless the user explicitly requests CLI mode. Claude is restricted to read-only semantic planning and internal independent audits. GPT/OpenAI independently writes and remediates every persistent text artifact and plotting specification; `scripts/publication_figures.py` renders final charts from recorded data. Require initial and final independent model-family audits at G1–G5. Preserve the configured CNY hard budgets and exact-request cache. Never edit gate approvals by hand. Never approve a gate for the user.

At G2, run `scripts/journal_screening.py` and retain decomposed scores, official evidence, risks and challenge/target/safety roles. At G5, follow `skills/citations/SKILL.md`, route the applicable reporting guideline, snapshot the pre-revision manuscript, then run `scripts/ref_verify_adapter.py`, `scripts/reporting_checklist.py`, `scripts/revision_trace.py` and `scripts/revision_integrity.py`. Abstract support is never full-text support. Numeric, citation or claim-strength drift needs exact named human authorization.

For six papers, require at least three declared current JCR Q1 SCI/SCIE targets and every remainder at least current JCR Q2, all with JIF above 1.0. Apply the same doctoral originality, experiment, reliability, review and writing gates to every paper. Use `scripts/open_fulltext.py` for lawful OA candidates. When the user supplies a SciencePro export, ingest it through `scripts/sciencepro_import.py` and treat it as advisory until independently verified.

When acting as the independent critic:

1. Do not read the author’s desired verdict.
2. Inspect runnable code, configs, datasets and raw result tables where available.
3. Recompute critical values and test leakage, seed sensitivity and alternative explanations.
4. Check each material claim against the claim-evidence matrix.
5. Report blockers, major and minor findings, residual uncertainty and a verdict.
6. Preserve findings under `projects/<slug>/reviews/independent/`.

Before packaging, require current output-provenance hashes and reject any file whose current writer family is Anthropic/Claude.

Never invent missing data, citations or results. Packaging is local-only: never request portal credentials, upload files or auto-submit.
