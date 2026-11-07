# Cloud research from a GitHub issue

Production uses [CheapAI and CodeKey task routes](PRODUCTION-MODEL-ROUTING.md)
and five dedicated Actions Secrets, with no UUAPI requirement. Configuration
checks do not enable paid automatic continuation. Existing budgets and human
gate decisions remain authoritative.

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

Default controlled literature search covers all seven available public sources
(six without an OpenAlex key) and permits twelve actual new search calls per
cycle. An explicit `program/literature-search-plan.json` may set
`max_search_calls` from 1 to 60; this is throughput, not a paid allowance or proof
of coverage. Fallback `direct`, `method_alternatives` and `counterevidence`
queries are broad leads, never invented adjacent-field evidence or saturation.
Topic-specific queries and actual citation chains still need source receipts.
The seven direction weights are the owner's actual finite nonnegative values
summing to one; the system does not force equal employment/PhD weights.

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
| `authorize_budget` | `new_ceiling_cny` | Record an actual authorized cumulative project total; no fixed increment or routine approval layer. No model call. |
| `reconcile_budget` | `reservation_id`, `actual_cost_cny`, `evidence_note` | Record the checked gateway bill for an ambiguous or interrupted call and release its reservation. No model call. |
| `cycle` | `context`, optional `stage` and critical `task_kind` | One current-stage Claude plan/critic and GPT writer/remediation cycle through the production task routes. |
| `continuation` | none | Recheck the bound owner policy, gates, configuration and ledger; run one permitted current-stage cycle and continue only while healthy. |
| `paperqa` | `corpus`, `question`, optional compatibility `settings` | Bounded native source Q&A with deterministic retrieval and Sol high through the central budget; not the upstream paid PaperQA2 SDK. |
| `auxiliary` | `manifest` | One bounded metadata/engineering/multimodal/format/screening helper from evidence/auxiliary-jobs/*.json; no model override or budget grant. |
| `literature` | `request_file` | Execute one declared operation from a project `program/*.json` file, including the scientific preparation operations below. |
| `tooluniverse` | `request_file` | Reviewed ToolUniverse 1.5.1 `UniProt_get_entry_by_accession` only: canonical accession, compact output, one fixed public HTTPS GET, no credentials/model calls, hash-bound attempts and cost basis. Other tools require a metered cost adapter. |

`allow_paid: true` identifies a potentially billable action, not fresh spending
authority. Apply [the current cost policy](TOTAL-COST-POLICY.md): actual existing
cumulative totals, all attempts and conservative unknown-charge bounds, without
fixed CNY 300 steps, per-paper/per-call caps, startup opt-ins or manual billing
gates. Never increase a configured total automatically. Current routes and
secrets are documented in [production routing](PRODUCTION-MODEL-ROUTING.md).

The serialized controller checks the exact current stage, runs `ready` and
`advance` after A/B checks, and records automated G0/G3/G4/G5 decisions. Only
actual G1/G2 topic choices require authenticated owner decisions. A stalled
research decision needs actual new input rather than a new budget approval.
No workflow logs into a publisher portal or submits a manuscript.

The existing `literature` action accepts these additional operation files:

| Operation JSON | Result |
|---|---|
| `{"action":"scientific_judgment","task":"claim_evidence","request_file":"program/claim-check.json"}` | Refresh the source-bound report using actual protected critic/panel responses; absent responses remain preparation. Other declared tasks are `citation_crosscheck`, `novelty_adjudication`, `judgment_benchmark` and `research_memory`. |
| `{"action":"research_case","paper_id":"P01"}` | Inspect `papers/P01/research-case.json` against the [research-case schema](../schemas/research-case.schema.json), current claims, sources and results; report missing evidence without filling it. |
| `{"action":"research_case","paper_id":"P01","kind":"reproduction"}` | Prepare a local, content-addressed release from the actual recorded runner inputs/results. Other exports are `case`, `preprint`, `rebuttal` and `retarget`; they retain history and never publish externally. |

To supply a scientific judgment to an existing model invocation, select its
`operation`, `request_file`, actual stage names and optional `paper_id` in
`program/research-control.json.scientific_judgments`; `panel_views` selects the
applicable final seats (`domain`, `editorial`, `statistics`). Source bindings
are checked again when consuming the protected response. Calibration answer
keys and independent sample labels are excluded from reviewer context. This
selection adds work to the existing call, not another automatic paid role.
Reproduction requires an actually completed Python result-table run. Portable
host runs retain the recorded interpreter; ordinary cloud Docker runs replay
their actual digest-pinned image, inputs, seed and resource limits with network
access disabled and inputs read-only. The container environment is identified
by its image, not the controller's host Python. Separately mounted Meta/theory
toolchains use their existing study-route exports. Unknown PIDs, missing rights
or incompatible environments are not invented.

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
