# Workflow

## Operating model

Use one deterministic control plane and bounded model roles:

1. Python on the selected runner owns stage state, output provenance, gates, hashes and execution authority. In cloud-only mode the runner is GitHub Actions, not the researcher's computer.
2. Claude supplies a read-only semantic plan and may perform internal independent criticism. Its text is stored only in run/audit records, never as a persistent scientific or submission artifact.
3. Codex/OpenAI independently expresses and remediates every persistent text artifact. It uses Claude's ideas as requirements, not wording to copy.
4. Codex writes plotting code/specifications; deterministic tools on the runner render result-bearing figures from recorded data and experiment outputs. A separately disclosed GPT Image conceptual illustration can supplement but never replace a data figure.
5. The human approves G0–G5 and owns authorship, scientific judgment, ethics, venue choice, and submission.

Do not ask multiple agents to produce one blended answer without preserving their separate evidence and disagreements. Store unresolved disagreements in `reviews/decision-log.md`.

## Stage loop

The native [scientific reasoning contract](../docs/SCIENTIFIC-REASONING.md)
is included in the existing stage/role method prompts. Source-bound question
value and discriminating decisions are checked at G1; empirical G3/G4 connects
critical tests to every actual comparison. Existing G5 reviews challenge the
supported contribution and conclusion scope. No extra paid role is introduced.

Use the [dedicated study routes](../docs/SCIENTIFIC-STUDY-ROUTES.md) for actual
Meta/formal-theory identities and separate reviewer-requested experiments.
These routes keep the shared evidence, budget, writer/critic and human gates.

For the current stage:

1. Run `python3 scripts/researchctl.py status --project <slug> --json`, or use `python3 scripts/autopilot.py plan --project <slug>`.
2. Read the matching stage contract in `references/stage-contracts.md`.
3. Ask Claude for a non-publishable semantic plan; keep it in the protected run record.
4. Ask Codex/OpenAI to write only the required artifacts in independent wording.
   At G5, run the deterministic academic-style audit after writing and again
   after remediation; use it to improve authentic academic expression. Mandatory
   automatic Unicode hygiene runs before builders and scans the resulting text
   after each pass; preserved originals, protected spans, source ancestry and
   remaining findings are covered by [the hygiene contract](../docs/MANUSCRIPT-HYGIENE.md).
   A clean character scan cannot establish statistical-watermark absence. Optional
   user-supplied detector feedback stays outside the scientific gate and never
   removes disclosure. Run citation identity, DOI-bound abstract
   claim, commitment-trace and revision-integrity checks against the final snapshot.
5. Ask a model family different from the writer to audit the artifacts without revealing the preferred verdict. Save the schema-bound initial findings.
6. Ask Codex/OpenAI to resolve findings explicitly; do not silently discard adverse feedback, then request a fresh independent audit.
7. Run `gate-check`, then `ready`.
8. Present a concise gate dossier to the human and stop.
9. After explicit approval, record it with `approve`; `autopilot.py resume` may then advance and run the next stage. Cloud-only projects use separate hash-bound owner issues for `ready`, `approve` and `advance`, as described in [Cloud human review controls](../docs/CLOUD-HUMAN-CONTROLS.md); a scheduled continuation never supplies the human decision.

`scripts/autopilot.py` implements this loop with Claude read-only tool permissions, Codex workspace writing, protected control/audit files, output-provenance hashes, bounded non-interactive CLI calls, local checkpoints and output limits. It never invokes `approve`. At G5 it works only on `state.active_paper`; an approved `advance` marks that paper ready and selects the next paper until all configured papers are complete.

## Evidence rules

Apply the [original-research-first portfolio policy](../docs/ORIGINAL-RESEARCH-POLICY.md).
Prefer primary original research for every paper. Narrative reviews and
literature-summary-only papers do not fulfill the portfolio. A substantive
secondary quantitative study needs a new question, complete analysis protocol,
actual executed analyses and current official evidence that the target venue
accepts that design in its research-article category. Meta analysis is a method,
not permission to rename a Review, hide secondary methods or waive scientific
checks. Keep each paper's type unassigned until topic/material assessment, then
create research-identity.json before G2 approval. Journal classification never
establishes degree eligibility; human scientific and institutional review remain.

- Prefer primary literature, official datasets, official degree regulations, official employer/job data, official journal pages, and official software documentation.
- Record query, database, date range, filters, result count, inclusion/exclusion reason, and access date.
- A DOI or URL is not proof that a source supports a claim. Capture the supporting location and a short paraphrase.
- Separate observed fact, source claim, model inference, forecast, and recommendation.
- Re-check temporally unstable facts at the gate where they matter.
- Treat at least three of six papers as current JCR Q1 SCI/SCIE targets and
  every remaining paper as at least current JCR Q2 SCI/SCIE. Apply identical
  scientific-quality gates to both groups.
  A quartile is a category/year journal rank, not proof that an experiment meets
  a scientific standard; apply `references/doctoral-q1-readiness.md` separately.

## Actor-critic protocol

Give the critic the artifact, evidence bundle, rubric, and constraints. Do not give it the desired answer. Require:

- fatal flaws;
- major and minor findings;
- missing evidence;
- alternative explanations;
- leakage/statistical/reproducibility risks;
- a verdict: block, revise, or pass with conditions.

The non-Claude writer must respond item by item. A different model agreeing is supporting evidence, not validation by itself. The writer and critic must be different model families.

## Completion boundary

`submission-ready` means every configured paper passed its own G5 checks and human approval. It does not mean submitted, accepted, publishable, ethically cleared, or guaranteed to meet a degree requirement.

After a real submission, use [Reviewer rounds](../docs/REVIEWER-ROUNDS.md) to import
the original decision and comments through a hash-bound owner decision. Each real
round retains its original submitted manuscript and receipt; an old G5 approval
cannot approve the changed paper. The same writer, independent critics, source
checks, cloud budgets and human G5 controls apply again. A request for additional
experiments is a scientific planning requirement, not execution permission; the
original confirmatory plan must never be retrospectively re-frozen.

The final paper receives no automatic AI-generated branding. Its truthful internal
use record and actual upload locations are checked against the current official
[journal disclosure policy](../docs/PUBLICATION-DISCLOSURE.md). Required statements
remain. [Configured statistical watermark detection](../docs/STATISTICAL-WATERMARKS.md)
is separate from character cleaning: an unknown scheme remains unknown, and a
negative result for one configured detector never certifies universal absence.
