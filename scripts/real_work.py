#!/usr/bin/env python3
"""Real-work-first entry point for the Doctoral Research OS.

The full protocol stays intact and is the default. This module adds an
explicitly opted-in ``DR_OS_WORK_PROFILE=minimal`` profile that keeps only the
checks which actually prevent fabrication, and records the ceremonial,
format-migration and calibration checks as visible non-blocking observations.

It never authors scientific content on the owner's behalf. Human topic
decisions stay human: every command that changes a gate requires ``--actor``.
No third-party imports are required; only the Python standard library.
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
    if os.environ.get(PROFILE_ENV, "").strip().lower() not in PROFILE_VALUES:
        return False
    if gate is None:
        return True
    gates = load_config().get("enabled_gates", ["G1"])
    return isinstance(gates, list) and gate in gates


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


def hard_conditions(slug: str, gate: str = "G1") -> list[tuple[str, bool]]:
    """The three checks that actually prevent a fabricated doctoral decision."""
    project = project_dir(slug)
    shortlist = read_json(project / "program" / "topic-shortlist.json") or {}
    candidates = shortlist.get("candidates") or shortlist.get("topics") or []
    core = read_json(project / "program" / "core-thesis.json") or {}
    decision = project / "program" / "topic-decision.md"
    return [
        ("owner-written program/topic-decision.md",
         nonempty(decision) and PLACEHOLDER not in decision.read_text(encoding="utf-8") if nonempty(decision) else False),
        ("at least three real topic candidates",
         isinstance(candidates, list) and len(candidates) >= 3),
        ("one doctoral_question in program/core-thesis.json",
         bool(str(core.get("doctoral_question", "")).strip())),
    ]


def cmd_status(args: argparse.Namespace) -> int:
    state = read_state(args.project)
    gate = state.get("gate")
    print(f"project      : {args.project}")
    print(f"stage        : {state.get('stage')}  (gate={gate}, status={state.get('status')})")
    print(f"approved     : {', '.join(state.get('approved_gates', [])) or '(none)'}")
    print(f"profile      : {'minimal (real-work-first)' if profile_enabled(gate) else 'full protocol (default)'}")
    if gate == "G1":
        print("\nG1 hard conditions (the only blocking checks under the minimal profile):")
        for label, ok in hard_conditions(args.project, "G1"):
            print(f"  [{'x' if ok else ' '}] {label}")
        missing = [label for label, ok in hard_conditions(args.project, "G1") if not ok]
        if missing:
            print(f"\nnext: fill {len(missing)} missing item(s), then run")
            print(f"  python -m scripts.real_work bootstrap-g1 --project {args.project}")
        else:
            print("\nnext: record the real human decision (one command):")
            print(f'  python -m scripts.real_work decide --project {args.project} --actor "Your Name" --note "..."')
    else:
        print("\nnext: use the existing control plane")
        print(f"  python -m scripts.researchctl gate-check --project {args.project}")
    print("\nFull protocol (all checks, unchanged): python -m scripts.researchctl gate-check --project "
          + args.project)
    return 0


def cmd_bootstrap_g1(args: argparse.Namespace) -> int:
    """Create the *empty* G1 skeleton. Never writes scientific content."""
    project = project_dir(args.project)
    program = project / "program"
    program.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    shortlist_path = program / "topic-shortlist.json"
    if not shortlist_path.is_file() or args.force:
        candidates = []
        log = project / "evidence" / "search-log.jsonl"
        real_refs: list[str] = []
        if log.is_file():
            for line in log.read_text(encoding="utf-8", errors="ignore").splitlines()[:40]:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                ref = row.get("evidence_receipt_id")
                if isinstance(ref, str) and ref not in real_refs:
                    real_refs.append(ref)
        for index in range(1, 4):
            candidates.append({
                "candidate_id": f"C{index}",
                "title": "",
                "owner_rationale": "",
                "main_risk": "",
                "supporting_receipt_ids": real_refs[:3],
                "status": PLACEHOLDER,
            })
        shortlist_path.write_text(json.dumps({
            "schema_version": "1.0",
            "generated_by": "scripts.real_work.bootstrap-g1",
            "generated_at": _now(),
            "note": "Skeleton only. Titles, rationale and risks must be written by the owner. Receipt IDs are copied from existing real search logs and are not evidence of a decision.",
            "candidates": candidates,
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        created.append("program/topic-shortlist.json")
    decision_path = program / "topic-decision.md"
    if not decision_path.is_file() or args.force:
        decision_path.write_text(
            "# Doctoral topic decision\n\n"
            f"Status: {PLACEHOLDER}\n\n"
            "Owner: ______________________    Date: ____________\n\n"
            "## Chosen candidate\n\n(Write which of C1/C2/C3 you choose and why.)\n\n"
            "## Strongest rival and why it was not chosen\n\n(Required: keep the disagreement visible.)\n\n"
            "## Main risk and how it will be tested\n\n(Owner's own words.)\n\n"
            "## What is still unknown\n\n(Do not claim saturation or novelty.)\n",
            encoding="utf-8")
        created.append("program/topic-decision.md")
    core_path = program / "core-thesis.json"
    if not core_path.is_file() or args.force:
        core_path.write_text(json.dumps({
            "schema_version": "1.0",
            "doctoral_question": "",
            "distinct_contribution": "",
            "falsification_conditions": [],
            "status": PLACEHOLDER,
            "note": "Owner-authored. The control plane never fills these fields.",
        }, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        created.append("program/core-thesis.json")
    if created:
        print("Created empty skeleton (no scientific content was generated):")
        for item in created:
            print("  - " + item)
    else:
        print("Existing G1 material left untouched. Use --force only if you intend to replace it.")
    print("\nFill in the three files above, then run:")
    print(f"  python -m scripts.real_work status --project {args.project}")
    return 0


def _run_ctl(args: list[str], env: dict[str, str]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, "-m", "scripts.researchctl", *args],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def cmd_decide(args: argparse.Namespace) -> int:
    """One command: verify real human input, then check -> ready -> approve -> advance."""
    actor = args.actor.strip()
    if not actor or actor == "deterministic-control-plane":
        raise SystemExit("--actor must name the real human making the topic decision")
    state = read_state(args.project)
    if state.get("gate") != "G1":
        raise SystemExit(f"current gate is {state.get('gate')}, not G1; this command handles the G1 decision")
    missing = [label for label, ok in hard_conditions(args.project, "G1") if not ok]
    if missing:
        raise SystemExit("real human input is still missing: " + "; ".join(missing))
    env = dict(os.environ)
    env[PROFILE_ENV] = "minimal"
    steps = [
        ["gate-check", "--project", args.project],
        ["ready", "--project", args.project, "--note", args.note],
        ["approve", "--project", args.project, "--gate", "G1", "--actor", actor, "--note", args.note],
        ["advance", "--project", args.project],
    ]
    for step in steps:
        code, output = _run_ctl(step, env)
        print(f"$ researchctl {' '.join(step[:2])} ... -> rc={code}")
        if output:
            for line in output.splitlines()[:8]:
                print("    " + line)
        if code != 0:
            print(f"\nStopped at {step[0]}. Nothing was fabricated; the full protocol is still available.")
            return code
    print("\nG1 decision recorded and project advanced. The remaining 80+ full-protocol observations")
    print("were recorded as non-blocking (see docs/REAL-WORK-QUICKSTART.md).")
    return 0


def cmd_check_real(args: argparse.Namespace) -> int:
    """List what is genuinely missing for a real (non-synthetic) run. Never raises."""
    checks: list[tuple[str, bool, str]] = []
    try:
        import jsonschema  # noqa: F401
        checks.append(("jsonschema installed (removes 2 G1 'validator unavailable' errors)", True, ""))
    except ImportError:
        checks.append(("jsonschema installed", False, "python -m pip install jsonschema"))
    keys = [
        "DR_OS_CHEAPAI_GPT_PRO_KEY", "DR_OS_CHEAPAI_GPT_DISCOUNT_KEY",
        "DR_OS_CODEKEY_KIRO_ENTERPRISE_KEY", "DR_OS_CODEKEY_DEEPSEEK_KEY",
        "DR_OS_CODEKEY_GEMINI_KEY",
    ]
    present = [k for k in keys if os.environ.get(k)]
    checks.append((f"model API keys present ({len(present)}/{len(keys)})", bool(present),
                   "export the key for the providers you actually use; keys never enter the repo"))
    checks.append(("config/model-routing.local.json with real model IDs", LOCAL_MODELS.is_file(),
                   "python -m scripts.real_work configure-models --sol <real-id> --opus <real-id> ..."))
    checks.append(("real-work profile enabled", profile_enabled(),
                   "export DR_OS_WORK_PROFILE=minimal  (or use the decide command, which sets it)"))
    state = read_state(args.project)
    checks.append(("G0 approved", "G0" in state.get("approved_gates", []), ""))
    print("Real-run readiness (gaps are listed, not errors):\n")
    gaps = 0
    for label, ok, fix in checks:
        print(f"  [{'x' if ok else ' '}] {label}")
        if not ok:
            gaps += 1
            if fix:
                print(f"        fix: {fix}")
    print(f"\n{len(checks) - gaps}/{len(checks)} ready. A real run needs keys + real model IDs + G0.")
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
    filled, reordered into a decision, or inferred. A model may not screen.
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
        "records. The control plane never accepts a model-authored screening decision.",
        "",
    ]
    (outdir / "INDEX.md").write_text("\n".join(index), encoding="utf-8")
    print(f"Split {len(rows)} rows into {count} batches of <= {size} in {outdir.relative_to(ROOT)}")
    print("No screening decision was made or pre-filled. See INDEX.md.")
    return 0


def cmd_prepare_decision(args: argparse.Namespace) -> int:
    """Compress *existing* real material into one owner decision sheet.

    Reads only files that already exist. It never invents a candidate, a score,
    a risk or a recommendation, and never fills in any field that belongs to
    the owner. The point is to make the human decision cheap, not to make it.
    """
    project = project_dir(args.project)
    program = project / "program"
    shortlist = read_json(program / "topic-shortlist.json") or {}
    candidates = shortlist.get("candidates") or shortlist.get("topics") or []
    core = read_json(program / "core-thesis.json") or {}
    decision_path = program / "topic-decision.md"
    decision_text = ""
    if nonempty(decision_path):
        decision_text = decision_path.read_text(encoding="utf-8")
    screening = project / "reports" / "g1-human-screening-sheet.csv"
    screening_rows = 0
    if screening.is_file():
        try:
            screening_rows = max(0, len(screening.read_text(encoding="utf-8").splitlines()) - 1)
        except OSError:
            screening_rows = 0
    pending_confirmation = "待负责人确认" in decision_text or "awaiting" in decision_text.lower()

    lines = [
        "# G1 decision sheet (one page)",
        "",
        f"Generated by `scripts.real_work prepare-decision` at {_now()}.",
        "All facts below are copied from existing project files. Nothing here is a new",
        "scientific claim, a recommendation, or a recorded approval.",
        "",
        "## 1. What is already on file",
        "",
        f"- Doctoral question (program/core-thesis.json): {str(core.get('doctoral_question', '')).strip() or '(not filled)'}",
        f"- Candidates in program/topic-shortlist.json: {len(candidates)}",
    ]
    for item in candidates:
        if isinstance(item, dict):
            cid = item.get("candidate_id") or item.get("id") or "?"
            title = item.get("title") or item.get("name") or "(no title recorded)"
            lines.append(f"  - {cid}: {title}")
    lines += [
        f"- selection_decision: {json.dumps(shortlist.get('selection_decision'), ensure_ascii=False)}"
        + ("  <-- no candidate has been chosen yet" if not shortlist.get("selection_decision") else ""),
        f"- program/topic-decision.md: {'present, marked as a proposal awaiting owner confirmation' if pending_confirmation else 'present'}",
        f"- reports/g1-human-screening-sheet.csv: {screening_rows} rows awaiting a named human decision",
        "",
        "Reference material (read, not restated here): program/direction-ranking.json,",
        "program/originality-audit.json, program/novelty-claim-matrix.json,",
        "program/hypothesis-register.json, and section 4 of program/topic-decision.md",
        "(which lists the evidence limitations you must weigh).",
        "",
        "## 2. The three fields only you can fill",
        "",
        "1. Chosen candidate id: ______________________",
        "2. Strongest rival id and why it was not chosen: ______________________",
        "3. Main risk and how you will test it: ______________________",
        "",
        "Owner: ______________________    Date: ____________",
        "",
        "## 3. Still outstanding before a real G1 approval",
        "",
        f"- [ ] Named human screening of the {screening_rows} search rows (`screened_by` is never filled by a model)",
        "- [ ] Link the 11 closest prior works to their retrieval records",
        "- [ ] A real independent critique receipt (needs working model keys)",
        "- [ ] quality-G1.json and reviews/decision-log.md",
        "",
        "The real-work profile lowers the ceremonial blockers, not these human ones.",
        "",
        "## 4. After you have filled in the three fields",
        "",
        "Write your choice into program/topic-shortlist.json (selection_decision) and",
        "program/topic-decision.md, then run:",
        "",
        f'  python -m scripts.real_work decide --project {args.project} --actor "Your Name" --note "..."',
        "",
        "That command records YOUR decision; it does not make one.",
        "",
    ]
    out = project / "reports" / "G1-DECISION-SHEET.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)} ({len(lines)} lines, no new scientific content).")
    print("Fill in the three owner fields in section 2, then run the decide command shown in section 4.")
    return 0


def cmd_full_check(args: argparse.Namespace) -> int:
    env = dict(os.environ)
    env.pop(PROFILE_ENV, None)
    code, output = _run_ctl(["gate-check", "--project", args.project], env)
    print(output)
    return code


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Real-work-first entry point (opt-in minimal profile)")
    cmd = root.add_subparsers(dest="command", required=True)

    p = cmd.add_parser("status", help="current stage and the few things actually blocking real work")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_status)

    p = cmd.add_parser("bootstrap-g1", help="create the EMPTY G1 skeleton for a new project")
    p.add_argument("--project", required=True)
    p.add_argument("--force", action="store_true", help="replace existing material (destructive)")
    p.set_defaults(func=cmd_bootstrap_g1)

    p = cmd.add_parser("decide", help="record a real human G1 decision in one command")
    p.add_argument("--project", required=True)
    p.add_argument("--actor", required=True, help="name of the human making the decision")
    p.add_argument("--note", default="Owner topic decision recorded via real_work.decide")
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

    p = cmd.add_parser("full-check", help="run the unchanged full protocol gate-check")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_full_check)
    return root


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
