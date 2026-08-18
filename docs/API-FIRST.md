# API-first mode (v1.0)

Doctoral Research OS can run its reasoning stages without Claude Code or Codex CLI. The Python control plane calls the Claude and/or OpenAI APIs directly, validates the returned artifact bundle, and writes only approved project artifacts.

## Required environment

```bash
export ANTHROPIC_API_KEY='...'
export ANTHROPIC_MODEL='your-current-Anthropic-model-id'
export OPENAI_API_KEY='...'
export OPENAI_MODEL='gpt-5.6'
```

You do not need both providers for every stage. A recommended setup is Claude for research synthesis/writing and OpenAI for independent criticism/statistical/code review. API keys are read only from environment variables and are never written to project state.

Check configuration:

```bash
python3 scripts/api_orchestrator.py health
```

Run one stage through an API:

```bash
python3 scripts/api_orchestrator.py stage my-phd intake --provider anthropic \
  --context 'PhD application goal; AI + robotics/mechanical engineering; no laboratory; limited GPU.'
```

The API mode writes its response and manifest under `projects/my-phd/api_runs/<run-id>/`. Model-generated files are restricted to `projects/<project>/`; traversal, hidden files, credentials, `.env`, and state files are rejected. The model cannot call `approve`, `advance`, edit `state/run.json`, execute shell commands, or submit a manuscript.

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
