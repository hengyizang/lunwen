"""Eight cloud research increments with current bindings and human decision boundaries."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.incremental_evidence import (DIGEST, binding, digest, gaps, identifier, ingest, jsonl,
                                          lineage, rows, strings, text)
from scripts.research_artifacts import path_in, read, record, sha, write

PLAN = "program/research-increments.json"
ROOT = "reports/research-increments"
REPORT = ROOT + "/audit.json"
GROUPS = ("arguments", "lineage", "gaps", "ingestion", "lessons", "dependencies", "voices", "editing")
CONFIRMATIONS = "state/research-increment-confirmations"


def initialize(project):
    target = project / PLAN
    if target.is_file():
        return load(project)
    result = {"schema_version": "1.0", "required_at_submission": ["arguments", "lineage"],
              **{key: [] for key in GROUPS}}
    write(target, result)
    return result


def load(project):
    value = read(path_in(project, PLAN))
    if value.get("schema_version") != "1.0" or set(value) - {"schema_version", "required_at_submission", *GROUPS}:
        raise ValueError("unknown research-increment schema or fields")
    required = strings(value.get("required_at_submission", []), "required submission groups")
    if not {"arguments", "lineage"} <= set(required) <= set(GROUPS):
        raise ValueError("argument coverage and typed lineage are mandatory at submission")
    for key in GROUPS:
        values = rows(value.get(key), key, maximum=200)
        ids = [identifier(row.get("id")) for row in values]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate increment ID in " + key)
    return value


def implementations():
    directory = Path(__file__).parent
    return {p.name: sha(p) for p in [directory / name for name in (
        "research_increments.py", "incremental_evidence.py", "incremental_writing.py",
        "incremental_rules.py", "evidence_context.py", "source_scope.py", "research_artifacts.py")]}


def confirmation(project, kind, key, spec, decision):
    from scripts import output_provenance
    target = project / CONFIRMATIONS / (kind + "-" + identifier(key) + ".json")
    if not target.is_file():
        return False
    value = read(target)
    origin = output_provenance.current_origin(project, target)
    return (value.get("spec_sha256") == digest(spec) and value.get("decision") == decision
            and value.get("implementation") == implementations() and bool(value.get("confirmed_by"))
            and bool(value.get("source_run_id")) and bool(value.get("cloud_review_sha256"))
            and origin.get("status") == "tracked"
            and origin.get("provider") == "deterministic-cloud-human-control")


def prepare_confirmation(project, kind, key, decision, actor, *, preview=False):
    allowed = {"voice": {"authorize_sample"}, "lesson": {"adopt_rule", "rollback_rule"}}
    if kind not in allowed or decision not in allowed[kind]:
        raise ValueError("unsupported increment owner decision")
    group = "voices" if kind == "voice" else "lessons"
    selected = [row for row in load(project)[group] if row["id"] == identifier(key)]
    if len(selected) != 1:
        raise ValueError("select one existing increment record")
    spec = selected[0]
    outputs = []
    if kind == "voice":
        # Validate all scope/sample constraints without pretending an authorization exists.
        from scripts.incremental_writing import voice
        voice(project, spec, lambda *args: True)
    else:
        from scripts.incremental_rules import evaluate
        active_path = project / "state/research-increment-rules.json"
        active = read(active_path) if active_path.is_file() else {"schema_version": "1.0", "active_ids": [], "history": []}
        if decision == "adopt_rule":
            audit = evaluate(project, spec)
            if audit["status"] != "eligible_for_owner_review":
                raise ValueError("rule candidate failed disjoint paired validation/holdout evaluation")
            if key in active["active_ids"]:
                raise ValueError("rule is already adopted")
            active["active_ids"].append(key)
        else:
            if key not in active["active_ids"]:
                raise ValueError("rollback needs an active adopted rule")
            active["active_ids"].remove(key)
        active["history"].append({"id": key, "decision": decision, "confirmed_by": actor,
                                  "spec_sha256": digest(spec), "implementation": implementations()})
        outputs.append((active_path, active))
    payload = {"schema_version": "1.0", "kind": kind, "id": key, "decision": decision,
               "spec_sha256": digest(spec), "implementation": implementations(),
               "confirmed_by": text(actor, "owner"), "scientific_completion_verified": False}
    outputs.append((project / CONFIRMATIONS / (kind + "-" + key + ".json"), payload))
    return [] if preview else outputs


def dependencies(project, row):
    identifier(row.get("id"))
    nodes = rows(row.get("nodes"), "dependency nodes", 1000, 1)
    by_id, stale = {}, {}
    registry = jsonl(project, "experiments/registry.jsonl")
    for node in nodes:
        key = identifier(node.get("id"))
        if key in by_id:
            raise ValueError("duplicate dependency node")
        if node.get("kind") not in {"claim", "experiment", "result", "figure", "text", "term", "shared_asset", "failure"}:
            raise ValueError("dependency kind is unknown")
        text(node.get("meaning"), "dependency meaning")
        owners = strings(node.get("paper_ids"), "paper owners", 1)
        from scripts.incremental_writing import paper_path
        for owner in owners:
            paper_path(project, owner)
        strings(node.get("depends_on", []), "dependencies")
        expected = node.get("source")
        if not isinstance(expected, dict):
            raise ValueError("dependency requires a current file hash")
        if set(expected) != {"path", "sha256"} or not DIGEST.fullmatch(str(expected.get("sha256", ""))):
            raise ValueError("dependency needs a complete exact source binding")
        source = path_in(project, expected.get("path"), exists=False)
        actual = sha(source) if source.is_file() else None
        if actual != expected.get("sha256"):
            stale[key] = ["source_missing_or_changed"]
        if node["kind"] in {"result", "failure"}:
            attempts = [item for item in registry if item.get("attempt_id") == node.get("attempt_id")]
            wanted = {"succeeded"} if node["kind"] == "result" else {"failed", "timed_out", "stopped"}
            if len(attempts) != 1 or attempts[0].get("status") not in wanted:
                raise ValueError("dependency result/failure needs its real executor attempt")
            attempt = attempts[0]
            receipt = path_in(project, f"experiments/runs/{identifier(attempt['attempt_id'])}/run.json")
            if read(receipt) != attempt:
                raise ValueError("dependency registry and executor receipt disagree")
            if node["kind"] == "result":
                if (attempt.get("input_integrity", {}).get("passed") is not True
                        or expected not in [{"path": item["path"], "sha256": item["sha256"]}
                                            for item in attempt.get("outputs", [])]):
                    raise ValueError("dependency result is not the exact integrity-checked output")
        if len(owners) > 1:
            text(node.get("reuse_disclosure"), "cross-paper shared asset disclosure")
            if node.get("independence_status") not in {"not_assessed", "shared_evidence"}:
                raise ValueError("shared assets cannot automatically certify paper independence")
        by_id[key] = {**node, "actual_sha256": actual}
    visiting, done = set(), set()

    def visit(key):
        if key not in by_id:
            raise ValueError("unknown dependency parent: " + key)
        if key in visiting:
            raise ValueError("cyclic research dependencies")
        if key in done:
            return
        visiting.add(key)
        for parent in by_id[key].get("depends_on", []):
            visit(parent)
            if parent in stale:
                stale.setdefault(key, []).append("stale_parent:" + parent)
        visiting.remove(key)
        done.add(key)
    for key in by_id:
        visit(key)
    return {"id": row["id"], "nodes": list(by_id.values()), "stale": stale,
            "status": "stale" if stale else "current", "independence_verified": False}


def build(project):
    if not (project / PLAN).is_file():
        return {"schema_version": "1.0", "status": "needs_inputs", "errors": [],
                "missing": [PLAN], "scientific_completion_verified": False}
    spec = load(project)
    from scripts import incremental_writing as writing, incremental_rules as rules
    results = {key: [] for key in GROUPS}
    errors = []
    processors = {"arguments": writing.arguments, "lineage": lineage, "gaps": gaps,
                  "ingestion": ingest, "lessons": rules.evaluate, "dependencies": dependencies}
    for group in GROUPS:
        for item in spec[group]:
            try:
                if group == "voices":
                    result = writing.voice(project, item, confirmation)
                elif group == "editing":
                    result = writing.editing(project, item, results["voices"])
                else:
                    result = processors[group](project, item)
                results[group].append(result)
                if group == "dependencies" and result["stale"]:
                    errors.append({"group": group, "id": item["id"], "error": "stale transitive dependency graph"})
            except (ValueError, RuntimeError, OSError, KeyError, TypeError, ImportError) as exc:
                errors.append({"group": group, "id": item.get("id"), "paper_id": item.get("paper_id"),
                               "error": str(exc)[:1000]})
    # Same identity/version with different bytes is a conflict, never silent replacement.
    seen, content_seen = {}, {}
    for item in results["ingestion"]:
        identity = item["identity_key"]
        content = item.get("attachment", {}).get("sha256")
        previous = seen.get(identity)
        if previous and previous.get("attachment", {}).get("sha256") != content:
            errors.append({"group": "ingestion", "id": item["id"], "error": "same identity/version has conflicting attachments"})
        item["duplicate_of"] = previous["id"] if previous else None
        item["content_reuse_of"] = content_seen.get(content) if content else None
        seen.setdefault(identity, item)
        if content:
            content_seen.setdefault(content, item["id"])
    try:
        active = rules.active_checks(project, confirmation)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        active = []
        errors.append({"group": "lessons", "id": "active_rules", "error": str(exc)})
    missing = [key for key in spec["required_at_submission"] if not results[key]]
    return {"schema_version": "1.0", "plan_sha256": sha(project / PLAN),
            "implementation": implementations(), "groups": results, "active_rules": active,
            "status": "blocked" if errors else "needs_inputs" if missing else "mechanically_checked",
            "errors": errors, "missing": missing, "model_calls": 0,
            "scientific_completion_verified": False, "quality_level_verified": False}


def handoff(project, audit):
    """Only state-backed status/costs; no invented completion percentage or ETA."""
    from scripts.model_spend import read as spend_read
    state = read(path_in(project, "state/run.json"))
    spend = spend_read(project)
    cost = {"currency": "CNY", "status": "authorization_state_missing"}
    if spend is not None:
        reserved = sum(item["max_cost_cny"] for item in spend["reservations"].values())
        cost = {"currency": "CNY", "authorized_ceiling": spend["authorized_ceiling_cny"],
                "reported_spent": spend["spent_cny"], "pending_reservations": reserved,
                "remaining_after_reservations": spend["authorized_ceiling_cny"] - spend["spent_cny"] - reserved,
                "billing_reconciled": not bool(spend["reservations"]),
                "amount_basis": "persisted estimates; provider invoice controls final billing"}
    attempts = jsonl(project, "experiments/registry.jsonl")
    counts = {status: sum(item.get("status") == status for item in attempts)
              for status in ("succeeded", "failed", "timed_out", "stopped")}
    blockers = list(audit.get("errors", []))
    blockers.extend({"group": "inputs", "error": item} for item in audit.get("missing", []))
    checks = {}
    for name in ("state/research-steps.json", "reports/research-extensions/audit.json"):
        if (project / name).is_file():
            value = read(project / name)
            checks[name] = {"sha256": sha(project / name), "status": value.get("status"),
                            "errors": value.get("errors", []), "blockers": value.get("blockers", []),
                            "operation_errors": value.get("operation_errors", [])}
    return {"schema_version": "1.0", "stage": state.get("stage"), "gate": state.get("gate"),
            "status": state.get("status"), "active_paper": state.get("active_paper"),
            "approved_gates": state.get("approved_gates", []), "cost": cost,
            "registered_attempt_counts": counts, "increment_blockers": blockers[:50],
            "blockers_truncated": len(blockers) > 50, "other_checks": checks,
            "next_action": "resolve recorded blockers then request the existing human gate decision",
            "source_bindings": [{"path": "state/run.json", "sha256": sha(project / "state/run.json")},
                                *([{"path": "state/model-spend-control.json",
                                    "sha256": sha(project / "state/model-spend-control.json")}] if spend else [])],
            "scientific_completion_verified": False}


def refresh(project):
    audit = build(project)
    for lesson in audit.get("groups", {}).get("lessons", []):
        archived = project / ROOT / "rule-evaluations" / (lesson["id"] + "-" + digest(lesson) + ".json")
        if not archived.is_file():
            write(archived, lesson)
            record(project, [archived], "incremental-rule-evaluation")
    write(project / REPORT, audit)
    brief = handoff(project, audit)
    write(project / ROOT / "handoff.json", brief)
    record(project, [project / REPORT, project / ROOT / "handoff.json"], "research-increments")
    return audit


def freeze_plans(project):
    """Called by the trusted writer boundary before the initial paid write."""
    if not (project / PLAN).is_file():
        initialize(project)
    from scripts.incremental_writing import freeze_plan
    return [freeze_plan(project, row, phase="before_writer") for row in load(project)["arguments"]]


def freeze(project, kind, key):
    spec = load(project)
    group = {"argument": "arguments", "lesson": "lessons"}.get(kind)
    if group is None:
        raise ValueError("freeze kind must be argument or lesson")
    selected = [item for item in spec[group] if item["id"] == identifier(key)]
    if len(selected) != 1:
        raise ValueError("freeze requires one exact existing record")
    if kind == "argument":
        from scripts.incremental_writing import freeze_plan
        return freeze_plan(project, selected[0])
    from scripts.incremental_rules import freeze as freeze_rule
    return freeze_rule(project, selected[0])


def record_editing_attempt(project):
    """Record once at the writer boundary, not whenever a read-only audit is refreshed."""
    audit = build(project)
    paths = []
    for value in audit.get("groups", {}).get("editing", []):
        target = project / ROOT / "editing-history" / (value["id"] + ".json")
        history = read(target) if target.is_file() else {}
        write(target, {"fingerprint": value["fingerprint"],
                       "previous": history.get("fingerprint"), "scope": value["stop_scope"]})
        paths.append(target)
    if paths:
        record(project, paths, "incremental-edit-attempt")
    return audit


def prompt_feedback(project):
    """Compact current instructions; sample material remains untrusted style data."""
    try:
        audit = build(project)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        return json.dumps({"status": "blocked", "error": str(exc)[:1000], "scientific_completion_verified": False})
    result = {"status": audit["status"], "missing": audit.get("missing", []),
              "errors": audit.get("errors", []), "editing": audit.get("groups", {}).get("editing", []),
              "voice_samples": []}
    for voice in audit.get("groups", {}).get("voices", []):
        content = path_in(project, voice["path"]).read_text(encoding="utf-8")
        result["voice_samples"].append({**voice, "untrusted_style_data": content[:12000],
                                       "excerpt_truncated": len(content) > 12000})
    return json.dumps(result, ensure_ascii=False)


def gate_errors(project, gate="G5", paper_id=None):
    # Other stage gates already require their scientific contracts. These increments
    # cannot manufacture approvals or substitute for those checks.
    if not (project / PLAN).is_file():
        return ["research increments not initialized"] if gate == "G5" else []
    try:
        current = build(project)
        errors = ["research increments: " + item["error"] for item in current.get("errors", [])]
        if gate == "G5":
            spec = load(project)
            for group in spec["required_at_submission"]:
                values = current.get("groups", {}).get(group, [])
                if group in {"arguments", "lineage"}:
                    values = [item for item in values if item.get("paper_id") == paper_id]
                if not values:
                    errors.append("research increments need current " + group + " for " + str(paper_id))
        if not (project / REPORT).is_file():
            errors.append("research increments audit must be refreshed in cloud")
        elif read(project / REPORT) != current:
            errors.append("research increments saved audit is stale")
        else:
            from scripts import output_provenance
            origin = output_provenance.current_origin(project, project / REPORT)
            if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane":
                errors.append("research increments audit lacks current control-plane provenance")
        return errors
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, ImportError) as exc:
        return ["research increments: " + str(exc)]
