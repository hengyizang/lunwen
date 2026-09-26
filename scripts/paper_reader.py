#!/usr/bin/env python3
"""Page-anchored personal PDF reader, optionally translated through the GPT API.

The extracted text/page image is not independently verified scientific evidence.
Only run on a local copy the user is authorized to process; do not redistribute.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import uuid
from pathlib import Path

try:
    from scripts import model_runtime, output_provenance
    from scripts.publication_figures import PROJECTS_ROOT, safe_file, sha256_file
except ImportError:
    import model_runtime, output_provenance  # type: ignore
    from publication_figures import PROJECTS_ROOT, safe_file, sha256_file  # type: ignore


def build(project: Path, pdf: Path, output: Path, *, max_pages: int = 30,
          translate: bool = False, include_page_images: bool = False) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("install the optional reader dependency: pip install '.[reader]'") from exc
    if pdf.is_symlink():raise ValueError("symlinked PDF sources are not supported")
    pdf=pdf.resolve()
    if not pdf.is_file() or pdf.suffix.lower()!=".pdf":
        raise ValueError("input must be an explicit regular local PDF")
    if not 1<=max_pages<=100:raise ValueError("max-pages must be 1..100")
    if output.exists():raise ValueError("refusing to overwrite an existing reader")
    reader=PdfReader(str(pdf),strict=False)
    if reader.is_encrypted:raise ValueError("encrypted PDF requires separate authorized access")
    if len(reader.pages)>max_pages:raise ValueError("PDF exceeds selected page limit; select a bounded section")
    if include_page_images and not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm is required for page images")
    lines=["# Page-anchored PDF reader", "", f"Local source SHA-256: `{sha256_file(pdf)}`", "",
           "Personal reading aid; verify all quotes, figures and claims against the original PDF.", ""]
    output.parent.mkdir(parents=True,exist_ok=True)
    images=[];run_id="reader-"+uuid.uuid4().hex
    for index,page in enumerate(reader.pages,1):
        text=(page.extract_text() or "").strip()
        if not text:raise ValueError(f"page {index} has no extractable text; OCR/visual review is required")
        if len(text)>40000:raise ValueError(f"page {index} is too long for safe bounded processing")
        lines += [f"## PDF page {index}","", "### Original extracted text", "",text,"",
                  "### Chinese reading translation", ""]
        if translate:
            result=model_runtime.call(project,run_id=run_id,stage="auxiliary",role="reader-translation",
                provider="openai",prompt=f"Translate this PDF page into faithful Chinese for personal reading. Preserve all numbers, abbreviations, hedges, citations and page order. Do not add claims.\n\n{text}",
                max_output_tokens=min(6000,max(1200,model_runtime.estimate_tokens(text)*2)))
            lines.extend([result.text,""])
        else:lines.extend(["[Translation pending; no model call made.]",""])
        if include_page_images:
            stem=output.with_name(f"{output.stem}-page-{index:03d}")
            subprocess.run(["pdftoppm","-f",str(index),"-l",str(index),"-singlefile","-scale-to","1200","-png",str(pdf),str(stem)],
                           check=True,timeout=90,capture_output=True)
            image=stem.with_suffix(".png")
            images.append({"path":image.relative_to(project).as_posix(),"sha256":sha256_file(image),"pdf_page":index})
            lines += [f"![Original PDF page {index}]({image.name})", ""]
    output.write_text("\n".join(lines)+"\n",encoding="utf-8")
    receipt={"schema_version":"1.0","pdf_sha256":sha256_file(pdf),"page_count":len(reader.pages),
             "translation_provider":"openai" if translate else None,"page_images":images,
             "reader_sha256":sha256_file(output),"personal_use_only":True,"not_citation_evidence":True}
    receipt_path=output.with_suffix(".reader.json")
    receipt_path.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf-8")
    output_provenance.record_model_writes(project,[output,receipt_path,*[project/i["path"] for i in images]],
        family="openai" if translate else "other",provider="page-reader",model="GPT translator" if translate else "local extractor",
        role="reader-not-manuscript",run_id=run_id)
    return {"reader":output.relative_to(project).as_posix(),"receipt":receipt_path.relative_to(project).as_posix(),
            "pages":len(reader.pages),"translated":translate}


def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--pdf",type=Path,required=True)
    p.add_argument("--output",required=True);p.add_argument("--max-pages",type=int,default=30)
    p.add_argument("--translate",action="store_true",help="explicit paid GPT translation")
    p.add_argument("--include-page-images",action="store_true")
    args=p.parse_args();project=PROJECTS_ROOT/args.project
    if not args.output.startswith("evidence/readers/"):p.error("reader output must be in evidence/readers")
    print(json.dumps(build(project,args.pdf,safe_file(project,args.output,"output"),max_pages=args.max_pages,
                           translate=args.translate,include_page_images=args.include_page_images),indent=2))
    return 0


if __name__=="__main__":raise SystemExit(main())
