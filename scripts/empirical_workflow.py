"""Optional empirical contracts within the existing stages, gates and freezes."""
from __future__ import annotations
import re
from pathlib import Path
from scripts.research_artifacts import path_in, read


def requirements(project, paper_id):
    if not re.fullmatch(r"P[0-9]{2}", paper_id):
        raise ValueError("explicit paper ID required")
    contract_path = project/f"papers/{paper_id}/paper-contract.json"
    contract = read(contract_path) if contract_path.is_file() else {}
    value = contract.get("empirical_workflow", {})
    if not isinstance(value, dict) or set(value) - {"data_contract_ids", "causal_design", "reporting", "economic_request_ids"}:
        raise ValueError("invalid empirical_workflow declaration")
    declared, economic = value.get("data_contract_ids", []), value.get("economic_request_ids", [])
    for items in (declared, economic):
        if not isinstance(items, list) or len(items) > 30 or any(
                not isinstance(i, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,100}", i) for i in items) or len(set(items)) != len(items):
            raise ValueError("unique bounded empirical dataset/request IDs required")
    datasets = contract.get("datasets", [])
    if set(declared) - set(datasets):
        raise ValueError("data contracts must belong to this paper's declared datasets")
    ids = set(declared) | {i for i in datasets if (project/f"data/contracts/{i}.json").is_file()
                          or (project/f"reports/data-contracts/{i}.json").is_file()}
    causal, reporting = value.get("causal_design", False), value.get("reporting", False)
    if type(causal) is not bool or type(reporting) is not bool:
        raise ValueError("empirical feature declarations must be explicit booleans")
    card_path = project/f"papers/{paper_id}/empirical-design.json"
    causal = causal or card_path.is_file() or (project/f"papers/{paper_id}/reviews/empirical-design.json").is_file()
    if card_path.is_file():
        dataset = read(card_path).get("dataset_id")
        if dataset not in datasets:
            raise ValueError("empirical estimator dataset must belong to its paper contract")
        ids.add(dataset)
    return {"data_contract_ids": sorted(ids), "causal_design": causal, "reporting": reporting or causal, "economic_request_ids": economic}


def papers(project, paper_id=None):
    return [paper_id] if paper_id else [p.name for p in sorted((project/"papers").glob("P[0-9][0-9]"))]


def preregistration_inputs(project, paper_id):
    from scripts import data_contracts, empirical_design
    wanted, inputs = requirements(project, paper_id), {}
    for dataset in wanted["data_contract_ids"]:
        checked = data_contracts.audit(project, dataset)
        if checked["errors"]:
            raise ValueError("cannot freeze invalid data contract: " + "; ".join(checked["errors"]))
        inputs.update({r["path"]: path_in(project, r["path"]) for r in checked["inputs"]})
        preview = project/f"data/processed-preview/{dataset}.csv"
        if preview.is_file():
            issues = data_contracts.validate_preview(project, dataset)
            if issues:
                raise ValueError("cannot freeze stale prepared data: " + "; ".join(issues))
            for file in (preview, project/f"reports/data-cleaning/preview-{dataset}.json"):
                inputs[file.relative_to(project).as_posix()] = file
    if wanted["causal_design"]:
        checked = empirical_design.audit(project, paper_id)
        if checked["status"] == "not_configured" or checked["errors"]:
            raise ValueError("cannot freeze missing/invalid empirical design: " + "; ".join(checked["errors"]))
        inputs.update({r["path"]: path_in(project, r["path"]) for r in checked["sources"]})
    for request_id in wanted["economic_request_ids"]:
        from scripts import economic_data
        issues = economic_data.validate_saved_report(project, request_id)
        if issues:
            raise ValueError("cannot freeze invalid economic source: " + "; ".join(issues))
        for relative in (f"data/economic-requests/{request_id}.json", f"evidence/economic-data/{request_id}/latest.json"):
            inputs[relative] = path_in(project, relative)
    return list(inputs.values())


def preflight_run(project, run):
    """Inspect native runtime commands before the existing G3 runner launches."""
    from scripts import data_contracts, empirical_design
    from scripts.research_artifacts import sha
    argv = run.get("argv", [])
    if len(argv) < 2 or argv[0] not in {"python", "python3"}:
        return
    script = path_in(project, argv[1], exists=False) if isinstance(argv[1], str) and argv[1].endswith(".py") else None
    if script is None:
        return
    if script.name == "empirical_runtime.py":
        checked = empirical_design.audit(project, run["paper_id"], require_frozen=True)
        if checked["status"] == "not_configured" or checked["errors"]:
            raise ValueError("native empirical runtime requires current frozen design: " + "; ".join(checked["errors"]))
    if argv[1] == "analysis/data_cleaning_runtime.py":
        if len(argv) != 10 or argv[2::2] != ["--contract", "--dataset-id", "--output", "--receipt"]:
            raise ValueError("use the exact standalone cleaning command")
        dataset, output, receipt = argv[5], argv[7], argv[9]
        if argv[3] != f"data/contracts/{dataset}.json" or run.get("cwd", ".") != ".":
            raise ValueError("cleaning requires canonical contract and project-root cwd")
        runtime = Path(__file__).with_name("data_cleaning_runtime.py")
        if not script.is_file() or sha(script) != sha(runtime):
            raise ValueError("standalone cleaning runtime differs from the reviewed implementation")
        checked = data_contracts.audit(project, dataset)
        if checked["errors"]:
            raise ValueError("data cleaning preflight: " + "; ".join(checked["errors"]))
        declared = {row["path"]:row["sha256"] for row in run.get("inputs", [])}
        required = [*checked["inputs"], {"path": argv[1], "sha256": sha(runtime)}]
        if any(declared.get(row["path"]) != row["sha256"] for row in required):
            raise ValueError("cleaning run must declare every frozen source and its reviewed runtime")
        if (set(run.get("expected_outputs", [])) != {output, receipt} or not output.startswith("data/processed/")
                or not output.endswith(".csv") or not receipt.startswith("reports/data-cleaning/") or not receipt.endswith(".json")):
            raise ValueError("cleaning outputs differ from the exact controlled CSV/receipt paths")


def cloud_outputs_allowed(project, run):
    outputs = run.get("expected_outputs", [])
    if outputs and all(p.startswith("results/") for p in outputs):
        return True
    try:
        preflight_run(project, run)
        if run.get("argv", [None, None])[1] == "analysis/data_cleaning_runtime.py":
            return True
        card = read(path_in(project, f"papers/{run['paper_id']}/empirical-design.json"))
        matches = [s for s in [*card["specifications"], *card["diagnostics"]] if s["run_id"] == run["run_id"]]
        return bool(matches) and {s["output"] for s in matches} == set(outputs) and all(
            p.startswith(f"papers/{run['paper_id']}/results/") and p.endswith(".json") for p in outputs)
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        return False


def gate_errors(project, gate, paper_id=None):
    if gate not in {"G3", "G4", "G5"}:
        return []
    from scripts import data_contracts, empirical_design, empirical_reporting, economic_data
    errors = []
    for paper in papers(project, paper_id if gate == "G5" else None):
        try:
            wanted = requirements(project, paper)
            for dataset in wanted["data_contract_ids"]:
                errors.extend(data_contracts.validate_saved_report(project, dataset))
                if (project/f"data/processed-preview/{dataset}.csv").is_file():
                    errors.extend(data_contracts.validate_preview(project, dataset))
            if wanted["causal_design"]:
                check = empirical_design.audit(project, paper, require_frozen=gate != "G3")
                errors.extend(check["errors"])
                if check["status"] == "not_configured":
                    errors.append(paper + ": required empirical design missing")
                elif gate != "G3":
                    errors.extend(empirical_design.validate_saved_report(project, paper))
            if wanted["reporting"] and gate != "G3":
                errors.extend(empirical_reporting.validate_saved_report(project, paper, require_mapping=gate == "G5"))
            for request_id in wanted["economic_request_ids"]:
                errors.extend(economic_data.validate_saved_report(project, request_id))
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError) as exc:
            errors.append(paper + ": " + str(exc))
    return errors


def refresh(project, stage, paper_id=None):
    from scripts import data_contracts, empirical_design, empirical_reporting
    result = {"status": "not_configured", "errors": [], "datasets": {}, "papers": {}, "paid_calls": 0}
    for paper in papers(project, paper_id if stage == "writing-and-review" else None):
        try:
            wanted = requirements(project, paper)
            for dataset in wanted["data_contract_ids"]:
                if dataset not in result["datasets"]:
                    checked = data_contracts.refresh(project, dataset)
                    result["datasets"][dataset] = {"pass": checked["pass"], "errors": checked["errors"]}
                    result["errors"].extend(checked["errors"])
            if wanted["causal_design"]:
                checked = empirical_design.refresh(project, paper)
                result["papers"][paper] = {"design_status": checked["status"], "errors": list(checked["errors"])}
                result["errors"].extend(checked["errors"])
                if stage in {"experiment-execution", "writing-and-review"}:
                    table = empirical_reporting.refresh(project, paper, require_mapping=stage == "writing-and-review")
                    result["papers"][paper]["reporting_status"] = table["status"]
                    result["errors"].extend(table["errors"])
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError) as exc:
            result["errors"].append(paper + ": " + str(exc))
    if result["datasets"] or result["papers"] or result["errors"]:
        result["status"] = "blocked" if result["errors"] else "ready_for_scientific_review"
    return result
