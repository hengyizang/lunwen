# Upstream components

The local orchestrator is the authority for state, artifacts and human gates. An upstream skill may contribute a bounded method; it cannot approve a gate, change experimental results, or submit a manuscript.

## K-Dense Scientific Agent Skills

Selected because the upstream is cross-agent, MIT-licensed, actively tested, and contains useful generic scientific methods. The repository also contains many biomedical and chemistry skills that are irrelevant to an undecided AI + mechanical/robotics topic, so the first install is deliberately limited to the 14 entries pinned in `integrations/upstreams.lock.json`.

Install the reviewed snapshot for both Claude Code and Codex:

```bash
bash scripts/install-kdense-core.sh --install
```

The installer fetches the exact commit, verifies the resolved SHA and MIT license marker, and copies only the allowlisted skill directories. It does not execute their bundled scripts. Before first use, inspect any script, package requirement, network endpoint, API key request and pricing implication.

Select domain skills only after G1. Examples that may become relevant are `openpiv`, `fluidsim`, `pymoo`, `simpy`, `stable-baselines3`, `modal` or `timesfm-forecasting`; none should be installed merely because its name sounds useful.

## Academic Research Skills

This is a strong optional second implementation for deep research, drafting, revision and multi-perspective review. Its license is CC BY-NC 4.0, so the repository does not copy or silently install it. Confirm that the planned use is non-commercial and that attribution obligations are acceptable, then use Claude Code's plugin manager:

```text
/plugin marketplace add Imbad0202/academic-research-skills
/plugin install academic-research-skills
```

Use it only as an evidence/semantic-planning worker behind the local contracts, not as a competing state machine. Do not export Claude-authored manuscript or chart artifacts into final project paths. The local G1–G5 rules, non-Claude writer, output provenance and independent model-family audit remain authoritative.

## Experiment Agent

The reviewed upstream is also CC BY-NC 4.0. It is not installed in v1 because the local `experiment` skill already defines preregistration, budgets, execution logs, negative-result retention and independent statistical audits. Running two experiment orchestrators would create ambiguous state and duplicate provenance. Reconsider it only after G2 if it adds a capability the local executor lacks and the use satisfies the license.

## proselint

[`amperser/proselint`](https://github.com/amperser/proselint) is an optional
BSD-3-Clause command-line linter for English prose. Version `0.16.0` is the
reviewed integration target, corresponding to Git commit
`a83a6164999803909f69eb3274d783c7070e73c1`. The G5 controller runs it only
when the executable is already installed, only over a temporary plain-text extraction of the active
manuscript, and with `config/proselint-academic.json`. The temporary file is
removed after the local process exits; no manuscript is uploaded.

Its diagnostics are advisory. In particular, the project disables the generic
hedging rule because uncertainty and limitations can be scientifically required.
The built-in hash-bound audit remains the gate authority, and neither tool is an
AI detector or a basis for concealing model assistance.

## Academic writing-pattern sources

The built-in line-level G5 rules in `config/academic-style-rules.json` use a
reviewed academic subset of ideas from three MIT-licensed projects:

- [`conorbronsdon/avoid-ai-writing`](https://github.com/conorbronsdon/avoid-ai-writing)
  contributes the preservation-first review model and a broad taxonomy of
  formulaic prose patterns.
- [`tbhb/vale-ai-tells`](https://github.com/tbhb/vale-ai-tells) contributes
  technical-writing warnings for filler, unsupported certainty, vague
  attribution and repeated structural formulas.
- [`petergyang/no-ai-slop`](https://github.com/petergyang/no-ai-slop) contributes
  high-confidence conversational artifacts, importance puffery and generic
  conclusion patterns.

The repository does not execute their automatic rewriters and does not copy a
general social-media rule set into manuscripts. It records the reviewed commits
in `integrations/upstreams.lock.json`, implements a small academic allowlist
locally, reports the exact line and rule, and lets Codex make evidence-preserving
edits. Numerical results, equations, citations, limitations and required AI-use
disclosures are not targets for stylistic substitution. The audit estimates
neither authorship nor the output of Turnitin, GPTZero or another detector.

## Harper

[`Automattic/harper`](https://github.com/Automattic/harper) is an optional
Apache-2.0 offline English grammar checker. When `harper-cli` is already
available on `PATH` or in the repository `.venv`, `scripts/academic_style.py`
runs it over the same temporary plain-text extraction used for proselint and
normalizes its JSON findings. The temporary text is removed after execution.

Harper is advisory and intentionally not auto-installed: its release and
platform-specific binary must be reviewed before installation. A missing Harper
binary never disables the built-in audit or G5; the dashboard reports its status
separately.

## Update protocol

Do not replace a pinned commit with the latest branch tip automatically. For an update:

1. inspect the upstream diff, license and security workflow;
2. review new scripts, hooks, network domains, dependencies and credential handling;
3. run upstream tests and this repository's checks;
4. update the full commit SHA and review date in the lock file;
5. preserve attribution and document the decision.
