"""Check truthful AI-use records and existing statements without a journal-policy gate."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from scripts import output_provenance
from scripts.ref_verify_adapter import canonical_manuscript
from scripts.research_artifacts import path_in, read, sha, write
from scripts.revision_trace import RevisionTraceError, normalized, verify_location

PREFIX = "reports/publication-disclosure"
PROVIDER = "deterministic-publication-disclosure"
MAX_BYTES = 2_000_000
LIMITS = {"paid_calls": 0, "automatic_submission": False, "manuscript_label_added": False,
          "human_policy_interpretation_review_required": False,
          "publisher_domain_authenticity_requires_human_review": False,
          "truthfulness_of_usage_requires_human_review": False,
          "independent_policy_and_source_review_required": False,
          "journal_ai_policy_evaluated": False,
          "external_author_responsibility_retained": True,
          "watermark_scan_can_waive_disclosure": False}


def _implementation() -> dict:
    root = Path(__file__).resolve().parent
    return {name: hashlib.sha256((root / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in ("publication_disclosure.py", "revision_trace.py")}


def _paper(project: Path, pid: str) -> Path:
    if not isinstance(pid, str) or not re.fullmatch(r"P[0-9]{2}", pid):
        raise ValueError("publication disclosure needs a valid paper ID")
    return path_in(project, f"papers/{pid}/venue.json").parent


def _bounded_text(path: Path) -> str:
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("disclosure input exceeds the 2 MB inspection limit")
    return path.read_text(encoding="utf-8")


def _object(path: Path) -> dict:
    value = json.loads(_bounded_text(path))
    if not isinstance(value, dict):
        raise ValueError("disclosure input must be a JSON object")
    return value


def _specific(value: object, label: str, minimum: int = 15) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise ValueError(label + " needs a specific nonempty explanation")
    text = value.strip()
    if re.search(r"(?i)\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b|\[(?:NAME|REASON|TOOL)[^\]]*\]", text):
        raise ValueError(label + " contains an unresolved template")
    return text


def _usage(value: object) -> object:
    if value is None or value == "" or value == {}:
        return value
    if isinstance(value, str):
        if not value.strip():
            return value
        text = _specific(value, "internal ai_use", 1)
        if re.search(r"(?i)^\s*(?:none|n/?a|not (?:used|applicable)|no (?:ai|artificial intelligence)|"
                     r"(?:ai|artificial intelligence|generative ai)(?: tools?)? (?:was |were |is |are )?not used)\b", text):
            raise ValueError("internal ai_use cannot deny the recorded AI-assisted workflow")
        return text
    if not isinstance(value, dict):
        raise ValueError("recorded ai_use must be text or an object")
    tools = value.get("tools") or []
    if not isinstance(tools, list) or len(tools) > 30:
        raise ValueError("recorded AI tools must be an array of at most 30 entries")
    for item in tools:
        if not isinstance(item, dict):
            raise ValueError("ai_use tools must be objects")
        _specific(item.get("name"), "AI tool name", 2)
        if item.get("purpose") is not None:
            _specific(item["purpose"], "AI tool purpose", 1)
    if value.get("human_oversight"):
        _specific(value["human_oversight"], "AI-use human oversight", 1)
    return value


def _statement(paper: Path, value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("a declared AI disclosure needs a real statement and source-bound location")
    excerpt = normalized(_specific(value.get("excerpt"), "AI disclosure statement", 30))
    location = value.get("location")
    if not isinstance(location, dict):
        raise ValueError("AI disclosure statement location must be a hash-bound object")
    if value.get("placement") == "manuscript":
        if location.get("kind") not in {"source_lines", "docx_paragraph", "docx_table_cell"}:
            raise ValueError("manuscript disclosure requires a canonical source location")
        verified = verify_location(paper, canonical_manuscript(paper), json.dumps(location), excerpt)
    elif value.get("placement") == "separate_upload":
        relative = location.get("path")
        if not isinstance(relative, str) or not relative.startswith("submission-materials/"):
            raise ValueError("separate disclosure must be in submission-materials for manual upload")
        target = path_in(paper, relative)
        if target.suffix.lower() not in {".txt", ".md", ".tex", ".docx"}:
            raise ValueError("unsupported separate disclosure source format")
        if target.suffix.lower() in {".tex", ".docx"}:
            verified = verify_location(paper, target, json.dumps(location), excerpt)
        else:
            text = _bounded_text(target)
            start, end = location.get("start_line"), location.get("end_line")
            lines = text.splitlines()
            if location.get("kind") != "text_lines" or location.get("sha256") != sha(target):
                raise ValueError("separate text disclosure needs current text_lines path/hash")
            if any(isinstance(n, bool) or not isinstance(n, int) for n in (start, end)) or not 1 <= start <= end <= len(lines):
                raise ValueError("separate disclosure line range does not exist")
            if excerpt not in normalized(" ".join(lines[start - 1:end])):
                raise ValueError("AI disclosure is absent from the declared upload location")
            verified = {**location, "verified": True}
    else:
        raise ValueError("AI disclosure placement must be manuscript or separate_upload")
    return {"placement": value["placement"], "verified_location": verified,
            "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest()}


def audit(project: Path, pid: str, *, now: datetime | None = None) -> dict:
    result = {"schema_version": "1.0", "paper_id": pid, "status": "blocked", "errors": [],
              "inputs": {}, "policy": {"status": "not_evaluated", "blocking": False,
                  "reason": "Journal AI policy is excluded by the recorded user instruction."},
              "statement": None, "implementation": _implementation(), **LIMITS}
    try:
        paper = _paper(project, pid)
        venue_path = path_in(project, f"papers/{pid}/venue.json")
        disclosure_path = path_in(project, f"papers/{pid}/disclosures.json")
        _object(venue_path)
        disclosure = _object(disclosure_path)
        result["inputs"] = {"venue_sha256": sha(venue_path), "disclosures_sha256": sha(disclosure_path)}
        _usage(disclosure.get("ai_use"))
        policy = disclosure.get("ai_policy")
        statements = [policy.get("statement") if isinstance(policy, dict) else None,
                      disclosure.get("statement")]
        for statement in statements:
            if statement is not None:
                result["statement"] = _statement(paper, statement)
        result["status"] = "pass"
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ImportError, RuntimeError, IndexError) as exc:
        result["errors"].append(str(exc))
    return result


def refresh(project: Path, pid: str) -> dict:
    if os.environ.get("GITHUB_ACTIONS") != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("publication disclosure refresh requires authorized cloud execution")
    value = audit(project, pid)
    target = path_in(project, f"{PREFIX}/{pid}/latest.json", exists=False)
    value["execution"] = {"mode": "cloud", "receipt_id": str(os.environ.get("GITHUB_RUN_ID") or
        os.environ.get("DR_OS_CLOUD_EXECUTION_RECEIPT_ID") or "authorized-cloud")}
    write(target, value)
    output_provenance.record_model_writes(project, [target], family="other", provider=PROVIDER,
        model="scripts/publication_disclosure.py", role="disclosure-audit", run_id="disclosure-refresh")
    return value


def integrity_errors(project: Path, pid: str) -> list[str]:
    """Existing internal usage must be truthful; manuscript statements are optional."""
    try:
        if not isinstance(pid, str) or not re.fullmatch(r"P[0-9]{2}", pid):
            raise ValueError("internal usage needs an exact paper ID")
        target = project / "papers" / pid / "disclosures.json"
        if target.is_file():
            _usage(_object(target).get("ai_use"))
        return []
    except (OSError, ValueError, TypeError, KeyError) as exc:
        return [str(exc)]


def validate_saved_report(project: Path, pid: str) -> list[str]:
    try:
        target = path_in(project, f"{PREFIX}/{pid}/latest.json")
        saved = read(target)
        origin = output_provenance.current_origin(project, target)
        if origin.get("status") != "tracked" or origin.get("provider") != PROVIDER or origin.get("family") != "other":
            raise ValueError("publication disclosure audit lacks protected control-plane provenance")
        if saved.get("execution", {}).get("mode") != "cloud" or not saved["execution"].get("receipt_id"):
            raise ValueError("publication disclosure audit lacks cloud execution identity")
        current = audit(project, pid)
        errors = current["errors"][:]
        if any(saved.get(key) != value for key, value in current.items()):
            errors.append("publication disclosure audit is stale or differs from current source verification")
        return errors
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return [str(exc)]


def review_binding(project: Path, pid: str) -> dict:
    if not isinstance(pid, str) or not re.fullmatch(r"P[0-9]{2}", pid):
        raise ValueError("publication disclosure needs a valid paper ID")
    target = path_in(project, f"{PREFIX}/{pid}/latest.json", exists=False)
    return {"path": target.relative_to(project).as_posix(), "sha256": sha(target) if target.is_file() else None,
            "implementation": _implementation()}


def prompt_feedback(project: Path, pid: str) -> dict:
    """Small structured feedback about actual usage and declared statement sources."""
    value = audit(project, pid)
    return {"status": value["status"], "errors": value["errors"],
            "requirement": (value.get("policy") or {}).get("requirement"),
            "report": f"{PREFIX}/{pid}/latest.json", "human_policy_review_required": False,
            "independent_policy_and_source_review_required": False,
            "journal_ai_policy_evaluated": False,
            "manuscript_label_added": False, "watermark_scan_can_waive_disclosure": False,
            "input_contract": "Existing ai_use records may contain actual tools, purposes and human oversight, including none or unknown; missing records do not require a new declaration or approval. A declared statement may be recorded as statement (legacy ai_policy.statement remains supported), with placement manuscript|separate_upload, excerpt, and hash-bound location. Journal AI policy is not a gate.",
            "instruction": "Record actual assistance and oversight truthfully. AI-use statements are optional author-editable text; retain truthful internal usage/provenance records. Verify statements only when the author currently declares them. Do not invent author consent or add blanket AI-generated branding. Journal AI policy is excluded by user instruction; detector results cannot falsify provenance."}
