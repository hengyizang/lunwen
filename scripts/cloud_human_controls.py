"""Hash-bound owner decisions for cloud scientific gates; never calls a model.

Invoked only by the owner issue boundary in cloud_job. Review dossiers are
returned as run artifacts, not written into the scientific evidence being hashed.
"""
from __future__ import annotations

import hashlib
import json
import re
from types import SimpleNamespace
from pathlib import Path

from scripts import cloud_checkpoint as cp, output_provenance, researchctl, research_quality as quality

GATE_ACTIONS = {"ready", "approve", "advance", "reopen"}
QUALITY_ACTIONS = {"freeze_preregistration", "confirm_data_quality", "confirm_reproduction"}
ACTIONS = GATE_ACTIONS | QUALITY_ACTIONS | {"screen_literature", "confirm_source_scope", "confirm_review_packet"}
SELECTORS = {
    **{action: {"gate"} for action in GATE_ACTIONS},
    "freeze_preregistration": {"paper_id"},
    "confirm_data_quality": {"dataset_id"},
    "confirm_reproduction": {"paper_id"},
    "screen_literature": {"receipt_id"},
    "confirm_source_scope": {"source", "scope"},
    "confirm_review_packet": {"packet_id"},
}
DECISIONS = {"screen_literature": {"included_work_ids", "exclusion_reasons"}, "confirm_review_packet": {"judgments"}}
AUDIT = "state/cloud-human-decisions.jsonl"
VOLATILE = {cp.MANIFEST, AUDIT, "state/continuation-status.json"}


class HumanControlError(RuntimeError):
    pass


def validate_fields(value: dict) -> str:
    operation = value.get("operation") if value["action"] == "review_dossier" else value["action"]
    if not isinstance(operation, str) or operation not in ACTIONS:
        raise HumanControlError("select a supported human operation")
    selectors = SELECTORS[operation]
    if not selectors <= set(value):
        raise HumanControlError("missing human operation selectors")
    if "gate" in selectors and (not isinstance(value["gate"], str) or value["gate"] not in {f"G{i}" for i in range(6)}):
        raise HumanControlError("gate must be G0-G5")
    if "paper_id" in selectors:
        paper = value["paper_id"]
        if not isinstance(paper, str) or not (
            re.fullmatch(r"P[0-9]{2}", paper)
            or (operation == "freeze_preregistration" and paper == "all")
        ):
            raise HumanControlError("select an exact paper_id or freeze all papers")
    if "dataset_id" in selectors and (
        not isinstance(value["dataset_id"], str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,100}", value["dataset_id"])
        or ".." in value["dataset_id"]
    ):
        raise HumanControlError("invalid dataset_id")
    if "receipt_id" in selectors and (
        not isinstance(value["receipt_id"], str)
        or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,127}", value["receipt_id"])
    ):
        raise HumanControlError("invalid receipt_id")
    if "source" in selectors:
        cp.relative(value["source"])
        if cp.excluded(value["source"]):
            raise HumanControlError("source must be a checkpoint-safe supplied document")
        if not isinstance(value["scope"], str) or value["scope"] not in {"full_text", "abstract", "excerpt", "metadata"}:
            raise HumanControlError("invalid supplied source scope")
    if "packet_id" in selectors and (not isinstance(value["packet_id"], str)
            or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value["packet_id"])):
        raise HumanControlError("select an exact safe packet_id")
    if value["action"] != "review_dossier":
        if not isinstance(value.get("expected_sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["expected_sha256"]):
            raise HumanControlError("exact reviewed dossier SHA-256 required")
        if (not isinstance(value.get("note"), str) or not 10 <= len(value["note"].strip()) <= 500
                or any(ord(ch) < 32 for ch in value["note"])):
            raise HumanControlError("human decision needs a 10-500 character review note")
        if operation == "screen_literature":
            for field, minimum, limit in (("included_work_ids", 0, 200), ("exclusion_reasons", 1, 100)):
                items = value.get(field)
                if (not isinstance(items, list) or not minimum <= len(items) <= limit
                        or any(not isinstance(item, str) or not 0 < len(item.strip()) <= 500
                               or any(ord(ch) < 32 for ch in item) for item in items)):
                    raise HumanControlError("screening needs bounded work IDs and explicit exclusion reasons")
        if operation == "confirm_review_packet" and (not isinstance(value.get("judgments"), dict)
                or len(json.dumps(value["judgments"]).encode()) > 100_000):
            raise HumanControlError("review packet needs bounded structured human judgments")
    return operation


def _papers(project: Path, value: dict) -> list[str]:
    paper = value["paper_id"]
    papers = quality._paper_ids(project) if paper == "all" else [paper]
    state = researchctl.load_state(value["project"])
    expected = {f"P{i:02d}" for i in range(1, int(state["paper_count"]) + 1)}
    if not papers or any(p not in expected or not (project / "papers" / p).is_dir() for p in papers):
        raise HumanControlError("paper must belong to the configured portfolio")
    if paper == "all" and set(papers) != expected:
        raise HumanControlError("configured paper portfolio is incomplete")
    return papers


def _screen_inputs(project: Path, receipt_id: str) -> dict:
    from scripts import literature_evidence as literature
    records = literature.read_jsonl(project / "evidence/literature-api-ledger.jsonl")
    matches = [r for r in records if r.get("receipt_id") == receipt_id]
    if len(matches) != 1 or matches[0].get("status") != "success":
        raise HumanControlError("select one successful executed literature receipt")
    receipt = matches[0]
    for path_key, hash_key in (("raw_response_path", "response_sha256"),
                               ("normalized_results_path", "normalized_results_sha256")):
        path = literature.safe_project_file(project, str(receipt[path_key]))
        cp.check_file(path, project)
        if cp.sha(path) != receipt[hash_key]:
            raise HumanControlError("literature receipt evidence is stale")
    searches = literature.read_jsonl(project / "evidence/search-log.jsonl")
    if len([r for r in searches if r.get("evidence_receipt_id") == receipt_id]) != 1:
        raise HumanControlError("receipt needs exactly one matching search log entry")
    return json.loads((project / receipt["normalized_results_path"]).read_text(encoding="utf-8"))


def _check_and_prepare(value: dict, operation: str) -> list[tuple[Path, dict]]:
    slug = value["project"]
    project = researchctl.project_dir(slug)
    state = researchctl.load_state(slug)
    if operation in GATE_ACTIONS:
        if state["gate"] != value["gate"]:
            raise HumanControlError("reviewed gate is not the current gate")
        if operation == "approve" and state["status"] != "awaiting_approval":
            raise HumanControlError("ready and explicit human review are required before approval")
        if operation == "advance" and state["status"] != "approved":
            raise HumanControlError("current gate needs explicit approval before advance")
        if operation == "reopen" and state["status"] != "awaiting_approval":
            raise HumanControlError("only a gate awaiting approval can be reopened")
        if operation != "reopen":
            errors = researchctl.gate_errors(slug, state["gate"])
            if errors:
                raise HumanControlError("gate requirements remain: " + "; ".join(errors))
        current = researchctl.artifact_hash(slug, state["gate"])
        if operation == "approve" and (
            state.get("ready_gate") != state["gate"] or state.get("ready_artifact_sha256") != current
        ):
            raise HumanControlError("artifacts changed after ready; prepare a fresh review")
        if operation == "advance":
            key = f"G5:{state['active_paper']}" if state["gate"] == "G5" else state["gate"]
            approval = next((a for a in reversed(state["approvals"]) if a.get("gate") == state["gate"]
                             and (state["gate"] != "G5" or a.get("paper_id") == state["active_paper"])), None)
            if key not in state["approved_gates"] or not approval or approval.get("artifact_sha256") != current:
                raise HumanControlError("approval is absent or stale")
        return []
    required_gate = {"freeze_preregistration": "G3", "confirm_data_quality": "G3",
                     "confirm_reproduction": "G4", "screen_literature": "G1"}.get(operation)
    if state["status"] != "awaiting_work" or (required_gate and state["gate"] != required_gate) or state["gate"] is None:
        raise HumanControlError("human evidence decisions require the matching gate open for work")
    actor = value["actor"]
    if operation == "confirm_review_packet":
        from scripts import review_packets
        if value["action"] == "review_dossier":
            review_packets.review_snapshot(project, value["packet_id"])
            return []
        return [review_packets.create_confirmation(project, value["packet_id"], actor, value["judgments"])]
    if operation == "confirm_data_quality":
        dataset = value["dataset_id"]
        return [(project / "data/quality" / f"{dataset}-confirmation.json",
                 quality.create_data_quality_confirmation(project, dataset, actor))]
    if operation == "freeze_preregistration":
        return [(project / "papers" / paper / "preregistration.json",
                 quality.create_preregistration(project, paper, actor)) for paper in _papers(project, value)]
    if operation == "confirm_reproduction":
        paper = _papers(project, value)[0]
        return [(project / "papers" / paper / "reproduction-confirmation.json",
                 quality.create_reproduction_confirmation(project, paper, actor))]
    if operation == "screen_literature":
        _screen_inputs(project, value["receipt_id"])
    if operation == "confirm_source_scope":
        path = quality._safe_path(project, value["source"])
        cp.check_file(path, project)
    return []


def dossier(value: dict) -> dict:
    operation = validate_fields(value)
    project = researchctl.project_dir(value["project"])
    state = researchctl.load_state(value["project"])
    files = [
        {key: item[key] for key in ("path", "sha256", "bytes")}
        for item in cp.inventory(project)
        if item["path"] not in VOLATILE
        and not item["path"].startswith(("api_runs/", ".cache/"))
    ]
    # Bind the exact implementation too; an upgrade requires a new human review.
    repository = Path(__file__).resolve().parents[1]
    implementation_paths = sorted(
        [*repository.joinpath("scripts").rglob("*.py"), *repository.joinpath("schemas").glob("*.json"),
         *repository.joinpath("config").glob("*.json"), *repository.joinpath(".github/workflows").glob("*.yml")]
    )
    implementation = {p.relative_to(repository).as_posix(): cp.sha(p) for p in implementation_paths}
    snapshot = {"schema_version": "1.0", "project": value["project"], "operation": operation,
                "actor": value["actor"], "selectors": {k: value[k] for k in sorted(SELECTORS[operation])},
                "state": {"stage": state["stage"], "gate": state["gate"], "status": state["status"],
                          "active_paper": state["active_paper"]},
                "gate_artifact_sha256": researchctl.artifact_hash(value["project"], state["gate"]) if state["gate"] else None,
                "implementation": implementation, "files": sorted(files, key=lambda item: item["path"])}
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    try:
        _check_and_prepare(value, operation)
        blockers = []
    except (RuntimeError, OSError, ImportError, ValueError, KeyError, TypeError) as exc:
        blockers = [str(exc)]
    return {**snapshot, "review_sha256": digest, "blockers": blockers, "ready_for_operation": not blockers,
            "approval_effect": "No decision is recorded by generating this dossier.",
            "scientific_completion_verified": False}


def execute(value: dict, run_id: str) -> dict:
    operation = validate_fields(value)
    if value["action"] == "review_dossier":
        return dossier(value)
    if not re.fullmatch(r"[0-9]+", str(run_id)):
        raise HumanControlError("a numeric cloud run ID is required for a human decision")
    reviewed = dossier(value)
    if reviewed["review_sha256"] != value["expected_sha256"]:
        raise HumanControlError("review dossier changed; inspect a fresh dossier before deciding")
    if reviewed["blockers"]:
        raise HumanControlError("; ".join(reviewed["blockers"]))
    # Prepare all requested freezes before writing any of them.
    prepared = _check_and_prepare(value, operation)
    project = researchctl.project_dir(value["project"])
    outputs = []
    if operation in GATE_ACTIONS:
        args = SimpleNamespace(project=value["project"], gate=value.get("gate"),
                               actor=value["actor"], note=value["note"])
        {"ready": researchctl.mark_ready, "approve": researchctl.approve,
         "advance": researchctl.advance, "reopen": researchctl.reopen}[operation](args)
        if operation == "approve":
            state = researchctl.load_state(value["project"])
            state["approvals"][-1].update({"cloud_review_sha256": reviewed["review_sha256"],
                                         "source_run_id": str(run_id)})
            researchctl.save_state(value["project"], state)
    elif operation == "screen_literature":
        from scripts import literature_evidence as literature
        literature.screen_receipt(project, value["receipt_id"], value["included_work_ids"],
                                  value["exclusion_reasons"], value["actor"])
        outputs = [project / "evidence/search-log.jsonl"]
    elif operation == "confirm_source_scope":
        from scripts import source_scope
        outputs = [source_scope.record(project, value["source"], value["scope"], value["actor"])]
    else:
        for path, payload in prepared:
            payload["cloud_review_sha256"] = reviewed["review_sha256"]
            payload["source_run_id"] = str(run_id)
            quality._atomic_json(path, payload)
            outputs.append(path)
    if outputs and operation != "confirm_source_scope":
        output_provenance.record_model_writes(
            project, outputs, family="other", provider="deterministic-cloud-human-control",
            model="scripts/cloud_human_controls.py", role="human-reviewed-control",
            run_id=str(run_id),
        )
    receipt = {"schema_version": "1.0", "operation": operation, "project": value["project"],
               "actor": value["actor"], "review_sha256": reviewed["review_sha256"],
               "source_run_id": str(run_id), "note": value["note"],
               "selectors": reviewed["selectors"], "state_before": reviewed["state"],
               "state_after": {k: researchctl.load_state(value["project"])[k] for k in reviewed["state"]},
               "outputs": [{"path": p.relative_to(project).as_posix(), "sha256": cp.sha(p)} for p in outputs],
               "paid_calls": 0, "scientific_completion_verified": False}
    audit = project / AUDIT
    audit.parent.mkdir(parents=True, exist_ok=True)
    with audit.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False, sort_keys=True) + "\n")
    return receipt
