---
name: cloud
description: Use owner-only GitHub Actions to inspect or run a Doctoral Research OS project without a local research runtime.
argument-hint: <action> <project-slug>
disable-model-invocation: true
---

# Cloud research

1. Read `docs/CLOUD-RESEARCH.md`, `references/workflow.md`, and the relevant stage contract.
2. Use the GitHub repository `hengyizang/lunwen`. Check the current issue and state branch before creating a new request.
3. Create an owner issue titled `[research-cloud] <action> <project>` with the exact marker and single JSON block described in `docs/CLOUD-RESEARCH.md`. Do not put credentials in the issue.
4. Treat `cycle`, `paperqa` and `tooluniverse` as potentially billable. First disclose an estimate; set `allow_paid: true` only when the current user instruction explicitly authorizes that individual run. Use `false` for all other actions.
5. Monitor the issue comment, Actions run, redacted artifact and `cloud-state/<project>` branch. Diagnose failed steps without repeating a paid request.
6. Inspect the diff before offering a PR. Keep Claude read-only, GPT/Codex as persistent writer, and every human scientific gate pending. Never run `ready`, `approve`, `advance`, publisher login or submission through this skill.
