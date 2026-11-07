# API-first mode (v2.0.0)

Doctoral Research OS can run without Claude Code or Codex CLI. The Python control plane calls Claude only for a non-publishable semantic plan and independent audits. OpenAI/Codex independently writes and remediates every persistent artifact. The control plane validates bundles atomically, rejects long verbatim spans copied from Claude control text, records writer-family hashes, and requires a current non-Anthropic origin for every final packaged file.

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
  --context 'PhD application goal; AI + robotics/mechanical engineering; no laboratory; limited GPU.'
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
is no longer required. G3 prioritizes every paper contract. If all providers
fail, the command stops before model charges. `--no-auto-data-discovery` exists for
deliberate CLI-only diagnostics; the visual dashboard keeps automation enabled.

The API mode writes Claude's semantic plan and all raw responses under `projects/my-phd/api_runs/<run-id>/`; this local audit/debug directory is ignored by Git and excluded from submission packages. It sends a bounded text snapshot of the current project, excluding raw/private data, prior API responses, build/cache directories, hidden files, obvious credential files and—during independent review—prior reviews. Only the non-Anthropic writer bundle can become a persistent artifact. Traversal, hidden files, credentials, `.env`, state/provenance files, independent audits and the decision log are protected. No model can call `approve`, `advance`, execute shell commands, or submit a manuscript.

Ordinary `cycle` uses planner → writer → one source-bound independent critique.
Actual actionable findings alone trigger repair and fresh re-review. The current
observation receipt binds the notebook decision and has no independent gate
authority; legacy dual-review records remain readable history. At final submission
the three-family mutually blind panel replaces the ordinary critic. A actual
source/claim/numeric failures block; C observations do not manufacture repairs.
See [workflow.md](../references/workflow.md) for exact views and B snapshot reuse.

G1 uses source-bound closest-work evidence and honest stopping limits. G2 uses
cumulative contribution/evidence rows and paper contracts, preserving standalone
value and one doctoral question instead of fifteen repeated pair forms. G3 binds
the active paper's actual rights, design, frozen inputs and appropriate methods.
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
  |             +---- local experiments after G3 approval
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

Claude Code and Codex CLI remain optional acceleration interfaces. The repository's deterministic control plane is the source of truth.

## What is and is not automatic

Automatic: semantic planning, non-Claude structured artifact generation, evidence bookkeeping, public metadata discovery, data-download validation, approved experiment execution, citation checks, venue checks, manuscript/review artifacts, hash-bound G5 academic-style auditing, deterministic chart rendering workflows and manual submission packages.

The G5 style audit runs after both Codex writing passes and is available manually
through `python3 scripts/academic_style.py audit --project <slug> --paper P01`.
It evaluates writing quality without estimating an AI probability or attempting
detector evasion. Codex must preserve scientific meaning, numbers, equations,
citations, uncertainty and the applicable AI-use disclosure while resolving its
findings. The report includes line-level findings from the reviewed academic
subset of `avoid-ai-writing`, `vale-ai-tells` and `No AI Slop`. If local
`proselint==0.16.0` or `harper-cli` is installed, it also contains advisory
offline grammar diagnostics; absence or failure of either optional tool does not
bypass or weaken the built-in deterministic gate.

Human required: final topic choice, doctoral architecture, data-license confirmation, experiment approval, interpretation of scientific evidence, authorship/ethics, current JCR verification, final PDF/DOCX inspection and every journal portal action.

The system intentionally cannot guarantee novelty, acceptance, publication, doctoral admission or employment outcomes. It is an auditable research workflow, not a substitute for scientific judgment.

Every paid call also passes through the local CNY budget ledger and
byte-identical request cache described in `RESEARCH-CAPABILITIES.md`. Cache hits
do not remove planner/critic roles; they only avoid paying twice for the exact
same audited request.

For the natural Codex-chat workflow and short commands to start, continue,
inspect and package work, see [`CHAT-USAGE.md`](CHAT-USAGE.md).
