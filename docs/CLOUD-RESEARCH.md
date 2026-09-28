# Cloud research from a GitHub issue

The researcher can start Codex locally and use GitHub Actions for the runtime. The
cloud runner installs its own dependencies, reads and writes `cloud-state/<project>`,
and returns a GitHub Actions artifact. Local WSL2/Docker remains an optional,
separate machine-specific check. No local API key or Python environment is needed
for this path.

Only a new issue created by the `hengyizang` repository owner, with a title
starting exactly `[research-cloud]`, starts `.github/workflows/cloud-research.yml`.
Use the marker and one fenced JSON object; no prose or credentials:

````markdown
<!-- doctoral-research-os-cloud-job -->

```json
{
  "schema_version": "1.0",
  "action": "preflight",
  "project": "my-phd",
  "actor": "Hengyi",
  "allow_paid": false
}
```
````

The issue comment reports the result and links its run. The artifact contains
redacted logs, public acceptance receipts when applicable, and a ZIP of selected
tracked project results. The state branch contains only bounded project results;
raw/private data, credentials, model usage logs, caches, and experiment run
directories are excluded. The branch is updated without force push. Inspect
the branch diff and artifact before importing its work into `main`.
Open a new state-changing issue after the previous run finishes. Concurrent
updates to the same project fail safely on a non-fast-forward push and need a
new request; the runner never overwrites an earlier branch update.

| Action | Extra JSON properties | Effect |
|---|---|---|
| `preflight` | none | Check Python and redacted provider configuration. |
| `acceptance` | none | Call public literature APIs, run Docker isolation, and check installed adapter versions. No model call. |
| `init` | `paper_count` (default 6) | Create a six-paper project in its state branch. |
| `status` | none | Read the persisted stage, gate and blockers. |
| `cycle` | `context`, optional `stage` | One current-stage Claude plan/critic and GPT writer/remediation cycle through UUAPI. |
| `paperqa` | `corpus`, `question`, optional `settings` | Query a project-relative, authorized corpus with PaperQA2. |
| `tooluniverse` | `request_file` | Run a validated, project-relative ToolUniverse request. |

Only `cycle`, `paperqa`, and `tooluniverse` accept `allow_paid: true`; every
other action requires `false`. A new explicit owner issue is required for each
potentially billable run. Before creating one, estimate and disclose its model
and gateway charges. The default model budget in `config/defaults.json` is a
CNY 300 project ceiling, not an estimate or an authorization. The `cycle` uses
the current stage stored in `state/run.json`; it refuses a mismatched `stage`
and stops at a pending human gate. The workflow never invokes `ready`,
`approve`, `advance`, a publisher login, or submission.

For `cycle`, configure GitHub repository secret `UUAPI_API_KEY` and repository
variables `UUAPI_BASE_URL`, `UUAPI_ANTHROPIC_MODEL`, and `UUAPI_OPENAI_MODEL`
with the exact model IDs. The runner fixes the roles to `uuapi-anthropic` for
planning and independent criticism and `uuapi-openai` for persistent writing.
Strict reported-model checking is enabled. PaperQA2 may require its own
`OPENAI_API_KEY` secret according to the approved local settings; no key is
placed in an issue, commit, ZIP, or comment.

`acceptance` is a Linux GitHub runner result. It cannot establish that Docker
Desktop or the D-drive path works on a Windows computer. It excludes
quota-consuming SerpApi and unauthenticated Semantic Scholar; failures in the
remaining public providers are recorded as failures, not silently skipped.
For reliable OpenAlex calls, put a free OpenAlex key in the repository secret
`OPENALEX_API_KEY`. It is sent only in the Authorization header. The preflight
reports whether it is configured without revealing it. A public provider's
503 or 406 remains a failed acceptance receipt; retry when its service recovers.
The cloud literature job also passes the optional `LITERATURE_CONTACT_EMAIL`
secret used by the scheduled acceptance run as provider contact metadata.
OpenAlex's [authentication](https://help.openalex.org/api/authentication/) and
[deprecation](https://help.openalex.org/api/deprecations/) guidance was checked
on 2026-09-28.

The exact input contract is in `schemas/cloud-job.schema.json`. The script
also enforces action-specific properties, owner ID, a single JSON object,
strict paths and the paid-action flag before any project is restored.
