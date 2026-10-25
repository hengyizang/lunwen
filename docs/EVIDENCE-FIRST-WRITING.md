# Evidence-first argument and contribution review

These controls strengthen existing records and existing author/critic cycles.
They do not add a model, paid call, result authority, issue ledger or scientific
approval. A located quote, complete form or executable code is not proof that an
inference is scientifically valid. Final manuscripts remain English.

## Paragraph purpose and reasoning

In `program/research-increments.json`, each arguments paragraph retains its exact
source units/hashes, function, claim IDs, evidence and inference boundary. Add:

- `takeaway`: one main point a reader should retain, not a compulsory one-sentence
  paragraph or stock opening.
- `warrant`: why the actual evidence or premises support that point. A theory may
  explain a derivation; a question paragraph may explain the motivation. Do not
  invent numbers or force every paragraph into three sentences.
- `reasoning_status`: `not_assessed`, `ready_for_scientific_review`,
  `needs_material`, or `not_applicable` (only transition/non_argument functions).
- `material_needs`: bounded items `{id,material_type,description,completion_condition,claim_ids}`.
  Types: data/literature/analysis/proof/explanation/scope/other. They always remain
  pending preparation, never a model-assigned scientific verification.

Legacy purpose remains readable as a takeaway fallback but is explicitly
unassessed. All conceptual fields enter the existing before-writer freeze; a
changed warrant cannot be laundered by refreshing text hashes. G5 requires
current argument preparation, full source coverage and the original independent
scientific review. Readiness does not establish semantic claim support.

## Concrete contribution and expectation check

Keep contributions in each existing `paper-facts.json` claim_alignment row as
`contribution_detail`; see `schemas/contribution-reporting.schema.json`.
It records subject, finding, conditions and the scientific question answered.
Its kind must agree with the actual research identity's `design_family`.

Each fact role has `{role,fact_id,value}` and uses a current fact already linked
to that claim. The value must occur in its exact source excerpt. Required roles:

| Design | Required roles |
|---|---|
| Empirical/computational | finding, magnitude, uncertainty, comparison |
| Meta analysis | the above plus heterogeneity and bias |
| Theoretical | proposition, assumptions, proof |
| Qualitative | finding, scope |

`execution` binds `{run_id,path,sha256}` to exact successful outputs using the
existing approved-plan executor seals. Findings, magnitudes, intervals and proof
checks cannot use a model-authored report as their result authority. Theoretical
propositions and assumptions instead bind frozen proof inputs; no fabricated
effect sizes are required.

`expectation_review` contains `planned_source:{path,sha256}`, `planned_quote`,
`observed_status`, `decision`, `reason`, `scope`. The source must be an actual
frozen preregistration input; its quote must exist. Observed status must equal
the current claim's supported/partially_supported/not_supported/contradicted/
inconclusive status. Choose retain/narrow/reframe/unsupported with a reason.
Unsupported or inconclusive outcomes cannot retain the original success story.
Reframing does not change the registered hypothesis, delete adverse outcomes,
authorize a new experiment or leave the approved doctoral question.

The existing manuscript audit checks current claim expressions in title,
abstract, question, results and conclusion. It now carries these source-bound
contribution checks and reruns automatically after initial writing and remediation
in both API and CLI orchestrators. G5 and packaging require current reporting;
legacy missing detail is not a pass. An audit that is ready for scientific review
still requires actual scientific assessment of the inference and contribution.

## Closest-work comparison

Use the existing `program/research-extensions.json` comparisons with optional
`closest_work`, following `schemas/closest-work-comparison.schema.json`.
It binds the actual paper/claim/work IDs to the novelty matrix, originality audit
and registered literature item. Three axes are research_object/method/result.
Every reported statement has an exact own-source or original-paper line/page
anchor. Original-paper details require the correct full-text reading scope.

Keep unknown/not_reported/planned explicit. They are legitimate research states,
not proof of novelty or superiority. Final contribution coverage needs located
reported or genuinely inspected not_reported axes for every closest-work ID
declared on that claim. Unread unknowns stay preparation work. A descriptive
theory comparison does not need empirical dataset/metric fields.

Quantitative result comparisons bind actual dataset ID, manifest version, metric
and evaluation basis. Cross-condition numbers cannot establish superiority or
equivalence just because both values are available. Differences and missing
information remain visible to the independent review.

## Actionable findings in the existing issue ledger

Use `writing_action` on an existing research-extension review finding or CCFA
internal-review issue; do not create another competing list. The shared schema
is `schemas/writing-review-action.schema.json`.

The task records problem categories (including empty evaluation, missing evidence,
inference gap, unclear contribution comparison or unsupported generality), exact
current locations, paper/claim scope, required data/literature/analysis/proof/
protocol/manuscript edits, a concrete action and completion conditions. Missing
material is pending; supplied material awaits independent review. If writing is
sound, do not manufacture a finding merely to fill a checklist.

Stable issue/material IDs, scope, former task versions and change reasons remain
in the same issue. Deleting a task, dropping a required material or changing an
active issue to historical cannot erase pending work. A failed refresh retains
the last protected issue definition, so a second refresh cannot wash it away.
Model-declared resolved status never converts missing material into a pass.
Inherited structured issues cannot be downgraded to avoid a blocker. Deleting the
whole extensions input also retains protected issue history across failed refreshes;
projects that never created this optional record remain compatible.

## Quality and cost

The existing planner remains read-only; the scientific writer independently
authors persistent prose; the separate-family critic evaluates support and
reasoning. Reuse initial/final reviews. Deterministic tools verify bindings and
prepare compact deficits; do not add one model call per paragraph or another
whole-manuscript polishing loop. Recheck changed units and affected dependencies
while preserving necessary whole-argument context and every scientific gate.

The motivating execution study used 43 researchers and a Claude 3.5 Sonnet NLP
ideation agent: [Si et al., 2025](https://arxiv.org/html/2506.20803v1). It supports
evaluating executed outcomes rather than treating idea-stage ratings as achieved
research value. It does not establish the quality of our present model routes.
All local engineering fixtures are synthetic, with no scientific completion.
