"""Complete, source-bound row provenance without changing or exporting raw rows.

The existing dataset contract, manifest and owner authorization remain the
authorities. Located metadata is not source truth, human verification or G3.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date, datetime, timezone
import hashlib
import io
import ipaddress
import json
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

from scripts import data_contracts, dataset_fetch
from scripts.network_safety import validate_https_url
from scripts.research_artifacts import path_in, read, record, sha, write

REQUEST = "program/data-row-provenance.json"
OUTPUT = "reports/data-row-provenance"
STATES = {"pending", "located", "disputed"}
ISSUES = {"unexplained_missing", "not_published", "not_accessible", "not_applicable", "ambiguous", "conflict"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _keys(value, required, optional=()):
    data_contracts._keys(value, required, optional)


def _url(value):
    url = validate_https_url(value, "row source URL")
    parsed = urlsplit(url)
    if any(k.casefold() in {"api_key", "apikey", "access_token", "token", "key", "signature", "sig", "password", "secret", "credential", "authorization"}
           for k, _ in parse_qsl(parsed.query)):
        raise ValueError("row source URL must not contain credentials")
    host = parsed.hostname.casefold().rstrip(".")
    if host == "localhost" or host.endswith((".local", ".localhost", ".internal")):
        raise ValueError("row source URL must identify a public source")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        pass  # Metadata only: do not perform DNS or fetch a URL while recording it.
    else:
        if not address.is_global:
            raise ValueError("row source URL must identify a public source")
    return url


def _instant(value, label, *, publication=False):
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError(label + " must be an ISO date/time or null")
    try:
        if publication and len(value) == 10:
            return datetime.combine(date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc)
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(label + " must be an actual ISO date/time") from exc
    if result.tzinfo is None or "T" not in value:
        raise ValueError(label + " needs an actual timezone-aware collection timestamp")
    return result.astimezone(timezone.utc)


def _dataset(project, dataset_id):
    dataset_id = data_contracts._id(dataset_id)
    declaration = read(path_in(project, f"data/contracts/{dataset_id}.json"))
    manifest_binding = data_contracts._binding(project, declaration["manifest"])
    if manifest_binding["path"] != f"data/manifests/{dataset_id}.json":
        raise ValueError("row provenance requires the canonical dataset manifest")
    manifest = read(path_in(project, manifest_binding["path"]))
    errors = dataset_fetch.validate_manifest(manifest)
    if errors or manifest.get("license", {}).get("confirmed_by_human") is not True:
        raise ValueError("row provenance needs the existing reviewed dataset license")
    authorizations = read(path_in(project, "state/data-authorizations.json"))
    permission = authorizations.get("manifests", {}).get(manifest_binding["path"], {})
    if (permission.get("sha256") != manifest_binding["sha256"] or permission.get("cloud_use_confirmed") is not True
            or not isinstance(permission.get("actor"), str) or not permission["actor"].strip()):
        raise ValueError("row provenance needs current owner-authorized dataset/cloud rights")
    contract, fields, rows, variables, inputs = data_contracts._load(project, dataset_id)
    # Preserve actual physical CSV line ranges, including quoted multiline rows.
    ranges = []
    with path_in(project, contract["input"]["path"]).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        reader.fieldnames
        previous = reader.line_num
        for _ in reader:
            ranges.append((previous + 1, reader.line_num))
            previous = reader.line_num
    if len(ranges) != len(rows):
        raise ValueError("CSV changed while recording physical row ranges")
    inputs += [{"path": "state/data-authorizations.json", "permission_manifest": manifest_binding["path"],
                "permission_sha256": _digest(permission)}]
    return contract, fields, rows, variables, inputs, ranges, manifest


def _row_identity(source, number, row):
    row_hash = _digest(row)
    return "row-" + _digest({"source_sha256": source["sha256"], "row_number": number, "row_sha256": row_hash})[:32], row_hash


def prepare(project: Path, dataset_id: str, key_columns=None) -> dict:
    """Prepare every pending row, with fingerprints; never copy raw values."""
    contract, fields, rows, variables, _, _, _ = _dataset(project, dataset_id)
    keys = [] if key_columns is None else key_columns
    _key_columns(keys, fields)
    records = []
    for number, row in enumerate(rows, 1):
        _, row_hash = _row_identity(contract["input"], number, row)
        issues = [{"field": name, "state": "unexplained_missing", "reason": "Original missing code; source explanation is pending."}
                  for name in fields if row[name] in variables[name]["missing_codes"]]
        records.append({"row_number": number, "row_sha256": row_hash, "status": "pending", "sources": [], "issues": issues})
    return {"schema_version": "1.0", "dataset_id": dataset_id, "input": contract["input"],
            "key_columns": keys, "records": records}


def _key_columns(value, fields):
    if (not isinstance(value, list) or len(value) > 10 or any(not isinstance(c, str) or c not in fields for c in value)
            or len(set(value)) != len(value)):
        raise ValueError("key_columns must be 0..10 distinct actual CSV columns")


def _material(project, value, row_binding):
    if value is None:
        return None, []
    if not isinstance(value, dict):
        raise ValueError("row material must be a bound dataset row or registered literature anchor")
    if value.get("kind") == "dataset_row":
        _keys(value, {"kind"})
        return {"kind": "dataset_row", **row_binding,
                "origin_relationship_verified": False}, []
    _keys(value, {"kind", "paper_id", "anchor"})
    if value["kind"] != "literature":
        raise ValueError("unsupported row source material")
    from scripts import literature_workbench as workbench
    library, _, manifest = workbench._snapshot(project)
    paper = next((p for p in library["papers"] if p["id"] == value["paper_id"] and p.get("status") == "current"), None)
    if paper is None:
        raise ValueError("row source material needs a current registered paper")
    anchor = workbench.validate_anchor(project, paper, value["anchor"])
    if anchor["path"] not in {paper["source"]["path"], (paper.get("reader") or {}).get("path")}:
        raise ValueError("row provenance must locate original material, not generated notes")
    safe = {k: anchor[k] for k in ("path", "sha256", "start_line", "end_line", "pdf_page", "locator") if k in anchor}
    safe.update(kind="literature", paper_id=value["paper_id"], quote_sha256=_digest(anchor["quote"]),
                source_semantics_verified=False)
    binding = {"path": manifest["output_dir"] + "/manifest.json",
               "sha256": sha(path_in(project, manifest["output_dir"] + "/manifest.json"))}
    return safe, [binding]


def build(project: Path, spec: dict) -> dict:
    """Validate complete row declarations and return only provenance metadata."""
    _keys(spec, {"schema_version", "dataset_id", "input", "key_columns", "records"})
    if spec["schema_version"] != "1.0":
        raise ValueError("unsupported row provenance schema")
    contract, fields, rows, variables, bindings, physical, manifest = _dataset(project, spec["dataset_id"])
    if spec["input"] != contract["input"]:
        raise ValueError("row provenance input differs from the original dataset version")
    keys = spec["key_columns"]
    _key_columns(keys, fields)
    incoming = spec["records"]
    if not isinstance(incoming, list) or len(incoming) != len(rows):
        raise ValueError("row provenance must cover every original data row exactly once")
    declared = {}
    for item in incoming:
        _keys(item, {"row_number", "row_sha256", "status", "sources", "issues"})
        number = item["row_number"]
        if type(number) is not int or not 1 <= number <= len(rows) or number in declared:
            raise ValueError("row numbers must identify every original data row exactly once")
        declared[number] = item
    key_hashes = [_digest({c: row[c] for c in keys}) if keys else None for row in rows]
    key_counts = Counter(k for k in key_hashes if k is not None)
    result, material_bindings = [], []
    for number, row in enumerate(rows, 1):
        item = declared[number]
        row_id, digest = _row_identity(contract["input"], number, row)
        if item["row_sha256"] != digest:
            raise ValueError("row fingerprint differs from the original data row")
        if not isinstance(item["status"], str) or item["status"] not in STATES:
            raise ValueError("row status must be pending, located or disputed; no automatic verified status")
        issues = item["issues"]
        if not isinstance(issues, list) or len(issues) > len(fields) * 4:
            raise ValueError("row issues must be bounded field-specific declarations")
        for issue in issues:
            _keys(issue, {"field", "state", "reason"})
            if (not isinstance(issue["field"], str) or issue["field"] not in fields
                    or not isinstance(issue["state"], str) or issue["state"] not in ISSUES):
                raise ValueError("row issue must distinguish a supported missing/doubt state")
            data_contracts._text(issue["reason"], "row issue reason")
        missing = [name for name in fields if row[name] in variables[name]["missing_codes"]]
        if set(missing) - {i["field"] for i in issues}:
            raise ValueError("every missing cell needs an explicit source explanation or unexplained_missing")
        if item["status"] == "disputed" and not any(i["state"] in {"ambiguous", "conflict"} for i in issues):
            raise ValueError("a disputed row needs an explicit ambiguity or conflict")
        if item["status"] == "located" and any(i["state"] in {"ambiguous", "conflict", "unexplained_missing"} for i in issues):
            raise ValueError("unresolved ambiguity, conflict or unexplained missingness cannot be labelled located")
        sources = item["sources"]
        if not isinstance(sources, list) or len(sources) > 30:
            raise ValueError("row sources must be a bounded list; conflicting sources remain distinct")
        bound_sources = []
        row_binding = {**contract["input"], "row_number": number, "row_sha256": digest,
                       "start_line": physical[number - 1][0], "end_line": physical[number - 1][1]}
        for source in sources:
            _keys(source, {"url", "published_at", "collected_at", "fields", "material"})
            applies = source["fields"]
            if (not isinstance(applies, list) or not applies or len(applies) > len(fields)
                    or any(not isinstance(c, str) or c not in fields for c in applies) or len(set(applies)) != len(applies)):
                raise ValueError("each source must name its actual covered CSV fields")
            url = _url(source["url"])
            publication = _instant(source["published_at"], "published_at", publication=True)
            collected = _instant(source["collected_at"], "collected_at")
            if publication is not None and collected is not None and publication > collected:
                raise ValueError("publication cannot be later than the recorded collection timestamp")
            material, extra = _material(project, source["material"], row_binding)
            material_bindings.extend(extra)
            if item["status"] == "located" and (collected is None or material is None):
                raise ValueError("located row needs actual collection time and bound material")
            bound_sources.append({"url": url, "published_at": source["published_at"], "collected_at": source["collected_at"],
                "fields": applies, "material": material, "source_url_resolved": False,
                "publication_date_semantics_verified": False, "source_semantics_verified": False})
        if item["status"] == "located" and not bound_sources:
            raise ValueError("located row requires at least one actual source binding")
        covered_fields = {name for source in bound_sources for name in source["fields"]}
        result.append({"row_id": row_id, "row_number": number, "csv_line_start": physical[number - 1][0],
            "csv_line_end": physical[number - 1][1], "row_sha256": digest, "key_sha256": key_hashes[number - 1],
            "duplicate_key": bool(keys) and key_counts[key_hashes[number - 1]] > 1,
            "key_contains_missing": any(row[c] in variables[c]["missing_codes"] for c in keys),
            "status": item["status"], "sources": bound_sources, "missing_fields": missing,
            "fields_without_declared_row_source": [name for name in fields if name not in covered_fields],
            "all_fields_have_declared_row_source": covered_fields == set(fields),
            "issues": issues, "human_verified": False, "scientific_validity_verified": False})
    # Source/authorization changes during this complete scan cannot yield a pass.
    for binding in bindings:
        if "sha256" in binding:
            data_contracts._binding(project, binding)
        else:
            permission = read(path_in(project, binding["path"]))["manifests"].get(binding["permission_manifest"])
            if _digest(permission) != binding["permission_sha256"]:
                raise ValueError("owner data authorization changed during provenance recording")
    inputs = bindings + list({b["path"]: b for b in material_bindings}.values())
    report = {"schema_version": "1.0", "dataset_id": spec["dataset_id"], "input": contract["input"],
        "key_columns": keys, "rows": result, "row_count": len(rows), "complete_original_row_coverage": True,
        "duplicate_key_rows": sum(r["duplicate_key"] for r in result),
        "duplicate_key_policy": "retained_with_source_version_row_number_and_fingerprint",
        "row_identity_method": "source_version_row_number_fingerprint", "inputs": inputs,
        "declaration_sha256": _digest(spec), "implementation_sha256": sha(Path(__file__)),
        "inherited_dataset_source": {"url": _url(manifest["source_url"]), "version": manifest["version"],
            "accessed_at": manifest["accessed_at"], "scope": "dataset_metadata_not_row_verification"},
        "raw_values_exported": False, "digests_are_not_anonymization": True,
        "data_mutated": False, "model_call_made": False, "data_rights_granted": False,
        "human_verified": False, "scientific_validity_verified": False, "gate_approved": False}
    report["fingerprint"] = _digest(report)
    return report


def _csv_cell(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text


def csv_text(report):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(["row_id", "row_number", "csv_line_start", "csv_line_end", "row_sha256", "key_sha256",
                     "duplicate_key", "status", "source_count", "source_urls", "published_at", "collected_at",
                     "missing_fields", "issues", "human_verified"])
    for row in report["rows"]:
        values = [row["row_id"], row["row_number"], row["csv_line_start"], row["csv_line_end"], row["row_sha256"],
            row["key_sha256"] or "", row["duplicate_key"], row["status"], len(row["sources"]),
            json.dumps([s["url"] for s in row["sources"]]), json.dumps([s["published_at"] for s in row["sources"]]),
            json.dumps([s["collected_at"] for s in row["sources"]]), json.dumps(row["missing_fields"]),
            json.dumps(row["issues"], ensure_ascii=False), False]
        writer.writerow([_csv_cell(v) for v in values])
    return stream.getvalue()


def _request(project, relative):
    if (not isinstance(relative, str) or Path(relative).suffix != ".json"
            or not relative.startswith(("program/", "data/row-provenance/"))):
        raise ValueError("row provenance request belongs in program/ or data/row-provenance/")
    target = path_in(project, relative)
    if target.stat().st_size > 8_000_000:
        raise ValueError("row provenance declaration exceeds 8 MB; use a narrower declared dataset")
    from scripts.literature_workbench import _json
    return _json(target.read_bytes())


def refresh(project: Path, request_path=REQUEST) -> dict:
    project = Path(project).resolve()
    report = build(project, _request(project, request_path))
    directory = path_in(project, OUTPUT + "/" + report["dataset_id"], exists=False)
    directory.mkdir(parents=True, exist_ok=True)
    output, table, manifest_path = directory / "rows.json", directory / "rows.csv", directory / "manifest.json"
    write(output, report)
    table.write_text(csv_text(report), encoding="utf-8")
    manifest = {"schema_version": "1.0", "request": {"path": request_path, "sha256": sha(path_in(project, request_path))},
        "fingerprint": report["fingerprint"], "implementation_sha256": sha(Path(__file__)),
        "outputs": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in (output, table)]}
    write(manifest_path, manifest)
    record(project, [output, table, manifest_path], "scripts/data_row_provenance.py")
    return {"report": output.relative_to(project).as_posix(), "csv": table.relative_to(project).as_posix(),
            "manifest": manifest_path.relative_to(project).as_posix(), "row_count": report["row_count"],
            "duplicate_key_rows": report["duplicate_key_rows"], "model_call_made": False, "raw_values_exported": False}


def validate_saved_report(project: Path, request_path=REQUEST) -> dict:
    project = Path(project).resolve()
    spec = _request(project, request_path)
    report = build(project, spec)
    prefix = OUTPUT + "/" + report["dataset_id"]
    manifest_path = path_in(project, prefix + "/manifest.json")
    from scripts.output_provenance import current_origin
    origin = current_origin(project, manifest_path)
    if (origin.get("status") != "tracked" or origin.get("family") != "other"
            or origin.get("model") != "scripts/data_row_provenance.py"):
        raise ValueError("row provenance manifest lacks current deterministic execution provenance")
    manifest = read(manifest_path)
    if manifest.get("request") != {"path": request_path, "sha256": sha(path_in(project, request_path))}:
        raise ValueError("row provenance declaration changed")
    if manifest.get("fingerprint") != report["fingerprint"] or manifest.get("implementation_sha256") != sha(Path(__file__)):
        raise ValueError("row provenance source, dictionary, permission or implementation changed")
    expected = {prefix + "/rows.json", prefix + "/rows.csv"}
    outputs = manifest.get("outputs")
    if not isinstance(outputs, list) or len(outputs) != 2 or {o.get("path") for o in outputs} != expected:
        raise ValueError("row provenance output inventory changed")
    for binding in outputs:
        data_contracts._binding(project, binding)
    if read(path_in(project, prefix + "/rows.json")) != report or path_in(project, prefix + "/rows.csv").read_text(encoding="utf-8") != csv_text(report):
        raise ValueError("row provenance no longer reproduces its complete source-bound output")
    return {"valid": True, "row_count": report["row_count"], "fingerprint": report["fingerprint"],
            "scientific_validity_verified": False}
