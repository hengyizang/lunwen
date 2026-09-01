---
name: audit
description: Run a cross-stage integrity audit over citations, datasets, experiments, claims, templates, disclosures and gate history.
argument-hint: <project-slug> [paper-id]
disable-model-invocation: true
---

# Audit

Read `references/research-integrity.md`. Do not repair findings silently.

Check:

- gate state and recorded human approvals;
- source existence, exact support and retraction/correction status;
- dataset rights, provenance, checksum, transformations and split leakage;
- experiment/config/code/data traceability and failed-run retention;
- statistical assumptions, multiplicity, uncertainty and robustness;
- claim-evidence coverage and unsupported generalization;
- current venue identity, JCR evidence, template provenance and policy compliance;
- authorship, funding, conflict, ethics, data/code and AI-use disclosures;
- secrets, raw/private data and publisher files accidentally tracked by Git.

Use a model family different from the Codex/OpenAI persistent writer for the independent initial and final schema-bound passes. Require Codex/OpenAI to disposition and remediate every finding. Also verify `state/output-provenance.json` and block current Anthropic-authored final files. Emit blocking, major and minor findings with exact paths and remediation evidence. Do not mark a gate ready while blockers remain.
