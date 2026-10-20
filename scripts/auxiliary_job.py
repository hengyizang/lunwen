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

try:
    from scripts import ai_providers, metadata_contract, model_routing, task_router, engineering_contract
    from scripts.publication_figures import PROJECTS_ROOT
except ImportError:
    import ai_providers, metadata_contract, model_routing, task_router, engineering_contract  # type: ignore
    from publication_figures import PROJECTS_ROOT  # type: ignore


KINDS = {"metadata-extraction", "engineering-diagnosis", "multimodal-inspection",
         "format-conversion", "screening-assist", *engineering_contract.TASKS}
FIELDS = {"schema_version", "kind", "prompt_file", "source_contract_file", "attachments", "max_output_tokens", "task_profile"}
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
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("manifest/contract JSON contains a duplicate field")
            value[key] = item
        return value
    def invalid_constant(_):
        raise ValueError("manifest/contract JSON contains a nonfinite number")
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)
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
    inputs = [{"role":"manifest","path":manifest_relative,"sha256":_sha(manifest_bytes)},
              {"role":"prompt","path":manifest["prompt_file"],"sha256":_sha(prompt_bytes)}]
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
            "manifest_sha256":_sha(manifest_bytes)}


def _check_inputs(project: Path, inputs: list[dict]) -> None:
    for item in inputs:
        path = _path(project,item["path"],item["role"],limit=MAX_ATTACHMENT_BYTES)
        if _sha(_read(path,MAX_ATTACHMENT_BYTES,item["role"])) != item["sha256"]:
            raise ValueError("an auxiliary request source changed; the diagnostic was not written")


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
