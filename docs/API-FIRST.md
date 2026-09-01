# API-first mode (v1.4)

Doctoral Research OS can run without Claude Code or Codex CLI. The Python control plane calls Claude only for a non-publishable semantic plan and independent audits. OpenAI/Codex independently writes and remediates every persistent artifact. The control plane validates bundles atomically, rejects long verbatim spans copied from Claude control text, records writer-family hashes, and requires a current non-Anthropic origin for every final packaged file.

## Required environment

```bash
export ANTHROPIC_API_KEY='...'
export ANTHROPIC_MODEL='your-current-Anthropic-model-id'
export OPENAI_API_KEY='...'
export OPENAI_MODEL='gpt-5.6'
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

The requested stage must match an `awaiting_work` `state/run.json`; API writing is blocked while a gate is awaiting human approval or already approved. Initialize first, and use the
human `ready` → `approve` → `advance` sequence between stages.

The API mode writes Claude's semantic plan and all raw responses under `projects/my-phd/api_runs/<run-id>/`; this local audit/debug directory is ignored by Git and excluded from submission packages. It sends a bounded text snapshot of the current project, excluding raw/private data, prior API responses, build/cache directories, hidden files, obvious credential files and—during independent review—prior reviews. Only the non-Anthropic writer bundle can become a persistent artifact. Traversal, hidden files, credentials, `.env`, state/provenance files, independent audits and the decision log are protected. No model can call `approve`, `advance`, execute shell commands, or submit a manuscript.

For G1–G5, `cycle` validates Claude critic JSON against the independent-audit contract,
writes matching initial/final audits under `reviews/independent/`, and deterministically appends the
non-Claude writer's itemized dispositions to `reviews/decision-log.md` after the final audit. Fatal or major findings, missing evidence, remediation steps, unresolved dispositions, or a stale/mismatched log keep the gate closed.

G1 additionally requires `program/originality-audit.json`; G2 requires a
complete pairwise paper-distinctness matrix and paper-contract schema 2.0; G3
requires one or more linked experiment designs per paper, with every planned run
assigned exactly once. Candidate and selected venues
must be current JCR Q1 SCI/SCIE. At G4 the registry and claim matrix are hash-linked to the approved plan and outputs. At G5 the control plane checks the final source and all submission-bound text, deterministic figure provenance, current citation/venue report hashes and per-paper approval hash. These are readiness
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

Automatic: semantic planning, non-Claude structured artifact generation, evidence bookkeeping, public metadata discovery, data-download validation, approved experiment execution, citation checks, venue checks, manuscript/review artifacts, deterministic chart rendering workflows and manual submission packages.

Human required: final topic choice, doctoral architecture, data-license confirmation, experiment approval, interpretation of scientific evidence, authorship/ethics, current JCR verification, final PDF/DOCX inspection and every journal portal action.

The system intentionally cannot guarantee novelty, acceptance, publication, doctoral admission or employment outcomes. It is an auditable research workflow, not a substitute for scientific judgment.
