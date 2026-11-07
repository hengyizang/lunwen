# UUAPI + CC Switch first run

This is the optional legacy UUAPI/CC Switch adapter guide. Current production
research uses [CheapAI + CodeKey](PRODUCTION-MODEL-ROUTING.md) through
[Gateway startup](GATEWAY-STARTUP.md); production workflows do not load UUAPI
credentials. The local CC Switch/WSL2 instructions below apply only to an
explicitly selected compatible runtime and are not cloud setup prerequisites.
The current [workflow](../references/workflow.md) and
[total-cost policy](TOTAL-COST-POLICY.md) apply to both entry points.

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
`/v1/usage`. If the gateway documents only OpenAI-compatible Chat Completions,
set `UUAPI_OPENAI_PROTOCOL=chat_completions`; the GPT route then uses
`/v1/chat/completions`, with `max_completion_tokens` by default. Set
`UUAPI_OPENAI_CHAT_TOKEN_FIELD=max_tokens` only for a gateway requiring the old
field. Complete `UUAPI_OPENAI_API_KEY` / `UUAPI_OPENAI_BASE_URL` and
`UUAPI_ANTHROPIC_API_KEY` / `UUAPI_ANTHROPIC_BASE_URL` pairs support separate
providers; partial overrides fail closed. Never put the API key in the URL and never enable a
silent model fallback.

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

## 4. Run an optional live diagnostic when needed

After the project exists and has its existing cumulative allowance and exact
route quote, an actual endpoint diagnosis can use this small billable request:

```bash
python3 scripts/api_orchestrator.py health \
  --project my-phd --provider uuapi-openai --live
```

Use `uuapi-anthropic` when diagnosing that route. Neither probe is a mandatory
paid startup step; both share the project's existing cost accounting.
Stop if the reported model differs from the requested model, if either endpoint
returns no text, or if the usage record is missing unexpectedly. Do not disable
strict model checking to hide a mismatch or accept an unreviewed model merely
because the gateway reports it. Verify the configured exact route and preserve
the failed request's actual or conservatively estimated charge.

## 5. Initialize the first trial

```bash
python3 scripts/researchctl.py init --project my-phd --paper-count 6

python3 scripts/api_orchestrator.py cycle my-phd intake \
  --planner-provider uuapi-anthropic \
  --writer-provider uuapi-openai \
  --critic-provider uuapi-anthropic \
  --max-output-tokens 4000 \
  --context 'Use the actual recorded intake constraints. Propose doctoral directions without choosing for the owner. Keep one cumulative doctoral question, core A and independently evidenced extension B, and six distinct papers. Preserve recorded venue ambitions as planning observations. Do not invent scientific evidence, career weights or application routes.'
```

An ordinary cycle performs three calls: Claude semantic plan, Codex/OpenAI writer
and one fresh independent advisory critic. Actual actionable findings trigger
writer remediation and a fresh recheck; a clean critique creates no second
review call or fictitious final receipt. The run manifest records the actual
requested/reported model, protocol, endpoint, request ID and usage. The cycle
does not itself approve or advance G0; stage transitions remain with the
controller and record automated decisions as such.

At final submission, configure the three mutually blind source-view routes from
different families, each different from the writer. The legacy two-model setup
alone cannot supply that panel. Preserve each real response before synthesis,
including uncertainty and disagreement; do not vote or infer acceptance odds.
See the production routes above rather than inventing missing reviews.

From G1 onward, provide enough context/output capacity for closest-work evidence,
the six-paper cumulative question and pairwise independence comparisons. After
the actual G1/G2 topic decisions, complete the active paper's G3–G5 before the
next enters G3. Use its canonical frozen plan and exact run coverage, preserving
legacy executed batch records. Existing Q1/Q2 ambitions remain planning
observations rather than scientific or packaging thresholds. At G5, OpenAI
writes the English manuscript; language/style diagnostics are C observations,
while evidence integrity remains A.

Before G3, install the local analytical power tool and use the dashboard's data
quality, power and preregistration controls:

```bash
bash scripts/bootstrap-wsl.sh --with-research-quality-tools
```

G1 now requires a claim-level novelty/saturation matrix. G3 requires a current
local quality report for the active paper's selected datasets and its frozen,
hash-bound preregistration. The controller can verify lawful data rights and
record automated confirmations without another human approval. G4 checks actual registry-bound
domain/strong-baseline and clean-room reproduction. Full operation and the
Monte Carlo alternative for ML metrics are in `docs/RESEARCH-QUALITY.md`.

`api_runs/` contains the Claude plan, raw model responses and usage diagnostics
and is ignored by Git. Claude cannot write scientific or submission artifacts;
its schema-checked audits are stored only as internal control records. The
Codex/OpenAI structured scientific artifacts remain normal project files. The
control plane writes the decision log from the real critique and any actual
repairs/rechecks; it never invents a missing second review.

`state/output-provenance.json` records the current writer family and file hash.
G5 and submission packaging reject Anthropic, untracked, or modified-after-record
final files. Human-created files can be explicitly attested with
`scripts/output_provenance.py attest` after independent review.

After the command finishes:

```bash
python3 scripts/researchctl.py status --project my-phd --json
python3 scripts/researchctl.py gate-check --project my-phd
python3 scripts/api_orchestrator.py balance
```

Inspect `projects/my-phd/intake/`, the corresponding `api_runs/<run-id>/`, and
the recorded costs. The owner chooses the doctoral topic at G1 and each paper
topic at G2. Checked `ready`/`advance` transitions at G0/G3/G4/G5 use explicit
automated decisions and do not require a human signature.

Once actual G0 constraints and checks are complete, the deterministic transition
is:

```bash
python3 scripts/researchctl.py ready --project my-phd \
  --note 'G0 constraints and source checks completed'
python3 scripts/researchctl.py advance --project my-phd
```

Do not run these commands just to clear an error. If `gate-check` reports missing
time, budget, equipment, ethics or scope values, edit and review
`intake/constraints.json` first.

A checks retain source/claim/numeric integrity, lawful data, frozen experiments
and all negative/failed outcomes. Final B venue/export/panel checks bind the
submission snapshot and are reused while unchanged. Numeric scores, CFH/H/AD
coverage and editorial dispositions remain C observations, not compulsory
scorecards or reasons for an otherwise unnecessary paid repair.

## Troubleshooting

- `403` or `Connection blocked`: confirm the dashboard host and the configured
  User-Agent. Override only with a value documented by UUAPI using
  `UUAPI_ANTHROPIC_USER_AGENT` or `UUAPI_OPENAI_USER_AGENT`.
- Wrong path: CC Switch uses the provider root; Python uses full endpoints
  internally. Set only `UUAPI_BASE_URL`, not `.../responses` or `.../messages`.
- Model mismatch: inspect the exact configured and returned identities against
  the reviewed route. Keep strict identity validation enabled; do not relabel
  an unexpected response as an accepted model.
- One provider fails: stop the cycle. Do not silently let Claude become the
  persistent writer or let the writer family audit itself.
