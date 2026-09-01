# Workflow

## Operating model

Use one deterministic control plane and bounded model roles:

1. Local Python owns stage state, output provenance, gates, hashes and execution authority.
2. Claude supplies a read-only semantic plan and may perform internal independent criticism. Its text is stored only in run/audit records, never as a persistent scientific or submission artifact.
3. Codex/OpenAI independently expresses and remediates every persistent text artifact. It uses Claude's ideas as requirements, not wording to copy.
4. Codex writes plotting code/specifications; deterministic local tools render final figures from recorded data and experiment outputs.
5. The human approves G0–G5 and owns authorship, scientific judgment, ethics, venue choice, and submission.

Do not ask multiple agents to produce one blended answer without preserving their separate evidence and disagreements. Store unresolved disagreements in `reviews/decision-log.md`.

## Stage loop

For the current stage:

1. Run `python3 scripts/researchctl.py status --project <slug> --json`, or use `python3 scripts/autopilot.py plan --project <slug>`.
2. Read the matching stage contract in `references/stage-contracts.md`.
3. Ask Claude for a non-publishable semantic plan; keep it in the protected run record.
4. Ask Codex/OpenAI to write only the required artifacts in independent wording.
5. Ask a model family different from the writer to audit the artifacts without revealing the preferred verdict. Save the schema-bound initial findings.
6. Ask Codex/OpenAI to resolve findings explicitly; do not silently discard adverse feedback, then request a fresh independent audit.
7. Run `gate-check`, then `ready`.
8. Present a concise gate dossier to the human and stop.
9. After explicit approval, record it with `approve`; `autopilot.py resume` may then advance and run the next stage.

`scripts/autopilot.py` implements this loop with Claude read-only tool permissions, Codex workspace writing, protected control/audit files, output-provenance hashes, bounded non-interactive CLI calls, local checkpoints and output limits. It never invokes `approve`. At G5 it works only on `state.active_paper`; an approved `advance` marks that paper ready and selects the next paper until all configured papers are complete.

## Evidence rules

- Prefer primary literature, official datasets, official degree regulations, official employer/job data, official journal pages, and official software documentation.
- Record query, database, date range, filters, result count, inclusion/exclusion reason, and access date.
- A DOI or URL is not proof that a source supports a claim. Capture the supporting location and a short paraphrase.
- Separate observed fact, source claim, model inference, forecast, and recommendation.
- Re-check temporally unstable facts at the gate where they matter.
- Treat current JCR Q1 SCI/SCIE as the required venue target.
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
