"""Cloud acceptance demonstration; fixture behavior is not scientific validation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from scripts import literature_evidence, literature_workbench, literaturectl
from scripts.research_artifacts import record, sha, write


def demonstrate(directory: Path, live: bool = False) -> dict:
    literaturectl.require_cloud()
    directory.mkdir(parents=True, exist_ok=True)
    installed = literaturectl.install()
    project = directory / "fixture-project"
    papers = []
    for identifier, text in (
        ("fixture-a", "SOFTWARE FIXTURE ONLY.\nThe baseline uses logistic regression.\nEvaluation uses held-out devices.\n"),
        ("fixture-b", "SOFTWARE FIXTURE ONLY.\nThe comparison uses calibration error.\nAblation removes the device identifier.\n")):
        path = project / "evidence/sources" / (identifier + ".txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        papers.append({"id": identifier, "title": "Synthetic reading demonstration " + identifier,
            "topic_id": "software-fixture", "paper_ids": ["P01", "P02"],
            "source": {"path": path.relative_to(project).as_posix(), "sha256": sha(path)}})
    write(project / literature_workbench.CONFIG, {"schema_version": "1.0", "papers": papers})
    first = literature_workbench.build(project)
    search = literature_workbench.search(project, "baseline devices", topic_id="software-fixture")
    itinerary = literature_workbench.itinerary(project, "baseline comparison devices", topic_id="software-fixture")
    comparison = literature_workbench.comparison_packet(project, [p["id"] for p in papers])
    repeated = literature_workbench.build(project)
    if not search["results"] or set(repeated["reused_papers"]) != {p["id"] for p in papers}:
        raise ValueError("Source-bound retrieval/reuse acceptance failed")
    if comparison.get("experiment_executed") or first.get("scientific_completion_verified"):
        raise ValueError("Software fixture must not certify science")
    probe = {"requested": live, "paid_model_calls": 0, "results": []}
    if live:
        target = directory / "metadata-connectivity-only"
        for provider, query in (("crossref", "Attention Is All You Need"), ("arxiv", "1706.03762"),
                                ("dblp", "*")):
            try:
                receipt = literature_evidence.execute_search(target, provider, query,
                    query_family="engineering_connectivity_probe_not_thesis_selection",
                    date_range="2017-2018" if provider != "dblp" else "2025",
                    filters={"venue": "conf/icml", "year": 2025, "transport": "search"} if provider == "dblp" else {},
                    limit=2)
                normalized = json.loads((target / receipt["normalized_results_path"]).read_text(encoding="utf-8"))
                probe["results"].append({"provider": provider, "status": receipt["status"],
                    "works": len(normalized.get("works", [])), "receipt_id": receipt["receipt_id"],
                    "record_identity_and_semantics_verified": False})
            except (ValueError, RuntimeError, OSError) as exc:
                probe["results"].append({"provider": provider, "status": "unavailable",
                                         "error": str(exc)[-800:]})
        probe["all_providers_returned_records"] = all(r.get("works", 0) > 0 for r in probe["results"])
    result = {"schema_version": "1.0", "engineering_status": "pass",
        "fixture_only": True, "scientific_completion_verified": False, "paid_model_calls": 0,
        "installed": installed, "workbench": first, "reused_papers": repeated["reused_papers"],
        "retrieval": {"matched_blocks": search["matched_blocks"]},
        "itinerary_steps": len(itinerary["steps"]), "metadata_connectivity": probe}
    write(directory / "acceptance.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/literature-workbench"))
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    print(json.dumps(demonstrate(args.directory, args.live), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
