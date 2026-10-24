"""Pinned metadata-only figure reference search; no paid models or image copies.

The bilingual concept vocabulary is adapted from the MIT-licensed Top-Conf
Figure Gallery retrieval ideas. This module reports lexical/concept retrieval
truthfully; actual CPU image embedding search lives in figure_gallery_semantic.
Retrieval scores, venue badges and layout references never verify science.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from scripts.research_artifacts import path_in, record, sha, write

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "integrations/topconf-figure-gallery.lock.json"
INDEX = "literature/figure-gallery/index.json"
RECEIPT = "literature/figure-gallery/index.receipt.json"
MAX_BYTES = 3_000_000
MAX_ROWS = 10_000
MAX_TOP_K = 20
VENUES = {"iclr", "icml", "neurips", "cvpr", "acl", "aaai"}
PATTERNS = {"conceptual", "architecture", "teaser", "pipeline", "framework",
            "results", "taxonomy", "comparison"}
TIERS = {"best_paper", "oral", "spotlight", "unknown"}
HOSTS = {"ojs.aaai.org", "aclanthology.org", "openaccess.thecvf.com",
         "openreview.net", "proceedings.mlr.press", "proceedings.neurips.cc",
         "arxiv.org", "raw.githubusercontent.com"}
HASH = re.compile(r"[0-9a-f]{64}\Z")
ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\Z")
STOP = set("a an the of for to in on and or with by as at from is are be this that "
           "we our it its into using use paper figure diagram draw create generate "
           "please scientific research show showing".split())
# These labels describe metadata matches, not confirmed visual understanding.
CONCEPTS = {
    "multimodal": ("multimodal", "multi-modal", "多模态"),
    "vision_language": ("vision-language", "image-text", "图文", "视觉语言"),
    "diffusion": ("diffusion", "denoising", "扩散", "去噪"),
    "image_generation": ("image generation", "image synthesis", "text-to-image", "图像生成", "文生图"),
    "graph_neural_network": ("graph neural", "gnn", "图神经网络"),
    "knowledge_graph": ("knowledge graph", "知识图谱"),
    "reinforcement_learning": ("reinforcement learning", "强化学习"),
    "segmentation": ("segmentation", "分割"),
    "object_detection": ("object detection", "目标检测"),
    "depth_estimation": ("depth estimation", "深度估计"),
    "three_dimensional": ("3d", "three-dimensional", "三维"),
    "point_cloud": ("point cloud", "点云"),
    "robotics": ("robot", "robotic", "robotics", "机器人"),
    "recommendation": ("recommendation", "recommender", "推荐系统"),
    "time_series": ("time series", "time-series", "时间序列"),
    "retrieval_augmented": ("retrieval augmented", "retrieval-augmented", "rag", "检索增强"),
    "language_model": ("large language", "language model", "llm", "llms", "大语言模型", "语言模型"),
    "contrastive_learning": ("contrastive", "对比学习"),
    "self_supervised": ("self-supervised", "自监督"),
    "causal": ("causal", "causality", "因果"),
    "federated": ("federated", "联邦"),
    "distillation": ("distillation", "蒸馏"),
    "attention": ("attention", "注意力"),
    "optimization": ("optimization", "optimisation", "优化"),
    "interpretability": ("interpretability", "explainability", "可解释性"),
    "computer_vision": ("computer vision", "image", "visual", "计算机视觉"),
    "natural_language": ("natural language", "nlp", "自然语言处理"),
}
STRUCTURES = {
    "architecture": ("architecture", "网络结构", "架构图"),
    "pipeline": ("pipeline", "流程图", "流水线"),
    "framework": ("framework", "框架图", "框架"),
    "comparison": ("comparison", "对比图", "对照图"),
    "conceptual": ("conceptual", "机制图", "概念图"),
    "taxonomy": ("taxonomy", "分类图"),
    "teaser": ("teaser", "主视觉图"),
    "results": ("results", "结果图"),
}
BOUNDARY = ("Reference discovery only. Metadata and retrieval scores are not "
            "evidence of scientific quality, image inspection, reuse permission, "
            "novelty or support for our claims. Inspect the original paper and "
            "create an original figure from our own verified method/data.")


def _cloud():
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("figure gallery execution requires the cloud runner")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _json(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError("duplicate JSON field in figure gallery metadata")
            obj[key] = value
        return obj
    def constant(_):
        raise ValueError("nonfinite gallery metadata")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _lock():
    value = _json(LOCK.read_bytes())
    if (value.get("repository") != "qwdwqfwq/topconf-paper-figure-gallery"
            or not re.fullmatch(r"[0-9a-f]{40}", value.get("commit", ""))
            or value.get("metadata", {}).get("path") != "data/figures.json"
            or not HASH.fullmatch(value.get("metadata", {}).get("sha256", ""))):
        raise ValueError("invalid pinned figure gallery lock")
    return value


def _url(value):
    if not isinstance(value, str) or len(value) > 2500 or re.search(r"[\s\x00-\x1f\x7f]", value):
        raise ValueError("invalid source URL")
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username
            or parsed.password or parsed.port not in {None, 443}):
        raise ValueError("source link must be an approved public HTTPS paper host")
    return value


def _matches(text, phrase):
    if re.search(r"[\u3400-\u9fff]", phrase):
        return phrase in text
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase).replace(r"\ ", r"[\s-]+")
                     + r"(?![a-z0-9])", text) is not None


def concepts(text, vocabulary=None):
    text = text.casefold()
    return [key for key, phrases in (CONCEPTS if vocabulary is None else vocabulary).items()
            if any(_matches(text, phrase) for phrase in phrases)]


def query_terms(text):
    words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.casefold())
    found = concepts(text)
    # The same synthetic concept token is present in Chinese and English.
    return list(dict.fromkeys([word for word in words if word not in STOP]
                              + ["concept:" + key for key in found]))


def normalize_figures(raw, lock=None):
    lock = _lock() if lock is None else lock
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_ROWS:
        raise ValueError("gallery metadata must be a bounded nonempty list")
    figures, seen = [], set()
    for row in raw:
        if not isinstance(row, dict) or not ID.fullmatch(str(row.get("id", ""))):
            raise ValueError("gallery record needs a safe unique ID")
        identity = row["id"]
        if identity in seen:
            raise ValueError("duplicate gallery figure ID")
        seen.add(identity)
        title, authors = row.get("title"), row.get("authors")
        if not isinstance(title, str) or not title.strip() or len(title) > 2500:
            raise ValueError("gallery title is invalid")
        if (not isinstance(authors, list) or not 1 <= len(authors) <= 300
                or any(not isinstance(a, str) or not a.strip() or len(a) > 250 for a in authors)):
            raise ValueError("gallery authors are invalid")
        if (row.get("venue") not in VENUES or type(row.get("year")) is not int
                or not 2023 <= row["year"] <= 2026 or row.get("pattern") not in PATTERNS):
            raise ValueError("gallery venue/year/pattern is outside the pinned collection")
        image = row.get("image", "")
        if not re.fullmatch(r"images/[a-z]+/final/[A-Za-z0-9_.-]+\.(?:jpg|jpeg|png)", image):
            raise ValueError("gallery image path is invalid")
        tier = "best_paper" if row.get("award") == "best" else row.get("tier", "unknown")
        if tier not in TIERS:
            raise ValueError("unknown gallery tier value")
        figure_url = "https://raw.githubusercontent.com/" + lock["repository"] + "/" + lock["commit"] + "/" + image
        figures.append({"id": identity, "title": title, "authors": authors,
                        "venue": row["venue"], "year": row["year"], "tier": tier,
                        "award": row.get("award"), "pattern": row["pattern"],
                        "topics": concepts(title), "topics_basis": "title_bilingual_concept_inference",
                        "paper_url": _url(row.get("paper")), "pdf_url": _url(row.get("pdf_source")),
                        "figure_url": figure_url, "metadata_sha256": digest(row),
                        "source_record_sha256": digest(row), "image_downloaded": False,
                        "image_inspected": False,
                        "license": {"code_license": "MIT", "image_license": "unknown",
                                    "reuse_authorized": False, "authority": "original_paper_or_publisher",
                                    "policy_url": "https://github.com/" + lock["repository"] + "/blob/" + lock["commit"] + "/IMAGES_POLICY.md"}})
    return figures


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("pinned metadata redirects are forbidden")


def _download(url):
    request = Request(url, headers={"User-Agent": "lunwen-figure-gallery/1.0", "Accept": "application/json"})
    with build_opener(_NoRedirect).open(request, timeout=30) as response:
        if response.geturl() != url:
            raise ValueError("pinned metadata URL changed")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("gallery metadata exceeds byte ceiling")
    return data


def sync(project: Path):
    """Fetch exact pinned JSON metadata, never the original images or a model."""
    _cloud()
    lock = _lock()
    url = "https://raw.githubusercontent.com/" + lock["repository"] + "/" + lock["commit"] + "/" + lock["metadata"]["path"]
    target = path_in(project, INDEX, exists=False)
    if target.is_file() and sha(target) == lock["metadata"]["sha256"]:
        data = target.read_bytes()
    else:
        data = _download(url)
    if (len(data) != lock["metadata"]["size_bytes"]
            or hashlib.sha256(data).hexdigest() != lock["metadata"]["sha256"]):
        raise ValueError("pinned gallery metadata SHA-256/size mismatch")
    figures = normalize_figures(_json(data), lock)
    if len(figures) != lock["metadata"]["record_count"]:
        raise ValueError("pinned gallery record count differs")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False) as handle:
        handle.write(data)
        temporary = handle.name
    os.replace(temporary, target)
    result = {"schema_version": "1.0", "source": {"repository": lock["repository"],
              "commit": lock["commit"], "url": url, "metadata_sha256": lock["metadata"]["sha256"],
              "upstream_git_blob_sha": lock["metadata"]["git_blob_sha"], "lock_sha256": sha(LOCK),
              "verified_access_date": lock["verified_access_date"]},
              "snapshot_binding": {"path": INDEX, "sha256": sha(target)},
              "record_count": len(figures), "metadata_only": True,
              "paid_api_calls": 0, "images_downloaded": 0, "boundary": BOUNDARY}
    receipt = path_in(project, RECEIPT, exists=False)
    write(receipt, result)
    record(project, [target, receipt], "scripts/figure_gallery.py")
    return result


def load_index(project: Path):
    """Revalidate exact downloaded bytes and normalize at every consumption."""
    lock = _lock()
    target, receipt = path_in(project, INDEX), path_in(project, RECEIPT)
    if target.stat().st_size > MAX_BYTES or sha(target) != lock["metadata"]["sha256"]:
        raise ValueError("gallery snapshot is stale or modified; sync the pinned source")
    result = _json(receipt.read_bytes())
    expected_url = "https://raw.githubusercontent.com/" + lock["repository"] + "/" + lock["commit"] + "/" + lock["metadata"]["path"]
    expected_source = {"repository": lock["repository"], "commit": lock["commit"], "url": expected_url,
                       "metadata_sha256": lock["metadata"]["sha256"],
                       "upstream_git_blob_sha": lock["metadata"]["git_blob_sha"], "lock_sha256": sha(LOCK),
                       "verified_access_date": lock["verified_access_date"]}
    if (result.get("source") != expected_source or result.get("snapshot_binding") != {"path": INDEX, "sha256": sha(target)}
            or result.get("metadata_only") is not True or result.get("record_count") != lock["metadata"]["record_count"]):
        raise ValueError("gallery source receipt differs from the current exact pinned snapshot")
    figures = normalize_figures(_json(target.read_bytes()), lock)
    if len(figures) != lock["metadata"]["record_count"]:
        raise ValueError("gallery record count differs")
    return {"source": expected_source, "snapshot_binding": result["snapshot_binding"], "figures": figures}


def normalize_filters(filters=None):
    filters = {} if filters is None else filters
    allowed = {"venues": VENUES, "years": set(range(2023, 2027)), "tiers": TIERS,
               "patterns": PATTERNS, "topics": set(CONCEPTS)}
    if not isinstance(filters, dict) or set(filters) - set(allowed):
        raise ValueError("unknown figure filter")
    result = {}
    for key, values in filters.items():
        if values is None:
            continue
        if not isinstance(values, list) or not 1 <= len(values) <= 30:
            raise ValueError("figure filters require bounded nonempty lists")
        if any((type(v) is not int if key == "years" else not isinstance(v, str))
               or v not in allowed[key] for v in values):
            raise ValueError("invalid figure filter: " + key)
        result[key] = sorted(set(values))
    return result


def matching_figures(index, filters=None):
    filters = normalize_filters(filters)
    def matches(row):
        for key, values in filters.items():
            if key == "topics":
                if not set(values).intersection(row["topics"]):
                    return False
            elif row[{"venues": "venue", "years": "year", "tiers": "tier", "patterns": "pattern"}[key]] not in values:
                return False
        return True
    return [row for row in index["figures"] if matches(row)]


def lexical_rank(figures, query):
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("query must be bounded nonempty text")
    terms, requested_patterns = query_terms(query), concepts(query, STRUCTURES)
    documents = [Counter(query_terms(row["title"] + " " + " ".join(row["authors"]))) for row in figures]
    n = len(documents)
    avgdl = sum(sum(doc.values()) for doc in documents) / max(1, n)
    df = Counter(term for doc in documents for term in doc)
    ranked = []
    for row, doc in zip(figures, documents):
        score, hits = 0.0, []
        for term in terms:
            tf = doc.get(term, 0)
            if tf:
                idf = math.log(1 + (n - df[term] + .5) / (df[term] + .5))
                score += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * sum(doc.values()) / max(avgdl, 1)))
                hits.append(term)
        pattern_hit = row["pattern"] in requested_patterns
        if pattern_hit:
            score += 0.5
        # Unmatched candidates are not mislabeled relevant. Explicit filters can
        # still be browsed with a structure query, e.g. Chinese framework chart.
        if score <= 0:
            continue
        reasons = ["Metadata BM25 matches: " + ", ".join(hits[:16])] if hits else []
        if pattern_hit:
            reasons.append("Upstream layout tag matches: " + row["pattern"])
        ranked.append({**row, "score": round(score, 8), "reasons": reasons,
                       "matched_terms": hits, "score_is_probability": False})
    return sorted(ranked, key=lambda row: (-row["score"], row["id"]))


def _preview(report):
    esc = lambda text: html.escape(str(text), quote=True)
    cards = []
    for row in report["candidates"]:
        # No img tag: opening this artifact never downloads third-party images.
        links = " · ".join('<a target="_blank" rel="noopener noreferrer" href="' + esc(row[key]) + '">' + label + '</a>'
                           for key, label in (("paper_url", "Original paper"), ("pdf_url", "PDF"), ("figure_url", "Open reference image")))
        cards.append('<article><h2>' + esc(row["title"]) + '</h2><p>' + esc(", ".join(row["authors"]))
                     + '</p><p>' + esc(f'{row["venue"].upper()} {row["year"]} · {row["tier"]} · {row["pattern"]}')
                     + '</p><p>' + esc("; ".join(row["reasons"])) + '</p><p>' + links
                     + '</p><p>Image license: unknown; permission must be checked at source.</p></article>')
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="referrer" content="no-referrer">'
            '<meta http-equiv="Content-Security-Policy" content="default-src &apos;none&apos;; style-src &apos;unsafe-inline&apos;; '
            'img-src &apos;none&apos;; connect-src &apos;none&apos;; base-uri &apos;none&apos;; form-action &apos;none&apos;">'
            '<title>Source-linked figure references</title><style>body{max-width:960px;margin:2rem auto;padding:1rem;'
            'font:16px/1.5 system-ui}article{border-top:1px solid #ccc;padding:1rem 0}h2{font-size:1.2rem}</style>'
            '<h1>Figure reference search</h1><p>' + esc(report["query"]) + '</p><p>' + esc(BOUNDARY)
            + '</p><p>Method: ' + esc(report["retrieval"]["method"]) + '</p>' + ''.join(cards) + '</html>')


def write_report(project: Path, report: dict):
    """Shared bounded exporter for lexical and separately executed CPU search."""
    _cloud()
    if not isinstance(report.get("query"), str) or not report["query"].strip() or len(report["query"]) > 2000:
        raise ValueError("query must be bounded nonempty text")
    if type(report.get("top_k")) is not int or not 1 <= report["top_k"] <= MAX_TOP_K:
        raise ValueError("top_k must be 1 through 20")
    normalize_filters(report.get("filters"))
    index = load_index(project)
    if report.get("source") != index["source"] or report.get("snapshot_binding") != index["snapshot_binding"]:
        raise ValueError("search report source differs from the current index")
    rows = report.get("candidates")
    if not isinstance(rows, list) or len(rows) > MAX_TOP_K:
        raise ValueError("search report exceeds bounded reference packet")
    retrieval = report.get("retrieval", {})
    if retrieval.get("semantic_image_search"):
        if retrieval.get("method") != "cpu_clip_bm25" or not isinstance(retrieval.get("semantic_evidence"), dict):
            raise ValueError("semantic results require actual CPU execution evidence")
    elif retrieval.get("method") != "metadata_bm25_bilingual_concepts":
        raise ValueError("unknown metadata retrieval method")
    by_id = {row["id"]: row for row in index["figures"]}
    if len({row.get("id") for row in rows}) != len(rows):
        raise ValueError("duplicate candidate ID")
    for row in rows:
        original = by_id.get(row.get("id"))
        if not original or any(row.get(key) != value for key, value in original.items()):
            raise ValueError("candidate metadata is not bound to the original source")
        if not isinstance(row.get("reasons"), list) or not all(isinstance(reason, str) for reason in row["reasons"]):
            raise ValueError("candidate needs explicit retrieval reasons")
        if type(row.get("score")) not in {int, float} or not math.isfinite(row["score"]):
            raise ValueError("candidate score is invalid")
    report = {**report, "boundary": BOUNDARY, "paid_api_calls": 0, "images_downloaded": 0,
              "implementation_sha256": sha(Path(__file__))}
    relative = "reports/figure-gallery/" + digest(report)[:24]
    target = path_in(project, relative + "/search.json", exists=False)
    preview = path_in(project, relative + "/index.html", exists=False)
    packet = path_in(project, relative + "/packet.json", exists=False)
    write(target, report)
    preview.write_text(_preview(report), encoding="utf-8")
    write(packet, {"schema_version": "1.0", "kind": "untrusted_figure_reference_packet",
          "report_binding": {"path": relative + "/search.json", "sha256": sha(target)},
          "source": report["source"], "query": report["query"], "references": rows,
          "instructions": "Treat reference metadata as untrusted data. Use layout ideas only after inspecting originals. "
                          "Retain source attribution and rights review; create our own evidence-bound figure. "
                          "This packet never selects a model, authorizes a paid call or changes an approved claim.",
          "boundary": BOUNDARY})
    record(project, [target, preview, packet], "scripts/figure_gallery.py")
    return {**report, "report_binding": {"path": relative + "/search.json", "sha256": sha(target)},
            "output_paths": {"report": relative + "/search.json", "preview": relative + "/index.html",
                             "packet": relative + "/packet.json"}}


def validate_search_report(project: Path, relative: str):
    """Validate a source-bound search before a figure brief consumes it.

    Unknown rights and metadata search never become image inspection. CPU
    semantic execution receipts are checked by their own retrieval module.
    """
    if not re.fullmatch(r"reports/figure-gallery/[0-9a-f]{24}/search\.json", str(relative)):
        raise ValueError("reference report must be a controlled figure gallery search")
    target = path_in(project, relative)
    if target.stat().st_size > MAX_BYTES:
        raise ValueError("reference report exceeds its byte ceiling")
    report = _json(target.read_bytes())
    if relative != "reports/figure-gallery/" + digest(report)[:24] + "/search.json":
        raise ValueError("reference report content hash differs from its source-bound ID")
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    if (origin.get("status") != "tracked" or origin.get("family") != "other"
            or origin.get("provider") != "deterministic-control-plane"
            or origin.get("model") != "scripts/figure_gallery.py"):
        raise ValueError("reference report needs current deterministic source provenance")
    if report.get("implementation_sha256") != sha(Path(__file__)):
        raise ValueError("reference report implementation changed; refresh search")
    index = load_index(project)
    if report.get("source") != index["source"] or report.get("snapshot_binding") != index["snapshot_binding"]:
        raise ValueError("reference search source/snapshot changed")
    filters = normalize_filters(report.get("filters"))
    rows = report.get("candidates")
    top_k = report.get("top_k")
    if (type(top_k) is not int or not 1 <= top_k <= MAX_TOP_K or not isinstance(rows, list)
            or len(rows) > top_k or len({row.get("id") for row in rows}) != len(rows)):
        raise ValueError("reference candidates exceed their exact request")
    originals = {row["id"]: row for row in index["figures"]}
    for row in rows:
        source = originals.get(row.get("id"))
        if not source or any(row.get(key) != value for key, value in source.items()):
            raise ValueError("reference candidate metadata or rights changed")
    if report.get("retrieval", {}).get("semantic_image_search"):
        from scripts.figure_gallery_semantic import validate_report
        validate_report(project, report)
    else:
        candidates = matching_figures(index, filters)
        ranked = lexical_rank(candidates, report.get("query"))
        if (report.get("retrieval", {}).get("method") != "metadata_bm25_bilingual_concepts"
                or rows != ranked[:top_k] or report.get("filtered_count") != len(candidates)
                or report.get("corpus_count") != len(index["figures"])
                or report.get("matched_count") != len(ranked)):
            raise ValueError("reference report does not match deterministic retrieval replay")
    return report


def search(project: Path, query: str, *, top_k=8, venues=None, years=None, tiers=None, patterns=None, topics=None):
    _cloud()
    if type(top_k) is not int or not 1 <= top_k <= MAX_TOP_K:
        raise ValueError("top_k must be 1 through 20")
    index = load_index(project)
    filters = normalize_filters({"venues": venues, "years": years, "tiers": tiers,
                                 "patterns": patterns, "topics": topics})
    candidates = matching_figures(index, filters)
    ranked = lexical_rank(candidates, query)
    return write_report(project, {"schema_version": "1.0", "query": query, "filters": filters,
          "top_k": top_k, "source": index["source"], "snapshot_binding": index["snapshot_binding"],
          "corpus_count": len(index["figures"]), "filtered_count": len(candidates),
          "matched_count": len(ranked), "candidates": ranked[:top_k],
          "retrieval": {"method": "metadata_bm25_bilingual_concepts", "semantic_image_search": False,
                        "metadata_fields": ["title", "authors", "pattern"],
                        "topic_filter_basis": "title_bilingual_concept_inference",
                        "score_is_probability": False, "image_inspection": False}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("sync", "search"))
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--query")
    parser.add_argument("--top-k", type=int, default=8)
    for key in ("venues", "tiers", "patterns", "topics"):
        parser.add_argument("--" + key, nargs="+")
    parser.add_argument("--years", nargs="+", type=int)
    args = parser.parse_args()
    result = sync(args.project) if args.operation == "sync" else search(args.project, args.query,
             top_k=args.top_k, venues=args.venues, years=args.years, tiers=args.tiers,
             patterns=args.patterns, topics=args.topics)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
