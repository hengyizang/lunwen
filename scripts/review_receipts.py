"""Protected, current-source critic receipts; no calls, scores or approvals.

Receipts describe actual completed controller invocations. Writer notes are
record-coverage checks, never evidence that a scientific concern is resolved.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts import output_provenance
from scripts.research_artifacts import path_in, read, sha, write, record

MODULE = "scripts/review_receipts.py"
PREFIX = "state/review-receipts"
STAGES = {"G1": "topic-intelligence", "G2": "paper-architecture", "G3": "experiment-design",
          "G4": "experiment-execution", "G5": "writing-and-review"}
FIELDS = {"verdict", "fatal_findings", "major_findings", "minor_findings", "missing_evidence", "remediation_steps", "uncertainty"}


def _cloud():
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("critic sealing requires the authorized cloud controller")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def material_snapshot(project: Path, stage: str, paper_id: str | None = None) -> dict:
    """Hash scientific inputs, excluding requests, verdicts and volatile bookkeeping.

    Bind all program/evidence/experiment inputs and current paper files, including
    review *inputs* such as paper-facts and reviewer comments. Generated review
    results, decision logs and this receipt cannot invalidate their own review.
    """
    from scripts.context_efficiency import operational_path, instruction_paths
    ignored = instruction_paths(project)
    rows = []
    review_inputs = {"paper-facts.json", "citation-claims.jsonl", "original-comments.json", "concern-cards.json",
                     "reviewer-response.json", "response-matrix.csv", "revision-ledger.json",
                     "pre-submission-checklist.json", "reviewer-required-experiment-plan.json"}
    roots = {"intake", "program", "literature", "evidence", "claims", "experiments", "results", "data", "papers"}
    for target in sorted(project.rglob("*")):
        relative = target.relative_to(project).as_posix()
        parts = Path(relative).parts
        if not parts or parts[0] not in roots or any(p.startswith(".") or p in {"raw", "build", "submission"} for p in parts):
            continue
        if relative in ignored or operational_path(relative, exclude_reviews=True):
            continue
        if target.is_symlink():
            raise ValueError("scientific review sources cannot be symlinks: " + relative)
        if not target.is_file():
            continue
        if stage == "writing-and-review" and parts[0] == "papers" and len(parts) > 1 and parts[1] != paper_id and target.name != "paper-contract.json":
            continue
        if "reviews" in parts and target.name not in review_inputs:
            continue
        if any(marker in target.name.casefold() for marker in ("api_key", "apikey", "credential", "password", "secret")):
            continue
        path_in(project, relative)
        rows.append({"path": relative, "sha256": sha(target)})
        if len(rows) > 10000:
            raise ValueError("review material inventory exceeds its bound")
    return {"stage": stage, "paper_id": paper_id, "files": rows, "sha256": _digest(rows)}


def _identity(identity: dict, writer_family: str) -> dict:
    required = ("provider", "family", "requested_model", "reported_model", "completion_status")
    if not isinstance(identity, dict) or any(not isinstance(identity.get(k), str) or not identity[k].strip() for k in required):
        raise ValueError("critic needs actual provider/family/requested and reported model/completion identity")
    if identity["completion_status"] != "completed" or identity.get("cache_hit") is not False:
        raise ValueError("independent criticism must be a fresh completed invocation")
    if writer_family != "openai" or identity["family"] in {writer_family, "other", "unknown"}:
        raise ValueError("critic family must differ from the actual OpenAI writer family")
    if identity["requested_model"] != identity["reported_model"]:
        raise ValueError("critic requested/reported model mismatch")
    return {k: identity.get(k) for k in (*required, "cache_hit", "request_id", "endpoint", "transport")}


def api_identity(result) -> dict:
    from scripts.ai_providers import provider_family
    return {"provider": result.provider, "family": provider_family(result.provider), "requested_model": result.model,
            "reported_model": result.reported_model, "completion_status": result.completion_status,
            "cache_hit": result.cache_hit, "request_id": result.request_id, "endpoint": result.endpoint, "transport": "api"}


def cli_identity(stdout: Path) -> dict:
    """Use actual CLI metadata, not a model name guessed from an environment default."""
    payload = read(stdout)
    models = list(payload.get("modelUsage", {}))
    reported = payload.get("model") or (models[0] if len(models) == 1 else None)
    requested = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("CLAUDE_MODEL") or reported
    if not reported or not str(reported).startswith("claude-") or payload.get("is_error") is True:
        raise ValueError("Claude CLI must return one verified actual model identity before its review can be sealed")
    return {"provider": "claude-cli", "family": "anthropic", "requested_model": requested, "reported_model": reported,
            "completion_status": "completed", "cache_hit": False, "request_id": payload.get("session_id"), "transport": "cli"}


def _key(gate, paper_id):
    if gate not in STAGES or (gate == "G5" and not re.fullmatch(r"P[0-9]{2}", str(paper_id))):
        raise ValueError("review needs a scientific gate and, at G5, the exact paper")
    return gate + ("-" + paper_id if gate == "G5" else "")


def _owned(project, path):
    origin = output_provenance.current_origin(project, path)
    if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane" or origin.get("model") != MODULE:
        raise ValueError("independent review receipt lacks current controller provenance")


def seal_phase(project: Path, *, stage: str, run_id: str, phase: str, audit_path: Path, prompt: str,
               identity: dict, writer_family: str, materials: dict, notes: list[str] | None = None) -> dict:
    _cloud()
    if phase not in {"initial", "final"} or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", run_id):
        raise ValueError("safe actual critic run/phase required")
    gate = next((g for g, s in STAGES.items() if s == stage), None)
    state = read(project / "state/run.json")
    paper_id = state.get("active_paper") if gate == "G5" else None
    key = _key(gate, paper_id)
    if materials != material_snapshot(project, stage, paper_id):
        raise ValueError("scientific inputs changed during independent criticism; review current sources again")
    relative = audit_path.relative_to(project).as_posix()
    path_in(project, relative)
    if not relative.startswith("reviews/independent/"):
        raise ValueError("controller audit must use the independent review directory")
    audit = read(audit_path)
    from scripts.researchctl import audit_document_valid
    errors = []
    audit_document_valid(audit_path, audit, errors)
    if errors:
        raise ValueError("; ".join(errors))
    actual_identity = _identity(identity, writer_family)
    directory = f"{PREFIX}/{key}/{run_id}"
    target = path_in(project, f"{directory}/{phase}.json", exists=False)
    if target.exists():
        raise ValueError("independent phase receipt is immutable; start a new actual invocation")
    initial = None
    if phase == "final":
        initial_path = path_in(project, f"{directory}/initial.json")
        _owned(project, initial_path)
        first = read(initial_path)
        if first.get("run_id") != run_id or first.get("stage") != stage or first.get("paper_id") != paper_id:
            raise ValueError("final review requires its same-run initial phase")
        if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
            raise ValueError("final review needs actual writer dispositions")
        from scripts.api_orchestrator import validate_remediation_notes
        validate_remediation_notes({"notes": notes, "stage": stage}, read(project / first["audit"]["path"]))
        initial = {"path": initial_path.relative_to(project).as_posix(), "sha256": sha(initial_path)}
    value = {"schema_version": "1.0", "gate": gate, "stage": stage, "paper_id": paper_id, "run_id": run_id,
             "phase": phase, "created_at": datetime.now(timezone.utc).isoformat(),
             "materials": materials, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
             "identity": actual_identity, "writer_family": writer_family,
             "audit": {"path": relative, "sha256": sha(audit_path)}, "initial": initial,
             "dispositions": notes if phase == "final" else None, "scientific_completion_verified": False}
    write(target, value)
    paths = [target, audit_path]
    if phase == "final":
        latest = path_in(project, f"{PREFIX}/{key}/latest.json", exists=False)
        write(latest, {"path": target.relative_to(project).as_posix(), "sha256": sha(target)})
        paths.append(latest)
    record(project, paths, MODULE)
    return {"path": target.relative_to(project).as_posix(), "sha256": sha(target)}


def validate_gate(project: Path, gate: str, paper_id: str | None = None) -> list[str]:
    if gate not in STAGES:
        return []
    try:
        key = _key(gate, paper_id)
        latest = path_in(project, f"{PREFIX}/{key}/latest.json")
        _owned(project, latest)
        pointer = read(latest)
        final_path = path_in(project, pointer["path"])
        if not pointer["path"].startswith(f"{PREFIX}/{key}/") or sha(final_path) != pointer["sha256"]:
            raise ValueError("latest independent receipt pointer changed")
        _owned(project, final_path)
        final = read(final_path)
        if (final.get("gate"), final.get("stage"), final.get("paper_id"), final.get("phase")) != (gate, STAGES[gate], paper_id if gate == "G5" else None, "final"):
            raise ValueError("independent review receipt gate/paper/phase mismatch")
        if final["materials"] != material_snapshot(project, STAGES[gate], paper_id if gate == "G5" else None):
            raise ValueError("independent final review is stale for current scientific inputs")
        _identity(final["identity"], final["writer_family"])
        initial_path = path_in(project, final["initial"]["path"])
        _owned(project, initial_path)
        if sha(initial_path) != final["initial"]["sha256"]:
            raise ValueError("initial review receipt changed")
        initial = read(initial_path)
        if any(initial.get(k) != final.get(k) for k in ("gate", "stage", "paper_id", "run_id")) or initial.get("phase") != "initial":
            raise ValueError("initial/final review receipt runs are not matched")
        _identity(initial["identity"], initial["writer_family"])
        from scripts.researchctl import audit_document_valid
        errors = []
        audits = []
        for receipt in (initial, final):
            audit_path = path_in(project, receipt["audit"]["path"])
            _owned(project, audit_path)
            if sha(audit_path) != receipt["audit"]["sha256"]:
                raise ValueError("actual critic audit changed after sealing")
            audit = read(audit_path)
            audits.append(audit)
            audit_document_valid(audit_path, audit, errors, final=receipt["phase"] == "final")
        from scripts.api_orchestrator import validate_remediation_notes
        validate_remediation_notes({"notes": final["dispositions"], "stage": final["stage"]}, audits[0])
        if any(re.match(r"^unresolved:", note.strip(), re.I) for note in final["dispositions"]):
            errors.append("independent review has unresolved author dispositions")
        return errors
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return ["source-bound independent review: " + str(exc)]


def review_binding(project: Path, paper_id: str) -> dict:
    target = path_in(project, f"{PREFIX}/G5-{paper_id}/latest.json", exists=False)
    return {"path": target.relative_to(project).as_posix(), "sha256": sha(target) if target.is_file() else None,
            "implementation_sha256": sha(Path(__file__))}
