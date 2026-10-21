#!/usr/bin/env python3
"""Cloud-only source acquisition and original PDF evidence assets.

No search, model, payment, scientific approval or reproduction permission is
implied by these operations. Page previews and decoded PDF image objects are
source evidence, never newly generated scientific figures.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qsl, unquote, urljoin, urlsplit, urlunsplit

try:
    from scripts.network_safety import fetch_bytes, validate_https_url
except ImportError:
    from network_safety import fetch_bytes, validate_https_url

MAX_BYTES = 64 * 1024 * 1024
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_PAGES = 100
MAX_PIXELS = 25_000_000
MAX_ASSETS = 500
MAX_ASSET_BYTES = 256 * 1024 * 1024
SOURCE_DIR = "evidence/literature/assets"
FIGURE_DIR = "evidence/literature/figures"
ARXIV_RE = re.compile(r"^(?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$", re.I)
SECRET_QUERY = {"api_key", "apikey", "access_token", "token", "key", "signature", "x-amz-signature"}


class LiteratureAssetError(RuntimeError):
    pass


def cloud() -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise LiteratureAssetError("literature acquisition and extraction require an authorized cloud executor")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def path_in(project: Path, relative: str, *, exists: bool = False) -> Path:
    """Reject absolute/Windows paths, traversal and every symlink component."""
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise LiteratureAssetError("asset paths must be nonempty POSIX project-relative paths")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or any(part in {"..", "."} for part in relative.split("/")):
        raise LiteratureAssetError("asset paths cannot contain absolute paths or traversal")
    root = Path(project).resolve()
    candidate = root.joinpath(*rel.parts)
    if candidate == root or root not in candidate.resolve().parents:
        raise LiteratureAssetError("asset path escapes project")
    for item in (candidate, *candidate.parents):
        if item == root:
            break
        if item.is_symlink():
            raise LiteratureAssetError("asset paths cannot contain symlinks")
    if exists and not candidate.is_file():
        raise LiteratureAssetError("source asset is not a regular project file")
    return candidate


def relative(project: Path, path: Path) -> str:
    return path.relative_to(Path(project).resolve()).as_posix()


def _output(project: Path, output_dir: str) -> Path:
    # An asset operation must never overwrite gates, budgets or manuscripts.
    if not output_dir.startswith("evidence/"):
        raise LiteratureAssetError("asset outputs must remain under evidence/")
    return path_in(project, output_dir)


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def _save(project: Path, directory: Path, value: dict) -> dict:
    data = _json_bytes(value)
    receipt = path_in(project, relative(project, directory / "receipts" / (digest(data) + ".json")))
    _write(receipt, data)
    _write(path_in(project, relative(project, directory / "latest.json")), data)
    from scripts.research_artifacts import record
    record(project, [receipt, directory / "latest.json"], "scripts/literature_assets.py")
    return {**value, "manifest_path": relative(project, receipt), "manifest_sha256": digest(data)}


def _arxiv_id(value: str) -> str | None:
    if value.lower().startswith("arxiv:"):
        value = value.split(":", 1)[1].strip()
    parsed = urlsplit(value)
    if parsed.scheme:
        if (parsed.hostname or "").lower() not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
            return None
        if parsed.username or parsed.password:
            return None
        candidate = re.sub(r"^/(?:abs|pdf|html|e-print)/", "", unquote(parsed.path))
        candidate = re.sub(r"\.pdf$", "", candidate, flags=re.I).strip("/")
    else:
        candidate = re.sub(r"^arxiv:\s*", "", value, flags=re.I)
    if not ARXIV_RE.fullmatch(candidate):
        return None
    if re.match(r"^\d{4}\.", candidate) and not 1 <= int(candidate[2:4]) <= 12:
        return None
    return candidate


def _url(value: str) -> tuple[str, str | None]:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise LiteratureAssetError("provide one public source URL or arXiv identifier")
    value = value.strip()
    arxiv = _arxiv_id(value)
    # An explicit arXiv PDF URL stays a direct PDF; raw identifiers become abs.
    if arxiv:
        prefix = "pdf" if "/pdf/" in urlsplit(value).path else "abs"
        value = f"https://arxiv.org/{prefix}/{arxiv}"
    value = validate_https_url(value)
    if any(key.lower() in SECRET_QUERY for key, _ in parse_qsl(urlsplit(value).query)):
        raise LiteratureAssetError("source URLs cannot contain access tokens or API credentials")
    return value, arxiv


def _rights() -> dict:
    return {"license": "unknown", "reuse_permission": "unknown", "permission_evidence_url": None,
            "human_review": "required", "public_access_is_not_reuse_permission": True}


class SourceHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.links: list[dict] = []
        self.text: list[str] = []
        self.title: list[str] = []
        self.anchor: dict | None = None
        self.in_title = False
        self.skipping = 0

    def handle_starttag(self, tag, attrs):
        attrs = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg"}:
            self.skipping += 1
        if self.skipping:
            return
        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key and attrs.get("content"):
                self.meta.setdefault(key, []).append(attrs["content"])
        if tag == "title":
            self.in_title = True
        if tag == "a":
            self.anchor = {"href": attrs.get("href", ""), "text": []}
        if tag in {"p", "div", "section", "article", "h1", "h2", "h3", "li", "br", "figcaption"}:
            self.text.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.skipping:
            self.skipping -= 1
            return
        if self.skipping:
            return
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.anchor is not None:
            self.anchor["text"] = " ".join(self.anchor["text"]).strip()
            self.links.append(self.anchor)
            self.anchor = None

    def handle_data(self, value):
        if self.skipping:
            return
        clean = " ".join(value.split())
        if clean:
            self.text.append(clean + " ")
            if self.in_title:
                self.title.append(clean)
            if self.anchor is not None:
                self.anchor["text"].append(clean)


def _html(payload: bytes, final_url: str) -> dict:
    if len(payload) > MAX_HTML_BYTES:
        raise LiteratureAssetError("HTML source exceeds 8 MiB")
    parser = SourceHTML()
    parser.feed(payload.decode("utf-8", errors="replace"))
    metadata = {key: values[0] for key, values in parser.meta.items() if values}
    candidates = list(parser.meta.get("citation_pdf_url", []))
    for link in parser.links:
        label = link["text"].strip().lower()
        if label in {"paper", "pdf", "full paper", "download paper", "download pdf", "view pdf"}:
            candidates.append(urljoin(final_url, link["href"]))
    # Do not acquire every reference PDF on a blog or bibliography page.
    links = []
    for candidate in candidates[:20]:
        try:
            public, _ = _url(urljoin(final_url, candidate))
            if public not in links:
                links.append(public)
        except (ValueError, RuntimeError):
            continue
    blog = metadata.get("og:type") == "article" or "/blog/" in urlsplit(final_url).path.lower()
    return {"title": metadata.get("citation_title") or metadata.get("og:title") or " ".join(parser.title),
            "authors": parser.meta.get("citation_author", []),
            "publication_date": metadata.get("citation_publication_date") or metadata.get("article:published_time"),
            "publication_date_basis": "publisher-supplied HTML metadata" if
                metadata.get("citation_publication_date") or metadata.get("article:published_time") else None,
            "source_type": "project_page" if links else "blog" if blog else "webpage",
            "pdf_candidates": links,
            "text": "".join(parser.text).strip()}


def _cached(project: Path, directory: Path) -> dict | None:
    latest = directory / "latest.json"
    if not latest.is_file() or latest.is_symlink():
        return None
    try:
        value = json.loads(latest.read_text(encoding="utf-8"))
        if value.get("status") != "acquired":
            return None
        for item in value.get("downloads", []):
            path = path_in(project, item["path"], exists=True)
            if digest(path.read_bytes()) != item["sha256"]:
                return None
            if item.get("text_path") and digest(path_in(project, item["text_path"], exists=True).read_bytes()) != item["text_sha256"]:
                return None
        data = _json_bytes(value)
        receipt = directory / "receipts" / (digest(data) + ".json")
        if not receipt.is_file() or receipt.read_bytes() != data:
            return None
        return {**value, "manifest_path": relative(project, receipt), "manifest_sha256": digest(data), "cache_hit": True}
    except (ValueError, OSError, KeyError, RuntimeError):
        return None


def resolve(project: Path, url: str, output_dir: str = SOURCE_DIR, *,
            max_bytes: int = MAX_BYTES, max_linked_pdfs: int = 2, refresh: bool = False) -> dict:
    """Acquire a supplied lead, never search or infer access/reuse rights.

    Uses the shared bounded HTTPS fetcher, including pre-follow redirect checks.
    Inaccessible sources return lead_only with a failure receipt. Hash-verified
    successful acquisitions are reused unless refresh=True.
    """
    cloud()
    project = Path(project).resolve()
    canonical, arxiv = _url(url)
    if not 1 <= max_bytes <= MAX_BYTES or not 0 <= max_linked_pdfs <= 3:
        raise LiteratureAssetError("invalid acquisition byte/link limits")
    source_id = digest(canonical.encode())[:24]
    directory = path_in(project, relative(project, _output(project, output_dir) / source_id))
    # Raw objects are content-addressed across distinct supplied source URLs.
    raw_directory = path_in(project, "data/raw/literature/sources")
    if not refresh:
        cached = _cached(project, directory)
        if cached and all(item.get("bytes", max_bytes + 1) <= max_bytes for item in cached.get("downloads", [])):
            return cached
    version = re.search(r"v(\d+)$", arxiv or "")
    value: dict = {"schema_version": 1, "original_input": url, "source_url": canonical,
        "final_url": None, "source_type": "arxiv" if arxiv else "unresolved", "acquired_at": utc_now(),
        "arxiv_id": arxiv, "version": version.group(0) if version else None,
        "version_basis": "explicit input identifier" if version else "unspecified; acquired bytes fixed by SHA256",
        "status": "lead_only", "permissions": _rights(), "downloads": [], "pdfs": [], "failures": [],
        "execution": {"mode": "cloud", "receipt_id": os.environ.get("GITHUB_RUN_ID") or
                      os.environ.get("DR_OS_CLOUD_EXECUTION_RECEIPT_ID") or "authorized-cloud"},
        "scientific_support_status": "unreviewed_source", "publication_date": None}

    def acquire(target: str) -> dict:
        # _url also rejects credential query strings before any fetch or receipt.
        target, _ = _url(target)
        payload, final, status, content_type = fetch_bytes(target, max_bytes=max_bytes, timeout=45,
            headers={"Accept": "application/pdf,text/html;q=0.9", "User-Agent": "DoctoralResearchOS/source-assets"})
        final, final_arxiv = _url(final)
        if status is not None and status != 200:
            raise LiteratureAssetError(f"source returned HTTP {status}")
        if not payload or len(payload) > max_bytes:
            raise LiteratureAssetError("source is empty or exceeds its byte limit")
        is_pdf = payload.startswith(b"%PDF-")
        if not is_pdf and (content_type or "").split(";", 1)[0].lower() == "application/pdf":
            raise LiteratureAssetError("PDF endpoint did not return PDF magic bytes")
        looks_html = re.search(br"<(?:!doctype\s+html|html|head|body|title|meta)\b", payload[:8192], re.I)
        if not is_pdf and not looks_html:
            raise LiteratureAssetError("source is neither a PDF nor identifiable HTML")
        info = None if is_pdf else _html(payload, final)
        extension = ".pdf" if is_pdf else ".html"
        sha = digest(payload)
        raw = path_in(project, relative(project, raw_directory / (sha + extension)))
        _write(raw, payload)
        record = {"source_url": target, "final_url": final, "path": relative(project, raw),
                  "sha256": sha, "bytes": len(payload), "http_status": status,
                  "content_type": content_type, "kind": "pdf" if is_pdf else "html", "acquired_at": utc_now()}
        if not any(old["sha256"] == sha and old["source_url"] == target for old in value["downloads"]):
            value["downloads"].append(record)
        if is_pdf:
            pdf_version = re.search(r"v(\d+)$", final_arxiv or "")
            record = {**record, "source_pdf_sha256": sha, "version": value["version"],
                      "permissions": _rights()}
            if pdf_version:
                record["version"] = pdf_version.group(0)
            if not any(old["sha256"] == sha for old in value["pdfs"]):
                value["pdfs"].append(record)
        else:
            text = path_in(project, relative(project, raw_directory / (sha + ".txt")))
            _write(text, info.pop("text").encode())
            record["text_path"] = relative(project, text)
            record["text_sha256"] = digest(text.read_bytes())
            record["page_metadata"] = info
        return record

    try:
        main = acquire(canonical)
        value["final_url"] = main["final_url"]
        if main["kind"] == "pdf":
            value["source_type"] = "arxiv" if arxiv else "pdf_url"
        else:
            info = main["page_metadata"]
            value.update({key: info[key] for key in ("title", "authors", "publication_date", "publication_date_basis")})
            value["source_type"] = "arxiv" if arxiv else info["source_type"]
            leads = info["pdf_candidates"]
            if arxiv and not leads:
                leads = [f"https://arxiv.org/pdf/{arxiv}"]
            for candidate in leads[:max_linked_pdfs]:
                try:
                    linked = acquire(candidate)
                    if linked["kind"] != "pdf":
                        value["failures"].append({"source_url": candidate, "reason": "linked paper did not return a PDF"})
                except (ValueError, OSError, RuntimeError) as exc:
                    value["failures"].append({"source_url": candidate, "reason": str(exc)[:1000]})
        value["status"] = "acquired"
        value["pdf_status"] = "acquired" if value["pdfs"] else "not_acquired"
        if value["pdfs"]:
            value["local_pdf"] = value["pdfs"][0]["path"]
            value["source_pdf_sha256"] = value["pdfs"][0]["sha256"]
            if value["pdfs"][0].get("version"):
                value["version"] = value["pdfs"][0]["version"]
                value["version_basis"] = "explicit acquired PDF URL"
    except (ValueError, OSError, RuntimeError) as exc:
        value["failures"].append({"source_url": canonical, "reason": str(exc)[:1000]})
        value["pdf_status"] = "not_acquired"
    return _save(project, directory, value)


def _normalize_text(value: str) -> str:
    return " ".join(str(value).split()).casefold()


def _label(request: dict, page_text: str) -> dict:
    """Match supplied labels to actual page text; never derive from object order."""
    result = {"figure_number": None, "table_number": None, "caption": None,
              "label_verification": {"scope": "same PDF page text", "status": "unverified",
                                     "spatial_association": "caller-supplied crop; not automatically verified"}}
    normalized = _normalize_text(page_text)
    matched = False
    for field, keyword in (("figure_number", r"(?:figure|fig\.?)"), ("table_number", "table")):
        number = request.get(field)
        if number is not None:
            number = str(number).strip()
            if len(number) <= 24 and re.search(r"\b" + keyword + r"\s*" + re.escape(number) + r"(?!\w|\.\d)",
                                               page_text, re.I):
                result[field] = number
                matched = True
    caption = request.get("caption")
    if isinstance(caption, str) and 3 <= len(caption) <= 10000 and _normalize_text(caption) in normalized:
        result["caption"] = caption
        matched = True
    if matched:
        result["label_verification"]["status"] = "page_text_match"
    return result


def _page_dimensions(page) -> tuple[float, float]:
    width, height = float(page.cropbox.width), float(page.cropbox.height)
    rotation = int(page.rotation or 0) % 360
    if rotation in {90, 270}:
        width, height = height, width
    if not all(math.isfinite(v) and 0 < v < 100000 for v in (width, height)):
        raise LiteratureAssetError("invalid or excessive PDF page dimensions")
    return width, height


def _image_preflight(page, seen=None, depth=0) -> None:
    """Check declared raster sizes before pypdf decodes XObjects."""
    if depth > 12:
        raise LiteratureAssetError("PDF image resource nesting exceeds limit")
    seen = set() if seen is None else seen
    resources = page.get("/Resources", {})
    if hasattr(resources, "get_object"):
        resources = resources.get_object()
    xobjects = resources.get("/XObject", {})
    if hasattr(xobjects, "get_object"):
        xobjects = xobjects.get_object()
    for ref in xobjects.values():
        obj = ref.get_object()
        identity = id(obj)
        if identity in seen:
            continue
        seen.add(identity)
        if obj.get("/Subtype") == "/Image":
            width, height = int(obj.get("/Width", 0)), int(obj.get("/Height", 0))
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise LiteratureAssetError("PDF raster image dimensions exceed limit")
        elif obj.get("/Subtype") == "/Form":
            _image_preflight(obj, seen, depth + 1)


def extract(project: Path, pdf_relative: str, output_dir: str = FIGURE_DIR, *,
            figures: list[dict] | None = None, source: dict | None = None,
            dpi: int = 120, max_pages: int = MAX_PAGES) -> dict:
    """Extract decoded original image objects plus explicitly labeled page/crops.

    figures=[{pdf_page: 1, bbox: [x0,y0,x1,y1], figure_number: "1",
              caption: "Figure 1. Actual caption"}].
    bbox uses displayed CropBox PDF points, top-left origin, after page rotation.
    All pages get a faithful Poppler preview so vector figures/tables are retained.
    These previews remain page_render evidence, not identified figures.
    """
    cloud()
    from PIL import Image
    from pypdf import PdfReader

    project = Path(project).resolve()
    pdf = path_in(project, pdf_relative, exists=True)
    if pdf.stat().st_size > MAX_BYTES or not pdf.read_bytes()[:5] == b"%PDF-":
        raise LiteratureAssetError("source must be a PDF no larger than 64 MiB")
    if not isinstance(dpi, int) or not 36 <= dpi <= 200 or not 1 <= max_pages <= MAX_PAGES:
        raise LiteratureAssetError("invalid PDF rendering limits")
    renderer = shutil.which("pdftoppm")
    if renderer is None:
        raise LiteratureAssetError("cloud PDF extraction requires poppler-utils (pdftoppm)")
    source_sha = digest(pdf.read_bytes())
    if source and source.get("source_pdf_sha256") not in {None, source_sha}:
        raise LiteratureAssetError("source receipt PDF hash does not match current PDF")
    pdf_source = next((item for item in (source or {}).get("pdfs", [])
                       if item.get("sha256") == source_sha), {})
    reader = PdfReader(str(pdf), strict=False)
    if reader.is_encrypted:
        raise LiteratureAssetError("encrypted PDFs are not opened or bypassed")
    if not 1 <= len(reader.pages) <= max_pages:
        raise LiteratureAssetError("PDF page count exceeds extraction limit")
    requests = figures or []
    if not isinstance(requests, list) or len(requests) > 100:
        raise LiteratureAssetError("figure requests must be a list of at most 100 crops")
    grouped: dict[int, list[dict]] = {}
    for item in requests:
        if not isinstance(item, dict) or isinstance(item.get("pdf_page"), bool) or not isinstance(item.get("pdf_page"), int):
            raise LiteratureAssetError("each figure request needs a one-based integer pdf_page")
        page_no = item["pdf_page"]
        if not 1 <= page_no <= len(reader.pages):
            raise LiteratureAssetError("figure request page is outside the PDF")
        bbox = item.get("bbox")
        width, height = _page_dimensions(reader.pages[page_no - 1])
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4 or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in bbox
        ):
            raise LiteratureAssetError("figure crops require four finite PDF-point coordinates")
        x0, y0, x1, y1 = bbox
        if not 0 <= x0 < x1 <= width or not 0 <= y0 < y1 <= height:
            raise LiteratureAssetError("figure crop is outside displayed PDF CropBox")
        grouped.setdefault(page_no, []).append(item)
    spec = digest(_json_bytes({"pdf": source_sha, "dpi": dpi, "figures": requests, "version": 1}))[:20]
    directory = path_in(project, relative(project, _output(project, output_dir) / source_sha[:24] / spec))
    object_directory = path_in(project, "data/raw/literature/figures/" + source_sha[:24] + "/" + spec)
    manifest: dict = {"schema_version": 1, "status": "complete", "source_pdf": pdf_relative,
        "source_pdf_sha256": source_sha, "source_url": (source or {}).get("source_url"),
        "final_url": (source or {}).get("final_url"), "version": (source or {}).get("version"),
        "source_pdf_url": pdf_source.get("final_url") or (source or {}).get("final_url"),
        "source_receipt_path": (source or {}).get("manifest_path"),
        "source_receipt_sha256": (source or {}).get("manifest_sha256"),
        "permissions": (source or {}).get("permissions") or _rights(), "created_at": utc_now(),
        "pdf_page_count": len(reader.pages), "assets": [], "warnings": [], "rejected_labels": [],
        "coordinate_system": "displayed CropBox points; top-left origin; after page rotation",
        "storage_policy": "original source assets quarantined under data/raw/literature; no redistribution permission inferred",
        "scientific_support_status": "source_assets_only; human evidence/reuse review required",
        "execution": {"mode": "cloud", "receipt_id": os.environ.get("GITHUB_RUN_ID") or
                      os.environ.get("DR_OS_CLOUD_EXECUTION_RECEIPT_ID") or "authorized-cloud"},
        "tools": {"pypdf": __import__("pypdf").__version__, "Pillow": Image.__version__, "renderer": "pdftoppm"}}
    asset_by_sha: dict[str, dict] = {}
    total_bytes = 0

    def save_asset(data: bytes, extension: str, occurrence: dict) -> None:
        nonlocal total_bytes
        sha = digest(data)
        if sha in asset_by_sha:
            asset_by_sha[sha]["occurrences"].append(occurrence)
            return
        if len(asset_by_sha) >= MAX_ASSETS or total_bytes + len(data) > MAX_ASSET_BYTES:
            raise LiteratureAssetError("PDF extracted asset count/byte limit exceeded")
        target = object_directory / (sha + extension)
        _write(path_in(project, relative(project, target)), data)
        record = {"asset_id": "sha256:" + sha, "path": relative(project, target), "sha256": sha,
                  "bytes": len(data), "source_pdf_sha256": source_sha, "version": manifest["version"],
                  "permissions": manifest["permissions"], **occurrence, "occurrences": [occurrence]}
        asset_by_sha[sha] = record
        manifest["assets"].append(record)
        total_bytes += len(data)

    for page_no, page in enumerate(reader.pages, 1):
        width, height = _page_dimensions(page)
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            page_text = ""
            manifest["warnings"].append({"pdf_page": page_no, "method": "text", "reason": str(exc)[:300]})
        neutral = {"pdf_page": page_no, "figure_number": None, "table_number": None, "caption": None}
        try:
            _image_preflight(page)
            for index, image in enumerate(page.images):
                data = image.data
                if len(data) > MAX_BYTES:
                    raise LiteratureAssetError("decoded PDF image exceeds byte limit")
                with Image.open(io.BytesIO(data)) as probe:
                    if probe.width * probe.height > MAX_PIXELS:
                        raise LiteratureAssetError("decoded PDF image exceeds pixel limit")
                ext = Path(image.name).suffix.lower()
                if ext not in {".png", ".jpg", ".jpeg", ".jp2", ".tif", ".tiff", ".bmp"}:
                    ext = ".bin"
                save_asset(data, ext, {**neutral, "kind": "image_object", "method": "pypdf-decoded-image-object",
                    "original_filename": image.name, "object_index": index, "bbox": None,
                    "representation": "original PDF raster image object decoded; pypdf may re-encode"})
        except Exception as exc:
            manifest["warnings"].append({"pdf_page": page_no, "method": "image_objects", "reason": str(exc)[:300]})
        render_dpi = min(dpi, int(72 * math.sqrt(MAX_PIXELS / (width * height))))
        if render_dpi < 12:
            raise LiteratureAssetError("PDF dimensions cannot be rendered within pixel limit")
        with tempfile.TemporaryDirectory(prefix="source-pdf-", dir=directory if directory.exists() else None) as temp:
            prefix = Path(temp) / "page"
            command = [renderer, "-f", str(page_no), "-l", str(page_no), "-singlefile", "-cropbox",
                       "-r", str(render_dpi), "-png", str(pdf), str(prefix)]
            try:
                subprocess.run(command, check=True, timeout=45, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    env={key: val for key, val in os.environ.items() if key in {"PATH", "LANG", "LC_ALL", "TZ"}})
            except (subprocess.SubprocessError, OSError) as exc:
                raise LiteratureAssetError(f"PDF page {page_no} renderer failed: {type(exc).__name__}") from exc
            rendered = prefix.with_suffix(".png")
            if not rendered.is_file() or rendered.stat().st_size > MAX_BYTES:
                raise LiteratureAssetError("PDF page render missing or exceeds byte limit")
            with Image.open(rendered) as preview:
                if preview.width * preview.height > MAX_PIXELS:
                    raise LiteratureAssetError("PDF page render exceeds pixel limit")
                save_asset(rendered.read_bytes(), ".png", {**neutral, "kind": "page_render",
                    "method": "pdftoppm-page-render", "bbox": [0, 0, width, height], "dpi": render_dpi})
                for item in grouped.get(page_no, []):
                    bbox = item["bbox"]
                    labels = _label(item, page_text)
                    for key in ("figure_number", "table_number", "caption"):
                        if item.get(key) is not None and labels[key] is None:
                            manifest["rejected_labels"].append({"pdf_page": page_no, "field": key,
                                "requested": item[key], "reason": "not matched in actual page text"})
                    pixel_box = (math.floor(bbox[0] / width * preview.width),
                                 math.floor(bbox[1] / height * preview.height),
                                 math.ceil(bbox[2] / width * preview.width),
                                 math.ceil(bbox[3] / height * preview.height))
                    with preview.crop(pixel_box) as crop:
                        buffer = io.BytesIO()
                        crop.save(buffer, format="PNG")
                        save_asset(buffer.getvalue(), ".png", {**neutral, **labels, "kind": "source_crop",
                            "method": "pdftoppm-page-crop", "bbox": list(bbox), "dpi": render_dpi,
                            "derived_from_page_sha256": digest(rendered.read_bytes())})
    if digest(pdf.read_bytes()) != source_sha:
        raise LiteratureAssetError("source PDF changed during extraction")
    manifest["total_asset_bytes"] = total_bytes
    return _save(project, directory, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    acquire = sub.add_parser("resolve")
    acquire.add_argument("--project", type=Path, required=True)
    acquire.add_argument("--url", required=True)
    acquire.add_argument("--output-dir", default=SOURCE_DIR)
    acquire.add_argument("--refresh", action="store_true")
    assets = sub.add_parser("extract")
    assets.add_argument("--project", type=Path, required=True)
    assets.add_argument("--pdf", required=True)
    assets.add_argument("--output-dir", default=FIGURE_DIR)
    assets.add_argument("--figures", help="project-relative JSON array of caller-selected page crops")
    assets.add_argument("--source-receipt", help="project-relative acquired source receipt")
    args = parser.parse_args()
    if args.operation == "resolve":
        value = resolve(args.project, args.url, args.output_dir, refresh=args.refresh)
    else:
        figures = json.loads(path_in(args.project, args.figures, exists=True).read_text()) if args.figures else None
        source = json.loads(path_in(args.project, args.source_receipt, exists=True).read_text()) if args.source_receipt else None
        value = extract(args.project, args.pdf, args.output_dir, figures=figures, source=source)
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
