"""Original-research-first portfolio rules. Read-only; never relabels a paper."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from scripts.research_artifacts import path_in, read, sha

PRIMARY = {"empirical", "computational", "theoretical", "case-study", "policy", "software"}
SECONDARY = {"meta-analysis", "quantitative-reanalysis", "bibliometric-hypothesis-test"}
PROTOCOL_FIELDS = {"question", "input_selection", "data_extraction", "comparability",
                   "bias_and_dependence", "estimand", "analysis_method", "uncertainty",
                   "robustness", "added_knowledge", "cloud_execution"}
FIELDS = {"schema_version", "paper_id", "research_kind", "design_family", "methods",
          "reporting_description", "new_analysis_rationale", "validation_plan", "claim_ids",
          "secondary_protocol", "venue_classifications", "analysis_evidence", "reporting_statement"}
POLICY = "original-research-first-v1"


def template(paper_id: str) -> dict:
    return {"schema_version": "1.0", "paper_id": paper_id, "research_kind": "unassigned",
            "design_family": "unassigned", "methods": [], "reporting_description": "",
            "new_analysis_rationale": "", "validation_plan": "", "claim_ids": [],
            "secondary_protocol": None, "venue_classifications": [], "analysis_evidence": [],
            "reporting_statement": None}


def _text(value, label, minimum=30, maximum=5000):
    if (not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum
            or re.search(r"(?i)\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b", value)):
        raise ValueError(label + " requires a concrete bounded explanation")
    return value.strip()


def _strings(value, label):
    if (not isinstance(value, list) or not 1 <= len(value) <= 100
            or any(not isinstance(x, str) or not 0 < len(x.strip()) <= 200 for x in value)
            or len(value) != len(set(value))):
        raise ValueError(label + " requires unique bounded nonempty strings")
    return value


def _host(value):
    parsed = urlsplit(value) if isinstance(value, str) else None
    if (not parsed or parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.port not in {None, 443} or parsed.query):
        raise ValueError("official article-category URL requires credential-free HTTPS")
    return parsed.hostname.lower().removeprefix("www.")


def _anchor(project, value):
    if not isinstance(value, dict) or not str(value.get("path", "")).startswith("evidence/"):
        raise ValueError("article-category evidence must be a preserved source under evidence/")
    target = path_in(project, value["path"])
    if target.stat().st_size > 2_000_000 or value.get("sha256") != sha(target):
        raise ValueError("article-category evidence is oversized or has a stale hash")
    lines = target.read_text(encoding="utf-8").splitlines()
    start, end = value.get("start_line"), value.get("end_line")
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
        raise ValueError("article-category evidence needs actual 1-based source lines")
    quote = _text(value.get("quote"), "article-category quote", 10, 4000)
    if quote not in "\n".join(lines[start - 1:end]):
        raise ValueError("article-category quote is absent from the declared source lines")
    return quote


def _venues(project, paper_id, identity, contract, gate):
    venues = identity.get("venue_classifications")
    if not isinstance(venues, list) or not 1 <= len(venues) <= 20 or any(not isinstance(v, dict) for v in venues):
        raise ValueError("declare source-bound research-article classifications for target venues")
    names = [v.get("venue_name") for v in venues]
    if any(not isinstance(n, str) or not n for n in names) or len(names) != len(set(names)):
        raise ValueError("venue classifications need unique exact venue names")
    targets = contract.get("target_venues", [])
    if not isinstance(targets, list) or any(not isinstance(v, dict) for v in targets):
        raise ValueError("paper contract target venues must be objects")
    candidates = read(path_in(project, "program/venue-candidates.json"))
    candidate_rows = [v for row in candidates.get("papers", []) if row.get("paper_id") == paper_id
                      for v in row.get("candidates", [])]
    required_names = {v["name"] for v in targets}
    selected = None
    if gate == "G5":
        selected = read(path_in(project, f"papers/{paper_id}/venue.json"))
        if not selected.get("name") or selected["name"] not in required_names:
            raise ValueError("selected venue must match an exact paper-contract target")
        required_names = {selected["name"]}
    if not required_names or not required_names <= set(names):
        raise ValueError("missing research-article classification for a required target venue")
    now = datetime.now(timezone.utc)
    for name in sorted(required_names):
        item = next(v for v in venues if v["venue_name"] == name)
        target = next(v for v in targets if v["name"] == name)
        matches = [v for v in candidate_rows if v.get("name") == name]
        if len(matches) != 1:
            raise ValueError("article-category evidence needs one matching registered venue candidate")
        hosts = {_host(matches[0][key]) for key in ("official_guidelines_url", "policy_source_url")}
        if _host(item.get("official_url")) not in hosts:
            raise ValueError("article-category evidence must use the registered journal/publisher domain")
        checked = datetime.fromisoformat(str(item.get("checked_at", "")).replace("Z", "+00:00"))
        if checked.tzinfo is None or not now - timedelta(days=30) <= checked <= now + timedelta(minutes=5):
            raise ValueError("article-category policy must be checked within 30 days")
        category = _text(item.get("article_type"), "actual journal article type", 3, 200)
        if category != target.get("article_type") or category != matches[0].get("article_type"):
            raise ValueError("actual article type must match the contract and registered venue; never rename Review")
        if re.search(r"(?i)\b(?:review|survey|editorial|commentary|perspective)\b", category):
            raise ValueError("the original-research-first portfolio excludes a venue's actual review/opinion category")
        if item.get("research_article_eligible") is not True or item.get("design_eligible") is not True:
            raise ValueError("resolve research-article and actual study-design eligibility")
        quote = _anchor(project, item.get("evidence"))
        if category.casefold() not in quote.casefold():
            raise ValueError("preserved official quote must identify the actual article category")
        _text(item.get("rationale"), "design-specific journal eligibility rationale", 60)
    # Source authenticity, policy interpretation and scientific merit still need
    # the existing independent audit and named human gate; booleans are not proof.


def _analysis(project, paper_id, evidence):
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 50:
        raise ValueError("secondary quantitative research needs actual executor-issued analysis evidence")
    from scripts.research_quality import _registry
    registry = _registry(project)
    plan_path = path_in(project, "experiments/plan.json")
    plan = read(plan_path)
    state = read(path_in(project, "state/run.json"))
    approval = next((a for a in reversed(state.get("approvals", [])) if a.get("gate") == "G3"), None)
    if ("G3" not in state.get("approved_gates", []) or not approval
            or approval.get("experiment_plan_sha256") != sha(plan_path)):
        raise ValueError("secondary analysis needs the current human-approved G3 experiment-plan hash")
    _text(approval.get("actor"), "named human G3 approver", 2, 200)
    seen = set()
    for item in evidence:
        if not isinstance(item, dict) or not isinstance(item.get("attempt_id"), str):
            raise ValueError("secondary analysis evidence needs an exact attempt ID")
        key = (item["attempt_id"], item.get("path"))
        if key in seen:
            raise ValueError("duplicate secondary analysis evidence")
        seen.add(key)
        matches = [r for r in registry if r.get("attempt_id") == item["attempt_id"]]
        if len(matches) != 1:
            raise ValueError("secondary analysis requires one exact registered attempt")
        receipt = matches[0]
        runs = [r for r in plan.get("runs", []) if r.get("run_id") == receipt.get("run_id") and r.get("paper_id") == paper_id]
        if (receipt.get("status") != "succeeded" or receipt.get("paper_id") != paper_id
                or receipt.get("approved_plan_sha256") != sha(plan_path) or len(runs) != 1
                or read(path_in(project, f"experiments/runs/{item['attempt_id']}/run.json")) != receipt):
            raise ValueError("secondary analysis evidence differs from the successful approved executor receipt")
        if item.get("path") not in runs[0].get("expected_outputs", []):
            raise ValueError("secondary analysis must use a predeclared output")
        output = path_in(project, item.get("path", ""))
        if (not any(o.get("path") == item["path"] and o.get("sha256") == sha(output) for o in receipt.get("outputs", []))
                or item.get("sha256") != sha(output)):
            raise ValueError("secondary analysis output is stale or absent from the executor receipt")
    # Existing G4 statistics, all-attempt inclusion, provenance, preregistration,
    # independence and reproduction checks remain mandatory in addition to this.


def validate(project: Path, paper_id: str, gate: str) -> list[str]:
    if gate not in {"G2", "G3", "G4", "G5"}:
        return []
    try:
        if not isinstance(paper_id, str) or not re.fullmatch(r"P[0-9]{2}", paper_id):
            raise ValueError("select an exact paper ID")
        identity_path = path_in(project, f"papers/{paper_id}/research-identity.json")
        if identity_path.stat().st_size > 200_000:
            raise ValueError("research identity exceeds the bounded input size")
        identity = read(identity_path)
        contract = read(path_in(project, f"papers/{paper_id}/paper-contract.json"))
        if set(identity) != FIELDS or identity.get("schema_version") != "1.0" or identity.get("paper_id") != paper_id:
            raise ValueError("research identity needs the exact declared schema and paper ID")
        kind, design = identity["research_kind"], identity["design_family"]
        if not ((kind == "primary" and design in PRIMARY) or (kind == "secondary_quantitative" and design in SECONDARY)):
            raise ValueError("assign original primary research or substantive secondary quantitative research; narrative/systematic-summary reviews are excluded")
        methods = _strings(identity["methods"], "actual research methods")
        if kind == "primary" and any(m in {"meta_analysis", "literature_summary", "systematic_review"} for m in methods):
            raise ValueError("a literature-based synthesis cannot be relabeled primary research; use secondary_quantitative or explicitly meta_analysis_of_own_studies")
        _text(identity["new_analysis_rationale"], "new knowledge beyond the closest work", 60)
        _text(identity["validation_plan"], "study-specific validation plan", 60)
        description = _text(identity["reporting_description"], "honest manuscript study description", 15, 250)
        if design == "meta-analysis" and ("meta_analysis" not in methods or not re.search(r"(?i)meta[ -]analysis", description)):
            raise ValueError("Meta analysis must be declared as an actual method and in the manuscript study description")
        claims = _strings(identity["claim_ids"], "research contribution claim IDs")
        if set(claims) != set(contract.get("independence", {}).get("unique_claim_ids", [])):
            raise ValueError("research identity claim IDs must match the paper's independent contribution")
        protocol = identity["secondary_protocol"]
        if kind == "secondary_quantitative":
            if not isinstance(protocol, dict) or set(protocol) != PROTOCOL_FIELDS:
                raise ValueError("secondary research needs a complete quantitative protocol, not a method name")
            for field in sorted(PROTOCOL_FIELDS):
                _text(protocol[field], "secondary_protocol." + field, 40)
            if gate in {"G4", "G5"}:
                _analysis(project, paper_id, identity["analysis_evidence"])
        elif protocol is not None:
            raise ValueError("primary research cannot silently carry a secondary-literature protocol")
        _venues(project, paper_id, identity, contract, gate)
        if gate == "G5":
            from scripts.ref_verify_adapter import canonical_manuscript
            from scripts.revision_trace import normalized, verify_location
            statement = identity["reporting_statement"]
            if not isinstance(statement, dict) or normalized(description) not in normalized(statement.get("excerpt", "")):
                raise ValueError("the final manuscript must state its actual study design, including Meta analysis when used")
            paper = project / "papers" / paper_id
            verify_location(paper, canonical_manuscript(paper), json.dumps(statement.get("location")), statement["excerpt"])
            checklist = read(path_in(project, f"papers/{paper_id}/reviews/pre-submission-checklist.json"))
            expected = "review" if kind == "secondary_quantitative" else "computational" if design == "software" else design
            if checklist.get("article_type") != expected:
                raise ValueError("scientific checklist must match the actual research design; a research journal category cannot waive synthesis checks")
        return []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError, RuntimeError) as exc:
        return [f"{paper_id} original-research policy: {exc}"]


def review_binding(project: Path, paper_id: str) -> dict:
    """Bind classification policy/evidence into the existing paper approval hash."""
    target = path_in(project, f"papers/{paper_id}/research-identity.json", exists=False)
    sources = []
    if target.is_file():
        try:
            value = read(target)
            for row in value.get("venue_classifications", []):
                anchor = row.get("evidence", {})
                source = path_in(project, anchor.get("path", ""))
                sources.append({"path": anchor["path"], "sha256": sha(source)})
        except (ValueError, OSError, KeyError, TypeError, AttributeError):
            sources = [{"status": "unverifiable"}]
    return {"policy": POLICY, "implementation_sha256": sha(Path(__file__)),
            "identity_sha256": sha(target) if target.is_file() else None, "sources": sources}


def prompt_contract() -> str:
    return ("Original-research-first policy: plan every portfolio paper around a distinct new question, "
        "analysis and defensible contribution. Exclude narrative reviews and literature-summary-only papers. "
        "Prefer primary research; secondary quantitative research needs a genuine new analysis protocol, "
        "current source-bound journal Research/Original Article eligibility for that actual design, and "
        "successful approved executor analysis evidence at G4/G5. Meta analysis is a method, not a relabeling "
        "shortcut. State secondary methods truthfully in the manuscript and retain the review/synthesis "
        "scientific checklist. Never rename a venue's actual Review category, hide synthesis or promise "
        "degree eligibility. At G2 create papers/Pxx/research-identity.json for every paper using "
        "schemas/research-identity.schema.json and docs/ORIGINAL-RESEARCH-POLICY.md. Keep types unassigned "
        "until actual topic/material assessment. Existing G3/G4 experiments and all human approvals remain "
        "required; this policy introduces no alternative executor, paid call, budget grant, or model switch.")
