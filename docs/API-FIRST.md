# API-first mode (v2.0.0)

Doctoral Research OS can run without Claude Code or Codex CLI. The Python control plane calls Claude only for a non-publishable semantic plan and independent audits. OpenAI/Codex independently writes and remediates every persistent artifact. The control plane validates bundles atomically, rejects long verbatim spans copied from Claude control text, records writer-family hashes, and requires a current non-Anthropic origin for every final packaged file.

`autopilot.py start/resume/plan` now delegates to this same API cycle and checked
stage transitions. The old local Claude Code/Codex process backend is retired;
it no longer provides subscription authentication, arbitrary workspace tools or
process transcripts. `plan` is read-only and makes no requests. See
[the compatibility commands](CHAT-USAGE.md#api-兼容命令入口) for retired options.

## Required environment

```bash
export ANTHROPIC_API_KEY='...'
export ANTHROPIC_MODEL='your-current-Anthropic-model-id'
export OPENAI_API_KEY='...'
export OPENAI_MODEL='your-current-OpenAI-model-id'
```

The full `cycle` requires both model families. Claude plans and audits; OpenAI/Codex writes. API keys are read only from environment variables and are never written to project state.

UUAPI is supported as an explicit third-party gateway through
`uuapi-anthropic` and `uuapi-openai`. It uses one gateway key but keeps the
Anthropic Messages planner/auditor and OpenAI Responses writer as separate
roles. See [`UUAPI-CC-SWITCH.md`](UUAPI-CC-SWITCH.md) before the first run.

Check configuration:

```bash
python3 scripts/api_orchestrator.py health
```

`health --live` makes a small billable request. `balance` queries the configured
UUAPI wallet/quota endpoint without generating model output.

Run one complete stage cycle:

```bash
python3 scripts/researchctl.py init --project my-phd --paper-count 6
python3 scripts/api_orchestrator.py cycle my-phd intake \
  --planner-provider anthropic \
  --writer-provider openai \
  --critic-provider anthropic \
  --context 'Your research background, doctoral objective, constraints, available data and compute.'
```

The writer/remediator output ceiling defaults to 12,000 tokens. Read-only
planning and independent critique use a separate 4,000-token ceiling, which
can be changed for one session with `DR_OS_CONTROL_MAX_OUTPUT_TOKENS`. Writing
snapshots contain the complete active paper but only the contracts of inactive
papers; prior reviews remain excluded and are supplied to the appropriate
review/remediation call explicitly. This lowers repeated input without weakening
cross-paper constraints or review independence.

Inspect actual token use, cache hits and estimated CNY cost without making a
model call:

```bash
python3 scripts/api_orchestrator.py cost my-phd
python3 scripts/api_orchestrator.py cost my-phd --paper P01
```

The requested stage must match an `awaiting_work` `state/run.json`; writing is blocked while a decision is pending or already recorded. Use `gate-check` → `ready`; only G1 and each G2 paper topic require human `approve`. Other stages receive recorded automated decisions before `advance`. See [the workflow](../references/workflow.md) for paper-scoped execution and exploration/scientific/submission phases.

For G1 and G3, `cycle` and the one-pass `stage` command automatically derive up
to eight dataset-query variants, search the eight reviewed public metadata
providers, deduplicate results and
build a deterministic metadata shortlist before the first paid model call. An
optional `--discovery-query` gives the automatic builder a preferred focus but
is no longer required. G3 prioritizes the active paper's contract and preserves recorded legacy batch scope. If all providers
fail, the command stops before model charges. `--no-auto-data-discovery` exists for
deliberate diagnostics; the cloud controls keep automation enabled.

The API mode writes Claude's semantic plan and all raw responses under `projects/my-phd/api_runs/<run-id>/`; this local audit/debug directory is ignored by Git and excluded from submission packages. It sends a bounded text snapshot of the current project, excluding raw/private data, prior API responses, build/cache directories, hidden files, obvious credential files and—during independent review—prior reviews. Only the non-Anthropic writer bundle can become a persistent artifact. Traversal, hidden files, credentials, `.env`, state/provenance files, independent audits and the decision log are protected. No model can call `approve`, `advance`, execute shell commands, or submit a manuscript.

API and CLI share the same cycle rule: administrative G0 intake uses planner → writer
(two calls); ordinary G1+ research uses planner → writer → one source-bound independent critique
(three calls).
Actual actionable findings alone trigger repair and fresh re-review. The current
observation receipt binds the notebook decision and has no independent gate
authority; legacy dual-review records remain readable history. At final submission
the three-family mutually blind panel replaces the ordinary critic. Actual
source/claim/numeric failures block; C observations do not manufacture repairs.
See [workflow.md](../references/workflow.md) for exact views and B snapshot reuse.

G1 uses source-bound closest-work evidence and honest stopping limits. G2 uses
cumulative contribution/evidence rows and paper contracts, preserving standalone
value and one doctoral question instead of fifteen repeated pair forms. G3 binds
the active paper's source/version, privacy, known access restrictions, design, frozen inputs and appropriate methods.
Licence/research-use verification is optional metadata, not a pre-use gate or a human approval.
Complete outcomes, failures and registered comparisons are backed up separately under
`experiments/archive`; manuscripts select scientifically relevant evidence and retain material
contrary evidence affecting their conclusions. Public AI-use statements are optional and author-editable;
internal writer provenance remains protected. These three user choices apply to every phase.
Venue ranking is truthful planning metadata; actual fit replaces rank floors.
At G4 the registry and claim matrix are hash-linked to the approved plan and
outputs; clean-room claims require an executor-issued, digest-pinned container
isolation receipt. A linked worktree alone does not qualify. At G5 the control plane checks the final source and
all submission-bound text, deterministic figure provenance, current
citation/venue report hashes and per-paper approval hash. These are readiness
checks, not an acceptance guarantee.

## Architecture

```text
Human
  |
  v
Python control plane ---- state/gates/hashes/budgets/audits
  |             |
  |             +---- controlled experiments after frozen, checked G3
  |
  +---- Claude API -------- read-only semantic planning / independent audit
  |
  +---- OpenAI API -------- persistent writing / remediation / plotting code
  |
  +---- public metadata ---- literature/data discovery
  |
  +---- venue adapter ------ template/compliance checks
  |
  +---- submission package - manual upload only
```

The deterministic control plane remains authoritative. Command compatibility does not restore the retired local Claude Code/Codex subprocess backend.

## What is and is not automatic

Automatic: semantic planning, non-Claude structured artifact generation, evidence bookkeeping, public metadata discovery, data-download validation, approved experiment execution, citation checks, venue checks, manuscript/review artifacts, hash-bound G5 academic-style auditing, deterministic chart rendering workflows and manual submission packages.

The G5 style audit runs after existing writing/remediation passes and is available manually
through `python3 scripts/academic_style.py audit --project <slug> --paper P01`.
It evaluates writing quality without estimating an AI probability or attempting
detector evasion. Codex must preserve scientific meaning, numbers, equations,
citations, uncertainty and internal provenance while resolving concrete findings;
public AI-use statements remain author-editable. Style findings are C observations,
not scientific gates or compulsory extra editing passes. The report includes line-level findings from the reviewed academic
subset of `avoid-ai-writing`, `vale-ai-tells` and `No AI Slop`. If local
`proselint==0.16.0` or `harper-cli` is installed, it also contains advisory
offline grammar diagnostics; absence or failure of either optional tool does not
bypass scientific integrity or final rendering checks.

Human stage decisions: the G1 doctoral topic and each G2 paper topic. Other stages use
recorded automatic checks, including frozen experiment inputs and cumulative budgets.
Scientific interpretation and optional visual feedback need actual evidence; they do not
create additional administrative approval gates. Authors handle external authorship and every journal portal action.

The system intentionally cannot guarantee novelty, acceptance, publication, doctoral admission or employment outcomes. It is an auditable research workflow, not a substitute for scientific judgment.

Every paid call passes through the CNY ledger and existing cumulative project totals
in [TOTAL-COST-POLICY.md](TOTAL-COST-POLICY.md). Verified charges or honest conservative upper
estimates count against those totals; no extra billing approval or per-call cap is added.
Byte-identical eligible planner/writer requests may reuse the cache. Independent scientific
critiques always make a fresh call and retain their actual source-bound identity receipts.

For the natural Codex-chat workflow and short commands to start, continue,
inspect and package work, see [`CHAT-USAGE.md`](CHAT-USAGE.md).


## Explicit temporary G1 validation roster

An owner auxiliary manifest with `kind: g1-transport-validation` may explicitly
set `validation_roster: astra-argon`. This single G1 sample uses the existing
CodeKey Astra/high for read-only planning and persistent writing, and the existing
native Argon/high for fresh, source-only independent criticism. Omitting this
option retains the original Opus planner/critics and temporary same-model writer
transport. Only the exact recorded project, manifest, role and source snapshot
are eligible; ordinary production role checks and routes resume on exit.

The native three-call cycle adds repair/review only for actual findings, up to
five distinct role calls. Explicit 12000 output tokens give a conservative
53.5104264 CNY upper estimate at the full 2 MB input bound; every actual request
is quoted and accounted through the original cumulative project allowance.
This estimate supplies no new allowance or per-paper cap. Model IDs, high effort,
writer provenance, different-family criticism, source bindings, deadline and
single-POST controls apply. Astra planning records use `semantic-plan` names.
The sample cannot approve G1/G2, advance a gate, auto-reschedule, promote a route
or substitute for the separate public-review calibration.

The same explicit roster may set `response_streaming: true` for its CodeKey
Astra Responses requests. Argon and default production requests keep their
existing transport. The stream must end with a complete, identity-consistent
`response.completed` object and complete HTTP framing. Deltas, `[DONE]`, a
truncated body or an incomplete/error event cannot supply a successful result.
The scope/cache identity records streaming; one reservation still permits one
POST, with no automatic retry. Provider support and any improvement over a 524
require a separate actual sample, not just software tests.

For a failed temporary transport, an owner `preflight` request may name the
allowlisted `billing_provider`, for example `codekey-codex-pro`. Its separate
`billing-inspection.json` reads only that provider's debit counters and shared
guard; default catalogs and routes remain unchanged. It generates no text,
settles no charge and grants no budget. Keep an unknown reservation until
independent evidence supports the existing explicit reconciliation operation.

## Bounded public-review calibration batches

An explicit `public-review-calibration` auxiliary manifest may set
`calibration_batch_cases` to an integer from 1 to 8 and optionally
`calibration_batch_index` to one actual, one-based batch in the canonical frozen
queue. For example, cases `1` and index `1` plan one complete-paper request.
The index must exist after the full corpus is verified. Omitting both options
keeps the existing maximum of eight cases and 750 KB per batch and complete
queue execution.

Smaller batches retain every original scientific API field, the same official
rubric, source hashes and blind case identities. They do not truncate a paper,
change the 24-paper population or its 16/8 split, send answer labels, lower the
reasoning effort, change models or bypass central billing. The report records
the full canonical batch/case counts and the actual selected plan. A successful
single-batch probe returns `bounded_batch_complete` and remains
`NOT_CALIBRATED` until all corpus cases have current predictions; missing
partition coverage keeps full-partition agreement unknown.
Descriptive `observed_subset_exact_agreement` covers only received predictions,
including abstentions as nonmatches; it cannot replace the full-partition result.
Raw outputs,
identity checks, failed-attempt fees, deadline checks and no-retry behavior
remain the same. One batch cannot establish model quality or validate the
three-view panel, numerical scores, human claim agreement or doctoral science.
