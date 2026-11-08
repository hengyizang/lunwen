"""Eight cloud research increments with current bindings and human decision boundaries."""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts.incremental_evidence import (DIGEST, digest, gaps, identifier, ingest, lineage, primary_attempts, rows, strings, text)
from scripts.research_artifacts import path_in, read, record, sha, write

PLAN = "program/research-increments.json"
ROOT = "reports/research-increments"
REPORT = ROOT + "/audit.json"
GROUPS = ("arguments", "lineage", "gaps", "ingestion", "lessons", "dependencies", "voices", "editing")
OBSERVATIONS = {"voices", "editing"}
CONFIRMATIONS = "state/research-increment-confirmations"


from scripts.paper_execution import enabled, paper_scoped, selected

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


def scientific_spec(spec):
    return {**{key: spec[key] for key in GROUPS if key not in OBSERVATIONS},
        "required_at_submission": [key for key in spec["required_at_submission"] if key not in OBSERVATIONS]}


def _collect_binding_paths(value, paths):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and "sha256" in value:
            paths.add(value["path"])
        for item in value.values():
            _collect_binding_paths(item, paths)
    elif isinstance(value, list):
        for item in value:
            _collect_binding_paths(item, paths)


def context_dependencies(project, *, scientific_only=False):
    """Invalidate narrow packets when any declared increment source changes."""
    if not (project / PLAN).is_file():
        return []
    spec = load(project)
    if scientific_only:
        spec = scientific_spec(spec)
    paths = set() if scientific_only else {PLAN}

    _collect_binding_paths(spec, paths)
    for group in ("arguments", "lineage"):
        for item in spec[group]:
            from scripts.incremental_writing import paper_path
            paper_path(project, item.get("paper_id"))
            paths.add("papers/" + item["paper_id"] + "/reviews/paper-facts.json")
    if len(paths) > 2000:
        raise ValueError("increment context dependency inventory exceeds 2000 sources")
    result = []
    for relative in sorted(paths):
        source = path_in(project, relative, exists=False)
        if source.is_file() and source.stat().st_size > 50_000_000:
            raise ValueError("increment context source exceeds 50 MB")
        result.append({"path": relative, "sha256": sha(source) if source.is_file() else None})
    return result


@paper_scoped
def paper_review_binding(project, paper_id):
    """Bind shared scientific inputs to the existing per-paper decision."""
    if not (project / PLAN).is_file():
        return {"status": "not_initialized"}
    spec = load(project)
    selected = {key: [row for row in spec[key] if row.get("paper_id") == paper_id]
                for key in ("arguments", "lineage")}
    selected["dependencies"] = []
    for graph in spec["dependencies"]:
        nodes = {row["id"]: row for row in graph["nodes"]}
        keep = {key for key, row in nodes.items() if paper_id in row["paper_ids"]}
        pending = list(keep)
        while pending:
            key = pending.pop()
            if key not in nodes:
                raise ValueError("unknown dependency parent in paper approval")
            for parent in nodes[key].get("depends_on", []):
                if parent not in keep:
                    keep.add(parent)
                    pending.append(parent)
        if keep:
            selected["dependencies"].append({"id": graph["id"], "nodes": [nodes[key] for key in sorted(keep)]})
    matrix_path = project / "program/novelty-claim-matrix.json"
    claims = read(matrix_path).get("claims", []) if matrix_path.is_file() else []
    claim_ids = {row.get("claim_id") for row in claims if paper_id in row.get("paper_ids", [])}
    selected["gaps"] = [row for row in spec["gaps"] if row.get("paper_id") == paper_id
                        or row.get("novelty_claim_id") in claim_ids
                        or (not claims and not row.get("paper_id"))]
    work_ids = {key for row in selected["gaps"] for key in row.get("closest_work_ids", [])}
    paths = set()

    _collect_binding_paths(selected, paths)
    selected["ingestion"] = [row for row in spec["ingestion"] if row["work_id"] in work_ids
                            or row.get("attachment", {}).get("path") in paths]
    _collect_binding_paths(selected["ingestion"], paths)
    sources = []
    for relative in sorted(paths):
        source = path_in(project, relative, exists=False)
        sources.append({"path": relative, "sha256": sha(source) if source.is_file() else None})
    return {"specification": selected, "sources": sources, "implementation": implementations(),
            "required_at_submission": [group for group in spec["required_at_submission"] if group not in OBSERVATIONS]}


def scientific_audit(value):
    """Compare actual scientific results without requiring fresh C bookkeeping."""
    return {**{key: value.get(key) for key in ("schema_version", "implementation", "scientific_plan_sha256", "active_rules",
                "model_calls", "scientific_completion_verified", "quality_level_verified")},
        "groups": {key: value.get("groups", {}).get(key) for key in GROUPS if key not in OBSERVATIONS},
        "errors": [row for row in value.get("errors", []) if row.get("group") not in OBSERVATIONS],
        "missing": [key for key in value.get("missing", []) if key not in OBSERVATIONS],
        "paper_owners": {key: owner for key, owner in value.get("paper_owners", {}).items() if not key.startswith("editing/")}}


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
    registry = primary_attempts(project)
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
    paper_owners = {}
    if enabled(project):
        if (project / REPORT).is_file():
            from scripts.output_provenance import current_origin
            origin = current_origin(project, project / REPORT)
            if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane":
                raise ValueError("research increments saved audit is stale or lacks control-plane provenance")
            prior = read(project / REPORT)
            paper_owners = dict(prior.get("paper_owners", {}))
            for group in ("arguments", "lineage", "editing"):
                for row in prior.get("groups", {}).get(group, []):
                    if row.get("paper_id"):
                        paper_owners.setdefault(group + "/" + row["id"], row["paper_id"])
            for row in prior.get("errors", []):
                if row.get("group") in {"arguments", "lineage", "editing"} and row.get("paper_id"):
                    paper_owners.setdefault(row["group"] + "/" + row["id"], row["paper_id"])
        for group in ("arguments", "lineage", "editing"):
            for row in spec[group]:
                owner = row.get("paper_id")
                key = group + "/" + row["id"]
                if key in paper_owners and paper_owners[key] != owner:
                    errors.append({"group": group, "id": row["id"], "paper_id": paper_owners[key],
                                   "ownership_changed": True, "error": "keep inherited increment paper ownership stable"})
                elif isinstance(owner, str) and re.fullmatch(r"P[0-9]{2}", owner):
                    paper_owners.setdefault(key, owner)
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
        identities = [digest({"kind": kind, "value": value.casefold(), "version": item["version"]})
                      for kind, value in item["identifiers"].items()]
        content = item.get("attachment", {}).get("sha256")
        matches = [seen[key] for key in identities if key in seen]
        previous = matches[0] if matches else None
        if len({value["id"] for value in matches}) > 1:
            errors.append({"group": "ingestion", "id": item["id"], "error": "identifier aliases join conflicting prior records"})
        if previous and content and previous.get("attachment", {}).get("sha256") and previous["attachment"]["sha256"] != content:
            errors.append({"group": "ingestion", "id": item["id"], "error": "same identity/version has conflicting attachments"})
        item["duplicate_of"] = previous["id"] if previous else None
        item["content_reuse_of"] = content_seen.get(content) if content else None
        for identity in identities:
            seen.setdefault(identity, item)
            if content and not seen[identity].get("attachment"):
                seen[identity] = item  # Metadata-to-attachment receipt, preserving both records.
        if content:
            content_seen.setdefault(content, item["id"])
    try:
        active = rules.active_checks(project, confirmation)
    except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
        active = []
        errors.append({"group": "lessons", "id": "active_rules", "error": str(exc)})
    missing = [key for key in spec["required_at_submission"] if not results[key]]
    return {"schema_version": "1.0", "plan_sha256": sha(project / PLAN),
            "scientific_plan_sha256": digest(scientific_spec(spec)),
            "implementation": implementations(), "groups": results, "active_rules": active,
            **({"paper_owners": paper_owners} if enabled(project) else {}),
            "status": "blocked" if errors else "needs_inputs" if missing else "mechanically_checked",
            "errors": errors, "missing": missing, "model_calls": 0,
            "scientific_completion_verified": False, "quality_level_verified": False}


def handoff(project, audit):
    """Only state-backed status/costs; no invented completion percentage or ETA."""
    from scripts.model_spend import read as spend_read
    state_path = path_in(project, "state/run.json", exists=False)
    state = read(state_path) if state_path.is_file() else {}
    spend = spend_read(project)
    cost = {"currency": "CNY", "status": "authorization_state_missing"}
    if spend is not None:
        reserved = sum(item["max_cost_cny"] for item in spend["reservations"].values())
        cost = {"currency": "CNY", "authorized_ceiling": spend["authorized_ceiling_cny"],
                "reported_spent": spend["spent_cny"], "pending_reservations": reserved,
                "remaining_after_reservations": spend["authorized_ceiling_cny"] - spend["spent_cny"] - reserved,
                "billing_reconciled": not bool(spend["reservations"]),
                "amount_basis": "persisted estimates; provider invoice controls final billing"}
    attempts = primary_attempts(project)
    counts = {status: sum(item.get("status") == status for item in attempts)
              for status in ("succeeded", "failed", "timed_out", "stopped")}
    scientific = scientific_audit(audit)
    blockers = list(scientific["errors"])
    if not state:
        blockers.append({"group": "state", "error": "project state is unavailable; restore the cloud checkpoint"})
    blockers.extend({"group": "inputs", "error": item} for item in scientific["missing"])
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
            "next_action": "resolve recorded blockers then run the existing checked stage decision",
            "state_verified": bool(state),
            "source_bindings": [*([{"path": "state/run.json", "sha256": sha(state_path)}] if state else []),
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
    # Narrow chapter packets need current blockers and bindings, not two copies
    # of every manuscript paragraph from inventory and reverse outline.
    summary = {"schema_version": "1.0", "status": audit["status"], "errors": audit.get("errors", []),
               "missing": audit.get("missing", []),
               "groups": {key: [{"id": row["id"], "paper_id": row.get("paper_id"),
                                 "status": row.get("status"), "stale": row.get("stale", {})}
                                for row in values] for key, values in audit.get("groups", {}).items()},
               "bindings": [{"path": REPORT, "sha256": sha(project / REPORT)},
                            *([{"path": PLAN, "sha256": sha(project / PLAN)}] if (project / PLAN).is_file() else [])],
               "scientific_completion_verified": False}
    write(project / ROOT / "context-summary.json", summary)
    record(project, [project / REPORT, project / ROOT / "handoff.json",
                     project / ROOT / "context-summary.json"], "research-increments")
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
    scientific = scientific_audit(audit)
    result = {"status": "blocked" if scientific["errors"] else "needs_inputs" if scientific["missing"] else "mechanically_checked",
              "missing": scientific["missing"], "errors": scientific["errors"],
              "observations": [row for row in audit.get("errors", []) if row.get("group") in OBSERVATIONS],
              "editing": audit.get("groups", {}).get("editing", []),
              "voice_samples": []}
    result["argument_preparation"] = [{"paper_id": row["paper_id"], "id": row["id"],
        "reasoning_review": row["reasoning_review"], "paragraphs": [{"paragraph_id": p["paragraph_id"],
            "reasoning_status": p["reasoning_status"], "review_gaps": p["review_gaps"], "material_needs": p["material_needs"]}
            for p in row["reverse_outline"] if p["review_gaps"] or p["material_needs"]]}
        for row in audit.get("groups", {}).get("arguments", [])]
    for voice in audit.get("groups", {}).get("voices", []):
        content = path_in(project, voice["path"]).read_text(encoding="utf-8")
        result["voice_samples"].append({**voice, "untrusted_style_data": content[:12000],
                                       "excerpt_truncated": len(content) > 12000})
    return json.dumps(result, ensure_ascii=False)


@paper_scoped
def gate_errors(project, gate="G5", paper_id=None):
    # Other stage gates already require their scientific contracts. These increments
    # cannot manufacture approvals or substitute for those checks.
    if not (project / PLAN).is_file():
        return ["research increments not initialized"] if gate == "G5" else []
    try:
        current = build(project)
        focus = selected(project, paper_id) if enabled(project) and gate in {"G3", "G4", "G5"} else None

        def applicable(item):
            if item.get("group") in OBSERVATIONS:
                return False
            if (focus is None or item.get("ownership_changed")
                    or item.get("group") not in {"arguments", "lineage", "editing"}):
                return True
            owner = item.get("paper_id")
            try:
                return selected(project, owner) == focus or not (project / "papers" / owner).is_dir()
            except (ValueError, TypeError):
                return True

        errors = []
        for item in current.get("errors", []):
            if not applicable(item):
                continue
            target_paper = focus or paper_id
            if gate == "G5" and target_paper is not None and item.get("group") == "dependencies":
                graph = next((g for g in current.get("groups", {}).get("dependencies", [])
                              if g.get("id") == item.get("id")), None)
                # A source change only blocks papers which actually consume it.
                # Structural graph errors still fail closed (no valid graph).
                if graph is not None and not any(node["id"] in graph["stale"] and target_paper in node["paper_ids"]
                                                 for node in graph["nodes"]):
                    continue
            errors.append("research increments: " + item["error"])
        if gate == "G5":
            spec = load(project)
            for group in spec["required_at_submission"]:
                if group in OBSERVATIONS:
                    continue
                values = current.get("groups", {}).get(group, [])
                if group in {"arguments", "lineage"}:
                    values = [item for item in values if item.get("paper_id") == paper_id]
                if not values:
                    errors.append("research increments need current " + group + " for " + str(paper_id))
                if group == "arguments":
                    for item in values:
                        if item.get("reasoning_review", {}).get("ready_for_scientific_review") is not True:
                            errors.append("research increments need explicit paragraph takeaways, warrants and resolved material preparation for " + str(paper_id))
        if not (project / REPORT).is_file():
            errors.append("research increments audit must be refreshed in cloud")
        elif scientific_audit(read(project / REPORT)) != scientific_audit(current):
            errors.append("research increments saved audit is stale")
        else:
            from scripts import output_provenance
            origin = output_provenance.current_origin(project, project / REPORT)
            if origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane":
                errors.append("research increments audit lacks current control-plane provenance")
        return errors
    except (ValueError, RuntimeError, OSError, KeyError, TypeError, ImportError) as exc:
        return ["research increments: " + str(exc)]
