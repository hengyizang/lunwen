"""Bounded, deterministic research work around the API author/critic cycle.

Scientific approvals remain in protected records. Generated plans request work;
they cannot grant data rights, fabricate search receipts or authorize experiments.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts import cloud_checkpoint, dataset_fetch, experiment_runner, literature_evidence

REPORT = "state/research-steps.json"
AUTHORIZATIONS = "state/data-authorizations.json"
MAX_DATA_BYTES = 2_000_000_000


class ResearchStepError(RuntimeError):
    pass


def read(path: Path, default=None):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def path_in(project: Path, relative: str) -> Path:
    relative = cloud_checkpoint.relative(relative)
    path = project / relative
    if any(p.is_symlink() for p in (path, *path.parents) if p == project or project in p.parents):
        raise ResearchStepError("research inputs cannot be symlinks")
    return path


def fresh(receipt: dict, project: Path, days: int = 7) -> bool:
    try:
        at = datetime.fromisoformat(receipt["completed_at"])
        if at.tzinfo is None or not timedelta(0) <= datetime.now(timezone.utc) - at < timedelta(days=days):
            return False
        for field, digest in (("raw_response_path", "response_sha256"),
                              ("normalized_results_path", "normalized_results_sha256")):
            if cloud_checkpoint.sha(path_in(project, receipt[field])) != receipt[digest]:
                return False
        return receipt.get("status") == "success"
    except (ValueError, KeyError, OSError, ResearchStepError):
        return False


def literature_context(project: Path, query: str) -> dict:
    plan = read(project / "program/literature-search-plan.json")
    if plan is None:
        providers = ["crossref", "arxiv", "openalex" if os.environ.get("OPENALEX_API_KEY") else "hal"]
        searches = [{"provider": provider, "query": text, "query_family": family, "limit": 15}
                    for family, text in (("direct", query), ("adjacent", query + " baseline benchmark"),
                                         ("counterevidence", query + " limitations failure robustness"))
                    for provider in providers]
    else:
        searches = plan.get("searches")
    if not isinstance(searches, list) or not 1 <= len(searches) <= 60:
        raise ResearchStepError("literature-search-plan needs 1–60 explicit searches")
    ledger = literature_evidence.read_jsonl(project / "evidence/literature-api-ledger.jsonl")
    searches_done = literature_evidence.read_jsonl(project / "evidence/search-log.jsonl")
    families = {r.get("evidence_receipt_id"): r.get("query_family") for r in searches_done}
    results, errors, works = [], [], []
    calls = 0
    pending = 0
    attempts_path = project / "state/literature-attempts.json"
    attempts = read(attempts_path, {})
    for item in searches:
        provider, text = item.get("provider"), item.get("query", "")
        family, limit = item.get("query_family"), item.get("limit", 15)
        if (provider not in literature_evidence.DEFAULT_SEARCH_PROVIDERS or not isinstance(text, str)
                or not 1 <= len(text.strip()) <= 1000 or not isinstance(family, str) or not family.strip()
                or type(limit) is not int or not 1 <= limit <= 50):
            raise ResearchStepError("search plan uses an invalid or unmetered provider/query/limit")
        cached = next((r for r in reversed(ledger) if r.get("provider") == provider and r.get("query") == text.strip()
                       and families.get(r.get("receipt_id")) == family and fresh(r, project)), None)
        if cached is None:
            key = hashlib.sha256(json.dumps(item, sort_keys=True).encode()).hexdigest()
            failed = attempts.get(key, {})
            if failed.get("at") and datetime.now(timezone.utc) - datetime.fromisoformat(failed["at"]) < timedelta(hours=6):
                errors.append({"provider": provider, "query_family": family, "error": failed["error"]})
                continue
            if calls >= 6:
                pending += 1
                continue
            calls += 1
            try:
                cached = literature_evidence.execute_search(project, provider, text,
                    query_family=family, date_range="all indexed years; inspect dates before claiming novelty",
                    filters="unfiltered relevance discovery; pending human screening", limit=limit)
            except (literature_evidence.LiteratureEvidenceError, OSError, ValueError) as exc:
                errors.append({"provider": provider, "query_family": family, "error": str(exc)[:500]})
                attempts[key] = {"at": datetime.now(timezone.utc).isoformat(), "error": str(exc)[:500]}
                continue  # One failed database must not suppress other providers.
        results.append(cached)
        normalized = read(path_in(project, cached["normalized_results_path"]), {"works": []})
        works.extend(normalized.get("works", [])[:15])
    write(attempts_path, attempts)
    return {"receipts": results, "works": works[:90], "provider_errors": errors,
            "pending_searches": pending, "new_search_calls": calls,
            "human_screening_required": True, "novelty_proven": False}


def authorize_data(project: Path, relative: str, expected_sha256: str, actor: str, run_id: str) -> dict:
    manifest_path = path_in(project, relative)
    if not relative.startswith("data/manifests/") or manifest_path.suffix != ".json":
        raise ResearchStepError("authorize an exact data/manifests/*.json file")
    if cloud_checkpoint.sha(manifest_path) != expected_sha256 or not actor.strip():
        raise ResearchStepError("data authorization must name the reviewer and exact reviewed manifest hash")
    manifest = dataset_fetch.load_manifest(manifest_path)
    errors = dataset_fetch.validate_manifest(manifest)
    if errors or manifest["license"].get("confirmed_by_human") is not True:
        raise ResearchStepError("review data license, privacy and cloud-use rights before authorizing acquisition")
    download = manifest["download"]
    if (not re.fullmatch(r"[a-fA-F0-9]{64}", download["sha256"])
            or type(download.get("expected_bytes")) is not int or not 0 < download["expected_bytes"] <= MAX_DATA_BYTES):
        raise ResearchStepError("cloud acquisition needs a pinned checksum and a positive byte ceiling up to 2 GB")
    values = read(project / AUTHORIZATIONS, {"schema_version": "1.0", "manifests": {}})
    values["manifests"][relative] = {"sha256": expected_sha256, "actor": actor, "source_run_id": str(run_id),
                                    "cloud_use_confirmed": True, "confirmed_at": datetime.now(timezone.utc).isoformat()}
    write(project / AUTHORIZATIONS, values)
    return values["manifests"][relative]


def acquire_data(project: Path) -> dict:
    authorizations = read(project / AUTHORIZATIONS, {}).get("manifests", {})
    acquired, blockers = [], []
    manifests = sorted((project / "data/manifests").glob("*.json"))
    for manifest_path in manifests:
        relative = manifest_path.relative_to(project).as_posix()
        auth = authorizations.get(relative, {})
        if auth.get("sha256") != cloud_checkpoint.sha(manifest_path) or auth.get("cloud_use_confirmed") is not True:
            blockers.append({"kind": "data_rights_review", "path": relative, "sha256": cloud_checkpoint.sha(manifest_path)})
            continue
        manifest = dataset_fetch.load_manifest(manifest_path)
        identifier = manifest.get("dataset_id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,100}", identifier):
            raise ResearchStepError("invalid dataset identifier")
        filename = dataset_fetch.safe_filename(manifest)
        if "\\" in filename or ":" in filename:
            raise ResearchStepError("unsafe dataset filename")
        destination = path_in(project, f"data/raw/{identifier}")
        target = destination / filename
        pinned = manifest["download"]["sha256"].lower()
        if not target.is_file() or cloud_checkpoint.sha(target) != pinned:
            if target.exists():
                raise ResearchStepError("downloaded dataset changed; inspect it before reacquiring")
            target = dataset_fetch.download_dataset(manifest_path, destination, True,
                        min(MAX_DATA_BYTES, manifest["download"]["expected_bytes"]), False)
        receipt = {"schema_version": "1.0", "dataset_id": identifier, "manifest_path": relative,
                   "manifest_sha256": auth["sha256"], "authorization": auth,
                   "path": target.relative_to(project).as_posix(), "sha256": cloud_checkpoint.sha(target),
                   "bytes": target.stat().st_size}
        if receipt["sha256"] != pinned or receipt["bytes"] != manifest["download"]["expected_bytes"]:
            raise ResearchStepError("authorized dataset checksum/size mismatch")
        write(project / "data/acquisition" / f"{identifier}.json", receipt)
        acquired.append(receipt)
    return {"acquired": acquired, "blockers": blockers}


def resume_experiments(project: Path) -> dict:
    plan_path, budget_path = project / "experiments/plan.json", project / "experiments/budget.json"
    plan, _ = experiment_runner.approved_plan(project, plan_path, budget_path)
    plan_sha = cloud_checkpoint.sha(plan_path)
    registry = literature_evidence.read_jsonl(project / "experiments/registry.jsonl")
    completed, failures = set(), []
    for record in registry:
        if record.get("approved_plan_sha256") != plan_sha:
            raise ResearchStepError("experiment registry differs from the approved plan; inspection required")
        receipt = path_in(project, f"experiments/runs/{record['attempt_id']}/run.json")
        if read(receipt) != record:
            raise ResearchStepError("experiment registry lacks its matching executor receipt")
        if record.get("status") != "succeeded":
            failures.append(record["attempt_id"])
        else:
            for output in record.get("outputs", []):
                if cloud_checkpoint.sha(path_in(project, output["path"])) != output["sha256"]:
                    raise ResearchStepError("registered experiment output changed or was not restored")
            completed.add(record["run_id"])
    if failures:
        return {"blockers": [{"kind": "experiment_inspection", "attempt_ids": failures}], "pending_runs": 0}
    pending = [run for run in plan["runs"] if run["run_id"] not in completed]
    if not pending:
        return {"completed_runs": sorted(completed), "pending_runs": 0, "blockers": []}
    run = pending[0]
    if (run["isolation"]["kind"] != "container" or run["isolation"]["engine"] != "docker"
            or run["timeout_seconds"] > 1200 or any(not p.startswith("results/") for p in run["expected_outputs"])):
        return {"pending_runs": len(pending), "blockers": [{"kind": "cloud_experiment_plan",
                 "detail": "Use a pinned Docker image, <=1200 seconds per run and explicit results/ outputs"}]}
    results = experiment_runner.execute(project.name, [run["run_id"]], project_root=project)
    result = results[0]
    return {"executed_attempt": result["attempt_id"], "pending_runs": len(pending) - 1,
            "blockers": [] if result["status"] == "succeeded" else [{"kind": "experiment_inspection", "attempt_ids": [result["attempt_id"]]}]}


def before_cycle(project: Path, stage: str) -> dict:
    report = {"schema_version": "1.0", "stage": stage, "blockers": [], "control_only": False}
    if stage in {"topic-intelligence", "experiment-design", "experiment-execution", "writing-and-review"}:
        report["data"] = acquire_data(project)
        report["blockers"].extend(report["data"]["blockers"])
    if stage == "experiment-execution":
        if report["blockers"]:
            report["control_only"] = True
        else:
            report["experiments"] = resume_experiments(project)
            report["blockers"].extend(report["experiments"].get("blockers", []))
            # One real attempt/checkpoint per job; only analyze once all planned
            # runs have completed. A failed attempt is retained and never retried.
            report["control_only"] = bool(report["experiments"].get("executed_attempt") or report["blockers"])
            if not report["control_only"] and report["experiments"].get("pending_runs") == 0:
                from scripts.experiment_evidence import refresh
                report["statistical_evidence"] = refresh(project)
                for paper, evidence in report["statistical_evidence"].items():
                    if evidence["status"] != "complete":
                        report["blockers"].append({"kind": "experiment_inspection", "paper_id": paper,
                                                   "detail": evidence["errors"]})
                report["control_only"] = bool(report["blockers"])
        from scripts.research_quality import refresh_runtime_evidence_catalog
        refresh_runtime_evidence_catalog(project)
    write(project / REPORT, report)
    return report


def after_write(project: Path, stage: str) -> dict:
    """Run declared deterministic builders; never treat model output as a receipt."""
    from scripts import research_quality
    report = read(project / REPORT, {"schema_version": "1.0", "stage": stage, "blockers": []})
    report["operation_errors"] = []
    if stage == "topic-intelligence":
        from scripts import direction_evidence
        try:
            report["direction_ranking"] = direction_evidence.refresh(project)
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            report["operation_errors"].append({"action": "direction_ranking", "error": str(exc)[:700]})
    queue = read(project / "program/cloud-operations.json", {"operations": []})
    operations = queue.get("operations", [])
    if not isinstance(operations, list) or len(operations) > 16:
        raise ResearchStepError("cloud-operations needs an array of at most 16 operations")
    if sum(op.get("action") == "direction_search" for op in operations) > 1:
        raise ResearchStepError("at most one direction_search operation (three queries) per cycle")
    cache_path = project / "state/cloud-operations-cache.json"
    cache = read(cache_path, {})
    for operation in operations:
        if operation.get("stage") != stage:
            continue
        action = operation.get("action")
        operation_sha = hashlib.sha256(json.dumps(operation, sort_keys=True).encode()).hexdigest()
        try:
            if action == "data_quality" and stage == "experiment-design":
                identifier = operation["dataset_id"]
                if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,100}", identifier):
                    raise ResearchStepError("invalid dataset identifier")
                source = path_in(project, operation["path"])
                if not source.exists():
                    continue  # The data-rights/acquisition report supplies the blocker.
                output = project / "data/quality" / f"{identifier}.json"
                old = read(output)
                if (old and cache.get(str(output.relative_to(project))) == operation_sha
                        and not research_quality.validate_data_quality_report(old, identifier, project)):
                    continue
                result = research_quality.create_data_quality_report(project, identifier, operation["path"],
                    actor="cloud-control-plane", label_column=operation.get("label_column"),
                    split_column=operation.get("split_column"), group_column=operation.get("group_column"))
                write(output, result)
                cache[str(output.relative_to(project))] = operation_sha
            elif action == "power" and stage == "experiment-design":
                paper = operation["paper_id"]
                if not re.fullmatch(r"P[0-9]{2}", paper):
                    raise ResearchStepError("invalid paper ID")
                args = {k: operation[k] for k in ("method", "effect_size", "alpha", "target_power", "ratio", "effect_size_basis")}
                output = project / "papers" / paper / "power-analysis.json"
                old = read(output)
                if (old and cache.get(str(output.relative_to(project))) == operation_sha
                        and not research_quality.validate_power_report(old, paper, project)):
                    continue
                result = research_quality.create_power_report(project, paper, **args, groups=operation.get("groups", 2))
                write(output, result)
                cache[str(output.relative_to(project))] = operation_sha
            elif action == "render_figure" and stage == "writing-and-review":
                from scripts.publication_figures import render
                render(project, path_in(project, operation["spec"]))
            elif action == "read_paper" and stage == "topic-intelligence":
                from scripts.paper_reader import build
                source = path_in(project, operation["pdf"])
                output = path_in(project, operation["output"])
                if not operation["output"].startswith("literature/readers/"):
                    raise ResearchStepError("readers belong under literature/readers/")
                if not source.is_file():
                    report["blockers"].append({"kind": "authorized_fulltext", "path": operation["pdf"]})
                    continue
                manifest_rel = operation["manifest"]
                authorization = read(project / AUTHORIZATIONS, {}).get("manifests", {}).get(manifest_rel, {})
                manifest_path = path_in(project, manifest_rel)
                manifest = read(manifest_path, {})
                if (authorization.get("sha256") != cloud_checkpoint.sha(manifest_path)
                        or manifest.get("license", {}).get("redistribution_allowed") is not True
                        or manifest.get("download", {}).get("sha256") != cloud_checkpoint.sha(source)):
                    raise ResearchStepError("persisted cloud readers require an owner-reviewed redistributable full-text manifest")
                if not output.exists():
                    build(project, source, output, max_pages=operation.get("max_pages", 30), translate=False)
            elif action == "docx" and stage == "writing-and-review":
                from scripts.manuscript_docx import build
                source, metadata = path_in(project, operation["source"]), path_in(project, operation["metadata"])
                build(project, source, metadata, path_in(project, operation["output"]), prefer_pandoc=False)
            elif action == "statistical_reporting" and stage == "writing-and-review":
                from scripts.statistical_reporting import refresh
                refresh(project, operation["paper_id"])
            elif action == "docx_revision" and stage == "writing-and-review":
                from scripts.docx_revision import build
                build(project, operation["paper_id"])
            elif action == "research_notebook" and stage in {"topic-intelligence", "paper-architecture", "experiment-design", "experiment-execution", "writing-and-review"}:
                from scripts.research_notebook import refresh
                refresh(project)
            elif action == "research_notebook_daily" and stage in {"topic-intelligence", "paper-architecture", "experiment-design", "experiment-execution", "writing-and-review"}:
                from scripts.research_notebook import daily_brief
                daily_brief(project)
            elif action == "revision_ledger" and stage == "writing-and-review":
                from scripts.revision_ledger import refresh
                refresh(project, operation["paper_id"])
            elif action == "research_support" and stage in {"topic-intelligence", "paper-architecture", "experiment-design", "experiment-execution", "writing-and-review"}:
                from scripts.research_support import refresh
                refresh(project)
            elif action == "support_sources" and stage in {"topic-intelligence", "paper-architecture", "experiment-design", "writing-and-review"}:
                from scripts.research_support import fetch_sources
                fetch_sources(project)
            elif action == "review_packets" and stage in {"topic-intelligence", "paper-architecture", "experiment-design", "experiment-execution", "writing-and-review"}:
                from scripts.review_packets import refresh
                refresh(project)
            elif action == "method_tools" and stage in {"experiment-design", "experiment-execution"}:
                from scripts.method_tools import refresh
                refresh(project)
            elif action == "journal_dossiers" and stage in {"paper-architecture", "writing-and-review"}:
                from scripts.journal_dossier import refresh
                refresh(project)
            elif action == "journal_sources" and stage in {"paper-architecture", "writing-and-review"}:
                from scripts.journal_dossier import fetch_sources
                fetch_sources(project)
            elif action == "compile_tex" and stage == "writing-and-review":
                from scripts.cloud_runtime import compile_tex
                compile_tex(project, operation["paper_id"])
            elif action == "citation_graph" and stage == "topic-intelligence":
                ledger = literature_evidence.read_jsonl(project / "evidence/literature-api-ledger.jsonl")
                if not any(r.get("mode") == "citation_graph" and r.get("query") == operation["doi"]
                           and r.get("direction") == operation["direction"] and fresh(r, project) for r in ledger):
                    literature_evidence.execute_citation_graph(project, operation["doi"], direction=operation["direction"],
                        date_range="all indexed years", filters="citation chaining; pending human screening")
            elif action == "triage_leads" and stage == "topic-intelligence":
                from scripts.lead_triage import triage
                triage(project, operation["receipt_id"], operation["provider"], operation.get("limit", 5))
            elif action == "direction_search" and stage == "topic-intelligence":
                from scripts.web_research import search
                queries = operation["queries"]
                if not isinstance(queries, list) or not 1 <= len(queries) <= 3:
                    raise ResearchStepError("direction_search requires 1–3 public search queries")
                for query in queries:
                    search(query, project_root=project)
            else:
                raise ResearchStepError("operation is unsupported in this stage; no arbitrary commands or approvals are allowed")
        except (ValueError, OSError, RuntimeError, KeyError, TypeError, ImportError) as exc:
            report["operation_errors"].append({"action": action, "error": str(exc)[:700]})
    write(project / REPORT, report)
    write(cache_path, cache)
    return report
