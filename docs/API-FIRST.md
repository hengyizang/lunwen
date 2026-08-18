# API-first mode (v1.1)

Doctoral Research OS can run its reasoning stages without Claude Code or Codex CLI. The Python control plane calls the Claude and/or OpenAI APIs directly, validates the returned artifact bundle, and writes only approved project artifacts.

## Required environment

```bash
export ANTHROPIC_API_KEY='...'
export ANTHROPIC_MODEL='your-current-Anthropic-model-id'
export OPENAI_API_KEY='...'
export OPENAI_MODEL='gpt-5.6'
```

You do not need both providers for every stage. A recommended setup is Claude for research synthesis/writing and OpenAI for independent criticism/statistical/code review. API keys are read only from environment variables and are never written to project state.

UUAPI is supported as an explicit third-party gateway through
`uuapi-anthropic` and `uuapi-openai`. It uses one gateway key but keeps the
Anthropic Messages author and OpenAI Responses critic as separate provider
roles. See [`UUAPI-CC-SWITCH.md`](UUAPI-CC-SWITCH.md) before the first run.

Check configuration:

```bash
python3 scripts/api_orchestrator.py health
```

`health --live` makes a small billable request. `balance` queries the configured
UUAPI wallet/quota endpoint without generating model output.

Run one stage through an API:

```bash
python3 scripts/researchctl.py init --project my-phd --paper-count 6
python3 scripts/api_orchestrator.py stage my-phd intake --provider anthropic \
  --context 'PhD application goal; AI + robotics/mechanical engineering; no laboratory; limited GPU.'
```

The requested stage must match `state/run.json`; initialize first, and use the
human `ready` → `approve` → `advance` sequence between stages.

The API mode writes its response and manifest under `projects/my-phd/api_runs/<run-id>/`; this local audit/debug directory is ignored by Git. It sends a bounded text snapshot of the current project to the selected model, excluding raw/private data, prior API responses, build/cache directories, hidden files, obvious credential files and—during independent review—prior reviews. Model-generated files are restricted to `projects/<project>/`; traversal, hidden files, credentials, `.env`, state files, independent audits and the decision log are protected. The model cannot call `approve`, `advance`, edit `state/run.json`, execute shell commands, or submit a manuscript.

For G1–G5, `cycle` validates critic JSON against the independent-audit contract,
writes matching initial/final audits under `reviews/codex/`, and appends the
author's itemized dispositions to `reviews/decision-log.md`. A non-passing final
verdict remains recorded and keeps the deterministic gate closed.

## Architecture

```text
Human
  |
  v
Python control plane ---- state/gates/hashes/budgets/audits
  |             |
  |             +---- local experiments after G3 approval
  |
  +---- Claude API -------- research synthesis / writing
  |
  +---- OpenAI API -------- independent critique / code/statistical audit
  |
  +---- public metadata ---- literature/data discovery
  |
  +---- venue adapter ------ template/compliance checks
  |
  +---- submission package - manual upload only
```

Claude Code and Codex CLI remain optional acceleration interfaces. The repository's deterministic control plane is the source of truth.

## What is and is not automatic

Automatic: research-task drafting, structured artifact generation, evidence bookkeeping, public metadata discovery, data-download validation, approved experiment execution, citation checks, venue checks, manuscript/review artifacts and manual submission packages.

Human required: final topic choice, doctoral architecture, data-license confirmation, experiment approval, interpretation of scientific evidence, authorship/ethics, current JCR verification, final PDF/DOCX inspection and every journal portal action.

The system intentionally cannot guarantee novelty, acceptance, publication, doctoral admission or employment outcomes. It is an auditable research workflow, not a substitute for scientific judgment.
