# Cloud research from a GitHub issue

For owner-confirmed round-the-clock continuation, see
[Continuous cloud research](CONTINUOUS-CLOUD-RESEARCH.md).
For shared or separate OpenAI/Claude gateways, see [the cloud startup checklist](GATEWAY-STARTUP.md).

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
Manual jobs retain an owner issue as their command and audit record. Approved
continuation uses the standing confirmation with serialized schedule/dispatch
receipts. Both workflows share a lock to protect the budget and project state;
a new job is not a new spending approval.

| Action | Extra JSON properties | Effect |
|---|---|---|
| `preflight` | none | Restore project state and report gateway configuration, budget and continuation readiness; no model call. |
| `acceptance` | none | Call public literature APIs, run Docker isolation, and check installed adapter versions. No model call. |
| `free_jev_probe` | none | One fixed, synthetic public-metadata request to OpenRouter `typesafe/jev-router`, only with a dedicated API key capped at USD 0 (BYOK counted). Require zero provider prices, an exact serving model and a zero-cost generation receipt. No research data or scientific gate change. |
| `init` | `paper_count` (default 6) | Create a six-paper project in its state branch. |
| `status` | none | Read the persisted stage, gate and blockers. |
| `authorize_budget` | `new_ceiling_cny` | Record the owner's next CNY 300 cumulative model API tranche. No model call. |
| `reconcile_budget` | `reservation_id`, `actual_cost_cny`, `evidence_note` | Record the checked gateway bill for an ambiguous or interrupted call and release its reservation. No model call. |
| `cycle` | `context`, optional `stage` | One current-stage Claude plan/critic and GPT writer/remediation cycle through UUAPI. |
| `continuation` | none | Recheck the bound owner policy, gates, configuration and ledger; run one permitted current-stage cycle and continue only while healthy. |
| `paperqa` | `corpus`, `question`, optional `settings` | Paused as a paid cloud action until its external model charges are meterable against the tranche. |
| `tooluniverse` | `request_file` | Paused as a paid cloud action until any external API charges are meterable against the tranche. |

Only `cycle`, `continuation`, `paperqa`, and `tooluniverse` accept `allow_paid: true`; every
other action requires `false`. `allow_paid: true` identifies a potentially
billable job, not a fresh spending approval. The owner first approves a
**cumulative** ceiling of CNY 300 with a separate `authorize_budget` issue,
then CNY 600, CNY 900 and so on by one CNY 300 increment each time. Subsequent
cycles inside the approved unused ceiling need no new spending approval. The
owner issue remains the manual-cycle trigger; approved continuation uses native
workflow wakeups. The initial ceiling is zero;
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
and stops at a pending human gate. Automatic cycles never invoke `ready`, `approve` or `advance`. Explicit owner
operations use the separate [hash-bound human controls](CLOUD-HUMAN-CONTROLS.md).
No workflow performs a publisher login or submission.

For a shared gateway, configure GitHub repository secret `UUAPI_API_KEY` and repository
variables `UUAPI_BASE_URL`, `UUAPI_ANTHROPIC_MODEL`, `UUAPI_OPENAI_MODEL` and
`DR_OS_MODEL_PRICING_JSON` with the exact model IDs and each model's verified
CNY input/output rates per million tokens, e.g. an object keyed by exact model
ID with `input_per_million` and `output_per_million` numbers. Missing rates
block the paid call. Alternatively configure complete `UUAPI_OPENAI_API_KEY` /
`UUAPI_OPENAI_BASE_URL` and `UUAPI_ANTHROPIC_API_KEY` /
`UUAPI_ANTHROPIC_BASE_URL` pairs. Both cloud entry points pass
`UUAPI_OPENAI_PROTOCOL` and `UUAPI_OPENAI_CHAT_TOKEN_FIELD` to the same validated
adapter. See [startup](GATEWAY-STARTUP.md) for the non-billable check and immediate
manual start modes. The runner fixes the roles to `uuapi-anthropic` for
planning and independent criticism and `uuapi-openai` for persistent writing.
Strict reported-model checking is enabled. PaperQA2 may require its own
`OPENAI_API_KEY` secret according to the approved local settings; no key is
placed in an issue, commit, ZIP, or comment.

`acceptance` is a Linux GitHub runner result. It cannot establish that Docker
Desktop or the D-drive path works on a Windows computer. It excludes
quota-consuming SerpApi and unauthenticated Semantic Scholar; failures in the
remaining public providers are recorded as failures, not silently skipped.
For reliable OpenAlex calls, put a free OpenAlex key in the repository secret
`OPENALEX_API_KEY`. It is sent only in the Authorization header. The key is optional for startup configuration; the literature transport checks
its own provider configuration before use. A public provider's
503 or 406 remains a failed acceptance receipt; retry when its service recovers.
The cloud literature job also passes the optional `LITERATURE_CONTACT_EMAIL`
secret used by the scheduled acceptance run as provider contact metadata.
OpenAlex's [authentication](https://help.openalex.org/api/authentication/) and
[deprecation](https://help.openalex.org/api/deprecations/) guidance was checked
on 2026-09-28.

The exact input contract is in `schemas/cloud-job.schema.json`. The script
also enforces action-specific properties, owner ID, a single JSON object,
strict paths and the paid-action flag before any project is restored.

For an optional `free_jev_probe`, configure the repository secret
`OPENROUTER_API_KEY` with a **dedicated key whose per-key limit and
remaining limit are both USD 0, with BYOK usage included in the limit**.
The probe checks those fields through OpenRouter's `GET /api/v1/key` before its
single model request. It also sets `provider.max_price` to zero for token,
request, and image pricing. If the router cannot serve this request for free,
the job fails without a paid-model fallback. It then checks the generation's
`total_cost`, actual serving model and provider, and key usage; the artifact
contains only a bounded synthetic label and billing/identity receipt. A
zero-cost probe does not enable Jev for the manuscript author, Claude critic,
literature exclusion, novelty assessment, or a G0–G5 gate. Bocha's API remains
outside this action until its exact free quota and API contract are verifiable.
