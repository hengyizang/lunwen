---
name: audit
description: Run a cross-stage integrity audit over citations, datasets, experiments, claims, templates, disclosures and gate history.
argument-hint: <project-slug> [paper-id]
disable-model-invocation: true
---

# Audit

Use `docs/EVIDENCE-FIRST-WRITING.md` for located empty evaluation, missing
evidence and inference gaps. Independently judge why evidence supports each
claim; source/hash checks do not establish this. Put consequential findings and
specific data/literature/analysis/proof tasks into existing issue records with
stable IDs, scope, actions and completion conditions. Do not invent a finding
to fill a checklist or add a model call per paragraph.

Read `references/research-integrity.md`. Do not repair findings silently.

Check:

- gate state, actual G1/G2 human topic decisions and the other stages' evidence-bound automated decisions;
- source existence, exact support and retraction/correction status;
- dataset rights, provenance, checksum, transformations and split leakage;
- experiment/config/code/data traceability and failed-run retention;
- statistical assumptions, multiplicity, uncertainty and robustness;
- claim-evidence coverage and unsupported generalization;
- actual selected venue fit and source-bound template/export requirements at submission; ranking unknowns remain explicit, without a rank or AI-policy gate;
- actual authorship, funding, conflict, ethics and data/code statements, and preservation of any existing disclosure;
- secrets, raw/private data and publisher files accidentally tracked by Git.

Use the current critique and final three-view panel defined in [workflow.md](../../references/workflow.md). Keep model-family independence, actual sources, stable issue IDs and disagreement. Report A scientific-integrity failures separately from B final-submission checks and C observations; only actual blocking problems require repair. Preserve the decision log and current output-provenance hashes; Claude cannot persist final scientific files. Do not turn a style warning, legacy score or administrative receipt into a new gate.
