# Research-quality hard gates (v2.0.0)

These controls raise the evidence floor for a doctoral programme targeting
current JCR Q1 journals. They do not prove novelty, guarantee acceptance or
replace an advisor, statistician, domain expert, data steward or named human
approver.

## Recommended visual workflow

Start the dashboard:

```bash
bash scripts/bootstrap-wsl.sh --with-research-quality-tools
bash scripts/start-dashboard.sh
```

The quality panel reports six independent evidence states: novelty matrix, data
quality, power, preregistration, baseline reproduction and clean-room
reproduction. The ordinary `gate-check` remains authoritative and lists the
exact missing or stale artifact.

## G1: novelty and doctoral contribution

G1 literature evidence must come from executed retrievals, not model-authored
search summaries. Use the dashboard or `scripts/literature_evidence.py` to query
OpenAlex, Crossref, Semantic Scholar, arXiv, Europe PMC, DBLP or HAL. The
control plane stores the exact response bytes, a normalized work list and both
SHA-256 values. OpenCitations expands DOI citation graphs; authorized Web of
Science and Scopus CSV/JSON exports can be imported locally without automating
or bypassing their access controls. Every receipt remains blocked until a named
person screens the exact returned IDs and records exclusion reasons.

Theme B is a separate hard contract, not a status label. It must declare its
own doctoral question, claim IDs, paper IDs, primary-evidence plan,
falsification conditions, boundary conditions and negative-result fallback.
Its claims and papers must be disjoint from Theme A, and it must remain
scientifically meaningful if Theme A fails. G2 verifies those assignments
against `program/paper-map.json`.

Run the ordinary G1 model cycle. Codex must create both
`program/originality-audit.json` and `program/novelty-claim-matrix.json`.
The matrix is rejected unless every novelty claim:

- matches a claim in the originality audit;
- compares at least three recorded closest works;
- separates already-known components from the exact proposed difference;
- states a mechanism or rationale, falsification test, result expected if the
  claim is false, boundary conditions and residual risk;
- is backed by forward and backward citation chaining and at least two
  consecutive search rounds without a materially closer work.

This is a saturation rule, not proof that no unknown prior work exists. Read the
primary sources yourself before approving G1.

PaperQA2 and ToolUniverse are reviewed, disabled-by-default upstream options.
They can support local-corpus synthesis or topic-appropriate AI4Science work,
but never replace primary-source checks. Bind real local inputs and outputs
with `scripts/ai4science_evidence.py`; these receipts remain advisory and
require human verification.

## G2: complete venue candidates

Build `program/venue-candidates.json` from a human-authored candidate
specification and an authorized local JCR CSV/JSON export:

```bash
python3 scripts/venue_candidates.py build \
  --project my-phd \
  --spec private/venue-candidate-spec.json \
  --jcr-export private/jcr-export.csv \
  --source-url https://jcr.clarivate.com/ \
  --actor 'Your Name'
```

Every paper needs at least two candidates. Each candidate is bound to its exact
export row and must use a current or immediately prior JCR year, Q1, IF > 1 and
SCI/SCIE indexing. Scope fit, article type, official author guidelines, policy
source, ranking and selection status remain explicit. The licensed export is
not redistributed.

## G3: data quality

After a candidate becomes a human-confirmed entry in `data/datasets.jsonl` and
the licensed file is local, use the G3 **本地数据质量审计** card. Supply the exact
`dataset_id`, the project-relative local path, and—where available—the label,
split and group columns. The core scanner checks current SHA-256, complete scan,
missing cells, exact duplicates, constant columns, class imbalance, identical
rows across splits and group identifiers crossing splits.

Non-tabular paths are content-scanned rather than accepted with a warning. The
handlers cover images (Pillow), WAV, NPY/NPZ, HDF5 and Parquet; they inspect
readability, dimensions/shapes/dtypes, rates/channels, structure, exact
duplicates and path-inferred cross-split overlap. An unknown or unavailable
format handler is a blocker.

Equivalent CLI example:

```bash
python3 scripts/research_quality.py data-audit \
  --project my-phd \
  --dataset-id bearing-v1 \
  --path data/raw/bearing.csv \
  --label-column fault_label \
  --split-column split \
  --group-column machine_id \
  --actor 'Your Name'
```

Read the complete report and every warning. Only then use **阅读报告后确认**;
the confirmation is a separate protected file bound to the report hash:

```bash
python3 scripts/research_quality.py confirm-data-quality \
  --project my-phd --dataset-id bearing-v1 --actor 'Your Name'
```

Changing the report or underlying data invalidates the confirmation.

For processed data, add `--derived`; the manifest must already contain the
transformation history. A warning still requires scientific review even when
the deterministic report has no blocker. Sensor calibration, construct
validity, selection bias and label validity cannot be inferred from a CSV.

## G3: executable power or precision

Choose the analysis that matches the confirmatory estimand. The dashboard can
run `statsmodels` for independent, paired or one-sample t tests, ANOVA and an
independent two-proportion comparison. The effect size must come from a cited
prior study, a pilot not reused as the locked test set, or a prespecified
minimum practically important difference—not from the eventual result.

For complex ML metrics, clustering, temporal dependence or nested evaluation,
select Monte Carlo simulation. Provide a project-local simulation script and a
JSON result file with at least 1,000 simulations. The script reads parameters
from `RESEARCH_OS_SIMULATION_COUNT`, `RESEARCH_OS_EFFECT_SIZE`,
`RESEARCH_OS_ALPHA` and `RESEARCH_OS_RANDOM_SEEDS`, then writes JSON to the path
in `RESEARCH_OS_POWER_OUTPUT`. The result must record the
simulation/rejection counts, achieved power, effect size, alpha, random seeds,
decision rule, data-generating process and the script SHA-256. The control plane
checks that `achieved_power = rejection_count / simulation_count`, cross-checks
the command values and hashes both files. Example result:

```json
{
  "schema_version": "1.0",
  "simulation_count": 5000,
  "rejection_count": 4200,
  "achieved_power": 0.84,
  "effect_size": 0.02,
  "alpha": 0.05,
  "random_seeds": [104729],
  "decision_rule": "Corrected lower confidence bound exceeds zero",
  "data_generating_process": "Cluster bootstrap over machines under the prespecified 0.02 effect",
  "generated_by_script_sha256": "<64-character SHA-256 of the simulation script>"
}
```

Then bind it with:

```bash
python3 scripts/research_quality.py simulation-power \
  --project my-phd --paper P01 \
  --effect-size 0.02 \
  --effect-size-basis 'Minimum practical difference defined before results' \
  --alpha 0.05 --power 0.80 \
  --simulation-count 5000 --achieved-power 0.84 \
  --script papers/P01/experiments/power_simulation.py \
  --evidence papers/P01/experiments/power_simulation-results.json \
  --method-note 'Cluster bootstrap over machines; success is a corrected lower CI bound above the locked 0.02 margin.'
```

The control plane executes the script twice in separate clean temporary
directories using Python isolated mode and a sanitized environment. Both
canonical JSON outputs must exactly reproduce the supplied evidence. The report
records exit codes and output/stdout/stderr hashes and is invalidated if its
contract, design, script or evidence changes.

## G3: plan reproduction before approval

Every paper-level design must assign approved run IDs to:

- a domain-standard baseline;
- a strong recent baseline;
- the original confirmatory execution;
- a disjoint clean-room reproduction in a digest-pinned, network-disabled
  container.

Every experiment-plan run declares an `isolation` object. Ordinary runs may use
`{"kind":"host"}`. A linked worktree uses `{"kind":"git_worktree"}` but is
only a separate checkout—not a clean-room executor. A clean-room run uses
Docker or Podman and a digest-pinned image. Container runs use
no network, a read-only root filesystem, a private temporary filesystem and
`no-new-privileges`; project outputs remain on the explicit workspace mount.

It must also predeclare the second-operator process, environment capture and
numeric metric tolerances. This must happen at G3 because adding reproduction
runs after G3 approval would alter the approved plan.

After all six papers have valid data reports, named confirmations and power
reports, click **全部检查后冻结预注册**.
CLI equivalent:

```bash
python3 scripts/research_quality.py freeze \
  --project my-phd --all --actor 'Your Name'

python3 scripts/research_quality.py validate \
  --project my-phd --stage g3
```

The freeze refuses to run after any experiment attempt exists. It hashes the
dataset manifest, relevant data reports, paper contract, all designs, global
plan, budget and power analysis. Changing any one requires an explicit revised
protocol and a new human review before execution.

## G4: baseline and clean-room reproduction

Run every G3-approved experiment through `scripts/experiment_runner.py`. The
executor rejects any overlap between declared inputs and outputs, mounts each
declared input read-only for container runs, and re-hashes every input after the
process exits; a missing or changed input makes the attempt fail. Recognized
script, configuration and data-file command arguments must be listed as
hash-declared inputs (or approved outputs). At the start
of a G4 model cycle, the control plane creates the protected
`reports/runtime-evidence-catalog.json` from successful registry entries and
current output hashes. Codex uses those deterministic facts to write:

- `papers/Pxx/baseline-reproduction.json`;
- `papers/Pxx/clean-room-reproduction.json`.

The gate independently recalculates absolute tolerances, requires every run ID,
baseline source and tolerance to match the frozen G3 design, binds every claim
to exact successful attempt IDs and all current outputs of those attempts,
requires original/reproduction run IDs and executor-issued isolation instance
IDs to be disjoint, verifies container properties, and recomputes
environment digests without using run names as fake environment differences.
Different directory strings without an execution-boundary receipt no longer
count as clean-room reproduction. For a group of exact attempts, obtain the
digest with:

```bash
python3 scripts/research_quality.py environment-digest \
  --project my-phd \
  --attempt p01-original-seed-1-attempt-001 \
  --attempt p01-original-seed-2-attempt-001
```

After Codex produces both reports for a paper, use the G4 **人工确认复现证据**
button. It reruns every deterministic check before creating the protected,
named and hash-bound `reproduction-confirmation.json`. The model cannot create
or edit that file. CLI equivalent:

```bash
python3 scripts/research_quality.py confirm-reproduction \
  --project my-phd --paper P01 --actor 'Your Name'
```

A failed reproduction remains a result; do not increase a tolerance after
seeing it. Revise or narrow the claim and preserve the negative outcome.

## What remains human

The program can reject missing, stale, internally inconsistent or numerically
false evidence. It cannot establish that the chosen construct is meaningful,
that every adjacent literature was found, that a second operator was genuinely
independent, or that a study is doctoral-level and publishable. Those judgments
remain explicit G1–G5 human approvals, informed by domain experts and the target
journal's current requirements.
