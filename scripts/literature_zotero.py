"""Read-only Zotero Web API/export bridge for the existing cloud library.

Bibliographic records are discovery leads. No attachment, note, credential,
scientific decision or Zotero server write is copied into the workbench.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

from scripts import literature_evidence as evidence, literature_workbench as wb
from scripts.research_artifacts import path_in, record, sha, write

OUTPUT = "reports/literature-zotero"
KEY = re.compile(r"^[A-Z0-9]{8}$")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Zotero API redirect forbidden; credentials remain on api.zotero.org")


def _get(url, authenticated):
    headers = {"Zotero-API-Version": "3", "Accept": "application/json"}
    if authenticated:
        key = os.environ.get("ZOTERO_API_KEY", "")
        if not key.strip() or any(c in key for c in "\r\n"):
            raise ValueError("private Zotero reads require ZOTERO_API_KEY in cloud secrets")
        headers["Zotero-API-Key"] = key
    try:
        with build_opener(_NoRedirect).open(Request(url, headers=headers), timeout=30) as response:
            data = response.read(8_000_001)
            if response.geturl() != url or len(data) > 8_000_000:
                raise ValueError("Zotero API redirected or exceeded the response bound")
            version = response.headers.get("Last-Modified-Version")
            total = response.headers.get("Total-Results")
    except OSError:
        # Do not persist a transport object's potentially credential-bearing repr.
        raise ValueError("Zotero read failed; inspect library permission or service availability") from None
    if not str(version).isdigit() or (total is not None and not str(total).isdigit()):
        raise ValueError("Zotero response needs actual library version and numeric result count")
    return data, int(version), int(total) if total is not None else None


def _item(value):
    if not isinstance(value, dict):
        raise ValueError("Zotero item must be an object")
    data = value.get("data", value)
    key = value.get("key", data.get("key")) if isinstance(data, dict) else None
    if not isinstance(data, dict) or not KEY.fullmatch(str(key)):
        raise ValueError("Zotero items require their actual eight-character key")
    version = value.get("version", data.get("version"))
    if version is not None and (type(version) is not int or version < 0):
        raise ValueError("invalid Zotero item version")
    # Notes, annotations and attachment bytes are neither bibliography nor rights.
    if data.get("itemType") in {"note", "attachment", "annotation"}:
        return key, {"key": key, "version": version, "status": "nonbibliographic_not_imported"}
    title = data.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 5000:
        raise ValueError("bibliographic item needs a bounded actual title")
    names = []
    creators = data.get("creators", [])
    if not isinstance(creators, list) or len(creators) > 1000:
        raise ValueError("invalid creators")
    for creator in creators:
        if isinstance(creator, dict):
            names.append(str(creator.get("name") or " ".join(str(creator.get(k, "")) for k in ("firstName", "lastName"))).strip())
    date = str(data.get("date") or "")[:200]
    year = re.search(r"\b(?:18|19|20|21)\d{2}\b", date)
    work = evidence.normalized_work("zotero", key, title, int(year[0]) if year else None,
        data.get("DOI"), None, names, abstract=data.get("abstractNote"),
        venue=data.get("publicationTitle"), publication_date=None)
    return key, {"key": key, "version": version, "status": "bibliographic_metadata_only",
                 "date_as_exported": date, "work": work, "full_text_checked": False}


def _spec(project, spec):
    allowed = {"schema_version", "id", "mode", "library_type", "library_id", "authenticated", "max_items", "export"}
    if not isinstance(spec, dict) or set(spec) - allowed or spec.get("schema_version") != "1.0":
        raise ValueError("unsupported Zotero request")
    identifier = wb._id(spec.get("id"))
    maximum = spec.get("max_items", 500)
    if type(maximum) is not int or not 1 <= maximum <= 5000:
        raise ValueError("Zotero max_items must be 1..5000")
    mode = spec.get("mode")
    if mode == "web":
        if spec.get("library_type") not in {"users", "groups"} or not re.fullmatch(r"[1-9][0-9]{0,11}", str(spec.get("library_id", ""))):
            raise ValueError("Zotero Web API needs actual users/groups library ID")
        if type(spec.get("authenticated", False)) is not bool or "export" in spec:
            raise ValueError("web authentication is a boolean; no key or export in requests")
    elif mode == "export":
        binding = spec.get("export")
        if not isinstance(binding, dict) or set(binding) != {"path", "sha256"}:
            raise ValueError("Zotero export needs an exact source binding")
        source = wb._path(project, binding["path"], corpus=True)
        if source.suffix.lower() != ".json" or source.stat().st_size > 8_000_000 or sha(source) != binding["sha256"]:
            raise ValueError("Zotero JSON export changed or exceeds 8 MB")
        if any(k in spec for k in ("library_type", "library_id", "authenticated")):
            raise ValueError("export imports cannot assert web library identity")
    else:
        raise ValueError("Zotero mode must be web or export")
    return identifier, maximum


def _saved(project, directory):
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        return None
    from scripts.output_provenance import current_origin
    manifest = wb._json(manifest_path.read_bytes())
    if manifest.get("implementation_sha256") != sha(Path(__file__)):
        raise ValueError("Zotero implementation changed; refresh with a new import ID")
    for binding in manifest.get("files", []):
        path = path_in(project, binding["path"])
        if sha(path) != binding["sha256"] or current_origin(project, path).get("status") != "tracked":
            raise ValueError("Zotero receipt/output changed")
    if current_origin(project, manifest_path).get("status") != "tracked":
        raise ValueError("Zotero manifest lacks executor provenance")
    return wb._json((directory / "index.json").read_bytes())


def build(project, spec, *, fetch=None):
    from scripts.literaturectl import require_cloud
    require_cloud()
    identifier, maximum = _spec(project, spec)
    relative = OUTPUT + "/" + identifier
    directory = path_in(project, relative, exists=False)
    previous = _saved(project, directory)
    identity = {k: spec.get(k) for k in ("mode", "library_type", "library_id", "authenticated")}
    if previous and previous.get("library") != identity:
        raise ValueError("use a new Zotero import ID when changing library identity")
    files, receipts = [], []
    records = {r["key"]: r for r in previous.get("items", [])} if previous and spec["mode"] == "web" else {}
    previous_version = previous.get("library_version", 0) if previous else 0
    version, removed = None, []
    if spec["mode"] == "export":
        source = path_in(project, spec["export"]["path"])
        payload = wb._json(source.read_bytes())
        items = payload.get("items") if isinstance(payload, dict) else payload
        if not isinstance(items, list) or len(items) > maximum:
            raise ValueError("Zotero export exceeds the declared item bound")
        version, batches = None, [items]
        receipts.append({"mode": "export", "source": spec["export"], "search_executed": False})
    else:
        get = fetch or _get
        prefix = f"https://api.zotero.org/{spec['library_type']}/{spec['library_id']}"
        batches, offset, returned_keys = [], 0, set()
        while True:
            url = prefix + "/items?" + urlencode({"format": "json", "limit": 100, "start": offset, "since": previous_version})
            raw, current_version, total = get(url, spec.get("authenticated", False))
            if version is not None and current_version != version:
                raise ValueError("Zotero library changed during pagination; no partial snapshot committed")
            version = current_version
            if version < previous_version or total is None or total > maximum:
                raise ValueError("Zotero library version/count exceeds the declared consistent scope")
            items = wb._json(raw)
            if not isinstance(items, list) or len(items) > 100 or offset + len(items) > total:
                raise ValueError("invalid Zotero page/count")
            digest = hashlib.sha256(raw).hexdigest()
            raw_path = directory / "responses" / (digest + ".json")
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            # Keep only the reviewed projection. Private notes/annotations and
            # attachment metadata must not leak via an ostensibly raw receipt.
            write(raw_path, {"raw_response_sha256": digest, "raw_response_not_retained": True,
                             "items": [_item(item)[1] for item in items]})
            files.append(raw_path)
            receipts.append({"url": url, "raw_response_sha256": digest,
                             "sanitized_projection": {"path": raw_path.relative_to(project).as_posix(), "sha256": sha(raw_path)},
                             "library_version": version, "total_results": total, "returned": len(items)})
            for item in items:
                key, _ = _item(item)
                if key in returned_keys:
                    raise ValueError("duplicate Zotero key across pages")
                returned_keys.add(key)
            batches.append(items)
            offset += len(items)
            if offset == total:
                break
            if not items:
                raise ValueError("Zotero pagination ended before actual Total-Results")
        if previous_version:
            url = prefix + "/deleted?" + urlencode({"since": previous_version})
            raw, deleted_version, _ = get(url, spec.get("authenticated", False))
            if deleted_version != version:
                raise ValueError("Zotero library changed while reading deletions")
            deleted = wb._json(raw)
            removed = deleted.get("items") if isinstance(deleted, dict) else None
            if not isinstance(removed, list) or any(not KEY.fullmatch(str(k)) for k in removed):
                raise ValueError("invalid Zotero deleted item keys")
            raw_path = directory / "responses" / (hashlib.sha256(raw).hexdigest() + ".json")
            write(raw_path, {"raw_response_sha256": hashlib.sha256(raw).hexdigest(), "deleted_item_keys": removed})
            files.append(raw_path)
            receipts.append({"url": url, "response": {"path": raw_path.relative_to(project).as_posix(), "sha256": sha(raw_path)},
                             "library_version": version, "deletions": len(removed)})
    changed = []
    for batch in batches:
        for item in batch:
            key, row = _item(item)
            if key in changed:
                raise ValueError("duplicate item in Zotero source")
            if row != records.get(key):
                changed.append(key)
            records[key] = row
    for key in removed:
        records.pop(key, None)
    if len(records) > maximum:
        raise ValueError("merged Zotero library exceeds max_items; narrow the source")
    report = {"schema_version": "1.0", "kind": "cloud_zotero_bibliography", "library": identity,
        "request_sha256": wb._digest(spec),
        "library_version": version, "previous_version": previous_version,
        "items": [records[k] for k in sorted(records)], "changed_keys": sorted(changed),
        "removed_keys": sorted(removed), "receipts": receipts, "read_only": True,
        "paid_calls": 0, "attachments_downloaded": False, "full_text_checked": False,
        "imported_at": datetime.now(timezone.utc).isoformat(), "scientific_inclusion": False}
    index = directory / "index.json"
    write(index, report)
    page = directory / "index.html"
    page.write_text("<!doctype html><meta charset='utf-8'><title>Zotero bibliography</title><h1>Zotero bibliography</h1>"
        "<p>Metadata leads only. No PDF, scientific screening or server writes.</p><ul>" + "".join(
        "<li>" + html.escape(r.get("work", {}).get("title", r["status"])) + "</li>" for r in report["items"]) + "</ul>", encoding="utf-8")
    files += [index, page]
    manifest = directory / "manifest.json"
    write(manifest, {"implementation_sha256": sha(Path(__file__)), "files": [
        {"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in dict.fromkeys(files)]})
    record(project, [*dict.fromkeys(files), manifest], "scripts/literature_zotero.py")
    return {**report, "report_path": relative + "/index.json", "html_path": relative + "/index.html"}


def refresh(project, request_path="program/literature-zotero.json"):
    if not isinstance(request_path, str) or not request_path.startswith("program/"):
        raise ValueError("Zotero request belongs under program/")
    source = path_in(project, request_path)
    if source.stat().st_size > 64000:
        raise ValueError("Zotero request exceeds 64 KB")
    return build(project, wb._json(source.read_bytes()))


def validate_saved_report(project, request_path="program/literature-zotero.json"):
    spec = wb._json(path_in(project, request_path).read_bytes())
    identifier, _ = _spec(project, spec)
    report = _saved(project, path_in(project, OUTPUT + "/" + identifier, exists=False))
    if report is None:
        raise ValueError("Zotero report missing")
    if report.get("request_sha256") != wb._digest(spec):
        raise ValueError("Zotero request changed")
    return report


def register(project, request_path, item_key, *, paper_id=None):
    """Put one actual imported bibliography item in the shared metadata library.

    Versioned source identities preserve older entries. No PDF right, reading
    coverage, thesis mapping or scientific inclusion is granted by this bridge.
    """
    from scripts.literaturectl import require_cloud
    require_cloud()
    report = validate_saved_report(project, request_path)
    matches = [row for row in report["items"] if row["key"] == item_key and row["status"] == "bibliographic_metadata_only"]
    if len(matches) != 1:
        raise ValueError("select one current actual bibliographic item key")
    row = matches[0]
    content = {"library": report["library"], "item": row}
    identity = wb._digest(content)
    identifier = wb._id(paper_id or "zotero-" + item_key.lower() + "-" + identity[:12])
    relative = "literature/zotero-metadata/" + identity + ".md"
    source = path_in(project, relative, exists=False)
    work = row["work"]
    text = "# Bibliographic discovery metadata\n\n" + work["title"] + "\n\nDOI: " + (work.get("doi") or "unknown") + \
        "\n\nAuthors: " + ", ".join(work.get("authors", [])) + "\n\nAbstract as exported (unverified):\n" + \
        (work.get("abstract") or "unknown") + "\n\nNot original full text, reading completion or scientific inclusion.\n\n" + json.dumps(content, ensure_ascii=False, sort_keys=True) + "\n"
    if source.exists() and source.read_text(encoding="utf-8") != text:
        raise ValueError("refusing to overwrite a different Zotero metadata source")
    config_path = path_in(project, wb.CONFIG, exists=False)
    config = wb._json(config_path.read_bytes()) if config_path.exists() else {"schema_version": "1.0", "papers": []}
    papers = config.get("papers")
    if not isinstance(papers, list):
        raise ValueError("current shared library has invalid papers")
    entry = {"id": identifier, "title": work["title"], "topic_id": "zotero-discovery",
        "paper_ids": [], "source_scope": "metadata_only", "source": {"path": relative, "sha256": hashlib.sha256(text.encode()).hexdigest()}}
    existing = [p for p in papers if p.get("id") == identifier]
    if existing and existing != [entry]:
        raise ValueError("paper ID already belongs to another source/version")
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(text, encoding="utf-8")
    if not existing:
        papers.append(entry)
    write(config_path, config)
    record(project, [source, config_path], "scripts/literature_zotero.py")
    built = wb.build(project)
    return {"paper_id": identifier, "source": entry["source"], "reused": bool(existing),
        "attachment_status": "metadata_only", "human_screening_approved": False,
        "paid_calls": 0, "workbench": built}
