"""Inspect actual vector output; numerical data and image pixels are never edited."""
from __future__ import annotations
import hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
import math
import re
import unicodedata

# Numerical severity-100 matrices from Machado et al. (2009),
# DOI 10.1109/TVCG.2009.113; checked against colorspacious upstream data.
MACHADO_SOURCE = "https://raw.githubusercontent.com/njsmith/colorspacious/master/colorspacious/cvd.py"
MACHADO_100 = {
    "protan": ((0.152286,1.052583,-0.204868),(0.114503,0.786281,0.099216),(-0.003882,-0.048116,1.051998)),
    "deutan": ((0.367322,0.860646,-0.227968),(0.280085,0.672501,0.047413),(-0.011820,0.042940,0.968881)),
    "tritan": ((1.255528,-0.076749,-0.178779),(-0.078411,0.930809,0.147602),(0.004733,0.691367,0.303900)),
}
MATH_SYMBOLS = {
    "alpha":"α","beta":"β","gamma":"γ","delta":"δ","epsilon":"ϵ","varepsilon":"ε","theta":"θ","lambda":"λ","mu":"μ","nu":"ν","pi":"π","rho":"ρ","sigma":"σ","tau":"τ","phi":"ϕ","varphi":"φ","chi":"χ","psi":"ψ","omega":"ω",
    "Gamma":"Γ","Delta":"Δ","Theta":"Θ","Lambda":"Λ","Xi":"Ξ","Pi":"Π","Sigma":"Σ","Phi":"Φ","Psi":"Ψ","Omega":"Ω",
    "pm":"±","mp":"∓","times":"×","cdot":"·","le":"≤","leq":"≤","ge":"≥","geq":"≥","ne":"≠","neq":"≠","approx":"≈","infty":"∞","sum":"∑","prod":"∏","int":"∫","partial":"∂","nabla":"∇","in":"∈","to":"→","sqrt":"√","%":"%","&":"&","_":"_",
    "sin":"sin","cos":"cos","tan":"tan","log":"log","ln":"ln","exp":"exp","min":"min","max":"max","lim":"lim","Pr":"Pr",
}
MATH_WRAPPERS = {"mathrm","mathbf","mathit","mathsf","mathtt","mathnormal","text","operatorname","left","right","displaystyle"}
MATH_SPACING = {",",";",":","!"," ","quad","qquad"}
MATH_STRUCTURE = {"frac","dfrac","tfrac","overline","underline","hat","widehat","bar","vec","dot","ddot"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compact_text(value):
    return "".join(unicodedata.normalize("NFKC", value).replace("−", "-").split())


def expected_glyphs(label):
    unknown, structural = [], []
    def command(match):
        name = match.group(1)
        if name == "_":
            return "\ue000"
        if name in MATH_SYMBOLS:
            if name == "sqrt":
                structural.append("sqrt-layout")
            return MATH_SYMBOLS[name]
        if name in MATH_WRAPPERS or name in MATH_SPACING:
            return ""
        if name in MATH_STRUCTURE:
            structural.append(name)
            return ""
        unknown.append(name)
        return ""
    display = re.sub(r"\\([A-Za-z]+|.)", command, label)
    if "$" in display:
        for char in "$^_{}":
            display = display.replace(char, "")
    display = display.replace("\ue000", "_")
    return {"display":display,"signature":compact_text(display),"math":"$" in label,
            "unknown_commands":sorted(set(unknown)),"structural_commands":sorted(set(structural))}


def verify_labels(text_nodes, expected):
    checks, errors, pending = [], [], []
    for value in expected:
        entry = {"text":value,"role":"label"} if isinstance(value,str) else value
        label, role = entry["text"], str(entry.get("role","label"))
        glyphs = expected_glyphs(label)
        present = bool(glyphs["signature"] and any(glyphs["signature"] in compact_text(text) for text in text_nodes))
        row = {"text":label,"role":role,"source":entry.get("source"),**glyphs,
               "glyphs_verified":present and not glyphs["unknown_commands"],"mathematical_layout_verified":False if glyphs["math"] else None}
        if glyphs["unknown_commands"] or glyphs["structural_commands"]:
            row["status"] = "review_required"
            pending.append(f"{role}: TeX command/structure requires human inspection: {label}")
        elif not present:
            row["status"] = "fail"
            errors.append(f"missing expected editable label/glyphs ({role}): {label}")
        else:
            row["status"] = "pass"
        checks.append(row)
    return checks, errors, pending


def simulate_rgb(rgb, mode):
    import numpy as np
    if mode not in MACHADO_100:
        raise ValueError("unknown color-vision simulation")
    encoded = np.asarray(rgb,dtype=float) / 255.0
    if encoded.ndim < 1 or encoded.shape[-1] != 3 or not np.isfinite(encoded).all() or np.any(encoded<0) or np.any(encoded>1):
        raise ValueError("simulation requires finite RGB channels between 0 and 255")
    linear = np.where(encoded<=0.04045, encoded/12.92, ((encoded+0.055)/1.055)**2.4)
    transformed = np.clip(linear @ np.asarray(MACHADO_100[mode],dtype=float).T,0.0,1.0)
    result = np.where(transformed<=0.0031308, transformed*12.92, 1.055*transformed**(1.0/2.4)-0.055)
    return np.rint(np.clip(result,0.0,1.0)*255.0).astype(np.uint8)


def final_size_qa(page_sizes,text_sizes,final_width_mm=None):
    if final_width_mm is not None and (isinstance(final_width_mm,bool) or not isinstance(final_width_mm,(int,float)) or not math.isfinite(final_width_mm) or final_width_mm<=0):
        raise ValueError("final_width_mm must be a positive finite number")
    checks=[]
    for index,(width,height) in enumerate(page_sizes):
        scale=float(final_width_mm)/width if final_width_mm is not None else 1.0
        effective=[size*scale for size in text_sizes[index]]
        checks.append({"page":index+1,"actual_pdf_size_mm":[width,height],"final_size_mm":[round(width*scale,3),round(height*scale,3)],
            "uniform_scale":scale,"minimum_final_text_points":min(effective) if effective else None,
            "maximum_final_text_points":max(effective) if effective else None,"text_span_count":len(effective),
            "minimum_review_threshold_points":6.0,"status":"review_required" if not effective or any(size<6 for size in effective) else "pass",
            "dimensions_source":"actual PDF page box","manuscript_placement_verified":False})
    return checks


def audit_outputs(project: Path, outputs: list[dict], expected_text=None, *, final_width_mm=None) -> dict:
    project = project.resolve()
    result = {"schema_version": "1.0", "errors": [], "outputs": [],
              "pending_human_checks": [], "visual_review_required": True, "accessibility_verified": False,
              "color_vision_model": {"doi": "10.1109/TVCG.2009.113", "severity": 100, "matrix_source": MACHADO_SOURCE,
                                     "linear_srgb": True, "gamut_clipping": True, "individual_vision_not_predicted": True},
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
                checks, errors, pending = verify_labels(texts, expected_text or [])
                row["label_checks"] = checks
                result["errors"].extend(f"{item['path']}: {error}" for error in errors)
                result["pending_human_checks"].extend(f"{item['path']}: {check}" for check in pending)
                row["fonts"] = sorted({part.strip() for node in tree.iter()
                    for part in node.get("style", "").split(";") if "font" in part})
            except ET.ParseError:
                result["errors"].append(f"{item['path']}: malformed SVG")
        if path.suffix == ".pdf":
            try:
                import fitz
                import numpy as np
                from PIL import Image
                with fitz.open(path) as document:
                    actual_sizes = [[page.rect.width * 25.4 / 72, page.rect.height * 25.4 / 72] for page in document]
                    row["physical_pages_mm"] = [[round(x, 2) for x in pair] for pair in actual_sizes]
                    page_sizes, pdf_texts = [], []
                    for page in document:
                        blocks = page.get_text("dict")["blocks"]
                        spans = [span for block in blocks for line in block.get("lines", [])
                                 for span in line.get("spans", []) if span.get("text", "").strip()]
                        page_sizes.append([span["size"] for span in spans])
                        pdf_texts.extend("".join(span.get("text", "") for span in line.get("spans", []))
                                         for block in blocks for line in block.get("lines", []))
                    sizes = [size for page in page_sizes for size in page]
                    row["minimum_text_points"] = min(sizes) if sizes else None
                    row["small_text_human_review"] = any(size < 6 for size in sizes)
                    row["final_size_qa"] = final_size_qa(actual_sizes, page_sizes, final_width_mm)
                    result["pending_human_checks"].extend(f"{item['path']}: inspect final-size text on page {check['page']}"
                        for check in row["final_size_qa"] if check["status"] == "review_required")
                    checks, errors, pending = verify_labels(pdf_texts, expected_text or [])
                    row["label_checks"] = checks
                    result["errors"].extend(f"{item['path']}: {error}" for error in errors)
                    result["pending_human_checks"].extend(f"{item['path']}: {check}" for check in pending)
                    row["grayscale_previews"] = []
                    row["color_vision_previews"] = []
                    for index, page in enumerate(document):
                        preview = project / "reports/figure-output-qa" / row["sha256"] / f"page-{index + 1}-grayscale.png"
                        if any(p.is_symlink() for p in (preview, *preview.parents)) or not preview.resolve().is_relative_to(project):
                            raise ValueError("unsafe preview output path")
                        preview.parent.mkdir(parents=True, exist_ok=True)
                        page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csGRAY).save(preview)
                        row["grayscale_previews"].append({"path": preview.relative_to(project).as_posix(),
                            "sha256": sha(preview), "purpose": "visual_QA_only", "source_pdf_sha256": row["sha256"]})
                        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), colorspace=fitz.csRGB, alpha=False)
                        rgb = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, 3)
                        for mode in MACHADO_100:
                            target = preview.with_name(f"page-{index + 1}-{mode}.png")
                            if target.is_symlink():
                                raise ValueError("unsafe color preview output path")
                            Image.fromarray(simulate_rgb(rgb, mode)).save(target)
                            row["color_vision_previews"].append({"path": target.relative_to(project).as_posix(),
                                "sha256": sha(target), "mode": mode, "severity": 100,
                                "purpose": "visual_QA_only", "source_pdf_sha256": row["sha256"]})
            except ImportError:
                result["errors"].append("PDF output QA requires declared PyMuPDF, NumPy and Pillow dependencies")
            except (RuntimeError, ValueError, OSError) as exc:
                result["errors"].append(f"{item['path']}: cannot inspect PDF: {exc}")
        result["outputs"].append(row)
        if path.is_file() and sha(path) != row["sha256"]:
            result["errors"].append(f"{item['path']}: scientific output changed during QA")
    result["status"] = "fail" if result["errors"] else "review_required" if result["pending_human_checks"] else "pass"
    return result
