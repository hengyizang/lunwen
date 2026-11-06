"""Paper-scoped G3-G5 work inside the existing project and executor.

The portfolio keeps one doctoral scope, state manager, model ledger and compute
ceiling. A paper owns its protocol and receipts; another paper's draft cannot
change them. Existing executed batch protocols keep their original authority.
"""
from __future__ import annotations

import csv
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import io
import json
import re
from pathlib import Path

ALIASES = {
    "experiments/plan.json": "experiments/papers/{paper}/plan.json",
    "experiments/budget.json": "experiments/papers/{paper}/budget.json",
    "experiments/registry.jsonl": "experiments/papers/{paper}/registry.jsonl",
    "experiments/quality-G3.json": "experiments/papers/{paper}/quality-G3.json",
    "reports/quality-G4.json": "papers/{paper}/reviews/quality-G4.json",
    "reports/reproducibility.md": "papers/{paper}/reports/reproducibility.md",
    "reports/runtime-evidence-catalog.json": "papers/{paper}/reports/runtime-evidence-catalog.json",
    "claims/claim-evidence.csv": "claims/papers/{paper}/claim-evidence.csv",
}
_SCOPES = ContextVar("paper_execution_scopes", default={})


def state(project: Path) -> dict:
    path = project / "state/run.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def enabled(project: Path) -> bool:
    return state(project).get("paper_execution_mode") == "independent"


def selected(project: Path, paper_id: str | None = None) -> str:
    value = state(project)
    paper = paper_id or _SCOPES.get().get(str(project.resolve())) or value.get("active_paper")
    count = value.get("paper_count")
    if (not isinstance(paper, str) or not re.fullmatch(r"P[0-9]{2}", paper)
            or type(count) is not int or paper not in {f"P{n:02d}" for n in range(1, count + 1)}):
        raise ValueError("independent execution requires a declared active paper")
    return paper


@contextmanager
def scope(project: Path, paper_id: str):
    """Read another paper's evidence without changing workflow state or files."""
    paper = selected(project, paper_id)
    token = _SCOPES.set({**_SCOPES.get(), str(project.resolve()): paper})
    try:
        yield
    finally:
        _SCOPES.reset(token)


def paper_scoped(function):
    """Bind nested native evidence helpers to their explicit paper argument."""
    signature = inspect.signature(function)
    @wraps(function)
    def wrapped(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        project, paper = bound.arguments.get("project"), bound.arguments.get("paper_id")
        if isinstance(project, Path) and paper is not None and enabled(project):
            with scope(project, paper):
                return function(*args, **kwargs)
        return function(*args, **kwargs)
    return wrapped


def artifact_path(project: Path, relative: str, paper_id: str | None = None) -> Path:
    from scripts.research_artifacts import path_in
    if relative in ALIASES and enabled(project):
        relative = ALIASES[relative].format(paper=selected(project, paper_id))
    return path_in(project, relative, exists=False)


def primary_registry_paths(project: Path) -> list[Path]:
    """Read historical paper evidence together without changing active focus."""
    from scripts.research_artifacts import path_in
    return [path_in(project,p.relative_to(project).as_posix()) for p in [project/"experiments/registry.jsonl",
                       *sorted((project/"experiments/papers").glob("P[0-9][0-9]/registry.jsonl"))] if p.is_file()]


def papers(project: Path, gate: str | None = None) -> list[str]:
    value = state(project)
    if enabled(project) and (gate or value.get("gate")) in {"G3", "G4", "G5"}:
        return [selected(project)]
    return [p.name for p in sorted((project / "papers").glob("P[0-9][0-9]"))]


def relevant(project: Path, relative: str, paper_id: str | None = None) -> bool:
    """Keep shared topic contracts and the selected paper's experimental work."""
    if not enabled(project):
        return True
    paper = selected(project, paper_id)
    parts = Path(relative).parts
    if relative in ALIASES or relative == "data/datasets.jsonl":
        return False  # Unexecuted legacy master files are not active protocols.
    if len(parts) >= 2 and parts[0] == "papers" and re.fullmatch(r"P[0-9]{2}", parts[1]):
        return parts[1] == paper
    if len(parts) >= 3 and parts[:2] in {("experiments", "papers"), ("claims", "papers")}:
        return parts[2] == paper
    if len(parts)>=3 and parts[:2]==("experiments","supplemental"):
        return parts[2]==paper
    if len(parts)>=3 and parts[:2]==("experiments","history"):
        archived = re.match(r"exploration-(P[0-9]{2})-", parts[2])
        if archived:
            return archived[1] == paper
    if len(parts)>=3 and parts[:2] in {("data","processed"),("reports","data-cleaning")} and re.fullmatch(r"P[0-9]{2}",parts[2]):
        return parts[2]==paper
    if len(parts)==3 and parts[:2] in {("data","quality"),("data","acquisition"),("data","manifests"),
                                       ("data","contracts"),("data","processed-preview"),("reports","data-contracts")}:
        contract=json.loads((project/"papers"/paper/"paper-contract.json").read_text(encoding="utf-8"))
        wanted=set(contract.get("datasets",[]))
        if parts[1] in {"manifests","contracts","data-contracts"}:
            path=project/relative
            if path.is_file() and path.suffix==".json":
                return json.loads(path.read_text(encoding="utf-8")).get("dataset_id") in wanted
        else:
            return parts[2] in {name+suffix for name in wanted for suffix in (".json","-confirmation.json",".csv")}
    if len(parts)==3 and parts[:2]==("reports","data-cleaning") and parts[2].startswith("preview-"):
        contract=json.loads((project/"papers"/paper/"paper-contract.json").read_text(encoding="utf-8"))
        return parts[2] in {"preview-"+name+".json" for name in contract.get("datasets",[])}
    if len(parts) >= 2 and parts[0] == "results":
        return parts[1] == paper
    if len(parts) >= 3 and parts[:2] == ("experiments","runs"):
        registry = project / "experiments/papers" / paper / "registry.jsonl"
        rows = [json.loads(line) for line in registry.read_text(encoding="utf-8").splitlines() if line.strip()] if registry.is_file() else []
        return parts[2] in {row.get("attempt_id") for row in rows}
    return True


def plan_errors(project: Path, plan: dict) -> list[str]:
    if not enabled(project):
        return []
    paper = selected(project)
    errors = []
    for run in plan.get("runs", []):
        if not isinstance(run, dict):
            continue
        if run.get("paper_id") != paper:
            errors.append("the active paper plan cannot execute another paper")
        if not str(run.get("run_id", "")).startswith(paper + "-"):
            errors.append("independent run IDs must be prefixed with " + paper + "-")
        prefixes = (f"results/{paper}/", f"papers/{paper}/results/")
        argv = run.get("argv", [])
        if len(argv) > 1 and argv[1] == "analysis/data_cleaning_runtime.py":
            prefixes += (f"data/processed/{paper}/", f"reports/data-cleaning/{paper}/")
        for output in run.get("expected_outputs", []):
            if not isinstance(output, str) or not output.startswith(prefixes):
                errors.append("independent outputs must use this paper's results or native cleaning scope: " + paper)
                continue
            from scripts.research_artifacts import path_in
            try:
                path_in(project, output, exists=False)
            except ValueError as exc:
                errors.append("independent output path: " + str(exc))
    return errors


def approval(project: Path, gate: str, paper_id: str | None = None) -> dict | None:
    scoped = enabled(project) and gate in {"G3", "G4", "G5"}
    paper = selected(project, paper_id) if scoped else paper_id
    value = state(project)
    if scoped and f"{gate}:{paper}" not in value.get("approved_gates",[]):
        return None
    return next((a for a in reversed(value.get("approvals", []))
                 if a.get("gate") == gate and (not scoped or a.get("paper_id") == paper)), None)


def dataset_snapshot(project: Path, paper_id: str | None = None) -> Path:
    if not enabled(project):
        return project / "data/datasets.jsonl"
    paper = selected(project, paper_id)
    return project / "experiments/papers" / paper / "datasets.jsonl"


def refreshable_preregistration(project: Path, paper_id: str) -> bool:
    """Only the current, unsealed controller draft may follow author revisions.

    The preregistration file remains controller owned. Actual execution or a G3
    decision locks its scientific inputs; another paper never gets this exception.
    """
    from scripts.research_artifacts import read, sha
    from scripts.output_provenance import current_origin
    try:
        value = state(project)
        if (value.get("gate"), value.get("stage"), value.get("status"), value.get("active_paper")) != (
                "G3", "experiment-design", "awaiting_work", paper_id):
            return False
        gate_key = f"G3:{paper_id}" if enabled(project) else "G3"
        if (project / "state/experiment-execution-lease.json").exists() or gate_key in value.get("approved_gates", []) or approval(project, "G3", paper_id):
            return False
        registry = artifact_path(project, "experiments/registry.jsonl", paper_id)
        if registry.is_file() and registry.read_text(encoding="utf-8").strip():
            return False
        plan = artifact_path(project, "experiments/plan.json", paper_id)
        if not plan.is_file():
            return False
        plan_hash = sha(plan)
        for receipt in (project / "experiments/runs").glob("*/run.json"):
            item = read(receipt)
            if item.get("paper_id") == paper_id and item.get("approved_plan_sha256") == plan_hash:
                return False
        path = project / "papers" / paper_id / "preregistration.json"
        report = read(path)
        origin = current_origin(project, path)
        return (report.get("paper_id") == paper_id and report.get("status") == "frozen"
                and report.get("human_confirmation") is False and report.get("confirmation_kind") == "automated"
                and report.get("frozen_by") == "deterministic_control_plane" and origin.get("status") == "tracked"
                and origin.get("provider") == "automated-quality-control" and origin.get("model") == "scripts/automated_quality.py")
    except (OSError, ValueError, KeyError, TypeError):
        return False


def prepare_datasets(project: Path) -> None:
    """Freeze only selected manifest rows; raw data and rights stay canonical."""
    if not enabled(project):
        return
    from scripts.research_artifacts import read, record
    paper = selected(project)
    contract = read(project / "papers" / paper / "paper-contract.json")
    wanted = set(contract.get("datasets", []))
    source = project / "data/datasets.jsonl"
    rows = [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()] if source.is_file() else []
    found = [row for row in rows if row.get("dataset_id") in wanted]
    if {row.get("dataset_id") for row in found} != wanted or len(found) != len(wanted):
        raise ValueError("the active paper still needs its exact dataset manifests")
    payload = "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in sorted(found, key=lambda r: r["dataset_id"]))
    target = dataset_snapshot(project)
    if target.is_file() and target.read_text(encoding="utf-8") == payload:
        return
    prereg = project / "papers" / paper / "preregistration.json"
    if (prereg.is_file() and not refreshable_preregistration(project, paper)) or approval(project, "G3"):
        raise ValueError("the selected dataset manifest changed after protocol freezing")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(payload, encoding="utf-8")
    record(project, [target], "scripts/paper_execution.py")


def enable(project: Path) -> None:
    """Losslessly split unexecuted plans after the existing G2 topic decisions.

    This runs in researchctl.advance, never in a model response. Previously
    executed/frozen projects must finish or explicitly retire their old protocol.
    """
    from scripts.research_artifacts import read, write, record
    value = state(project)
    if value.get("gate") != "G2" or value.get("status") != "approved":
        raise ValueError("independent execution starts after checked human G2 topic decisions")
    if any(a.get("gate") in {"G3", "G4", "G5"} for a in value.get("approvals", [])):
        raise ValueError("do not silently migrate an already sealed experiment protocol")
    registry = project / "experiments/registry.jsonl"
    if (registry.is_file() and registry.read_text(encoding="utf-8").strip()) or list((project / "papers").glob("P[0-9][0-9]/preregistration.json")):
        raise ValueError("executed or frozen experiments require their original recorded protocol")
    plan = read(project / "experiments/plan.json")
    budget = read(project / "experiments/budget.json")
    created = []
    for paper in papers(project, "G2"):
        root = project / "experiments/papers" / paper
        for name, data in (("plan.json", {**plan, "runs": [r for r in plan.get("runs", []) if r.get("paper_id") == paper]}), ("budget.json", budget)):
            target = root / name
            if not target.exists():
                write(target, data)
                created.append(target)
        target = project / "claims/papers" / paper / "claim-evidence.csv"
        if not target.exists():
            source = project / "claims/claim-evidence.csv"
            content = source.read_text(encoding="utf-8") if source.is_file() else "claim_id,paper_id,claim,evidence_ids,analysis_ids,support,uncertainty,status\n"
            reader = csv.DictReader(io.StringIO(content))
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames or [])
            writer.writeheader()
            writer.writerows(row for row in reader if row.get("paper_id") == paper)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(output.getvalue(), encoding="utf-8")
            created.append(target)
    record(project, created, "scripts/paper_execution.py")


def prompt_contract(project: Path) -> str:
    if not enabled(project):
        return ""
    paper = selected(project)
    paths = {name: artifact_path(project, name).relative_to(project).as_posix() for name in ALIASES}
    return ("INDEPENDENT PAPER EXECUTION: Work only on " + paper + " at this stage. "
            "Keep the approved six-paper doctoral mapping. Other papers need not have experiment designs or results yet. "
            "Use these actual canonical paths instead of the legacy batch aliases:\n" + json.dumps(paths, sort_keys=True) +
            "\nUse unique run IDs prefixed with " + paper + "- and result outputs under results/" + paper +
            "/ or the native papers/" + paper + "/results/ contract. Native cleaning may use data/processed/" + paper +
            "/ and reports/data-cleaning/" + paper + "/, with the frozen dataset snapshot declared as an input. "
            "Other papers' sealed inputs and results are immutable. All attempts share the original cumulative project total; "
            "a copied budget declaration is not an extra allowance or a per-paper cap. Never author executor receipts, freezes, approvals or outcomes.")
