# Empirical data, identification and result reporting

These independent native adaptations cover variable dictionaries, reproducible
cleaning, panel/time checks, optional causal design, economic vintages and sealed
reporting. They reuse existing manifests, owner data authorization, G3 freezing,
runner receipts, evidence, figures and G5. No model route, paid service, scientific
approval or separate result authority is added. All execution stays on the cloud.

## Data contracts and preparation

Create `data/contracts/<dataset_id>.json` using `schemas/data-contract.schema.json`.
Bind its original CSV, canonical manifest and identical data/datasets.jsonl entry.
Every variable needs type, definition, unit, source field, formula, explicit missing
codes and required status. Formulas are explanatory metadata, never executable
expressions. Full bounded scans reject nonfinite/invalid values and ragged rows.

Panel declarations include unit columns, time column, complete expected calendar
and explicit balanced/unbalanced policy. Checks cover entirely missing periods,
duplicate/blank keys, entry/exit, singletons, treatment timing and reversals.
Allowed imbalance causes warnings without silently dropping or filling rows.
Join checks cover key units, missing codes, one-to-one/many-to-one cardinality and
match rates. They do not silently merge inputs.

Cleaning allows only declared rename, missing-code normalization, fixed linear
unit conversion and value exclusions. Preserve originals, step-level sample
counts, output dictionary/formulas and hashes. No automatic winsorization,
imputation, outlier deletion, significance search or arbitrary code is enabled.

`data_cleaning_preview` runs deterministic preparation only in an open G3, before
freezing or any experiment attempt. It writes data/processed-preview/<id>.csv and
reports/data-cleaning/preview-<id>.json; changed recipes retain history. Validate
and freeze this prepared input. Copy scripts/data_cleaning_runtime.py unchanged
to analysis/data_cleaning_runtime.py for independent G4 replay. Use exact command:

```text
python analysis/data_cleaning_runtime.py --contract data/contracts/ID.json --dataset-id ID --output data/processed/ID.csv --receipt reports/data-cleaning/ID.json
```

Both implementation hashes belong in the contract; every original/contract/
manifest/registry/join source and copied runtime must be an approved run input.
The runner preflights exact commands, inputs and outputs before launching its
isolated container. The copied runtime has no dependency on an unmounted plan or
native package. Prepared data are not evidence of a research result.

## Optional causal designs

In the existing paper contract declare empirical_workflow with
`data_contract_ids:[ID]`, `causal_design:true`, `reporting:true` and optional
`economic_request_ids:[]`. Then use schemas/empirical-design.schema.json for
papers/Pxx/empirical-design.json. Bind actual dataset, runtime, estimand, treatment
assignment, sample rules, assumptions, rivals, diagnostic runs and all fixed
specifications. Each specification has its own ID, run, output, phase, family and
claim IDs. The scientific validity of assumptions is never self-certified.

| Native method | Supported scope | Explicit limits |
|---|---|---|
| DID | Two groups/two periods, stable treatment, complete observations per unit; unit-cluster CR1 | No staggered/dynamic DID; one pre-period cannot test a trend |
| IV | One endogenous variable, independent homoskedastic linear 2SLS | No clustered/robust IV interval or weak-IV-robust confidence set; first-stage threshold does not verify exclusion/independence |
| RDD | Sharp cutoff, fixed bandwidth, triangular local-linear HC1 | Conventional interval, not robust bias correction; manipulation/continuity/bias require registered diagnostics and review |

Other methods fail explicitly until a suitable reviewed adapter exists. Python/R
commands remain available through the ordinary approved runner; Stata is not a
required licensed dependency. The native runtime uses CPU numpy/scipy, which must
be installed in the chosen pinned container. Copy empirical_runtime.py unchanged
and use exact command `python <runtime> --design papers/Pxx/empirical-design.json
--data <CSV> --spec <ID> --output papers/Pxx/results/<ID>.json`. Data, design and
runtime hashes are frozen. No actual estimate runs before human G3 approval.

In existing experiment-evidence-plan comparisons use analysis_mode
`empirical_estimator`, empirical_specification_id, and
registered_result:{run_id,output,method_id}. Use unit_design:model,
aggregation:model_based_on_declared_units and pairs:[]; do not invent paired arm
observations. The adapter currently supports zero-null superiority only. Its
two-sided p-value cannot test a nonzero margin or equivalence. Existing pilot,
baseline/robustness coverage and simulation power remain required. Every
specification maps once, and one fit cannot masquerade as multiple baselines.
Declare family-adjusted confidence before running; existing Holm correction and
direction/interval decisions remain. Null/adverse/exploratory outcomes are kept.

## Economic data versions and permissions

Use data/economic-requests/<id>.json and economic-data-request.schema.json. FRED
requires FRED_API_KEY in cloud Secrets and an explicit snapshot_as_of vintage.
Observation requests bind exact units/frequency/seasonal adjustment. World Bank
supports current retrieval snapshots; unavailable historical vintages are rejected.
Metadata-only discovery does not authorize acquisition. Observations need an exact
query-scoped licensed access manifest, explicit allow_observations and the existing
protected owner data authorization. The owner control can approve a bounded API
scope before response bytes exist; it does not approve analysis or data fitness.

Keep that access manifest immutable. After retrieval, register a separate analysis
dataset manifest with the downloaded CSV hash and source-receipt provenance;
changing the original access manifest invalidates its permission/snapshot.
Raw responses/observations stay in ignored data/raw/economic-data. Public-safe
metadata/hash receipts stay in evidence/economic-data. Bounded HTTPS, pagination
totals, duplicates, dates, units and credential echoes are checked. Keys and
key-bearing URLs never enter receipts/errors. Identical current requests reuse
snapshots; tampered snapshots are not silently overwritten.

## Tables, figures and manuscript checks

The reporting builder checks actual approved executor seals and recomputes every
estimate from the current frozen CSV. Diagnostic outputs need their registered
ID, computed passed boolean and nonempty details; failed/missing diagnostics
block readiness. This does not establish their scientific adequacy.
All specifications go to papers/Pxx/tables/empirical-estimates.csv. Holm p-value
adjustments are separate by family and analysis phase; no best-p selection occurs.

At G5 create empirical-reporting-map.json with schema_version:1.0, paper_id and
specifications:[{id,locations:[{field,path,sha256,locator,quote,decimals}]}]. Map
every estimate, SE, interval bounds/confidence, raw/adjusted p, observation/unit
counts and phase to exact current source lines. Use L1 or L1-L3 and 0..12 decimals.
A positive p-value cannot be rounded to zero. A numeric location
can use notation:scientific with bounded decimals for an exact nonzero tiny value;
fixed decimal presentation remains the default. Every adverse/exploratory specification
remains locatable in the manuscript or supplement under the existing narrative rules.

Runtime JSON includes records:[{estimate,ci_low,ci_high,...}]. Existing
derive_figure_data with operation:json_rows, record_path:records, selected columns
and exact sealed source runs creates figure CSV through existing lineage. Reuse
registered renderers and human visual approval; do not redraw numbers by model.

## Cloud operations and sources

Use existing program/cloud-operations.json, with stage and actual input IDs:
data_contract / data_cleaning_preview / empirical_design at experiment-design;
empirical_reporting at experiment-execution or writing-and-review; economic_data
at topic-intelligence or experiment-design. Cleaning preview is preparation only;
actual replay and estimation go through experiment_runner. New reports/outputs are
writer-protected. G3/G4/G5 and packaging check source freshness. Raw input may need
exact authorized reacquisition after checkpoint restore; unavailable data blocks
recomputation rather than becoming a cached pass. Unconfigured Meta/theory and
non-tabular projects keep their existing routes.

Processed and preview data inherit source restrictions and never enter public Git.
They use the existing bounded cloud artifact checkpoint, retaining exact hashes
across fresh runners. Owner-reviewed cloud storage/use rights remain required;
restricted materials need an appropriate storage plan. Original raw bytes remain
excluded and may need exact authorized reacquisition. Missing bytes block the
current audit. No private or licensed dataset was uploaded in this engineering work.

Reviewed method ideas: [AERS selection](https://github.com/brycewang-stanford/Auto-Empirical-Research-Skills/blob/7a2437b8fc972774fa23cf9c572df12ff5fd1334/docs/CHOOSING_A_SKILL.md),
[Econ recipes](https://github.com/meleantonio/awesome-econ-ai-stuff/tree/dd890d51c789fb8f8e316a2d7e4ed5d4bd793c50/_skills),
[FRED metadata](https://fred.stlouisfed.org/docs/api/fred/series.html),
[FRED real-time semantics](https://fred.stlouisfed.org/docs/api/fred/realtime_period.html).
The upstream template's confusion between an overidentification test and weak-IV
inference was not copied; see [official interface](https://bashtage.github.io/linearmodels/iv/iv/linearmodels.iv.results.IVResults.anderson_rubin.html).
No p-hacking skill, CoPaper SaaS, broad catalog installer or external LLM DAG is
enabled. Native implementations are independently expressed. No upstream/data
licence is waived. Software checks never certify causality, novelty or Q1 quality.
