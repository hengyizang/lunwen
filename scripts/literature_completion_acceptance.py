"""Cloud engineering/known-location checks on an actual openly licensed paper.

Primary-source location labels are not an independent blind scientific review.
No provider credentials or paid language-model calls are used by this entrypoint.
"""
import argparse
import base64
import io
import json
import re
from pathlib import Path
from scripts import literature_real_acceptance as original
from scripts import literature_semantic as semantic, literature_pdf, literature_comparison as comparison
from scripts import literature_reading as reading, literature_workbench as wb, literature_benchmark
from scripts import literature_paperqa
from scripts.research_artifacts import read, sha, write


def demonstrate(directory):
    directory = Path(directory).resolve()
    original.demonstrate(directory / "source")
    project = directory / "source/real-paper-acceptance-fixture"
    paper_id = original.IDENTIFIER
    library, _, _ = wb._snapshot(project)
    paper = next(p for p in library["papers"] if p["id"] == paper_id)
    from scripts.literaturectl import source_blocks
    blocks, _ = source_blocks(project, paper)
    cases, summaries = [], []
    for number, (marker, question) in enumerate((
        ("matplotlib", "Which underlying plotting library does this package extend?"),
        ("sns.relplot", "How is the relationship plotting example invoked?"),
        ("pandas", "Which data frame ecosystem integrates with the plotting interface?"))):
        matches = [(b, i, line) for b in blocks for i, line in enumerate(b["text"].splitlines()) if marker in line.casefold()]
        if not matches:
            raise ValueError("Actual paper no longer contains the declared location marker: " + marker)
        block, offset, line = matches[0]
        anchor = {"paper_id": paper_id, "path": block["path"], "sha256": block["sha256"],
            "start_line": block["start_line"] + offset, "end_line": block["start_line"] + offset,
            "quote": re.search(re.escape(marker), line, re.I)[0], "pdf_page": block["pdf_page"]}
        request = {"schema_version": "1.0", "question": question, "paper_ids": [paper_id], "limit": 6}
        request_path = f"program/semantic-case-{number}.json"
        write(project / request_path, {"schema_version": "1.0", "retrieval": request, "rerank": True})
        ranked = semantic.refresh(project, request_path)
        semantic.validate_saved_report(project, request_path)
        sdk_path = f"program/sdk-case-{number}.json"
        write(project / sdk_path, {"schema_version": "1.0", "id": f"public-case-{number}",
            "retrieval": request, "semantic_request": request_path,
            "semantic": {"path": "reports/literature-semantic/latest.json", "sha256": sha(project / "reports/literature-semantic/latest.json")}})
        sdk = literature_paperqa.refresh(project, sdk_path)
        literature_paperqa.validate_saved_report(project, sdk_path)
        repeated = semantic.refresh(project, request_path)
        if not repeated.get("complete_result_cache_hit"):
            raise ValueError("unchanged real source ranking should reuse the complete result")
        benchmark = literature_benchmark.evaluate(project, {"schema_version": "1.0",
            "annotation": {"kind": "primary_source_fixture", "by": "machine-curated real-paper location probes; NOT independent semantic gold"},
            "cases": [{"id": f"location-{number}", "request": ranked["retrieval_request"], "relevant": [anchor]}]})
        cases.append({"id": f"case-{number}", "request": ranked["retrieval_request"], "relevant": [anchor], "expected_abstain": False})
        summaries.append({"marker": marker, "question": question,
            "metrics": benchmark["cases"][0], "index_cache_hit": ranked["corpus_index_cache_hit"],
            "result_cache_hit": repeated["complete_result_cache_hit"], "embedding_execution": ranked["index_execution"],
            "reranker_execution": ranked["reranker_execution"], "sdk_receipt": sdk, "semantic_support_verified": False})
    compare_spec = {"schema_version": "1.0", "id": "public-paper", "annotation": {
        "kind": "primary_source_fixture", "by": "source-bound known-location probes; no independent human rating"},
        "cases": cases, "max_full_text_chars": 120000}
    write(project / "program/literature-comparison.json", compare_spec)
    plan = comparison.refresh(project)
    comparison.validate_saved_report(project)
    sentence_index = reading.build_index(project, paper_id)
    selected = [s["sentence_id"] for s in sentence_index["sentences"] if s["pdf_page"] == 2 and "sns.relplot" in s["quote"]]
    if not selected:
        raise ValueError("real plotting example sentence missing")
    write(project / "program/literature-pdf.json", {"schema_version": "1.0", "id": "public-paper",
        "paper_id": paper_id, "pages": [2], "sentence_ids": selected, "annotate_pdf": True})
    pdf = literature_pdf.refresh(project)
    literature_pdf.validate_saved_report(project)
    if not pdf["original_bytes_preserved"] or not pdf["annotations"]:
        raise ValueError("real PDF annotation must preserve original bytes and locate a real sentence")
    # Preserve a small actual page/overlay image for remote visual QA. Rendering
    # and image preparation happen here on the cloud, never on the owner's PC.
    from PIL import Image, ImageDraw
    page = pdf["pages"][0]
    with Image.open(project / page["image"]["path"]) as image:
        image = image.convert("RGB")
        image.thumbnail((900, 1200))
        drawing = ImageDraw.Draw(image, "RGBA")
        scale_x, scale_y = image.width / page["page_size"][0], image.height / page["page_size"][1]
        for sentence in pdf["sentences"]:
            if sentence["pdf_page"] == page["pdf_page"] and sentence.get("rects"):
                for x0, y0, x1, y1 in sentence["rects"]:
                    drawing.rectangle((x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y), fill=(255, 210, 0, 65), outline=(160, 100, 0, 255), width=1)
        preview = directory / "pdf-overlay-preview.png"
        image.save(preview)
    result = {"schema_version": "1.0", "status": "engineering_acceptance_pass",
        "real_published_source": True, "doi": "10.21105/joss.03021", "location_cases": summaries,
        "paired_reading_plan": plan, "pdf_overlay": {"html": pdf["html"], "annotations": len(pdf["annotations"])},
        "paid_calls": 0, "model_answer_comparison_executed": False,
        "independent_human_semantic_review_completed": False, "route_promoted": False,
        "scientific_completion_verified": False}
    write(directory / "acceptance.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("VISUAL_QA_PNG_BASE64=" + base64.b64encode(preview.read_bytes()).decode("ascii"))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("artifacts/literature-completion"))
    demonstrate(parser.parse_args().directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
