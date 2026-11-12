# Owner decision: effect-first operation

- **Date:** 2026-11-09
- **Actor:** repository owner
- **Decision ID:** `owner-2026-11-09-effect-first`
- **Status:** active. Builds on `owner-2026-11-09-third-party-runtime`.

## Stated goal

The owner wants **effect first, not governance first**: maximise doctoral-topic
innovation and value, novelty of results, manuscript quality and the calibre of
target journals, with as few constraints as possible. Runtime choices should
serve that goal, including giving OpenAI dots a substantially larger role and
installing whatever its cloud computer can support.

## What is lifted

1. **Free choice of runtime.** Codex Cloud, GitHub Actions, dots cloud computers,
   self-provisioned VMs and paired local machines may be combined freely. No
   case-by-case justification, per-file review, default opt-in, mandatory native
   reimplementation, or documentation-reading step may block work.
2. **dots becomes a research collaborator, not just a tool host.** It may run
   literature and counter-evidence sweeps, generate and stress-test novelty
   candidates, iterate experiment code, refine figures and prose, match target
   venues, and prepare submission materials. It may install any **user-space**
   dependency, run long-lived background work, and host localhost services on
   its cloud computer.
3. **Tool output is no longer categorically advisory.** The owner may authorise a
   class of tool outputs to enter the **candidate-evidence queue** directly, as
   long as each output is hash-bound and source-verified before any claim link.
   This removes a round-trip without weakening the claim-evidence chain.
4. **Automate the rest.** Non-G1/G2 stage decisions should proceed on recorded
   automated checks wherever evidence permits. Formalities are observations,
   not blockers.
5. **Pursue stronger venues actively.** Higher-impact targets should drive
   stronger evidence and writing standards. Q1/Q2/IF thresholds and journal
   AI-policy checks remain non-gating observations, and ranking evidence must
   stay source-bound — these are external facts, not internal friction.

## What is deliberately retained, and why it serves the goal

These are **not** governance preferences. They are the mechanisms that make a
result publishable, and removing them would lower the chance of acceptance at a
strong journal rather than raise it.

| Retained | What it actually buys you |
|---|---|
| Rule 1 — no invented citations, data, results, reviews, author contributions, journal metrics or submission status | A single fabricated item is a retraction or degree-integrity issue. No venue tier is worth that. |
| Rules 2, 8, 9 — claims bound to evidence, pre-registration, complete outcomes including failures and negative results | This is the substance of a novelty argument and reproducibility. Reviewers at strong venues ask exactly this. |
| Rule 17 — author and independent critic from different model families | Quality comes from a challenge that can disagree, not from self-confirmation. |
| Rules 3, 4, 16 — current primary sources, no confusion of ranking systems, model-identity checks | Publisher and gateway facts. Not negotiable by editing a repo. |
| Rule 11 — no automatic submission | Journal portals require a real account and human confirmation; G5 still produces a complete package for the author. |
| Rules 5, 24 — human G1/G2 topic decisions | The owner is the decision-maker and may decide at any moment; this is responsibility, not a system blocking them. |
| Rules 6, 7, 23 — secrets, raw data, access controls, cumulative budget | Security and spending facts. Circumventing them risks the account, the data and the project. |

The assistant did **not** unilaterally delete these. If the owner wants any of
them removed, that needs a separate explicit dated decision naming the rule.

## What cannot be solved by editing repository files

- **Docker on a dot cloud computer**: the environment is an unprivileged Debian
  13 workspace (no sudo, no Linux capabilities, read-only system directories,
  Kata VM + bubblewrap). Docker binaries may exist but cannot reach a host
  socket, and rootless Docker lacks the required privileges. Installing a daemon
  would require breaking the platform sandbox.
- **WSL on a dot cloud computer**: WSL is a Windows host feature; the dot runs a
  Linux VM, so the concept does not apply.
- **GPU / inbound ports / privileged kernel access on dots or standard Actions
  runners**: not provided. GPU belongs to paid larger runners or your own VM.

Trying to break these sandboxes is a platform-boundary and terms-of-service
issue, not a repository-policy issue. This decision does not authorise it.
Equivalent, compliant arrangements are in `docs/DOTS-EFFECT-FIRST.md`.

## Reversal

Any further relaxation needs a new dated owner decision. Any tightening can be
recorded the same way. Historical records, receipts and archived outcomes are
retained under rule 9.
