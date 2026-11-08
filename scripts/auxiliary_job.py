#!/usr/bin/env python3
"""Strict manifest entry point for production auxiliary tasks on the cloud runner.

No HTTP adapter or spending grant lives here. Model selection and execution go
through task_router and the central runtime; outputs remain internal candidates.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.research_artifacts import strict_json
from scripts import ai_providers, metadata_contract, model_routing, task_router, engineering_contract
from scripts.publication_figures import PROJECTS_ROOT


KINDS = {"metadata-extraction", "engineering-diagnosis", "multimodal-inspection",
         "format-conversion", "screening-assist", "public-review-calibration", "citation-crosscheck", "g1-transport-validation", *engineering_contract.TASKS}
FIELDS = {"schema_version", "kind", "prompt_file", "source_contract_file", "attachments", "max_output_tokens", "task_profile", "calibration_seat", "source_task_file"}
REQUIRED = {"schema_version", "kind", "prompt_file"}
PRIVATE_PARTS = {"state", "api_runs", "private", "raw", "secrets", "credentials", "keys", "auth", "tokens"}
PRIVATE_STEMS = {"api", "hosts", "credentials", "secrets", "keys", "tokens", "auth"}
MAX_JSON_BYTES = 2_000_000
MAX_PROMPT_BYTES = 48_000
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024


def _relative(value: object, label: str) -> Path:
    if (not isinstance(value, str) or not value or len(value) > 250 or "\\" in value
            or ":" in value or any(ord(character) < 32 for character in value)):
        raise ValueError(f"{label} must be a bounded portable project-relative path")
    path = Path(value)
    if path.is_absolute() or PureWindowsPath(value).is_absolute() or any(
        part in {".", "..", ""} for part in value.split("/")):
        raise ValueError(f"{label} escapes its strict project-relative boundary")
    if any(part.startswith(".") or part.casefold() in PRIVATE_PARTS for part in path.parts) \
       or path.stem.casefold() in PRIVATE_STEMS:
        raise ValueError(f"{label} may not address private or control files")
    return path


def _path(project: Path, value: object, label: str, *, existing=True, limit=MAX_JSON_BYTES) -> Path:
    relative = _relative(value, label)
    if project.is_symlink():
        raise ValueError("project root may not be a symlink")
    root = project.resolve()
    cursor = root
    for part in relative.parts:
        cursor = cursor/part
        if cursor.is_symlink():
            raise ValueError(f"{label} may not use a symlink or symlinked parent")
    resolved = cursor.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError(f"{label} escapes its project")
    if existing and (not resolved.is_file() or not 0 < resolved.stat().st_size <= limit):
        raise ValueError(f"{label} must be a nonempty regular file within its byte limit")
    return resolved


def _strict_json(raw: bytes) -> object:
    try:
        return strict_json(raw.decode("utf-8"), duplicate_error="manifest/contract JSON contains a duplicate field",
                           nonfinite_error="manifest/contract JSON contains a nonfinite number")
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("manifest/contract must contain bounded strict UTF-8 JSON") from exc


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read(path: Path, limit: int, label: str) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError(f"{label} exceeds its nonempty byte limit")
    return raw


def load(project: Path, manifest_relative: str) -> dict:
    """Read/validate local request files without keys, HTTP or model execution."""
    if os.environ.get("DR_OS_ROUTING_PROFILE") != "production" or not model_routing.production_enabled():
        raise ValueError("auxiliary manifests require DR_OS_ROUTING_PROFILE=production")
    # Validate the actual policy as well as its environment selector.
    model_routing.load_policy()
    manifest_path = _path(project, manifest_relative, "manifest")
    if manifest_path.suffix != ".json":
        raise ValueError("manifest must be a project-relative .json file")
    manifest_bytes = _read(manifest_path, MAX_JSON_BYTES, "manifest")
    manifest = _strict_json(manifest_bytes)
    if (not isinstance(manifest, dict) or not REQUIRED.issubset(manifest)
            or set(manifest) - FIELDS or manifest.get("schema_version") != "1.0"):
        raise ValueError("unsupported auxiliary manifest fields or schema_version")
    kind = manifest["kind"]
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError("manifest kind is outside the bounded auxiliary roles")
    from scripts import dynamic_routing
    task_profile = dynamic_routing.validate_profile(manifest.get("task_profile"), stage="auxiliary", role=kind)
    if kind in {"public-review-calibration", "citation-crosscheck", "g1-transport-validation"} and (task_profile["task_class"] != kind or task_profile["science_risk"] != "critical"):
        raise ValueError(kind + " requires its explicit critical scientific task profile")
    seat = manifest.get("calibration_seat")
    if kind == "public-review-calibration":
        if seat not in {"domain", "editorial", "statistics"}:
            raise ValueError("public-review calibration requires one fixed calibration_seat")
    elif "calibration_seat" in manifest:
        raise ValueError("calibration_seat is allowed only for public-review-calibration")
    prompt_path = _path(project, manifest["prompt_file"], "prompt_file", limit=MAX_PROMPT_BYTES)
    try:
        prompt_bytes = _read(prompt_path, MAX_PROMPT_BYTES, "prompt_file")
        prompt = prompt_bytes.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("prompt_file must be UTF-8 text") from exc
    if not prompt.strip():
        raise ValueError("prompt_file must be nonempty text")
    tokens = manifest.get("max_output_tokens")
    if "max_output_tokens" in manifest and (type(tokens) is not int or not 1 <= tokens <= 32768):
        raise ValueError("max_output_tokens must be a positive bounded integer")
    if kind in {"public-review-calibration", "g1-transport-validation"} and tokens is not None and tokens not in model_routing.VALIDATION_OUTPUT_CAPS:
        raise ValueError("validation max_output_tokens must be 4000 or 12000")
    if kind == "citation-crosscheck" and tokens is not None:
        raise ValueError(kind + " uses its native bounded output plan")
    inputs = [{"role":"manifest","path":manifest_relative,"sha256":_sha(manifest_bytes)},
              {"role":"prompt","path":manifest["prompt_file"],"sha256":_sha(prompt_bytes)}]
    source_task_file = manifest.get("source_task_file")
    if kind == "citation-crosscheck":
        if not isinstance(source_task_file, str) or not source_task_file.startswith("program/") or not source_task_file.endswith(".json"):
            raise ValueError("citation-crosscheck requires a program/*.json source_task_file")
        task_path = _path(project, source_task_file, "source_task_file")
        task_bytes = _read(task_path, MAX_JSON_BYTES, "source_task_file")
        if not isinstance(_strict_json(task_bytes), dict):
            raise ValueError("source_task_file must be a strict JSON task object")
        inputs.append({"role": "source_task", "path": source_task_file, "sha256": _sha(task_bytes)})
    elif "source_task_file" in manifest:
        raise ValueError("source_task_file is allowed only for citation-crosscheck")
    contract = None
    if kind == "metadata-extraction" or kind in engineering_contract.TASKS:
        if "source_contract_file" not in manifest:
            raise ValueError(kind + " requires source_contract_file")
        contract_path = _path(project, manifest["source_contract_file"], "source_contract_file")
        contract_bytes = _read(contract_path, MAX_JSON_BYTES, "source_contract_file")
        handler = engineering_contract if kind in engineering_contract.TASKS else metadata_contract
        contract = handler.validate_contract(_strict_json(contract_bytes))
        inputs.append({"role":"source_contract","path":manifest["source_contract_file"],
                       "sha256":_sha(contract_bytes)})
    elif "source_contract_file" in manifest:
        raise ValueError("source_contract_file is allowed only for metadata-extraction or bounded engineering support")
    attachments = []; attachment_receipts = []
    if kind == "multimodal-inspection":
        records = manifest.get("attachments")
        if not isinstance(records, list) or not 1 <= len(records) <= 5:
            raise ValueError("multimodal-inspection requires 1..5 explicit local attachments")
        total = 0; seen = set()
        for item in records:
            if not isinstance(item, dict) or set(item) != {"path", "mime_type"}:
                raise ValueError("attachment manifest records need exactly path and mime_type")
            path = _path(project, item["path"], "attachment", limit=MAX_ATTACHMENT_BYTES)
            relative = path.relative_to(project.resolve()).as_posix()
            if relative in seen:
                raise ValueError("duplicate attachment source paths are not allowed")
            seen.add(relative)
            raw = _read(path, MAX_ATTACHMENT_BYTES, "attachment"); total += len(raw)
            if total > MAX_ATTACHMENT_BYTES:
                raise ValueError("attachments exceed the shared 10 MiB limit")
            digest = _sha(raw)
            attachments.append({"mime_type":item["mime_type"],"filename":path.name,
                "data_base64":base64.b64encode(raw).decode("ascii"),"sha256":digest})
            receipt = {"role":"attachment","path":relative,"sha256":digest,
                       "mime_type":item["mime_type"],"size_bytes":len(raw)}
            attachment_receipts.append(receipt); inputs.append(receipt)
        # The provider validator checks MIME signatures, UTF-8, hashes and totals.
        # Keep its decoded/raw records in memory only; reports contain metadata.
        ai_providers.validate_attachments(attachments)
    elif "attachments" in manifest:
        raise ValueError("attachments are allowed only for multimodal-inspection")
    return {"kind":kind,"prompt":prompt,"max_output_tokens":tokens,"source_contract":contract,"task_profile":task_profile,
            "attachments":attachments,"attachment_receipts":attachment_receipts,"inputs":inputs,
            "manifest_sha256":_sha(manifest_bytes), "calibration_seat":seat, "source_task_file":source_task_file}


def _check_inputs(project: Path, inputs: list[dict]) -> None:
    for item in inputs:
        path = _path(project,item["path"],item["role"],limit=MAX_ATTACHMENT_BYTES)
        if _sha(_read(path,MAX_ATTACHMENT_BYTES,item["role"])) != item["sha256"]:
            raise ValueError("an auxiliary request source changed; the diagnostic was not written")


def run_g1_transport_validation(project, destination, request, *, execute=False):
    """Run the existing G1 cycle once with the same-model writer transport."""
    from scripts import api_orchestrator, model_runtime, billing_quotes
    from scripts.public_review_anchors import calibration_costs
    from scripts.research_artifacts import read, write
    from scripts.literature_evidence import read_jsonl
    before = read(project / "state/run.json")
    production = model_routing.cycle_routes("topic-intelligence", "scientific-judgment")
    check_inputs = lambda: _check_inputs(project, request["inputs"])
    control_tokens = request["max_output_tokens"] or 4000
    with model_routing.g1_transport_validation_route(project, request["manifest_sha256"], check_inputs=check_inputs, max_output_tokens=control_tokens):
        routes = model_routing.cycle_routes("topic-intelligence", "scientific-judgment")
        cost_plan = []
        for role, route in routes.items():
            tokens = 12000 if role in model_routing.WRITER_ROLES else control_tokens
            quote = model_runtime.pricing(route["provider"], route["model"])
            cost_plan.append({"role": role, "production_route": production[role], "planned_route": route,
                "request_input_bytes_ceiling": route["validation_max_input_bytes"], "max_output_tokens": tokens,
                "reserved_upper_bound_cny": model_runtime.reservation_bound(route["provider"],
                    "x" * route["validation_max_input_bytes"], None, tokens, quote,
                    billing_quotes.tool_limits(quote, None), controlled=True)})
        report = {"schema_version": "1.0", "kind": "g1-transport-validation", "status": "dry_run_no_model_call",
            "execution_requested": execute, "manifest_sha256": request["manifest_sha256"], "input_receipts": request["inputs"],
            "calls_planned": 3, "maximum_calls": 5, "calls_attempted": 0, "budget_granted_cny": 0,
            "maximum_reserved_upper_bound_cny": round(sum(row["reserved_upper_bound_cny"] for row in cost_plan), 8),
            "model_plan": cost_plan, "attempt_receipts": [], "topic_approval_granted": False,
            "scientific_completion_verified": False, "not_manuscript_or_evidence": True,
            "discovery_policy": "At most twelve new literature search operations use native defaults. Dataset query/catalog operations keep their separate native defaults; all are metadata leads. Model calls are counted separately. Additional paid helpers are outside this bounded validation.",
            "scope": "One native G1 candidate-development cycle; actual findings alone justify repair and fresh re-review. No topic selection, gate approval, advancement, automatic rescheduling or new budget."}
        write(destination, report)
        if not execute:
            return report
        if os.environ.get("DR_OS_REQUIRE_REMOTE_RESERVATION") != "1" or api_orchestrator.project_root(project.name).resolve() != project:
            raise ValueError("G1 transport validation requires the existing owner cloud project and spending controller")
        previous_rows = len(model_runtime.ledger_entries(project))
        source_journals = ("evidence/literature-api-ledger.jsonl", "evidence/dataset-search-log.jsonl")
        previous_sources = {relative: len(read_jsonl(project / relative)) for relative in source_journals}
        started = time.monotonic()
        try:
            report["status"] = "in_progress"
            report["budget_before"] = model_runtime.budget_status(project)
            write(destination, report)
            report["result"] = api_orchestrator.run_cycle(project.name, "topic-intelligence", "anthropic", "openai", "anthropic",
                request["prompt"], "", max_output_tokens=12000, control_max_output_tokens=control_tokens, automatic_data=True,
                task_kind="scientific-judgment", task_profile=request["task_profile"])
            check_inputs()
            after = read(project / "state/run.json")
            if any(before.get(field) != after.get(field) for field in ("stage", "gate", "approved_gates", "paper_count")):
                raise ValueError("the G1 validation changed a protected scientific scope")
            report["status"] = "native_cycle_returned_without_topic_approval"
        except Exception as exc:
            report.update(status="partial_failed_no_retry", failure_type=type(exc).__name__)
            raise
        finally:
            rows = model_runtime.ledger_entries(project)[previous_rows:]
            report["cache_hits"] = sum(row.get("cache_hit") is True for row in rows)
            report["attempt_receipts"] = [{"run_id": row["run_id"], "role": row["role"], "usage_receipts": [row]}
                                           for row in rows if row.get("cache_hit") is not True]
            report["calls_attempted"] = len(report["attempt_receipts"])
            report["accounting"] = calibration_costs(report["attempt_receipts"])
            literature = read_jsonl(project / source_journals[0])[previous_sources[source_journals[0]]:]
            datasets = read_jsonl(project / source_journals[1])[previous_sources[source_journals[1]]:]
            report["discovery_operations"] = {"new_literature_receipts": len(literature),
                "literature": [{key: row.get(key) for key in ("receipt_id", "provider", "mode", "status", "query", "requested_at", "completed_at")} for row in literature],
                "dataset_catalog_operations": sum(len(row.get("providers", [])) for row in datasets),
                "dataset_batches": datasets, "metadata_only": True,
                "counts_are_query_provider_operations_not_underlying_http_retries": True,
                "individual_dataset_operation_duration_seconds": None}
            report["budget_after"] = model_runtime.budget_status(project)
            if all(type(report.get(side, {}).get(key)) in {int, float} for side in ("budget_before", "budget_after") for key in ("spent", "reserved")):
                report["cumulative_budget_consumption_change_cny"] = round(
                    sum(report["budget_after"][key] - report["budget_before"][key] for key in ("spent", "reserved")), 8)
            report["duration_seconds"] = round(time.monotonic() - started, 6)
            write(destination, report)
    return report


def run(project: Path, manifest_relative: str, output_relative: str, *, execute=False) -> dict:
    """Plan or run one strict manifest; never choose a model or grant a budget."""
    if type(execute) is not bool:
        raise ValueError("execute must be an explicit boolean")
    if project.is_symlink():
        raise ValueError("project root may not be a symlink")
    project = project.resolve()
    destination = _path(project,output_relative,"output",existing=False)
    if not output_relative.startswith("evidence/auxiliary/") or destination.suffix != ".json":
        raise ValueError("auxiliary diagnostic output must be .json under evidence/auxiliary/")
    if destination.exists():
        raise ValueError("refusing to overwrite an existing auxiliary diagnostic")
    request = load(project,manifest_relative)
    kind = request["kind"]
    if kind == "g1-transport-validation":
        report = run_g1_transport_validation(project, destination, request, execute=execute)
        return {"output": output_relative, "status": report["status"], "kind": kind, "execute": execute,
                "calls_planned": report["calls_planned"], "calls_attempted": report["calls_attempted"],
                "not_manuscript_or_evidence": True}
    if kind == "citation-crosscheck":
        from scripts.literature_source_tasks import run_citation_crosscheck
        _check_inputs(project, request["inputs"])
        report = run_citation_crosscheck(project, destination, request["manifest_sha256"],
            request_file=request["source_task_file"], task_profile=request["task_profile"], execute=execute,
            check_inputs=lambda: _check_inputs(project, request["inputs"]))
        _check_inputs(project, request["inputs"])
        return {"output": output_relative, "status": report["status"], "kind": kind, "execute": execute,
                "calls_planned": report["calls_planned"], "calls_attempted": report["calls_attempted"],
                "not_manuscript_or_evidence": True}
    if kind == "public-review-calibration":
        from scripts.public_review_anchors import run_calibration
        _check_inputs(project, request["inputs"])
        report = run_calibration(project, destination, request["manifest_sha256"], seat=request["calibration_seat"], execute=execute,
                                 check_inputs=lambda: _check_inputs(project, request["inputs"]),
                                 max_output_tokens=request["max_output_tokens"] or 4000)
        _check_inputs(project, request["inputs"])
        return {"output": output_relative, "status": report["status"], "kind": kind, "execute": execute,
                "calls_planned": report["calls_planned"], "calls_attempted": report["calls_attempted"],
                "reserved_upper_bound_cny": report["reserved_upper_bound_cny"], "not_manuscript_or_evidence": True}
    # Provider is an internal family placeholder. The production policy chooses
    # the exact model/group; no manifest field can override that policy.
    provider = task_router.PROFILES[kind][0]
    preview = task_router.plan(project,kind,provider,request["prompt"],request["max_output_tokens"],
                               source_contract=request["source_contract"],task_profile=request["task_profile"])
    if request["attachments"]:
        preview = {**preview,"estimated_cost_complete":False,
                   "within_estimated_budget":None,"preview_attachment_cost_included":False,
                   "notice":"Attachment input is reserved by central runtime at execution; this text-only preview is incomplete."}
    report = {"schema_version":"1.0","kind":kind,"manifest_sha256":request["manifest_sha256"],
        "input_receipts":request["inputs"],"attachments":request["attachment_receipts"],
        "execution_requested":execute,"budget_granted_cny":0,"not_manuscript_or_evidence":True,
        "automatic_acceptance":False,"model_output_accepted_for_science":False,"plan":preview}
    _check_inputs(project,request["inputs"])
    if execute:
        report["execution"] = task_router.run(project,kind,provider,request["prompt"],request["max_output_tokens"],
            attachments=request["attachments"] or None,source_contract=request["source_contract"],task_profile=request["task_profile"])
        report["status"] = "internal_candidate_requires_review"
    else:
        report["status"] = "dry_run_no_model_call"
    _check_inputs(project,request["inputs"])
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open("x",encoding="utf-8") as handle:
        handle.write(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    return {"output":destination.relative_to(project).as_posix(),"status":report["status"],
            "kind":kind,"execute":execute,"not_manuscript_or_evidence":True}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",required=True)
    parser.add_argument("--manifest",required=True,help="strict project-relative JSON request")
    parser.add_argument("--output",required=True,help="new evidence/auxiliary/*.json diagnostic")
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*",args.project):
        parser.error("project must be a simple project slug")
    project=PROJECTS_ROOT/args.project
    print(json.dumps(run(project,args.manifest,args.output,execute=args.execute),indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
