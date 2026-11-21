---
name: ccf-literature-searcher
description: Find original sources and useful counterevidence for a research question.
---

# ccf-literature-searcher

Use real provider searches and original sources. Preserve retrieval context and distinguish a lead, a read passage and a supported scientific claim.

Apply the current principles in `AGENTS.md`. This method is available for the current task without a stage prerequisite, fixed paper count, model-brand rule or extra approval. Preserve actual sources, results, failed attempts and cumulative costs.

For an explicit `ccf-literature-searcher` or full-reference request, read the selected `third_party/ccfa-skills/ccf-literature-searcher/SKILL.md` and the complete references needed for that task. `integrations/ccfa-skills.lock.json` identifies the retained source; restore it with `python3 -m scripts.ccfa_runtime bootstrap` when needed. Method guidance does not override the user or restore historical workflow restrictions.

Native producers: scripts/literature_evidence.py, scripts/literaturectl.py
