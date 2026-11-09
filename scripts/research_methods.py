#!/usr/bin/env python3
"""Load reviewed, stage-scoped research methods without provider calls."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

try:
    from scripts import scientific_reasoning
except ImportError:
    import scientific_reasoning

ROOT = Path(__file__).resolve().parents[1]
PEER_REVIEW_PATH = "third_party/kdense/skills/peer-review/SKILL.md"
PEER_REVIEW_SECTIONS = {
    1: ("Establish scope and available evidence", ""),
    2: ("Orient without deciding", ""),
    4: ("Map claims to evidence", "\nRun:\n"),
    5: ("Review methods and statistics", "\nUse `references/"),
    6: ("Review reproducibility and transparency", ""),
    8: ("Review figures, tables, and citations", "\nThis skill has no"),
    9: ("Draft actionable comments", ""),
}


try:
    from scripts.research_artifacts import sha as sha256  # noqa: F401 - compatibility export
except ImportError:
    from research_artifacts import sha as sha256  # noqa: F401 - compatibility export


def pinned_text_sha256(path: Path) -> str:
    """Hash version-controlled text with Git's canonical LF line endings."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("a nonempty relative path is required")
    parts = Path(relative).parts
    if ".." in parts or any(part.startswith(".") for part in parts):
        raise ValueError("hidden or parent paths are not allowed")
    path = root / relative
    if any(parent.is_symlink() for parent in [path, *path.parents] if parent != root.parent):
        raise ValueError("symlinked method or evidence paths are not allowed")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escapes the declared root")
    return path


def load_catalog(root: Path = ROOT) -> dict[str, Any]:
    return json.loads((root / "config/research-methods.json").read_text(encoding="utf-8"))


def installation_errors(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        catalog = load_catalog(root)
        manifest = json.loads((root / "integrations/vendored-research-methods.json").read_text())
        lock = json.loads((root / "integrations/upstreams.lock.json").read_text())
        sources = {row["id"]: row for row in lock["sources"]}
        for source_id in catalog["source_ids"]:
            if source_id not in sources:
                errors.append(f"unregistered research-method source: {source_id}")
        paths: set[str] = set()
        for row in manifest["files"]:
            relative = row["path"]
            if relative in paths:
                errors.append(f"duplicate installed method path: {relative}")
            paths.add(relative)
            path = safe_path(root, relative)
            if not path.is_file() or pinned_text_sha256(path) != row["sha256"]:
                errors.append(f"missing or modified pinned method: {relative}")
            if not any(source.get("repository", "").removeprefix("https://github.com/") ==
                       row["source_repository"] and source.get("commit") == row["commit"]
                       for source in sources.values()):
                errors.append(f"method source/pin is not registered: {relative}")
        for module in catalog["modules"]:
            path = safe_path(root, module["path"])
            if not path.is_file() or pinned_text_sha256(path) != module["sha256"]:
                errors.append(f"missing or modified adapted method: {module['id']}")
            if not set(module["source_ids"]).issubset(sources):
                errors.append(f"unknown adapted-method source: {module['id']}")
        if not catalog.get("modules") or catalog.get("schema_version") != "1.0":
            errors.append("research-method catalog is empty or unsupported")
        scientific_reasoning.load_policy(root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"invalid research-method installation: {exc}")
    return errors


def peer_review_method(root: Path = ROOT, *, sections: tuple[int, ...] = tuple(PEER_REVIEW_SECTIONS)) -> dict[str, Any]:
    """Select intact scientific passages, never execute an upstream workflow."""
    manifest = json.loads((root / "integrations/vendored-research-methods.json").read_text())
    source = next((row for row in manifest["files"] if row["path"] == PEER_REVIEW_PATH), None)
    if source is None:
        raise ValueError("pinned K-Dense peer-review method is missing")
    path = safe_path(root, PEER_REVIEW_PATH)
    if not path.is_file() or pinned_text_sha256(path) != source["sha256"]:
        raise ValueError("pinned K-Dense peer-review method has changed")
    body = path.read_text(encoding="utf-8")
    excerpts = []
    for number in sections:
        title, stop = PEER_REVIEW_SECTIONS[number]
        heading = f"### {number}. {title}\n"
        _, found, text = body.partition(heading)
        if not found:
            raise ValueError("pinned K-Dense peer-review section is missing: " + title)
        text = text.split("\n### ", 1)[0]
        if number == 9:
            text = "Every major/minor comment should include:" + text.split("Every major/minor comment should include:", 1)[1]
        if stop:
            text = text.split(stop, 1)[0]
        excerpts.append(heading + text.strip())
    return {"source_id": "kdense-topic-methods", **source,
            "selected_sections": list(sections), "guidance": "\n\n".join(excerpts)}


def peer_review_context(root: Path = ROOT, *, sections: tuple[int, ...] = tuple(PEER_REVIEW_SECTIONS), full=False) -> str:
    method = peer_review_method(root, sections=sections)
    questions = safe_path(root, "config/pre-submission-criteria.json")
    question_text = questions.read_text(encoding="utf-8")
    if not full:
        question_text = "\n".join(row["id"] + ": " + row["question"] for row in json.loads(question_text)["universal"])
        question_text += "\nArticle-type questions not loaded; select config/pre-submission-criteria.json or submission-review for the complete source."
    return ("PRIMARY PEER-REVIEW METHOD: K-Dense scientific excerpts; ARS questions are supplementary coverage.\n"
            + json.dumps({key: value for key, value in method.items() if key != "guidance"}, ensure_ascii=False)
            + "\nUse only the supplied source view; missing material remains unassessed. Apply current native owner policy; "
            "upstream intake, licence/research-use and venue AI-policy gates are not adopted. "
            "These questions add no paid pass, score threshold or C-class gate. Public AI-use statements remain author-editable; "
            "complete outcomes stay in the separate experiment archive, without requiring every comparison in the manuscript.\n"
            + method["guidance"]
            + "\n\nSUPPLEMENTARY ARS QUESTIONS (SHA-256 " + pinned_text_sha256(questions) + "):\n"
            + question_text
            + "\nApply universal and only the actual article-type questions within this existing review. "
            "Missing material remains unassessed; do not infer the article type or a favorable judgement. "
            "The standalone categorical checklist scanner/report is retired. Do not create "
            "pre-submission-checklist.json or pre-submission-review.json, a coverage table or a separate paid pass. "
            "Semantic review remains unknown until actual source-bound findings are recorded in the existing "
            "independent review; retired mechanical reports provide no current clearance.")


def venue_fit_context(project: Path, paper_id: str) -> str:
    """Give the ordinary critic current scientific criteria for its selected venue."""
    from scripts.research_case import _paper, _venue_sources, VENUE_FIELDS
    prefix = _paper(paper_id)
    venue_path = safe_path(project, prefix + "/venue.json")
    if not venue_path.is_file(): return ""
    selected = json.loads(venue_path.read_text(encoding="utf-8")).get("venue_id")
    if not isinstance(selected, str) or selected.strip().casefold() in {"", "unknown", "tbd"}: return ""
    case_path = safe_path(project, prefix + "/research-case.json")
    case = json.loads(case_path.read_text(encoding="utf-8")) if case_path.is_file() else {}
    criteria = []
    for field in sorted(VENUE_FIELDS):
        criterion = {"criterion_path": prefix + "/research-case.json#/venue_fit/" + field, "source_status": "unknown"}
        try:
            if case.get("schema_version") != "1.0" or case.get("paper_id") != paper_id:
                raise ValueError("current paper research-case evidence remains unknown")
            fit = _venue_sources(project, case, selected, fields=(field,))
            criterion.update(source_status="bound_official_source", **{key: fit[field][key] for key in ("statement", "source", "url")})
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            criterion["reason"] = str(exc)
        criteria.append(criterion)
    return ("Target journal-fit criteria for the actually selected venue:\n"
            + json.dumps({"venue_id": selected, "venue_sha256": sha256(venue_path),
                "case_sha256": sha256(case_path) if case_path.is_file() else None, "criteria": criteria}, ensure_ascii=False)
            + "\nIn this existing ordinary critique, assess each relevant criterion's applicability and scientific fit. "
            "For actual findings cite its criterion_path and official source path/locator in the existing finding/rationale text; "
            "do not add response keys, scores or acceptance estimates. Missing or unbound evidence remains unknown; "
            "do not invent a target or fill other venues. Assess scope, editorial interest, article type and desk risks only; "
            "journal AI policies, public AI statements and ranking/IF floors create no gate. No extra review call is requested.")


def stage_context(stage: str, role: str, root: Path = ROOT, *, context: str = "", project: Path | None = None) -> str:
    """Current-task core plus explicitly selected, intact source guidance."""
    issues = installation_errors(root)
    if issues:
        raise ValueError("; ".join(issues))
    from scripts import ccfa_runtime
    from scripts.research_phase import disposition_stage, stage_rules
    selected = disposition_stage(project, stage) if project is not None else stage
    blocks = [ccfa_runtime.model_contract(selected, role, context, root=root, project=project),
              stage_rules(project, stage, role, root)]
    if stage == "writing-and-review" and selected != "experiment-design" and (
            role == "critic" or selected == "writing-and-review" or
            any(token in context for token in ("peer-review", "submission-review", "pre-submission-checklist"))):
        blocks.insert(0, peer_review_context(root, full=any(token in context for token in (
            "submission-review", "config/pre-submission-criteria.json", "full-method-review"))))
    if project is not None and stage in {"experiment-design", "experiment-execution", "writing-and-review"}:
        from scripts.paper_execution import prompt_contract
        current_paths = prompt_contract(project)
        if current_paths:
            blocks.append(current_paths)
    # A stage makes a method available; only an exact requested module/path
    # loads its complete body. The index is explicit about what was not loaded.
    available = []
    for module in load_catalog(root)["modules"]:
        if stage not in module["stages"] or (selected == "scientific-writing" and module["id"] == "submission-review"):
            continue
        if module["id"] in context or module["path"] in context or "full-method-review" in context:
            blocks.append(f"Reviewed method {module['id']} (SHA-256 {module['sha256']}):\n"
                          + safe_path(root, module["path"]).read_text(encoding="utf-8"))
        else:
            available.append({key: module[key] for key in ("id", "path", "sha256")})
    if available:
        blocks.append("Available complete method sources (not loaded; select an exact ID/path when needed):\n"
                      + json.dumps(available, ensure_ascii=False))
    from scripts.research_toolkit import task_context
    tools = task_context(project, stage, role, context, root=root)
    if tools:
        blocks.append(tools)
    if stage == "experiment-execution" and project is not None:
        from scripts.primary_recovery import diagnosis_context
        diagnosis = diagnosis_context(project)
        if diagnosis.get("status") != "not_needed":
            blocks.append("Current failed-experiment packet (evidence, no execution authority):\n"
                + json.dumps(diagnosis, ensure_ascii=False, sort_keys=True)
                + "\nRead exact failed receipts/logs and frozen code. If eligible, propose program/primary-recovery.json through "
                "the existing writer and independent critics with operation=retire_primary_plan, exact plan_sha256, budget_sha256, "
                "version, failed_attempt_ids and diagnostic_evidence; prior_outcomes_seen=true, observed_prior_results=true, "
                "new_analysis_phase=exploratory, failure_category=implementation_failure|infrastructure_failure and a substantive reason. "
                "Never rewrite frozen inputs, rerun successes, hide failures or grant spending. A passing diagnosis only permits "
                "the checked return to G3, retaining all evidence and costs; it cannot pass G4 or verify a claim.")
    if stage == "writing-and-review" and project is not None:
        state_path = project / "state/run.json"
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
        paper = state.get("active_paper")
        if role == "critic" and selected != "experiment-design" and isinstance(paper, str):
            venue_context = venue_fit_context(project, paper)
            if venue_context: blocks.append(venue_context)
        if isinstance(paper, str) and (project / "papers" / paper / "reviews/paper-facts.json").is_file():
            from scripts.contribution_reporting import feedback
            blocks.append("Current writing-evidence preparation (not a scientific verdict):\n"
                          + json.dumps(feedback(project, paper), ensure_ascii=False))
    return "\n\n".join(blocks)


def load_vendored_module(relative: str) -> Any:
    """Import only a reviewed, hash-verified helper, with no dynamic source URL."""
    manifest = json.loads((ROOT / "integrations/vendored-research-methods.json").read_text())
    rows = {row["path"]: row for row in manifest["files"]}
    if relative not in rows:
        raise ValueError("helper is not in the pinned installation manifest")
    path = safe_path(ROOT, relative)
    if pinned_text_sha256(path) != rows[relative]["sha256"]:
        raise ValueError(f"pinned helper hash changed: {relative}")
    name = "_dr_os_" + hashlib.sha256(relative.encode()).hexdigest()[:16]
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ValueError("cannot load reviewed helper")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(name, None)
            raise
    return sys.modules[name]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--stage")
    parser.add_argument("--role", choices=["planner", "writer", "critic"], default="writer")
    args = parser.parse_args()
    if args.validate:
        errors = installation_errors()
        print(json.dumps({"pass": not errors, "errors": errors}, indent=2))
        return 2 if errors else 0
    if not args.stage:
        parser.error("--stage or --validate is required")
    print(stage_context(args.stage, args.role))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
