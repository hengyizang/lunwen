# Controlled cloud research operations

For data_contract, data_cleaning_preview, empirical_design, empirical_reporting
and economic_data, see [empirical data workflow](../docs/EMPIRICAL-DATA-WORKFLOW.md).
These reuse the stage-scoped queue. Preparation/retrieval never grants G3, and
observation acquisition requires protected, source-bound rights verification.
The controller records lawful automatic decisions without inventing human review. Estimation and
cleaning replay remain exact approved experiment commands.

The controlled operations `research_extensions`, `evidence_context`, `calibration_analysis` and `word_render` are documented in [Experiment and evidence extensions](../docs/RESEARCH-EXTENSIONS.md). `read_paper` accepts optional `pages` (unique original 1-based page numbers) for bounded reading without paid translation. No operation changes model roles, approves a scientific gate or starts unapproved paid computation.

The model authors plans and code. The GitHub controller retrieves evidence, executes approved experiments and builds final files. A model-authored JSON boolean is never human approval. Unknown facts remain missing. No action below grants a scientific gate, submits a paper or changes the cumulative CNY spending ceiling.

The [workflow](workflow.md) is authoritative: ordinary planner → writer → one
fresh advisory critic means three calls; actual findings trigger repair/recheck.
Final B preparation uses one source-bound three-family blind panel and the
actual venue/export checks, reused while that snapshot remains unchanged.
G1/G2 retain owner topic decisions, and A checks protect real scientific
integrity. Numeric ratings and CFH/H/AD/editorial observations are C, not gates.

## Request format

Study-specific builders: study_prepare plus paper_id at experiment-design
prepares the reviewed Meta/Lean CPU runtime, input hashes and identity projection.
supplemental_prepare plus paper_id at writing-and-review initializes a separate
unapproved reviewer child study and its deterministic builders. Dependency setup
is cloud-only; neither operation executes scientific runs or grants approval.
See [dedicated study routes](../docs/SCIENTIFIC-STUDY-ROUTES.md).

Write `program/cloud-operations.json` as `{"schema_version":"1.0","operations":[...]}`. Maximum 16 operations, each with `stage` and `action`. Paths are relative to this project. The controller saves results and failures in `state/research-steps.json`. Read this report before making another plan. Do not write controlled receipts yourself.

| Stage | Action and fields | Controller behavior |
|---|---|---|
| topic-intelligence | `direction_search`, `queries` (1–3 strings; one operation) | Optional Tavily search with explicit CNY/credit pricing, shared budget reservation and exact usage settlement. Seven-day query cache. Results are leads, not primary evidence. Without its key/rate, supply official URLs from Codex web research. |
| topic-intelligence | `citation_graph`, `doi`, `direction` (`forward` or `backward`) | Controlled citation API receipt; one failed source does not establish search saturation. |
| topic-intelligence | `read_paper`, `pdf`, `output`, `manifest`, optional `max_pages` | Bounded PDF extraction to `literature/readers/`. The exact manifest must have source-verified research/cloud/redistribution rights recorded by the controller and match the PDF hash. A real owner decision can also supply reviewed evidence. Personal-use-only papers must not be published to Git or public artifacts. Extraction is not a human read declaration. |
| topic-intelligence | `triage_leads`, `receipt_id`, `provider` (`openrouter` or `bocha`), optional `limit` ≤8 | Optional labels on public metadata from a valid search receipt. Retains every lead; cannot certify novelty, quality, eligibility or source inclusion. No private project text is sent. |
| experiment-design | `data_quality`, `dataset_id`, `path`, optional `label_column`, `split_column`, `group_column` | Measures actual acquired data; the controller records a separate current hash-bound automated confirmation after applicable checks pass. Changed operation arguments invalidate the cached report. |
| experiment-design | `power`, `paper_id`, `method`, `effect_size`, `alpha`, `target_power`, `ratio`, `effect_size_basis`, optional `groups` | Uses the declared statistics runtime and existing research-quality contract. An assumed effect size requires a defensible source. It does not freeze a preregistration. |
| writing-and-review | `render_figure`, `spec` | Executes the deterministic figure renderer on actual registered data. |
| writing-and-review | `docx`, `source`, `metadata`, `output` | Creates genuine DOCX from provenance-bound English source and metadata using python-docx. |
| writing-and-review | `compile_tex`, `paper_id` | Compiles provenance-bound `manuscript/main.tex` in a pinned, network-disabled, read-only TeX container; preserves the build receipt and PDF. |
| topic-intelligence through writing-and-review | `research_notebook` | Builds incremental question/evidence/decision views from `program/research-notebook.json`; keeps opposing evidence and honest reading scope. No interpretation or gate is certified. |
| topic-intelligence through writing-and-review | `retrieve_evidence` | Free lexical/BM25 leads from explicit hash-bound sources in program/retrieval-plan.json. Records original line locators and all searched sources; never modifies a context plan or excludes nonmatches. See COST-EFFICIENCY.md. |
| experiment-design or experiment-execution | `method_tools` | Inspects pinned `program/method-tools.json` contracts and registered validation outputs; never directly executes methods. |
| paper-architecture or writing-and-review | `journal_dossiers` | Rechecks dated official cost/OA/timing/policy sources from `program/journal-dossiers.json`; unknown values remain unknown. |
| paper-architecture or writing-and-review | `journal_sources` | Fetches declared public publisher URLs with network safeguards, at most twenty GETs per operation; records protected raw/normalized hashes and pending URLs. |
| writing-and-review | `statistical_reporting`, `paper_id` | Checks actual numerical evidence against current Methods/Results/caption passages. False or mismatched numbers remain A blockers; the final checked report binds the current sources and is reused only while unchanged. |
| writing-and-review | `citation_audit`, `paper_id`, optional `manual_verifications` (owner-controlled `state/` path), `refresh_metadata:true` | Rechecks the current canonical references.bib and manuscript. Reuses only hash-bound Crossref metadata younger than 24h, never an old PASS; expired, changed or corrupt records are fetched again. Offline/failed requests never become verified. Manual names and DOCX human checks cannot be invented by the queue. The report is controller-owned. |
| writing-and-review | `docx_revision`, `paper_id` | Builds genuine Word clean/tracked/response package after revision controls pass; unsupported complex changes are refused. |
| writing-and-review | `watermark_cleanup`, `paper_id`, `source`, `expected_sha256` | Runs the pinned upstream Unicode cleaner on supported prose; creates a protected derived candidate/diff/receipt and reuses a still-valid receipt. Does not overwrite canonical text or verify statistical watermark absence. |

An example request is `{"stage":"writing-and-review","action":"render_figure","spec":"papers/P01/figures/main.spec.json"}`. Final exports still require scientific and visual review.

Input contracts and limits for the added quality operations are in [Research improvements](../docs/RESEARCH-IMPROVEMENTS.md). Models may author proposed inputs, but generated receipts, histories and revision packages are protected.

## Literature and data

G1 controlled literature search runs before paid authoring.
`program/literature-search-plan.json` can contain 1–60 `searches`, each with
`provider`, `query`, `query_family`, and `limit` (≤50). Defaults cover Crossref,
Semantic Scholar, arXiv, Europe PMC, DBLP and HAL; configured OpenAlex adds the
seventh provider. The default direct, method-alternative and counterevidence
query families create 18 or 21 planned searches. Each invocation performs at
most 12 fresh calls by default; explicit `max_search_calls` accepts integers
1–60. Remaining searches continue through the existing queue and receipts.
Citation chaining supplies additional source-bound leads, not proof of saturation.
Raw/normalized hashes and search-log/API-ledger records are persisted. Fresh
successful searches are reused for seven days. Failed queries have a six-hour
cooldown so they cannot starve remaining providers. A total failure stops paid
authoring. Coverage, screening and saturation remain evidence-bound judgments.

Write proposed downloads under `data/manifests/`, following
`schemas/dataset-manifest.schema.json`. Pin the exact SHA-256 and expected bytes
(up to 2 GB per file). The controller verifies primary license, privacy,
research/cloud-use and storage evidence and records the exact manifest hash in
protected `state/data-authorizations.json`. Sufficient lawful evidence enables
an explicitly automated authorization; missing or conflicting evidence stays
blocked. `authorize_data` also preserves actual owner-reviewed decisions, but
does not impose another human approval on every lawful acquisition. A generated
`confirmed_by_human` boolean cannot supply either kind of evidence. Acquisition
preserves a hash-bound receipt and re-downloads missing raw files after a runner
change. Raw/private data is excluded from checkpoints; derived data also need
verified redistribution/storage rights.

At G4 the controller executes one pending run per job using the exact G3-frozen
plan and budget. Use digest-pinned Docker, hash-declared inputs and distinct
explicit `results/` output paths. Optional run `resources` declares positive
`cpu` and `memory_gb` and an integer `gpu` count ≥0; omitted fields default to
2 CPUs / 4 GB / 0 GPUs. These defaults are not hard research-scale ceilings.
Before reserving compute cost, the runner checks actual CPU affinity, cgroup
limits, daemon capacity and, for GPU requests, visible NVIDIA devices and the
Docker NVIDIA runtime. Insufficient or unknown capacity produces an actionable
failure; no hardware is rented or silently substituted. The default GitHub
Ubuntu runner does not supply a GPU.

`timeout_seconds` must fit the current controller deadline with 120 seconds left
for receipts/checkpoints. The two 65-minute cloud workflows establish a
60-minute work deadline at their first step; nested command deadlines cannot
extend their parent. Without a controller deadline the conservative fallback is
1,200 seconds. A larger frozen request therefore needs an actually capable
controlled runner and sufficient remaining execution time, within the same
cumulative compute/cash total. Changed resources invalidate the existing G3
plan hash; no new per-run budget or payment approval is created.

The container keeps network disabled, a read-only root, dropped capabilities,
credential exclusion and only named output files writable. Receipts record the
requested and observed capacity without claiming measured utilization. Failed
and negative results remain registered; actual recovery conditions govern a
retry, and changed protocols return to G3 without erasing earlier attempts.

## Direction assessment contract

Write `program/direction-assessments.json` with a shared recent `window_start`/`window_end` (≤90 days, ending within 14 days) and at least three `candidates`. Each candidate needs:

- `id`, `cloud_feasible:true`, `no_future_lab_dependency:true`, `authorized_data_plan`, `cloud_compute_plan`, `career_stage` and `sample_limits`.
- `observations`: each has `kind` (`funded_phd` or `job`), `employer`, `title`, `country`, `observed_date`, `eligible`, `eligibility_rationale`, the current `constraints_sha256`, and `evidence:{url,quote}`. The quote must occur in the fetched official page and include the posting title. Funded entries additionally need `fully_funded:true` and separate `funding_evidence:{url,quote}` supporting funding.
- Job `salary`: `amount`, `currency`, `period` (`year` or `month`), `basis:"gross"`, matching `career_stage`, and `evidence:{url,quote}` containing the actual number. Non-CNY salaries also need `fx_to_cny` and dated `fx_evidence`. Missing salary is a blocker, not an invented midpoint.
- `assessments` for `future_growth_potential`, `phd_position_competition`, `job_market_competition`, `background_fit`, `application_route_fit`. Each needs `score` (0–5, higher is more favorable), `method` (`measured`, `proxy`, `assessment`), `confidence`, `rationale`, `anchor_description`, and `evidence:[{url,quote}]`. Background fit instead binds the current `constraints_sha256`. Explain proxies and unknown applicant counts; never invent a competition rate.

The controller retrieves allowed primary URLs, saves their content/hash/date,
deduplicates employer/title/country within each posting type and writes protected
`program/direction-ranking.json`. Only verified observations contribute. When
this optional career-ranking adapter is selected, use the project's declared
`intake/constraints.json.ranking_weights`, with all seven factors summing to one;
the historical user's 25/25/15/7.5/7.5/10/10 preference is not a universal default.
The adapter's provisional count anchors are 1/5/15/30/60 observed eligible
postings. Employment combines job counts and gross annual salary equally;
nominal CNY salary anchors are 100k/200k/300k/500k/800k. These C decision aids and
±20% weight sensitivity do not estimate populations, purchasing power or
admission probabilities, and do not select a doctoral topic. Missing evidence
cannot be replaced with invented scores. Scientific novelty and independence
require evidence-based judgment and the actual G1/G2 topic decisions.

## Protected controls and optional owner review

The [eight research increments](../docs/RESEARCH-INCREMENTS.md) add
non-billable research_increments, increments_inventory (paper_id at G5) and
increments_freeze (kind argument/lesson, record_id). evidence_context additionally
accepts task_id for a declared chapter/task. The trusted author boundary freezes
argument plans before writing; a queue-requested argument freeze is a review
checkpoint only. Reports and freeze/history files are executor-owned.
Owner-only confirm_research_increment selects kind voice/lesson, record_id and
decision authorize_sample/adopt_rule/rollback_rule through the existing exact
dossier flow. These operations never approve science or change paid authority.

Follow-up deterministic builders are documented in [Quality controls follow-up](../docs/RESEARCH-IMPROVEMENTS-FOLLOWUP.md). Add `research_support`, `support_sources`, `research_notebook_daily` or `review_packets` at their documented stages, or `revision_ledger` plus `paper_id` at writing-and-review. Only `support_sources` performs bounded public metadata GETs; none enables paid calls or experiments. Owner-only `confirm_review_packet` uses `packet_id`, exact dossier SHA and structured human `judgments`; it never grants a scientific gate.

The model-authored queue cannot write protected approvals, receipts or a human
identity. The controller performs applicable source/evidence checks, records
automated data/reproduction/protocol decisions honestly, and advances checked
G0/G3/G4/G5 states. Only G1/G2 topic decisions require the owner. Existing
authenticated actions remain available for real owner decisions and exceptional
corrections; their presence is not a new mandatory review at every stage. See
[Cloud topic controls](../docs/CLOUD-HUMAN-CONTROLS.md) for exact dossier-bound
`review_dossier`, `ready`, `approve`, `advance`, `reopen` and source decisions.
# Literature workbench operations

Figure-reference operations use the existing non-billable `literature` boundary
or current-stage queue at G1–G5: `figure_gallery_sync`, `figure_gallery_search`
(`query`, optional `top_k`, `semantic`, `venues`, `years`, `tiers`, `patterns`,
`topics`), `figure_story` (`operation`, `request_file`), `editable_figure_export`
(`request_file`), `editable_figure_verify` (`receipt`). Read
[Figure workbench](../docs/FIGURE-REFERENCE-WORKBENCH.md) for exact schemas,
bounded model context, original briefs, shared style, native exports and rights.
These operations never spend model budget or approve a scientific figure/gate.

Use [LITERATURE-REASONING.md](../docs/LITERATURE-REASONING.md) for the existing
authorized scientific writer's section-specific objectives, attributed reading
answers, closest-work comparisons, gap hypotheses and 20-axis experiment
proposals. Read original full texts before filling scientific fields. Persist
semantic objectives and experiment candidates in program/literature-reasoning.json;
itinerary/compare validate exact source anchors and the shared doctoral question.
A limitation or unsuccessful search is a hypothesis to challenge, never proof of
novelty. Route reviewed proposals into existing G1/G3 records; no new paid role,
automatic gate approval, budget or experiment authority is introduced.

literature_progress(request,progress?) records an attributed answer bound to the
current step hash and adapts the next question. Do not directly replace protected
reading history. The browser supports snapshot search for metadata, original
text/notes, card experiment settings and original figure captions with P01-P06
and topic filters. literature_figures also accepts question, max_selected and
auto_discover; automatic crops retain actual caption/page coordinates and are
explicitly page-context candidates rather than verified exact plot boundaries.

literature_feedback(feedback,expected_leads_sha256,plan?) records relevance,
identity duplicates, source accessibility, evidence sufficiency and experimental
usefulness. Actual executed use requires current run/registry/output evidence.
literature_feedback_propose(event_ids,expected_plan_sha256,proposal?,plan?) creates
bounded before/after keyword/weight changes and operational follow-ups. Only an
authenticated owner cloud issue can literature_feedback_review a proposal with
exact current plan/proposal hashes; the model operation queue cannot authorize
adoption. Repeated feedback batches cannot be learned twice. Doctoral scope,
exclusions, contrary evidence, gates and budgets cannot be changed through feedback.

literature_register selects a real candidate from the exact current topic-leads
hash using candidate_id and expected_leads_sha256. Optional paper_id,
acquisition_receipt {path,sha256}, manifest and reader {path,sha256} link an
lawfully authorized full text; metadata-only registration grants no screening or
full-text-read decision.

See [LITERATURE-WORKBENCH.md](../docs/LITERATURE-WORKBENCH.md). At any research
stage after intake, the existing queue accepts literature_discover(plan,output?),
literature_resolve(url), literature_figures(pdf,manifest,figures?),
literature_analyze(paper_id,config?,execute?,max_output_tokens?),
literature_workbench(config?), literature_search(query,topic_id?,paper_id?,limit?),
literature_itinerary(question,topic_id?,paper_id?,limit?), and
literature_compare(paper_ids,question?). Discovery uses the explicit proposed or
current doctoral question in program/literature-plan.json. Source-bound topic
leads feed the existing G1 shortlist/hypothesis/novelty/thesis contracts; ranking
does not choose a topic or grant novelty. Rhetoric keywords are discovery aids.

Do not author program/topic-leads.json or reports/literature-* executor results.
Author source-bound workbench inputs/cards instead and request their builders.
No paid call occurs except explicit literature_analyze execute:true through the
existing authorized OpenAI evidence-synthesis route. Use metadata and current
notes before requesting full-text reanalysis. Do not alter model routing.
Acquisition quarantines raw full text; reader/figure persistence requires the
existing exact manifest with controller-recorded lawful rights. The non-billable owner cloud
job literature can execute one request_file operation without a paid cycle and
forbids execute:true. No operation supplies a human topic decision or bypasses G0-G5.

