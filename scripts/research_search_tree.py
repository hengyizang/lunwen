"""Receipt-bound experiment search views; no search agent, execution or selection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

from scripts import research_iteration as iteration
from scripts.research_artifacts import path_in, read, record, sha, write

ROOT = Path(__file__).resolve().parents[1]
MODULE = "scripts/research_search_tree.py"
OUTPUT = "reports/research-search-tree"
PHASES = {"investigation", "tuning", "main", "ablation"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", value):
        raise ValueError("search tree requires bounded node and task IDs")
    return value


def _prepare(project, request_file, root):
    if not isinstance(request_file, str) or not request_file.startswith("program/") or not request_file.endswith(".json"):
        raise ValueError("search tree request belongs under program/*.json")
    source = path_in(project, request_file)
    if source.stat().st_size > 64000:
        raise ValueError("search tree request exceeds 64 KB")
    request = read(source)
    if (set(request) - {"kind", "id", "iteration_report", "nodes", "max_items", "max_debug_depth"}
            or request.get("kind") != "research_search_tree"):
        raise ValueError("search tree requires its exact request kind and supported fields")
    identity = _id(request.get("id"))
    for field, default, ceiling in (("max_items", 10, 20), ("max_debug_depth", 3, 10)):
        if type(request.get(field, default)) is not int or not 1 <= request.get(field, default) <= ceiling:
            raise ValueError(field + " is outside its bounded preparation range")
    report_path = request.get("iteration_report")
    # This validates all actual source, module and provenance bindings without writes.
    iteration.model_context(project, report_path, "critic", root=root)
    report_file = path_in(project, report_path)
    report = read(report_file)
    attempts = {a["attempt_id"]: a for a in report["attempts"]}
    plan_file = path_in(project, "experiments/plan.json")
    planned = {r["run_id"]: r for r in read(plan_file).get("runs", [])}
    nodes = request.get("nodes")
    if not isinstance(nodes, list) or not 1 <= len(nodes) <= 50:
        raise ValueError("search tree needs one to fifty declared nodes")
    indexed = {}
    for node in nodes:
        if (not isinstance(node, dict) or set(node) - {"node_id", "parent_id", "branch_kind", "run_id", "attempt_id", "workflow_phase"}
                or not {"node_id", "parent_id", "branch_kind", "run_id"} <= set(node)):
            raise ValueError("search node has missing or unsupported fields")
        name = _id(node["node_id"])
        if name in indexed:
            raise ValueError("duplicate search node ID")
        if not isinstance(node["run_id"], str) or node["run_id"] not in planned:
            raise ValueError("search node must identify an existing planned run")
        if not isinstance(node["branch_kind"], str) or node["branch_kind"] not in {"root", "debug", "variation"}:
            raise ValueError("search branch must be root, debug or variation")
        if node["parent_id"] is not None:
            _id(node["parent_id"])
        if "workflow_phase" in node and (not isinstance(node["workflow_phase"], str) or node["workflow_phase"] not in PHASES):
            raise ValueError("unsupported declared workflow phase")
        if "attempt_id" in node and not isinstance(node["attempt_id"], str):
            raise ValueError("attempt_id must name an exact existing executor attempt")
        attempt = attempts.get(node.get("attempt_id"))
        if "attempt_id" in node and (attempt is None or attempt["run_id"] != node["run_id"]
                or attempt["paper_id"] != planned[node["run_id"]].get("paper_id")):
            raise ValueError("node has no matching real executor attempt")
        if (node["parent_id"] is None) != (node["branch_kind"] == "root"):
            raise ValueError("only root nodes have no parent")
        indexed[name] = node
    visiting, depths = set(), {}

    def depth(name):
        if name in visiting:
            raise ValueError("search ancestry contains a cycle")
        if name in depths:
            return depths[name]
        visiting.add(name)
        node = indexed[name]
        parent = node["parent_id"]
        if parent is not None and parent not in indexed:
            raise ValueError("search parent is absent")
        parent_depth = depth(parent) if parent is not None else 0
        if parent is not None and planned[indexed[parent]["run_id"]].get("paper_id") != planned[node["run_id"]].get("paper_id"):
            raise ValueError("a search branch cannot silently cross paper scope")
        depths[name] = (parent_depth + 1 if node["branch_kind"] == "debug" else 0)
        visiting.remove(name)
        return depths[name]

    facts, worklist, used_attempts = [], [], set()
    for name, node in indexed.items():
        debug_depth = depth(name)
        attempt = attempts.get(node.get("attempt_id"))
        if attempt:
            if attempt["attempt_id"] in used_attempts:
                raise ValueError("one actual attempt cannot impersonate multiple nodes")
            used_attempts.add(attempt["attempt_id"])
        if node["branch_kind"] == "debug":
            parent = indexed[node["parent_id"]]
            observed = attempts.get(parent.get("attempt_id"))
            if (not observed or observed["status"] not in {"failed", "timed_out"}
                    or not any(d["condition"] in {"engineering_failure", "incomplete_execution"} for d in observed["diagnostics"])):
                raise ValueError("debug requires actual engineering failure or incomplete execution, never a weak score")
        known = [a["attempt_id"] for a in report["attempts"] if a["run_id"] == node["run_id"]]
        status = attempt["status"] if attempt and attempt["status"] in ("succeeded", "failed", "timed_out") else "unknown"
        state = ("executed_" + status + "_pending_scientific_review" if attempt else
                 "attempt_not_selected" if known else "planned_not_executed")
        fact = {"node_id": name, "parent_id": node["parent_id"], "branch_kind": node["branch_kind"],
                "run_id": node["run_id"], "paper_id": planned[node["run_id"]].get("paper_id"),
                "attempt_id": node.get("attempt_id"), "known_attempt_ids": known,
                "status": state, "actual_analysis_phase": attempt["analysis_phase"] if attempt else None,
                "declared_workflow_phase": node.get("workflow_phase"), "workflow_phase_verified": False,
                "receipt_binding": attempt["receipt_binding"] if attempt else None,
                "attempt_plan_binding": attempt["plan_binding"] if attempt else None,
                "history_version": attempt["history_version"] if attempt else None,
                "observed_conditions": [d["code"] for d in attempt["diagnostics"]] if attempt else [],
                "consecutive_debug_depth": debug_depth,
                "debug_preparation_limit_reached": debug_depth >= request.get("max_debug_depth", 3),
                "scientific_validation": "not_assessed", "selected_by_metric": False}
        facts.append(fact)
        worklist.append({"node_id": name, "status": "proposal_only_not_executed",
            "next_action": "review_debug_limit_and_existing_failure" if fact["debug_preparation_limit_reached"] else
                           "select_exact_existing_attempt_before_interpretation" if state == "attempt_not_selected" else
                           "review_existing_G3_budget_and_runner_prerequisites" if attempt is None else
                           "review_actual_outputs_without_discarding_any_path"})
    payload = {"schema_version": "1.0", "kind": "research_search_tree", "id": identity,
        "request_binding": {"path": request_file, "sha256": sha(source)},
        "iteration_binding": {"path": report_path, "sha256": sha(report_file)},
        "plan_binding": {"path": "experiments/plan.json", "sha256": sha(plan_file)},
        "module_sha256": sha(path_in(root, MODULE)), "nodes": facts,
        "root_ids": [n["node_id"] for n in facts if n["parent_id"] is None],
        "leaf_ids": [name for name in indexed if not any(n["parent_id"] == name for n in facts)],
        "all_attempt_count": len(report["attempts"]), "unrepresented_attempt_count": len(attempts) - len(used_attempts),
        "history_retained_in": report_path, "worklist": worklist[:request.get("max_items", 10)],
        "worklist_omitted": max(0, len(worklist) - request.get("max_items", 10)),
        "paid_calls": 0, "experiments_executed": 0, "gate_approved": False,
        "scientific_completion_verified": False, "automatic_selection_or_pruning": False}
    digest = _digest(payload)
    return {**payload, "report_sha256": digest, "report_path": f"{OUTPUT}/{identity}-{digest}.json"}


def _origin(project, target):
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    if origin.get("status") != "tracked" or origin.get("model") != MODULE or origin.get("provider") != "deterministic-control-plane":
        raise ValueError("search tree lacks current executor provenance")


def refresh(project: Path, request_file: str, *, root: Path = ROOT):
    from scripts.literaturectl import require_cloud
    require_cloud()
    result = _prepare(project, request_file, root)
    target = path_in(project, result["report_path"], exists=False)
    if target.exists():
        _origin(project, target)
        if read(target) != result:
            raise ValueError("immutable search tree changed")
    else:
        write(target, result)
        record(project, [target], MODULE)
    return result


def model_context(project: Path, relative: str, role: str, *, root: Path = ROOT):
    if role not in {"planner", "writer", "critic", "remediator"}:
        raise ValueError("unsupported search tree role")
    if not isinstance(relative, str) or not re.fullmatch(re.escape(OUTPUT) + r"/[A-Za-z0-9][A-Za-z0-9_-]{0,79}-[a-f0-9]{64}\.json", relative):
        raise ValueError("select one immutable search tree")
    target = path_in(project, relative)
    actual = read(target)
    expected = _prepare(project, actual.get("request_binding", {}).get("path", ""), root)
    _origin(project, target)
    if actual != expected or relative != expected["report_path"]:
        raise ValueError("search tree is stale or changed")
    nodes = [{k: v for k, v in n.items() if role != "critic" or k != "declared_workflow_phase"} for n in expected["nodes"][:20]]
    context = {"report_path": relative, "report_sha256": expected["report_sha256"], "nodes": nodes,
        "nodes_omitted": max(0, len(expected["nodes"]) - 20), "all_attempt_count": expected["all_attempt_count"],
        "history_retained_in": expected["history_retained_in"], "scientific_validation": "not_assessed",
        "boundary": "Declared ancestry is not a repaired-bug, novelty, scientific-quality, or execution-approval verdict. Retain all failed, negative and independent replication paths."}
    if role != "critic":
        context.update(worklist=expected["worklist"], worklist_omitted=expected["worklist_omitted"])
    return context
