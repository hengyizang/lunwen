#!/usr/bin/env python3
"""Record a named person's supplied-source scope; never certify scientific reading."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    from scripts import output_provenance
    from scripts.research_methods import safe_path, sha256
except ImportError:
    import output_provenance
    from research_methods import safe_path, sha256

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = "deterministic-source-scope"
SCOPES = {"full_text", "abstract", "excerpt", "metadata"}


def record(project: Path, source: str, scope: str, confirmed_by: str) -> Path:
    if scope not in SCOPES or not isinstance(confirmed_by, str) or not confirmed_by.strip():
        raise ValueError("an explicit source scope and named human confirmation are required")
    path = safe_path(project, source)
    if not path.is_file():
        raise ValueError("the supplied primary source is missing")
    digest = sha256(path)
    output = project / "evidence/source-scopes" / (digest + ".json")
    payload = {"schema_version": "1.0", "primary_source": {"path": source, "sha256": digest},
               "provided_scope": scope, "confirmed_by": confirmed_by.strip(),
               "confirmed_at": datetime.now(timezone.utc).isoformat(),
               "human_read_scope": "not_declared", "semantic_verification": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_provenance.record_model_writes(
        project, [output], family="other", provider=PROVIDER, model="scripts/source_scope.py",
        role="human-source-scope", run_id="source-scope-" + digest[:16],
    )
    return output


def _registered_basis(project: Path, paper_id: str) -> tuple[dict, dict]:
    """Identify the supplied PDF via its controlled registration and acquisition."""
    from scripts.literaturectl import approved_pdf
    from scripts.research_artifacts import path_in, read, sha
    if not isinstance(paper_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,100}", paper_id):
        raise ValueError("invalid registered paper identifier")
    config_path = path_in(project, "program/literature-workbench.json")
    config_origin = output_provenance.current_origin(project, config_path)
    if config_origin.get("status") != "tracked" or config_origin.get("model") != "scripts/literature_registration.py":
        raise ValueError("registered source needs the current executor-owned library")
    papers = read(config_path).get("papers", [])
    rows = [row for row in papers if isinstance(row, dict) and row.get("id") == paper_id]
    if len(rows) != 1 or rows[0].get("source_scope") != "full_text":
        raise ValueError("registered supplied full-text source is required")
    spec = rows[0]; primary = spec.get("source")
    metadata_path = path_in(project, f"literature/metadata/{paper_id}.json")
    metadata_origin = output_provenance.current_origin(project, metadata_path)
    if metadata_origin.get("status") != "tracked" or metadata_origin.get("model") != "scripts/literature_registration.py":
        raise ValueError("source registration metadata lacks executor provenance")
    metadata = read(metadata_path); binding = metadata.get("acquisition_receipt", {})
    acquired_path = path_in(project, binding.get("path", ""))
    if sha(acquired_path) != binding.get("sha256"):
        raise ValueError("source acquisition receipt is stale")
    acquired_origin = output_provenance.current_origin(project, acquired_path)
    if acquired_origin.get("status") != "tracked" or acquired_origin.get("family") == "anthropic":
        raise ValueError("source acquisition receipt lacks executor provenance")
    if not isinstance(primary, dict):
        raise ValueError("registered PDF identity is missing")
    pdf = approved_pdf(project, primary["path"], spec["manifest"])
    if sha(pdf) != primary.get("sha256") or not any(p.get("path") == primary["path"] and p.get("sha256") == primary["sha256"] for p in read(acquired_path).get("pdfs", [])):
        raise ValueError("registered PDF differs from acquisition receipt")
    basis = {"paper_id": paper_id, "registration_path": metadata_path.relative_to(project).as_posix(),
             "registration_sha256": sha(metadata_path), "acquisition_path": binding["path"],
             "acquisition_sha256": binding["sha256"], "manifest_path": spec["manifest"],
             "manifest_sha256": sha(path_in(project, spec["manifest"]))}
    return primary, basis


def record_registered(project: Path, paper_id: str) -> Path:
    primary, basis = _registered_basis(project, paper_id)
    digest = primary["sha256"]
    output = project / "evidence/source-scopes" / (digest + ".json")
    payload = {"schema_version": "1.1", "primary_source": primary, "provided_scope": "full_text",
               "basis": basis, "scope_meaning": "full_text_supplied_by_registered_acquisition_not_completeness_verified",
               "human_read_scope": "not_declared", "semantic_verification": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    output_provenance.record_model_writes(project, [output], family="other", provider=PROVIDER,
        model="scripts/source_scope.py", role="registered-source-scope", run_id="source-scope-" + digest[:16])
    return output


def verify(project: Path, primary: object, receipt: object, expected_scope: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(primary, dict) or not isinstance(receipt, dict):
        return ["source_scope_unconfirmed: primary_source and scope_record are required"]
    try:
        source = safe_path(project, primary["path"])
        path = safe_path(project, receipt["path"])
        if not receipt["path"].startswith("evidence/source-scopes/"):
            errors.append("source scope record must be in the protected control directory")
        if sha256(source) != primary.get("sha256") or sha256(path) != receipt.get("sha256"):
            errors.append("source scope record or primary source is stale")
        origin = output_provenance.current_origin(project, path)
        if (origin.get("status") != "tracked" or origin.get("family") != "other" or
                origin.get("provider") != PROVIDER):
            errors.append("source scope record lacks current deterministic control provenance")
        value = json.loads(path.read_text(encoding="utf-8"))
        if value.get("schema_version") not in {"1.0", "1.1"} or value.get("primary_source") != primary:
            errors.append("source scope record refers to a different primary source")
        if value.get("schema_version") == "1.1":
            registered, basis = _registered_basis(project, value["basis"]["paper_id"])
            if registered != primary or basis != value.get("basis") or value.get("scope_meaning") != "full_text_supplied_by_registered_acquisition_not_completeness_verified":
                errors.append("source_scope_unconfirmed: registered acquisition changed")
        elif not value.get("confirmed_by"):
            errors.append("source_scope_unconfirmed: supplied scope is not human-confirmed")
        if value.get("provided_scope") != expected_scope:
            errors.append("source_scope_unconfirmed: supplied scope differs")
        if value.get("human_read_scope") != "not_declared" or value.get("semantic_verification") is not False:
            errors.append("a supplied-scope record cannot attest reading or scientific verification")
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        errors.append("source_scope_unconfirmed: " + str(exc))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--scope", required=True, choices=sorted(SCOPES))
    parser.add_argument("--confirmed-by", required=True, help="named human who confirmed the supplied material's scope")
    args = parser.parse_args()
    project = safe_path(ROOT / "projects", args.project)
    print(record(project, args.source, args.scope, args.confirmed_by).relative_to(project).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
