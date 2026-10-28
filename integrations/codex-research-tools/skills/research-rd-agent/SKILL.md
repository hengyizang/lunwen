---
name: research-rd-agent
description: Use RD-Agent's hypothesis-experiment-feedback method to plan a bounded research iteration or recover useful lessons from actual experiment receipts in lunwen.
---

# RD-Agent research iteration

Codex adaptation of [microsoft/RD-Agent](https://github.com/microsoft/RD-Agent/tree/484776c211e4fbbeef03e0ec00d6bbee7362a4f4), pinned on 2026-10-28. This entry supplies the workflow below; the separate Python/Docker agent runtime and model clients are not deployed by this skill.

Find the user-selected lunwen checkout. Read `AGENTS.md`, `references/workflow.md`, the current stage contract and `docs/EXPERIMENT-EVIDENCE.md`. Research scripts, dependencies and experiments execute on the existing GitHub Actions runner.

1. Identify the paper, registered hypothesis, development or confirmatory phase, approved plan and original run IDs. Missing inputs mean prepare a proposal only.
2. Build a hypothesis-to-feedback chain: mechanism → discriminating observable → original run/output location → observed feedback → proposed action. Separate measurement, interpretation and scientific judgment.
3. Inspect relevant earlier failures before suggesting another attempt. Compare data/split, code, environment, configuration and evidence hashes. Reuse a lesson only when its conditions still apply; explain which changed assumption justifies revisiting a failed idea.
4. Propose one distinguishable next iteration, its expected information, correctness checks, resource ceiling and stop condition. Explain what uncertainty it resolves beyond improving a leaderboard score.
5. Use the approved `scripts/experiment_runner.py` route for actual execution. Preserve successful, failed and unfavorable attempts. A proposal cannot approve G3, change frozen evaluation or authorize model calls.

Return an evidence-linked iteration table and next action. Missing receipts remain missing; an agent's positive feedback is not a verified result. Preserve the one doctoral question and paper independence.

For a source-bound cloud task packet use `docs/RESEARCH-AUTOMATION-TOOLKIT.md`, operation `research_toolkit`, tool ID `rd-agent`. The optional `RESEARCH_TOOLKIT_PACKET=<project-relativepath>` selects only the requested guidance for the existing model cycle.

## Pinned source

Canonical staged source: `D:\ad\codex\research-automation\sources\rd-agent`. Verify its source manifest before relying on local bytes, otherwise use the pinned links:

- [proposal.py](https://github.com/microsoft/RD-Agent/blob/484776c211e4fbbeef03e0ec00d6bbee7362a4f4/rdagent/core/proposal.py): hypotheses, experiments and feedback.
- [evolving_framework.py](https://github.com/microsoft/RD-Agent/blob/484776c211e4fbbeef03e0ec00d6bbee7362a4f4/rdagent/core/evolving_framework.py): learning from previous attempts.

Upstream is MIT licensed; retain its notice when copying components. Finance/Kaggle defaults do not select our topic, and upstream OpenAI/LiteLLM clients do not inherit lunwen's budget authority.
