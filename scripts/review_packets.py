"""Protected internal blind/visual review; no calls, approvals or inferred scores."""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from scripts import output_provenance
from scripts.research_artifacts import path_in, read, sha, write, record

INPUT = "program/review-packets.json"
ROOT = Path(__file__).resolve().parents[1]
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
CHECKS = {"math_symbols", "final_size_readability", "color_vision", "statistical_labels", "Word_complex_content"}
RENDERERS = {"cloud_runtime": ("cloud_runtime.py", "cloud-tex-renderer"),
             "publication_figures": ("publication_figures.py", "publication-figure-renderer")}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("packet/case ID must be a safe lower-case identifier")
    return value


def text(value, label, limit=2000):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= limit:
        raise ValueError(f"{label} needs bounded non-empty text")
    return value.strip()


def source(project, value, locator=True):
    if not isinstance(value, dict) or not isinstance(value.get("path"), str):
        raise ValueError("source needs path/hash")
    target = path_in(project, value["path"])
    if target.stat().st_size > 32 * 1024 * 1024 or sha(target) != value.get("sha256"):
        raise ValueError(f"review source stale or oversized: {value['path']}")
    result = {"path": value["path"], "sha256": sha(target)}
    if locator:
        result["locator"] = text(value.get("locator"), "source locator")
    return result


def rubric(value):
    if not isinstance(value, dict) or set(value) != {"dimensions", "critical_errors"}:
        raise ValueError("rubric needs dimensions and critical_errors")
    for field in ("dimensions", "critical_errors"):
        rows = value[field]
        if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
            raise ValueError("rubric needs 1-32 dimensions and critical errors")
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("rubric item must be an object")
            key = identifier(row.get("id"))
            if key in seen:
                raise ValueError("duplicate rubric criterion")
            seen.add(key)
            if field == "critical_errors":
                if set(row) != {"id", "criterion"}:
                    raise ValueError("critical error needs id/criterion")
                text(row["criterion"], "critical error")
                continue
            if set(row) != {"id", "description", "value_type", "min", "max"} or not isinstance(row["value_type"], str) or row["value_type"] not in {"integer", "number"}:
                raise ValueError("dimension needs id/description/value_type/min/max")
            text(row["description"], "dimension description")
            for endpoint in (row["min"], row["max"]):
                if isinstance(endpoint, bool) or not isinstance(endpoint, (int, float)) or not math.isfinite(endpoint):
                    raise ValueError("rubric bounds must be finite")
                if row["value_type"] == "integer" and not isinstance(endpoint, int):
                    raise ValueError("integer rubric needs integer bounds")
            if row["min"] >= row["max"]:
                raise ValueError("rubric bounds are reversed")
    return value


def plan(project):
    target = path_in(project, INPUT)
    value = read(target)
    if value.get("schema_version") != "1.0" or not isinstance(value.get("packets"), list) or not 1 <= len(value["packets"]) <= 64:
        raise ValueError("review plan needs schema 1.0 and 1-64 packets")
    seen = set()
    for packet in value["packets"]:
        if not isinstance(packet, dict) or not isinstance(packet.get("kind"), str) or packet.get("kind") not in {"calibration", "visual"}:
            raise ValueError("review kind must be calibration or visual")
        key = identifier(packet.get("id"))
        if key in seen:
            raise ValueError("duplicate packet ID")
        seen.add(key)
        rubric(packet.get("rubric"))
    return value, {"path": INPUT, "sha256": sha(target)}


def base(project, packet_id):
    return path_in(project, f"reports/review-packets/{identifier(packet_id)}/manifest.json", exists=False).parent


def label(seed, *values):
    return hmac.new(bytes.fromhex(seed), "\0".join(values).encode(), hashlib.sha256).hexdigest()[:20]


def plain(project, bound, hidden=()):
    target = path_in(project, bound["path"])
    if target.suffix.lower() not in {".txt", ".md"} or target.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("blind evidence/candidates must be bounded UTF-8 text without provider payload metadata")
    payload = target.read_bytes()
    value = payload.decode("utf-8")
    if not value.strip() or any(term and term.casefold() in value.casefold() for term in hidden):
        raise ValueError("blind text is empty or exposes model/channel/price/source filename; do not rewrite scientific facts to hide clues")
    return payload


def calibration(project, packet, seed):
    cases = packet.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
        raise ValueError("calibration needs 1-200 cases")
    dependencies, roster, key, copies, seen = [], [], [], [], set()
    # Immutable version directories retain old/failed candidate texts when a
    # later plan changes its roster; stable labels still depend only on IDs.
    version = digest(packet)[:20]
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("case must be an object")
        case_id = identifier(case.get("id"))
        if case_id in seen:
            raise ValueError("duplicate case ID")
        seen.add(case_id)
        sources, candidates = case.get("sources"), case.get("candidates")
        if not isinstance(sources, list) or not sources or not isinstance(candidates, list) or not 1 <= len(candidates) <= 20:
            raise ValueError("case needs evidence and every candidate attempt")
        evidence = [source(project, row) for row in sources]
        dependencies.extend(evidence)
        case_label = label(seed, "case", case_id)
        evidence_names = []
        for index, bound in enumerate(evidence):
            name = f"materials/{version}/{case_label}/evidence-{index + 1}.txt"
            copies.append((name, plain(project, bound, [bound["path"], Path(bound["path"]).name]), bound))
            evidence_names.append(name)
        candidate_ids = set()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError("candidate must be an object")
            candidate_id = identifier(candidate.get("id"))
            if candidate_id in candidate_ids:
                raise ValueError("duplicate candidate attempt")
            candidate_ids.add(candidate_id)
            if candidate.get("authorized_for_internal_review") is not True:
                raise ValueError("candidate needs explicit internal read-only authorization")
            text(candidate.get("authorization_note"), "authorization note")
            author = text(candidate.get("author_id"), "candidate author", 128)
            status = candidate.get("status")
            if not isinstance(status, str) or status not in {"success", "failed"}:
                raise ValueError("candidate status must preserve success/failed")
            candidate_label = label(seed, "candidate", case_id, candidate_id)
            row = {"case_label": case_label, "candidate_label": candidate_label, "status": status,
                   "evidence": evidence_names, "internal_read_only": True}
            origin = {"status": "no_artifact_failed_attempt"}
            if status == "success" or candidate.get("artifact") is not None:
                bound = source(project, candidate.get("artifact"))
                dependencies.append(bound)
                hidden = [bound["path"], Path(bound["path"]).name]
                for field in ("model", "channel"):
                    value = candidate.get(field, "")
                    if not isinstance(value, str):
                        raise ValueError("model/channel metadata must be strings")
                    hidden.append(value)
                if "price_cny" in candidate:
                    price = candidate["price_cny"]
                    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price < 0:
                        raise ValueError("recorded price must be finite CNY")
                    hidden.extend((f"CNY {price}", f"¥{price}"))
                name = f"materials/{version}/{case_label}/candidate-{candidate_label}.txt"
                copies.append((name, plain(project, bound, hidden), bound))
                row["artifact"] = name
                origin = output_provenance.current_origin(project, path_in(project, bound["path"]))
            if status == "failed":
                text(candidate.get("failure_reason"), "failure reason")
                failure = source(project, candidate.get("failure_receipt"))
                dependencies.append(failure)
            roster.append(row)
            key.append({"case_id": case_id, "candidate_id": candidate_id, "case_label": case_label,
                        "candidate_label": candidate_label, "candidate": candidate, "author_id": author,
                        "original_provenance": origin, "sources": evidence})
    if len(copies) > 1000 or sum(len(row[1]) for row in copies) > 32 * 1024 * 1024:
        raise ValueError("blind material limits exceeded")
    roster.sort(key=lambda row: (row["case_label"], row["candidate_label"]))
    return dependencies, roster, key, copies


def render_dependencies(project, value, sources, artifact, previews):
    bound = source(project, value)
    target = path_in(project, bound["path"])
    receipt = read(target)
    renderer = receipt.get("renderer")
    if not isinstance(renderer, dict) or not isinstance(renderer.get("name"), str) or renderer.get("name") not in RENDERERS:
        raise ValueError("visual relation requires a controlled renderer")
    script, provider = RENDERERS[renderer["name"]]
    if renderer.get("implementation_sha256") != sha(ROOT / "scripts" / script):
        raise ValueError("render implementation changed; render and review again")
    origin = output_provenance.current_origin(project, target)
    if (origin.get("status") != "tracked" or origin.get("family") != "other"
            or origin.get("provider") != provider or origin.get("role") != "render-receipt"):
        raise ValueError("visual render receipt needs current protected executor provenance")
    execution = receipt.get("execution")
    if (receipt.get("schema_version") != "1.0" or receipt.get("status") != "pass"
            or not isinstance(execution, dict) or execution.get("mode") != "cloud"
            or not isinstance(execution.get("receipt_id"), str) or not execution["receipt_id"].strip()):
        raise ValueError("render receipt requires a passing identified cloud execution")
    if not isinstance(receipt.get("inputs"), list) or not isinstance(receipt.get("outputs"), list):
        raise ValueError("render receipt needs actual inputs/outputs")
    inputs = [source(project, row, False) for row in receipt["inputs"]]
    outputs = [source(project, row, False) for row in receipt["outputs"]]
    left = {(row["path"], row["sha256"]) for row in inputs}
    right = {(row["path"], row["sha256"]) for row in outputs}
    if any((row["path"], row["sha256"]) not in left for row in sources):
        raise ValueError("review source is absent from actual render inputs")
    if any((row["path"], row["sha256"]) not in right for row in [artifact, *previews]):
        raise ValueError("review artifact/preview is absent from actual render outputs")
    return [bound, *inputs, *outputs]


def visual(project, packet):
    rows = packet.get("artifacts")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise ValueError("visual packet needs 1-200 actual outputs")
    dependencies, roster, seen = [], [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("visual artifact must be an object")
        key = identifier(row.get("id"))
        if key in seen:
            raise ValueError("duplicate visual artifact")
        seen.add(key)
        artifact = source(project, row.get("artifact"))
        extension = Path(artifact["path"]).suffix.lower()
        if extension not in {".docx", ".pdf", ".svg", ".png", ".tif", ".tiff"}:
            raise ValueError("visual review needs an actual figure/document")
        if not isinstance(row.get("sources"), list) or not row["sources"] or not isinstance(row.get("previews"), list) or not row["previews"]:
            raise ValueError("visual packet needs live sources and actual rendered previews")
        sources = [source(project, item) for item in row["sources"]]
        previews = [source(project, item) for item in row["previews"]]
        if any(Path(item["path"]).suffix.lower() not in {".pdf", ".png", ".svg", ".tif", ".tiff"} for item in previews):
            raise ValueError("previews must be actual visual files")
        qa = source(project, row.get("qa_report"))
        qa_value = read(path_in(project, qa["path"]))
        if qa_value.get("status") not in {"pass", "review_required"} or qa_value.get("errors"):
            raise ValueError("actual output QA must pass mechanical checks or await explicit visual inspection")
        qa_origin = output_provenance.current_origin(project, project / qa["path"])
        if qa_origin.get("status") != "tracked" or qa_origin.get("family") != "other" or qa_origin.get("provider") not in {"publication-figure-renderer", "cloud-tex-renderer", "deterministic-control-plane"}:
            raise ValueError("visual QA report lacks current protected control-plane provenance")
        checks = row.get("checklist")
        required = {"math_symbols", "final_size_readability", "statistical_labels", "Word_complex_content" if extension == ".docx" else "color_vision"}
        if (not isinstance(checks, list) or any(not isinstance(item, str) for item in checks)
                or len(checks) != len(set(checks)) or set(checks) - CHECKS or not required <= set(checks)):
            raise ValueError("visual checklist omits applicable required checks")
        render_inputs = render_dependencies(project, row.get("render_receipt"), sources, artifact, previews)
        dependencies.extend([artifact, *sources, *previews, qa, *render_inputs])
        roster.append({"artifact_id": key, "artifact": artifact, "sources": sources, "previews": previews,
                       "qa_report": qa, "render_receipt": render_inputs[0], "required_checklist": checks})
    return dependencies, roster, [], []


def build(project, packet, bound_plan, seed):
    dependencies, roster, private, copies = calibration(project, packet, seed) if packet["kind"] == "calibration" else visual(project, packet)
    bound = {(row["path"], row["sha256"]): row for row in [bound_plan, *dependencies]}
    result = {"schema_version": "1.0", "id": packet["id"], "kind": packet["kind"],
              "packet_definition_sha256": digest(packet), "rubric": packet["rubric"], "rubric_sha256": digest(packet["rubric"]),
              "dependencies": sorted(bound.values(), key=lambda row: row["path"]), "roster": roster,
              "materials": [{"path": name, "sha256": hashlib.sha256(payload).hexdigest()} for name, payload, _ in copies],
              "internal_read_only": True, "calibration_status": "NOT_CALIBRATED", "gate_approved": False,
              "scientific_completion_verified": False, "blindness_verified": False, "rater_independence_verified": False}
    key = {"schema_version": "1.0", "id": packet["id"], "seed": seed, "packet_definition_sha256": digest(packet),
           "answer_key": private, "internal_read_only": True}
    return result, key, copies


def refresh(project: Path) -> dict:
    document, bound = plan(project)
    packets, errors, metadata = [], [], []
    for packet in document["packets"]:
        directory = base(project, packet["id"])
        answer_path = path_in(project, f"reports/review-packets/{packet['id']}/answer-key.json", exists=False)
        manifest_path = path_in(project, f"reports/review-packets/{packet['id']}/manifest.json", exists=False)
        try:
            previous = read(answer_path) if answer_path.is_file() else {}
            seed = previous.get("seed") or secrets.token_hex(32)
            if not isinstance(seed, str) or not re.fullmatch(r"[a-f0-9]{64}", seed):
                raise ValueError("protected seed is malformed")
            manifest, answer, copies = build(project, packet, bound, seed)
            for name, payload, original in copies:
                target = path_in(project, f"reports/review-packets/{packet['id']}/{name}", exists=False)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(payload)
                origin = output_provenance.current_origin(project, path_in(project, original["path"]))
                output_provenance.record_model_writes(project, [target], family=origin.get("family", "other"),
                    provider=origin.get("provider", "deterministic-internal-copy"), model=origin.get("model", "scripts/review_packets.py"),
                    role="internal-read-only-review-copy", run_id="review-packet-refresh")
            write(answer_path, answer)
            index = path_in(project, f"reports/review-packets/{packet['id']}/materials/index.json", exists=False)
            write(index, {"schema_version": "1.0", "kind": packet["kind"], "rubric": packet["rubric"],
                          "cases": manifest["roster"] if packet["kind"] == "calibration" else [], "internal_read_only": True})
            manifest.update(answer_key_sha256=sha(answer_path), reviewer_index_sha256=sha(index))
            write(manifest_path, manifest)
            archive_value = {"manifest": manifest, "answer_key": answer, "internal_read_only": True}
            archive = path_in(project, f"reports/review-packets/{packet['id']}/history/{digest(archive_value)}.json", exists=False)
            if archive.is_file() and read(archive) != archive_value:
                raise ValueError("immutable review history changed")
            if not archive.is_file():
                write(archive, archive_value)
            metadata.append(archive)
            metadata.extend([answer_path, manifest_path, index])
            packets.append({"id": packet["id"], "kind": packet["kind"], "status": "prepared", "manifest_sha256": sha(manifest_path)})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            errors.append(f"{packet['id']}: {exc}")
            packets.append({"id": packet["id"], "kind": packet["kind"], "status": "blocked", "error": str(exc)})
        attempts = path_in(project, f"reports/review-packets/{packet['id']}/refresh-attempts.jsonl", exists=False)
        attempts.parent.mkdir(parents=True, exist_ok=True)
        with attempts.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "input_sha256": bound["sha256"],
                                     "result": packets[-1]}, sort_keys=True) + "\n")
        metadata.append(attempts)
    result = {"schema_version": "1.0", "status": "pass" if not errors else "fail", "errors": errors, "packets": packets,
              "calibration_status": "NOT_CALIBRATED", "gate_approved": False, "scientific_completion_verified": False}
    report = project / "reports/review-packets.json"
    write(report, result)
    record(project, [*metadata, report], "scripts/review_packets.py")
    return result


def review_snapshot(project: Path, packet_id: str) -> dict:
    document, bound = plan(project)
    matches = [packet for packet in document["packets"] if packet["id"] == packet_id]
    if len(matches) != 1:
        raise ValueError("select one current review packet")
    directory = base(project, packet_id)
    saved = read(path_in(project, f"reports/review-packets/{packet_id}/manifest.json"))
    answer = read(path_in(project, f"reports/review-packets/{packet_id}/answer-key.json"))
    current, current_answer, _ = build(project, matches[0], bound, answer["seed"])
    if answer != current_answer or saved.get("answer_key_sha256") != sha(directory / "answer-key.json"):
        raise ValueError("answer key or original provenance changed")
    if any(saved.get(key) != value for key, value in current.items()):
        raise ValueError("packet/source changed; refresh and re-review")
    for row in current["materials"]:
        if sha(path_in(project, f"reports/review-packets/{packet_id}/{row['path']}")) != row["sha256"]:
            raise ValueError("blind material changed")
    index = path_in(project, f"reports/review-packets/{packet_id}/materials/index.json")
    if saved.get("reviewer_index_sha256") != sha(index):
        raise ValueError("reviewer index changed")
    result = {"schema_version": "1.0", "packet_id": packet_id, "kind": saved["kind"],
              "manifest": {"path": f"reports/review-packets/{packet_id}/manifest.json", "sha256": sha(directory / "manifest.json")},
              "rubric": saved["rubric"], "rubric_sha256": saved["rubric_sha256"], "roster": saved["roster"],
              "dependencies": saved["dependencies"], "materials": saved["materials"],
              "answer_key_sha256": saved["answer_key_sha256"], "reviewer_index_sha256": sha(index),
              "calibration_status": "NOT_CALIBRATED", "gate_approved": False, "scientific_completion_verified": False}
    result["snapshot_sha256"] = digest(result)
    return result


def judgments_checked(project, packet_id, value):
    snapshot = review_snapshot(project, packet_id)
    if not isinstance(value, dict) or value.get("independent") is not True:
        raise ValueError("independent named human rater declaration required")
    rater = text(value.get("rater_id"), "rater ID", 128)
    text(value.get("independence_note"), "independence disclosure")
    answer = read(path_in(project, f"reports/review-packets/{packet_id}/answer-key.json"))
    if rater.casefold() in {row["author_id"].casefold() for row in answer["answer_key"]}:
        raise ValueError("candidate author cannot independently rate themselves")
    if snapshot["kind"] == "calibration":
        rows = value.get("observations")
        if not isinstance(rows, list) or len(rows) != len(snapshot["roster"]):
            raise ValueError("rate every candidate, including failed attempts")
        expected = {(row["case_label"], row["candidate_label"]): row for row in snapshot["roster"]}
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("rating must be an object")
            if not isinstance(row.get("case_label"), str) or not isinstance(row.get("candidate_label"), str):
                raise ValueError("rating labels must be exact opaque strings")
            key = (row.get("case_label"), row.get("candidate_label"))
            if key not in expected or key in seen:
                raise ValueError("unknown/duplicate blinded rating")
            seen.add(key)
            text(row.get("rationale"), "rating rationale")
            if expected[key]["status"] == "failed":
                if row.get("status") != "unscorable_failed" or "ratings" in row or "critical_errors" in row:
                    raise ValueError("failed attempt requires unscorable disposition, never fabricated ratings")
                continue
            ratings, critical, frozen = row.get("ratings"), row.get("critical_errors"), snapshot["rubric"]
            if not isinstance(ratings, dict) or set(ratings) != {dimension["id"] for dimension in frozen["dimensions"]}:
                raise ValueError("ratings must exactly cover frozen dimensions")
            for dimension in frozen["dimensions"]:
                score = ratings[dimension["id"]]
                if (isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score)
                        or not dimension["min"] <= score <= dimension["max"]
                        or (dimension["value_type"] == "integer" and not isinstance(score, int))):
                    raise ValueError("rating violates typed rubric bounds")
            if not isinstance(critical, dict) or set(critical) != {item["id"] for item in frozen["critical_errors"]} or any(type(item) is not bool for item in critical.values()):
                raise ValueError("every critical-error criterion needs an exact boolean")
    else:
        rows = value.get("inspections")
        if not isinstance(rows, list) or len(rows) != len(snapshot["roster"]):
            raise ValueError("inspect every actual visual artifact")
        expected = {row["artifact_id"]: row for row in snapshot["roster"]}
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("artifact_id"), str) or row.get("artifact_id") not in expected or row["artifact_id"] in seen:
                raise ValueError("unknown/duplicate visual inspection")
            seen.add(row["artifact_id"])
            checks = row.get("checks")
            if not isinstance(checks, dict) or set(checks) != set(expected[row["artifact_id"]]["required_checklist"]) or any(type(item) is not bool for item in checks.values()):
                raise ValueError("visual checks must exactly cover required boolean checklist")
            text(row.get("note"), "inspection note")
    return snapshot


def create_confirmation(project: Path, packet_id: str, actor: str, judgments: dict) -> tuple[Path, dict]:
    """Prepare only; caller enforces owner authorization and whole-dossier hash."""
    actor = text(actor, "actor", 128)
    snapshot = judgments_checked(project, packet_id, judgments)
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", actor).strip("-")[:40] or "actor"
    filename = f"{safe}-{hashlib.sha256(actor.encode()).hexdigest()[:16]}.json"
    target = path_in(project, f"state/review-packet-confirmations/{identifier(packet_id)}/{filename}", exists=False)
    previous = read(target) if target.is_file() else {}
    if previous and (previous.get("schema_version") != "1.0" or previous.get("packet_id") != packet_id or previous.get("actor") != actor):
        raise ValueError("confirmation history identity changed")
    attempts = previous.get("attempts", [])
    if not isinstance(attempts, list):
        raise ValueError("confirmation attempts malformed")
    attempt = {"at": datetime.now(timezone.utc).isoformat(), "actor": actor,
               "snapshot_sha256": snapshot["snapshot_sha256"], "judgments": judgments}
    attempt["attempt_sha256"] = digest(attempt)
    return target, {"schema_version": "1.0", "packet_id": packet_id, "actor": actor, "attempts": [*attempts, attempt],
                    "calibration_status": "NOT_CALIBRATED", "gate_approved": False,
                    "scientific_completion_verified": False, "rater_independence_verified": False}


def validate_gate_reviews(project: Path) -> list[str]:
    """Declared visual packets require actual current human observations."""
    if not (project / INPUT).is_file():
        return []
    try:
        result = audit(project)
        return result["errors"] + [f"{packet['id']}: visual packet requires current passing human inspection"
            for packet in result["packets"] if packet["kind"] == "visual" and packet.get("visual_checklist_passed_by_human") is not True]
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return ["review packet validation failed: " + str(exc)]


def audit(project: Path) -> dict:
    document, _ = plan(project)
    packets, errors = [], []
    for packet in document["packets"]:
        row = {"id": packet["id"], "kind": packet["kind"], "confirmations": [], "review_status": "needs_human_review"}
        try:
            snapshot = review_snapshot(project, packet["id"])
            row["snapshot_sha256"] = snapshot["snapshot_sha256"]
            rater_ids, visual_observations = set(), []
            directory = project / "state/review-packet-confirmations" / packet["id"]
            for target in sorted(directory.glob("*.json")):
                receipt = read(path_in(project, target.relative_to(project).as_posix()))
                if (receipt.get("schema_version") != "1.0" or receipt.get("packet_id") != packet["id"]
                        or receipt.get("calibration_status") != "NOT_CALIBRATED" or receipt.get("gate_approved") is not False
                        or not isinstance(receipt.get("attempts"), list) or not receipt["attempts"]):
                    raise ValueError("human confirmation receipt malformed")
                attempts = []
                for attempt in receipt["attempts"]:
                    if not isinstance(attempt, dict) or attempt.get("actor") != receipt.get("actor"):
                        raise ValueError("human review attempt identity changed")
                    expected_hash = digest({key: value for key, value in attempt.items() if key != "attempt_sha256"})
                    if attempt.get("attempt_sha256") != expected_hash:
                        raise ValueError("human attempt integrity changed")
                    fresh = attempt.get("snapshot_sha256") == snapshot["snapshot_sha256"]
                    if fresh:
                        judgments_checked(project, packet["id"], attempt["judgments"])
                        rater_ids.add(attempt["judgments"]["rater_id"])
                        if packet["kind"] == "visual":
                            visual_observations.append(all(all(item["checks"].values()) for item in attempt["judgments"]["inspections"]))
                    attempts.append({"attempt_sha256": expected_hash, "current": fresh, "judgments": attempt["judgments"]})
                row["confirmations"].append({"path": target.relative_to(project).as_posix(), "sha256": sha(target), "attempts": attempts})
            row.update(status="pass", current_independent_rater_ids=sorted(rater_ids),
                       review_status="human_observations_recorded" if rater_ids else "needs_human_review",
                       visual_checklist_passed_by_human=bool(visual_observations) and all(visual_observations) if packet["kind"] == "visual" else None)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row.update(status="fail", error=str(exc))
            errors.append(f"{packet['id']}: {exc}")
        packets.append(row)
    return {"schema_version": "1.0", "status": "pass" if not errors else "fail", "errors": errors, "packets": packets,
            "calibration_status": "NOT_CALIBRATED", "gate_approved": False, "scientific_completion_verified": False}
