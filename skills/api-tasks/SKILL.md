---
name: api-tasks
description: Route bounded auxiliary extraction, formatting, screening, synthesis and independent critique to priced external models while Codex manages checks and human gates.
---

# API tasks

Use `scripts/task_router.py` first without `--execute` to show family, minimum quality tier, task risk, healthy candidates, token ceiling and estimated CNY charge. Declare alternates in `DR_OS_ROUTING_CANDIDATES_JSON` and exact model-specific prices in `DR_OS_MODEL_PRICING_JSON`; a model failing a paid, explicit `scripts/model_health.py --execute` probe is excluded for 24 hours. Low-risk extraction/formatting may prefer a cheaper qualifying model; high-risk scientific judgment/critique prioritizes quality and independent family constraints. Execute only the chosen bounded auxiliary job with `--execute`; its output is held in protected `api_runs/` and is not a verified citation, experimental result or manuscript.

Use `scripts/api_orchestrator.py cycle` for the full G0–G5 planner/writer/independent-critic flow. Preserve Claude as internal read-only planner/critic and GPT/OpenAI as the persistent writer. Do not silently switch model identity, provider protocol, reviewer family, gate status or requested publication artifact to a cheap tier. Cache only byte-identical prompts.
