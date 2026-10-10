"""Hash-bound page/line indexes from an already rendered manuscript PDF.

The cloud controller calls this only after its source-bound renderer succeeds.
This module reads PDF bytes; it never renders, calls a model or invents pages.
"""
from __future__ import annotations

from pathlib import Path

try:
    from scripts.citation_audit import manuscript_digest, tex_source_paths
    from scripts.ref_verify_adapter import canonical_manuscript
    from scripts.research_artifacts import path_in, read, record, sha, write
except ImportError:
    from citation_audit import manuscript_digest, tex_source_paths  # type: ignore
    from ref_verify_adapter import canonical_manuscript  # type: ignore
    from research_artifacts import path_in, read, record, sha, write  # type: ignore


def source_hashes(paper: Path) -> list[dict]:
    main = canonical_manuscript(paper)
    sources = tex_source_paths(main) if main.suffix.lower() == ".tex" else {main.resolve()}
    return [{"path": item.relative_to(paper.resolve()).as_posix(), "sha256": sha(item)}
            for item in sorted(sources)]


def pdf_pages(pdf: Path) -> list[dict]:
    try:
        import fitz
    except ImportError as exc:
        raise ValueError("PyMuPDF is required to verify actual rendered PDF locations") from exc
    if pdf.stat().st_size > 100_000_000:
        raise ValueError("rendered manuscript PDF exceeds the 100 MB indexing limit")
    try:
        with fitz.open(pdf) as document:
            if document.needs_pass or not 1 <= len(document) <= 1000:
                raise ValueError("rendered PDF is encrypted, empty or exceeds 1000 pages")
            pages = []
            for index, page in enumerate(document, 1):
                lines = []
                for block in page.get_text("dict", sort=True)["blocks"]:
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        text = "".join(str(span.get("text", "")) for span in line.get("spans", []))
                        if text.strip():
                            lines.append(text)
                pages.append({"page": index, "lines": lines})
            return pages
    except (RuntimeError, OSError) as exc:
        raise ValueError(f"cannot read rendered manuscript PDF: {exc}") from exc


def validate_render_receipt(paper: Path, pdf: Path, receipt_path: Path) -> dict:
    from scripts.output_provenance import current_origin
    paper = paper.resolve()
    project = paper.parents[1]
    relative = receipt_path.resolve().relative_to(paper).as_posix()
    receipt_path = path_in(paper, relative)
    value = read(receipt_path)
    if value.get("schema_version") != "1.0" or value.get("status") != "pass":
        raise ValueError("PDF locations need a passing real cloud rendering receipt")
    execution, renderer = value.get("execution", {}), value.get("renderer", {})
    if not isinstance(execution, dict) or execution.get("mode") != "cloud" or not isinstance(execution.get("receipt_id"), str) or not execution["receipt_id"].strip():
        raise ValueError("rendering receipt lacks cloud execution identity")
    # Only the implemented manuscript-to-PDF renderer can attest this relation.
    if not isinstance(renderer, dict) or renderer.get("name") != "cloud_runtime" or renderer.get("implementation_sha256") != sha(Path(__file__).resolve().parent / "cloud_runtime.py"):
        raise ValueError("rendering receipt is stale or unsupported for the real renderer implementation")
    def artifacts(key):
        items = value.get(key)
        if not isinstance(items, list) or not items:
            raise ValueError("rendering receipt needs nonempty inputs and outputs")
        bound = {}
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise ValueError("invalid rendering receipt artifact")
            target = path_in(project, item["path"])
            if item["path"] in bound or sha(target) != item.get("sha256"):
                raise ValueError("duplicate or stale rendering receipt artifact")
            bound[item["path"]] = item["sha256"]
        return bound
    inputs, outputs = artifacts("inputs"), artifacts("outputs")
    for item in source_hashes(paper):
        source_relative = (paper / item["path"]).relative_to(project).as_posix()
        if inputs.get(source_relative) != item["sha256"]:
            raise ValueError("rendering receipt does not bind every current canonical manuscript source")
    if outputs.get(pdf.resolve().relative_to(project).as_posix()) != sha(pdf):
        raise ValueError("rendering receipt does not bind the actual PDF output")
    origin = current_origin(project, receipt_path)
    if any(origin.get(key) != expected for key, expected in {"status": "tracked", "family": "other", "provider": "cloud-tex-renderer", "role": "render-receipt"}.items()):
        raise ValueError("rendering receipt lacks protected deterministic control-plane provenance")
    return {"path": relative, "sha256": sha(receipt_path)}


def build_render_manifest(paper: Path, pdf: Path, renderer: str, renderer_version: str,
                          *, rendering_receipt: Path | None = None) -> dict:
    paper = paper.resolve()
    if not str(renderer).strip() or not str(renderer_version).strip():
        raise ValueError("render manifest needs the actual renderer name and version")
    try:
        relative = pdf.resolve().relative_to(paper).as_posix()
    except ValueError as exc:
        raise ValueError("rendered PDF must belong to the canonical paper") from exc
    pdf = path_in(paper, relative)
    if pdf.suffix.lower() != ".pdf":
        raise ValueError("render manifest requires an actual PDF file")
    pages = pdf_pages(pdf)
    main = canonical_manuscript(paper)
    result = {"schema_version": "1.0", "status": "pass", "generated_by": "scripts/revision_render.py",
              "manuscript_sha256": manuscript_digest(main), "source_hashes": source_hashes(paper),
              "pdf": {"path": relative, "sha256": sha(pdf)}, "page_count": len(pages), "pages": pages,
              "renderer": {"name": renderer.strip(), "version": renderer_version.strip()},
              "line_numbering": "1-based nonempty extracted text lines in PyMuPDF sorted reading order",
              "printed_line_numbers_verified": False, "visual_review_required": True}
    if rendering_receipt is None:
        raise ValueError("build the source-bound cloud rendering receipt before indexing PDF pages")
    result["rendering_receipt"] = validate_render_receipt(paper, pdf, rendering_receipt)
    target = paper / "reviews/revision-render.json"
    write(target, result)
    record(paper.parents[1], [target], "scripts/revision_render.py")
    return result


def validate_render_manifest(paper: Path) -> tuple[dict, list[dict]]:
    path = path_in(paper, "reviews/revision-render.json")
    saved = read(path)
    if saved.get("schema_version") != "1.0" or saved.get("status") != "pass" or saved.get("generated_by") != "scripts/revision_render.py":
        raise ValueError("rendered page locations require a protected passing controller manifest")
    if saved.get("manuscript_sha256") != manuscript_digest(canonical_manuscript(paper)) or saved.get("source_hashes") != source_hashes(paper):
        raise ValueError("rendered page/line manifest is stale for the canonical manuscript sources")
    renderer = saved.get("renderer", {})
    if not isinstance(renderer, dict) or any(not str(renderer.get(key, "")).strip() for key in ("name", "version")):
        raise ValueError("render manifest lacks the actual renderer identity/version")
    output = saved.get("pdf")
    if not isinstance(output, dict):
        raise ValueError("render manifest lacks its PDF output")
    pdf = path_in(paper, output.get("path", ""))
    if pdf.suffix.lower() != ".pdf" or sha(pdf) != output.get("sha256"):
        raise ValueError("rendered PDF changed after the source-bound render")
    receipt = saved.get("rendering_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("rendered page locations require a real cloud rendering receipt")
    if validate_render_receipt(paper, pdf, path_in(paper, receipt.get("path", ""))) != receipt:
        raise ValueError("rendering receipt changed after page indexing")
    pages = pdf_pages(pdf)
    if saved.get("pages") != pages or saved.get("page_count") != len(pages):
        raise ValueError("render manifest pages/lines do not match actual PDF text")
    return saved, pages
