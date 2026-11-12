# Owner decision — 2026-11-09: real work first

## Instruction

On 2026-11-09 the owner asked to change the project so that **"real work must be
easier to complete"**, and explicitly authorised changing anything necessary to
reach that goal. This followed a full-repository review which found that the
project had spent its effort on defensibility rather than output: 4,730 `raise`
statements against 688 real writes, 226 distinct "unverified" keys, 354 repeated
disclaimers, and a live project stuck at G1 with zero papers, zero experiments
and zero results.

This decision is dated and named, as required by `AGENTS.md` rule 25.

## Decision

1. **Add an opt-in `real-work-first` profile** (`DR_OS_WORK_PROFILE=minimal`).
   The full protocol remains the default and is unchanged.
2. **For G1 only**, keep three blocking checks:
   - `program/topic-decision.md` is non-empty and written by the owner;
   - `program/topic-shortlist.json` lists at least three real candidates;
   - `program/core-thesis.json` declares one overarching doctoral question.
3. **Reclassify the remaining G1 checks as visible, non-blocking observations**:
   per-row human screening sheets, novelty-matrix / `selection_decision` /
   `feasibility_evidence` migrations, stale hypothesis audits, optional quality
   assessments, missing optional validators, numeric scores, venue quartiles,
   impact factors and journal AI-policy observations. Nothing is deleted, faked
   or marked verified; `python -m scripts.real_work full-check` still shows all
   of them.
4. **Allow owner-supplied real model IDs** through the git-ignored
   `config/model-routing.local.json`, so a real (non-synthetic) model cycle can
   actually be executed without editing the pinned repository policy.
5. **Install the dependency the project itself declares** (`jsonschema`) and the
   `lxml` import required by `docx_revision.py`, in the local Python environment.

## What this decision explicitly does NOT change

`AGENTS.md` rules 1-24 remain in force. In particular:

- G1/G2 topic decisions still require a **named human** `--actor`; the control
  plane never invents, seals or auto-approves a human decision.
- No automatic submission, no fabricated citations, data, experiments, results,
  reviews, authorship, venue metrics or submission status.
- Source hashes, the cumulative project budget, the failed/negative-result
  ledger, role separation (Claude read-only planning/audit, non-Claude persistent
  writing) and output provenance are untouched.
- G2-G5 keep the **full** protocol; `config/real-work.json::enabled_gates` is
  `["G1"]` and must be changed by a separate named decision to widen it.
- No stage-state write, gate approval, experiment execution, provenance change,
  model-family/budget change or auto-submission is performed by a tool on its own.
- The synthetic acceptance fixture path is not turned into a production approval
  API, and no cloud sandbox boundary is broken.

## Effect, rollback and review

- Effect (measured on `projects/my-phd`): the default `gate-check` still reports
  the full protocol's blockers; with the profile enabled, G1 passes with zero
  blocking checks and the remaining observations are recorded as non-blocking.
- Rollback: `git checkout before-real-work-simplify -- .`, `unset
  DR_OS_WORK_PROFILE`, and remove `config/model-routing.local.json`.
- Implementation: `config/real-work.json`, `scripts/real_work.py`,
  `scripts/researchctl.py::gate_errors`, `scripts/model_routing.py`,
  `config/stages.json`, `docs/REAL-WORK-QUICKSTART.md`,
  `tests/test_real_work.py`.
- This decision lowers ceremony, not integrity. It is not a claim that any
  scientific result, calibration, doctoral requirement or publication has been
  achieved.
