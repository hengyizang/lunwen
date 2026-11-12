# Third-party runtime policy

Effective 2026-11-09 under
[owner decision](OWNER-DECISION-2026-11-09.md). This document governs **new**
third-party integrations. The 46 reviewed sources in
`integrations/upstreams.lock.json` and the 11 adapted entries in
`integrations/research-automation-tools.json` keep their original reviewed
status and are not retroactively rewritten.

Registry: `integrations/third-party-runtime.json`.
CLI: `python3 scripts/third_party_runtime.py --help`.
Adapting an upstream that cannot run as-is (`scaffold` / `wrap`):
[`docs/THIRD-PARTY-ADAPTATION.md`](THIRD-PARTY-ADAPTATION.md).

## 1. Risk tiers

Choose the lowest tier that actually applies. The tier is recorded, not a
blocking approval gate.

| Tier | Typical case | Requirements |
|---|---|---|
| `local-readonly` | Pure library, local model, no network, no credentials, no spend | Record repository, ref, license, access date. No further review required. |
| `network-no-credentials` | Public API/search/retrieval without keys or payment | Same, plus record which network endpoints the tool contacts. Do not send raw datasets, manuscripts, or credentials. |
| `credentials-or-paid` | Needs an API key, paid provider, or GPU service | Same, plus keep keys out of files, URLs, argv and logs; use HTTPS; record requested and reported model IDs; stop on mismatched identity; every attempt counts against the configured cumulative total. |

Tier choice is self-declared at registration and can be corrected later. A
tool that turns out to need credentials or spend must be re-registered in the
higher tier before continued use.

## 2. What is allowed without further approval

- Clone, install, build and start upstream runtimes, services, CLIs and APIs.
- Follow an upstream branch or tag instead of pinning a full commit.
- Use the tool's full functionality, not only selected method notes.
- Feed it project-owned inputs, and keep its raw outputs locally.
- Run multiple third-party tools side by side and compare their results.
- Decide, from actual use, whether a tool is worth keeping.

## 3. What remains prohibited

These constraints concern **outputs and authority**, not which tools may run.
They are retained by `docs/OWNER-DECISION-2026-11-09-EFFECT-FIRST.md` because
they are what make results publishable, not because of governance preference.
That later decision **widens output handling**: tool output is no longer
categorically advisory, and the owner may authorise a class of outputs to enter
the candidate-evidence queue directly, provided each is hash-bound and
source-verified before any claim link. The authority boundaries below are
unchanged. See `docs/DOTS-EFFECT-FIRST.md` for the wider dot role.

- No writing `projects/*/state/`, no approving G0–G5, no changing the
  claim-evidence matrix, no fabricating human decisions.
- No registered experiment outside `scripts/experiment_runner.py` with a
  matching approved G3 plan and budget hashes. A tool run is exploration or
  tooling, never a registered result.
- No forging or bypassing output provenance; no third-party tool becomes the
  persistent writer of a manuscript-bound artifact.
- No repository secrets in files, URLs, argv or logs; no upload of raw research
  data; no bypass of access controls.
- No changes to writer/critic model-family separation, cumulative budget, or
  gateway model-identity checks; no automatic manuscript submission.
- Popularity, star count and upstream documentation are not evidence. Every
  scientific claim still needs primary-source verification and an evidence link.

## 4. Minimum registration

Free integration keeps a small, cheap record so a run remains reproducible:

```
python3 scripts/third_party_runtime.py register \
  --id deer-flow \
  --repo https://github.com/bytedance/deer-flow \
  --ref main \
  --tier network-no-credentials \
  --license MIT \
  --capability literature-search \
  --note "Owner-authorized free integration"
```

Required fields: `id`, `repository`, `ref`, `license`, `access_date`,
`risk_tier`. Everything else is optional. Per-file source review, an allowlist
of components, a native rewrite, a `selection_note`, and a full commit SHA are
**not** required for new registrations.

## 5. Running a tool and using its output

```
python3 scripts/third_party_runtime.py run --id deer-flow -- \
  python3 /path/to/deer-flow/cli.py --query "..."
python3 scripts/third_party_runtime.py run --id deer-flow --execute -- \
  python3 /path/to/deer-flow/cli.py --query "..."
python3 scripts/third_party_runtime.py bind-output --id deer-flow \
  --file reports/third-party/deer-flow/result.json
python3 scripts/third_party_runtime.py promote --id deer-flow \
  --receipt reports/third-party/receipts/<receipt>.json --authorized-by Owner
python3 scripts/third_party_runtime.py verify
```

`run` is a dry run unless `--execute` is given. Execution uses no shell, a
filtered environment with no repository credentials, a bounded timeout, and
writes a receipt containing argv, exit code, and stdout/stderr hashes. The
receipt states `advisory_only: true`, `gate_authority: false`, and
`registered_experiment: false` by default. `bind-output` hash-binds a local
output file without interpreting it. Under the effect-first decision the owner
may authorise a class of hash-bound outputs as **candidate evidence**; that
changes their queue, not their need for source verification before any claim link.

To promote any output into a scientific claim, follow the existing path:
primary-source verification, an approved G3 plan, execution through
`experiment_runner.py`, and a link in `claim-evidence.csv`. A tool receipt is
candidate material, never a substitute for that chain.

Authorization and deployment are separate fields. `register` sets
`deployment_authorized: true` and leaves `standalone_runtime_deployed: false`
until someone records the observed fact:

```
python3 scripts/third_party_runtime.py mark-deployed --id deer-flow --deployed true
```

## 6. Reality check: "high-star" does not mean "directly callable"

`docs/RESEARCH-AUTOMATION-TOOLKIT.md` records what each adapted upstream still
needs. Most of the well-known projects are applications, not importable
libraries:

| Tool | Additional requirement to actually run it |
|---|---|
| deer-flow | Backend, frontend, sandbox and model configuration |
| gpt-researcher | Python service plus search/model/embedding configuration |
| RD-Agent | Python, Docker, a research scenario and model service |
| AutoResearchClaw | Python application and model service |
| MiroThinker | Model service and tool framework; model weights not included |
| pi-autoresearch | Pi extension and proprietary tooling |
| PaperBanana | Full Python project plus image/model services |
| aipoch/open-science | Electron/CLI, notebooks and artifact interfaces |
| EvoScientist | Standalone Python agent and model configuration |
| synthetic-sciences/openscience | Bun/TypeScript workbench and compute-job interfaces |
| The AI Scientist V1/V2 | Linux/CUDA, model and full-text services; custom source license with disclosure duties |

By contrast, library-style integrations (`statsmodels`, `ref-verify`,
`paper-qa`, `tooluniverse`, `proselint`) already install and run through the
existing optional-dependency groups. Skill-style packages are plain files.

So the practical consequence of this decision is: you may now supply those
runtimes, dependencies, model endpoints and keys and run them. What the
decision cannot do is make a service-based upstream work without them. Start
with one tool, record its tier and receipts, and confirm it actually runs
before wiring more.

Engineering acceptance is not scientific validity. Freeing tool access raises
tooling capability; it does not by itself improve research conclusions.
