#!/usr/bin/env python3
"""Record a named person's supplied-source scope; never certify scientific reading."""
from __future__ import annotations

import argparse
import json
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
        if value.get("schema_version") != "1.0" or value.get("primary_source") != primary:
            errors.append("source scope record refers to a different primary source")
        if value.get("provided_scope") != expected_scope or not value.get("confirmed_by"):
            errors.append("source_scope_unconfirmed: supplied scope is not human-confirmed")
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
