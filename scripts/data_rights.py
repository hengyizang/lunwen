"""Source-bound automatic checks for a deliberately limited public-data route.

Zenodo's published record supplies the copyright-license declaration and exact
file identity. The existing writer/independent-critic cycle supplies the privacy
and terms assessment. Unknown or restricted rights never become authorization.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from scripts import network_safety, output_provenance, review_receipts
from scripts.research_artifacts import path_in, read, record, sha, write

MODULE = "scripts/data_rights.py"
LICENSES = {
    "cc-by-4.0": "https://creativecommons.org/licenses/by/4.0/",
    "cc-zero": "https://creativecommons.org/publicdomain/zero/1.0/",
    "cc0-1.0": "https://creativecommons.org/publicdomain/zero/1.0/",
}


def _canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _paths(project, manifest):
    identifier = manifest.get("dataset_id")
    if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,100}", identifier) or ".." in identifier:
        raise ValueError("exact safe dataset ID required for automatic rights checks")
    return (path_in(project, f"evidence/data-rights/{identifier}/metadata.json", exists=False),
            path_in(project, f"state/data-rights/{identifier}.json", exists=False))


def _identity(manifest):
    match = re.fullmatch(r"https://zenodo.org/records?/([0-9]+)/?", str(manifest.get("source_url", "")))
    if not match or str(manifest.get("provider", "")).casefold() != "zenodo":
        raise ValueError("automatic rights adapter requires an exact published Zenodo record")
    return match[1], f"https://zenodo.org/api/records/{match[1]}"


def _declaration(manifest, metadata):
    identifier, _ = _identity(manifest)
    if not isinstance(metadata, dict):
        raise ValueError("official record must be a JSON object")
    detail = metadata.get("metadata", {})
    if not isinstance(detail, dict) or not isinstance(detail.get("resource_type"), dict):
        raise ValueError("published dataset metadata has an unsupported shape")
    license_value = detail.get("license", {})
    license_id = license_value.get("id") if isinstance(license_value, dict) else None
    if (str(metadata.get("id")) != identifier or detail.get("access_right") != "open"
            or detail.get("resource_type", {}).get("type") != "dataset" or license_id not in LICENSES):
        raise ValueError("published record must declare an open dataset with a supported CC license")
    if (manifest.get("title") != detail.get("title") or manifest.get("version") != detail.get("version")
            or not isinstance(manifest.get("version"), str) or not manifest["version"].strip()):
        raise ValueError("dataset title/version differs from the published record")
    license_manifest = manifest.get("license", {})
    if (license_manifest.get("url") != LICENSES[license_id]
            or license_manifest.get("research_use_allowed") is not True
            or license_manifest.get("redistribution_allowed") is not True
            or license_manifest.get("confirmed_by_human") is not False):
        raise ValueError("automatic license record must match the published CC grant and cannot claim human confirmation")
    download = manifest.get("download", {})
    files = metadata.get("files")
    if not isinstance(files, list) or not str(download.get("url", "")).startswith("https://zenodo.org/"):
        raise ValueError("official dataset file identity is missing")
    matches = [f for f in files if isinstance(f, dict) and isinstance(f.get("links"), dict)
               and f["links"].get("self") == download.get("url")]
    if len(matches) != 1 or type(download.get("expected_bytes")) is not int or matches[0].get("size") != download["expected_bytes"]:
        raise ValueError("download URL/size must identify one exact file in the published record")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(download.get("sha256", ""))):
        raise ValueError("automatic acquisition still requires a predeclared SHA-256")
    return {"license_id": license_id, "license_url": LICENSES[license_id],
            "attribution_required": license_id == "cc-by-4.0", "public_access": True}


def _assessment(project, manifest, metadata_path):
    assessment = manifest.get("provenance", {}).get("rights_assessment")
    if (not isinstance(assessment, dict) or assessment.get("source_metadata_sha256") != sha(metadata_path)
            or assessment.get("personal_data") != "none" or assessment.get("cloud_use_allowed") is not True
            or assessment.get("additional_restrictions") is not False
            or any(not isinstance(assessment.get(k), str) or len(assessment[k].strip()) < 30
                   for k in ("privacy_basis", "terms_basis"))):
        raise ValueError("source-bound privacy and terms assessment is missing or unresolved")
    state = read(path_in(project, "state/run.json"))
    gate = state.get("gate")
    if gate not in {"G1", "G3"} or state.get("status") != "awaiting_work":
        raise ValueError("new automatic data authorization requires an open G1 or G3 stage")
    issues = review_receipts.validate_gate(project, gate)
    if issues:
        raise ValueError("current independent scientific review of data rights is required: " + "; ".join(issues))
    latest = read(path_in(project, f"state/review-receipts/{gate}/latest.json"))
    final = path_in(project, latest["path"])
    if latest.get("sha256") != sha(final):
        raise ValueError("independent review receipt changed")
    return {"gate": gate, "assessment_sha256": _canonical(assessment),
            "receipt": {"path": latest["path"], "sha256": sha(final)}}


def prepare(project: Path, manifest_path: Path, *, fetcher=None) -> dict:
    """Fetch public license evidence and authorize only reviewed, resolved rights.

    No model call is added. A first pass can leave metadata for the existing
    writer/critic cycle, then return a missing-assessment blocker.
    """
    project = project.resolve()
    relative = manifest_path.relative_to(project).as_posix()
    if not relative.startswith("data/manifests/") or not relative.endswith(".json"):
        raise ValueError("exact data manifest required")
    manifest_path = path_in(project, relative)
    manifest = read(manifest_path)
    metadata_path, receipt_path = _paths(project, manifest)
    _, endpoint = _identity(manifest)
    payload, final_url, status, _ = (fetcher or network_safety.fetch_bytes)(endpoint, max_bytes=1_000_000)
    if final_url != endpoint or status != 200:
        raise ValueError("public license evidence requires the exact successful official endpoint")
    metadata = json.loads(payload.decode("utf-8"))
    declaration = _declaration(manifest, metadata)
    # Save the parsed original provider JSON, with its exact response hash. Its
    # stable canonical form allows the existing critic receipt to remain current.
    envelope = {"source_url": endpoint, "raw_response_sha256": hashlib.sha256(payload).hexdigest(),
                "raw_response": payload.decode("utf-8"), "record": metadata}
    if metadata_path.is_file():
        previous = read(metadata_path)
        old_record = previous.get("record", {})
        # Download/view counters and response formatting do not change the
        # published metadata, file identities or rights assessment. Retain the
        # original raw response when those complete authoritative fields agree.
        if (previous.get("source_url") == endpoint
                and {k: old_record.get(k) for k in ("id", "metadata", "files")}
                == {k: metadata.get(k) for k in ("id", "metadata", "files")}):
            envelope = previous
    if not metadata_path.is_file() or read(metadata_path) != envelope:
        write(metadata_path, envelope)
        record(project, [metadata_path], MODULE)
    origin = output_provenance.current_origin(project, manifest_path)
    if origin.get("status") != "tracked" or origin.get("family") != "openai":
        raise ValueError("automatic rights assessment needs current authorized non-Claude writer provenance")
    review = _assessment(project, manifest, metadata_path)
    receipt = {"schema_version": "1.0", "kind": "automated_data_rights", "manifest_path": relative,
               "manifest_sha256": sha(manifest_path), "manifest_content_sha256": _canonical(manifest),
               "metadata_path": metadata_path.relative_to(project).as_posix(), "metadata_sha256": sha(metadata_path),
               "review": review, "declaration": declaration, "created_at": datetime.now(timezone.utc).isoformat(),
               "human_confirmation": False, "scientific_validity_verified": False,
               "privacy_assessment": "source-bound writer assessment with current independent critic receipt"}
    write(receipt_path, receipt)
    record(project, [receipt_path], MODULE)
    return {"path": receipt_path.relative_to(project).as_posix(), "sha256": sha(receipt_path)}


def verify(project: Path, manifest: dict) -> list[str]:
    """Recheck protected current evidence without a network or model request."""
    try:
        metadata_path, receipt_path = _paths(project, manifest)
        receipt = read(receipt_path)
        for target in (metadata_path, receipt_path):
            origin = output_provenance.current_origin(project, target)
            if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane" or origin.get("model") != MODULE:
                raise ValueError("automatic rights evidence lacks current controller provenance")
        original = path_in(project, receipt["manifest_path"])
        if (receipt.get("kind") != "automated_data_rights" or receipt.get("human_confirmation") is not False
                or receipt.get("manifest_sha256") != sha(original) or read(original) != manifest
                or receipt.get("manifest_content_sha256") != _canonical(manifest)
                or receipt.get("metadata_sha256") != sha(metadata_path)):
            raise ValueError("automatic rights evidence differs from the exact current manifest")
        envelope = read(metadata_path)
        if (hashlib.sha256(envelope["raw_response"].encode("utf-8")).hexdigest() != envelope.get("raw_response_sha256")
                or json.loads(envelope["raw_response"]) != envelope["record"]):
            raise ValueError("official raw response does not match the stored metadata")
        if envelope.get("source_url") != _identity(manifest)[1] or receipt.get("declaration") != _declaration(manifest, envelope["record"]):
            raise ValueError("published license or file declaration differs")
        assessment = manifest.get("provenance", {}).get("rights_assessment", {})
        if receipt.get("review", {}).get("assessment_sha256") != _canonical(assessment):
            raise ValueError("privacy or terms assessment changed")
        review = receipt["review"]["receipt"]
        final = path_in(project, review["path"])
        origin = output_provenance.current_origin(project, final)
        if (sha(final) != review["sha256"] or origin.get("status") != "tracked"
                or origin.get("provider") != "deterministic-control-plane"
                or origin.get("model") != "scripts/review_receipts.py"):
            raise ValueError("original independent review evidence changed")
        return []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return ["data-rights evidence: " + str(exc)]
