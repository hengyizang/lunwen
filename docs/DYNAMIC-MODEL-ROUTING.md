# Dynamic task routing

Codex manages task declarations and the approved candidate pool. A deterministic
selector chooses a route immediately before each existing model request. It does
not call another model to decide where to send the task, add a paid planning
role, grant a budget, approve science or automatically retry a failed request.

The objective is lower measured cost per accepted task, subject to the task's
quality and role requirements. This implementation does not establish global
optimality or scientific equivalence. The existing seven-model assignments are
the approved baselines. Additional transports, groups, efforts and context bands
in `config/model-candidates.json` are candidates, not accepted alternatives.

## Declare the actual task

`cycle` cloud requests and the `stage`/`cycle` API CLI accept `task_profile`:

```json
{
  "task_class": "routine-implementation",
  "science_risk": "routine",
  "min_output_tokens": 1000,
  "deadline_seconds": 180,
  "priority": "quality"
}
```

`task_class` is a lowercase slug of at most 80 characters. `science_risk` is
`critical`, `scientific`, `routine` or `auxiliary`. `priority` defaults to
`quality`; `cost` and `latency` can rank only candidates that already meet the
quality and scope requirements. Optional `min_output_tokens` is a positive
integer up to 32768; `deadline_seconds` is a positive integer up to 600.
The output requirement must fit the approved request limit before any call.
These are task requirements, not permission to increase a spending ceiling.
The profile cannot specify a provider, model, effort, URL, key or budget.

Classify the work from its actual purpose and evidence. Do not mark scientific
interpretation or a key algorithm as routine to obtain a cheaper route. The
selector does not guess task classes from prompt keywords. Existing explicit
critical `task_kind` declarations remain effective. A critical profile or a
recognized critical task class selects the Astra/Opus scientific baseline.
In dynamic mode, an unclassified G4/G5 cycle is conservatively treated as
critical. Explicitly declared routine work can retain the original Sol/Sonnet
baseline; the final independent critic retains its approved Opus role.

For the CLI, pass the object as `--task-profile '<JSON object>'`. Duplicate JSON
properties, non-object profiles and unsupported fields are rejected. The cloud
owner issue uses the same object directly:

```json
{
  "schema_version": "1.0",
  "action": "cycle",
  "project": "my-phd",
  "actor": "Hengyi Zang",
  "allow_paid": true,
  "stage": "experiment-execution",
  "task_profile": {
    "task_class": "routine-implementation",
    "science_risk": "routine",
    "priority": "quality"
  }
}
```

This example is not a dispatch or new spending authorization. The authenticated
owner issue boundary, existing cumulative allowance, reservations, human gates,
cloud execution and frozen experimental inputs remain required.

## Automatic continuation

Continuation reads the optional fixed control file
`state/task-routing-profile.json` after restoring the project:

```json
{
  "schema_version": "1.0",
  "stage": "experiment-execution",
  "task_profile": {
    "task_class": "scientific-interpretation",
    "science_risk": "critical",
    "priority": "quality"
  }
}
```

This is protected management state, not an artifact the scientific writer may
create. Codex can set it through the non-billable authenticated owner cloud action
`set_routing_profile`, supplying `stage`, `task_profile` and `allow_paid:false`.
The declared stage must equal the persisted current stage. First creation needs
no prior hash; replacement requires `expected_profile_sha256` matching the exact
existing file, preventing stale management requests from overwriting a newer
declaration. The controller records deterministic provenance and a management
receipt without changing stage, authorizing spending or approving science.

The file binds the exact current stage. A missing file leaves the task
unclassified; continuation never invents a routine declaration. A stale stage,
malformed or oversized file, duplicate property or symlink stops the request
before model execution. Update a stage-bound declaration when the actual work
changes; keeping an old declaration is not permission to downgrade later work.

## Admit a candidate using real evidence

The route identity includes provider/group, exact model, family, reasoning
effort and context envelope. A same-named model on another gateway or promotional
group does not inherit acceptance. A successful HTTP response, provider model
label, short smoke test or registry `status` field does not establish equal
quality. Current Anthropic and DeepSeek transport support remains high-only.
The historically approved Gemini native base ID and the high-suffixed diagnostic
remain distinct exact routes. Base low/medium payload support is an unaccepted
candidate capability; the approved baseline still requests high thinking.
The high-suffixed ID requires high thinking. No low/medium-suffixed ID is inferred
from the portal. Empty or changing catalogs mean availability is unconfirmed;
they do not establish unsupported generation. Production still requires current
exact-ID advertisement before any paid request.
OpenAI low and medium protocol support does not mean those settings have
passed project acceptance. No additional low effort, cheap group or long-context
candidate is declared accepted by this change.

Candidate promotion reuses the existing frozen blind-review packets. It requires
at least six paired baseline/candidate cases, including at least three held-out
cases, all required quality thresholds passing, independent human judgments,
exact route identity and fully reconciled billing for the actual requests.
The controller rechecks hashes, evidence and scope rather than trusting a
model-authored pass boolean. It records acceptance under protected
`state/dynamic-routing-acceptances.json`. A missing or changed packet, candidate,
baseline identity or human evidence blocks acceptance or later use.

Codex can inspect the pool using the non-billable owner cloud action
`routing_status` with `allow_paid:false`. To admit an existing candidate, the
non-billable action `accept_route` accepts exactly these selectors in addition to
the common owner fields:

```json
{
  "candidate_id": "<existing candidate ID>",
  "packet_id": "<existing reviewed packet ID>",
  "profile_file": "evidence/routing-profiles/routine.json",
  "expected_profile_sha256": "<exact 64-character lowercase SHA-256>",
  "stage": "experiment-execution",
  "role": "persistent-writer"
}
```

The profile file contains the strict task-profile object. The controller invokes
only the bounded routing management entry point. An acceptance cannot introduce
an arbitrary model, change API credentials, run a shell, approve a scientific
gate or grant paid trial calls. Creating new benchmark evidence still requires
the existing separate authorization and cloud execution controls.

## Choose at request time

For each existing role the selector checks complete input size, required output,
attachments, supported modality, exact acceptance scope, route availability,
recent incomplete responses and the switching cooldown. A long-context label
does not prove reliable reasoning over a long document: the actual request must
fit both the configured limit and the measured acceptance envelope. No evidence
is silently truncated to fit a cheaper route.

For critical/scientific work and fresh independent audits, the scientific model,
family and effort floor are retained; an accepted gateway/group can change.
Persistent scientific authoring remains OpenAI, and Claude plans/audits remain
read-only. Metadata and bounded engineering contracts retain their scoped models.
Candidates outside these constraints are excluded even if their price is lower.

Ranking uses actual cost per accepted task and measured latency, with a required
improvement margin and cooldown. Cache reads and writes are included in settled
costs; caches are not assumed portable across gateways or groups. The selector
does not merely multiply a group's advertised coefficient by an assumed token
count. The central runtime still quotes, reserves and reconciles each request.

An outstanding reservation or unresolved charge stops new paid requests and
route switching. A timeout or incomplete response may already have incurred a
charge; it is not an instruction to send the same job to another gateway.
Record the original outcome, reconcile its bill and inspect existing artifacts
before any separately authorized retry. No automatic paid fallback is introduced.

Before a production generation request, the runtime also reads the selected
group's live model catalog. A missing model or unavailable catalog stops before
billing reservation or generation, and records an availability event. This GET
does not verify model authenticity or quality. An exact validated response-cache
replay needs no live catalog or new generation. Catalog failure never authorizes
an unaccepted replacement or a paid probe.

Acceptance also binds the runtime task class and scientific risk, the scored
artifact's actual provider/model/role/run provenance, and both current price
contracts. A high-quality answer from another model cannot be paired with the
candidate's bill. Changed prices invalidate the old cost comparison; a manager
must review fresh evidence before using that alternative again.

## Audit and rollback

Each role's usage record contains its declared task profile, selection decision,
candidate identity, exclusions and actual transport. A cycle manifest separates
`production_route_baseline` from `actual_routes`, whose provider/model/effort and
endpoint come from the returned model results. Declared and effective task kinds
remain distinct. Initial and final scientific audits stay fresh and the existing
five-role review sequence remains intact.

`DR_OS_DYNAMIC_ROUTING=production` enables selection; it is the default. With no
task-specific accepted alternatives the approved baseline is used. Set
`DR_OS_DYNAMIC_ROUTING=off` to roll back candidate selection and the additional
conservative late-stage classification to the static production routes. Profile
validation, requested output checks, central budget controls and all scientific
gates still apply. Rollback does not approve a failed request or settle its bill.

All engineering validation for this change runs on GitHub's cloud runners with
simulated transports. Such tests verify control behavior; they do not certify
new model/channel quality, doctoral merit, experimental completion or publication
readiness.

## Task-level operational review, 2026-10-29

The [2026-10-29 task assignment and review policy](MODEL-TASK-ASSIGNMENTS-20261029.md)
registers 48 fine-grained task classes. `dynamic_routing.validate_profile` applies
their risk floors before model resolution. Each enabled selection and the status
command expose `management_review` from existing receipts and spending authority;
normal review, identity/completion failures, source defects, cost/latency changes
and optional current catalog/quote observations never trigger an extra paid call.
Declare the actual task class before execution. A new candidate cannot replace
the baseline without the existing scoped acceptance, role and quality controls.

## Cloud comparison evidence, 2026-10-21

The [model and gateway report](MODEL-COMPARISON-RESULTS-20261021.md) records
120 requests across the fixed model/group matrix, a separate clarified cohort,
and one native Argon base image check. Preserve its immutable ledger references
and [instrument errata](MODEL-COMPARISON-VALIDITY-ERRATA.md). The ambiguous v1
aggregate scores cannot rank capability or promote routes. The clarified short
cases and masked model-assisted proposal review do not replace the paired
real-task and independent human acceptance controls above.

Before scheduling a proposed experiment, check that a mechanism-removed arm
does not duplicate an existing baseline with the same data, configuration and
seed. Reuse matching predictions and account for justified distinct fits.
Separate an inconclusive interval from an equivalence claim, specify the actual
gain-shift evaluation, and enforce resource limits across active workers,
preprocessing, inference and statistics. Stopping new launches alone does not
enforce a total wall-clock, CPU or memory ceiling. These checks preserve the
existing scientific gates; model-generated proposals cannot approve themselves.

