# Workflow

## Operating model

Use one orchestrator and several bounded workers:

1. Claude Code owns stage state, integrates artifacts, presents decisions, and stops at gates.
2. Claude Science or a literature worker produces traceable evidence bundles. It does not decide the topic alone.
3. Focused Claude subagents handle topic intelligence, data stewardship, experiment design, statistics, review, and venue adaptation.
4. Codex acts as the independent model-family critic for code, statistics, leakage, reproducibility, and claim support.
5. The human approves G0–G5 and owns authorship, scientific judgment, ethics, venue choice, and submission.

Do not ask multiple agents to produce one blended answer without preserving their separate evidence and disagreements. Store unresolved disagreements in `reviews/decision-log.md`.

## Stage loop

For the current stage:

1. Run `python3 scripts/researchctl.py status --project <slug> --json`.
2. Read the matching stage contract in `references/stage-contracts.md`.
3. Gather evidence and write only the required artifacts.
4. Ask Codex to audit the artifact without revealing the preferred verdict. Save the raw findings.
5. Resolve findings explicitly; do not silently discard adverse feedback.
6. Run `gate-check`, then `ready`.
7. Present a concise gate dossier to the human and stop.
8. After explicit approval, record it with `approve` and use `advance`.

## Evidence rules

- Prefer primary literature, official datasets, official degree regulations, official employer/job data, official journal pages, and official software documentation.
- Record query, database, date range, filters, result count, inclusion/exclusion reason, and access date.
- A DOI or URL is not proof that a source supports a claim. Capture the supporting location and a short paraphrase.
- Separate observed fact, source claim, model inference, forecast, and recommendation.
- Re-check temporally unstable facts at the gate where they matter.

## Actor-critic protocol

Give the critic the artifact, evidence bundle, rubric, and constraints. Do not give it the desired answer. Require:

- fatal flaws;
- major and minor findings;
- missing evidence;
- alternative explanations;
- leakage/statistical/reproducibility risks;
- a verdict: block, revise, or pass with conditions.

The authoring agent must respond item by item. A different model agreeing is supporting evidence, not validation by itself.

## Completion boundary

`submission-ready` means the package passed local checks and G5. It does not mean accepted, publishable, ethically cleared, or guaranteed to meet a degree requirement.

