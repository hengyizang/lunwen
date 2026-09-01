# UUAPI + CC Switch first run

This integration keeps the Doctoral Research OS control plane and research files
local. CC Switch manages optional Claude Code/Codex CLI configurations; the
Python API-first mode calls UUAPI directly. CC Switch does not automatically
export its credentials into the WSL2 Python process.

In other words, CC Switch is the visual manager for interactive Claude
Code/Codex use; `scripts/api_orchestrator.py` is the reproducible research
runner. Switching a card in CC Switch does not change the Python runner's
environment. Configure the same UUAPI account in both places, but never save a
key inside this repository.

UUAPI is a third-party gateway. Confirm the base URL in your own dashboard,
start with a small balance, disable automatic recharge, and do not send private,
licensed or identifying data unless its terms explicitly allow that use.

## 1. Configure CC Switch

Download CC Switch only from `farion1231/cc-switch` GitHub Releases and verify
the published checksum.

- UUAPI quickstart: <https://uuapi.io/docs#quickstart>
- CC Switch releases: <https://github.com/farion1231/cc-switch/releases>

Create two provider cards using the exact root shown by the UUAPI dashboard:

| Card | Application | Protocol | Base URL |
|---|---|---|---|
| Planner / internal critic | Claude Code | Anthropic Messages | `<UUAPI_ROOT>` |
| Persistent writer | Codex | OpenAI Responses | `<UUAPI_ROOT>/v1` |

Use a Claude-family model only for read-only planning/auditing and a GPT/Codex-family model for all persistent writing. Do not configure automatic failover between the two roles. Restart the
corresponding CLI after switching a card. Avoid cloud-syncing provider secrets.

## 2. Configure API-first mode in WSL2

Do not create a repository `.env` file. In a WSL2 shell, obtain the exact model
IDs from the UUAPI dashboard, then enter:

```bash
read -rsp 'UUAPI key: ' UUAPI_API_KEY && echo
export UUAPI_API_KEY
export UUAPI_BASE_URL='https://replace-with-dashboard-host'
export UUAPI_ANTHROPIC_MODEL='replace-with-exact-claude-model-id'
export UUAPI_OPENAI_MODEL='replace-with-exact-gpt-or-codex-model-id'
export UUAPI_STRICT_MODEL_ID='true'
```

`UUAPI_BASE_URL` may be the root or end in `/v1`; the adapter normalizes it.
The Python adapter itself calls `/v1/messages`, `/v1/responses`, and
`/v1/usage`. Never put the API key in the URL.

The runner sends the current project's bounded safe-text snapshot through
UUAPI. It excludes raw/private data, old API responses, build/cache directories,
hidden files and obvious credential files, but this is not a data-loss
prevention guarantee. For the first test, use only synthetic/non-confidential
context and inspect the project directory before every call.

## 3. Run non-billable checks

```bash
python3 scripts/api_orchestrator.py health \
  --provider uuapi-anthropic \
  --provider uuapi-openai

python3 scripts/api_orchestrator.py balance
```

The health output intentionally contains no API key. The balance request does
not generate model output, but the gateway's current billing policy controls.

## 4. Run two minimal live probes

The next commands make small billable requests:

```bash
python3 scripts/api_orchestrator.py health \
  --provider uuapi-anthropic --live

python3 scripts/api_orchestrator.py health \
  --provider uuapi-openai --live
```

Stop if the reported model differs from the requested model, if either endpoint
returns no text, or if the usage record is missing unexpectedly. Do not disable
strict model checking merely to hide a mismatch; first use the exact model ID
reported by the gateway.

## 5. Initialize the first trial

```bash
python3 scripts/researchctl.py init --project my-phd --paper-count 6

python3 scripts/api_orchestrator.py cycle my-phd intake \
  --planner-provider uuapi-anthropic \
  --writer-provider uuapi-openai \
  --critic-provider uuapi-anthropic \
  --max-output-tokens 4000 \
  --context 'AI + robotics/mechanical engineering; no laboratory; limited GPU; target JCR Q1 SCI/SCIE; build a doctoral Theme A with a separately doctoral-level extension Theme B and six non-salami-sliced papers.'
```

The cycle performs five calls: Claude semantic plan, Codex/OpenAI writer, Claude
independent critic, Codex/OpenAI remediation and Claude final critic. It records the requested and gateway-reported model, protocol, endpoint,
request ID and token usage in the run manifest. It does not approve or advance
G0. At G1–G5 it additionally creates the matching initial/final JSON audits and
decision log required by the deterministic gate.

`api_runs/` contains the Claude plan, raw model responses and usage diagnostics
and is ignored by Git. Claude cannot write scientific or submission artifacts;
its schema-checked audits are stored only as internal control records. The
Codex/OpenAI structured scientific artifacts and decision log remain normal
project files so you can review and version them.

`state/output-provenance.json` records the current writer family and file hash;
submission packaging rejects a current Anthropic-authored output.

After the command finishes:

```bash
python3 scripts/researchctl.py status --project my-phd --json
python3 scripts/researchctl.py gate-check --project my-phd
python3 scripts/api_orchestrator.py balance
```

Inspect `projects/my-phd/intake/`, the corresponding `api_runs/<run-id>/`, and
the balance change. Only you may call `ready`, `approve`, and `advance` after
reviewing the artifacts.

If `gate-check` passes and you agree with every G0 value, the first manual gate
sequence is:

```bash
python3 scripts/researchctl.py ready --project my-phd \
  --note 'G0 constraints manually reviewed'
python3 scripts/researchctl.py approve --project my-phd --gate G0 \
  --actor 'your-name' --note 'I confirm the recorded constraints'
python3 scripts/researchctl.py advance --project my-phd
```

Do not run these commands just to clear an error. If `gate-check` reports missing
time, budget, equipment, ethics or scope values, edit and review
`intake/constraints.json` first.

## Troubleshooting

- `403` or `Connection blocked`: confirm the dashboard host and the configured
  User-Agent. Override only with a value documented by UUAPI using
  `UUAPI_ANTHROPIC_USER_AGENT` or `UUAPI_OPENAI_USER_AGENT`.
- Wrong path: CC Switch uses the provider root; Python uses full endpoints
  internally. Set only `UUAPI_BASE_URL`, not `.../responses` or `.../messages`.
- Model mismatch: replace the requested model with the exact dashboard/reported
  ID. `UUAPI_STRICT_MODEL_ID=false` is an explicit, logged-risk escape hatch.
- One provider fails: stop the cycle. Do not silently let Claude become the
  persistent writer or let the writer family audit itself.
