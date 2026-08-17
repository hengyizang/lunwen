# Doctoral Research OS

Use the plugin skills in `skills/` as the entry points. Start with `/doctoral-research-os:start` or resume with `/doctoral-research-os:continue`.

Maintain the deterministic state in `projects/<slug>/state/run.json` through `scripts/researchctl.py`. Never edit approvals by hand and never approve a gate for the user.

Delegate high-volume work to the focused agents in `agents/`. Keep the main conversation responsible for integration and decisions. At G1–G5, ask the Codex MCP server for an independent audit and preserve its findings under the project review directory.

Read only the reference file needed for the current stage. Follow `references/research-integrity.md` at every stage.

Claude Science is an evidence producer, not an undocumented callable dependency. Import its exported evidence bundle according to `references/claude-science-handoff.md`.

