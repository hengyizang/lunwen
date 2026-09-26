---
name: citations
description: Audit bibliography identity and DOI-bound claim support while preserving the distinction between abstract and full-text evidence.
argument-hint: <project-slug> <paper-id>
disable-model-invocation: true
---

# Citation verification

Run the built-in citation audit first. It verifies reference identity, DOI/title/year consistency and manuscript usage but does not by itself establish that a source supports a sentence.

For each DOI-backed topline or numeric statement, add one JSONL row to `reviews/citation-claims.jsonl` with `id`, `doi`, `claim`, `claim_type` (`topline` or `numeric`) and `evidence_depth: abstract`. Install the pinned engine with `bash scripts/bootstrap-wsl.sh --with-reference-tools`, then run:

```json
{"id":"CIT-P01-001","doi":"10.xxxx/xxxxx","claim":"Exact claim text.","claim_type":"numeric","evidence_depth":"abstract","source":"auto"}
```

```bash
.venv/bin/python scripts/ref_verify_adapter.py --project <project> --paper <paper>
```

Only `ACCEPT` plus `SUPPORTED` with a fetched evidence excerpt passes. A pass is abstract-level evidence only. Mechanism, implementation, procedure, subgroup, table and figure claims require direct full-text inspection and an exact source location in the claim-evidence record. Preserve unsupported claims as failures until the sentence is narrowed, removed or supported by a better source; never change a citation merely to make the checker pass.
