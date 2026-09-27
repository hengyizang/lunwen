---
name: paper-audit
description: Check located paper facts, theory-to-measurement validity, title/abstract/question/results/conclusion alignment, paragraph argument flow, and terminology/acronym consistency.
---

# Paper audit

Read the active paper contract, claim-evidence table, results and full manuscript. Build `schemas/paper-facts.schema.json`-compatible `reviews/paper-facts.json`: exact source path/hash and page/table/row for each fact; each material claim's canonical wording, allowed inference, actual claim strength, result status and five section anchors; construct→definition→operationalization→item→coding→analysis→evidence→validity-risk chains; paragraph role/evidence/inference/transition; terminology/acronym glossary; and every mathematical symbol's canonical token, definition, first use and unit. Use `ignored_symbols` only for deliberate mathematical constants or syntax, never to hide an undefined variable.

Run `scripts/manuscript_audit.py --project <slug> --paper <Pxx> --manuscript <path> --spec <path> --output <path>`. It requires anchors to occur in their declared title, abstract, research-question/introduction, results and conclusion regions and blocks claim strength above the allowed inference. G5 recomputes and hash-checks this report. Treat lexical checks as a first pass, then have independent scientific and writing reviewers judge whether the inference is warranted. Prioritize a small repair plan with owners and verification criteria, without suppressing unfavorable results.

For a user-requested detector-feedback pass, run `scripts/detector_feedback.py --prepare` on a hash-bound external baseline score first. It produces local line-level language findings and an evidence-preserving editing brief. Have GPT/Codex revise only where precision, natural flow and argument structure improve, then supply a hash-bound after score and run the before/after comparison. A lower score can be a secondary signal, never a substitute for scientific integrity, human authorship judgment or required disclosure. Do not accept numerical, citation or claim-strength drift without the existing named authorization.
