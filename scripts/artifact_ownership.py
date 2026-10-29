"""Control-plane ownership of executed facts, including plan-declared outputs."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

EXECUTOR_ROOTS = ("experiments/runs", "results", "data/acquisition", "reports/research-extensions",
                  "reports/data-contracts", "reports/data-cleaning", "reports/empirical-reporting",
                  "evidence/economic-data", "data/raw/economic-data", "data/processed", "data/processed-preview",
                  "reports/word-render", "reports/review-packets", "reports/research-increments",
                  "reports/manuscript-hygiene", "reports/reviewer-rounds",
                  "reports/publication-disclosure", "reports/statistical-watermarks",
                  "reports/literature-workbench", "reports/literature-intelligence",
                  "reports/literature-analysis", "reports/literature-feedback",
                  "reports/literature-retrieval", "reports/literature-reading", "reports/literature-matrix",
                  "reports/literature-benchmark",
                  "reports/literature-semantic", "reports/literature-pdf", "reports/literature-zotero",
                  "reports/literature-roles", "reports/literature-comparison", "reports/literature-paperqa",
                  "reports/data-row-provenance", "reports/literature-source-tasks",
                  "reports/literature-search-strategy", "reports/literature-synthesis", "reports/diagram-mermaid",
                  "reports/ccfa-tasks", "reports/ccfa-science", "reports/ccfa-humanization", "reports/research-toolkit",
                  "reports/research-iteration", "reports/research-frontier",
                  "reports/figure-panel-cache",
                  "reports/figure-data", "reports/figure-gallery", "reports/figure-gallery-semantic",
                  "reports/figure-story", "reports/figure-visual-style", "literature/figure-gallery",
                  "experiments/history", "experiments/recovery-artifacts",
                  "state/primary-recovery", "state/review-receipts", "state/scientific-scope", "state/scientific-scope-amendments")
EXECUTOR_FILES = {"experiments/registry.jsonl", "reports/evidence-retrieval/latest.json",
                  "program/topic-leads.json", "program/literature-progress.json"}


def declared_outputs(root: Path) -> set[str]:
    """Include old registry outputs even if a writer proposes a different plan."""
    values: set[str] = set()
    plan = root / "experiments/plan.json"
    if plan.is_file():
        try:
            value = json.loads(plan.read_text(encoding="utf-8"))
            for run in value.get("runs", []):
                values.update(p for p in run.get("expected_outputs", []) if isinstance(p, str))
            state_path = root / "state/run.json"
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
            if state.get("stage") in {"experiment-execution", "writing-and-review", "submission-ready"}:
                values.update({"experiments/plan.json", "experiments/budget.json"})
                for prereg in (root / "papers").glob("P[0-9][0-9]/preregistration.json"):
                    values.add(prereg.relative_to(root).as_posix())
                    frozen = json.loads(prereg.read_text(encoding="utf-8"))
                    values.update(item["path"] for item in frozen.get("files", [])
                                  if isinstance(item, dict) and isinstance(item.get("path"), str))
                values.update(item["path"] for run in value.get("runs", []) for item in run.get("inputs", [])
                              if isinstance(item, dict) and isinstance(item.get("path"), str))
        except (ValueError, TypeError, AttributeError):
            pass  # A draft plan can be repaired; it grants no execution authority.
    registry = root / "experiments/registry.jsonl"
    if registry.is_file():
        try:
            for line in registry.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    entry = json.loads(line)
                    values.update(p["path"] for p in entry.get("outputs", [])
                                  if isinstance(p, dict) and isinstance(p.get("path"), str))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ValueError("Executor registry is invalid; control-plane inspection is required") from exc
    return {PurePosixPath(p).as_posix().casefold() for p in values}


def executor_owned(root: Path, relative: str, outputs: set[str] | None = None) -> bool:
    value = PurePosixPath(relative).as_posix().casefold()
    parts = PurePosixPath(relative).parts
    if value == "intake/constraints.json":
        # G0 writers may prepare intake, but an approved owner's constraints can
        # change only through the authenticated operating-amendment controller.
        # Both API target validation and CLI snapshot/restoration use this rule.
        state_path = root / "state/run.json"
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise ValueError("Cannot establish approved intake ownership from workflow state") from exc
            if not isinstance(state, dict):
                raise ValueError("Cannot establish approved intake ownership from workflow state")
            approved_gates = state.get("approved_gates", [])
            if not isinstance(approved_gates, list) or any(not isinstance(gate, str) for gate in approved_gates):
                raise ValueError("Cannot establish approved intake ownership from workflow state")
            if "G0" in approved_gates:
                return True
    if len(parts) >= 6 and value.startswith("experiments/supplemental/"):
        child = root.joinpath(*parts[:5])
        child_relative = PurePosixPath(*parts[5:]).as_posix()
        child_lower = child_relative.casefold()
        if child_lower.startswith(("state/", "reviews/independent/", "reviews/codex/", "data/quality/", "data/acquisition/")) or child_lower in {
                "evidence/literature-api-ledger.jsonl", "evidence/search-log.jsonl", "reviews/decision-log.md"}:
            return True
        return executor_owned(child, child_relative)
    return (value in EXECUTOR_FILES
            or value.endswith((".editable.svg", ".editable.pptx", ".editable.drawio",
                               ".editable-export.json", ".editable-layout.json", ".editable-source.json", ".editable.renderer.py"))
            or (len(parts) >= 5 and value.startswith("papers/") and parts[2:4] == ("figures", "source-data"))
            or (len(PurePosixPath(value).parts) >= 5 and value.startswith("papers/")
                and PurePosixPath(value).parts[2] == "supplement"
                and PurePosixPath(value).parts[3] in {"study-results", "reviewer-experiments"})
            or (len(PurePosixPath(value).parts) == 3 and value.startswith("papers/")
                and value.endswith("/study-validation-confirmation.json"))
            or (len(PurePosixPath(value).parts) == 4 and value.startswith("papers/")
                and value.endswith("/reviews/cloud-word-build.json"))
            or (len(PurePosixPath(value).parts) == 4 and value.startswith("papers/")
                and value.endswith("/reviews/citation-audit.json"))
            or (len(PurePosixPath(value).parts) == 4 and value.startswith("papers/")
                and value.endswith("/reviews/manuscript-audit.json"))
            or (len(parts) == 4 and value.startswith("papers/")
                and (value.endswith("/reviews/empirical-design.json") or value.endswith("/tables/empirical-estimates.csv")))
            or (len(PurePosixPath(value).parts) == 4 and value.startswith("papers/")
                and value.endswith("/reviews/ccfa-humanization.json"))
            or (len(PurePosixPath(value).parts) == 3 and value.startswith("papers/")
                and value.endswith("/experiment-evidence.json"))
            or any(value == prefix or value.startswith(prefix + "/") for prefix in EXECUTOR_ROOTS)
            or value in (declared_outputs(root) if outputs is None else outputs))


def executor_snapshot(root: Path) -> dict[str, bytes]:
    outputs = declared_outputs(root)
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and executor_owned(root, p.relative_to(root).as_posix(), outputs)}
