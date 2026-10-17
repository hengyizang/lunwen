"""Study-specific G3/G4/G5 controls for Meta analysis and formal theory.

The empirical route retains its original checks. These alternatives require
different positive evidence, not fabricated datasets, power or baseline fields.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
from pathlib import Path

from scripts.research_artifacts import path_in, read, sha, write

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "study-protocol.json"
CONFIRMATION = "study-validation-confirmation.json"
IDENTITY_LOCK = "study-identity-lock.json"


def identity_projection(project, paper_id):
    value = read(project / "papers" / paper_id / "research-identity.json")
    return {k: value[k] for k in ("research_kind", "design_family", "methods", "claim_ids", "reporting_description", "secondary_protocol")}


def route(project, paper_id):
    identity = project / "papers" / paper_id / "research-identity.json"
    if not identity.is_file():
        return "empirical"
    value = read(identity)
    design = value.get("design_family")
    if design == "theoretical" and value.get("research_kind") == "primary":
        return "theory"
    if design == "meta-analysis" and value.get("research_kind") == "secondary_quantitative":
        return "meta_analysis"
    return "empirical"


def protocol_path(project, paper_id):
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("exact paper ID required")
    return project / "papers" / paper_id / PROTOCOL


def need(condition, message):
    if not condition:
        raise ValueError(message)


def text(value, label):
    need(isinstance(value, str) and 10 <= len(value.strip()) <= 10000, label + " needs substantive text")
    return value


def ids(value, label, minimum=1):
    need(isinstance(value, list) and minimum <= len(value) <= 10000
         and all(isinstance(v, str) and 0 < len(v) <= 200 for v in value)
         and len(set(value)) == len(value), label + " needs distinct bounded IDs")
    return set(value)


def anchor(project, item):
    need(isinstance(item, dict), "source anchor required")
    source = path_in(project, item.get("path", ""))
    need(source.is_file() and sha(source) == item.get("sha256"), "source hash changed")
    lines = source.read_text(encoding="utf-8").splitlines()
    start, end = item.get("start_line"), item.get("end_line")
    need(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines), "exact source lines required")
    quote = item.get("quote")
    need(isinstance(quote, str) and quote.strip() and quote in "\n".join(lines[start-1:end]), "source excerpt does not match")
    return source


def _meta_inputs(project, value):
    data_path = path_in(project, value["extraction_file"])
    data = read(data_path)
    records = data.get("records")
    need(isinstance(records, list) and 2 <= len(records) <= 10000, "independently extracted study effects required")
    selection_path = path_in(project, value["selection_file"])
    selection = read(selection_path)
    receipts = ids(selection.get("search_receipt_ids"), "executed search receipts")
    ledger_path = project / "evidence/literature-api-ledger.jsonl"
    ledger = [json.loads(l) for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    universe, sources = set(), [data_path, selection_path, ledger_path]
    for receipt_id in receipts:
        matches = [r for r in ledger if r.get("receipt_id") == receipt_id and r.get("status") == "success"]
        need(len(matches) == 1, "selection needs an exact successful executed search receipt")
        receipt = matches[0]
        for key, digest in (("raw_response_path", "response_sha256"), ("normalized_results_path", "normalized_results_sha256")):
            source = path_in(project, receipt[key]); need(sha(source) == receipt[digest], "search evidence changed")
            sources.append(source)
        works = read(path_in(project, receipt["normalized_results_path"])).get("works", [])
        universe.update(w["id"] for w in works)
    decisions = selection.get("records")
    need(isinstance(decisions, list) and len(decisions) <= 10000, "complete selection decisions required")
    selected = set()
    seen = set()
    for decision in decisions:
        work = decision["work_id"]
        need(work not in seen and decision.get("decision") in {"include", "exclude"}, "duplicate or invalid screening decision")
        seen.add(work); text(decision.get("reason"), "screening rationale")
        if decision["decision"] == "include":
            selected.add(work)
    need(seen == universe and bool(selected), "screen every retrieved work, retaining exclusions and reasons")
    outcomes = value.get("outcomes")
    need(isinstance(outcomes, list) and 1 <= len(outcomes) <= 100, "preregistered Meta outcomes required")
    outcome_ids = ids([o["id"] for o in outcomes], "Meta outcomes")
    for outcome in outcomes:
        for field in ("estimand", "population", "comparability", "precision_rationale"):
            text(outcome.get(field), field)
        need(outcome.get("effect_measure") in {"mean_difference", "standardized_mean_difference", "log_risk_ratio", "log_odds_ratio", "log_hazard_ratio"}, "unsupported or mixed effect measure")
        need(outcome.get("direction") in {"greater", "less"} and outcome.get("analysis_phase") in {"confirmatory", "exploratory"}, "predeclare analysis phase and direction")
        need(type(outcome.get("alpha")) in (float, int) and 0 < outcome["alpha"] < 1, "invalid alpha")
        need(type(outcome.get("minimum_effect")) in (float, int) and math.isfinite(outcome["minimum_effect"]) and outcome["minimum_effect"] >= 0, "invalid practical threshold")
        text(outcome.get("family"), "multiplicity family")
        ids(outcome.get("claim_ids"), "outcome claims")
    observed = set()
    extracted_studies = set()
    for row in records:
        study, outcome = row["study_id"], row["outcome_id"]
        need(study in selected and outcome in outcome_ids and (study, outcome) not in observed, "unselected, duplicate or undeclared effect")
        observed.add((study, outcome)); extracted_studies.add(study)
        need(row.get("risk_of_bias") in {"low", "some_concerns", "high"}, "record risk of bias")
        text(row.get("bias_rationale"), "bias rationale")
        text(row.get("license_or_research_rights"), "source rights")
        for field in ("effect", "variance"):
            need(type(row.get(field)) in (float, int) and math.isfinite(row[field]) and (field != "variance" or row[field] > 0), "invalid extracted effect or sampling variance")
        sources.append(anchor(project, row["source"]))
        extracts = row.get("independent_extractions")
        need(isinstance(extracts, list) and len(extracts) == 2 and len({e.get("reviewer") for e in extracts}) == 2
             and all(isinstance(e.get("reviewer"), str) and e["reviewer"].strip() for e in extracts), "two separately attributed extractions required")
        for e in extracts:
            for field in ("effect", "variance"):
                need(type(e.get(field)) in (float, int) and math.isfinite(e[field]), "invalid independent extraction")
        if any(e["effect"] != row["effect"] or e["variance"] != row["variance"] for e in extracts):
            sources.append(anchor(project, row.get("adjudication")))
        need(isinstance(row.get("cohort_id"), str) and row["cohort_id"].strip(), "cohort dependence identity required")
    need(extracted_studies == selected, "included studies without an extracted outcome cannot disappear")
    for outcome in outcomes:
        rows = [r for r in records if r["outcome_id"] == outcome["id"]]
        need(len(rows) >= 2 and len({r["cohort_id"] for r in rows}) == len(rows), "dependent or insufficient study effects require another reviewed method")
        need(all(r["effect_measure"] == outcome["effect_measure"] for r in rows), "outcome scales must be comparable")
    return sources


def _theory_inputs(project, value):
    theorems = value.get("theorems")
    need(isinstance(theorems, list) and 1 <= len(theorems) <= 100, "formal obligations required")
    ids([t["id"] for t in theorems], "proof obligations")
    declarations = ids([t["declaration"] for t in theorems], "Lean declarations")
    sources, covered = [], {}
    for item in theorems:
        need(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", item["declaration"]), "unsafe theorem name")
        need(item.get("role") in {"main", "assumption_witness", "scope_check"}, "declare theorem, non-vacuity and scope obligations")
        for field in ("statement", "formal_type", "assumptions", "scope", "proof_strategy", "comparison_to_closest_result"):
            text(item.get(field), field)
        claim_ids = ids(item.get("claim_ids"), "theorem claims")
        for claim in claim_ids:
            covered.setdefault(claim, set()).add(item["role"])
        source = path_in(project, item["source"])
        need(source.suffix == ".lean" and sha(source) == item["sha256"], "exact Lean proof source required")
        sources.append(source)
        parents = ids(item.get("depends_on", []), "proof dependencies", 0)
        need(parents <= declarations and item["declaration"] not in parents, "invalid proof dependency")
    graph = {t["declaration"]: t.get("depends_on", []) for t in theorems}
    def visit(name, visiting):
        need(name not in visiting, "cyclic theorem dependency graph")
        for parent in graph[name]:
            visit(parent, visiting | {name})
    for name in graph:
        visit(name, set())
    need(all(roles == {"main", "assumption_witness", "scope_check"} for roles in covered.values()), "every theoretical claim needs a proof, an assumption witness and a scope check")
    need(type(value.get("proof_timeout_seconds")) is int and 1 <= value["proof_timeout_seconds"] <= 900, "bounded proof-check timeout required")
    return sources


def validate_protocol(project, paper_id):
    kind = route(project, paper_id)
    need(kind != "empirical", "select a supported study-specific route")
    path = protocol_path(project, paper_id)
    need(path.stat().st_size <= 500000, "study protocol exceeds bounded size")
    value = read(path)
    need(value.get("schema_version") == "1.0" and value.get("paper_id") == paper_id and value.get("route") == kind
         and value.get("status") == "ready_for_review", "study protocol identity/status mismatch")
    for key in ("question", "methodological_review", "replication_plan", "deviation_policy"):
        text(value.get(key), key)
    ids(value.get("limitations"), "scope limitations")
    contract = read(project / "papers" / paper_id / "paper-contract.json")
    if kind == "theory":
        need(contract.get("datasets") == [], "pure theory declares no empirical datasets; evidence consists of formal obligations")
    claims = ids(contract.get("independence", {}).get("unique_claim_ids"), "contracted claims")
    need(ids(value.get("claim_ids"), "study claims") == claims, "study claims must exactly match the paper contract")
    sources = _meta_inputs(project, value) if kind == "meta_analysis" else _theory_inputs(project, value)
    units = value["outcomes"] if kind == "meta_analysis" else value["theorems"]
    need(set().union(*(set(u["claim_ids"]) for u in units)) == claims, "study outcomes must cover all and only contracted claims")
    references = value.get("closest_work_comparison")
    need(isinstance(references, list) and len(references) >= 3, "compare at least three closest primary results")
    sources.extend(anchor(project, item) for item in references)
    run_ids = ids(value.get("execution_runs"), "original and isolated reproduction runs", 2)
    need(len(run_ids) == 2, "declare exactly one original and one independent replay")
    plan = read(project / "experiments/plan.json")
    from scripts.experiment_runner import validate_plan as validate_execution_plan
    need(not validate_execution_plan(plan), "; ".join(validate_execution_plan(plan)))
    runs = [r for r in plan["runs"] if r.get("paper_id") == paper_id]
    need({r["run_id"] for r in runs} == run_ids, "assign every paper run to this study protocol")
    tolerance = value.get("replication_tolerance")
    need(type(tolerance) in (float, int) and math.isfinite(tolerance) and 0 <= tolerance <= 1e-6, "predeclare a strict replication tolerance")
    engine = ROOT / "scripts" / ("meta_analysis_runtime.py" if kind == "meta_analysis" else "theory_verification_runtime.py")
    runtime = path_in(project, value["runtime_path"])
    need(sha(runtime) == sha(engine), "runtime must match the reviewed deterministic implementation")
    identity_lock = project / "papers" / paper_id / IDENTITY_LOCK
    need(read(identity_lock) == identity_projection(project, paper_id), "study identity/methods changed from their frozen projection")
    sources.extend([runtime, path, identity_lock, project / "papers" / paper_id / "paper-contract.json"])
    required_inputs = {p.relative_to(project).as_posix(): sha(p) for p in sources}
    for run in runs:
        need(run.get("isolation", {}).get("kind") == "container" and run["isolation"].get("engine") == "docker"
             and run["timeout_seconds"] <= 1200, "study runs require bounded digest-pinned Docker isolation")
        need(run.get("runtime", {}).get("profile") == kind, "use the reviewed CPU toolchain profile")
        output = value["outputs"].get(run["run_id"])
        need(isinstance(output, str) and output.startswith("results/") and run["expected_outputs"] == [output], "one immutable study-result JSON per run required")
        args = [value["runtime_path"], path.relative_to(project).as_posix()]
        if kind == "meta_analysis":
            args.append(value["extraction_file"])
        args.append(output)
        need(run["argv"][0] in {"python", "python3"} and run["argv"][1:] == args and run.get("cwd", ".") == ".", "study execution must use the reviewed runtime and exact preregistered inputs")
        inputs = {i["path"]: i["sha256"] for i in run["inputs"]}
        need(all(inputs.get(p) == digest for p, digest in required_inputs.items()), "run inputs omit or change study evidence")
    need(len(set(value["outputs"].values())) == 2, "independent runs must preserve distinct result files")
    return value, sorted(set(sources))


def prepare_runtime(project, paper_id):
    state = read(project / "state/run.json")
    need(state.get("gate") == "G3" and state.get("status") == "awaiting_work", "runtime preparation requires an open G3")
    kind = route(project, paper_id)
    value = read(protocol_path(project, paper_id))
    need(kind in {"meta_analysis", "theory"}, "unsupported study route")
    target = path_in(project, value["runtime_path"])
    need(value["runtime_path"] == f"analysis/runtime/{paper_id}/runtime.py", "use the reserved runtime path")
    source = ROOT / "scripts" / ("meta_analysis_runtime.py" if kind == "meta_analysis" else "theory_verification_runtime.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    identity_lock = project / "papers" / paper_id / IDENTITY_LOCK
    write(identity_lock, identity_projection(project, paper_id))
    plan_path = project / "experiments/plan.json"
    if plan_path.is_file():
        from scripts.study_environment import prepare
        environment, _ = prepare(kind)
        plan = read(plan_path)
        for run in plan.get("runs", []):
            if run.get("paper_id") == paper_id:
                run["runtime"] = environment
                run["isolation"] = {"kind": "container", "engine": "docker", "image": environment["base_image"]}
                items = {i["path"]: i for i in run.get("inputs", [])}
                for file in (target, identity_lock):
                    relative = file.relative_to(project).as_posix()
                    items[relative] = {"path": relative, "sha256": sha(file)}
                run["inputs"] = list(items.values())
        write(plan_path, plan)
    from scripts.research_artifacts import record
    record(project, [target, identity_lock, *([plan_path] if plan_path.is_file() else [])], "scripts/study_routes.py")
    return target


def preregistration_inputs(project, paper_id):
    _, inputs = validate_protocol(project, paper_id)
    return [*inputs, project / "experiments/plan.json", project / "experiments/budget.json"]


def plan_errors(project, paper_id):
    try:
        validate_protocol(project, paper_id)
        return []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [str(exc)]


def _equivalent(left, right, tolerance):
    if type(left) in (int, float) and type(right) in (int, float):
        return math.isfinite(left) and math.isfinite(right) and math.isclose(left, right, rel_tol=tolerance, abs_tol=tolerance)
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(_equivalent(left[k], right[k], tolerance) for k in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_equivalent(a, b, tolerance) for a, b in zip(left, right))
    return type(left) is type(right) and left == right


def build_report(project, paper_id):
    report = {"schema_version": "1.0", "paper_id": paper_id, "route": route(project, paper_id),
              "status": "blocked", "errors": [], "comparisons": [], "scientific_completion_verified": False}
    try:
        value, _ = validate_protocol(project, paper_id)
        from scripts import research_quality as quality, results_validation
        plan_path = project / "experiments/plan.json"
        registry_path = project / "experiments/registry.jsonl"
        registry = quality._registry(project)
        errors = results_validation.validate_registry(project, read(plan_path), registry)
        prereg = project / "papers" / paper_id / "preregistration.json"
        state = read(project / "state/run.json")
        approval = next((a for a in reversed(state.get("approvals", [])) if a.get("gate") == "G3"), {})
        need(approval.get("frozen_protocol_sha256", {}).get(f"papers/{paper_id}/preregistration.json") == sha(prereg), "study preregistration differs from the human G3 approval")
        errors += quality.validate_preregistration(read(prereg), paper_id, project)
        need(not errors, "; ".join(errors))
        results, sources = [], []
        for run_id in value["execution_runs"]:
            attempts = [r for r in registry if r.get("run_id") == run_id]
            need(len(attempts) == 1 and attempts[0].get("status") == "succeeded", "every study run needs exactly one successful attempt; failed attempts require inspection")
            receipt = attempts[0]
            need(receipt.get("input_integrity", {}).get("passed") is True, "study inputs mutated")
            isolation = receipt.get("executor_isolation", {})
            need(isolation.get("isolated_executor") is True and isolation.get("network_disabled") is True, "study replay lacks isolated executor evidence")
            need(read(project / "experiments/runs" / receipt["attempt_id"] / "run.json") == receipt, "executor receipt differs from registry")
            output = path_in(project, value["outputs"][run_id])
            need(any(o.get("path") == value["outputs"][run_id] and o.get("sha256") == sha(output) for o in receipt["outputs"]), "study result changed")
            result = read(output)
            need(result.get("route") == value["route"] and result.get("paper_id") == paper_id and result.get("protocol_sha256") == sha(protocol_path(project, paper_id))
                 and result.get("implementation_sha256") == sha(path_in(project, value["runtime_path"])), "result does not match the frozen study/runtime")
            results.append(result); sources.append({"run_id": run_id, "attempt_id": receipt["attempt_id"], "path": value["outputs"][run_id], "sha256": sha(output)})
        need(_equivalent(results[0], results[1], value["replication_tolerance"]), "isolated replay differs beyond preregistered tolerance")
        if value["route"] == "meta_analysis":
            from scripts.meta_analysis_runtime import calculate
            expected = calculate(value, read(path_in(project, value["extraction_file"])))
            need(_equivalent(expected["outcomes"], results[0].get("outcomes"), value["replication_tolerance"]), "Meta statistics differ from deterministic recomputation")
            for row in results[0]["outcomes"]:
                report["comparisons"].append({"comparison_id": row["id"], "claim_ids": row["claim_ids"],
                    "analysis_phase": row["analysis_phase"], "role": "primary", "decision": row["decision"],
                    "sources": sources, "statistics": row})
        else:
            expected = {t["id"]: t for t in value["theorems"]}
            actual = results[0].get("theorems", [])
            need(len(actual) == len(expected) and {t["id"] for t in actual} == set(expected), "proof report omits obligations")
            for theorem in actual:
                original = expected[theorem["id"]]
                need(theorem.get("status") == "kernel_checked" and set(theorem.get("axioms", [])) <= {"propext", "Classical.choice", "Quot.sound"}
                     and theorem.get("source_sha256") == original["sha256"]
                     and theorem.get("checked_type") == " ".join((original["declaration"] + " : " + original["formal_type"]).split()), "proof report does not verify the declared theorem")
                report["comparisons"].append({"comparison_id": theorem["id"], "claim_ids": original["claim_ids"],
                    "analysis_phase": "confirmatory", "role": original["role"], "decision": "kernel_checked",
                    "sources": sources, "proof": theorem})
        report.update(status="complete", protocol_sha256=sha(protocol_path(project, paper_id)),
                      preregistration_sha256=sha(prereg), registry_sha256=sha(registry_path),
                      approved_plan_sha256=sha(plan_path), implementation_sha256=sha(Path(__file__)), sources=sources)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError, RuntimeError) as exc:
        report["errors"].append(str(exc))
    return report


def create_confirmation(project, paper_id, actor):
    need(isinstance(actor, str) and actor.strip(), "named human scientific reviewer required")
    report = build_report(project, paper_id)
    need(report["status"] == "complete", "; ".join(report["errors"]))
    return {"schema_version": "1.0", "paper_id": paper_id, "actor": actor,
            "report_sha256": hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest(),
            "review_scope": "Source/extraction validity, independence, assumptions, non-vacuity, manuscript meaning, scope and isolated replay; no automatic novelty certification.",
            "scientific_completion_verified": False}


def validation_errors(project, paper_id, *, confirmation=True):
    report = build_report(project, paper_id)
    errors = list(report["errors"])
    saved = project / "papers" / paper_id / "experiment-evidence.json"
    if not saved.is_file() or read(saved) != report:
        errors.append("study evidence must match the current deterministic report")
    if confirmation:
        path = project / "papers" / paper_id / CONFIRMATION
        if not path.is_file():
            errors.append("named human study-validation confirmation required")
        else:
            value = read(path)
            if (not value.get("actor") or not re.fullmatch(r"[0-9]+", str(value.get("source_run_id", "")))
                    or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("cloud_review_sha256", "")))
                    or value.get("report_sha256") != hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()):
                errors.append("study-validation confirmation is stale")
    return errors


def reporting_audit(project, paper_id, *, manuscript_project=None, mapping_name="statistical-reporting-map.json"):
    """Map every actual result/proof to the canonical manuscript, including nulls."""
    from scripts.ref_verify_adapter import canonical_manuscript
    from scripts.revision_trace import verify_location, normalized
    manuscript_project = manuscript_project or project
    paper = manuscript_project / "papers" / paper_id
    evidence = build_report(project, paper_id)
    errors = list(evidence["errors"])
    mapping_path = project / "papers" / paper_id / mapping_name
    bindings = []
    try:
        mapping = read(mapping_path)
        rows = mapping["items"]
        expected = {c["comparison_id"]: c for c in evidence["comparisons"]}
        need(len(rows) == len(expected) and {r["result_id"] for r in rows} == set(expected), "report every preregistered outcome and proof obligation")
        canonical = canonical_manuscript(paper)
        for row in rows:
            result = expected[row["result_id"]]
            verify_location(paper, canonical, json.dumps(row["location"]), row["excerpt"])
            text(row.get("interpretation"), "bounded interpretation")
            text(row.get("uncertainty"), "uncertainty/scope")
            if evidence["route"] == "meta_analysis":
                actual = result["statistics"]
                fields = {**{k: actual["summary"][k] for k in ("k", "estimate", "ci_low", "ci_high", "tau_squared", "i_squared")}, "p_adjusted": actual["p_adjusted"]}
                need(set(row["values"]) == set(fields), "Meta reporting must include count, estimate, uncertainty, heterogeneity and adjusted test")
                for key, value in fields.items():
                    rendered = row["values"][key]
                    need(isinstance(rendered, str) and rendered in row["excerpt"] and math.isclose(float(rendered), value, rel_tol=1e-4, abs_tol=5e-6), "reported statistic differs from computed " + key)
            else:
                need(normalized(result["proof"]["natural_language_statement"]) in normalized(row["excerpt"]), "manuscript must state the registered theorem obligation")
                need(row.get("formal_type") == result["proof"]["checked_type"], "theory reporting must bind the exact checked formal type")
            bindings.append({"result_id": row["result_id"], "location": row["location"], "excerpt": row["excerpt"]})
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append(str(exc))
    return {"schema_version": "1.0", "paper_id": paper_id, "route": evidence["route"], "status": "pass" if not errors else "fail",
            "errors": errors, "bindings": bindings, "mapping_sha256": sha(mapping_path) if mapping_path.is_file() else None,
            "evidence_digest": hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest(),
            "scientific_completion_verified": False, "human_scientific_review_required": True}


def prompt_contract():
    return ("For actual Meta-analysis or theoretical identities, use papers/Pxx/study-protocol.json and the dedicated study route. "
            "Meta needs complete search/selection receipts, source-bound independently attributed extraction, cohort independence, bias assessment, "
            "preregistered PM/modified-HKSJ outcomes, DL/leave-one-out/bias sensitivities and isolated replay. Theory needs exact Lean types, "
            "proof, assumption-witness and scope-check obligations for every claim; numerical examples are not proofs. "
            "Do not invent empirical datasets, baseline classes or power calculations for these routes. Prepare the reserved runtime through "
            "study_prepare; hash-declare all protocol/source/runtime inputs and two distinct Docker result files. G3/G4 approvals remain human.")
