# Complete CCFA family integration

This project adapts all 17 skills from
`mikubaka88/CCFA-Skills` at commit
`f157d7ed2777b655809471873b32b9632e784cfa`. The upstream MIT license is retained.
The source inventory is `integrations/ccfa-skills.lock.json`; task/stage/producer
routing is `integrations/ccfa-skills.routes.json`. Pinned upstream source remains
under `third_party/ccfa-skills/`; native project entry points live under
`skills/ccf-*/SKILL.md` and install into this checkout's `.agents/skills/`.

All 17 skills are available; task selection loads the relevant specialist rather
than paying for 17 separate calls. Humanization is always the first preflight,
then Common. Existing approved models retain their planner/writer/critic roles,
reasoning effort, transport groups, cache, identity and cumulative charge
controls. This integration does not change those assignments.

The native orchestrator remains the only execution/state authority. Claude
plans and audits read-only; the existing authorized non-Claude writer produces
persistent scientific wording. A second `ccfa.yaml`, runner, budget, stage state
or approval system is not created. Original upstream examples and helper
commands are reference material, not new authority to execute a paid call,
change a model, acquire data or submit a paper.

## The 17 individual routes

In the table, `U/` means the complete pinned `third_party/ccfa-skills/` tree,
`S` means the existing authorized scientific writer, `P/C` means the existing
read-only planner/independent critic, and `D` means the cloud deterministic
control plane. Examples are natural task requests consumed by those roles,
not commands that bypass stage, rights or budget requirements. All tasks inherit
Humanization and Common. The exact current route registry remains authoritative.

| Skill | Owner, stage and task | Native producers and retained output | Complete upstream mode references and example invocation |
|---|---|---|---|
| `ccf-humanization` | S edits; P/C inspect; D locates signals. Applies at every stage, detailed prose/experiment modes only when relevant. | `ccfa_humanization.py`, `academic_style.py`; existing H01–H26/AD01–AD08 plus CFH01–CFH38 contextual coverage, protected-fact checks, `papers/Pxx/reviews/ccfa-humanization.json` and existing style audit. | `U/ccf-humanization/SKILL.md`, both `references/humanization-policy.md` and `experiment-discipline.md`, exact pinned prose checker. “Use ccf-humanization to revise the P01 Discussion around the supported contribution; preserve the actual uncertainty and all material results.” |
| `ccf-common` | All roles, G0–G5. Resolve outcome, scope, prerequisite, integrating owner and handoff. | `cloud_job.py`, `cloud_checkpoint.py`; optional `ccfa_science` continuity support uses canonical artifacts, current hashes, justified route and exact next action. No compulsory extra report for a short task. | All `U/ccf-common/references/`, especially routing, task/handoff modes, artifact contracts, privacy/evidence, continuity and preferences. “Use ccf-common to reconcile the current goal and changed inputs before continuing this handoff.” |
| `ccf-pipeline-orchestrator` | D coordinates; P proposes/S implements. All stages; an actual research loop only within its existing authorized scope. | `cloud_continuation.py`, `ccfa_science.py`; native checkpoint/gate continuation and source-bound continuity report, provisional versus measured candidates retained. | `U/ccf-pipeline-orchestrator/SKILL.md`, `references/autonomous-research.md`, complete `references/workflow-planning/`. “Resume P01 at the first unresolved prerequisite, preserving valid work and remaining budget.” |
| `ccf-project-scaffolder` | D/S, intake G0 and architecture G2. Initialize only missing compatible structure. | `researchctl.py`; existing project and P01–P06 contracts/templates/state. Unknown research content stays unassigned; no fabricated title/claims and no new competing state file. | `U/ccf-project-scaffolder/SKILL.md`, its `assets/`, Common artifact/schema rules, relevant venue/template references. “Use ccf-project-scaffolder to prepare the six-paper structure and preserve existing manuscripts.” |
| `ccf-idea-reviewer` | P/C inspect concept; S records decisions. Topic intelligence G1. Concept-only assessment remains separate from experiment/submission readiness. | `research_candidates.py`, `pre_submission_review.py`; source-bound existing hypothesis/originality records, anchored conceptual findings and smallest repairs. No invented prior art or acceptance probability. | `U/ccf-idea-reviewer/SKILL.md`, strict-idea-review, rubric, calibration, expert-panel and source-notes references. “Assess this mechanism against the nearest primary works; keep missing experiments separate from conceptual merit.” |
| `ccf-idea-optimizer` | P proposes/S authors, G1–G2. Develop the problem, mechanism, premise, transfer conditions and discriminating predictions. | `ccfa_science.py` lineage, `literature_reasoning.py`; existing hypotheses plus parent/operator candidate lineage, necessity argument and exact evidence. A changed mechanism receives a new child ID. | `U/ccf-idea-optimizer/SKILL.md`, literature-grounded-evolution, frontier-ideation, problem-method-blueprint, research-taste, idea-intake and venue adapters. “Develop distinct refine/transfer/invert candidates from these source observations; state the prediction separating each from its rival.” |
| `ccf-literature-searcher` | D retrieves; S synthesizes/P/C challenge. G1 and explicit prerequisite retrieval in other stages. | `literature_evidence.py`, `literaturectl.py`; actual provider receipts/search log, versioned sources, original text/figures, located reading cards and experiment comparison dossier. Metadata/abstract scoring remains discovery evidence. | `U/ccf-literature-searcher/SKILL.md`, `references/search-and-scoring.md`, report-template and Common privacy rules. “Retrieve closest and adjacent work for this mechanism and keep real filters, rejected sources and exact protocol anchors.” |
| `ccf-literature-monitor` | D incremental discovery; S/P/C interpret novelty implications. G1 or explicit later watch task. | `literature_intelligence.py`, `ccfa_science.py` novelty watch; dated executed retrieval, stable source versions, exact novelty claim IDs, overlap axes/signals and changes since the prior scan. | `U/ccf-literature-monitor/SKILL.md`, monitoring-workflow and report-template. “For this exact time window, identify which new paper changes C1's mechanism or comparison claim; distinguish unchanged results.” |
| `ccf-experiment-designer` | P/S design, C challenge, D executes only after existing G3. G3–G4. | `experiment_runner.py`, `experiment_evidence.py`, `literature_reasoning.py`; claim-to-test design, matched baselines/compute, complete configuration, preregistered outcomes, actual run receipts. Meta/theory and reviewer additions use their existing dedicated routes. | `U/ccf-experiment-designer/SKILL.md`, evidence-design/result-templates, Humanization experiment discipline. “Design a matched-budget main comparison and the smallest ablation separating the mechanism from the strongest rival; do not fill missing outcomes.” |
| `ccf-integrity-auditor` | C/S inspect, D verifies; G3–G5. Claim, numeric, citation or full modes. | `manuscript_audit.py`, `citation_audit.py`, `ref_verify_adapter.py`; existing claim-evidence/numeric/citation-context audits with exact locations, unsupported items and scope limits. | `U/ccf-integrity-auditor/SKILL.md`, shared privacy/evidence and review-output rules. “Check P01's abstract, table and figure values against the recorded results and verify each cited passage supports its actual use.” |
| `ccf-paper-reviewer` | Independent P/C diagnose, S remediates. G5 or scoped review request. | `ccfa_science.py` internal review, `pre_submission_review.py`, `api_orchestrator.py`; fresh existing independent audits, fixed finding IDs, frozen historical comparison and separate current categorical readiness. | `U/ccf-paper-reviewer/SKILL.md`, review-workflow, universal rubric, version-comparison, fixed-output-format, calibration and venue review styles. “Compare historical/current P01 under the frozen criteria; retain inherited issues and identify current regressions from exact evidence.” |
| `ccf-paper-writer` | S owns persistent English scientific prose; P/C remain independent. G2/G5. | `api_orchestrator.py`, `incremental_writing.py`; canonical manuscript, argument/claim contracts, verified citations, source format and revision ledger. Drafting, local polish, compression and submission fitting stay distinct. | `U/ccf-paper-writer/SKILL.md`; complete section/storyline/materials/citation/prose/compression/length/style guidance plus matched `references/venue-guides/` and `references/exemplars/`. “Draft this Results section from the actual run outputs, preserve missing values and explain the decisive evidence.” |
| `ccf-rebuttal-writer` | S authors response/edits; P/C inspect; D retains actual external rounds. G5 after real comments. | `reviewer_rounds.py`, `revision_trace.py`, `supplemental_experiments.py`; original review receipts, response matrix/letter, itemized commitments, changed manuscript evidence and independently executed authorized additions. | `U/ccf-rebuttal-writer/SKILL.md`, response-strategy/checklists, revision-ledger, tex-templates and `assets/templates/`. “Map these real comments to verified edits and unresolved evidence; never describe a proposed experiment as completed.” |
| `ccf-visual-composer` | S defines scientific/data/topology spec, D renders and checks; P/C inspect semantics. G4–G5. | `publication_figures.py`, native venue/render adapters; recorded-data figures and editable source, numeric/topology fidelity, build/render/output QA receipts and final-size inspection. | `U/ccf-visual-composer/SKILL.md`; complete visual-contract, architecture/layout/style/plotting/accessibility/editable-PPTX/render-QA references, recipes and assets. “Render these real results with shared scales, units and uncertainty; preserve IDs and inspect text/clipping at final publication size.” |
| `ccf-submission-checker` | D/S check, C independently audits; final human owns submission. G5. | `submission_package.py`, `journal_screening.py` and existing venue-policy/compliance tools; current official journal/category/year evidence, build/anonymity/metadata checks and manual submission package. | `U/ccf-submission-checker/SKILL.md`, exact venue guide/template and shared source registry. “Check this current journal's actual rules and the current built package; distinguish missing checks from passing checks and do not upload.” |
| `ccf-paper-to-exemplar` | S authors pattern interpretations, D binds full source; P/C inspect. G5 or explicit writing-reference preparation. | `ccfa_science.py` exemplar, `literature_workbench.py`; full-paper, original-page seven-family writing-move card, verified supplied-source scope, transfer conditions and do-not-copy boundaries. | `U/ccf-paper-to-exemplar/SKILL.md`, original `scripts/convert.py`, full writer exemplar/style references. “Distill this supplied full paper's problem–method–evidence structure for our matched study type; cite original locations and copy no wording or results.” |
| `ccf-skill-forger` | S/D maintain only the explicitly authorized project skill/tool surfaces; no scientific content ownership. Explicit maintenance trigger, no automatic research-stage activation. | `validate_repo.py`, `ccfa_runtime.py`; reviewed project-local adapters/registry/source lock and changed-case validation. No self-modifying production prompts, default models or global libraries. | `U/ccf-skill-forger/SKILL.md`, complete `references/design-checklist.md`, patterns/local-commands and shared trigger registry; ancillary maintenance resources remain pinned. “Check this adapter's trigger, dependency, source pin and actual producer; repair the scoped incompatibility and validate the changed cases.” |

CCF-A guides provide useful workflow/writing context, not journal eligibility.
The six-paper doctoral question, original-research requirement, current JCR
Q1/Q2 SCI/SCIE portfolio and identical scientific quality gates remain in force.
Concept-only idea review does not weaken G1's actual topic-selection gates;
results-pending drafting does not establish G5 readiness.

## Complete source and practical installation

The integration distinguishes three layers:

1. **Complete pinned upstream material.** Every upstream text/code file is
   retained and checked against its source identity and canonical LF hash.
   This includes all 17 SKILL entries, nested references, bilingual examples,
   original helpers, templates, venue guides, exemplar material and attribution.
   The complete tree/resource inventory also retains exact Git blob identity
   and size for ancillary assets.
2. **Native project adapters.** Each of the 17 entries maps to real existing
   producers and applicable native contracts. Cloud installation verifies these
   entries and installs the project discovery copies under `.agents/skills/`.
   It does not overwrite a changed adapter or install into the user's desktop
   profile. A fresh cloud checkout can discover them without global setup.
3. **Task-selected model guidance and real execution.** `model_contract` adds
   the mandatory full Humanization/Common preflights and applicable specialist
   workflow and complete applicable reference bodies to existing model requests,
   including ordinary API requests that have no file-reading tools. Selection is
   deterministic: the skill's ordinary rules, additional mode-specific rules
   (compression, version comparison, plotting, architecture, etc.), and any
   explicitly named pinned reference path. It does not load every venue guide,
   exemplar or maintenance document for every task. Original-source hashes are
   retained. Preparing or
   loading a packet makes no paid call; the normal authorized model cycle owns
   actual scientific work. Native validation/execution governs the result.

All original helpers are present as reviewed pinned code; that does not mean
each upstream command is automatically executed. Source inspection, current
dependency availability and native execution boundaries still apply. In
particular, upstream direct SDK/model commands, external uploads, automatic
submission and another project state do not replace the existing protected
control plane. Applicable workflows are fulfilled through native producers.

Ancillary non-text resources are retrieved only by an exact inventory path via
`ccfa_runtime.py resource --resource PATH`. The cloud downloader verifies size
and the original Git blob before caching under the fixed
`.runtime/ccfa/resources/<pinned-commit>/` tree. Resource access grants no data,
publisher-template or redistribution rights. The original upstream installer
acceptance uses the official pinned skill installer in isolated cloud storage;
native adapter installation is separately checked. Installation and research
validation are separate claims.

## Preparing and consuming a skill task

Ordinary stage tasks select relevant skills through the fixed registry and
include their guidance in the existing planner/writer/critic request.

Ordinary and explicitly prepared tasks now use the same full-reference loader.
An active task selects its actual specialists instead of adding a second set of
all stage-default skills. Each complete entry/reference body appears only once,
deduplicated by its pinned content hash across defaults, mode rules and explicit
references. All three Humanization policy bodies remain mandatory in every
research-role request. A nested venue/exemplar rule is reachable by its exact
`ccf-.../references/...` path in the task text or `references`; no model call is
added to choose references. `mode: full` loads the selected skill's direct rules,
while nested venue guides/cards remain an explicit source choice. Native role,
approval and scientific evidence contracts still take precedence over upstream
example commands, generic numeric scores and templates.

Explicit work uses one controlled operation request in `program/`, for example:

```json
{
  "action": "ccfa_task",
  "request": {
    "schema_version": "1.0",
    "id": "P01-mechanism-iteration",
    "skill": "ccf-idea-optimizer",
    "task": "Develop a source-grounded mechanism and a rival-discriminating prediction within the current doctoral question.",
    "stage": "topic-intelligence",
    "paper_id": "P01",
    "inputs": [],
    "references": [
      "ccf-idea-optimizer/references/literature-grounded-evolution.md",
      "ccf-idea-optimizer/references/frontier-ideation.md"
    ]
  }
}
```

The example contains no research source. For actual use, `inputs` must contain
the relevant current `{path,sha256}` source bindings; a source-free task must
not claim researched novelty or observed outcomes. The stage must match current
native state, P01–P06 mapping remains explicit, and combined text inputs are
bounded to 2 MB. Native PDF extraction supplies bounded text rather than raw
binary input. Private drafts, API keys, credentials and raw datasets are not
uploaded as search queries or skill packets.

On the authorized cloud runner, either entry point accepts this bounded request:

```bash
python3 scripts/ccfa_runtime.py request --project PROJECT --request-file program/ccfa-request.json
python3 scripts/literaturectl.py request --project PROJECT --request-file program/ccfa-request.json
```

The existing owner cloud-job action `literature` can execute that same request
with `allow_paid:false`; the normal writer can also enqueue the allowed action
in `program/cloud-operations.json`. A nonpaid request prepares an immutable
packet under `reports/ccfa-tasks/<id>/` and activates its source-bound pointer
for the next authorized model cycle. It is not scientific execution, approval
or additional spend authorization. The existing model runtime consumes current
packets, original guidance and source bindings in the selected role; stale
inputs/implementation/scope must be refreshed. A completed packet does not mean
the associated research task is complete.

The G1 novelty gate retains at least three closest works per claim and five
distinct closest works overall. Its project-bound saturation check now replays
actual successful retrieval receipts and raw/normalized hashes. Backward and
forward chaining require the corresponding executed `citation_graph` direction,
DOI request source and matching original/normalized edges; an ordinary keyword
search cannot stand in for either. Consecutive no-material-new-work rounds need
different actual executions: renaming a round or aliasing a prior receipt does
not create another search. These are evidence and coverage minima, not a proof
of exhaustive novelty or scientific completeness; named screening and human
review remain required.

## Five source-bound extension operations

`ccfa_science` adds practical native report builders where the earlier workflow
needed more than source instructions. Complete schemas/examples and constraints
are in [CCFA-SCIENCE.md](CCFA-SCIENCE.md).

| Native operation | Actual checked behavior | Persisted artifact and scientific boundary |
|---|---|---|
| `continuity` | Versioned objective/acceptance; current authoritative inputs; justified route/recovery; proposed/executed/verified artifact status; changed evidence invalidates verification. | Fixed source-bound report with immutable history. It indexes canonical state and never replaces it or grants a human approval. |
| `lineage` | Explicit parents/operator/mechanism/necessity/discriminator; rejected/refuted branches retained; changed mechanism gets a child ID. Measured status needs the actual native registered run, plan/config/output hashes. | Candidates and reasoned provisional selection. No invented best result across incomparable protocols and no novelty proof from labels. |
| `novelty_watch` | Actual dated search receipts/raw/normalized hashes; exact claim IDs and both-sided anchors; overlap axes and delta history. | Claim-specific RELAX/RESEARCH/FOLLOW-UP proposals. A scan is not exhaustive novelty clearance or a recurring scheduler. |
| `exemplar` | Native confirmed supplied-full-source scope; original source/reader locations; seven writing-move families with transfer conditions. | A reusable full-paper structure card with attribution and do-not-copy limits. No transferred scientific claims, global default or human-reading certification. |
| `internal_review` | Frozen historical/readiness criteria; stable issue IDs and provenance; both manuscript versions anchored; reopened changed evidence. | Categorical relative progress and separate current readiness. No acceptance probability or substitute external reviewer round. |

The operation shape is:

```json
{
  "action": "ccfa_science",
  "operation": "lineage",
  "request": {
    "schema_version": "1.0",
    "id": "P01-mechanisms",
    "source": "program/ccfa-inputs/P01-mechanisms.json",
    "expected_source_sha256": "REPLACE_WITH_CURRENT_INPUT_SHA256",
    "expected_previous_sha256": null
  }
}
```

This example documents the envelope, not executable real evidence. The existing
authorized writer must supply concrete schema-valid source-bound content and
its actual hash. Updates require the exact previous report hash. A report
replays input and implementation provenance before reuse; no operation calls a
model, starts an experiment or crosses a gate.

## Full Humanization coverage

`ccfa_humanization.prompt_contract` loads the complete pinned SKILL, the entire
humanization policy including bilingual repairs, and the entire experiment
discipline. It does not replace them with a short paraphrase. A stable local
coverage map CFH01–CFH38 makes the original policy inspectable alongside existing
Humanizer H01–H26 and anti-defensive AD01–AD08 coverage. The 38 identifiers are
our integration map, not a claimed upstream detector or quality score.

Coverage includes sentence payload and paragraph logic, fact/uncertainty
calibration, empty self-defense, repetition, section purpose, openings,
terminology, pronoun/antecedent precision, mechanical ordering, forced triads,
execution-log prose, punctuation and rhythm, repetitive contrasts, vague/hyped
terms, supported findings, source-format fidelity, internal gate-label leakage,
material negative information, warning-only edits, and final argument/negation/
comparison review. Experiment coverage includes full-method identity, legitimate
small studies, controlled ablations, distinct critical-path smoke tests, and
actual experiment-to-paper values/configuration. It preserves the supported
story while retaining material adverse evidence, required disclosure and fair
comparison conditions.

The exact pinned upstream nonmutating prose checker is reused after source
verification; native contextual checks complement it. Signals point to lines
for review rather than blindly rewriting text. The existing writer handles
authorized semantic edits, retaining numbers, units, citations, uncertainty,
negation, actor and comparison direction. Correct technical terms and justified
parallel structure stay intact. No randomized reordering or synonym spinning is
used to conceal assistance or corrupt scientific meaning.

At G5 the existing academic-style audit includes complete CCFA coverage and
checks it against the current manuscript snapshot. An independent protected
editorial review must give contextual dispositions with locations/reasons for
applicable items; changed manuscripts make saved findings stale. The standalone
nonpaid `ccfa_humanization` operation writes only internal reports:

```json
{"action": "ccfa_humanization", "paper_id": "P01"}
```

No-prose retrieval/maintenance/plotting tasks apply Humanization's baseline
without fabricating a manuscript-edit pass. Required source hashes remain in
internal control records even though manuscript prose avoids process labels.
A clean heuristic scan does not prove human authorship, statistical-watermark
absence, semantic equivalence or scientific quality. Existing hygiene,
citation/numeric integrity, mandatory disclosures and independent/human review
remain required.

## Verification and completion boundaries

The cloud checks cover complete upstream/native installation, source locks,
route/producer existence, all 17 task selections, complete source references,
role/prompt integration, safe explicit task packets, Humanization examples and
38-item contextual coverage, five source-bound builders and stale/tampered/
unauthorized inputs. The official original-skill installation is checked
separately from native discovery. Tests use isolated synthetic research inputs
and never provide production gate approvals or real scientific outcomes.

This document defines the implementation and validation contract. It does not
claim any cloud run has passed; completion evidence must name the actual tested
commit, current source tree and successful run. Source availability and working
controls establish engineering behavior, not topic novelty, full-text semantic
correctness, experimental validity, real-model quality or JCR Q1 acceptance.
Real research still requires materials, authorized cloud execution, located
evidence, independent scientific audits and human G0–G5 decisions.
# Active task lifecycle

Preparing `ccfa_task` activates an immutable, hash-bound task for the current native stage and optional active paper. Frozen source changes require a fresh packet. Declare manuscript files that this task is meant to edit in `request.editable_inputs`, as a subset of its bound inputs under `papers/<paper_id>/manuscript/`; only current tracked non-Claude writer/remediator edits may replace those bytes in subsequent existing role contexts. Internal reviews are rejected as task inputs. Independent critics receive neutral task identity and current scientific sources, with author instructions/preferred verdicts withheld.

To stop applying a task, submit `{"action":"ccfa_task_clear","expected_active_sha256":"<current reports/ccfa-tasks/active.json SHA-256>"}` through the same owner literature request route. This deactivates the task and preserves its packet; it does not assert completion or approve a gate. Replace or deactivate an old paper's task before the next paper uses that stage. Full source inputs are never silently truncated. Source content containing configured secrets is rejected before model emission.

