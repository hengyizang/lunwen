---
name: api-tasks
description: Route bounded auxiliary extraction, formatting, screening, synthesis and independent critique to priced external models while Codex manages checks and human gates.
---

# API tasks

Use `scripts/task_router.py` first without `--execute` to show model, ceiling and estimated CNY charge. Set explicit model-specific prices in `DR_OS_MODEL_PRICING_JSON` before routing to an alternate low-cost model. Execute only the chosen bounded auxiliary job with `--execute`; its output is held in protected `api_runs/` and is not a verified citation, experimental result or manuscript.

Use `scripts/api_orchestrator.py cycle` for the full G0–G5 planner/writer/independent-critic flow. Preserve Claude as internal read-only planner/critic and GPT/OpenAI as the persistent writer. Do not silently switch model identity, provider protocol, reviewer family, gate status or requested publication artifact to a cheap tier. Cache only byte-identical prompts.
