"""Collect dated primary-source receipts and recompute the owner's direction rubric.

Scores remain decision aids for human review. Counts describe the sampled window,
not the total market. Missing evidence never receives an invented neutral score.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from scripts import network_safety
from scripts.cloud_research_steps import path_in, read, write
from scripts.cloud_checkpoint import sha

ROOT = Path(__file__).resolve().parents[1]
FACTORS = ("funded_position_supply", "job_market_and_salary", "future_growth_potential",
           "phd_position_competition", "job_market_competition", "background_fit", "application_route_fit")
EXPECTED_WEIGHTS = (0.25, 0.25, 0.15, 0.075, 0.075, 0.10, 0.10)


class DirectionEvidenceError(ValueError):
    pass


class PageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.hidden = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def canonical_url(url: str) -> str:
    parsed = urlsplit(network_safety.validate_https_url(url))
    if parsed.query and any(k in parsed.query.lower() for k in ("token=", "key=", "password=")):
        raise DirectionEvidenceError("source URLs cannot contain credentials")
    return urlunsplit(("https", parsed.netloc.lower(), parsed.path, parsed.query, ""))


def primary(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain)
               for domain in read(ROOT / "config/direction-primary-domains.json")["domains"])


def fetch_sources(project: Path, urls: list[str], fetcher=None) -> dict:
    fetcher = fetcher or network_safety.fetch_bytes
    ledger_path = project / "evidence/direction-sources/index.json"
    ledger = read(ledger_path, {"schema_version": "1.0", "sources": {}})
    if len(set(urls)) > 80:
        raise DirectionEvidenceError("at most 80 primary source URLs per direction assessment")
    for url in sorted(set(urls)):
        url = canonical_url(url)
        if not primary(url):
            raise DirectionEvidenceError("source domain needs verification before adding it to direction-primary-domains.json")
        previous = ledger["sources"].get(url, {})
        try:
            current = (timedelta(0) <= datetime.now(timezone.utc) - datetime.fromisoformat(previous["retrieved_at"]) < timedelta(days=7)
                       and sha(path_in(project, previous["path"])) == previous["sha256"]
                       and sha(path_in(project, previous["raw_path"])) == previous["raw_sha256"])
        except (KeyError, ValueError, OSError):
            current = False
        if current:
            continue
        try:
            payload, final_url, status, mime = fetcher(url, max_bytes=4_000_000)
            if status != 200 or not primary(final_url):
                raise DirectionEvidenceError("primary source fetch failed or redirected outside reviewed domains")
            body = payload.decode("utf-8", errors="replace")
            parser = PageText()
            parser.feed(body)
            text = " ".join(" ".join(parser.parts).split()) if "html" in (mime or "") else body
            identity = hashlib.sha256((url + hashlib.sha256(payload).hexdigest()).encode()).hexdigest()[:24]
            relative = f"evidence/direction-sources/{identity}.txt"
            raw_relative = f"evidence/direction-sources/{identity}.html"
            path_in(project, relative).parent.mkdir(parents=True, exist_ok=True)
            path_in(project, relative).write_text(text, encoding="utf-8")
            path_in(project, raw_relative).write_bytes(payload)
            ledger["sources"][url] = {"url": url, "final_url": final_url, "http_status": status,
                "retrieved_at": datetime.now(timezone.utc).isoformat(), "path": relative,
                "sha256": sha(path_in(project, relative)), "raw_path": raw_relative,
                "raw_sha256": hashlib.sha256(payload).hexdigest(), "status": "retrieved"}
        except (ValueError, OSError, RuntimeError) as exc:
            ledger["sources"][url] = {"url": url, "status": "unavailable", "error": str(exc)[:400]}
    write(ledger_path, ledger)
    return ledger


def support(project: Path, reference: dict, ledger: dict) -> str:
    url = canonical_url(reference.get("url", ""))
    receipt = ledger["sources"].get(url, {})
    if receipt.get("status") != "retrieved":
        raise DirectionEvidenceError("assessment lacks a retrieved primary source")
    age = datetime.now(timezone.utc) - datetime.fromisoformat(receipt["retrieved_at"])
    if not timedelta(0) <= age <= timedelta(days=14):
        raise DirectionEvidenceError("direction source must have been retrieved within the last 14 days")
    path = path_in(project, receipt["path"])
    if sha(path) != receipt["sha256"] or sha(path_in(project, receipt["raw_path"])) != receipt["raw_sha256"]:
        raise DirectionEvidenceError("direction source receipt is stale")
    quote = reference.get("quote", "")
    normalized = " ".join(path.read_text(encoding="utf-8").split())
    if not isinstance(quote, str) or len(quote.strip()) < 12 or " ".join(quote.split()) not in normalized:
        raise DirectionEvidenceError("direction evidence needs an exact supporting passage in the retrieved page")
    return quote


def band(value: float, boundaries: tuple[float, ...]) -> int:
    return sum(value >= threshold for threshold in boundaries)


def number_supported(value, quote: str) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return False
    numbers = re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?!\d|\.\d)", re.sub(r"(?<=\d)[, ](?=\d{3}(?:\D|$))", "", quote))
    return any(math.isclose(float(n), value, rel_tol=1e-9) for n in numbers)


def rank(project: Path, assessment: dict, ledger: dict) -> dict:
    constraints = read(project / "intake/constraints.json", {})
    weights = constraints.get("ranking_weights", {})
    if set(weights) != set(FACTORS) or any(not math.isclose(weights[k], v) for k, v in zip(FACTORS, EXPECTED_WEIGHTS)):
        raise DirectionEvidenceError("ranking must use the owner's confirmed seven weights")
    start, end = date.fromisoformat(assessment["window_start"]), date.fromisoformat(assessment["window_end"])
    if not 0 < (end - start).days <= 90 or end > date.today() or (date.today() - end).days > 14:
        raise DirectionEvidenceError("use the same recent observation window of at most 90 days")
    candidates = assessment.get("candidates")
    if not isinstance(candidates, list) or len(candidates) < 3:
        raise DirectionEvidenceError("compare at least three eligible cloud-feasible directions")
    rows, errors = [], []
    seen_ids = set()
    for item in candidates:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen_ids:
            raise DirectionEvidenceError("direction IDs must be unique")
        seen_ids.add(identifier)
        if (item.get("cloud_feasible") is not True or item.get("no_future_lab_dependency") is not True
                or not item.get("authorized_data_plan") or not item.get("cloud_compute_plan")):
            rows.append({"id": identifier, "eligible": False, "reason": "cloud feasibility prerequisites missing"})
            continue
        try:
            unique, salaries = {}, []
            for observation in item.get("observations", []):
                quote = support(project, observation["evidence"], ledger)
                if not start <= date.fromisoformat(observation["observed_date"]) <= end:
                    raise DirectionEvidenceError("position is outside the shared observation window")
                if observation.get("eligible") is not True:
                    continue
                if (observation.get("kind") not in {"funded_phd", "job"}
                        or not observation.get("eligibility_rationale")
                        or observation.get("constraints_sha256") != sha(project / "intake/constraints.json")):
                    raise DirectionEvidenceError("eligible postings require a kind and intake-bound eligibility rationale")
                if observation.get("kind") == "funded_phd" and observation.get("fully_funded") is True:
                    support(project, observation["funding_evidence"], ledger)
                for key in ("employer", "title", "country"):
                    if not isinstance(observation.get(key), str) or not observation[key].strip():
                        raise DirectionEvidenceError("observations need employer, title and country")
                if observation["title"].casefold() not in quote.casefold():
                    raise DirectionEvidenceError("posting title must occur in its supporting passage")
                identity = tuple(observation[k].strip().casefold() for k in ("kind", "employer", "title", "country"))
                if identity in unique:
                    continue
                unique[identity] = observation
                salary = observation.get("salary")
                if observation["kind"] == "job" and salary:
                    if salary.get("basis") != "gross" or salary.get("career_stage") != item.get("career_stage"):
                        raise DirectionEvidenceError("salary comparisons need the same career stage and gross basis")
                    amount = salary.get("amount")
                    factor = {"year": 1, "month": 12}.get(salary.get("period"))
                    if isinstance(amount, bool) or not isinstance(amount, (float, int)) or not math.isfinite(amount) or amount <= 0 or factor is None:
                        raise DirectionEvidenceError("salary requires a positive amount and month/year period")
                    if not number_supported(amount, support(project, salary["evidence"], ledger)):
                        raise DirectionEvidenceError("salary amount is not present in its source passage")
                    rate = 1.0
                    if salary.get("currency") != "CNY":
                        rate = salary.get("fx_to_cny")
                        fx_quote = support(project, salary["fx_evidence"], ledger)
                        if not number_supported(rate, fx_quote):
                            raise DirectionEvidenceError("currency conversion needs dated primary rate evidence")
                    salaries.append(amount * factor * rate)
            phd = sum(o["kind"] == "funded_phd" and o.get("fully_funded") is True for o in unique.values())
            jobs = sum(o["kind"] == "job" for o in unique.values())
            if not salaries or not unique:
                raise DirectionEvidenceError("employment/salary evidence is incomplete; no neutral score is invented")
            scores = {"funded_position_supply": band(phd, (1, 5, 15, 30, 60)),
                      "job_market_and_salary": (band(jobs, (1, 5, 15, 30, 60)) + band(statistics.median(salaries), (100000, 200000, 300000, 500000, 800000))) / 2}
            for factor in FACTORS[2:]:
                value = item.get("assessments", {}).get(factor, {})
                score = value.get("score")
                if (isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 5
                        or value.get("method") not in {"measured", "proxy", "assessment"}
                        or value.get("confidence") not in {"low", "medium", "high"}
                        or not value.get("rationale") or not value.get("anchor_description")):
                    raise DirectionEvidenceError(f"{factor} needs anchored scoring, rationale, method and confidence")
                if factor == "background_fit":
                    if value.get("constraints_sha256") != sha(project / "intake/constraints.json"):
                        raise DirectionEvidenceError("background assessment must bind the confirmed intake; degrees remain self-reported")
                else:
                    refs = value.get("evidence", [])
                    if not refs:
                        raise DirectionEvidenceError(f"{factor} has no primary evidence")
                    for ref in refs:
                        support(project, ref, ledger)
                scores[factor] = score
            rows.append({"id": identifier, "eligible": True, "scores": scores,
                         "observed_funded_positions": phd, "observed_jobs": jobs,
                         "median_gross_annual_salary_cny": statistics.median(salaries),
                         "weighted_score": round(sum(weights[k] * scores[k] for k in FACTORS), 4),
                         "salary_limits": "Nominal gross conversion, not purchasing power or guaranteed take-home pay",
                         "sample_limits": item.get("sample_limits", "Coverage is limited to retrieved eligible postings")})
        except (ValueError, KeyError, TypeError, OSError) as exc:
            errors.append({"id": identifier, "error": str(exc)})
    valid = [r for r in rows if r.get("eligible")]
    sensitivity = []
    for factor in FACTORS:
        for multiplier in (0.8, 1.2):
            altered = {k: v * (multiplier if k == factor else 1) for k, v in weights.items()}
            total = sum(altered.values())
            ranking = sorted(valid, key=lambda r: sum(altered[k] / total * r["scores"][k] for k in FACTORS), reverse=True)
            sensitivity.append({"factor": factor, "multiplier": multiplier, "ranking": [r["id"] for r in ranking]})
    return {"schema_version": "1.0", "status": "blocked" if errors or len(valid) < 3 else "ready_for_human_review",
            "weights": weights, "window_start": str(start), "window_end": str(end),
            "candidates": sorted(rows, key=lambda r: r.get("weighted_score", -1), reverse=True),
            "errors": errors, "sensitivity": sensitivity, "novelty_is_a_tradeable_score": False,
            "assessment_sha256": hashlib.sha256(json.dumps(assessment, sort_keys=True).encode()).hexdigest(),
            "source_ledger_sha256": sha(project / "evidence/direction-sources/index.json"),
            "count_anchor_bands": [1, 5, 15, 30, 60], "annual_cny_salary_anchor_bands": [100000, 200000, 300000, 500000, 800000],
            "employment_salary_subweights": [0.5, 0.5], "human_review_required": True}


def refresh(project: Path) -> dict:
    assessment = read(project / "program/direction-assessments.json")
    if assessment is None:
        return {"status": "needs_assessments", "errors": ["Create source-bound direction-assessments.json"]}
    def urls(value):
        if isinstance(value, dict):
            return ([value["url"]] if isinstance(value.get("url"), str) else []) + [u for v in value.values() for u in urls(v)]
        return [u for v in value for u in urls(v)] if isinstance(value, list) else []
    ledger = fetch_sources(project, urls(assessment))
    result = rank(project, assessment, ledger)
    write(project / "program/direction-ranking.json", result)
    return result


def validate_saved(project: Path) -> list[str]:
    try:
        assessment = read(project / "program/direction-assessments.json")
        saved = read(project / "program/direction-ranking.json")
        ledger = read(project / "evidence/direction-sources/index.json")
        if not assessment or not saved or not ledger:
            return ["direction ranking needs retrieved primary sources and a deterministic score report"]
        expected = rank(project, assessment, ledger)
        if saved != expected or expected["status"] != "ready_for_human_review":
            return ["direction ranking is incomplete or stale; review its evidence and recompute"]
        return []
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return ["direction ranking: " + str(exc)]
