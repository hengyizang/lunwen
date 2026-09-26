---
name: skill-catalog
description: Inventory and compare Codex project or personal Skills with hash-cached offline reports and explicitly confirmed safe backup, update or disable operations.
---

# Skill catalog

Use `scripts/skill_catalog.py scan --root <exact-skills-folder> --output-dir <D-drive-report-folder>`. Report new/changed/reused/missing entries and possible overlaps as candidates, not proven duplicates. The offline HTML report reads no remote scripts.

For a targeted change, first run `plan --root <exact-root> --target <exact-child-skill> --action backup|update|disable --output-dir <report-folder>` and inspect its target/hash and one-use confirmation token. Only after the user requests that specific operation, run `apply --confirm-token <token> --output-dir <report-folder>`. Update is restricted to a clean standalone HTTPS GitHub repo and fast-forward only; disable moves the skill into recoverable trash. Never bulk-delete or modify plugin-owned Skills.
