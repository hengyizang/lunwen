"""Inspect actual vector output; numerical data and image pixels are never edited."""
from __future__ import annotations
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET


def audit_outputs(project: Path, outputs: list[dict], expected_text: list[str] | None = None) -> dict:
    result = {"schema_version": "1.0", "errors": [], "outputs": [],
              "grayscale_and_color_vision_human_review_required": True,
              "scientific_data_checked": False}
    for item in outputs:
        original = project / item["path"]
        path = original.resolve()
        if not path.is_relative_to(project.resolve()) or not path.is_file() or any(p.is_symlink() for p in (original, *original.parents)):
            result["errors"].append("unsafe or missing figure output")
            continue
        row = {"path": item["path"], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        if row["sha256"] != item["sha256"]:
            result["errors"].append(f"{item['path']}: hash changed")
        if path.suffix == ".svg":
            try:
                tree = ET.parse(path)
                texts = ["".join(node.itertext()).strip() for node in tree.iter()
                         if node.tag.endswith("}text") or node.tag == "text"]
                row["editable_text_nodes"] = len(texts)
                if not texts:
                    result["errors"].append(f"{item['path']}: no editable SVG text")
                joined = " ".join(texts)
                for label in expected_text or []:
                    if label and label not in joined:
                        result["errors"].append(f"{item['path']}: missing expected editable label {label}")
                row["fonts"] = sorted({part.strip() for node in tree.iter()
                    for part in node.get("style", "").split(";") if "font" in part})
            except ET.ParseError:
                result["errors"].append(f"{item['path']}: malformed SVG")
        if path.suffix == ".pdf":
            try:
                import fitz
                with fitz.open(path) as document:
                    row["physical_pages_mm"] = [[round(page.rect.width * 25.4 / 72, 2), round(page.rect.height * 25.4 / 72, 2)] for page in document]
                    sizes = [span["size"] for page in document for block in page.get_text("dict")["blocks"]
                             for line in block.get("lines", []) for span in line.get("spans", []) if span.get("text", "").strip()]
                    row["minimum_text_points"] = min(sizes) if sizes else None
                    row["small_text_human_review"] = any(size < 6 for size in sizes)
                    row["grayscale_previews"] = []
                    for index, page in enumerate(document):
                        preview = project / "reports/figure-output-qa" / row["sha256"] / f"page-{index + 1}-grayscale.png"
                        preview.parent.mkdir(parents=True, exist_ok=True)
                        page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csGRAY).save(preview)
                        row["grayscale_previews"].append({"path": preview.relative_to(project).as_posix(),
                            "sha256": hashlib.sha256(preview.read_bytes()).hexdigest(), "purpose": "visual_QA_only"})
            except ImportError:
                result["errors"].append("PDF output QA requires the declared PyMuPDF dependency")
            except (RuntimeError, ValueError) as exc:
                result["errors"].append(f"{item['path']}: cannot inspect PDF: {exc}")
        result["outputs"].append(row)
    result["status"] = "pass" if not result["errors"] else "fail"
    return result
