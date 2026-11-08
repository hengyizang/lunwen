#!/usr/bin/env python3
"""Compatibility commands for the canonical API research cycle.

The local Claude Code/Codex subprocess backend is retired. These commands use
configured API routes, protected artifact bundles and the existing project budget.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import ai_providers, api_orchestrator, model_runtime, researchctl
from scripts.cloud_continuation import transition_ready_gate
from scripts.research_cycle import decision_errors, requires_critic
from scripts.research_phase import requires_submission


class AutopilotError(RuntimeError):
    pass


def show_plan(project: str, context: str = "") -> dict[str, Any]:
    """Preview the current stage without requests, spending or state mutations."""
    state = researchctl.load_state(project)
    if state["gate"] is None:
        return {
            "project": project,
            "status": "submission_ready",
            "steps": [],
            "paid_model_calls": 0,
        }
    if state["status"] == "awaiting_approval" and state["gate"] in {"G1", "G2"}:
        return {
            "project": project,
            "status": "awaiting_human_topic_approval",
            "steps": [],
            "planned_model_calls": 0,
            "with_repair_model_calls": 0,
            "paid_model_calls": 0,
        }
    if state["status"] in {"approved", "awaiting_approval"}:
        return {
            "project": project,
            "stage": state["stage"],
            "gate": state["gate"],
            "status": "control_pending",
            "steps": ["checked gate transition before the next model-cycle plan"],
            "planned_model_calls": None,
            "with_repair_model_calls": None,
            "paid_model_calls": 0,
            "next_control": "Inspect the successor plan after its checked transition; successor calls are unknown here.",
        }
    api_orchestrator.stage_config(state["stage"])
    steps = ["read-only semantic plan", "non-Anthropic persistent writer"]
    conditional = []
    if requires_submission(researchctl.project_dir(project), state["stage"]):
        steps.extend(
            ["blind domain review", "blind editorial review", "blind statistics review"]
        )
        mode = "three_blind_submission_views"
    elif requires_critic(state["stage"]):
        steps.append("fresh source-bound independent critique")
        conditional = ["itemized repair", "fresh independent review of changed sources"]
        from scripts.supplemental_experiments import proposal_pending

        if proposal_pending(researchctl.project_dir(project)):
            steps.append("fresh final supplemental-protocol authority review")
            conditional = ["itemized repair before the final protocol review"]
        mode = "scientific_review"
    else:
        mode = "administrative_intake"
    return {
        "project": project,
        "stage": state["stage"],
        "gate": state["gate"],
        "active_paper": state.get("active_paper"),
        "context_supplied": bool(context),
        "backend": "api",
        "review_mode": mode,
        "steps": steps,
        "conditional_steps": conditional,
        "repair_trigger": "actual actionable findings",
        "planned_model_calls": len(steps),
        "with_repair_model_calls": len(steps) + len(conditional),
        "paid_model_calls": 0,
        "next_control": "Preview covers the current stage. Resume checks ready/advance first and may select a different stage with different calls. G1/G2 require the actual owner topic decision.",
    }


def run_stage(
    project: str,
    context: str = "",
    *,
    planner_provider: str = "anthropic",
    writer_provider: str = "openai",
    critic_provider: str = "anthropic",
    max_output_tokens: int = 12000,
    control_max_output_tokens: int = 4000,
) -> dict[str, Any]:
    """Run the shared API cycle, retaining checked stage transitions and stops."""
    state = researchctl.load_state(project)
    from scripts.scientific_scope import validate

    errors = validate(
        researchctl.project_dir(project), state.get("gate"), state.get("active_paper")
    )
    if errors:
        raise AutopilotError("; ".join(errors))
    if state["status"] == "approved":
        transition_ready_gate(project, {"reason": "approved_gate_ready_to_advance"})
        state = researchctl.load_state(project)
    if state["status"] == "awaiting_approval" and state["gate"] not in {"G1", "G2"}:
        reason = (
            "automatic_gate_reopen"
            if researchctl.gate_errors(project, state["gate"])
            else "automatic_gate_ready"
        )
        transition_ready_gate(project, {"reason": reason})
        state = researchctl.load_state(project)
    if state["gate"] is None:
        return {"project": project, "status": "submission_ready", "runs": []}
    if state["status"] == "awaiting_approval":
        return {
            "project": project,
            "stage": state["stage"],
            "gate": state["gate"],
            "status": "awaiting_human_topic_approval",
            "runs": [],
        }
    with model_runtime.authorized_calls(researchctl.project_dir(project)):
        manifest = api_orchestrator.run_cycle(
            project,
            state["stage"],
            planner_provider,
            writer_provider,
            critic_provider,
            context,
            "",
            max_output_tokens,
            control_max_output_tokens,
        )
    result = {"project": project, "gate": state["gate"], "backend": "api", **manifest}
    if manifest.get("paid_model_cycle") is False:
        return {**result, "status": "controlled_step", "runs": []}
    if manifest.get("writing_phase_transition"):
        return {**result, "status": "submission_preparation", "gate_errors": []}
    if manifest.get("primary_recovery", {}).get("retired"):
        return {**result, "status": "protocol_retired_to_G3"}
    errors = researchctl.gate_errors(project, state["gate"])
    errors.extend(decision_errors(manifest.get("research_decision", {})))
    if errors:
        return {**result, "status": "needs_work", "gate_errors": errors}
    transition_ready_gate(project, {"reason": "automatic_gate_ready"})
    current = researchctl.load_state(project)
    if current["status"] == "awaiting_approval" and state["gate"] not in {"G1", "G2"}:
        raise AutopilotError(
            "The checked non-topic gate did not record its automatic decision"
        )
    status = (
        "awaiting_human_topic_approval"
        if current["status"] == "awaiting_approval"
        else "stage_advanced"
    )
    return {**result, "status": status, "gate_errors": []}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    for command in ("start", "resume", "plan"):
        item = sub.add_parser(command)
        item.add_argument("--project", required=True)
        item.add_argument("--context", default="")
        for role, provider in (
            ("planner", "anthropic"),
            ("writer", "openai"),
            ("critic", "anthropic"),
        ):
            item.add_argument(
                f"--{role}-provider", choices=ai_providers.PROVIDERS, default=provider
            )
        item.add_argument(
            "--max-output-tokens",
            type=int,
            default=int(os.environ.get("DR_OS_MAX_OUTPUT_TOKENS", "12000")),
        )
        item.add_argument(
            "--control-max-output-tokens",
            type=int,
            default=int(os.environ.get("DR_OS_CONTROL_MAX_OUTPUT_TOKENS", "4000")),
        )
        for option in (
            "claude-mode",
            "timeout",
            "max-output-bytes",
            "claude-max-budget-usd",
        ):
            item.add_argument("--" + option, help=argparse.SUPPRESS)
        if command == "start":
            item.add_argument("--paper-count", type=int)
            item.add_argument("--venue")
    return root


def main(argv: Iterable[str] | None = None) -> int:
    arguments = parser()
    args = arguments.parse_args(argv)
    retired = [
        "--" + name.replace("_", "-")
        for name in (
            "claude_mode",
            "timeout",
            "max_output_bytes",
            "claude_max_budget_usd",
        )
        if getattr(args, name) is not None
    ]
    if retired:
        arguments.error(
            "Local process options are retired: "
            + ", ".join(retired)
            + ". Use API token limits; bytes are not tokens. Transport timeouts and spending use the configured API route and cumulative budget."
        )
    if not 1 <= args.control_max_output_tokens <= args.max_output_tokens <= 100000:
        arguments.error(
            "token limits must satisfy 1 <= control-max-output-tokens <= max-output-tokens <= 100000"
        )
    try:
        if (
            args.command == "start"
            and not researchctl.project_dir(args.project).exists()
        ):
            researchctl.initialize(
                SimpleNamespace(
                    project=args.project, paper_count=args.paper_count, venue=args.venue
                )
            )
        elif not researchctl.project_dir(args.project).is_dir():
            raise AutopilotError(f"Project does not exist: {args.project}")
        result = (
            show_plan(args.project, args.context)
            if args.command == "plan"
            else run_stage(
                args.project,
                args.context,
                planner_provider=args.planner_provider,
                writer_provider=args.writer_provider,
                critic_provider=args.critic_provider,
                max_output_tokens=args.max_output_tokens,
                control_max_output_tokens=args.control_max_output_tokens,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print("error: " + api_orchestrator.redact(str(exc)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
