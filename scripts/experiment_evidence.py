"""Preregistered experiment coverage and registry-bound statistical evidence.

These controls audit execution and numeric support. They cannot establish novelty,
causality, representativeness, doctoral merit or journal acceptance.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

PLAN = "experiment-evidence-plan.json"
REPORT = "experiment-evidence.json"
ROLES = {"primary", "ablation", "negative_control", "robustness", "external_validation"}
MAX_CSV_BYTES = 20_000_000
MAX_ROWS = 200_000


class EvidenceError(ValueError):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def text(value: Any, label: str) -> str:
    need(isinstance(value, str) and bool(value.strip()), f"{label} must be non-empty text")
    return value


def strings(value: Any, label: str, *, empty: bool = False) -> list[str]:
    need(isinstance(value, list) and (empty or bool(value)), f"{label} must be an array")
    for item in value:
        text(item, label)
    need(len(set(value)) == len(value), f"{label} contains duplicates")
    return value


def number(value: Any, label: str, low: float | None = None, high: float | None = None) -> float:
    need(type(value) in (int, float) and math.isfinite(value), f"{label} must be finite")
    need(low is None or value >= low, f"{label} is below its allowed minimum")
    need(high is None or value <= high, f"{label} exceeds its allowed maximum")
    return float(value)


def path_in(project: Path, relative: str) -> Path:
    from scripts.cloud_checkpoint import relative as safe_relative
    try:
        safe_relative(relative)
    except (ValueError, RuntimeError, TypeError) as exc:
        raise EvidenceError("unsafe experiment evidence path") from exc
    path = project / relative
    need(not any(p.is_symlink() for p in (path, *path.parents) if p == project or project in p.parents),
         "experiment evidence cannot use symlinks")
    return path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    need(isinstance(value, dict), f"{path.name} must contain an object")
    return value


def paper_plan(project: Path, paper_id: str) -> Path:
    need(isinstance(paper_id, str) and len(paper_id) == 3 and paper_id[0] == "P"
         and paper_id[1:].isdigit(), "invalid paper ID")
    return project / "papers" / paper_id / PLAN


def validate_plan(project: Path, paper_id: str) -> list[str]:
    try:
        _validate_plan(project, paper_id)
        return []
    except (EvidenceError, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return [str(exc)]


def _validate_plan(project: Path, paper_id: str) -> dict:
    protocol = read(paper_plan(project, paper_id))
    need(protocol.get("schema_version") == "1.0" and protocol.get("paper_id") == paper_id
         and protocol.get("status") == "ready_for_review", "invalid experiment evidence plan identity/status")
    runs_value = read(project / "experiments/plan.json").get("runs")
    need(isinstance(runs_value, list), "execution plan runs must be an array")
    runs = {r["run_id"]: r for r in runs_value if isinstance(r, dict) and r.get("paper_id") == paper_id}
    power = read(project / "papers" / paper_id / "power-analysis.json")
    designs = {}
    for path in sorted((project / "papers" / paper_id / "experiments").glob("*.json")):
        design = read(path)
        identifier = text(design.get("design_id"), "design_id")
        need(identifier not in designs, "duplicate design_id")
        designs[identifier] = design
    need(bool(designs), "paper has no experiment designs")
    contract = read(project / "papers" / paper_id / "paper-contract.json")
    claims = set(strings(contract.get("independence", {}).get("unique_claim_ids"), "contract claim IDs"))
    pilots = set(strings(protocol.get("pilot_run_ids"), "pilot_run_ids"))
    need(pilots <= runs.keys(), "pilot runs must belong to this paper")
    text(protocol.get("pilot_success_criteria"), "pilot_success_criteria")

    def ancestors(run_id: str, visiting: set[str] | None = None) -> set[str]:
        visiting = set() if visiting is None else visiting
        need(run_id in runs and run_id not in visiting, "unknown or cyclic experiment dependency")
        parents = strings(runs[run_id].get("depends_on", []), "depends_on", empty=True)
        result = set(parents)
        for parent in parents:
            result |= ancestors(parent, visiting | {run_id})
        return result

    for run_id in runs:
        ancestors(run_id)
    comparisons = protocol.get("comparisons")
    need(isinstance(comparisons, list) and 1 <= len(comparisons) <= 100, "comparisons needs 1-100 entries")
    seen, covered_claims = set(), set()
    coverage: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    families: dict[str, float] = {}
    run_conditions: dict[str, tuple] = {}
    claim_baselines: dict[tuple, set[str]] = defaultdict(set)
    for comp in comparisons:
        need(isinstance(comp, dict), "comparison must be an object")
        identifier = text(comp.get("comparison_id"), "comparison_id")
        need(identifier not in seen, "duplicate comparison_id")
        seen.add(identifier)
        design_id = text(comp.get("design_id"), "comparison design_id")
        need(design_id in designs, "comparison references an unknown design")
        design = designs[design_id]
        need(comp.get("hypothesis_id") in design.get("hypothesis_ids", []), "comparison hypothesis is not designed")
        assigned_claims = set(strings(comp.get("claim_ids"), "comparison claim_ids"))
        need(assigned_claims <= claims, "comparison references an uncontracted claim")
        role = comp.get("role")
        need(role in ROLES, "invalid comparison role")
        need(comp.get("analysis_phase") in {"confirmatory", "exploratory"}, "declare confirmatory or exploratory")
        if role == "primary":
            need(comp["analysis_phase"] == "confirmatory", "primary evidence cannot be exploratory")
            covered_claims |= assigned_claims
        comparator = text(comp.get("comparator_id"), "comparator_id")
        coverage[design_id][role].add(comparator)
        if role == "primary":
            coverage[design_id]["hypotheses"].add(comp["hypothesis_id"])
            for claim in assigned_claims:
                claim_baselines[(design_id, claim)].add(comparator)
        for key in ("metric", "analysis_unit", "independence_rationale", "assumptions", "rationale", "sample_size_rationale", "population_scope"):
            text(comp.get(key), key)
        metrics = design.get("metrics", {})
        names = {m.get("name") for m in metrics.get("primary", []) if isinstance(m, dict)}
        names |= set(metrics.get("secondary", []))
        need(comp["metric"] in names, "comparison metric is absent from the design")
        need(comp.get("dataset_id") in design.get("data_protocol", {}).get("datasets", []),
             "comparison dataset is absent from the design")
        need(comp.get("direction") in {"higher", "lower"}, "metric direction must be higher or lower")
        need(comp.get("decision_rule") in {"superiority", "equivalence"}, "invalid decision rule")
        margin = number(comp.get("minimum_effect"), "minimum_effect", 0)
        if comp["decision_rule"] == "equivalence":
            need(margin > 0, "equivalence requires a positive prespecified margin")
        alpha = number(comp.get("alpha"), "alpha", 0.000001, 0.1)
        family = text(comp.get("family"), "multiplicity family")
        need(family not in families or families[family] == alpha, "a family must use one alpha")
        families[family] = alpha
        need(type(comp.get("minimum_units")) is int and comp["minimum_units"] >= 3,
             "minimum_units must be >=3 and justified by the separate power/precision analysis")
        sample = power.get("required_sample_size", {})
        if sample:
            required = max(number(n, "power sample size", 1) for n in sample.values())
            need(comp["minimum_units"] >= required, "planned independent units fall below the power-analysis requirement")
        family_size = sum(c.get("family") == family and c.get("analysis_phase") == comp["analysis_phase"]
                          for c in comparisons if isinstance(c, dict))
        need(number(power.get("alpha"), "power alpha", 0.000000001, 0.1) <= alpha / family_size + 1e-12,
             "power analysis must account for the prespecified family multiplicity")
        mode = comp.get("analysis_mode")
        need(mode in {"paired_t", "registered_result"}, "unsupported analysis mode")
        if mode == "paired_t":
            need(power.get("method") in {"ttest_paired", "ttest_one_sample", "monte_carlo_simulation"},
                 "paired inference requires compatible paired or simulation power analysis")
        for key in ("unit_column", "value_column"):
            text(comp.get(key), key)
        need(comp["unit_column"] != comp["value_column"], "unit and value columns must differ")
        need(comp.get("aggregation") == "mean_within_unit_then_mean_across_seeds",
             "declare the aggregation that prevents seed/row pseudoreplication")
        pairs = comp.get("pairs")
        need(isinstance(pairs, list) and bool(pairs), "comparison needs executable pairs")
        seeds, used = set(), set()
        for pair in pairs:
            need(isinstance(pair, dict) and type(pair.get("seed")) is int, "pair needs an integer seed")
            need(pair["seed"] not in seeds, "duplicate comparison seed")
            seeds.add(pair["seed"])
            for arm in ("treatment", "comparator"):
                binding = pair.get(arm)
                need(isinstance(binding, dict), "both comparison arms need run/output bindings")
                run_id = binding.get("run_id")
                need(run_id in runs and run_id in design.get("run_ids", []),
                     "comparison run must belong to its paper and design")
                need(run_id not in pilots and run_id not in used, "pilot or reused run cannot masquerade as an independent arm")
                used.add(run_id)
                condition = (design_id, comp["dataset_id"], "proposed" if arm == "treatment" else comparator)
                need(run_id not in run_conditions or run_conditions[run_id] == condition,
                     "one run cannot be relabeled as different datasets or comparator conditions")
                run_conditions[run_id] = condition
                need(runs[run_id].get("seed") == pair["seed"], "paired runs must use the declared seed")
                need(pilots & ancestors(run_id), "each comparison arm must depend on a successful pilot")
                output = text(binding.get("output"), "comparison output")
                path_in(project, output)
                need(output in runs[run_id].get("expected_outputs", []), "comparison output is not executor-declared")
        need(seeds == set(design.get("seeds", [])), "each comparator must cover every preregistered seed")
        if mode == "registered_result":
            binding = comp.get("registered_result")
            need(isinstance(binding, dict), "registered_result needs an analysis run/output")
            run_id = binding.get("run_id")
            need(run_id in runs and run_id in design.get("run_ids", []) and run_id not in pilots,
                 "custom analysis must belong to the same paper/design")
            need(binding.get("output") in runs[run_id].get("expected_outputs", []),
                 "custom statistical result must be an executor output")
            text(binding.get("method_id"), "registered method_id")
            need(used <= ancestors(run_id), "custom analysis must depend on every comparison arm")
    need(covered_claims == claims, "every contracted claim needs confirmatory primary comparisons")
    for design_id, design in designs.items():
        group = coverage[design_id]
        baseline_ids = {item["id"] for item in design.get("baselines", [])}
        need(group["primary"] == baseline_ids, f"{design_id}: primary comparisons must cover exactly all declared baselines")
        for (covered_design, claim), baselines in claim_baselines.items():
            if covered_design == design_id:
                need(baselines == baseline_ids, f"{claim}: primary evidence must include every declared baseline")
        need(group["hypotheses"] == set(design.get("hypothesis_ids", [])),
             f"{design_id}: primary comparisons must cover all hypotheses")
        for role, field in (("ablation", "ablations"), ("negative_control", "negative_controls"), ("robustness", "robustness_checks")):
            need(group[role] == set(design.get(field, [])),
                 f"{design_id}: executable {role} comparisons must match every declared design item")
    external = protocol.get("external_validity")
    need(isinstance(external, dict) and external.get("mode") in {"tested", "scope_limited"},
         "external_validity must declare tested or scope_limited")
    text(external.get("rationale"), "external-validity rationale")
    if external["mode"] == "tested":
        need(any(comp["role"] == "external_validation" for comp in comparisons),
             "external validity claim needs an actual comparison")
    else:
        text(external.get("claim_limit"), "scope-limited claim boundary")
    return protocol


def _bound_output(project: Path, binding: dict, registry: list[dict], plan_hash: str) -> tuple[Path, dict]:
    attempts = [r for r in registry if r.get("run_id") == binding["run_id"]]
    need(len(attempts) == 1, "evidence needs exactly one retained attempt per run; repeated attempts require inspected protocol repair")
    attempt = attempts[0]
    need(attempt.get("status") == "succeeded" and attempt.get("approved_plan_sha256") == plan_hash,
         "comparison run failed, is missing, or belongs to another plan")
    receipt = path_in(project, f"experiments/runs/{attempt['attempt_id']}/run.json")
    need(read(receipt) == attempt, "comparison lacks its matching executor receipt")
    outputs = [p for p in attempt.get("outputs", []) if p.get("path") == binding["output"]]
    need(len(outputs) == 1, "comparison output is absent or ambiguous in the registry")
    path = path_in(project, binding["output"])
    need(path.is_file() and sha(path) == outputs[0]["sha256"], "comparison output hash changed")
    return path, {"run_id": binding["run_id"], "attempt_id": attempt["attempt_id"],
                  "path": binding["output"], "sha256": outputs[0]["sha256"]}


def _unit_values(path: Path, comp: dict) -> dict[str, float]:
    need(path.stat().st_size <= MAX_CSV_BYTES, "unit-level CSV exceeds the analysis byte ceiling")
    grouped: dict[str, list[float]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.DictReader(handle)
        need(rows.fieldnames is not None and len(set(rows.fieldnames)) == len(rows.fieldnames)
             and {comp["unit_column"], comp["value_column"]} <= set(rows.fieldnames),
             "unit-level CSV needs unique unit/value columns")
        for index, row in enumerate(rows):
            need(index < MAX_ROWS and None not in row, "malformed or oversized unit-level CSV")
            unit = text(row.get(comp["unit_column"]), "independent unit ID").strip()
            try:
                value = float(row[comp["value_column"]])
            except (ValueError, TypeError) as exc:
                raise EvidenceError("non-numeric observation; no silent missing-data exclusion") from exc
            number(value, "observation")
            grouped[unit].append(value)
    need(bool(grouped), "unit-level CSV is empty")
    return {unit: statistics.fmean(values) for unit, values in grouped.items()}


def _measure(project: Path, comp: dict, registry: list[dict], plan_hash: str, family_size: int) -> dict:
    sources, per_seed, expected = [], [], None
    for pair in comp["pairs"]:
        paths = []
        for arm in ("treatment", "comparator"):
            path, source = _bound_output(project, pair[arm], registry, plan_hash)
            sources.append(source)
            paths.append(path)
        treatment, comparator = [_unit_values(path, comp) for path in paths]
        need(treatment.keys() == comparator.keys(), "paired unit IDs differ; dropping unmatched units is forbidden")
        if expected is None:
            expected = set(treatment)
        need(set(treatment) == expected, "unit coverage changes across seeds")
        sign = 1 if comp["direction"] == "higher" else -1
        per_seed.append({unit: sign * (treatment[unit] - comparator[unit]) for unit in treatment})
    units = sorted(expected or [])
    need(len(units) >= comp["minimum_units"], "fewer independent units than preregistered")
    deltas = [statistics.fmean(seed[unit] for seed in per_seed) for unit in units]
    confidence = 1 - comp["alpha"] / family_size
    if comp["analysis_mode"] == "paired_t":
        from scipy import stats
        need(statistics.variance(deltas) > 0, "zero observed variation cannot establish population uncertainty; inspect the method")
        result = stats.ttest_1samp(deltas, popmean=0, nan_policy="raise")
        interval = result.confidence_interval(confidence_level=confidence)
        margin = comp["minimum_effect"]
        if comp["decision_rule"] == "equivalence":
            p = max(float(stats.ttest_1samp(deltas, -margin, alternative="greater").pvalue),
                    float(stats.ttest_1samp(deltas, margin, alternative="less").pvalue))
        else:
            p = float(stats.ttest_1samp(deltas, margin, alternative="greater").pvalue)
        measured = {"estimate": statistics.fmean(deltas), "ci_low": float(interval.low),
                    "ci_high": float(interval.high), "p_value": p, "ci_confidence": confidence,
                    "method": "paired unit means, Student t; TOST for equivalence",
                    "recomputed_from_units": True}
    else:
        path, source = _bound_output(project, comp["registered_result"], registry, plan_hash)
        need(path.stat().st_size <= 100_000, "registered result exceeds the byte ceiling")
        custom = read(path)
        need(custom.get("schema_version") == "1.0" and custom.get("comparison_id") == comp["comparison_id"],
             "custom result comparison identity differs")
        need(custom.get("method_id") == comp["registered_result"]["method_id"]
             and custom.get("decision_rule") == comp["decision_rule"], "custom method/decision rule differs")
        need(all(custom.get(key) == comp[key] for key in ("direction", "minimum_effect", "aggregation", "analysis_unit")),
             "custom null threshold, direction or unit definition differs")
        need(custom.get("independent_units") == len(units), "custom result independent-unit count differs")
        expected_sources = {item["path"]: item["sha256"] for item in sources}
        need(custom.get("source_hashes") == expected_sources, "custom analysis source hashes do not match all registered arms")
        measured = {key: number(custom.get(key), key) for key in ("estimate", "ci_low", "ci_high", "p_value", "ci_confidence")}
        need(confidence - 1e-12 <= measured["ci_confidence"] < 1, "custom interval lacks the preregistered family coverage")
        need(measured["ci_low"] <= measured["estimate"] <= measured["ci_high"], "custom confidence interval is incoherent")
        number(measured["p_value"], "p_value", 0, 1)
        measured.update(method=custom["method_id"], recomputed_from_units=False)
        sources.append(source)
    for key in ("estimate", "ci_low", "ci_high", "p_value"):
        number(measured[key], key)
    seed_effects = [statistics.fmean(seed.values()) for seed in per_seed]
    return {**measured, "independent_units": len(units), "seeds": len(per_seed),
            "seed_effects": seed_effects,
            "seed_effect_sd": statistics.stdev(seed_effects) if len(seed_effects) > 1 else None,
            "aggregation": comp["aggregation"], "sources": sources}


def build_report(project: Path, paper_id: str) -> dict:
    errors = validate_plan(project, paper_id)
    report = {"schema_version": "1.0", "paper_id": paper_id, "status": "blocked",
              "scientific_completion_verified": False, "errors": errors, "comparisons": []}
    if errors:
        return report
    protocol = read(paper_plan(project, paper_id))
    plan_path, registry_path = project / "experiments/plan.json", project / "experiments/registry.jsonl"
    prereg_path = project / "papers" / paper_id / "preregistration.json"
    from scripts.research_quality import validate_preregistration
    try:
        errors.extend(validate_preregistration(read(prereg_path), paper_id, project))
        registry = [json.loads(line) for line in registry_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        from scripts.results_validation import validate_registry
        errors.extend(validate_registry(project, read(plan_path), registry))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
        return report
    if errors:
        return report
    report["protocol_sha256"] = sha(paper_plan(project, paper_id))
    report["preregistration_sha256"] = sha(prereg_path)
    report["registry_sha256"] = sha(registry_path)
    report["approved_plan_sha256"] = sha(plan_path)
    report["implementation_sha256"] = sha(Path(__file__))
    try:
        report["software"] = {name: importlib.metadata.version(name) for name in ("scipy", "statsmodels")}
    except importlib.metadata.PackageNotFoundError:
        errors.append("Install the research-quality runtime before computing statistical evidence")
        return report
    families: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    for comp in protocol["comparisons"]:
        family_size = sum(c["family"] == comp["family"] and c["analysis_phase"] == comp["analysis_phase"]
                          for c in protocol["comparisons"])
        row = {key: comp[key] for key in ("comparison_id", "design_id", "hypothesis_id", "claim_ids",
               "role", "analysis_phase", "family", "alpha", "decision_rule", "minimum_effect", "analysis_unit")}
        try:
            row.update(_measure(project, comp, registry, sha(plan_path), family_size))
            row["status"] = "computed"
        except (EvidenceError, OSError, ValueError, KeyError, TypeError) as exc:
            row.update(status="blocked", error=str(exc), p_value=1.0)
            errors.append(f"{comp['comparison_id']}: {exc}")
        families[comp["family"] + ":" + comp["analysis_phase"]].append((comp, row))
        report["comparisons"].append(row)
    from statsmodels.stats.multitest import multipletests
    for group in families.values():
        adjusted = multipletests([row["p_value"] for _, row in group], method="holm")[1]
        for (comp, row), p_adjusted in zip(group, adjusted):
            row["p_adjusted"] = float(p_adjusted)
            row["family_size"] = len(group)
            row["decision"] = "incomplete"
            if row["status"] != "computed":
                continue
            low, high, margin = row["ci_low"], row["ci_high"], comp["minimum_effect"]
            threshold_met = (low > -margin and high < margin) if comp["decision_rule"] == "equivalence" else low > margin
            row["decision"] = ("meets_preregistered_threshold"
                               if threshold_met and p_adjusted <= comp["alpha"] else "does_not_establish_claim")
            if comp["analysis_phase"] == "exploratory":
                row["decision"] = "exploratory_only"
    report["status"] = "complete" if not errors else "blocked"
    report["interpretation"] = ("Numeric evidence only. Paired t inference assumes independent units and suitable "
        "difference distributions; repeated rows and seeds are averaged within units. Registered custom analyses "
        "are hash-checked but not statistically recomputed here. Human scientific review remains required.")
    return report


def refresh(project: Path) -> dict:
    from scripts.researchctl import write_json
    from scripts.output_provenance import record_model_writes
    summaries = {}
    for paper in sorted((project / "papers").glob("P[0-9][0-9]")):
        report = build_report(project, paper.name)
        path = paper / REPORT
        write_json(path, report)
        record_model_writes(project, [path], family="other", provider="deterministic-experiment-evidence",
                            model="scripts/experiment_evidence.py", role="statistical-auditor", run_id="evidence-refresh")
        summaries[paper.name] = {"status": report["status"], "errors": report["errors"]}
    return summaries


def validate_report(project: Path, paper_id: str) -> list[str]:
    try:
        expected = build_report(project, paper_id)
        saved = read(project / "papers" / paper_id / REPORT)
        errors = list(expected["errors"])
        if saved != expected:
            errors.append("experiment evidence report is stale or not produced by the current control plane")
        return errors
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        return [str(exc)]
