#!/usr/bin/env python3
"""Human-gated project state manager for Doctoral Research OS."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT / "projects"
DEFAULTS_PATH = ROOT / "config" / "defaults.json"

STAGES = [
    {"name": "intake", "gate": "G0"},
    {"name": "topic-intelligence", "gate": "G1"},
    {"name": "paper-architecture", "gate": "G2"},
    {"name": "experiment-design", "gate": "G3"},
    {"name": "experiment-execution", "gate": "G4"},
    {"name": "writing-and-review", "gate": "G5"},
    {"name": "submission-ready", "gate": None},
]

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
PAPER_RE = re.compile(r"^P[0-9]{2}$")


class ResearchCtlError(RuntimeError):
    """A user-correctable workflow error."""


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ResearchCtlError(f"Missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ResearchCtlError(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(payload)
        temp_name = handle.name
    os.replace(temp_name, path)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def validate_slug(slug: str) -> str:
    if not SLUG_RE.fullmatch(slug):
        raise ResearchCtlError(
            "Project slug must be 2-63 lowercase letters, digits or hyphens, "
            "starting with a letter or digit."
        )
    return slug


def validate_paper_id(paper_id: str) -> str:
    if not PAPER_RE.fullmatch(paper_id):
        raise ResearchCtlError("Paper id must look like P01.")
    return paper_id


def project_dir(slug: str) -> Path:
    return PROJECTS_ROOT / validate_slug(slug)


def state_path(slug: str) -> Path:
    return project_dir(slug) / "state" / "run.json"


def load_state(slug: str) -> dict[str, Any]:
    state = read_json(state_path(slug))
    index = state.get("stage_index")
    if not isinstance(index, int) or not 0 <= index < len(STAGES):
        raise ResearchCtlError("State has an invalid stage_index.")
    expected = STAGES[index]
    if state.get("stage") != expected["name"] or state.get("gate") != expected["gate"]:
        raise ResearchCtlError("State stage/gate does not match stage_index.")
    if "paper_statuses" not in state:
        count = int(state.get("paper_count", 1))
        active = state.get("active_paper", "P01")
        state["paper_statuses"] = {
            f"P{number:02d}": (
                "submission_ready"
                if state.get("gate") is None
                else "active" if f"P{number:02d}" == active else "planned"
            )
            for number in range(1, count + 1)
        }
        state["schema_version"] = "2.0"
    return state


def save_state(slug: str, state: dict[str, Any]) -> None:
    state["updated_at"] = now()
    write_json(state_path(slug), state)


def nonempty(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_nonempty_json(path: Path, errors: list[str]) -> dict[str, Any] | None:
    if not nonempty(path):
        errors.append(f"missing or empty: {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON: {path} ({exc})")
        return None
    if not isinstance(value, dict):
        errors.append(f"expected JSON object: {path}")
        return None
    return value


def jsonl_count(path: Path, errors: list[str]) -> int:
    if not nonempty(path):
        errors.append(f"missing or empty: {path}")
        return 0
    count = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSONL at {path}:{line_number}: {exc}")
        count += 1
    return count


def jsonl_objects(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if not nonempty(path):
        errors.append(f"missing or empty: {path}")
        return []
    values: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"invalid JSONL at {path}:{line_number}: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"expected JSON object at {path}:{line_number}")
            continue
        values.append(value)
    return values


def independent_audit_errors(
    project: Path, gate: str, errors: list[str], paper_id: str | None = None
) -> None:
    prefix = f"{gate}-{paper_id}" if paper_id else gate
    audits = sorted((project / "reviews" / "codex").glob(f"{prefix}-*-final.json"))[-1:]
    valid_audit = False
    for path in audits:
        initial_path = path.with_name(path.name.replace("-final.json", "-initial.json"))
        if not nonempty(initial_path):
            errors.append(f"{path.name}: matching initial Codex audit is missing")
            continue
        audit = load_nonempty_json(path, errors)
        if not audit:
            continue
        if audit.get("verdict") != "pass-with-conditions":
            errors.append(f"{path.name}: final Codex verdict must be pass-with-conditions")
        elif audit.get("fatal_findings"):
            errors.append(f"{path.name}: final Codex audit still has fatal findings")
        else:
            valid_audit = True
    if not valid_audit:
        errors.append(f"{gate} requires a passing final independent Codex audit")
    if not nonempty(project / "reviews" / "decision-log.md"):
        errors.append("reviews/decision-log.md must disposition independent findings")


def active_paper_id(slug: str) -> str:
    state = read_json(state_path(slug))
    paper_id = state.get("active_paper")
    return validate_paper_id(str(paper_id))


def gate_errors(slug: str, gate: str | None) -> list[str]:
    project = project_dir(slug)
    errors: list[str] = []
    if gate is None:
        return errors

    if gate == "G0":
        constraints = load_nonempty_json(project / "intake" / "constraints.json", errors)
        if constraints and constraints.get("status") != "ready_for_review":
            errors.append("intake/constraints.json status must be ready_for_review")

    elif gate == "G1":
        jsonl_count(project / "evidence" / "search-log.jsonl", errors)
        shortlist = load_nonempty_json(project / "program" / "topic-shortlist.json", errors)
        if shortlist:
            candidates = shortlist.get("candidates") or shortlist.get("topics")
            if not isinstance(candidates, list) or len(candidates) < 3:
                errors.append("topic-shortlist.json requires at least three candidates")
        for rel in ["program/core-thesis.json", "program/extension-thesis.json"]:
            value = load_nonempty_json(project / rel, errors)
            if value and value.get("status") not in {"ready_for_review", "approved"}:
                errors.append(f"{rel} status must be ready_for_review")
        if not nonempty(project / "program" / "topic-decision.md"):
            errors.append("missing or empty: program/topic-decision.md")
        independent_audit_errors(project, gate, errors)

    elif gate == "G2":
        load_nonempty_json(project / "program" / "paper-map.json", errors)
        paper_dirs = sorted((project / "papers").glob("P[0-9][0-9]"))
        state = read_json(state_path(slug))
        if len(paper_dirs) != state.get("paper_count"):
            errors.append(
                f"expected exactly {state.get('paper_count')} paper directories, found {len(paper_dirs)}"
            )
        for paper_dir in paper_dirs:
            contract = load_nonempty_json(paper_dir / "paper-contract.json", errors)
            if contract and contract.get("status") not in {"ready_for_review", "approved"}:
                errors.append(
                    f"{paper_dir.name}/paper-contract.json must be ready_for_review"
                )
            if contract:
                for field in ("working_title", "research_question", "distinct_contribution"):
                    if not str(contract.get(field, "")).strip():
                        errors.append(f"{paper_dir.name}/paper-contract.json needs {field}")
                if not contract.get("falsification_conditions"):
                    errors.append(
                        f"{paper_dir.name}/paper-contract.json needs falsification conditions"
                    )
        independent_audit_errors(project, gate, errors)

    elif gate == "G3":
        datasets = jsonl_objects(project / "data" / "datasets.jsonl", errors)
        if len(datasets) < 1:
            errors.append("at least one licensed dataset manifest is required")
        try:
            try:
                from scripts.dataset_fetch import validate_manifest
            except ModuleNotFoundError:
                from dataset_fetch import validate_manifest  # type: ignore[no-redef]
            for index, dataset in enumerate(datasets, 1):
                for issue in validate_manifest(dataset):
                    errors.append(f"datasets.jsonl entry {index}: {issue}")
                license_value = dataset.get("license", {})
                if license_value.get("confirmed_by_human") is not True:
                    errors.append(f"datasets.jsonl entry {index}: license needs human confirmation")
                if dataset.get("download", {}).get("sha256") == "pending":
                    errors.append(f"datasets.jsonl entry {index}: SHA-256 remains pending")
        except ImportError as exc:
            errors.append(f"dataset validator unavailable: {exc}")
        plan = load_nonempty_json(project / "experiments" / "plan.json", errors)
        if plan:
            try:
                try:
                    from scripts.experiment_runner import validate_plan
                except ModuleNotFoundError:
                    from experiment_runner import validate_plan  # type: ignore[no-redef]
                errors.extend(f"experiments/plan.json: {issue}" for issue in validate_plan(plan))
            except ImportError as exc:
                errors.append(f"experiment plan validator unavailable: {exc}")
        budget = load_nonempty_json(project / "experiments" / "budget.json", errors)
        if budget:
            if budget.get("status") != "ready_for_review":
                errors.append("experiments/budget.json status must be ready_for_review")
            ceiling = budget.get("hard_ceiling_usd")
            if not isinstance(ceiling, (int, float)) or isinstance(ceiling, bool) or ceiling < 0:
                errors.append("experiments/budget.json needs non-negative hard_ceiling_usd")
        independent_audit_errors(project, gate, errors)

    elif gate == "G4":
        registry = jsonl_objects(project / "experiments" / "registry.jsonl", errors)
        if len(registry) < 1:
            errors.append("at least one experiment registry entry is required")
        plan = load_nonempty_json(project / "experiments" / "plan.json", errors)
        if plan:
            planned = {item.get("run_id") for item in plan.get("runs", []) if isinstance(item, dict)}
            attempted = {item.get("run_id") for item in registry}
            missing = sorted(str(item) for item in planned - attempted)
            if missing:
                errors.append(f"planned runs without registry attempts: {', '.join(missing)}")
        claim_path = project / "claims" / "claim-evidence.csv"
        if not nonempty(claim_path):
            errors.append("missing or empty: claims/claim-evidence.csv")
        else:
            with claim_path.open(newline="", encoding="utf-8") as handle:
                if sum(1 for _ in csv.reader(handle)) < 2:
                    errors.append("claim-evidence.csv needs at least one claim row")
        if not nonempty(project / "reports" / "reproducibility.md"):
            errors.append("missing or empty: reports/reproducibility.md")
        independent_audit_errors(project, gate, errors)

    elif gate == "G5":
        paper_id = active_paper_id(slug)
        paper = project / "papers" / paper_id
        manuscript = any(
            nonempty(path)
            for path in [
                paper / "manuscript" / "main.tex",
                paper / "manuscript" / "main.docx",
            ]
        )
        if not manuscript:
            errors.append(f"{paper_id} requires manuscript/main.tex or manuscript/main.docx")
        venue = load_nonempty_json(paper / "venue.json", errors)
        if venue and not venue.get("g5_reverified_at"):
            errors.append(f"{paper_id}/venue.json needs g5_reverified_at")
        response = paper / "reviews" / "response-matrix.csv"
        if not nonempty(response):
            errors.append(f"{paper_id} requires reviews/response-matrix.csv")
        else:
            with response.open(newline="", encoding="utf-8") as handle:
                if sum(1 for _ in csv.reader(handle)) < 2:
                    errors.append(f"{paper_id} response matrix needs at least one finding row")
        for round_number in (1, 2):
            path = paper / "reviews" / f"round-{round_number}.md"
            if not nonempty(path):
                errors.append(f"{paper_id} requires reviews/round-{round_number}.md")
        citation = load_nonempty_json(paper / "reviews" / "citation-audit.json", errors)
        if citation and citation.get("status") != "pass":
            errors.append(f"{paper_id} citation audit must pass with zero unresolved entries")
        if citation and citation.get("status") == "pass":
            bibliography_value = citation.get("bibliography")
            bibliography = Path(bibliography_value) if isinstance(bibliography_value, str) else None
            if bibliography and not bibliography.is_absolute():
                bibliography = (ROOT / bibliography).resolve()
            if (
                not bibliography
                or not bibliography.is_file()
                or paper.resolve() not in bibliography.resolve().parents
            ):
                errors.append(f"{paper_id} citation audit bibliography is missing or outside the paper")
            elif citation.get("bibliography_sha256") != file_sha256(bibliography):
                errors.append(f"{paper_id} bibliography changed after citation audit")
            manuscript_path = next(
                (
                    path
                    for path in (
                        paper / "manuscript" / "main.tex",
                        paper / "manuscript" / "main.docx",
                    )
                    if path.is_file()
                ),
                None,
            )
            if (
                manuscript_path
                and citation.get("manuscript_sha256") != file_sha256(manuscript_path)
            ):
                errors.append(f"{paper_id} manuscript changed after citation audit")
        compliance = load_nonempty_json(
            paper / "reviews" / "venue-compliance.json", errors
        )
        if compliance and compliance.get("status") != "pass":
            errors.append(f"{paper_id} venue compliance report must pass")
        if compliance and compliance.get("status") == "pass":
            manuscript_record = compliance.get("manuscript", {})
            manuscript_path = next(
                (
                    path
                    for path in (
                        paper / "manuscript" / "main.tex",
                        paper / "manuscript" / "main.docx",
                    )
                    if path.is_file()
                ),
                None,
            )
            if (
                not manuscript_path
                or manuscript_record.get("sha256") != file_sha256(manuscript_path)
            ):
                errors.append(f"{paper_id} manuscript changed after venue compliance check")
            venue_path = paper / "venue.json"
            if venue_path.is_file() and compliance.get("venue_sha256") != file_sha256(venue_path):
                errors.append(f"{paper_id} venue manifest changed after compliance check")
            try:
                try:
                    from scripts.venue_compliance import audit_template
                except ModuleNotFoundError:
                    from venue_compliance import audit_template  # type: ignore[no-redef]
                current_template = audit_template(paper / "venue-template")
                if current_template.get("status") != "pass":
                    errors.append(f"{paper_id} venue template changed after compliance check")
            except (ImportError, OSError, RuntimeError) as exc:
                errors.append(f"{paper_id} cannot recheck venue template: {exc}")
        disclosures = load_nonempty_json(paper / "disclosures.json", errors)
        if disclosures and disclosures.get("status") != "ready_for_review":
            errors.append(f"{paper_id}/disclosures.json status must be ready_for_review")
        if disclosures:
            for field in ("author_contributions", "conflicts", "funding", "ethics", "ai_use"):
                if field not in disclosures:
                    errors.append(f"{paper_id}/disclosures.json needs {field}")
        independent_audit_errors(project, gate, errors, paper_id)

    else:
        errors.append(f"unknown gate: {gate}")

    return errors


def artifact_hash(slug: str, gate: str) -> str:
    project = project_dir(slug)
    digest = hashlib.sha256()
    for path in sorted(project.rglob("*")):
        relative_path = path.relative_to(project)
        if (
            not path.is_file()
            or relative_path.parts[0] == "state"
            or "raw" in relative_path.parts
            or "venue-template" in relative_path.parts
            or "build" in relative_path.parts
            or relative_path.parts[:2] == ("experiments", "runs")
        ):
            continue
        relative = relative_path.as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    digest.update(gate.encode("ascii"))
    return digest.hexdigest()


def initialize(args: argparse.Namespace) -> None:
    slug = validate_slug(args.project)
    destination = project_dir(slug)
    if destination.exists():
        raise ResearchCtlError(f"Project already exists: {destination}")

    defaults = read_json(DEFAULTS_PATH)
    paper_count = args.paper_count or int(defaults["paper_count"])
    if not 1 <= paper_count <= 20:
        raise ResearchCtlError("paper-count must be between 1 and 20")

    directories = [
        "state",
        "intake",
        "program",
        "evidence/claude-science",
        "data/raw",
        "data/processed",
        "experiments/runs",
        "claims",
        "reports",
        "reviews/codex",
    ]
    for rel in directories:
        (destination / rel).mkdir(parents=True, exist_ok=True)

    constraints = {
        "schema_version": "1.0",
        "status": "needs_user_input",
        "research_goal": None,
        "preferred_domains": ["AI", "robotics", "mechanical engineering"],
        "candidate_application_routes": [
            "France PhD or industrial doctorate",
            "Spain PhD or industrial doctorate",
            "Netherlands EngD",
            "United Kingdom PhD",
            "Japan PhD",
            "Hong Kong PhD",
            "PhD by publication where legally and institutionally available",
        ],
        "time_horizon_years": None,
        "weekly_hours": None,
        "cash_budget_usd": None,
        "cloud_compute_budget_usd": defaults["compute"]["default_cloud_budget_usd"],
        "local_compute": {
            "gpu": None,
            "ram_gb": None,
            "storage_gb": None,
        },
        "equipment": "No institutional laboratory assumed",
        "data_constraint": "Prefer public or authorized datasets",
        "ranking_weights": {
            "novelty_and_doctoral_depth": None,
            "feasibility_without_lab": None,
            "funded_position_supply": None,
            "competition": None,
            "job_market_and_salary": None,
            "background_fit": None,
        },
        "excluded_domains": [],
        "ethics_or_legal_constraints": [],
        "notes": [],
    }
    write_json(destination / "intake" / "constraints.json", constraints)

    capabilities = {
        "schema_version": "1.0",
        "status": "unverified",
        "os": "Windows 11 with WSL2 recommended",
        "orchestrator": "Claude Code",
        "evidence_workbench": "Claude Science export contract",
        "independent_auditor": "Codex MCP",
        "checked_at": None,
        "environment_report": None,
    }
    write_json(destination / "intake" / "capabilities.json", capabilities)
    write_text(destination / "evidence" / "search-log.jsonl", "")
    write_text(destination / "data" / "datasets.jsonl", "")
    write_text(destination / "experiments" / "registry.jsonl", "")
    write_text(
        destination / "claims" / "claim-evidence.csv",
        "claim_id,paper_id,claim,evidence_ids,analysis_ids,support,uncertainty,status\n",
    )

    for number in range(1, paper_count + 1):
        paper_id = f"P{number:02d}"
        paper = destination / "papers" / paper_id
        for rel in ["manuscript", "figures", "tables", "supplement", "reviews"]:
            (paper / rel).mkdir(parents=True, exist_ok=True)
        write_json(
            paper / "paper-contract.json",
            {
                "schema_version": "1.0",
                "paper_id": paper_id,
                "working_title": "",
                "research_question": "",
                "distinct_contribution": "",
                "relationship_to_core": "",
                "relationship_to_extension": "",
                "hypotheses": [],
                "datasets": [],
                "experiments": [],
                "falsification_conditions": [],
                "dependencies": [],
                "target_venues": [],
                "status": "draft",
            },
        )

    state = {
        "schema_version": "2.0",
        "project": slug,
        "created_at": now(),
        "updated_at": now(),
        "stage_index": 0,
        "stage": STAGES[0]["name"],
        "gate": STAGES[0]["gate"],
        "status": "awaiting_work",
        "active_paper": "P01",
        "paper_count": paper_count,
        "paper_statuses": {
            f"P{number:02d}": ("active" if number == 1 else "planned")
            for number in range(1, paper_count + 1)
        },
        "approved_gates": [],
        "approvals": [],
        "history": [
            {
                "at": now(),
                "event": "project_initialized",
                "stage": STAGES[0]["name"],
            }
        ],
    }
    save_state(slug, state)

    venue_id = args.venue or defaults.get("trial_venue")
    if venue_id:
        set_venue_values(slug, "P01", venue_id)

    print(f"Initialized {destination}")
    print("Next: complete intake/constraints.json and stop at G0.")


def print_status(args: argparse.Namespace) -> None:
    state = load_state(args.project)
    errors = gate_errors(args.project, state["gate"])
    output = {
        **state,
        "gate_ready": not errors and state["gate"] is not None,
        "gate_errors": errors,
    }
    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"Project: {state['project']}")
        print(f"Stage:   {state['stage']}")
        print(f"Gate:    {state['gate'] or '-'}")
        print(f"Status:  {state['status']}")
        print(f"Ready:   {'yes' if output['gate_ready'] else 'no'}")
        for error in errors:
            print(f"  - {error}")


def check_gate(args: argparse.Namespace) -> None:
    state = load_state(args.project)
    gate = args.gate or state["gate"]
    errors = gate_errors(args.project, gate)
    if errors:
        print(f"{gate} is not ready:")
        for error in errors:
            print(f"  - {error}")
        raise ResearchCtlError(f"{len(errors)} gate requirement(s) remain")
    print(f"{gate} artifact checks passed.")


def mark_ready(args: argparse.Namespace) -> None:
    state = load_state(args.project)
    gate = state["gate"]
    if gate is None:
        raise ResearchCtlError("Project is already submission-ready.")
    errors = gate_errors(args.project, gate)
    if errors:
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        raise ResearchCtlError(f"{gate} cannot be marked ready")
    state["status"] = "awaiting_approval"
    state["history"].append(
        {"at": now(), "event": "gate_marked_ready", "gate": gate, "note": args.note}
    )
    save_state(args.project, state)
    print(f"{gate} is awaiting explicit human approval.")


def approve(args: argparse.Namespace) -> None:
    state = load_state(args.project)
    gate = state["gate"]
    if gate != args.gate:
        raise ResearchCtlError(f"Current gate is {gate}, not {args.gate}.")
    if state["status"] != "awaiting_approval":
        raise ResearchCtlError("Run gate-check and ready before approval.")
    errors = gate_errors(args.project, gate)
    if errors:
        raise ResearchCtlError("Gate artifacts changed and no longer pass checks.")
    if not args.actor.strip():
        raise ResearchCtlError("actor must identify the human approver")

    approval = {
        "gate": gate,
        "actor": args.actor.strip(),
        "at": now(),
        "note": args.note,
        "artifact_sha256": artifact_hash(args.project, gate),
    }
    if gate == "G3":
        project = project_dir(args.project)
        approval["experiment_plan_sha256"] = hashlib.sha256(
            (project / "experiments" / "plan.json").read_bytes()
        ).hexdigest()
        approval["experiment_budget_sha256"] = hashlib.sha256(
            (project / "experiments" / "budget.json").read_bytes()
        ).hexdigest()
    approval_key = gate
    if gate == "G5":
        approval["paper_id"] = state["active_paper"]
        approval_key = f"G5:{state['active_paper']}"
    state["approvals"].append(approval)
    if approval_key not in state["approved_gates"]:
        state["approved_gates"].append(approval_key)
    state["status"] = "approved"
    state["history"].append({"at": now(), "event": "gate_approved", "gate": gate})
    save_state(args.project, state)
    print(f"Recorded human approval for {gate}. Run advance to continue.")


def advance(args: argparse.Namespace) -> None:
    state = load_state(args.project)
    gate = state["gate"]
    if gate is None:
        raise ResearchCtlError("Project is already at the final stage.")
    approval_key = f"G5:{state['active_paper']}" if gate == "G5" else gate
    if state["status"] != "approved" or approval_key not in state["approved_gates"]:
        raise ResearchCtlError(f"{gate} has not been approved.")
    matching_approval = next(
        (
            item
            for item in reversed(state.get("approvals", []))
            if item.get("gate") == gate
            and (gate != "G5" or item.get("paper_id") == state["active_paper"])
        ),
        None,
    )
    if not matching_approval or matching_approval.get("artifact_sha256") != artifact_hash(
        args.project, gate
    ):
        raise ResearchCtlError(
            "Artifacts changed after approval; run gate-check, ready and approve again."
        )
    if gate == "G5":
        completed = state["active_paper"]
        state.setdefault("paper_statuses", {})[completed] = "submission_ready"
        remaining = [
            f"P{number:02d}"
            for number in range(1, int(state["paper_count"]) + 1)
            if state["paper_statuses"].get(f"P{number:02d}") != "submission_ready"
        ]
        if remaining:
            next_paper = remaining[0]
            state["active_paper"] = next_paper
            state["paper_statuses"][next_paper] = "active"
            state["status"] = "awaiting_work"
            state["history"].append(
                {
                    "at": now(),
                    "event": "paper_advanced",
                    "from": completed,
                    "to": next_paper,
                }
            )
            save_state(args.project, state)
            print(f"Marked {completed} submission-ready; continuing G5 with {next_paper}.")
            return
    next_index = state["stage_index"] + 1
    next_stage = STAGES[next_index]
    previous = state["stage"]
    state["stage_index"] = next_index
    state["stage"] = next_stage["name"]
    state["gate"] = next_stage["gate"]
    state["status"] = (
        "submission_ready" if next_stage["gate"] is None else "awaiting_work"
    )
    state["history"].append(
        {
            "at": now(),
            "event": "stage_advanced",
            "from": previous,
            "to": next_stage["name"],
        }
    )
    save_state(args.project, state)
    print(f"Advanced to {next_stage['name']}.")


def set_venue_values(slug: str, paper_id: str, venue_id: str) -> None:
    validate_paper_id(paper_id)
    source = ROOT / "venues" / venue_id / "venue.json"
    if not source.is_file():
        raise ResearchCtlError(f"Unknown venue manifest: {venue_id}")
    target_paper = project_dir(slug) / "papers" / paper_id
    if not target_paper.is_dir():
        raise ResearchCtlError(f"Unknown paper: {paper_id}")
    manifest = read_json(source)
    manifest["selected_at"] = now()
    manifest["selection_status"] = "trial" if manifest.get("trial_only") else "candidate"
    write_json(target_paper / "venue.json", manifest)


def set_venue(args: argparse.Namespace) -> None:
    load_state(args.project)
    set_venue_values(args.project, args.paper, args.venue)
    print(f"Set {args.paper} venue to {args.venue}; G5 re-verification remains required.")


def list_stages(_: argparse.Namespace) -> None:
    print(json.dumps(STAGES, indent=2))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="Create a new research project")
    init.add_argument("--project", required=True)
    init.add_argument("--paper-count", type=int)
    init.add_argument("--venue", default=None)
    init.set_defaults(func=initialize)

    status = commands.add_parser("status", help="Show project state")
    status.add_argument("--project", required=True)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=print_status)

    check = commands.add_parser("gate-check", help="Validate gate artifacts")
    check.add_argument("--project", required=True)
    check.add_argument("--gate")
    check.set_defaults(func=check_gate)

    ready = commands.add_parser("ready", help="Mark current gate ready for human review")
    ready.add_argument("--project", required=True)
    ready.add_argument("--note", default="")
    ready.set_defaults(func=mark_ready)

    approve_cmd = commands.add_parser("approve", help="Record explicit human approval")
    approve_cmd.add_argument("--project", required=True)
    approve_cmd.add_argument("--gate", required=True)
    approve_cmd.add_argument("--actor", required=True)
    approve_cmd.add_argument("--note", default="")
    approve_cmd.set_defaults(func=approve)

    advance_cmd = commands.add_parser("advance", help="Move to the next approved stage")
    advance_cmd.add_argument("--project", required=True)
    advance_cmd.set_defaults(func=advance)

    venue = commands.add_parser("set-venue", help="Copy a venue manifest to a paper")
    venue.add_argument("--project", required=True)
    venue.add_argument("--paper", required=True)
    venue.add_argument("--venue", required=True)
    venue.set_defaults(func=set_venue)

    stages = commands.add_parser("stages", help="List the workflow stages")
    stages.set_defaults(func=list_stages)
    return root


def main(argv: Iterable[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        args.func(args)
        return 0
    except ResearchCtlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
