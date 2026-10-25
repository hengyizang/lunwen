"""Bounded economic-data acquisition; metadata is never a licence or causal verdict.

FRED's required query key exists only in the in-memory HTTPS request. Errors,
receipts and persisted responses never contain that key. World Bank's current
API is not presented as a historical-vintage service. No model calls occur.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import urllib.parse
from datetime import date, datetime, timezone
from pathlib import Path

from scripts import network_safety
from scripts.dataset_fetch import validate_manifest
from scripts.research_artifacts import path_in, read, record, sha, write

MODULE = "scripts/economic_data.py"
PREFIX = "evidence/economic-data"
RAW = "data/raw/economic-data"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
SERIES = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\Z")


def _cloud():
    if os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1" and os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("economic data acquisition requires the cloud executor")


def _keys(value, allowed, required, label):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError(label + " has missing or unknown fields")


def _date(value, label):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(label + " needs an explicit ISO date")
    return date.fromisoformat(value)


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(label + " is outside the bounded range")
    return value


def request_path(request_id):
    if not isinstance(request_id, str) or not ID.fullmatch(request_id):
        raise ValueError("economic request ID is unsafe")
    return f"data/economic-requests/{request_id}.json"


def _spec(project, request_id, *, require_current_snapshot=False):
    path = path_in(project, request_path(request_id))
    if path.stat().st_size > 100_000:
        raise ValueError("economic request exceeds the bounded configuration size")
    value = read(path)
    common = {"schema_version", "id", "provider", "scope", "as_of", "vintage_mode", "start", "end", "max_pages", "page_size", "dataset_manifest"}
    _keys(value, common | {"series", "countries", "indicators"}, common - {"dataset_manifest"}, "economic request")
    if value["schema_version"] != "1.0" or value["id"] != request_id or value["provider"] not in {"fred", "worldbank"}:
        raise ValueError("economic request version, identity or provider is invalid")
    if value["scope"] not in {"metadata_only", "observations"}:
        raise ValueError("economic request needs explicit metadata_only or observations scope")
    today = datetime.now(timezone.utc).date()
    as_of, start, end = (_date(value[k], k) for k in ("as_of", "start", "end"))
    if start > end or end > as_of or as_of > today:
        raise ValueError("economic dates must satisfy start <= end <= as_of <= today")
    _integer(value["max_pages"], 1, 20, "max_pages")
    _integer(value["page_size"], 1, 1000, "page_size")
    if value["provider"] == "fred":
        if value["vintage_mode"] != "snapshot_as_of" or "countries" in value or "indicators" in value:
            raise ValueError("FRED needs explicit snapshot_as_of and series only")
        items = value.get("series")
        if not isinstance(items, list) or not 1 <= len(items) <= 10:
            raise ValueError("one to ten explicit FRED series required")
        for item in items:
            required = {"id", "units", "frequency", "seasonal_adjustment"} if value["scope"] == "observations" else {"id"}
            _keys(item, {"id", "units", "frequency", "seasonal_adjustment"}, required, "FRED series")
            if not isinstance(item["id"], str) or not SERIES.fullmatch(item["id"]):
                raise ValueError("FRED series ID is unsafe")
            if any(not isinstance(item[k], str) or not item[k].strip() or len(item[k]) > 300 for k in ("units", "frequency", "seasonal_adjustment") if k in item):
                raise ValueError("FRED units, frequency and seasonal adjustment must be declared")
        if len({item["id"] for item in items}) != len(items):
            raise ValueError("duplicate FRED series")
    else:
        if value["vintage_mode"] != "retrieval_snapshot" or (require_current_snapshot and as_of != today) or "series" in value:
            raise ValueError("World Bank supports a current retrieval_snapshot only; historical vintages need a separately verified archive")
        if (start.month, start.day) != (1, 1) or (end.month, end.day) != (12, 31):
            raise ValueError("World Bank adapter supports explicit complete calendar-year windows only")
        countries, indicators = value.get("countries"), value.get("indicators")
        if (not isinstance(countries, list) or not 1 <= len(countries) <= 10 or len(set(countries)) != len(countries)
                or any(not isinstance(c, str) or not re.fullmatch(r"[A-Z]{3}", c) for c in countries)):
            raise ValueError("one to ten unique three-letter World Bank country codes required")
        if not isinstance(indicators, list) or not 1 <= len(indicators) <= 10:
            raise ValueError("one to ten World Bank indicators required")
        for item in indicators:
            _keys(item, {"id", "unit"}, {"id", "unit"} if value["scope"] == "observations" else {"id"}, "World Bank indicator")
            if (not isinstance(item["id"], str) or not SERIES.fullmatch(item["id"])
                    or ("unit" in item and (not isinstance(item["unit"], str) or len(item["unit"]) > 300))):
                raise ValueError("World Bank indicator ID and exact source unit required; an honestly blank unit is allowed")
        if len({item["id"] for item in indicators}) != len(indicators):
            raise ValueError("duplicate World Bank indicators")
    return value, path


def _rights(project, spec, allow_observations):
    binding = spec.get("dataset_manifest")
    if spec["scope"] == "metadata_only":
        if binding is not None:
            raise ValueError("metadata-only discovery must not imply dataset acquisition approval")
        return None
    if not allow_observations:
        raise ValueError("observation acquisition needs explicit allow_observations authorization")
    _keys(binding, {"path", "sha256"}, {"path", "sha256"}, "dataset manifest binding")
    if not re.fullmatch(r"data/manifests/[a-z0-9][a-z0-9._-]*\.json", str(binding["path"])):
        raise ValueError("observation rights must bind an actual canonical dataset manifest")
    manifest_path = path_in(project, binding["path"])
    if manifest_path.stat().st_size > 1_000_000:
        raise ValueError("economic rights manifest exceeds the bounded configuration size")
    if sha(manifest_path) != binding["sha256"]:
        raise ValueError("dataset manifest hash is stale")
    authorizations = path_in(project, "state/data-authorizations.json", exists=False)
    permission = read(authorizations).get("manifests", {}).get(binding["path"], {}) if authorizations.is_file() else {}
    if (permission.get("sha256") != binding["sha256"] or permission.get("cloud_use_confirmed") is not True
            or not isinstance(permission.get("actor"), str) or not permission["actor"].strip()):
        raise ValueError("economic observations require the existing protected owner data authorization")
    manifest = read(manifest_path)
    errors = validate_manifest(manifest)
    if errors or manifest.get("license", {}).get("confirmed_by_human") is not True:
        raise ValueError("observation acquisition needs a valid human-confirmed research-use licence")
    scope_fields = ("provider", "start", "end", "as_of", "vintage_mode", "series") if spec["provider"] == "fred" else ("provider", "start", "end", "as_of", "vintage_mode", "countries", "indicators")
    if manifest.get("provenance", {}).get("economic_scope") != {key: spec[key] for key in scope_fields}:
        raise ValueError("human-confirmed dataset manifest must cover these exact economic series, dates and vintage")
    hosts = {"fred": {"fred.stlouisfed.org", "api.stlouisfed.org"}, "worldbank": {"data.worldbank.org", "api.worldbank.org"}}[spec["provider"]]
    if any(urllib.parse.urlsplit(manifest[field]["url"] if field == "download" else manifest[field]).hostname not in hosts for field in ("source_url", "download")):
        raise ValueError("dataset manifest source and download must identify the selected official provider")
    return {"path": binding["path"], "sha256": binding["sha256"], "dataset_id": manifest["dataset_id"],
            "authorization_sha256": hashlib.sha256(json.dumps(permission, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}


def _url(provider, endpoint, parameters):
    base = "https://api.stlouisfed.org/fred/" if provider == "fred" else "https://api.worldbank.org/v2/"
    return base + endpoint + "?" + urllib.parse.urlencode(parameters)


def _fetch(url, provider, key, fetcher):
    """Never expose transport exceptions or key-echoing provider responses."""
    parsed = urllib.parse.urlsplit(url)
    expected_host = "api.stlouisfed.org" if provider == "fred" else "api.worldbank.org"
    if parsed.hostname != expected_host or parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("economic transport only permits its fixed official HTTPS origin")
    wire = url + ("&api_key=" + urllib.parse.quote(key, safe="") if key else "")
    try:
        payload, final, status, content_type = (fetcher or network_safety.fetch_bytes)(wire, max_bytes=MAX_RESPONSE_BYTES)
        target = urllib.parse.urlsplit(final)
        if target.scheme != "https" or target.hostname != expected_host or target.username or target.password or target.port not in {None, 443}:
            raise ValueError("unexpected response origin")
        if status != 200 or not isinstance(payload, bytes) or len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("invalid bounded response")
        if key and (key.encode() in payload or urllib.parse.quote(key, safe="").encode() in payload or key in str(content_type or "")):
            raise ValueError("credential echo")
        data = json.loads(payload.decode("utf-8"))
        if key and key in json.dumps(data, ensure_ascii=False):
            raise ValueError("decoded credential echo")
    except Exception:
        raise ValueError("economic provider request failed or returned unsafe data; request credentials were not recorded") from None
    return data, payload, {"url": url, "status": status, "content_type": str(content_type or "")[:150]}


def _number(value):
    if value is None or value == ".":
        return None
    if isinstance(value, bool):
        raise ValueError("economic observations must be finite numbers or explicit missing values")
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError("economic observations must be finite numbers or explicit missing values") from None
    if not math.isfinite(result):
        raise ValueError("economic observations must be finite")
    return result


def _retrieve(spec, fetcher):
    key = os.environ.get("FRED_API_KEY", "") if spec["provider"] == "fred" else ""
    if spec["provider"] == "fred" and not re.fullmatch(r"[A-Za-z0-9]{32}", key):
        raise ValueError("FRED_API_KEY must be configured in the cloud secret environment")
    raws, requests, metadata, observations = [], [], [], []
    def get(endpoint, parameters):
        if len(raws) >= 64:
            raise ValueError("economic request exceeded its bounded request count")
        data, payload, receipt = _fetch(_url(spec["provider"], endpoint, parameters), spec["provider"], key, fetcher)
        if sum(len(raw) for raw in raws) + len(payload) > MAX_TOTAL_BYTES:
            raise ValueError("economic request exceeded its total response-byte limit")
        raws.append(payload); requests.append(receipt)
        return data
    if spec["provider"] == "fred":
        base = {"file_type": "json", "realtime_start": spec["as_of"], "realtime_end": spec["as_of"]}
        for item in spec["series"]:
            common = {**base, "series_id": item["id"]}
            info = get("series", common)
            entries = info.get("seriess") if isinstance(info, dict) else None
            if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict) or entries[0].get("id") != item["id"]:
                raise ValueError("FRED metadata must identify the exact requested series")
            if info.get("realtime_start") != spec["as_of"] or info.get("realtime_end") != spec["as_of"]:
                raise ValueError("FRED metadata returned a different historical-vintage scope")
            meta = entries[0]
            if any(meta.get(k) != item[k] for k in ("units", "frequency", "seasonal_adjustment") if k in item):
                raise ValueError("FRED variable units/frequency/seasonal adjustment differ from the declared dictionary")
            metadata.append(meta)
            if spec["scope"] != "observations":
                continue
            offset, count = 0, None
            for page in range(spec["max_pages"]):
                value = get("series/observations", {**common, "observation_start": spec["start"], "observation_end": spec["end"],
                    "limit": spec["page_size"], "offset": offset, "sort_order": "asc", "units": "lin", "output_type": 1})
                if not isinstance(value, dict):
                    raise ValueError("FRED observation response must be an object")
                rows = value.get("observations")
                total = _integer(value.get("count"), 0, 100000, "FRED count")
                if value.get("realtime_start") != spec["as_of"] or value.get("realtime_end") != spec["as_of"]:
                    raise ValueError("FRED observations returned a different historical-vintage scope")
                if not isinstance(rows, list) or value.get("offset") != offset or value.get("limit") != spec["page_size"] or len(rows) > spec["page_size"]:
                    raise ValueError("FRED pagination receipt does not match the actual request")
                if count is not None and count != total:
                    raise ValueError("FRED count changed during pagination")
                count = total
                for row in rows:
                    if not isinstance(row, dict):
                        raise ValueError("FRED observation must be an object")
                    when = _date(row.get("date"), "FRED observation date")
                    if not _date(spec["start"], "start") <= when <= _date(spec["end"], "end"):
                        raise ValueError("FRED returned observations outside the declared time range")
                    if not _date(row.get("realtime_start"), "observation vintage start") <= _date(spec["as_of"], "as_of") <= _date(row.get("realtime_end"), "observation vintage end"):
                        raise ValueError("FRED returned a different historical-vintage scope")
                    observations.append({"provider": "fred", "series": item["id"], "country": "", "date": row["date"], "value": _number(row.get("value"))})
                offset += len(rows)
                if offset == count:
                    break
                if not rows or offset > count:
                    raise ValueError("FRED pagination is incomplete or inconsistent")
            if offset != count:
                raise ValueError("FRED pagination cap reached before all declared observations were retrieved")
    else:
        for item in spec["indicators"]:
            info = get("indicator/" + item["id"], {"format": "json"})
            if (not isinstance(info, list) or len(info) != 2 or not isinstance(info[1], list) or len(info[1]) != 1
                    or not isinstance(info[1][0], dict) or info[1][0].get("id") != item["id"] or ("unit" in item and info[1][0].get("unit") != item["unit"])):
                raise ValueError("World Bank indicator metadata/unit does not match the declared variable")
            metadata.append(info[1][0])
            if spec["scope"] != "observations":
                continue
            endpoint = "country/" + ";".join(spec["countries"]) + "/indicator/" + item["id"]
            total, pages, obtained = None, None, 0
            for page in range(1, spec["max_pages"] + 1):
                value = get(endpoint, {"format": "json", "date": spec["start"][:4] + ":" + spec["end"][:4], "per_page": spec["page_size"], "page": page})
                if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], dict):
                    raise ValueError("World Bank pagination structure is invalid")
                header, rows = value
                current_total = _integer(header.get("total"), 0, 100000, "World Bank total")
                current_pages = _integer(header.get("pages"), 0, 100000, "World Bank pages")
                try:
                    current_page, per_page = int(header.get("page")), int(header.get("per_page"))
                except (ValueError, TypeError):
                    raise ValueError("World Bank pagination is invalid") from None
                if (current_page != page or per_page != spec["page_size"] or not isinstance(rows, list)
                        or len(rows) > spec["page_size"] or current_pages != max(1, math.ceil(current_total / per_page))):
                    raise ValueError("World Bank pagination does not reconcile to the requested page size")
                if total is not None and (current_total != total or current_pages != pages):
                    raise ValueError("World Bank pagination totals changed during retrieval")
                total, pages = current_total, current_pages
                for row in rows:
                    if not isinstance(row, dict) or not isinstance(row.get("indicator"), dict):
                        raise ValueError("World Bank observation must identify its indicator")
                    year = row.get("date")
                    country = row.get("countryiso3code")
                    if (row.get("indicator", {}).get("id") != item["id"] or country not in spec["countries"]
                            or not isinstance(year, str) or not re.fullmatch(r"\d{4}", year)
                            or not int(spec["start"][:4]) <= int(year) <= int(spec["end"][:4])):
                        raise ValueError("World Bank observations differ from the requested indicator/country/year scope")
                    observations.append({"provider": "worldbank", "series": item["id"], "country": country, "date": year, "value": _number(row.get("value"))})
                obtained += len(rows)
                if page == pages:
                    break
            if total != obtained or page != pages:
                raise ValueError("World Bank pagination is truncated or inconsistent")
    keys = [(row["series"], row["country"], row["date"]) for row in observations]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate series/country/time keys in economic observations")
    return metadata, observations, raws, requests


def _immutable(path, payload):
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError("economic snapshot is immutable; reconcile prior data before retrying")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)


def _receipt_path(request_id):
    return f"{PREFIX}/{request_id}/latest.json"


def validate_saved_report(project: Path, request_id: str) -> list[str]:
    """Recheck request, rights, implementation, protected origin and every byte."""
    try:
        spec, source = _spec(project, request_id)
        rights = _rights(project, spec, True)
        target = path_in(project, _receipt_path(request_id))
        from scripts.output_provenance import current_origin
        if current_origin(project, target).get("provider") != "deterministic-control-plane":
            raise ValueError("economic receipt lacks current control-plane provenance")
        value = read(target)
        retrieved = datetime.fromisoformat(value["retrieved_at"])
        if retrieved.tzinfo is None or retrieved > datetime.now(timezone.utc):
            raise ValueError("economic receipt needs an actual past timezone-aware retrieval time")
        if spec["provider"] == "worldbank" and retrieved.date().isoformat() != spec["as_of"]:
            raise ValueError("World Bank retrieval day does not match the explicit current snapshot")
        if value.get("request") != {"path": request_path(request_id), "sha256": sha(source)} or value.get("implementation_sha256") != sha(Path(__file__)):
            raise ValueError("economic request or implementation changed")
        if value.get("rights") != rights or value.get("scientific_validity_verified") is not False or value.get("gate_approved") is not False:
            raise ValueError("economic rights or authority changed")
        snapshot = path_in(project, value["snapshot"]["path"])
        if sha(snapshot) != value["snapshot"]["sha256"]:
            raise ValueError("economic immutable snapshot receipt changed")
        original = read(snapshot)
        if {k: v for k, v in value.items() if k != "snapshot"} != original:
            raise ValueError("economic latest pointer no longer matches its immutable snapshot")
        for output in value["outputs"]:
            target_output = path_in(project, output["path"])
            if sha(target_output) != output["sha256"]:
                raise ValueError("economic source bytes changed")
        return []
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        return [str(exc)]


def execute(project: Path, request_id: str, *, allow_observations: bool = False, fetcher=None) -> dict:
    _cloud()
    spec, source = _spec(project, request_id)
    rights = _rights(project, spec, allow_observations)
    current = path_in(project, _receipt_path(request_id), exists=False)
    if current.is_file() and not validate_saved_report(project, request_id):
        return {"path": _receipt_path(request_id), "sha256": sha(current), "reused": True, "report": read(current)}
    _spec(project, request_id, require_current_snapshot=True)
    request_hash = sha(source)
    snapshot_rel = f"{PREFIX}/{request_id}/{request_hash}/receipt.json"
    if path_in(project, snapshot_rel, exists=False).exists():
        raise ValueError("existing economic snapshot is stale or altered; preserve it and use a new reviewed request ID")
    metadata, observations, raws, requests = _retrieve(spec, fetcher)
    outputs, generated = [], []
    for number, payload in enumerate(raws, 1):
        rel = f"{RAW}/{request_id}/{request_hash}/response-{number:03d}.json"
        target = path_in(project, rel, exists=False); _immutable(target, payload)
        outputs.append({"path": rel, "sha256": sha(target)}); generated.append(target)
    metadata_rel = f"{PREFIX}/{request_id}/{request_hash}/metadata.json"
    target = path_in(project, metadata_rel, exists=False)
    _immutable(target, (json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    outputs.append({"path": metadata_rel, "sha256": sha(target)}); generated.append(target)
    if spec["scope"] == "observations":
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=["provider", "series", "country", "date", "value"], lineterminator="\n")
        writer.writeheader(); writer.writerows(observations)
        rel = f"{RAW}/{request_id}/{request_hash}/observations.csv"
        target = path_in(project, rel, exists=False); _immutable(target, buffer.getvalue().encode())
        outputs.append({"path": rel, "sha256": sha(target)}); generated.append(target)
    result = {"schema_version": "1.0", "id": request_id, "provider": spec["provider"], "scope": spec["scope"],
        "request": {"path": request_path(request_id), "sha256": request_hash}, "rights": rights,
        "implementation_sha256": sha(Path(__file__)), "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "as_of": spec["as_of"], "vintage_mode": spec["vintage_mode"], "requests": requests,
        "outputs": outputs, "metadata_count": len(metadata), "observation_count": len(observations),
        "missing_observations": sum(row["value"] is None for row in observations), "pagination_complete": True,
        "historical_availability_verified": False, "scientific_validity_verified": False, "gate_approved": False,
        "paid_model_calls": 0, "limitations": ["Retrieval verifies source bytes and declared scope, not fitness, causal identification or journal quality.",
            "World Bank retrieval snapshots are not historical vintages; FRED as-of selection is provider-declared and still requires substantive review."]}
    snapshot = path_in(project, snapshot_rel, exists=False)
    _immutable(snapshot, (json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode())
    latest = {**result, "snapshot": {"path": snapshot_rel, "sha256": sha(snapshot)}}
    write(current, latest); record(project, [*generated, snapshot, current], MODULE)
    return {"path": _receipt_path(request_id), "sha256": sha(current), "reused": False, "report": latest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--allow-observations", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(execute(args.project_root, args.request_id, allow_observations=args.allow_observations), indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
