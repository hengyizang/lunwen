# Owner decision: maximum flexibility

- **Date:** 2026-11-09
- **Actor:** repository owner
- **Decision ID:** `owner-2026-11-09-maximum-flexibility`
- **Status:** active. Builds on `owner-2026-11-09-effect-first`.

## Decision

The owner restated that **effect comes first and everything must stay flexible**:
which tools are chosen, where they run, which GitHub projects or skills are
called, and in what order. The decision-point mapping, comparison workflow and
adoption ledger introduced earlier in the day were experienced as a new process,
and the owner does not want a process.

Accordingly, all workflow mechanisms are **optional tools, never prerequisites**:

| Previously introduced | Now |
|---|---|
| `docs/TOOL-CAPABILITY-MAP.md` decision-point table | Optional reference. Skip any row, any time. |
| Five levers, "choose tools by decision point" | One possible way to work, not a required first step. |
| `register` → `scaffold` → `wrap` → `compare` → `adopt` → `promote` | Optional commands. Use any one alone, in any order, or none. |
| Same-input comparison, disagreement preservation, adoption ledger | Available when useful; not required before or after a run. |
| "One decision point, 2–3 tools, one real input" | A suggestion, not a limit. |

## What is now explicitly free

- Any GitHub project, any skill (`skills/`, `third_party/`, a WorkBuddy skill,
  or any upstream skill repository), any local or hosted runtime.
- Any environment: Codex Cloud, GitHub Actions, dots cloud computer, paired local
  machine, self-provisioned VM, or this session — mixed freely, switched freely.
- Any order, any duration, with or without registration, a declared decision
  point, an adapter, a comparison, a receipt, or a predefined output location.
- `scripts/third_party_runtime.py free` runs a command directly with no registry
  entry and no licence/tier/decision metadata; `--no-receipt` is available.

## Unchanged

This decision is about **workflow flexibility only**. It does not remove the
scientific-validity rules retained in `AGENTS.md` rules 1-24 and rule 25, and it does not
authorise breaking a cloud sandbox (no root, Docker daemon, WSL, kernel or
privileged driver inside an unprivileged Linux dot VM). Those are external facts,
not workflow constraints. Removing any retained rule still needs a separate
explicit dated owner decision naming it.

## Reversal

Tighten or revoke with a new dated decision. Existing receipts, comparisons and
adoption records remain available if wanted; none are mandatory.
