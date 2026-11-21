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
from scripts.research_cycle import decision_errors


class AutopilotError(RuntimeError):
    pass


def show_plan(project: str, context: str = "", *, paper_id: str | None = None,
              stage: str | None = None, planning: bool = False, review: bool = False,
              remediate: bool = False, source_paths: list[str] | None = None) -> dict[str, Any]:
    """Preview selected research work without requests, spending or mutations."""
    work=researchctl.current_work(project)
    if paper_id:
        researchctl.validate_paper_id(paper_id)
        if not (researchctl.project_dir(project)/"papers"/paper_id).is_dir():
            raise AutopilotError("Unknown paper: "+paper_id)
        work={**work,"paper_id":paper_id}
    if stage:
        if stage not in {row["name"] for row in researchctl.STAGES[:-1]}:
            raise AutopilotError("Unknown research task stage")
        work={**work,"stage":stage}
    from scripts.research_cycle import requires_critic
    review = review or requires_critic(work["stage"],researchctl.project_dir(project))
    # The selected operation and review policy determine any additional calls.
    # A preview cannot promise a route or fabricate an independent review.
    return {**work,"active_paper":work["paper_id"],"task":context or work["task"],
            "backend":"api","context_supplied":bool(context),"status":"work_available",
            "steps":(["plan the selected task"] if planning else [])+["execute the selected research task with its relevant sources"]+(["independent source-bound review"] if review else []),
            "conditional_steps":["use a selected research tool or independent review when the task needs it"],
            "planned_model_calls":1+int(planning)+int(review),"with_repair_model_calls":1+int(planning)+int(review)+(2 if review and remediate else 0),"paid_model_calls":0,
            "next_control":"Run start or resume. Existing cumulative budgets and actual operation inputs apply; historical gates do not grant or withhold permission to work."}


def run_stage(project: str, context: str = "", *, planner_provider: str | None = None,
              writer_provider: str | None = None, critic_provider: str | None = None,
              max_output_tokens: int = 12000, control_max_output_tokens: int = 4000,
              paper_id: str | None = None, stage: str | None = None, planning: bool = False,
              review: bool = False, remediate: bool = False, source_paths: list[str] | None = None) -> dict[str, Any]:
    """Execute a task through the shared API, preserving all existing evidence."""
    work=researchctl.select_work(project,context,paper_id,stage)
    from scripts.research_cycle import requires_critic
    review=review or requires_critic(work["stage"],researchctl.project_dir(project))
    if remediate and not review:raise AutopilotError("remediate requires a selected review")
    with model_runtime.authorized_calls(researchctl.project_dir(project)):
        from scripts.cloud_progress import track_cycle
        execute=track_cycle(researchctl.project_dir)(api_orchestrator.run_cycle)
        manifest=execute(project,work["stage"],planner_provider,
            writer_provider,critic_provider,context or work["task"],"",max_output_tokens,control_max_output_tokens,
            planning=planning,review=review,remediate=remediate,source_paths=source_paths)
    result={"project":project,"gate":work["gate"],"active_paper":work["paper_id"],"backend":"api",**manifest}
    if manifest.get("control_only") is True or manifest.get("paid_model_cycle") is False:
        return {**result,"status":"controlled_step","runs":[]}
    # Scientific findings affect the stated conclusion. They do not send the
    # project through ready/approve/advance or invalidate other papers.
    issues=decision_errors(manifest.get("research_decision",{}))
    return {**result,"status":"needs_work" if issues else "work_completed", "research_findings":issues}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    for command in ("start", "resume", "plan"):
        item = sub.add_parser(command)
        item.add_argument("--project", required=True)
        item.add_argument("--context", default="")
        item.add_argument("--paper", dest="paper_id")
        item.add_argument("--plan-work", dest="planning", action="store_true")
        item.add_argument("--review", action="store_true")
        item.add_argument("--remediate", action="store_true")
        item.add_argument("--source", dest="source_paths", action="append")
        item.add_argument("--stage", choices=[row["name"] for row in researchctl.STAGES[:-1]])
        for role, provider in (
            ("planner", None),
            ("writer", None),
            ("critic", None),
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
            show_plan(args.project, args.context, paper_id=args.paper_id, stage=args.stage, planning=args.planning, review=args.review, remediate=args.remediate, source_paths=args.source_paths)
            if args.command == "plan"
            else run_stage(
                args.project,
                args.context,
                planner_provider=args.planner_provider,
                writer_provider=args.writer_provider,
                critic_provider=args.critic_provider,
                max_output_tokens=args.max_output_tokens,
                control_max_output_tokens=args.control_max_output_tokens,
                paper_id=args.paper_id, stage=args.stage, planning=args.planning, review=args.review,
                remediate=args.remediate, source_paths=args.source_paths,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (RuntimeError, ValueError, OSError) as exc:
        print("error: " + api_orchestrator.redact(str(exc)), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
