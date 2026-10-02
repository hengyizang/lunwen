# Controlled cloud research operations

The model authors plans and code. The GitHub controller retrieves evidence, executes approved experiments and builds final files. A model-authored JSON boolean is never human approval. Unknown facts remain missing. No action below grants a scientific gate, submits a paper or changes the cumulative CNY spending ceiling.

## Request format

Write `program/cloud-operations.json` as `{"schema_version":"1.0","operations":[...]}`. Maximum 16 operations, each with `stage` and `action`. Paths are relative to this project. The controller saves results and failures in `state/research-steps.json`. Read this report before making another plan. Do not write controlled receipts yourself.

| Stage | Action and fields | Controller behavior |
|---|---|---|
| topic-intelligence | `direction_search`, `queries` (1–3 strings; one operation) | Optional Tavily search with explicit CNY/credit pricing, shared budget reservation and exact usage settlement. Seven-day query cache. Results are leads, not primary evidence. Without its key/rate, supply official URLs from Codex web research. |
| topic-intelligence | `citation_graph`, `doi`, `direction` (`forward` or `backward`) | Controlled citation API receipt; one failed source does not establish search saturation. |
| topic-intelligence | `read_paper`, `pdf`, `output`, `manifest`, optional `max_pages` | Bounded PDF extraction to `literature/readers/`. The exact manifest must have owner-confirmed research/cloud/redistribution rights and match the PDF hash. Personal-use-only papers must not be published to Git or public artifacts. Extraction is not a human read declaration. |
| topic-intelligence | `triage_leads`, `receipt_id`, `provider` (`openrouter` or `bocha`), optional `limit` ≤8 | Optional labels on public metadata from a valid search receipt. Retains every lead; cannot certify novelty, quality, eligibility or source inclusion. No private project text is sent. |
| experiment-design | `data_quality`, `dataset_id`, `path`, optional `label_column`, `split_column`, `group_column` | Measures actual acquired data; leaves named human confirmation pending. Changed operation arguments invalidate the cached report. |
| experiment-design | `power`, `paper_id`, `method`, `effect_size`, `alpha`, `target_power`, `ratio`, `effect_size_basis`, optional `groups` | Uses the declared statistics runtime and existing research-quality contract. An assumed effect size requires a defensible source. It does not freeze a preregistration. |
| writing-and-review | `render_figure`, `spec` | Executes the deterministic figure renderer on actual registered data. |
| writing-and-review | `docx`, `source`, `metadata`, `output` | Creates genuine DOCX from provenance-bound English source and metadata using python-docx. |
| writing-and-review | `compile_tex`, `paper_id` | Compiles provenance-bound `manuscript/main.tex` in a pinned, network-disabled, read-only TeX container; preserves the build receipt and PDF. |

An example request is `{"stage":"writing-and-review","action":"render_figure","spec":"papers/P01/figures/main.spec.json"}`. Final exports still require scientific and visual review.

## Literature and data

G1 controlled literature search runs before paid authoring. `program/literature-search-plan.json` can contain `searches` with `provider`, `query`, `query_family`, and `limit` (≤50). Use direct, adjacent, counterevidence and citation chaining. Defaults query Crossref, arXiv and HAL (OpenAlex when configured). At most six fresh calls run per job; a second job completes the batch without paid authoring. Raw/normalized hashes and search-log/API-ledger records are persisted. Fresh successful searches are reused for seven days. Failed queries have a six-hour cooldown so they cannot starve remaining providers. A total failure stops paid authoring. Coverage, screening and saturation must still be honestly reviewed.

Write proposed downloads under `data/manifests/`, following `schemas/dataset-manifest.schema.json`. Pin the exact SHA-256 and expected bytes (up to 2 GB per file). The owner reviews the exact manifest and its cloud-use rights through `authorize_data`; the controller records the hash under protected `state/data-authorizations.json`. Merely setting `confirmed_by_human` in a generated manifest is insufficient. Acquisition preserves a hash-bound receipt and re-downloads missing raw files after a runner change. Raw/private data is excluded from checkpoints. Use a reviewed redistribution/storage plan for derived data too.

At G4 the controller executes one pending run per job using the exact G3-approved plan and budget. Use digest-pinned Docker, ≤1,200 seconds per run, 2 CPUs, 4 GB memory, hash-declared inputs, and distinct explicit `results/` output paths. No shell, host execution, network, credentials or control-state writes are available inside a cloud experiment. Failed and negative results remain registered; a failure pauses for inspection rather than silently retrying. A new plan requires a new G3 review.

## Direction assessment contract

Write `program/direction-assessments.json` with a shared recent `window_start`/`window_end` (≤90 days, ending within 14 days) and at least three `candidates`. Each candidate needs:

- `id`, `cloud_feasible:true`, `no_future_lab_dependency:true`, `authorized_data_plan`, `cloud_compute_plan`, `career_stage` and `sample_limits`.
- `observations`: each has `kind` (`funded_phd` or `job`), `employer`, `title`, `country`, `observed_date`, `eligible`, `eligibility_rationale`, the current `constraints_sha256`, and `evidence:{url,quote}`. The quote must occur in the fetched official page and include the posting title. Funded entries additionally need `fully_funded:true` and separate `funding_evidence:{url,quote}` supporting funding.
- Job `salary`: `amount`, `currency`, `period` (`year` or `month`), `basis:"gross"`, matching `career_stage`, and `evidence:{url,quote}` containing the actual number. Non-CNY salaries also need `fx_to_cny` and dated `fx_evidence`. Missing salary is a blocker, not an invented midpoint.
- `assessments` for `future_growth_potential`, `phd_position_competition`, `job_market_competition`, `background_fit`, `application_route_fit`. Each needs `score` (0–5, higher is more favorable), `method` (`measured`, `proxy`, `assessment`), `confidence`, `rationale`, `anchor_description`, and `evidence:[{url,quote}]`. Background fit instead binds the current `constraints_sha256`. Explain proxies and unknown applicant counts; never invent a competition rate.

The controller retrieves allowed primary URLs, saves their content/hash/date, deduplicates employer/title/country within each posting type and writes protected `program/direction-ranking.json`. Only verified observations contribute. Weights stay 25% funded positions, 25% employment/salary, 15% growth, 7.5% PhD competition, 7.5% job competition, 10% background, 10% application route. The provisional count anchors are 1/5/15/30/60 observed eligible postings. Employment combines job counts and gross annual salary equally; nominal CNY salary anchors are 100k/200k/300k/500k/800k. These are decision aids to review, not population estimates, purchasing-power comparisons or admission probabilities. The report includes ±20% weight sensitivity. Novelty, doctoral depth and originality are mandatory topic/design checks, never compensable direction scores.

## Separate owner review operations

The model-authored operations queue cannot approve a gate, confirm data/reproduction, screen literature as a human, or freeze preregistration. The authenticated owner issue boundary provides these non-billable actions with exact reviewed dossier hashes. See [Cloud human review controls](../docs/CLOUD-HUMAN-CONTROLS.md) for `review_dossier`, `ready`, `approve`, `advance`, `reopen`, quality confirmations, freeze and named source/screening decisions. All original scientific checks remain mandatory.
