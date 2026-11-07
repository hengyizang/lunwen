"""Control-plane ownership of executed facts, including plan-declared outputs."""
from __future__ import annotations

import json
import re
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

PAPER_OBSERVATION_FILES = {
    "watermark-assessment.json", "reviews/pre-submission-checklist.json", "reviews/pre-submission-review.json",
    "reviews/revision-ledger.json", "reviews/revision-ledger-report.json", "reviews/revision-trace.json",
    "reviews/docx-revision.json", "reviews/concern-cards.json"}


def paper_observation_path(relative: str) -> bool:
    """Paper-relative C records, excluded from scientific decision fingerprints."""
    return relative.startswith("style/") or relative in PAPER_OBSERVATION_FILES

EXECUTOR_ROOTS = ("experiments/archive", "experiments/runs", "results", "data/acquisition", "reports/research-extensions",
                  "reports/data-contracts", "reports/data-cleaning", "reports/empirical-reporting",
                  "evidence/economic-data", "evidence/data-rights", "data/raw", "data/processed", "data/processed-preview",
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
                  "reports/research-iteration", "reports/research-frontier", "reports/research-search-tree",
                  "reports/figure-panel-cache",
                  "reports/figure-data", "reports/figure-gallery", "reports/figure-gallery-semantic",
                  "reports/figure-story", "reports/figure-visual-style", "literature/figure-gallery",
                  "experiments/history", "experiments/recovery-artifacts",
                  "state/primary-recovery", "state/review-receipts", "state/scientific-scope", "state/scientific-scope-amendments")
EXECUTOR_FILES = {"experiments/registry.jsonl", "reports/evidence-retrieval/latest.json",
                  "program/topic-leads.json", "program/literature-progress.json"}

# The API target check and CLI snapshot/restoration use this same inventory.
# Executor ownership below additionally covers frozen and plan-declared outputs.
CONTROL_ROOTS = ("state", "reviews/codex", "reviews/independent", "data/quality",
    "evidence/literature", "evidence/direction-sources", "evidence/lead-triage", "evidence/web-search",
    "evidence/journal-sources", "evidence/support-sources", "evidence/model-screening",
    "evidence/model-screening-prepared", "evidence/source-scopes", "literature/readers",
    "reports/watermark-cleanup", "reports/figure-output-qa")
CONTROL_FILES = {"reviews/decision-log.md", "evidence/dataset-search-log.jsonl", "evidence/search-log.jsonl",
    "evidence/literature-api-ledger.jsonl", "evidence/ai4science-ledger.jsonl", "program/venue-candidates.json",
    "program/journal-screening.json", "program/direction-ranking.json", "program/hypothesis-audit.json",
    "program/journal-dossier-report.json", "reports/runtime-evidence-catalog.json",
    "reports/research-support.json", "reports/method-tools.json"}
CONTROL_PATTERNS = ("reports/research-notebook*", "data/discovery-broad-auto-*",
                    "*.render-receipt.json", "*.output-qa.json")


def controller_owned(relative: str) -> bool:
    value = relative.casefold()
    return (value in CONTROL_FILES or _controlled_paper_record(value)
            or any(value == prefix or value.startswith(prefix + "/") for prefix in CONTROL_ROOTS)
            or any(fnmatchcase(value, pattern) for pattern in CONTROL_PATTERNS))


def control_roots(root: Path) -> list[Path]:
    return [*(root / name for name in (*CONTROL_ROOTS, *EXECUTOR_ROOTS)),
            *root.glob("reports/research-notebook*"),
            *root.glob("papers/P[0-9][0-9]/reviews/revision-base")]


def control_files(root: Path) -> list[Path]:
    return [*(root / name for name in CONTROL_FILES),
            *(path for path in root.rglob("*") if controller_owned(path.relative_to(root).as_posix())
              and (path.is_file() or path.is_symlink()))]


def _controlled_paper_record(relative: str) -> bool:
    """Apply the existing authoring boundary to a nested study's paper records."""
    parts = PurePosixPath(relative).parts
    if len(parts) < 3 or parts[0] != "papers" or not re.fullmatch(r"p[0-9]{2}", parts[1]):
        return False
    if len(parts) == 3:
        return parts[2] in {"power-analysis.json", "preregistration.json",
                            "reproduction-confirmation.json", "watermark-assessment.json"}
    if parts[2:] == ("style", "academic-style-audit.json"):
        return True
    if parts[2:4] == ("submission-materials", "revision") or parts[2] == "release-preparation":
        return True
    return parts[2] == "reviews" and parts[3] in {
        "revision-base", "ref-verify.json", "revision-trace.json", "revision-integrity.json",
        "revision-ledger-report.json", "revision-render.json", "cloud-tex-build.json",
        "reporting-guideline.json", "revision-authorizations.json", "revision-base.tex",
        "revision-base.docx", "pre-submission-review.json", "statistical-reporting.json",
        "docx-revision.json",
    }


def declared_outputs(root: Path) -> set[str]:
    """Include old registry outputs even if a writer proposes a different plan."""
    values: set[str] = set()
    from scripts.paper_execution import enabled, refreshable_preregistration
    scoped = enabled(root)
    state_path = root / "state/run.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    preregistrations = sorted((root / "papers").glob("P[0-9][0-9]/preregistration.json"))
    fixed_preregistrations = [p for p in preregistrations if not refreshable_preregistration(root, p.parent.name)]
    plans = [root / "experiments/plan.json", *sorted((root / "experiments/papers").glob("P[0-9][0-9]/plan.json"))]
    for plan in plans:
        if not plan.is_file():
            continue
        try:
            value = json.loads(plan.read_text(encoding="utf-8"))
            for run in value.get("runs", []):
                values.update(p for p in run.get("expected_outputs", []) if isinstance(p, str))
            locked = ((not scoped and state.get("stage") in {"experiment-execution", "writing-and-review", "submission-ready"})
                      or (scoped and any(p.parent.name == plan.parent.name for p in fixed_preregistrations)))
            if locked:
                values.update({plan.relative_to(root).as_posix(), (plan.parent / "budget.json").relative_to(root).as_posix()})
                values.update(item["path"] for run in value.get("runs", []) for item in run.get("inputs", [])
                              if isinstance(item, dict) and isinstance(item.get("path"), str))
            if scoped or locked:
                for prereg in preregistrations:
                    values.add(prereg.relative_to(root).as_posix())
                    if prereg not in fixed_preregistrations:
                        continue
                    frozen = json.loads(prereg.read_text(encoding="utf-8"))
                    values.update(item["path"] for item in frozen.get("files", [])
                                  if isinstance(item, dict) and isinstance(item.get("path"), str))
        except (ValueError, TypeError, AttributeError):
            pass  # A draft plan can be repaired; it grants no execution authority.
    registries = [root / "experiments/registry.jsonl", *sorted((root / "experiments/papers").glob("P[0-9][0-9]/registry.jsonl"))]
    for registry in registries:
        if not registry.is_file():
            continue
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
    from scripts.paper_execution import enabled,selected,ALIASES
    if enabled(root):
        paper = selected(root)
        if value in ALIASES:
            return True
        if len(parts) >= 4 and parts[:2] in {("experiments","papers"),("claims","papers")}:
            if parts[2] != paper or (parts[:2] == ("experiments","papers") and parts[3] in {"registry.jsonl","datasets.jsonl"}):
                return True
        if len(parts) >= 2 and parts[0] == "papers" and re.fullmatch(r"P[0-9]{2}",parts[1]) and parts[1] != paper:
            return True
        if len(parts)==4 and parts[0]=="papers" and parts[2:]==("reports","runtime-evidence-catalog.json"):
            return True
    if len(parts) == 2 and parts[0] == "data" and re.fullmatch(r"discovery-broad-auto-\d{8}T\d{12}Z\.json", parts[1]):
        return True
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
        if _controlled_paper_record(child_lower):
            return True
        if child_lower.startswith(("state/", "reviews/independent/", "reviews/codex/", "data/quality/", "data/acquisition/")) or child_lower in {
                "evidence/literature-api-ledger.jsonl", "evidence/search-log.jsonl", "reviews/decision-log.md"}:
            return True
        return executor_owned(child, child_relative)
    return (value in EXECUTOR_FILES
            or (len(parts) >= 4 and parts[0] == "papers" and parts[2] == "release-preparation")
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
