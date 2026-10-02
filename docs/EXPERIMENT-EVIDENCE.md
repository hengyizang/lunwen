# Experiment design, execution and scientific evidence

These tools aim to make demanding doctoral and Q1 research auditable. They do not certify scientific merit or guarantee acceptance. A successfully executed program does not by itself support a paper's claim.

## Design before execution

Keep the existing paper contract and experiment designs. Add one `papers/Pxx/experiment-evidence-plan.json` using [its schema](../schemas/experiment-evidence-plan.schema.json). This plan sits outside `experiments/*.json`, which contains scientific design documents.

For each core claim, explain the proposed mechanism, alternative explanations, an outcome that would refute it and its population boundary. Register all domain-standard, strong recent and simple baselines with fair data access, tuning and compute budgets. Bind every baseline, ablation, negative control and robustness item to real run IDs and declared output files for every design seed. Each claim must include all baselines for the design supporting it. Runs cannot be relabeled as different comparator conditions or datasets.

Each comparison records the hypothesis, metric, dataset, independent analysis unit, population scope, assumptions, practical threshold, multiplicity family and sample-size rationale. Repeated rows from one unit and repeated random seeds do not increase the count of independent units. Power-analysis alpha must account for the family size; planned units cannot be less than the calculated requirement. A simulation-based calculation requires the existing reproducible simulation evidence and human assessment of its sample-size assumptions. The numeric floor of three units is only an implementation precondition, never an adequacy recommendation.

External validity must be either tested through actual registered comparisons or explicitly scope limited. For held-out organizations, future time periods or a separate dataset, register separate data and runs. Document leakage controls, test-set isolation, inclusion/exclusion rules, missingness, grouping, and randomization/blinding where relevant. Do not equate predictive accuracy with mechanism or causality.

## Technical pilot, then full execution

Use `depends_on` in the execution plan. Dependencies must name earlier runs of the same paper. Every evidence arm needs a pilot ancestor; use appropriate pilots for different datasets/environments. Freeze the pilot code, expected outputs and technical success criteria before G3. Encode criteria as assertions that fail the pilot when unmet. A zero exit status only verifies those encoded assertions; human review must assess their adequacy.

The executor checks the successful pilot receipt, current output hashes, approved plan and frozen protocol before launching a dependent process. Failed or repeated pilot attempts require inspection. Protocol or code changes require an explicit reviewed amendment; they cannot be silently refrozen after results exist. Existing controls preserve failed/negative runs and block unapproved spending. G0–G5 human approval is unchanged.

## Statistical evidence produced from executed data

After every planned run finishes, the cloud control plane writes `papers/Pxx/experiment-evidence.json`. Each source must have exactly one retained attempt, a matching executor receipt and unchanged registered output. A failed comparison, missing seed, altered file or selected retry prevents a complete report. No model may write this report.

The built-in `paired_t` mode is for suitable paired independent units. Each CSV has a unit-ID and numeric-value column. It averages repeated rows within each unit and then averages paired differences across the registered seeds. Paired unit IDs must match within and across seeds; unmatched, nonfinite or missing values are rejected instead of silently dropped. The independent sample count is the number of unique units. Seed-level effects and their descriptive standard deviation are also reported. Inference is conditional on the registered seeds and does not by itself quantify variation over future training runs; hierarchical or clustered inference needs an appropriate custom analysis.

Superiority tests improvement against the prespecified practical threshold, not merely zero. Equivalence uses two one-sided tests against a positive prespecified margin; nonsignificance alone cannot establish equivalence. Family p-values use Holm correction and intervals use conservative Bonferroni simultaneous coverage. A passing numeric decision requires both the corrected p-value and interval rule. Missing comparisons remain in the family. Exploratory results are labeled and cannot establish confirmation. Zero observed unit variance is blocked for method inspection.

For other valid models, use `registered_result`. Register an analysis run that depends on every arm and writes an expected JSON output. It can read immutable dependency outputs from the read-only project mount; its code and original inputs remain hash locked. The result must include:

- `schema_version=1.0`, `comparison_id`, registered `method_id`;
- the exact `decision_rule`, `direction`, `minimum_effect`, `aggregation`, `analysis_unit`;
- `independent_units` matching the complete unit coverage, and `source_hashes` mapping every arm's CSV path to its SHA-256;
- finite `estimate`, `ci_low`, `ci_high`, `p_value`, and `ci_confidence` sufficient for the registered family.

This route verifies execution, sources and metadata, not the correctness of the custom estimator. Its report explicitly says it was not statistically recomputed. The paired CSV unit contract still applies; unpaired, hierarchical or unusual estimands may need a reviewed adapter before execution. Do not coerce an unsuitable study into a paired t-test to make a gate pass.

## Conclusions and review

Include `comparison_ids` in the claim-evidence CSV, listing every comparison assigned to the claim, plus all source `analysis_ids`. An unrelated or other paper's successful run cannot support it. `supported` requires every linked confirmatory comparison to meet its threshold. `partially_supported` requires at least one passing primary comparison and an honest uncertainty statement. Retain adverse and inconclusive comparisons. A complete numerical report may contain wholly negative findings.

Scientific review must still assess the design's identification strategy, baseline implementation, substantive effect, residual confounding, model assumptions, error cases, external validity, reproduction and interpretation. Machine-readable completeness cannot decide whether the contribution is original, important or worthy of a doctorate.

## Method references

Checked 2026-10-02. These sources inform applicable reporting practices, not a universal Q1 checklist:

- [NeurIPS paper checklist](https://neurips.cc/public/guides/PaperChecklist): claim/evidence alignment, reproducibility, uncertainty, compute and limitations.
- [Nature reporting summary](https://www.nature.com/documents/nr-reporting-summary-flat.pdf): sample size, exclusions, randomization and blinding where relevant.
- [SciPy one-sample t-test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ttest_1samp.html): independent observations, test alternatives and confidence intervals.
- [statsmodels multiple-testing methods](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html): Holm family correction.

The separate cloud acceptance uses synthetic data, 25 container runs and a failed-pilot case. Passing it verifies software behavior only. No real model calls, project approvals or scientific completion are produced.
