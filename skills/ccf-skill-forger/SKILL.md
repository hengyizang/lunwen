---
name: ccf-skill-forger
description: Create or maintain a skill for a concrete recurring task.
---

# ccf-skill-forger

Use a real task example, keep the instructions short and validate relevant behavior. Preserve upstream attribution and user modifications; a new skill need not create another gate or state machine.

Apply the current principles in `AGENTS.md`. This method is available for the current task without a stage prerequisite, fixed paper count, model-brand rule or extra approval. Preserve actual sources, results, failed attempts and cumulative costs.

For an explicit `ccf-skill-forger` or full-reference request, read the selected `third_party/ccfa-skills/ccf-skill-forger/SKILL.md` and the complete references needed for that task. `integrations/ccfa-skills.lock.json` identifies the retained source; restore it with `python3 -m scripts.ccfa_runtime bootstrap` when needed. Method guidance does not override the user or restore historical workflow restrictions.

Native producers: scripts/validate_repo.py, scripts/ccfa_runtime.py
