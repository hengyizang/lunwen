# Owner decision: free integration and execution of third-party tools

- **Date:** 2026-11-09
- **Actor:** repository owner
- **Decision ID:** `owner-2026-11-09-third-party-runtime`
- **Status:** active. Supersedes the categorical restrictions below; does not rewrite historical records.

## Decision

The owner authorizes free integration and execution of third-party GitHub tools in
this repository. Starting a standalone upstream runtime, installing its
dependencies, invoking its CLI/API, following an upstream tag or branch, and
using its output as candidate material **no longer require** a per-file review,
a native reimplementation, or a pinned full commit SHA.

The motivation recorded by the owner is that these are widely adopted GitHub
projects whose capabilities should be directly usable rather than reduced to
method notes.

## What is lifted

- The categorical `standalone_runtime_deployed: false` posture for future
  integrations, described in `docs/RESEARCH-AUTOMATION-TOOLKIT.md`.
- "Adapted Codex skills are not deployed upstream services." and "Raw upstream
  launchers remain disabled." in `AGENTS.md`.
- The default expectation that every new upstream must be independently
  reimplemented natively before its capability can be used.
- Mandatory full-commit pinning for newly registered runtimes. A `ref`
  (branch, tag, or commit) plus a recorded access date is sufficient.

## What is explicitly retained

This decision amends **access**, not scientific authority. Rules 1, 2, 5, 9,
10, 11, 14, 16, 17, 18 and 23 of `AGENTS.md` are unchanged. A third-party
runtime may not:

- write stage state, approve a G0–G5 gate, or alter the claim-evidence matrix;
- run a registered experiment outside `scripts/experiment_runner.py` after the
  approved G3 plan and budget hashes match;
- forge or replace output provenance hashes, or become the persistent writer of
  a manuscript-bound artifact;
- receive repository secrets, credentials, or raw research data for upload;
- change writer/critic model-family separation, the cumulative budget, or the
  model-identity checks for third-party gateways;
- auto-submit a manuscript.

Its output is **advisory** until hash-bound, independently verified against
primary sources, and linked to evidence under the existing rules. Popularity,
stars, or upstream self-description are not evidence of scientific validity.

## Records and honesty

- `integrations/upstreams.lock.json` and
  `integrations/research-automation-tools.json` remain **historical reviewed
  snapshots**. Their `enabled_by_default`, `commit`, and
  `standalone_runtime_deployed` fields are factual statements about those
  snapshots and are deliberately **not** rewritten by this decision.
- New free runtimes are registered in the independent
  `integrations/third-party-runtime.json`, which separates
  `deployment_authorized` (a permission) from `standalone_runtime_deployed`
  (an observed fact). Authorization is never recorded as deployment.
- Operating rules: `docs/THIRD-PARTY-RUNTIME-POLICY.md`.
- Tooling: `scripts/third_party_runtime.py`.

## Later decision (same day)

`docs/OWNER-DECISION-2026-11-09-EFFECT-FIRST.md` widens this decision: effect
first rather than governance first, free choice of runtime, dots as research
collaborators rather than only tool hosts, and owner-authorised tool output
entering the candidate-evidence queue directly. The scientific-authority
boundaries recorded above remain.

## Revocation

The owner may tighten or revoke this decision at any time by recording a new
dated decision here and setting `deployment_authorized` to `false` in the
registry. Already archived outputs and receipts are retained under rule 9.
