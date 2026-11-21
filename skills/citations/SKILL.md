---
name: citations
description: Check reference identity and whether the available source supports the actual claim.
---

# Citations

Resolve DOI, stable URL or local original identity. Read the passage needed for the cited assertion and preserve its context, scope and uncertainty. `scripts/citation_audit.py` and `scripts/ref_verify_adapter.py` help with identity/abstract checks; do not call them full-text semantic verification. Distinct claims may need different passages. Correct important mismatches and report inaccessible material rather than inventing citations or human verification.

Follow the current research-first principles in `AGENTS.md`; use this capability whenever it helps the task. Historical stage labels are compatibility context, not prerequisites.
