"""Credential-free cloud acceptance against an actual CC-BY published paper.

This is an isolated engineering fixture. Its deliberately named machine fixture
authority is never written into a research project and does not approve G0-G5,
choose a doctoral topic, or claim that a person has read or reviewed the paper.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts import literature_assets, literature_workbench, literaturectl, paper_reader
from scripts.network_safety import fetch_bytes
from scripts.research_artifacts import read, record, sha, write


PUBLISHER = "https://joss.theoj.org/papers/10.21105/joss.03021"
PDF_URL = PUBLISHER + ".pdf"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
IDENTIFIER = "waskom-2021-seaborn"
EXPECTED_CAPTION = "An example seaborn figure demonstrating some of its key features."


def _fixture_authority(project: Path, pdf_relative: str, rights_evidence: dict) -> str:
    """Bind the test's reviewed source in a fresh, explicitly isolated test root."""
    marker = project / "ACCEPTANCE-FIXTURE-ONLY.json"
    if (not marker.is_file() or read(marker) != {"engineering_fixture_only": True,
            "production_owner_approval": False} or project.name != "real-paper-acceptance-fixture"):
        raise ValueError("Fixture authorization cannot be created in a production project")
    authority = project / "state/data-authorizations.json"
    if authority.exists():
        raise ValueError("Acceptance refuses to modify any existing authority")
    pdf = project / pdf_relative
    manifest_relative = "data/manifests/acceptance-seaborn-cc-by.json"
    manifest = {"schema_version": "1.0", "dataset_id": "acceptance-seaborn-cc-by",
        "purpose": "engineering-acceptance-only; no thesis selection or scientific approval",
        "source_url": PDF_URL, "license": {"name": "CC-BY-4.0", "url": LICENSE_URL,
            "redistribution_allowed": True, "attribution_required": True,
            "attribution": "Michael L. Waskom (2021), seaborn: statistical data visualization, JOSS 6(60), 3021. DOI:10.21105/joss.03021",
            "primary_evidence": rights_evidence},
        "download": {"sha256": sha(pdf), "expected_bytes": pdf.stat().st_size},
        "engineering_fixture_only": True, "production_owner_approval": False}
    write(project / manifest_relative, manifest)
    write(authority, {"engineering_fixture_only": True, "production_owner_approval": False,
        "manifests": {manifest_relative: {"sha256": sha(project / manifest_relative),
            "actor": "isolated-acceptance-fixture-machine-NOT-project-owner",
            "cloud_use_confirmed": True, "basis": "publisher CC-BY-4.0 source permission verified for this fixture only"}}})
    return manifest_relative


def demonstrate(directory: Path) -> dict:
    literaturectl.require_cloud()
    directory = Path(directory).resolve()
    project = directory / "real-paper-acceptance-fixture"
    if project.exists():
        raise ValueError("Real-paper acceptance needs a fresh output directory")
    project.mkdir(parents=True)
    write(project / "ACCEPTANCE-FIXTURE-ONLY.json", {"engineering_fixture_only": True,
        "production_owner_approval": False})
    # Verify rights from the actual publisher, not from a search snippet or DOI.
    html, final, status, content_type = fetch_bytes(PUBLISHER, max_bytes=2 * 1024 * 1024,
        timeout=45, headers={"Accept": "text/html", "User-Agent": "DoctoralResearchOS/real-paper-acceptance"})
    if status != 200 or "creativecommons.org/licenses/by/4.0" not in html.decode("utf-8", errors="replace"):
        raise ValueError("Publisher did not confirm the expected CC-BY-4.0 source license")
    rights = {"url": PUBLISHER, "final_url": final, "sha256": literature_assets.digest(html),
        "content_type": content_type, "accessed_at": literature_assets.utc_now(),
        "license_url": LICENSE_URL, "verification": "publisher HTML explicitly links CC-BY-4.0"}
    rights_path = project / "evidence/source-rights/publisher.html"
    rights_path.parent.mkdir(parents=True)
    rights_path.write_bytes(html)
    rights["path"] = rights_path.relative_to(project).as_posix()
    acquisition = literature_assets.resolve(project, PDF_URL)
    if acquisition.get("pdf_status") != "acquired":
        raise ValueError("Actual CC-BY paper could not be acquired: " + json.dumps(acquisition.get("failures")))
    pdf_relative = acquisition["local_pdf"]
    manifest_relative = _fixture_authority(project, pdf_relative, rights)
    pdf = literaturectl.approved_pdf(project, pdf_relative, manifest_relative)
    reader_path = project / "literature/readers/seaborn.md"
    reader = paper_reader.build(project, pdf, reader_path, max_pages=6, translate=False)
    figures = literature_assets.extract(project, pdf_relative, source=acquisition,
        question="seaborn example key features", max_selected=1)
    captions = [item for item in figures["caption_discovery"]["candidates"]
        if item["figure_number"] == "1" and item["pdf_page"] == 2]
    if len(captions) != 1 or EXPECTED_CAPTION.casefold() not in captions[0]["caption"].casefold():
        raise ValueError("Actual Figure 1 caption was not recovered from PDF page 2")
    selected = [occ for asset in figures["assets"] for occ in asset["occurrences"]
        if occ["kind"] == "caption_context_crop" and occ["figure_number"] == "1" and occ["pdf_page"] == 2]
    if not selected or not selected[0].get("caption_bbox"):
        raise ValueError("Actual source Figure 1 has no source-bound positioned preview")
    reused_figures = literature_assets.extract(project, pdf_relative, source=acquisition,
        question="seaborn example key features", max_selected=1)
    if not reused_figures.get("cache_hit") or reused_figures["manifest_sha256"] != figures["manifest_sha256"]:
        raise ValueError("Unchanged actual source figures were needlessly parsed or rendered again")
    paper = {"id": IDENTIFIER, "title": "seaborn: statistical data visualization",
        "topic_id": "engineering-acceptance-only", "paper_ids": [], "url": PUBLISHER,
        "source": {"path": pdf_relative, "sha256": sha(pdf)}, "source_scope": "full_text_extracted_not_human_reviewed",
        "manifest": manifest_relative, "reader": {"path": reader["reader"], "sha256": sha(reader_path)},
        "figure_manifest": {"path": figures["manifest_path"], "sha256": figures["manifest_sha256"]}}
    blocks, _ = literaturectl.source_blocks(project, paper)
    example_block = next((b for b in blocks if b["pdf_page"] == 2 and "sns.relplot" in b["text"]), None)
    if example_block is None:
        raise ValueError("Native reader did not recover the actual plotting example on PDF page 2")
    offset, line = next((i, line) for i, line in enumerate(example_block["text"].splitlines()) if "sns.relplot" in line)
    anchor = {"path": example_block["path"], "sha256": example_block["sha256"],
        "start_line": example_block["start_line"] + offset,
        "end_line": example_block["start_line"] + offset, "quote": "sns.relplot", "pdf_page": 2}
    card = {"schema_version": "1.0", "paper_id": IDENTIFIER,
        "fields": {field: [] for field in literaturectl.FIELDS}}
    card["fields"]["methods"] = [{"text": "The paper includes a plotting example using sns.relplot.",
        "kind": "author_claim", "evidence": [anchor]}]
    literaturectl.validate_card(card, IDENTIFIER, blocks)
    card_path = project / "literature/cards/seaborn.json"
    write(card_path, card)
    record(project, [card_path], "scripts/literature_real_acceptance.py")
    paper["card"] = {"path": card_path.relative_to(project).as_posix(), "sha256": sha(card_path)}
    write(project / literature_workbench.CONFIG, {"schema_version": "1.0", "papers": [paper]})
    built = literature_workbench.build(project)
    if built.get("status") == "blocked":
        raise ValueError("Production workbench rejected the actual source fixture: " + json.dumps(built.get("errors")))
    search = literature_workbench.search(project, "sns.relplot fmri")
    hits = [item for item in search["results"] if item.get("paper_id") == IDENTIFIER and item.get("pdf_page") == 2]
    if not hits:
        raise ValueError("Original example could not be retrieved through the production workbench")
    repeated = literature_workbench.build(project)
    if IDENTIFIER not in repeated["reused_papers"]:
        raise ValueError("Actual source was needlessly reread instead of hash-bound reuse")
    # Rights are checked on each use: revocation must also invalidate cached views.
    authority_path = project / "state/data-authorizations.json"
    authority = read(authority_path)
    authority["manifests"][manifest_relative]["cloud_use_confirmed"] = False
    write(authority_path, authority)
    try:
        literature_workbench.search(project, "sns.relplot")
    except ValueError:
        revocation_blocked = True
    else:
        raise ValueError("Revoked source rights did not block cached original-paper access")
    finally:
        authority["manifests"][manifest_relative]["cloud_use_confirmed"] = True
        write(authority_path, authority)
    result = {"schema_version": "1.0", "engineering_status": "pass",
        "real_published_source": True, "paid_model_calls": 0, "scientific_completion_verified": False,
        "production_owner_approval": False, "fixture_only_authority": True,
        "source": {"doi": "10.21105/joss.03021", "publisher": PUBLISHER, "pdf": PDF_URL,
            "sha256": sha(pdf), "license": "CC-BY-4.0", "rights_evidence": rights},
        "checks": {"actual_figure_number": "1", "actual_pdf_page": 2,
            "positioned_caption_verified": True, "exact_visual_boundary_verified": False,
            "native_example_source_anchor": anchor, "example_retrieved_at_original_page": True,
            "source_hash_bound_reuse": True, "original_figure_extraction_reused": True,
            "revoked_rights_block_cached_use": revocation_blocked},
        "workbench": built, "figure_manifest": paper["figure_manifest"]}
    write(directory / "real-paper-acceptance.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/literature-real-paper"))
    args = parser.parse_args()
    print(json.dumps(demonstrate(args.directory), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
