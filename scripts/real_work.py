#!/usr/bin/env python3
"""Compatibility helpers for the default task-based research workflow.

Use researchctl work/add-paper and autopilot start/resume for normal work.
These helpers preserve existing material and never fabricate decisions or evidence.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "real-work.json"
LOCAL_MODELS = ROOT / "config" / "model-routing.local.json"
PROFILE_ENV = "DR_OS_WORK_PROFILE"
PROFILE_VALUES = {"1", "true", "minimal", "real", "real-work-first"}
PLACEHOLDER = "HUMAN_INPUT_REQUIRED"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> dict[str, Any]:
    try:
        value = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def profile_enabled(gate: str | None = None) -> bool:
    """The single normal workflow is research-first; the old opt-in is retired."""
    return True


def project_dir(slug: str) -> Path:
    if not slug or any(c in slug for c in ("/", "\\", "..")):
        raise ValueError("project must be a simple directory name")
    return ROOT / "projects" / slug


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def nonempty(path: Path) -> bool:
    try:
        return bool(path.is_file() and path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def read_state(slug: str) -> dict[str, Any]:
    state = read_json(project_dir(slug) / "state" / "run.json")
    if not isinstance(state, dict):
        raise SystemExit(f"project {slug!r} has no readable state/run.json")
    return state


def hard_conditions(slug: str, gate: str = "G1") -> list[tuple[str,bool]]:
    """Compatibility input diagnostics, not a three-field scientific clearance."""
    state=read_state(slug);paper=state.get("active_paper","P01")
    return [("readable project state",True),("selected paper exists",(project_dir(slug)/"papers"/str(paper)).is_dir())]


def cmd_status(args: argparse.Namespace) -> int:
    from scripts import researchctl
    researchctl.print_status(argparse.Namespace(project=args.project,json=False,legacy_checks=False))
    return 0


def cmd_bootstrap_g1(args: argparse.Namespace) -> int:
    """Create optional empty working notes without inventing candidate quotas."""
    project=project_dir(args.project);program=project/"program";program.mkdir(parents=True,exist_ok=True)
    files={"topic-shortlist.json":{"schema_version":"1.0","candidates":[],"selection_decision":None},
           "core-thesis.json":{"schema_version":"1.0","doctoral_question":"","distinct_contribution":"","falsification_conditions":[]},
           "topic-decision.md":"# Research direction\n\n"+PLACEHOLDER+"\n"}
    for name,value in files.items():
        target=program/name
        if target.exists() and not args.force:continue
        target.write_text(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Optional empty notes prepared; existing material was preserved unless --force was explicitly selected.")
    print("Continue with the actual research question; no candidate count or approval form is required.")
    return 0


def _run_ctl(args: list[str], env: dict[str, str]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.researchctl", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def cmd_decide(args: argparse.Namespace) -> int:
    """Record an existing user decision without a gate transition ceremony."""
    from scripts import researchctl
    actor=args.actor.strip()
    if not actor or actor=="deterministic-control-plane":raise SystemExit("--actor must name the actual decision maker")
    path=project_dir(args.project)/"program/topic-decision.md"
    decision=args.note.strip() or (path.read_text(encoding="utf-8").strip() if path.is_file() else "")
    if not decision or PLACEHOLDER in decision:raise SystemExit("Supply the actual topic decision in --note or program/topic-decision.md")
    state=researchctl.load_state(args.project)
    state.setdefault("history",[]).append({"at":_now(),"event":"research_direction_recorded","actor":actor,
        "decision":decision,"scientific_approval_granted":False})
    researchctl.save_state(args.project,state)
    researchctl.select_work(args.project,decision)
    print("Recorded the research direction. Continue the selected task with autopilot resume.")
    return 0


def cmd_check_real(args: argparse.Namespace) -> int:
    """Inspect the selected model route and existing budget, without live calls."""
    from scripts.cloud_continuation import startup_report
    print(json.dumps(startup_report(args.project),ensure_ascii=False,indent=2))
    return 0


def cmd_configure_models(args: argparse.Namespace) -> int:
    """Write owner-supplied real model IDs. Never guesses or invents a model name."""
    names = ("sol", "astra", "luna", "sonnet", "opus", "deepseek", "argon")
    models = {name: getattr(args, name) for name in names if getattr(args, name)}
    if not models:
        raise SystemExit("provide at least one real model id, e.g. --sol gpt-4o --opus claude-sonnet-4-5")
    defaults = {
        "sol": ("cheapai-gpt-pro", "openai"), "astra": ("cheapai-gpt-pro", "openai"),
        "luna": ("cheapai-gpt-discount", "openai"),
        "sonnet": ("codekey-kiro-enterprise", "anthropic"), "opus": ("codekey-kiro-enterprise", "anthropic"),
        "deepseek": ("codekey-deepseek", "deepseek"), "argon": ("codekey-gemini", "google"),
    }
    payload = {
        "schema_version": "1.0",
        "created_at": _now(),
        "note": "Owner-supplied real transport model IDs. Never committed: keys and gateway details stay in the environment.",
        "models": {name: {"provider": defaults[name][0], "model": model, "family": defaults[name][1]}
                   for name, model in models.items()},
    }
    LOCAL_MODELS.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {LOCAL_MODELS.relative_to(ROOT)} with {len(models)} real model id(s).")
    print("Restart the process (or unset DR_OS_MODEL_OVERRIDES) to pick up changes.")
    return 0


def cmd_split_screening(args: argparse.Namespace) -> int:
    """Split the oversized human screening sheet into reviewable batches.

    Purely mechanical: rows and columns are copied verbatim. The four owner
    columns (human_decision, human_reason, screened_by, screened_at) are never
    filled, reordered into a decision, or inferred. Existing model or human decisions retain their recorded provenance.
    """
    import csv

    src = project_dir(args.project) / "reports" / args.sheet
    if not src.is_file():
        raise SystemExit(f"screening sheet not found: {src}")
    with src.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if not fieldnames or not rows:
        raise SystemExit("screening sheet has no data rows")
    size = max(1, args.size)
    outdir = src.parent / "g1-screening-batches"
    outdir.mkdir(parents=True, exist_ok=True)
    owner_columns = {"human_decision", "human_reason", "screened_by", "screened_at"}
    count = 0
    for start in range(0, len(rows), size):
        count += 1
        path = outdir / f"batch-{count:02d}.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows[start:start + size])
    themes: dict[str, int] = {}
    for row in rows:
        label = str(row.get("themes") or "(unlabelled)")
        themes[label] = themes.get(label, 0) + 1
    index = [
        "# G1 human screening batches",
        "",
        f"Generated by `scripts.real_work split-screening` at {_now()}.",
        f"Source: `{args.sheet}` — {len(rows)} rows, {len(fieldnames)} columns.",
        "",
        "**Mechanical split only.** No row was included, excluded, ranked, scored or",
        "annotated. The owner columns " + ", ".join(sorted(owner_columns)) + " are copied",
        "verbatim and remain empty. Only a named human may fill them.",
        "",
        "## Batches",
        "",
    ]
    for number in range(1, count + 1):
        first = (number - 1) * size + 1
        last = min(number * size, len(rows))
        index.append(f"- `batch-{number:02d}.csv` — source rows {first}–{last} ({last - first + 1} rows)")
    index += ["", "## Row counts by theme (informational, not a screening decision)", ""]
    for label, number in sorted(themes.items(), key=lambda item: -item[1])[:20]:
        index.append(f"- {label}: {number}")
    index += [
        "",
        "## How to use",
        "",
        "Work through one batch at a time and fill the four owner columns yourself.",
        "Then run `literature_evidence screen --actor \"Your Name\"` with the completed",
        "records. Source-bound model screening and human screening are both supported; retain the actual actor.",
        "",
    ]
    (outdir / "INDEX.md").write_text("\n".join(index), encoding="utf-8")
    print(f"Split {len(rows)} rows into {count} batches of <= {size} in {outdir.relative_to(ROOT)}")
    print("No screening decision was made or pre-filled. See INDEX.md.")
    return 0


def cmd_prepare_decision(args: argparse.Namespace) -> int:
    """Summarize existing questions and source locations without new assertions."""
    project=project_dir(args.project);program=project/"program"
    shortlist=read_json(program/"topic-shortlist.json") or {}
    core=read_json(program/"core-thesis.json") or {}
    lines=["# Current research direction", "", "This view copies existing material; it makes no scientific or approval decision.", "",
           "Question: "+str(core.get("doctoral_question") or "(not yet recorded)"), "", "Existing candidates:"]
    for item in shortlist.get("candidates",[]) or []:
        if isinstance(item,dict):lines.append("- "+str(item.get("candidate_id",item.get("id","?")))+": "+str(item.get("title") or item.get("name") or "(no title recorded)"))
    lines.extend(["", "Selection on file: "+json.dumps(shortlist.get("selection_decision"),ensure_ascii=False), "", "Existing material:"])
    for relative in ("program/topic-decision.md","program/hypothesis-register.json","evidence/search-log.jsonl","program/research-notebook.json"):
        if (project/relative).is_file():lines.append("- "+relative)
    lines.extend(["", "Choose the next useful reading, derivation, experiment or writing task. Use independent review when it would resolve an actual uncertainty.", "",
                  f"python -m scripts.autopilot resume --project {args.project} --context 'the next research task'", ""])
    output=project/"reports/G1-DECISION-SHEET.md";output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text("\n".join(lines),encoding="utf-8")
    print(f"Wrote {output.relative_to(ROOT)} from existing material.")
    return 0


def cmd_full_check(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    env.pop(PROFILE_ENV, None)
    code, output = _run_ctl(["gate-check", "--project", args.project], env)
    print(output)
    return code


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Compatibility helpers for the default research task workflow")
    cmd = root.add_subparsers(dest="command", required=True)

    p = cmd.add_parser("status", help="current research task and budget")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_status)

    p = cmd.add_parser("bootstrap-g1", help="prepare optional empty research notes")
    p.add_argument("--project", required=True)
    p.add_argument("--force", action="store_true", help="replace existing material (destructive)")
    p.set_defaults(func=cmd_bootstrap_g1)

    p = cmd.add_parser("decide", help="record an actual user direction without gate transitions")
    p.add_argument("--project", required=True)
    p.add_argument("--actor", required=True, help="name of the human making the decision")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_decide)

    p = cmd.add_parser("check-real", help="list gaps for a real (non-synthetic) run")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_check_real)

    p = cmd.add_parser("configure-models", help="write owner-supplied real model IDs")
    for name in ("sol", "astra", "luna", "sonnet", "opus", "deepseek", "argon"):
        p.add_argument("--" + name, default=None, help=f"real model id for the {name} route")
    p.set_defaults(func=cmd_configure_models)

    p = cmd.add_parser("split-screening", help="split the large human screening sheet into small batches")
    p.add_argument("--project", required=True)
    p.add_argument("--sheet", default="g1-human-screening-sheet.csv")
    p.add_argument("--size", type=int, default=50, help="rows per batch (default 50)")
    p.set_defaults(func=cmd_split_screening)

    p = cmd.add_parser("prepare-decision", help="compress existing real material into one owner decision sheet")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_prepare_decision)

    p = cmd.add_parser("full-check", help="run explicit legacy gate diagnostics (not a work prerequisite)")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_full_check)
    return root


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
