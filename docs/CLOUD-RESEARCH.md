# Cloud research from a GitHub issue

The researcher can start Codex locally and use GitHub Actions for the runtime. The
cloud runner installs its own dependencies, reads and writes `cloud-state/<project>`,
and returns a GitHub Actions artifact. Local WSL2/Docker remains an optional,
separate machine-specific check. No local API key or Python environment is needed
for this path.

For G0, set `execution_mode` to `cloud_only`. Local GPU, RAM and storage may
remain `null`; the GitHub runner supplies the execution environment. Record
an exact `target_submission_ready_date` when the goal is a short sprint, with
`time_horizon_years: null`. Cloud feasibility is mandatory for every current
paper, including any paper assigned to doctoral extension B. Future laboratory
work after admission may be planned separately, but no current result may depend
on it. Rank only feasible directions by funded positions, employment and salary,
future growth, competition, background fit and application-route fit. Novelty
evidence, doctoral depth and original contribution remain mandatory topic
requirements. When only the model API has a proposed CNY
ceiling, `cash_budget_usd` may stay null and external cloud compute must be
zero. A later non-model expense needs an explicit budget decision. Any draft
budget number remains subject to human review. A draft ceiling does not grant
spending authority or approve a scientific gate.

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
directories are excluded. The state branch does retain the aggregate approved
ceiling, estimated cumulative spend and unresolved reservations, without prompt
or response text. The branch is updated without force push. Inspect
the branch diff and artifact before importing its work into `main`.
Each job still has its own owner issue as a command and audit record. The cloud
workflow serializes issues to protect the shared budget and project state; it
does not treat a new issue as a new spending approval.

| Action | Extra JSON properties | Effect |
|---|---|---|
| `preflight` | none | Check Python and redacted provider configuration. |
| `acceptance` | none | Call public literature APIs, run Docker isolation, and check installed adapter versions. No model call. |
| `init` | `paper_count` (default 6) | Create a six-paper project in its state branch. |
| `status` | none | Read the persisted stage, gate and blockers. |
| `authorize_budget` | `new_ceiling_cny` | Record the owner's next CNY 300 cumulative model API tranche. No model call. |
| `reconcile_budget` | `reservation_id`, `actual_cost_cny`, `evidence_note` | Record the checked gateway bill for an ambiguous or interrupted call and release its reservation. No model call. |
| `cycle` | `context`, optional `stage` | One current-stage Claude plan/critic and GPT writer/remediation cycle through UUAPI. |
| `paperqa` | `corpus`, `question`, optional `settings` | Paused as a paid cloud action until its external model charges are meterable against the tranche. |
| `tooluniverse` | `request_file` | Paused as a paid cloud action until any external API charges are meterable against the tranche. |

Only `cycle`, `paperqa`, and `tooluniverse` accept `allow_paid: true`; every
other action requires `false`. `allow_paid: true` identifies a potentially
billable job, not a fresh spending approval. The owner first approves a
**cumulative** ceiling of CNY 300 with a separate `authorize_budget` issue,
then CNY 600, CNY 900 and so on by one CNY 300 increment each time. Subsequent
cycles inside the approved unused ceiling need no new spending approval. The
owner issue for each cycle remains the job trigger. The initial ceiling is zero;
the CNY 300 default in `config/defaults.json` is only a legacy local safety
limit. An approval example uses `action: "authorize_budget"`,
`new_ceiling_cny: 300` and `allow_paid: false`; the next approval must request
600. Before a cycle, estimate and disclose its possible gateway charges. The
runner persists aggregate CNY estimates and reserves a conservative per-call
amount before transport. Interrupted or ambiguous calls keep their reservation
until the actual provider bill is reconciled through an owner issue. A provider
usage report above the reservation is recorded and blocks further calls if the
approved ceiling is exceeded. These are estimates, so compare
them with the gateway bill before a threshold decision. The `cycle` uses
the current stage stored in `state/run.json`; it refuses a mismatched `stage`
and stops at a pending human gate. The workflow never invokes `ready`,
`approve`, `advance`, a publisher login, or submission.

For `cycle`, configure GitHub repository secret `UUAPI_API_KEY` and repository
variables `UUAPI_BASE_URL`, `UUAPI_ANTHROPIC_MODEL`, `UUAPI_OPENAI_MODEL` and
`DR_OS_MODEL_PRICING_JSON` with the exact model IDs and each model's verified
CNY input/output rates per million tokens, e.g. an object keyed by exact model
ID with `input_per_million` and `output_per_million` numbers. Missing rates
block the paid call. The runner fixes the roles to `uuapi-anthropic` for
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
