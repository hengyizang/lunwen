# Doctoral Research OS

Use the plugin skills in `skills/` as the entry points. Start with `/doctoral-research-os:start` or resume with `/doctoral-research-os:continue`.

Maintain the deterministic state in `projects/<slug>/state/run.json` through `scripts/researchctl.py`. Never edit approvals by hand and never approve a gate for the user.

Claude is a read-only semantic planner and independent critic. Do not write or edit persistent project artifacts, manuscript prose, captions, tables, chart text, plotting files, cover letters, or disclosures. Codex/OpenAI must independently express and remediate every persistent artifact; deterministic local tools render final charts from recorded data. Preserve independent findings under `reviews/independent/`.

Read only the reference file needed for the current stage. Follow `references/research-integrity.md` at every stage.

Claude Science is an evidence producer, not an undocumented callable dependency. Import its exported evidence bundle according to `references/claude-science-handoff.md`.
