"""Acquire/replay licensed eLife assessment anchors without a model or invented labels.

Raw publisher responses stay in the requested cache, outside Git. The small
manifest records exact versions, excerpts, rights evidence and disjoint splits.
It is an integration corpus, not human validation of a model or a paper.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from scripts.literature_benchmark import ELIFE_STRENGTHS, judgment_benchmark
from scripts.literature_evidence import fetch_provider_bytes
from scripts.network_safety import fetch_bytes
from scripts.research_artifacts import read, record, sha, write, json_field_spans

API = "https://api.elifesciences.org"
LICENSE = "https://creativecommons.org/licenses/by/4.0/"
PRIMARY_FIELDS = ("title", "abstract", "body", "references", "dataSets", "ethics", "additionalFiles", "impactStatement", "keywords")


def primary_json(raw):
    spans = json_field_spans(raw)
    return "{\n" + ",\n".join(json.dumps(key) + ":" + raw[slice(*spans[key])] for key in PRIMARY_FIELDS if key in spans) + "\n}"


def _fetch(url, cache):
    if urlsplit(url).hostname not in {"api.elifesciences.org", "api.crossref.org"} or not url.startswith("https://"):
        raise ValueError("only the two public source APIs are permitted")
    history = cache.with_name(cache.stem + "-attempts.json")
    attempts = read(history)["attempts"] if history.is_file() else []
    def transport(request_url, **kwargs):
        if urlsplit(request_url).hostname == "api.crossref.org":
            time.sleep(2)  # anonymous Crossref pool; one connection at a time
        event = {"url": request_url, "attempt": len(attempts) + 1, "at": datetime.now(timezone.utc).isoformat()}
        try:
            response = fetch_bytes(request_url, timeout=40, max_bytes=12_000_000, headers=kwargs["headers"])
            event["status"] = response[2]
            return response
        except Exception as exc:
            cause = exc.__cause__ or exc
            event.update(status=getattr(cause, "code", None), error=type(exc).__name__,
                         retry_after=(getattr(cause, "headers", None) or {}).get("Retry-After"))
            raise
        finally:
            attempts.append(event)
            write(history, {"attempts": attempts})
    body, _, _, _ = fetch_provider_bytes(transport, url, "crossref" if "api.crossref.org" in url else "elife")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(body)
    return json.loads(body)


def _plain(value):
    if isinstance(value, str):
        return html.unescape(re.sub(r"<[^>]*>", "", value))
    if isinstance(value, list):
        return "\n\n".join(filter(None, (_plain(item) for item in value)))
    if isinstance(value, dict):
        return "\n\n".join(_plain(value[key]) for key in ("title", "text", "content", "caption", "items", "body") if key in value)
    return ""


def _acquire(root, candidate, originals):
    identifier, version = candidate["id"], candidate["version"]
    if not re.fullmatch(r"[0-9]{4,8}", identifier) or type(version) is not int or version < 1:
        raise ValueError("source must identify an exact eLife version")
    base = root / "evidence/public-review-anchors" / identifier
    raw_base = originals / identifier
    url = f"{API}/articles/{identifier}/versions/{version}"
    assessment_doi = candidate["assessment_doi"]
    if not re.fullmatch(r"10\.7554/eLife\.[0-9]+\.[0-9]+\.sa[0-9]+", assessment_doi):
        raise ValueError("original assessment DOI is required")
    crossref = "https://api.crossref.org/works/" + quote(assessment_doi, safe="/")
    rights_path = raw_base / "crossref.json"
    rights = _fetch(crossref, rights_path)["message"]
    licenses = [row.get("URL", "").replace("http://", "https://") for row in rights.get("license", [])]
    if rights.get("type") != "peer-review" or rights.get("DOI", "").casefold() != assessment_doi.casefold() or LICENSE not in licenses:
        raise ValueError("public assessment needs its own registered CC BY 4.0 license")
    article_path = raw_base / "article.json"
    article = _fetch(url, article_path)
    assessment = article.get("elifeAssessment", {})
    if (article.get("copyright", {}).get("license") != "CC-BY-4.0" or article.get("id") != identifier
            or article.get("version") != version or assessment.get("doi") != assessment_doi
            or article.get("doi", "").casefold() != ("10.7554/eLife." + identifier).casefold()):
        raise ValueError("article version, rights or assessment identity changed")
    strengths = assessment.get("strength", [])
    if not strengths or not set(strengths) <= ELIFE_STRENGTHS:
        raise ValueError("published evidence category is missing or unknown")
    primary = primary_json(article_path.read_text(encoding="utf-8"))
    review = _plain(assessment.get("content", []))
    abstract = _plain(article.get("abstract", []))
    if not article.get("body") or len(primary) < 5_000 or not review or not abstract or review in primary:
        raise ValueError("complete primary text and a separate public assessment are required")
    def text(name, content):
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content + "\n", encoding="utf-8")
        return {"path": target.relative_to(root).as_posix(), "sha256": sha(target), "locator": "complete source text"}
    source, review_source = text("primary.txt", primary), text("assessment.txt", review)
    source["locator"] = "complete original API scientific fields; linked figures/attachments not visually assessed"
    attribution = text("source-attribution.txt", f"{_plain(article['title'])}\n{article['authorLine']}\nhttps://doi.org/{article['doi']}\nCC BY 4.0: {LICENSE}\nOriginal scientific API JSON values retained; review metadata excluded. Linked media not visually assessed.")
    declaration = base / "rights.json"
    write(declaration, {"reuse_allowed": True, "license_url": LICENSE, "paper_source_sha256": source["sha256"],
        "review_sha256": review_source["sha256"], "paper_copyright": article["copyright"],
        "assessment_doi": assessment_doi, "license_registry_url": crossref, "license_registry_sha256": sha(rights_path)})
    case = {"id": "elife-" + identifier, "paper_doi": article["doi"], "partition": candidate["partition"],
        "source": source, "quote": primary[:1500], "review": review_source, "review_quote": review[:1500],
        "label": "+".join(sorted(set(strengths))), "review_url": "https://doi.org/" + assessment_doi,
        "attribution": attribution,
        "rights": {"path": declaration.relative_to(root).as_posix(), "sha256": sha(declaration), "locator": "publisher and Crossref license records"},
        "question": "Assess the strength of evidence for the paper's central conclusions using the published eLife evidence-strength taxonomy. Preserve material weaknesses and distinguish evidence strength from significance."}
    observed = {**candidate, "title": _plain(article["title"]), "paper_doi": article["doi"], "api_url": url,
        "article_response_sha256": sha(article_path), "primary_sha256": source["sha256"],
        "assessment_sha256": review_source["sha256"], "license_url": LICENSE,
        "license_registry_url": crossref, "license_registry_sha256": sha(rights_path), "label": case["label"],
        "assessment_excerpt": case["review_quote"], "primary_characters": len(primary),
        "attribution": article["authorLine"], "assessment_attribution": "eLife editors and peer reviewers"}
    for key in ("primary_sha256", "assessment_sha256", "assessment_doi", "label"):
        if key in candidate and candidate[key] != observed[key]:
            raise ValueError("frozen public anchor changed: " + identifier + "/" + key)
    return case, observed


def collect(root: Path, frozen=None):
    project = root / "project"
    if frozen is None:
        listing = _fetch(API + "/articles?page=1&per-page=100&order=desc&sort=date", root / "listing.json")
        eligible = [row for row in listing["items"] if row.get("type") == "research-article"
            and row.get("copyright", {}).get("license") == "CC-BY-4.0" and row.get("elifeAssessment", {}).get("strength")]
        candidates = [{"id": row["id"], "version": row["version"], "assessment_doi": row["elifeAssessment"]["doi"],
            "partition": "holdout" if index % 3 == 2 else "calibration"} for index, row in enumerate(eligible[:24])]
    else:
        candidates = frozen["anchors"]
    if len(candidates) != 24 or len({row["id"] for row in candidates}) != 24:
        raise ValueError("exactly 24 distinct frozen papers are required")
    if sum(row.get("partition") == "calibration" for row in candidates) != 16 or sum(row.get("partition") == "holdout" for row in candidates) != 8:
        raise ValueError("the frozen design requires 16 calibration and 8 holdout papers")
    acquired = [_acquire(project, row, root / "originals") for row in candidates]
    anchors = project / "program/public-review-anchors.json"
    write(anchors, {"kind": "public_review", "label_space": "elife_evidence_strength", "cases": [row[0] for row in acquired]})
    sources = [project / case[key]["path"] for case, _ in acquired for key in ("source", "review", "rights", "attribution")]
    spec = {"schema_version": "1.0", "id": "elife-public-anchors", "anchor_set": {
        "path": anchors.relative_to(project).as_posix(), "sha256": sha(anchors), "locator": "frozen source-disjoint corpus"}}
    write(project / "program/judgment-benchmark.json", spec)
    write(project / "program/research-control.json", {"scientific_judgments": [{"operation": "judgment_benchmark",
        "request_file": "program/judgment-benchmark.json", "stages": ["topic-intelligence"], "panel_views": ["domain", "statistics"]}]})
    record(project, [anchors, *sources, project / "program/judgment-benchmark.json", project / "program/research-control.json"], "scripts/public_review_anchors.py")
    checked = judgment_benchmark(project, spec)
    return {"schema_version": "1.0", "observed_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed", "source_commit": os.environ.get("GITHUB_SHA"),
        "workflow_run_url": ("https://github.com/" + os.environ["GITHUB_REPOSITORY"] + "/actions/runs/" + os.environ["GITHUB_RUN_ID"])
            if os.environ.get("GITHUB_REPOSITORY") and os.environ.get("GITHUB_RUN_ID") else None,
        "implementation_sha256": sha(Path(__file__)), "model_calls": 0,
        "extraction_implementation_sha256": {"scripts/public_review_anchors.py": sha(Path(__file__)),
            "scripts/research_artifacts.py": sha(Path(__file__).with_name("research_artifacts.py"))},
        "primary_format": "original scientific JSON values, including all body/table/equation nodes and exact numeric lexemes; review fields excluded; linked media not visually assessed",
        "excerpt_transformation": "Review HTML markup removed and entities decoded; review excerpts truncated at 1500 characters; full originals retained outside the blind project",
        "sampling": "first 24 CC BY 4.0 research articles with assessments in the dated descending official listing; every third paper held out",
        "source": API, "anchors": [row[1] for row in acquired], "public_papers": checked["attributed_public_paper_count"],
        "requested_anchor_design_complete": checked["requested_anchor_design_complete"],
        "calibration_status": checked["calibration_status"], "model_predictions": 0,
        "human_claim_sample_agreement": None, "should_merge_detection": None,
        "scope": "published life-science evidence assessments; no claim of domain transfer, numerical score calibration or research completion"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    write(args.manifest, collect(args.cache, read(args.replay) if args.replay else None))
