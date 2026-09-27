---
name: skill-catalog
description: Inventory and compare Codex project or personal Skills with hash-cached offline reports and explicitly confirmed safe backup, update or disable operations.
---

# Skill catalog

Use `scripts/skill_catalog.py scan --root <exact-skills-folder> --output-dir <D-drive-report-folder> --mcp-config <exact-json>`. Report new/changed/reused/missing entries, security lint findings, MCP commands with literal-secret warnings, and possible overlaps as candidates rather than proven duplicates. The offline HTML report reads no remote scripts. Use `lint --target <exact-skill>` before planning any activation.

For a targeted change, first run `plan --root <exact-root> --target <exact-child-skill> --action backup|update|disable|install --output-dir <report-folder>`. Installation additionally requires an explicit `--install-root`; under the D-drive policy use a child of `D:\ad\lunwen`/`/mnt/d/ad/lunwen`. Inspect the exact target, tree hash, security report and one-use confirmation token. Only after the user requests that specific operation, run `apply --confirm-token <token> --output-dir <report-folder>`. Any source change invalidates the token. High-severity lint blocks install; update is restricted to a clean standalone HTTPS GitHub repository and fast-forward only; disable moves the Skill into recoverable trash. Never bulk-delete or modify plugin-owned Skills.
