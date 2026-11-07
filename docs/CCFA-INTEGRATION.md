# Complete CCFA family integration

This project adapts all 17 skills from
`mikubaka88/CCFA-Skills` at commit
`f157d7ed2777b655809471873b32b9632e784cfa`. The upstream MIT license is retained.
The source inventory is `integrations/ccfa-skills.lock.json`; task/stage/producer
routing is `integrations/ccfa-skills.routes.json`. Pinned upstream source remains
under `third_party/ccfa-skills/`; native project entry points live under
`skills/ccf-*/SKILL.md` and install into this checkout's `.agents/skills/`.

All 17 skills remain available through the [route registry](../integrations/ccfa-skills.routes.json), which is the single definition of task/stage triggers, native producers and outcomes. The authoritative instructions are `skills/ccf-*/SKILL.md`; `.agents/skills/` contains generated discovery pointers, not another maintained copy.

Ordinary model cycles receive compact native science/task rules and exact source identities. Topic authors select Idea Optimizer and critics select Idea Reviewer; manuscript authors select Paper Writer and critics select Paper Reviewer. Humanization/Common baselines apply throughout. Complete pinned entries and references are loaded for explicit skill/full-reference requests or exact task-selected references; ordinary requests are not labeled as having consumed absent full text. The selected source path and hash remain inspectable without a paid call.

The native controller retains state, existing model/role/effort assignments, cumulative costs, the current independent critique and final blind panel, source rights and experiment authority. Only G1 and each G2 topic require human decisions. Upstream examples cannot add a parallel runner/state, paid call, data permission or automatic submission. Editorial tables remain available as C observations; submission performs source-bound B preparation and the final panel without making full editorial dispositions another gate.

## Complete source and practical installation

The single `resources` inventory stores every original path, Git blob and size; vendored text/code rows additionally retain their canonical LF hash. The runtime derives its legacy `files` view from those rows. No source identity is removed or duplicated in a second list.

Native discovery entries are generated from `skills/` by both cloud installers. An exact old source copy can migrate; any local customization or symlink blocks replacement. Installation never writes a desktop/global skill profile. Preparing guidance makes no paid call and grants no research authority.

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

Explicit tasks reuse the same source-bound loader and select their own specialists. Full entries and selected reference bodies are deduplicated by content hash; nested venue/exemplar sources need an exact path or relevant task mode. The complete original remains retrievable. Native scientific and execution contracts govern any upstream example.

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

The final G1 novelty gate retains at least three closest works per claim and five
distinct closest works overall. Its project-bound saturation check now replays
actual successful retrieval receipts and raw/normalized hashes. Backward and
forward chaining require the corresponding executed `citation_graph` direction,
DOI request source and matching original/normalized edges; an ordinary keyword
search cannot stand in for either. Consecutive no-material-new-work rounds need
different actual executions: renaming a round or aliasing a prior receipt does
not create another search. These are evidence and coverage minima, not a proof
of exhaustive novelty or scientific completeness; recorded screening, independent
scientific audits and the G1 human topic decision remain required. Draft records
may remain exploring or reopened, retaining actual history, unresolved gaps,
affected claims and planned searches instead of fabricating saturation.

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

## Humanization

See [the Humanization integration](CCFA-HUMANIZATION.md) for the shared baseline, complete retrievable policies, CFH dispositions, protected facts and current reports. Full editorial dispositions apply to submission-phase G5; scientific drafting keeps its evidence and independent audits.

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
evidence, independent scientific audits, G1/G2 human topic decisions and the
other stages' recorded automated decisions.
# Active task lifecycle

Preparing `ccfa_task` activates an immutable, hash-bound task for the current native stage and optional active paper. Frozen source changes require a fresh packet. Declare manuscript files that this task is meant to edit in `request.editable_inputs`, as a subset of its bound inputs under `papers/<paper_id>/manuscript/`; only current tracked non-Claude writer/remediator edits may replace those bytes in subsequent existing role contexts. Internal reviews are rejected as task inputs. Independent critics receive neutral task identity and current scientific sources, with author instructions/preferred verdicts withheld.

To stop applying a task, submit `{"action":"ccfa_task_clear","expected_active_sha256":"<current reports/ccfa-tasks/active.json SHA-256>"}` through the same owner literature request route. This deactivates the task and preserves its packet; it does not assert completion or approve a gate. Replace or deactivate an old paper's task before the next paper uses that stage. Full source inputs are never silently truncated. Source content containing configured secrets is rejected before model emission.

