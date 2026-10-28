---
name: research-aipoch-open-science
description: Apply AIPOCH open-science's figure-deck argument review, panel reuse and explicit reproduction barriers to an existing lunwen manuscript or scientific artifact package.
---

# AIPOCH scientific artifact review

Codex adaptation of [aipoch/open-science](https://github.com/aipoch/open-science/tree/a3d66566d478bc7cdd0539ad7cd3a5761fbce2a9), pinned on 2026-10-28. The separate Electron/Node desktop/CLI and notebook, artifact-version or `host.delegate` APIs are not deployed by this entry. Use lunwen's cloud execution and provenance records.

Find the selected lunwen checkout. Read `AGENTS.md` and the current stage contract. For figures read `docs/FIGURE-REFERENCE-WORKBENCH.md` and `docs/FIGURE-LINEAGE-AND-TEX-SOURCES.md`; for reproduction read `docs/EXPERIMENT-EVIDENCE.md`.

For a figure deck:

1. Map each main figure to its claim, question and actual supporting outputs. Order figures into the strongest supported argument. Retain registered adverse outcomes in appropriate locations; emphasis changes do not authorize evidence deletion.
2. Separate missing analysis from drawing defects. Unperformed analysis becomes a proposal under the approved experiment route, never an invented panel.
3. Propose panel-specific changes. Reuse only panels whose bytes, source bindings, renderer and relevant style dependencies are unchanged. Bind each composition to exact dimensions and panel versions.
4. Render and inspect the actual output in the cloud. Keep a source-bound decision log of proposed, accepted and rejected changes.

For reproduction:

1. Inventory inputs, helper sources, exact environment locks, commands and receipts. List barriers such as unavailable data, truncated helpers, unpinned dependencies or missing execution authority.
2. State the scope actually reproduced: downstream rendering, one analysis stage or end-to-end computation. Replotting existing outputs does not reproduce the experiment.
3. Compare scientific outputs using declared identifiers, units, missingness rules and predeclared tolerances. Visual similarity is insufficient. Keep blocked/unexecuted checks explicit.

Return targeted changes or a reproduction-scope/barrier table with source locations and unresolved judgments. Use `docs/RESEARCH-AUTOMATION-TOOLKIT.md`, operation `research_toolkit`, tool ID `aipoch-open-science` for a packet. `RESEARCH_TOOLKIT_PACKET=<project-relativepath>` supplies only selected guidance to the current model cycle.

## Pinned source

Canonical staged source: `D:\ad\codex\research-automation\sources\aipoch-open-science`; verify its manifest before local use.

- [paper-narrative](https://github.com/aipoch/open-science/blob/a3d66566d478bc7cdd0539ad7cd3a5761fbce2a9/resources/skills/paper-narrative/SKILL.md): figure deck as an argument.
- [figure-composer](https://github.com/aipoch/open-science/blob/a3d66566d478bc7cdd0539ad7cd3a5761fbce2a9/resources/skills/figure-composer/kernel.py): exact layout and panel corrections.
- [reproducibility recipe](https://github.com/aipoch/open-science/blob/a3d66566d478bc7cdd0539ad7cd3a5761fbce2a9/packages/reproducibility/src/recipe.ts): barriers and scope.

Upstream is Apache-2.0 licensed; retain notices when copying components. Translate host-specific operations to native lunwen controls rather than assuming upstream tools exist in Codex. Keep human gates and model routes intact.
