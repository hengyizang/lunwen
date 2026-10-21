"""Persistent, deterministic, source-bound personal literature workbench.

No network, embeddings, paid model calls, scientific approvals or experiments.
``build(project, config_path=None, output_dir=None)`` prepares the static views;
``search``, ``itinerary`` and ``comparison_packet`` consume that exact snapshot.
Inputs are explicit project-relative hash bindings; discovery is pending only.
Cards contain fields of {text, kind, evidence, inference_boundary?}. Evidence
requires path, sha256, start_line, end_line, quote (and pdf_page for a reader).
Located quotations are not semantic verification or human full-text reading.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import quote, urlsplit

from scripts.research_artifacts import path_in, read, record, sha, write

CONFIG = "program/literature-workbench.json"
OUTPUT = "reports/literature-workbench"
FIELDS = ("research_question", "contributions", "methods", "baseline", "splits",
          "metrics", "ablations", "findings", "limitations", "counterevidence")
KINDS = {"author_claim", "model_inference", "human_interpretation"}
RELATIONS = {"cites", "extends", "supports", "contradicts", "compares_with",
             "replicates", "uses_baseline", "uses_dataset", "shares_method"}
DISCOVERY = ("literature/notes", "literature/readers", "literature/cards",
             "evidence/notes", "evidence/readers", "evidence/reading-cards")
BLOCKED = {"state", "api_runs", "raw", "private", "credentials", "secrets",
           "reviews", "review-packets", "submission", "manuscript-hygiene"}
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")
STOPWORDS = {"the", "and", "this", "that", "with", "from", "what", "which", "paper", "study"}
MAX_TEXT = 2_000_000
MAX_TOTAL = 100_000_000


def _json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON field in workbench input")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON value in workbench input")
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _id(value, label="ID"):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError(label + " must be a safe nonempty identifier")
    return value


def _text(value, label, maximum=6000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(label + " needs bounded nonempty text")
    return value


def _path(project, relative, *, exists=True, corpus=False):
    if not isinstance(relative, str):
        raise ValueError("path must be project-relative text")
    parts = Path(relative).parts
    if any(p.startswith(".") or p.casefold() in BLOCKED for p in parts):
        raise ValueError("private/control/hidden paths are not workbench inputs")
    if any(word in Path(relative).name.casefold() for word in
           ("api_key", "apikey", "credential", "password", "secret", "token")):
        raise ValueError("sensitive filenames are not workbench inputs")
    if corpus and (not parts or parts[0] not in {"literature", "evidence"}):
        raise ValueError("sources, readers, notes and cards must be controlled literature/evidence files")
    return path_in(project, relative, exists=exists)


def _output(project, relative=None):
    relative = OUTPUT if relative is None else relative
    path = _path(project, relative, exists=False)
    if not relative.startswith("reports/") or len(Path(relative).parts) < 2:
        raise ValueError("workbench output must be a dedicated directory under reports/")
    if path.exists() and not path.is_dir():
        raise ValueError("workbench output must be a directory")
    return relative, path


class _Files:
    """Read each dependency's bytes once per build, with explicit size ceilings."""
    def __init__(self, project):
        self.project, self.cache, self.total = project, {}, 0
        self.approved_pdfs = {}
        self.approved_assets = {}

    def get(self, relative, *, corpus=True):
        # Recheck the generic boundary even when a binary PDF dependency is
        # already cached through the separately authorized source-only route.
        path = _path(self.project, relative, corpus=corpus)
        if relative not in self.cache:
            limit = 30_000_000 if path.suffix.lower() == ".pdf" else MAX_TEXT
            if path.stat().st_size > limit:
                raise ValueError("source exceeds workbench size limit: " + relative)
            data = path.read_bytes()
            self.total += len(data)
            if self.total > MAX_TOTAL:
                raise ValueError("workbench input exceeds 100 MB; narrow the library")
            self.cache[relative] = (data, hashlib.sha256(data).hexdigest())
        return self.cache[relative]

    def binding(self, value, *, corpus=True):
        if not isinstance(value, dict) or not HASH.fullmatch(str(value.get("sha256", ""))):
            raise ValueError("input binding requires its exact SHA-256")
        _, digest = self.get(value.get("path"), corpus=corpus)
        if value["sha256"] != digest:
            raise ValueError("stale input hash: " + value["path"])
        return {"path": value["path"], "sha256": digest}

    def text(self, relative):
        if Path(relative).suffix.lower() == ".pdf":
            raise ValueError("binary PDFs are never indexed or sent as text; use the controlled reader")
        data, _ = self.get(relative)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("source must be UTF-8 text or a controlled PDF reader") from exc


def source_binding(project: Path, source: dict, *, manifest=None, files=None) -> dict:
    """Bind an original source; the raw exception permits authorized PDF bytes only.

    Authority is checked afresh on use, never inferred from an acquisition lead.
    Original raw assets stay quarantined and never become text/model inputs.
    """
    files = _Files(project) if files is None else files
    if not isinstance(source, dict) or not isinstance(source.get("path"), str):
        raise ValueError("source requires a project-relative hash binding")
    relative = source["path"]
    if not relative.startswith("data/raw/literature/"):
        return files.binding(source)
    prior = files.approved_pdfs.get(relative)
    if prior and prior["sha256"] == source.get("sha256") and prior["manifest"] == manifest:
        return {"path": relative, "sha256": prior["sha256"]}
    if (not HASH.fullmatch(str(source.get("sha256", ""))) or Path(relative).suffix.lower() != ".pdf"
            or any(p.startswith(".") or p.casefold() in (BLOCKED - {"raw"}) for p in Path(relative).parts)):
        raise ValueError("raw source exception permits only a bounded original PDF")
    if not isinstance(manifest, str) or not manifest.startswith("data/manifests/"):
        raise ValueError("raw PDF source requires its exact reviewed data manifest")
    # Late import avoids a control-plane/workbench import cycle.
    from scripts.literaturectl import approved_pdf
    candidate = approved_pdf(project, relative, manifest)
    if candidate.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("authorized original PDF exceeds 64 MiB")
    with candidate.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise ValueError("raw original source must have PDF magic")
    path = approved_pdf(project, relative, manifest)
    if path != path_in(project, relative) or path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("authorized original PDF exceeds 64 MiB or resolves differently")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if not data.startswith(b"%PDF-") or digest != source["sha256"]:
        raise ValueError("raw original PDF magic or exact source hash differs")
    if relative not in files.cache:
        files.total += len(data)
        if files.total > MAX_TOTAL:
            raise ValueError("workbench input exceeds 100 MB; narrow the library")
        files.cache[relative] = (data, digest)
    files.approved_pdfs[relative] = {"path": relative, "sha256": digest, "manifest": manifest}
    files.get(manifest, corpus=False)
    return {"path": relative, "sha256": digest}


def _asset_binding(project, value, source, manifest, files):
    """Binary-only original figure assets inherit the exact reviewed PDF authority."""
    if not isinstance(value, dict) or not HASH.fullmatch(str(value.get("sha256", ""))):
        raise ValueError("figure asset requires an exact source hash")
    relative = value.get("path")
    allowed = {".png", ".jpg", ".jpeg", ".jp2", ".tif", ".tiff", ".bmp", ".bin"}
    prefix = "data/raw/literature/figures/" + source["sha256"][:24] + "/"
    if (not isinstance(relative, str) or not relative.startswith(prefix)
            or Path(relative).suffix.lower() not in allowed or Path(relative).stem != value["sha256"]):
        raise ValueError("figure asset must be a content-addressed binary derived from this exact PDF")
    if not manifest:
        raise ValueError("figure previews require the original PDF's reviewed owner authority")
    from scripts.literaturectl import approved_pdf
    if source["path"].startswith("data/raw/literature/"):
        source_binding(project, source, manifest=manifest, files=files)
    else:
        approved_pdf(project, source["path"], manifest)
    path = path_in(project, relative)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("figure asset exceeds 64 MiB")
    if relative not in files.cache:
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != value["sha256"]:
            raise ValueError("figure asset hash changed")
        suffix = path.suffix.lower()
        if (suffix == ".png" and not data.startswith(b"\x89PNG\r\n\x1a\n")
                or suffix in {".jpg", ".jpeg"} and not data.startswith(b"\xff\xd8\xff")):
            raise ValueError("figure preview signature does not match its declared image type")
        files.total += len(data)
        if files.total > MAX_TOTAL:
            raise ValueError("workbench input exceeds 100 MB; select fewer figures")
        files.cache[relative] = (data, digest)
    elif files.cache[relative][1] != value["sha256"]:
        raise ValueError("conflicting figure asset hash bindings")
    result = {"path": relative, "sha256": value["sha256"]}
    files.approved_assets[relative] = {**result, "source": source, "manifest": manifest}
    return result


def _figures(project, binding, source, manifest, files):
    bound = files.binding(binding)
    value = _json(files.get(bound["path"])[0])
    if (not isinstance(value, dict) or value.get("schema_version") != 1
            or value.get("source_pdf_sha256") != source["sha256"]
            or value.get("source_pdf") != source["path"]
            or type(value.get("pdf_page_count")) is not int or not 1 <= value["pdf_page_count"] <= 100
            or not isinstance(value.get("assets"), list) or len(value["assets"]) > 500):
        raise ValueError("figure manifest must bind this exact original PDF and bounded actual pages/assets")
    assets = []
    for asset in value["assets"]:
        bound_asset = _asset_binding(project, asset, source, manifest, files)
        occurrences = asset.get("occurrences", [asset])
        if not isinstance(occurrences, list) or not 1 <= len(occurrences) <= 1000:
            raise ValueError("figure asset occurrences must be explicit and bounded")
        locations = []
        for occurrence in occurrences:
            page = occurrence.get("pdf_page")
            if type(page) is not int or not 1 <= page <= value["pdf_page_count"]:
                raise ValueError("figure occurrence page lies outside the original PDF")
            if occurrence.get("kind") not in {"image_object", "page_render", "source_crop"}:
                raise ValueError("figure occurrence must retain its original extraction kind")
            labels = {}
            for key in ("figure_number", "table_number", "caption"):
                label = occurrence.get(key)
                if label is not None and (not isinstance(label, str) or len(label) > 6000):
                    raise ValueError("original figure labels/captions must be bounded text or unknown")
                labels[key] = label
            locations.append({"pdf_page": page, "kind": occurrence["kind"], **labels,
                              "bbox": occurrence.get("bbox"), "semantic_verification": False})
        assets.append({**bound_asset, "occurrences": locations, "source_pdf_sha256": source["sha256"],
                       "previewable": Path(bound_asset["path"]).suffix.lower() in {".png", ".jpg", ".jpeg"}})
    return {**bound, "assets": assets, "source_pdf_sha256": source["sha256"],
            "labels_not_inferred": True, "semantic_verification": False}


def _reader(project, spec, source, files):
    """Check the native extraction receipt, actual bytes, page scope and origin."""
    from scripts import paper_reader
    from scripts.output_provenance import current_origin
    if Path(source["path"]).suffix.lower() != ".pdf":
        raise ValueError("native reader replacement requires its bound original PDF source")
    reader = files.binding(spec)
    path = Path(reader["path"])
    if path.suffix.lower() != ".md":
        raise ValueError("native PDF reader must be markdown")
    receipt_rel = path.with_suffix(".reader.json").as_posix()
    raw, receipt_hash = files.get(receipt_rel)
    receipt = _json(raw)
    if not isinstance(receipt, dict):
        raise ValueError("native reader receipt must be an object")
    origin = current_origin(project, _path(project, receipt_rel, corpus=True))
    if origin.get("status") != "tracked" or origin.get("family") == "anthropic":
        raise ValueError("native reader receipt requires current controlled non-Claude provenance")
    if (receipt.get("pdf_sha256") != source["sha256"]
            or receipt.get("reader_sha256") != reader["sha256"]
            or receipt.get("reader_implementation_sha256") != sha(Path(paper_reader.__file__))):
        raise ValueError("native reader source/output/implementation binding changed")
    mapping = files.binding(receipt.get("source_map"))
    source_map = _json(files.get(mapping["path"])[0])
    if not isinstance(source_map, dict):
        raise ValueError("native reader source map must be an object")
    if (source_map.get("source_sha256") != source["sha256"]
            or source_map.get("reader_sha256") != reader["sha256"]):
        raise ValueError("native reader map does not bind this source and reader")
    text = files.text(reader["path"])
    lines, ranges = text.splitlines(), {}
    heading = re.compile(r"## PDF page ([1-9][0-9]*)\s*\Z")
    for i, line in enumerate(lines):
        match = heading.fullmatch(line)
        if not match:
            continue
        page, first = int(match.group(1)), None
        for j in range(i + 1, len(lines)):
            if heading.fullmatch(lines[j]):
                break
            if lines[j] == "### Original extracted text":
                first = j + 2
            elif first is not None and lines[j].startswith("### "):
                ranges[page] = (first, j)
                break
    blocks = source_map.get("source_blocks", [])
    selected = receipt.get("selected_pages")
    if (not isinstance(blocks, list) or any(not isinstance(b, dict) for b in blocks)
            or type(receipt.get("page_count")) is not int
            or not isinstance(selected, list) or not selected or len(set(selected)) != len(selected)
            or any(type(p) is not int or not 1 <= p <= receipt.get("page_count", 0) for p in selected)
            or sorted(ranges) != sorted(selected)
            or [b.get("pdf_page") for b in blocks] != sorted(selected)):
        raise ValueError("native reader page scope/map is invalid")
    for block in blocks:
        first, last = ranges[block["pdf_page"]]
        original = "\n".join(lines[first - 1:last]).strip()
        if hashlib.sha256(original.encode()).hexdigest() != block.get("extracted_text_sha256"):
            raise ValueError("native reader original-page text hash changed")
    images = []
    for image in receipt.get("page_images", []):
        binding = files.binding(image)
        if image.get("pdf_page") not in ranges or Path(binding["path"]).suffix.lower() != ".png":
            raise ValueError("native page image has an invalid page or format")
        images.append({**binding, "pdf_page": image["pdf_page"]})
    return {**reader, "receipt": {"path": receipt_rel, "sha256": receipt_hash},
            "source_map": mapping, "page_ranges": ranges, "page_images": images,
            "extracted_not_semantically_verified": True}


def _anchor(project, value, paper, files):
    if not isinstance(value, dict):
        raise ValueError("evidence anchor must be an object")
    binding = files.binding(value)
    permitted = {paper["source"]["path"], *[n["path"] for n in paper.get("notes", [])]}
    if paper.get("reader"):
        permitted.add(paper["reader"]["path"])
    if binding["path"] not in permitted:
        raise ValueError("anchor does not belong to this paper's source, reader or notes")
    first, last = value.get("start_line"), value.get("end_line")
    lines = files.text(binding["path"]).splitlines()
    if type(first) is not int or type(last) is not int or not 1 <= first <= last <= len(lines):
        raise ValueError("anchor needs an exact valid line range")
    citation = _text(value.get("quote"), "verbatim quote", 4000)
    snippet = "\n".join(lines[first - 1:last])
    if citation not in snippet:
        raise ValueError("evidence quote is absent from its specified lines")
    page = value.get("pdf_page")
    reader = paper.get("reader")
    if reader and binding["path"] == reader["path"]:
        ranges = reader["page_ranges"]
        bounds = ranges.get(page, ranges.get(str(page)))
        if type(page) is not int or bounds is None or not bounds[0] <= first <= last <= bounds[1]:
            raise ValueError("reader anchor must lie in the original text of its exact PDF page")
        locator = f"PDF page {page}; reader lines {first}-{last}"
    else:
        if page is not None:
            raise ValueError("pdf_page is valid only for controlled native readers")
        locator = f"lines {first}-{last}"
    return {**binding, "start_line": first, "end_line": last, "quote": citation,
            "pdf_page": page, "locator": locator,
            "snippet_sha256": hashlib.sha256(snippet.encode()).hexdigest(),
            "semantic_verification": False}


def validate_card(project: Path, paper: dict, card: dict) -> dict:
    """Validate root-generated reading cards; never certify their interpretations."""
    project = Path(project).resolve()
    files = _Files(project)
    prepared = {**paper, "source": source_binding(project, paper.get("source"), manifest=paper.get("manifest"), files=files),
                "notes": [files.binding(n) for n in paper.get("notes", [])]}
    prepared["reader"] = _reader(project, paper["reader"], prepared["source"], files) if paper.get("reader") else None
    return _card(project, prepared, card, files)


def validate_anchor(project: Path, paper: dict, anchor: dict) -> dict:
    """Validate one exact source anchor using the same rules as reading cards."""
    sample = {"schema_version": "1.0", "paper_id": paper["id"], "fields": {
        "findings": [{"text": "Anchor location check only", "kind": "human_interpretation",
                      "evidence": [anchor], "inference_boundary": "No semantic verification."}]}}
    return validate_card(project, paper, sample)["fields"]["findings"][0]["evidence"][0]


def _card(project, paper, card, files):
    if not isinstance(card, dict) or card.get("schema_version") != "1.0" or card.get("paper_id") != paper["id"]:
        raise ValueError("card schema or paper identity differs from this library item")
    incoming = card.get("fields", {})
    if not isinstance(incoming, dict) or set(incoming) - set(FIELDS):
        raise ValueError("card has unsupported field names")
    fields = {}
    for field in FIELDS:
        rows = incoming.get(field, [])
        if not isinstance(rows, list) or len(rows) > 50:
            raise ValueError("card fields must contain at most 50 located entries")
        fields[field] = []
        for row in rows:
            if not isinstance(row, dict) or row.get("kind") not in KINDS:
                raise ValueError("card entries must distinguish author claims from interpretations")
            text = _text(row.get("text"), "card statement")
            anchors = row.get("evidence")
            if not isinstance(anchors, list) or not 1 <= len(anchors) <= 20:
                raise ValueError("every card statement requires located source evidence")
            bound = [_anchor(project, anchor, paper, files) for anchor in anchors]
            if row["kind"] == "author_claim" and any(a["path"] not in
                    {paper["source"]["path"], (paper.get("reader") or {}).get("path")} for a in bound):
                raise ValueError("author claims must cite the source or controlled original-text reader")
            boundary = row.get("inference_boundary")
            if row["kind"] != "author_claim":
                boundary = _text(boundary, "interpretation inference boundary")
            fields[field].append({"text": text, "kind": row["kind"], "evidence": bound,
                                  "inference_boundary": boundary, "semantic_verification": False})
    return {"schema_version": "1.0", "paper_id": paper["id"], "fields": fields,
            "status": "evidence_located_pending_review" if any(fields.values()) else "pending_analysis",
            "unknown_fields": [f for f in FIELDS if not fields[f]],
            "full_text_review_scope": card.get("full_text_review_scope", "not_declared"),
            "human_full_text_reading_verified": False, "semantic_verification": False,
            "not_citation_evidence": True}


def _tokens(text):
    result = [w.casefold() for w in re.findall(r"[^\W_]{2,}", text, re.UNICODE)
              if w.casefold() not in STOPWORDS]
    for sequence in re.findall(r"[\u3400-\u9fff]+", text):
        result.extend(sequence[i:i + 2] for i in range(len(sequence) - 1))
    return result


def _chunks(paper, relative, text, digest):
    lines, first, buffer, size, page = text.splitlines(), 1, [], 0, None
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"## PDF page ([1-9][0-9]*)\s*", line)
        if len(line) > 12000:
            raise ValueError("full-text indexing needs lines at most 12000 characters; prepare a traceable extract")
        if buffer and (size + len(line) > 3000 or match):
            yield _chunk(paper, relative, digest, first, number - 1, buffer, page)
            first, buffer, size = number, [], 0
        if match:
            page = int(match.group(1))
        buffer.append(line)
        size += len(line) + 1
    if buffer:
        yield _chunk(paper, relative, digest, first, len(lines), buffer, page)


def _chunk(paper, relative, digest, first, last, lines, page):
    return {"paper_id": paper["id"], "topic_id": paper.get("topic_id"),
            "paper_ids": paper.get("paper_ids", []), "path": relative, "sha256": digest,
            "start_line": first, "end_line": last, "pdf_page": page,
            "locator": (f"PDF page {page}; " if page else "") + f"lines {first}-{last}",
            "text": "\n".join(lines), "retrieval_is_not_verified_evidence": True}


def _index(documents):
    postings, lengths = defaultdict(list), []
    for number, document in enumerate(documents):
        terms = Counter(_tokens(document["text"]))
        lengths.append(sum(terms.values()))
        for term, count in terms.items():
            postings[term].append([number, count])
    return {"schema_version": "1.0", "method": "persistent_fulltext_bm25_no_external_services",
            "documents": documents, "postings": dict(postings), "lengths": lengths,
            "average_length": sum(lengths) / len(lengths) if lengths else 0,
            "k1": 1.2, "b": 0.75, "retrieval_completeness_verified": False}


def _graph(project, rows, papers, files):
    edges, errors, seen = [], [], set()
    for row in rows:
        if not isinstance(row, dict):
            errors.append({"relationship_id": None, "error": "relationship must be an object"})
            continue
        try:
            identifier = _id(row.get("id"), "relationship ID")
            if identifier in seen:
                raise ValueError("duplicate relationship ID")
            seen.add(identifier)
            left, right = row.get("from"), row.get("to")
            if left == right or left not in papers or right not in papers:
                raise ValueError("relationship needs two distinct current library endpoints")
            if row.get("type") not in RELATIONS or row.get("kind") not in KINDS:
                raise ValueError("relationship needs a supported type and interpretation kind")
            rationale = _text(row.get("rationale"), "relationship rationale")
            if row["kind"] != "author_claim":
                _text(row.get("inference_boundary"), "relationship inference boundary")
            anchors, endpoints = [], set()
            for value in row.get("evidence", []):
                owner = value.get("paper_id")
                if owner not in {left, right}:
                    raise ValueError("relationship evidence must name one of its endpoints")
                if papers[owner].get("status") != "current":
                    raise ValueError("relationship endpoint has stale or invalid inputs")
                anchors.append({"paper_id": owner, **_anchor(project, value, papers[owner], files)})
                if row["kind"] == "author_claim" and anchors[-1]["path"] not in {
                        papers[owner]["source"]["path"], (papers[owner].get("reader") or {}).get("path")}:
                    raise ValueError("author-claim relationships must cite original source text")
                endpoints.add(owner)
            required = {left} if row["type"] == "cites" else {left, right}
            if not required.issubset(endpoints):
                raise ValueError("relationship requires source anchors for both endpoints (cites: citing endpoint)")
            edges.append({"id": identifier, "from": left, "to": right, "type": row["type"],
                          "kind": row["kind"], "rationale": rationale, "evidence": anchors,
                          "inference_boundary": row.get("inference_boundary"),
                          "status": "evidence_located_pending_review", "semantic_verification": False})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append({"relationship_id": row.get("id"), "error": str(exc)})
    return {"nodes": [{"id": p["id"], "title": p["title"], "topic_id": p.get("topic_id"),
                       "paper_ids": p.get("paper_ids", [])} for p in papers.values()],
            "edges": edges, "errors": errors, "cooccurrence_is_not_a_semantic_relationship": True,
            "semantic_verification": False}


def _discovered(project, files):
    result = []
    for root in DISCOVERY:
        directory = _path(project, root, exists=False, corpus=True)
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            relative = path.relative_to(project).as_posix()
            if relative.endswith((".reader.json", ".source-map.json")):
                continue
            _, digest = files.get(relative)
            result.append({"id": "discovered-" + hashlib.sha256(relative.encode()).hexdigest()[:16],
                           "title": path.stem, "source": {"path": relative, "sha256": digest},
                           "discovered_pending": True})
            if len(result) > 200:
                raise ValueError("more than 200 discovered files; provide an explicit library")
    return result


def _snapshot(project, output_dir=None, *, current=True):
    from scripts.output_provenance import current_origin
    relative, directory = _output(project, output_dir)
    manifest_path = _path(project, relative + "/manifest.json")
    origin = current_origin(project, manifest_path)
    if origin.get("status") != "tracked" or origin.get("family") == "anthropic":
        raise ValueError("workbench manifest provenance is stale or untracked; rebuild")
    manifest = read(manifest_path)
    if manifest.get("schema_version") != "1.0" or manifest.get("implementation_sha256") != sha(Path(__file__)):
        raise ValueError("workbench implementation changed; rebuild the snapshot")
    if manifest.get("output_dir") != relative:
        raise ValueError("workbench manifest output directory differs")
    for item in manifest.get("outputs", []):
        if not item["path"].startswith(relative + "/") or sha(_path(project, item["path"])) != item["sha256"]:
            raise ValueError("workbench output changed; rebuild the snapshot")
    if current:
        checked_files = _Files(project)
        for item in manifest.get("inputs", []):
            if item.get("kind") == "approved_binary_pdf":
                actual = source_binding(project, item, manifest=item.get("manifest"), files=checked_files)["sha256"]
            elif item.get("kind") == "approved_figure_asset":
                actual = _asset_binding(project, item, item["source"], item.get("manifest"), checked_files)["sha256"]
            else:
                actual = sha(_path(project, item["path"]))
            if actual != item["sha256"]:
                raise ValueError("workbench source changed; rebuild before reading old evidence")
    library = read(directory / "library.json")
    if current:
        for paper in library.get("papers", []):
            receipt = paper["reader"]["receipt"] if paper.get("reader") else None
            bindings = [receipt] if receipt else []
            if paper.get("card_input"):
                bindings.append(paper["card_input"])
            for binding in bindings:
                origin = current_origin(project, _path(project, binding["path"]))
                if origin.get("family") == "anthropic" or (binding == receipt and origin.get("status") != "tracked"):
                    raise ValueError("workbench input provenance changed; rebuild")
    return library, read(directory / "search-index.json"), manifest


def build(project: Path, config_path: str | None = None, output_dir: str | None = None) -> dict:
    project = Path(project).resolve()
    relative, directory = _output(project, output_dir)
    files = _Files(project)
    selected_config = config_path or CONFIG
    config_file = _path(project, selected_config, exists=False)
    if config_path is not None or config_file.is_file():
        raw, _ = files.get(selected_config, corpus=False)
        config = _json(raw)
        if not isinstance(config, dict) or config.get("schema_version") != "1.0":
            raise ValueError("unsupported literature workbench configuration")
    else:
        config = {"schema_version": "1.0"}
    scope = {"doctoral_question": config.get("doctoral_question"), "status": "proposed_requires_G1_review"}
    if scope["doctoral_question"] is not None:
        _text(scope["doctoral_question"], "doctoral question", 4000)
    core_path = _path(project, "program/core-thesis.json", exists=False)
    if core_path.is_file():
        core_data, core_hash = files.get("program/core-thesis.json", corpus=False)
        core = _json(core_data)
        actual = core.get("doctoral_question") if isinstance(core, dict) else None
        scope["core_thesis"] = {"path": "program/core-thesis.json", "sha256": core_hash}
        if isinstance(actual, str) and actual.strip().casefold() not in {"", "unassigned", "tbd", "pending", "not selected", "not yet selected"}:
            if scope["doctoral_question"] is not None and scope["doctoral_question"].strip() != actual.strip():
                raise ValueError("workbench scope differs from the doctoral question; G1/G2 human review is required")
            scope.update(doctoral_question=actual.strip(), status="current_question_bound_requires_scientific_review")
    entries = config.get("papers")
    if entries is None:
        entries = _discovered(project, files)
    if not isinstance(entries, list) or len(entries) > 200:
        raise ValueError("papers must be an array of at most 200 controlled sources")
    if directory.exists() and any(directory.iterdir()) and not (directory / "manifest.json").is_file():
        raise ValueError("refusing to populate a nonempty directory owned by another tool")
    try:
        old, old_index, _ = _snapshot(project, relative, current=False)
        previous = {p["id"]: p for p in old["papers"]}
    except (ValueError, OSError, KeyError, TypeError):
        previous, old_index = {}, {"documents": []}
    papers, documents, errors, reused = {}, [], [], []
    for spec in entries:
        if not isinstance(spec, dict):
            raise ValueError("each library paper must be an object")
        identifier = _id(spec.get("id"), "paper ID")
        if identifier in papers:
            raise ValueError("duplicate library paper ID")
        paper_ids, topic = spec.get("paper_ids", []), spec.get("topic_id")
        if (not isinstance(paper_ids, list) or len(set(paper_ids)) != len(paper_ids)
                or any(p not in {f"P{i:02d}" for i in range(1, 7)} for p in paper_ids)):
            raise ValueError("paper mappings must be distinct P01-P06 identifiers")
        if topic is not None:
            _id(topic, "topic ID")
        if paper_ids and topic is None:
            raise ValueError("P01-P06 mappings require an explicit topic ID")
        paper = {"id": identifier, "title": _text(spec.get("title", identifier), "paper title", 1000),
                 "topic_id": topic, "paper_ids": paper_ids, "status": "current",
                 "discovered_pending": bool(spec.get("discovered_pending")),
                 "semantic_verification": False, "human_full_text_reading_verified": False}
        paper["output_card"] = relative + "/cards/" + identifier + ".json"
        paper["source_scope"] = spec.get("source_scope", "scope_not_declared")
        papers[identifier] = paper
        try:
            paper["source"] = source_binding(project, spec.get("source"), manifest=spec.get("manifest"), files=files)
            if spec.get("manifest"):
                paper["manifest"] = spec["manifest"]
            if Path(paper["source"]["path"]).suffix.lower() not in {".pdf", ".md", ".txt", ".json"}:
                raise ValueError("source must be a PDF or UTF-8 markdown/text/JSON file")
            if spec.get("url"):
                paper["url"] = _https(spec["url"])
            notes = spec.get("notes", [])
            if not isinstance(notes, list) or len(notes) > 30:
                raise ValueError("notes must be an array of at most 30 bindings")
            paper["notes"] = [files.binding(n) for n in notes]
            if any(Path(n["path"]).suffix.lower() not in {".md", ".txt", ".json"} for n in paper["notes"]):
                raise ValueError("notes must be UTF-8 markdown/text/JSON files")
            paper["reader"] = _reader(project, spec["reader"], paper["source"], files) if spec.get("reader") else None
            paper["figure_manifest"] = (_figures(project, spec["figure_manifest"], paper["source"],
                paper.get("manifest"), files) if spec.get("figure_manifest") else None)
            if paper["source_scope"] == "metadata_only":
                paper["read_scope"] = "metadata_only_not_full_text"
            elif Path(paper["source"]["path"]).suffix.lower() == ".pdf" and not paper["reader"]:
                paper["read_scope"] = "pdf_pending_controlled_extraction"
            else:
                paper["read_scope"] = "available_text_not_human_reviewed"
            card_binding = files.binding(spec["card"]) if spec.get("card") else None
            paper["card_input"] = card_binding
            if card_binding:
                from scripts.output_provenance import current_origin
                if current_origin(project, _path(project, card_binding["path"])).get("family") == "anthropic":
                    raise ValueError("persistent scientific cards may not have a current Claude writer")
            # The dependency identities (including actual receipt/map/image hashes)
            # determine whether extraction and card validation can be reused.
            dependencies = [paper["source"], *paper["notes"]]
            if paper["reader"]:
                dependencies += [paper["reader"], paper["reader"]["receipt"], paper["reader"]["source_map"],
                                 *paper["reader"]["page_images"]]
            if card_binding:
                dependencies.append(card_binding)
            if paper["figure_manifest"]:
                dependencies += [paper["figure_manifest"], *paper["figure_manifest"]["assets"]]
            fingerprint = _digest({"spec": spec, "dependencies": dependencies,
                                   "scope": scope, "implementation": sha(Path(__file__))})
            paper["input_fingerprint"] = fingerprint
            prior = previous.get(identifier, {})
            if prior.get("input_fingerprint") == fingerprint and prior.get("status") == "current":
                paper["card"] = prior["card"]
                documents.extend(d for d in old_index["documents"] if d["paper_id"] == identifier)
                reused.append(identifier)
            else:
                incoming = _json(files.get(card_binding["path"])[0]) if card_binding else {
                    "schema_version": "1.0", "paper_id": identifier, "fields": {}}
                paper["card"] = _card(project, paper, incoming, files)
                sources = [paper["reader"] or paper["source"], *paper["notes"]]
                unique = {s["path"]: s for s in sources}
                for source in unique.values():
                    if Path(source["path"]).suffix.lower() in {".md", ".txt", ".json"}:
                        documents.extend(_chunks(paper, source["path"], files.text(source["path"]), source["sha256"]))
        except (ValueError, KeyError, TypeError, OSError) as exc:
            paper["status"] = "stale_or_invalid"
            paper["error"] = str(exc)
            paper["card"] = {"schema_version": "1.0", "paper_id": identifier,
                             "status": "blocked", "fields": {f: [] for f in FIELDS},
                             "semantic_verification": False}
            documents = [d for d in documents if d["paper_id"] != identifier]
            errors.append({"paper_id": identifier, "error": str(exc)})
    relationship_rows = config.get("relationships", [])
    if not isinstance(relationship_rows, list) or len(relationship_rows) > 1000:
        raise ValueError("relationships must be an array of at most 1000 evidence-bound edges")
    graph = _graph(project, relationship_rows, papers, files)
    errors += graph["errors"]
    if len(documents) > 30000:
        raise ValueError("full-text index exceeds 30000 blocks; narrow the library")
    index = _index(documents)
    library = {"schema_version": "1.0", "papers": list(papers.values()), "scope": scope,
               "status": "blocked" if errors else "pending_scientific_review",
               "errors": errors, "gate_approved": False, "scientific_completion_verified": False,
               "human_source_review_required": True, "model_call_made": False}
    overview = {"schema_version": "1.0", "kind": "source_bound_comparison_and_experiment_evidence_packet",
                "question": None, "rows": [{"paper_id": p["id"], "title": p["title"],
                "topic_id": p.get("topic_id"), "paper_ids": p["paper_ids"], "status": p["status"],
                "fields": p["card"]["fields"], "unknown_fields": [f for f in FIELDS if not p["card"]["fields"][f]],
                "semantic_verification": False} for p in papers.values()],
                "comparability_verified": False, "experiment_executed": False, "gate_approved": False}
    pending_itinerary = {"schema_version": "1.0", "question": None, "steps": [],
                         "status": "pending_explicit_reading_question", "model_call_made": False,
                         "scientific_completion_verified": False, "gate_approved": False}
    targets = []
    for name, value in (("library.json", library), ("search-index.json", index), ("graph.json", graph),
                        ("comparison.json", overview), ("itinerary.json", pending_itinerary)):
        target = _path(project, relative + "/" + name, exists=False)
        write(target, value)
        targets.append(target)
    for paper in papers.values():
        if paper.get("output_card"):
            target = _path(project, paper["output_card"], exists=False)
            write(target, paper["card"])
            targets.append(target)
            note = _path(project, relative + "/notes/" + paper["id"] + ".md", exists=False)
            note.parent.mkdir(parents=True, exist_ok=True)
            note.write_text(_markdown_note(paper), encoding="utf-8")
            targets.append(note)
    dashboard = _path(project, relative + "/index.html", exists=False)
    dashboard.write_text(_html(project, directory, library, graph), encoding="utf-8")
    targets.append(dashboard)
    # Reject a concurrent source edit before presenting the newly built snapshot.
    checked_files = _Files(project)
    for name, (_, digest) in files.cache.items():
        if name in files.approved_pdfs:
            current_hash = source_binding(project, files.approved_pdfs[name],
                manifest=files.approved_pdfs[name]["manifest"], files=checked_files)["sha256"]
        elif name in files.approved_assets:
            asset = files.approved_assets[name]
            current_hash = _asset_binding(project, asset, asset["source"], asset["manifest"], checked_files)["sha256"]
        else:
            current_hash = sha(_path(project, name))
        if current_hash != digest:
            raise ValueError("workbench input changed during build; snapshot not committed")
    manifest = {"schema_version": "1.0", "output_dir": relative,
                "implementation_sha256": sha(Path(__file__)),
                "inputs": [{"path": name, "sha256": value[1],
                    **({"kind": "approved_binary_pdf", "manifest": files.approved_pdfs[name]["manifest"]}
                       if name in files.approved_pdfs else
                       {"kind": "approved_figure_asset", "source": files.approved_assets[name]["source"],
                        "manifest": files.approved_assets[name]["manifest"]} if name in files.approved_assets else {})}
                        for name, value in sorted(files.cache.items())],
                "outputs": [{"path": p.relative_to(project).as_posix(), "sha256": sha(p)} for p in targets],
                "status": library["status"], "reused_papers": reused,
                "model_call_made": False, "scientific_completion_verified": False}
    manifest_path = _path(project, relative + "/manifest.json", exists=False)
    write(manifest_path, manifest)
    record(project, targets + [manifest_path], "scripts/literature_workbench.py")
    return {"output_dir": relative, "library": relative + "/library.json",
            "dashboard": relative + "/index.html", "manifest": relative + "/manifest.json",
            "status": library["status"], "paper_count": len(papers), "block_count": len(documents),
            "reused_papers": reused, "errors": errors, "model_call_made": False,
            "scientific_completion_verified": False}


def search(project: Path, query: str, *, topic_id=None, paper_id=None, limit=10, output_dir=None) -> dict:
    _text(query, "search query")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("search limit must be 1..100")
    if topic_id is not None:
        _id(topic_id, "topic ID")
    if paper_id is not None and paper_id not in {f"P{i:02d}" for i in range(1, 7)}:
        raise ValueError("paper_id filter must be P01-P06")
    if paper_id is not None and topic_id is None:
        raise ValueError("P01-P06 search requires its topic scope")
    _, index, manifest = _snapshot(Path(project), output_dir)
    docs, scores = index["documents"], defaultdict(float)
    for term in set(_tokens(query)):
        posting = index["postings"].get(term, [])
        inverse = math.log(1 + (len(docs) - len(posting) + 0.5) / (len(posting) + 0.5))
        for number, frequency in posting:
            document = docs[number]
            if topic_id is not None and document["topic_id"] != topic_id:
                continue
            if paper_id is not None and paper_id not in document["paper_ids"]:
                continue
            norm = 1 - index["b"] + index["b"] * index["lengths"][number] / (index["average_length"] or 1)
            scores[number] += inverse * frequency * (index["k1"] + 1) / (frequency + index["k1"] * norm)
    order = sorted(scores, key=lambda n: (-scores[n], docs[n]["paper_id"], docs[n]["path"], docs[n]["start_line"]))
    return {"query": query, "topic_id": topic_id, "paper_id": paper_id,
            "method": index["method"], "results": [{**docs[n], "score": scores[n]} for n in order[:limit]],
            "matched_blocks": len(scores), "snapshot_sha256": _digest(manifest),
            "retrieval_completeness_verified": False, "scientific_completion_verified": False}


def itinerary(project: Path, question: str, *, topic_id=None, paper_id=None, limit=8, output_dir=None) -> dict:
    hits = search(project, question, topic_id=topic_id, paper_id=paper_id, limit=100, output_dir=output_dir)
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("itinerary limit must be 1..30 papers")
    library, _, _ = _snapshot(Path(project), output_dir)
    papers = {p["id"]: p for p in library["papers"]}
    groups = {}
    for hit in hits["results"]:
        groups.setdefault(hit["paper_id"], []).append(hit)
    steps = []
    for identifier, evidence in groups.items():
        paper = papers[identifier]
        fields = paper["card"].get("fields", {})
        steps.append({"paper_id": identifier, "title": paper["title"],
                      "reason": "Lexical relevance; read counterevidence and limitations before interpreting agreement.",
                      "priority": "counterevidence" if fields.get("counterevidence") else "relevance",
                      "score": max(h["score"] for h in evidence), "start_here": evidence[:3],
                      "questions": [question, "Which baseline, split, metric and ablation actually distinguish the explanation?",
                                    "Which limitation or contrary result could defeat this interpretation?"],
                      "unknown_fields": paper["card"].get("unknown_fields", list(FIELDS)),
                      "reading_status": paper["card"]["status"], "semantic_verification": False})
    steps.sort(key=lambda s: (s["priority"] != "counterevidence", -s["score"], s["paper_id"]))
    result = {"schema_version": "1.0", "question": question, "steps": steps[:limit],
              "status": "reading_plan_only" if steps else "no_lexical_match_not_evidence_of_absence",
              "retrieval_completeness_verified": False, "gate_approved": False,
              "scientific_completion_verified": False, "model_call_made": False}
    _save_view(Path(project), output_dir, "itinerary.json", result)
    return result


def comparison_packet(project: Path, paper_ids: list[str], *, question="", output_dir=None) -> dict:
    if (not isinstance(paper_ids, list) or not 1 <= len(paper_ids) <= 30
            or len(set(paper_ids)) != len(paper_ids)):
        raise ValueError("comparison needs 1..30 distinct library paper IDs")
    if question:
        _text(question, "comparison question")
    library, _, manifest = _snapshot(Path(project), output_dir)
    papers = {p["id"]: p for p in library["papers"]}
    if any(identifier not in papers for identifier in paper_ids):
        raise ValueError("comparison references an unknown library paper")
    rows = []
    for identifier in paper_ids:
        paper = papers[identifier]
        if paper["status"] != "current":
            raise ValueError("comparison refuses stale or invalid paper evidence")
        fields = paper["card"]["fields"]
        rows.append({"paper_id": identifier, "title": paper["title"], "topic_id": paper.get("topic_id"),
                     "paper_ids": paper["paper_ids"], "fields": fields,
                     "unknown_fields": [f for f in FIELDS if not fields[f]],
                     "experiment_planning_gaps": [f for f in ("baseline", "splits", "metrics", "ablations") if not fields[f]],
                     "source": paper["source"], "semantic_verification": False})
    result = {"schema_version": "1.0", "kind": "source_bound_comparison_and_experiment_evidence_packet",
              "question": question, "rows": rows, "snapshot_sha256": _digest(manifest),
              "comparability_verified": False, "experiment_executed": False, "gate_approved": False,
              "scientific_completion_verified": False, "author_claims_are_not_independent_facts": True}
    _save_view(Path(project), output_dir, "comparison.json", result)
    return result


def _save_view(project, output_dir, name, value):
    relative, _ = _output(project, output_dir)
    target = _path(project, relative + "/" + name, exists=False)
    write(target, value)
    manifest_path = _path(project, relative + "/manifest.json")
    manifest = read(manifest_path)
    manifest["outputs"] = [i for i in manifest["outputs"] if i["path"] != relative + "/" + name]
    manifest["outputs"].append({"path": relative + "/" + name, "sha256": sha(target)})
    write(manifest_path, manifest)
    record(project, [target, manifest_path], "scripts/literature_workbench.py")


def _https(value):
    value = _text(value, "original URL", 4000)
    parts = urlsplit(value)
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value):
        raise ValueError("external original links must be credential-free HTTPS")
    return value


def _href(project, directory, relative, *, page=None, source=None, manifest=None, asset=None):
    if relative.startswith("data/raw/literature/figures/"):
        if asset is None or asset.get("path") != relative or Path(relative).stem != asset.get("sha256"):
            raise ValueError("raw figure links need their prevalidated content-addressed asset binding")
        target = path_in(project, relative)
    elif relative.startswith("data/raw/literature/"):
        if source is None or source.get("path") != relative:
            raise ValueError("original raw PDF link needs its authorized source binding")
        if not manifest or Path(relative).suffix.lower() != ".pdf":
            raise ValueError("original raw PDF link needs its reviewed manifest")
        # _html receives only the build's already-authorized paper bindings.
        # The commit check rehashes all originals/figures before manifest write.
        target = path_in(project, relative)
    else:
        target = _path(project, relative, corpus=True)
    link = quote(Path(os.path.relpath(target, directory)).as_posix(), safe="/")
    if page is not None:
        link += "#page=" + str(page)
    return html.escape(link, quote=True)


def _graph_svg(graph):
    esc = lambda value: html.escape(str(value), quote=True)
    nodes = graph["nodes"]
    if not nodes:
        return "<p>No library nodes yet.</p>"
    columns = min(4, len(nodes))
    height = math.ceil(len(nodes) / columns) * 130 + 70
    width = columns * 250
    positions = {node["id"]: (125 + i % columns * 250, 55 + i // columns * 130)
                 for i, node in enumerate(nodes)}
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Clickable evidence relationship graph" viewBox="0 0 {width} {height}">',
             '<defs><marker id="relation-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#64748b"/></marker></defs>']
    for edge in graph["edges"]:
        x1, y1 = positions[edge["from"]]
        x2, y2 = positions[edge["to"]]
        parts.append(f'<a href="#relation-{esc(edge["id"])}"><title>{esc(edge["rationale"])}</title>'
                     f'<path d="M{x1} {y1} L{x2} {y2}" stroke="#64748b" fill="none" marker-end="url(#relation-arrow)"/>'
                     f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2-5}" fill="#334155" font-size="11" text-anchor="middle">{esc(edge["type"])}</text></a>')
    for node in nodes:
        x, y = positions[node["id"]]
        title = node["title"]
        label = title[:25] + ("…" if len(title) > 25 else "")
        parts.append(f'<a href="#{esc(node["id"])}"><title>{esc(title)}</title>'
                     f'<rect x="{x-108}" y="{y-25}" width="216" height="54" rx="8" fill="#eef5fb" stroke="#36608a"/>'
                     f'<text x="{x}" y="{y-4}" fill="#17324d" font-size="13" text-anchor="middle">{esc(label)}</text>'
                     f'<text x="{x}" y="{y+15}" fill="#475569" font-size="11" text-anchor="middle">{esc(node["id"])}</text></a>')
    parts.append("</svg>")
    return "\n".join(parts)


def _markdown_note(paper):
    def plain(value):
        return html.escape(str(value), quote=True).replace("[", "\\[").replace("]", "\\]")
    lines = ["# " + plain(paper["title"]), "",
        "Source-bound reading note. Located evidence is not semantic verification.", "",
        "Reading scope: " + plain(paper.get("read_scope", "pending")), "",
        "Doctoral topic: " + plain(paper.get("topic_id") or "pending"), "",
        "Paper mappings: " + plain(", ".join(paper.get("paper_ids", [])) or "pending"), ""]
    for field in FIELDS:
        lines += ["## " + field.replace("_", " "), ""]
        rows = paper["card"]["fields"].get(field, [])
        if not rows:
            lines += ["Unknown / pending source review.", ""]
        for row in rows:
            lines += [plain(row["text"]), ""]
            for anchor in row["evidence"]:
                lines += ["Source: " + plain(anchor["path"]) + " · " + plain(anchor["locator"]), "",
                          "> " + plain(anchor["quote"]).replace("\n", "\n> "), ""]
    return "\n".join(lines) + "\n"

def _html(project, directory, library, graph):
    esc = lambda value: html.escape(str(value), quote=True)
    parts = ["<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">",
             "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; form-action 'none'\">",
             "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Reading workbench</title>",
             "<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17324d}article{border:1px solid #ccd5df;border-radius:10px;padding:1rem;margin:1rem 0}a{color:#125ba1}pre{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#475569}img{max-width:300px}table{border-collapse:collapse}td,th{padding:.5rem;border:1px solid #ccd5df;vertical-align:top}</style>",
             "<h1>Reading workbench</h1><p>Personal reading aid. Located text is not semantic verification, a human reading record, or gate approval.</p>",
             "<p>Status: " + esc(library["status"]) + "</p>"]
    parts.append("<h2>Source relationship map</h2>" + _graph_svg(graph))
    for paper in library["papers"]:
        parts.append('<article id="' + esc(paper["id"]) + '"><h2>' + esc(paper["title"]) + "</h2>")
        parts.append("<p>" + esc(paper.get("topic_id") or "Topic pending") + " · " +
                     esc(", ".join(paper["paper_ids"]) or "Paper mapping pending") + " · " + esc(paper["status"]) + "</p>")
        if paper.get("error"):
            parts.append("<p>Blocked: " + esc(paper["error"]) + "</p>")
        if paper.get("status") == "current":
            source = paper["source"]["path"]
            original_link = lambda page=None: _href(project, directory, source, page=page,
                source=paper["source"], manifest=paper.get("manifest"))
            parts.append('<a href="' + original_link() + '">Original source</a> ')
            if paper.get("url"):
                parts.append('<a rel="noopener noreferrer" href="' + esc(_https(paper["url"])) + '">Original HTTPS page</a> ')
            for note in paper.get("notes", []):
                parts.append('<a href="' + _href(project, directory, note["path"]) + '">Note: ' + esc(Path(note["path"]).name) + '</a> ')
            reader = paper.get("reader")
            if reader:
                parts.append('<p><a href="' + _href(project, directory, reader["path"]) + '">Page-anchored reader</a></p>')
                for image in reader["page_images"]:
                    parts.append('<a href="' + original_link(image["pdf_page"]) +
                                 '"><img loading="lazy" src="' + _href(project, directory, image["path"]) +
                                 '" alt="Original PDF page ' + esc(image["pdf_page"]) + '"></a>')
            figures = paper.get("figure_manifest")
            if figures:
                parts.append('<h3>Original figures and pages</h3><p><a href="' +
                    _href(project, directory, figures["path"]) + '">Extraction manifest</a>; labels remain source-bound and unverified.</p>')
                for asset in figures["assets"]:
                    asset_link = _href(project, directory, asset["path"], asset=asset)
                    for occurrence in asset["occurrences"]:
                        label = "PDF page " + str(occurrence["pdf_page"]) + " · " + occurrence["kind"]
                        if occurrence.get("figure_number"):
                            label += " · Figure " + occurrence["figure_number"]
                        if occurrence.get("table_number"):
                            label += " · Table " + occurrence["table_number"]
                        parts.append('<p><a href="' + original_link(occurrence["pdf_page"]) + '">' + esc(label) + '</a></p>')
                        if occurrence.get("caption"):
                            parts.append("<p>" + esc(occurrence["caption"]) + "</p>")
                        if asset["previewable"]:
                            parts.append('<a href="' + asset_link + '"><img loading="lazy" src="' + asset_link + '" alt="' + esc(label) + '"></a>')
                        parts.append('<p><a download href="' + asset_link + '">Original extracted asset</a> · SHA-256 ' + esc(asset["sha256"]) + '</p>')
            parts.append("<p>Reading card: " + esc(paper["card"]["status"]) + "</p>")
            parts.append('<p><a href="notes/' + quote(paper["id"], safe="") + '.md">Reading note</a></p>')
            for field in FIELDS:
                rows = paper["card"]["fields"][field]
                parts.append("<h3>" + esc(field.replace("_", " ")) + "</h3>")
                if not rows:
                    parts.append("<p>Unknown / pending source review.</p>")
                for row in rows:
                    parts.append("<p><strong>" + esc(row["kind"]) + ":</strong> " + esc(row["text"]) + "</p>")
                    if row.get("inference_boundary"):
                        parts.append("<p>Inference boundary: " + esc(row["inference_boundary"]) + "</p>")
                    for anchor in row["evidence"]:
                        link_source = source if anchor["pdf_page"] is not None else anchor["path"]
                        link = original_link(anchor["pdf_page"]) if anchor["pdf_page"] is not None else _href(project, directory, link_source)
                        parts.append('<p><a href="' + link + '">' +
                                     esc(anchor["path"] + " · " + anchor["locator"]) + "</a></p><pre>" + esc(anchor["quote"]) + "</pre>")
        parts.append("</article>")
    parts.append("<h2>Evidence-anchored relationships</h2><p>Typed relationships remain unverified interpretations.</p>")
    parts.append("<table><thead><tr><th>Relationship</th><th>Reason and scope</th><th>Located evidence</th></tr></thead><tbody>")
    for edge in graph["edges"]:
        parts.append('<tr id="relation-' + esc(edge["id"]) + '"><td><a href="#' + esc(edge["from"]) + '">' + esc(edge["from"]) + "</a> · " +
                     esc(edge["type"]) + ' · <a href="#' + esc(edge["to"]) + '">' + esc(edge["to"]) +
                     "</a></td><td>" + esc(edge["kind"]) + ": " + esc(edge["rationale"]) + "<p>" + esc(edge.get("inference_boundary") or "Semantic review pending") + "</p></td><td>")
        for anchor in edge["evidence"]:
            parts.append('<p><a href="' + _href(project, directory, anchor["path"]) + '">' +
                         esc(anchor["locator"]) + "</a> · " + esc(anchor["quote"]) + "</p>")
        parts.append("</td></tr>")
    parts.append("</tbody></table>")
    for error in library["errors"]:
        parts.append("<p>Blocked input: " + esc(json.dumps(error, ensure_ascii=False)) + "</p>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"
