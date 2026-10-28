---
name: research-paperbanana
description: Use PaperBanana's reference-driven planning and visual critique to improve a method diagram in lunwen, producing an editable figure specification from verified scientific content.
---

# PaperBanana figure planning

Codex adaptation of [dwzhu-pku/PaperBanana](https://github.com/dwzhu-pku/PaperBanana/tree/f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3), pinned on 2026-10-28. This entry supports planning/critique using current tools; it does not deploy the separate Python/image pipeline or authorize Google/OpenRouter calls. Copying `skill/` alone is insufficient because `run.py` imports the full repository's agents, utilities and configuration.

Read the selected lunwen checkout's `skills/figures/SKILL.md` and `docs/FIGURE-REFERENCE-WORKBENCH.md`. Preserve existing planner/writer roles and cloud renderers.

1. Identify the one-sentence takeaway and exact manuscript, method, claim and evidence anchors. Result-bearing plots must use recorded data and deterministic plotting specifications, not values inferred or generated from reference images.
2. Select relevant references with original source/rights records. Explain useful panel hierarchy, flow, encoding or label density. Design an original diagram rather than copy scientific content.
3. Prepare panels, semantic entities, justified connections, hierarchy, labels and caption in the existing figure-story representation. Distinguish conceptual relationships from demonstrated causality or quantitative results.
4. Critique semantic fidelity before presentation. Name a specific panel/edge/label, source conflict or readability defect, and repair. Missing images, malformed critique and absent evidence stay unassessed rather than passing.
5. Render editable SVG/PPTX/draw.io or data-derived plots through the cloud workflow. Check the actual publication-size output with label, math, color and lineage checks. Reuse unchanged panels; stop after resolving the requested defects.

Return the source-bound plan, targeted critique and actual output when rendering is available. Visual quality does not verify the scientific claim. Optional raster conceptual illustrations use the separate authorization/disclosure route.

Use `docs/RESEARCH-AUTOMATION-TOOLKIT.md`, operation `research_toolkit`, tool ID `paperbanana` for a packet. `RESEARCH_TOOLKIT_PACKET=<project-relativepath>` supplies selected guidance to existing model roles.

## Pinned source

Canonical staged source: `D:\ad\codex\research-automation\sources\paperbanana`; verify its manifest before local use.

- [planner_agent.py](https://github.com/dwzhu-pku/PaperBanana/blob/f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3/agents/planner_agent.py): reference-conditioned layout planning.
- [critic_agent.py](https://github.com/dwzhu-pku/PaperBanana/blob/f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3/agents/critic_agent.py): critique structure; empty defaults are not evidence of success.

Do not inherit ten parallel candidates, three critic rounds or large token/retry caps. Reuse the existing writer/critic cycle and budget. Preserve the repository's Apache-2.0 notice and native skill's MIT-0 declaration for their respective components.
