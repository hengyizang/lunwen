"""Failure lessons become bounded checker candidates, never self-approved policy."""
from __future__ import annotations

from scripts.incremental_evidence import anchor, binding, digest, identifier, rows, strings, text
from scripts.research_artifacts import path_in, read, write, record

ROOT = "reports/research-increments"


def checker(value):
    if not isinstance(value, dict) or set(value) != {"op", "terms"}:
        raise ValueError("checker permits only op and bounded literal terms")
    if value["op"] not in {"contains_any", "contains_all", "missing_all"}:
        raise ValueError("checker must be a bounded literal check, never executable code or regex")
    terms = strings(value["terms"], "checker terms", 1)
    if len(terms) > 30 or any(len(term) > 200 for term in terms):
        raise ValueError("checker exceeds literal size limits")
    return value


def predict(rule, content):
    matches = [term.casefold() in content.casefold() for term in rule["terms"]]
    return any(matches) if rule["op"] == "contains_any" else all(matches) if rule["op"] == "contains_all" else not any(matches)


def candidate(row):
    return {"id": identifier(row.get("id")), "rule": checker(row.get("rule")),
            "baseline": checker(row.get("baseline")), "benchmark": binding_spec(row.get("benchmark"))}


def binding_spec(value):
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError("benchmark needs its exact path and SHA256")
    return value


def cases(project, row):
    source = binding(project, row["benchmark"])
    value = read(path_in(project, source["path"]))
    values = rows(value.get("cases"), "frozen paired cases", 600, 6)
    identifiers, identities, splits = set(), {}, {"development": [], "validation": [], "holdout": []}
    for item in values:
        key = identifier(item.get("id"))
        split = item.get("split")
        if key in identifiers or split not in splits or type(item.get("expected_flag")) is not bool:
            raise ValueError("unique case IDs, explicit split and boolean ground truth required")
        identifiers.add(key)
        text(item.get("rationale"), "case ground-truth rationale")
        bound = binding(project, item.get("source"))
        content = path_in(project, bound["path"]).read_text(encoding="utf-8")
        if len(content) > 100_000:
            raise ValueError("rule case exceeds the bounded evaluator")
        # Dedup normalized content AND group identity across splits, including renamed files.
        identity = digest(" ".join(content.casefold().split()))
        group = identifier(item.get("group_id"), "case independence group")
        for token in ("content:" + identity, "group:" + group):
            if token in identities and identities[token] != split:
                raise ValueError("benchmark splits share content or an independence group")
            identities[token] = split
        splits[split].append({**item, "source": bound, "text": content})
    for split, values in splits.items():
        if len(values) < 2 or {item["expected_flag"] for item in values} != {True, False}:
            raise ValueError(split + " needs positive and negative independently grouped cases")
    return source, splits


def freeze(project, row):
    key = identifier(row.get("id"))
    spec = candidate(row)
    source, splits = cases(project, row)
    target = project / ROOT / "rule-benchmarks" / (key + ".json")
    result = {"schema_version": "1.0", "id": key, "candidate_sha256": digest(spec),
              "benchmark": source,
              "cases": {split: [{k: v for k, v in case.items() if k != "text"} for case in values]
                        for split, values in splits.items()},
              "implementation_sha256": implementation(), "adopted": False}
    if target.is_file():
        if read(target) != result:
            raise ValueError("a frozen benchmark/candidate cannot be overwritten; use a new version ID")
        return result
    write(target, result)
    record(project, [target], "incremental-rule-freeze")
    return result


def implementation():
    from scripts.research_artifacts import sha
    return sha(__import__("pathlib").Path(__file__))


def evaluate(project, row):
    from scripts import output_provenance
    key = identifier(row.get("id"))
    lesson = anchor(project, row.get("lesson"))
    if lesson["path"].startswith((ROOT + "/", "state/")):
        raise ValueError("a rule proposal cannot act as its own failure lesson")
    for field in ("failure", "root_cause", "proposed_check", "limitations", "rollback_reason"):
        text(row.get(field), field)
    frozen_path = path_in(project, f"{ROOT}/rule-benchmarks/{key}.json")
    frozen = read(frozen_path)
    source, splits = cases(project, row)
    current = {split: [{k: v for k, v in case.items() if k != "text"} for case in values]
               for split, values in splits.items()}
    origin = output_provenance.current_origin(project, frozen_path)
    if (frozen.get("candidate_sha256") != digest(candidate(row)) or frozen.get("benchmark") != source
            or frozen.get("cases") != current or frozen.get("implementation_sha256") != implementation()
            or origin.get("status") != "tracked" or origin.get("provider") != "deterministic-control-plane"):
        raise ValueError("current candidate and disjoint benchmark must have been frozen before evaluation")
    metrics, regressions = {}, []
    for split, values in splits.items():
        paired = []
        for case in values:
            baseline = predict(checker(row["baseline"]), case["text"])
            proposed = predict(checker(row["rule"]), case["text"])
            truth = case["expected_flag"]
            if baseline == truth and proposed != truth:
                regressions.append(case["id"])
            paired.append({"case_id": case["id"], "expected_flag": truth,
                           "baseline_flag": baseline, "candidate_flag": proposed,
                           "baseline_correct": baseline == truth, "candidate_correct": proposed == truth})
        metrics[split] = {"paired": paired, "n": len(paired),
                          "baseline_errors": sum(not x["baseline_correct"] for x in paired),
                          "candidate_errors": sum(not x["candidate_correct"] for x in paired)}
    independent_improvement = all(metrics[s]["candidate_errors"] < metrics[s]["baseline_errors"]
                                  for s in ("validation", "holdout"))
    eligible = not regressions and independent_improvement
    return {"id": key, "lesson": lesson, "candidate_sha256": digest(candidate(row)),
            "rule": row["rule"], "implementation_sha256": implementation(),
            "metrics": metrics, "regression_case_ids": regressions,
            "status": "eligible_for_owner_review" if eligible else "rejected",
            "reason": "paired disjoint benchmark" if eligible else "regression or no independent strict improvement",
            "adopted": False, "scientific_effectiveness_verified": False,
            "scope": "literal_checker_on_frozen_cases_only", "model_calls": 0}


def active_checks(project, confirmation):
    """Adopted rules remain advisory; they cannot approve science or change models."""
    target = project / "state/research-increment-rules.json"
    if not target.is_file():
        return []
    value = read(target)
    results = []
    from scripts.research_increments import load
    specs = {item["id"]: item for item in load(project).get("lessons", [])}
    for key in strings(value.get("active_ids", []), "active rule IDs"):
        if key not in specs:
            raise ValueError("adopted rule specification disappeared")
        row = specs[key]
        if not confirmation(project, "lesson", key, row, "adopt_rule"):
            raise ValueError("adopted rule authorization is absent or stale")
        audit = evaluate(project, row)
        if audit["status"] != "eligible_for_owner_review":
            raise ValueError("adopted rule no longer passes its frozen benchmark")
        findings = []
        for source in rows(row.get("targets", []), "advisory rule targets", maximum=100):
            bound = binding(project, source)
            content = path_in(project, bound["path"]).read_text(encoding="utf-8")
            if len(content) > 100_000:
                raise ValueError("rule target exceeds the bounded evaluator")
            findings.append({**bound, "flagged": predict(row["rule"], content)})
        results.append({"id": key, "findings": findings, "effect": "advisory_only"})
    return results
