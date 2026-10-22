"""Cloud-only, no-provider acceptance of all seventeen installed CCFA skills."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from scripts import ccfa_runtime as runtime
from scripts.ccfa_humanization import policy_receipt
from scripts.research_artifacts import write

def acceptance(installed: Path, output: Path):
    runtime.cloud()
    errors = runtime.installation_errors()
    if errors:
        raise ValueError("; ".join(errors))
    native = runtime.install()
    manifest = runtime.lock()
    catalog = runtime.registry()
    ids = {row["id"] for row in catalog["routes"]}
    expected = [r for r in manifest["resources"] if r["path"].split("/")[0] in ids]
    checked = 0
    for row in expected:
        path = installed / row["path"]
        if not path.is_file():
            raise ValueError("Official installation omitted " + row["path"])
        data = path.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if blob != row["git_blob_sha"] or len(data) != row["size"]:
            raise ValueError("Official installation differs from pin: " + row["path"])
        checked += 1
    rows = []
    for route in catalog["routes"]:
        guide = runtime.guidance(route["id"], detailed=True)
        contract = runtime.model_contract("writing-and-review", "writer", skill=route["id"])
        if guide["text"] not in contract:
            raise ValueError("Full upstream skill is missing from actual model guidance")
        rows.append({"id": route["id"], "installed": True, "full_entry_in_model_contract": True,
            "references_accessible": len(guide["references"]), "native_tools": route["native_tools"],
            "original_installed_files": sum(r["path"].startswith(route["id"] + "/") for r in expected),
            "scientific_outcome_verified": False})
    report = {"schema_version": "1.0", "status": "pass", "upstream_commit": runtime.COMMIT,
        "skills": rows, "installed_skill_count": len(rows), "verified_original_files": checked,
        "vendored_functional_files": len(manifest["files"]), "native_installation": native,
        "humanization": policy_receipt(), "model_calls": 0, "paid_calls": 0,
        "scientific_completion_verified": False,
        "scope": "Installation, exact source bytes, complete guidance, native routing and separate unit/integration fixtures; no real-topic/model-quality claim."}
    write(output, report)
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--installed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = acceptance(args.installed, args.output)
    print(json.dumps({k: value[k] for k in ("status", "installed_skill_count", "verified_original_files", "paid_calls")}))
if __name__ == "__main__":
    main()

