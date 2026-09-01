# Stage contracts

## Intake — G0

Required:

- `intake/constraints.json` with status `ready_for_review`;
- target application routes and time horizon;
- available skills, time, budget, compute, data and equipment;
- excluded domains and ethical/legal boundaries;
- ranking weights for novelty, doctoral depth, feasibility, jobs, positions and background fit.

Do not begin broad topic scoring while critical constraints are unknown.

## Topic intelligence — G1

Required:

- `evidence/search-log.jsonl` with each line conforming to `schemas/search-record.schema.json`; every claimed database, query family and closest-work inclusion must be traceable to a logged search;
- `program/topic-shortlist.json` with at least three serious candidates and explicit rejection reasons;
- `program/core-thesis.json` for doctoral proposition A;
- `program/extension-thesis.json` for separately doctoral-level extension B;
- `program/originality-audit.json` conforming to `schemas/originality-audit.schema.json`, including at least five closest primary works, three adjacent fields, three query families, counterevidence, residual novelty risk, a doctoral case and a reliability strategy;
- `program/topic-decision.md` with novelty, contribution, feasibility, competition, PhD-position supply and job-market evidence.

Stress-test novelty against adjacent literatures, not only exact keywords. Distinguish “not found” from “novel.”

## Paper architecture — G2

Required:

- `program/paper-map.json` conforming to `schemas/paper-map.schema.json`, including every pairwise paper comparison, independently sufficient primary evidence, standalone value and a justification for any shared outcome;
- six default paper contracts under `papers/P01`–`papers/P06`;
- dependency graph, shared assets, independent contribution, falsification condition and fallback venue for each paper;
- thesis synthesis showing why the collection is more than six unrelated papers.

Avoid salami slicing. Each paper must answer a distinct research question and remain scientifically coherent.

## Experiment design — G3

Required:

- `data/datasets.jsonl` with licenses and provenance;
- `experiments/plan.json` conforming to `schemas/experiment-plan.schema.json`;
- one or more JSON design files under `papers/Pxx/experiments/` for every configured paper, each conforming to `schemas/paper-experiment-design.schema.json`, with every global plan run assigned to exactly one design;
- `experiments/budget.json` with `status: ready_for_review` and `hard_ceiling_usd`;
- hypotheses; traceable simple, domain-standard and strong-recent baselines with source, version, license and comparable tuning budgets; ablations; splits; primary/secondary metrics; estimands; practical-significance thresholds; effect sizes; confidence intervals; multiplicity handling; power/precision rationale; at least three seeds for stochastic designs; robustness, negative controls and stopping rules;
- leakage, privacy, bias and external-validity assessment.

Freeze the confirmatory plan before final runs. Label later exploration as exploratory.

## Experiment execution — G4

Required:

- `experiments/registry.jsonl` including failed runs;
- immutable configs, code commit identifiers, environment lock or image digest and random seeds;
- `claims/claim-evidence.csv`;
- `reports/reproducibility.md`;
- statistical audit and sensitivity analysis.

Do not write a favorable conclusion before the claim matrix and negative results are visible.

## Writing and review — G5

Required:

- manuscript source, figures, tables, supplement and data/code availability statements;
- citation audit with zero unresolved fabricated/unverified references;
- two simulated review rounds and itemized response matrices;
- official venue manifest and imported template inventory;
- passing venue compliance report and successful compile/render when tooling permits;
- author contributions, conflicts, funding, ethics and AI-use disclosures;
- current JCR/venue-policy re-verification;
- current output-provenance hashes showing no packaged manuscript, table, figure, supplement, disclosure, response or cover-letter file was persistently written by Claude/Anthropic;
- figures rendered by deterministic local code from recorded data, with plotting code/configuration retained.
- all manuscript-bound text—including title, abstract, body, captions, tables, supplement, responses and cover material—written in English, with `scripts/manuscript_language.py` passing on the final manuscript source.

Repeat G5 for `state.active_paper`. A paper-level approval moves to the next configured paper; only the last paper can move the project to `submission-ready`. After a paper is marked `submission_ready`, `scripts/submission_package.py` may create a deterministic local ZIP, manifest and manual checklist for that paper. The human must inspect every final PDF/DOCX, choose the portal upload slots and submit. Agents do not log into portals, upload or submit.
