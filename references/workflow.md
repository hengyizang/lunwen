# Workflow

Current financial policy: [TOTAL-COST-POLICY.md](../docs/TOTAL-COST-POLICY.md).
Calculate costs and enforce configured cumulative project totals only; older
per-paper caps, paid opt-ins, tranche steps and manual billing gates are superseded.

## Human topic decisions

The owner requires human decisions on the doctoral topic and each paper topic.
Other stage decisions are automated and recorded as such. Never label an
automated decision as human. The existing cumulative spending authority, source
rights, evidence checks and experiment seals still apply. Missing evidence or
unsupported checks remain blockers. Software tests alone do not demonstrate a
successful unattended research project or scientific validity.

## Operating model

Use one deterministic control plane and bounded model roles:

1. Python on the selected runner owns stage state, output provenance, gates, hashes and execution authority. In cloud-only mode the runner is GitHub Actions, not the researcher's computer.
2. Claude supplies a read-only semantic plan and may perform internal independent criticism. Its text is stored only in run/audit records, never as a persistent scientific or submission artifact.
3. Codex/OpenAI independently expresses and remediates every persistent text artifact. It uses Claude's ideas as requirements, not wording to copy.
4. Codex writes plotting code/specifications; deterministic tools on the runner render result-bearing figures from recorded data and experiment outputs. A separately disclosed GPT Image conceptual illustration can supplement but never replace a data figure.
5. The human selects the doctoral topic at G1 and every paper topic at G2. Other stage decisions use recorded automated checks and independent model audits. Authorship and external ethics or submission obligations still apply.

Do not ask multiple agents to produce one blended answer without preserving their separate evidence and disagreements. Store unresolved disagreements in `reviews/decision-log.md`.

## Stage loop

The native [scientific reasoning contract](../docs/SCIENTIFIC-REASONING.md)
is included in the existing stage/role method prompts. Source-bound question
value and discriminating decisions are checked at G1; empirical G3/G4 connects
critical tests to every actual comparison. Existing G5 reviews challenge the
supported contribution and conclusion scope. No extra paid role is introduced.

The [evidence-led narrative guide](../docs/EVIDENCE-LED-NARRATIVE.md) prioritizes
the strongest supported contribution, relevant comparisons and decisive evidence.
Existing paper contracts, claim records and argument plans hold the evolving
story. Scientific reviews remain internal; manuscript emphasis follows evidence
and actual analysis phase while preserving registered outcomes and frozen plans.

Use the [dedicated study routes](../docs/SCIENTIFIC-STUDY-ROUTES.md) for actual
Meta/formal-theory identities and separate reviewer-requested experiments.
These routes keep the shared evidence, budget, writer/critic and topic decisions.

After the existing six-paper G2 architecture and each paper's recorded human
topic decision, the native `advance` initializes independent execution for new
unexecuted portfolios. P01 completes G3 → G4 → G5 before P02 enters G3; a paper does not
wait for the other five experiment designs or results. Scientific topic scope and
the cumulative project totals remain shared. Protocols, budget declarations and
attempt ledgers and source-bound dataset snapshots use `experiments/papers/Pxx/`; claim records use
`claims/papers/Pxx/claim-evidence.csv`. The ordinary API/CLI prompts supply the exact
current paths. A copied budget declaration creates no additional allowance or
per-paper cap. All papers and follow-ups remain charged to the original totals.
Already executed/frozen legacy batch protocols are not silently rewritten.

Exploration may retain `status: in_progress`, unsaturated searches, untested
assumptions and provisional candidates. `research_quality.py novelty-check` checks
that record without claiming a topic decision; `--for-gate` applies the final G1
requirements. A reopened search retains all historical rounds, affected claim
IDs and the next actual queries. Candidate screening can use a focused decision
or narrative dispositions without manufactured numeric ratings.

Scientific exploration uses the same G3/G4 state and executor. An explicit
`plan.json.research_phase: exploratory` declares `exploration` with the unknown,
discriminating test, continue/revise/stop conditions, claim limit and prior outcome
exposure. It retains rights, source/input hashes, the frozen run plan, independent
current independent critique and the cumulative total; it need not invent a final power
analysis or complete confirmatory baseline suite. Checked G4 archives every actual
attempt and returns that paper to G3. Confirmatory work uses a separate frozen
protocol, new run/output identities and source-bound prior-exploration records.
Exploratory outcomes cannot supply confirmatory claims or pass final G5.

Writing starts in `scientific`: refine evidence, claims, comparisons and argument
under source/claim integrity checks and the current independent critique. The
frozen paper contract may declare an initial preference; existing
`state.writing_phases` stores the current phase. Passing scientific checks and
the reviewed decision lets the controller enter `submission`; writers do not
edit frozen contracts to change phase. Final submission preparation adds the
three-view panel and the B checks below. Scientific drafts and protocol-only
supplemental verdicts cannot approve the parent G5.

Checks have three levels, shared by `gate-check`, `ready`, `advance` and packaging:

- **A — scientific integrity:** real source/version-bound data, complete registered
  results, source/claim/citation/numeric consistency, frozen protocols, preserved
  adverse findings, actual runner provenance and existing writer permissions.
  Missing or false evidence blocks the affected work.
  Final G5 citation support uses the current selected `claim_evidence` task,
  lawful original full text and protected source judgments covering the actual
  manuscript's distinct citation uses and complete local assertion scopes,
  including different claims citing the same work. Missing or insufficient support stays pending;
  abstract-only `ref-verify` reports cannot replace this check. Drafts may retain
  unfinished checks, while actual contradictions remain visible and blocking.
- **B — submission preparation:** the actual selected venue, source-bound ranking
  where known, article type, reporting requirements, imported template,
  successful render/export and final panel. The machine approval binds these
  sources and implementation hashes. Reuse the checked unchanged snapshot;
  changed content, sources or implementation require recomputation. There is no
  arbitrary 120/180-day expiry, ranking floor or journal AI-policy gate.
- **C — observations:** numeric quality scores, editorial CFH/H/AD tables,
  style/language/Unicode/watermark hints, figure-layout preferences, concern cards,
  change-ledger completeness and per-stage audit administration. Expose their
  warnings and uncertainty; do not create another gate or paid repair merely to
  make these lists empty. Actual loss of evidence, a false number or a removed
  interpretation-changing negative finding remains A regardless of the tool that discovered it.

C report refreshes, edit-ledger completeness and style/voice preferences do not
revoke an unchanged scientific decision or invalidate its independent review.
The shared fingerprints still bind actual manuscript/package content, scientific
increment specifications and sources, protected reviews and preserved cleanup
history. Packaging reruns the same paper-level A checks as native G5; final B
preparation remains reusable only for its unchanged scientific/source snapshot.

Internal scientific review can request a separate `Ixxx` follow-up through the
same supplemental executor used for external `Rxxx` reviewer work. A protected
actual independent finding supplies its trigger. The existing model cycle
reviews the exact child protocol, and checked automatic records seal it and
validate actual results. A protocol-only verdict cannot pass parent G5 or verify
any outcome. Original G3 inputs, prior exposure, adverse results, source rights,
model identities and the cumulative spending authority remain unchanged.

For the current stage:

1. Run `python3 scripts/researchctl.py status --project <slug> --json`, or use `python3 scripts/autopilot.py plan --project <slug>`.
2. Read the matching stage contract in `references/stage-contracts.md`.
3. Ask Claude for a non-publishable semantic plan; keep it in the protected run record.
4. Ask Codex/OpenAI to write only the current task's required artifacts. Run
   deterministic source/claim/citation/numeric checks on that snapshot; retain
   originals and scientific ancestry when applying optional editorial changes.
5. Ask a different model family for one fresh independent critique without the
   desired verdict or earlier opinions. This completes the ordinary three-call
   cycle: planner → writer → critic.
6. Repair only an actual actionable finding, retain the itemized response and
   obtain a fresh review of the changed scientific sources. A clean critique
   ends the cycle without a synthetic second round. Before final submission,
   run the panel described below; retain real external comments independently.
7. Run `gate-check`, then `ready`.
8. At G1 present the doctoral topic dossier; at G2 present each paper topic for its own recorded decision. Stop only for those topic decisions. A changed topic or mapping invalidates the affected approval.
9. Record actual topic decisions with `approve` (G2 also requires `--paper Pxx`). The serialized continuation runs `ready` and `advance` when their checks pass. G0/G3/G4/G5 receive explicit machine decision records. [Cloud topic controls](../docs/CLOUD-HUMAN-CONTROLS.md) authenticate human topic decisions; scheduled work never supplies a human identity or increases the spending ceiling.

`scripts/autopilot.py` implements this loop with Claude read-only tool permissions, Codex workspace writing, protected control/audit files, output-provenance hashes, bounded non-interactive CLI calls, local checkpoints and output limits. It never supplies a human `approve`. In independent execution G3–G5 operate on `state.active_paper`; a checked automatic `advance` marks that paper ready and selects the next paper at G3 until all configured papers are complete.

Each G1-G5 model cycle appends its current decision to the existing
`program/research-notebook.json`. The question states the consequential unknown;
the decision binds this `cycle_id`, stage/paper, discriminating test, outcome,
method/claim decision, rationale, next action, actual `evidence_ids`, failure
condition and stop rule. Outcomes include `pending`, `unchanged`, `changed`,
`failed` and `stopped`. Pending/unchanged may lack evidence only with explicit
`missing_evidence` and the next action; no invented breakthrough is required.
The current independent critique reviews the notebook decision. G0 is exempt. Continuation
shows the source/review-bound decision alongside control progress and actual
attempts; fewer errors, new receipts or a recorded decision alone do not
establish scientific validity or an improved paper.

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
- Keep existing Q1/Q2 ambitions as planning observations, never scientific or
  packaging thresholds. Use actual audience/scope/article-type/desk-rejection
  evidence for venue fit; ranking missing from lawful sources stays unknown.
  A journal rank cannot establish novelty or scientific validity.

## Independent critique and final panel

Ordinary critics inspect the current scientific packet, evidence and constraints.
Preserve fatal/major/minor findings, missing evidence, alternative explanations,
statistical/leakage/reproducibility risks and specific resolution tests. Distinguish
a demonstrated problem from a question or optional extension. The non-Claude
writer records addressed, maintained or disagreed dispositions with evidence.
An opinion or model consensus is not independent scientific validation.

At the final submission checkpoint, `papers/Pxx/reviews/panel-inputs.json` binds
three different scientific views: domain sees Methods/Results/numeric tables;
editorial sees title/abstract/Figure 1/headline claim; statistics sees the frozen
protocol/numeric tables/figure values. The controller routes three critics from
different model families, each different from the writer, and freezes each view
and response before synthesis. They do not see other reviews or preferred
verdicts. Preserve stable finding/claim/evidence IDs, uncertainty and disagreements;
never vote, average verdicts or estimate acceptance odds. A source change requires
fresh review; an unchanged frozen panel is reused. Actual current routes and
charges remain governed by existing identity/budget controls.

Use full lawful primary passages for material cited claims and retain
`supports`, `contradicts` or `insufficient` judgments with their exact anchors.
The deterministic 15% sample requires real independent labels before agreement
can be reported. The 0.85 agreement target and a 20–30-paper public-review anchor
set are empirical validation work, not results supplied by these software tests.
Source-bound citation-extraction differences and failed-idea memory retain
unknowns and contrary evidence. See [the coverage matrix](../config/requirements-traceability.json).

## Completion boundary

`submission-ready` means every configured paper passed its own G5 checks and recorded machine decision after the actual G1/G2 topic decisions. It does not mean submitted, accepted, publishable, ethically cleared, or guaranteed to meet a degree requirement.

After a real submission, use [Reviewer rounds](../docs/REVIEWER-ROUNDS.md) to import
the original decision and comments through a hash-bound owner decision. Each real
round retains its original submitted manuscript and receipt; an old G5 approval
cannot approve the changed paper. The same writer, independent critics, source
checks, cloud budgets and automatic G5 controls apply again. A request for additional
experiments is a scientific planning requirement, not execution permission; the
original confirmatory plan must never be retrospectively re-frozen.

The workflow adds no automatic AI-generated branding and does not require a
journal AI-policy assessment as a gate. AI-use statements are optional author-editable text; internal assistance/provenance remains truthful. Complete experiment backups live under `experiments/archive/` and are excluded from default writing snapshots. Raw logs need not be inserted into a manuscript; material evidence belongs in the manuscript or supplements. Actual
external author obligations remain outside the automated workflow.
[Configured statistical watermark detection](../docs/STATISTICAL-WATERMARKS.md)
is separate from character cleaning: an unknown scheme remains unknown, and a
negative result for one configured detector never certifies universal absence.
