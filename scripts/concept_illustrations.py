#!/usr/bin/env python3
"""Optional GPT Image conceptual illustrations; never use for measured results.

Paid image generation is disabled until a separately verified image route has
central budget reservation, reconciliation and identity support. Importing a
ChatGPT-web download is manual; this script never borrows its session.
All images remain UNREGISTERED until visual inspection and separate approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

try:
    from scripts import output_provenance
    from scripts.publication_figures import PROJECTS_ROOT, safe_file, sha256_file
except ImportError:
    import output_provenance  # type: ignore
    from publication_figures import PROJECTS_ROOT, safe_file, sha256_file  # type: ignore


def _png(data: bytes) -> None:
    if len(data) > 20_000_000 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("expected a PNG smaller than 20 MB")


def prepare(project: Path, paper: str, stem: str, prompt: str, source: str,
            model: str, *, source_file: Path | None = None, execute: bool = False) -> dict:
    if not re.fullmatch(r"P[0-9]{2}", paper) or not re.fullmatch(r"[A-Za-z0-9_-]+", stem):
        raise ValueError("paper/stem must be Pxx and a simple filename")
    if not prompt.strip() or not model.strip():
        raise ValueError("prompt and model ID are required")
    if source not in {"chatgpt-web", "gpt-image-api"}:
        raise ValueError("unsupported illustration source")
    if source == "gpt-image-api":
        if execute:
            raise ValueError("paid image generation is disabled: no verified, centrally metered image route is configured; import an authorized PNG or use deterministic research_diagrams")
        return {"dry_run": True, "available": False, "source": source, "model_id": model,
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "notice": "No paid request sent. Image generation remains disabled pending verified route, permission and central billing support."}
    destination = safe_file(project, f"papers/{paper}/figures/{stem}.png", "figure")
    receipt_path = destination.with_suffix(".image-source.json")
    if destination.exists() or receipt_path.exists():
        raise ValueError("refusing to overwrite an existing image/receipt")
    if source == "chatgpt-web":
        if source_file is None or not source_file.is_file():
            raise ValueError("ChatGPT-web import requires a local downloaded PNG")
        data = source_file.read_bytes()
    _png(data)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    receipt = {"schema_version":"1.0","kind":"conceptual_illustration", "source":source,
               "model_id":model,"model_identity_note":"user-reported" if source == "chatgpt-web" else "requested via official API",
               "prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),"prompt":prompt,
               "output_sha256":sha256_file(destination),"not_experimental_evidence":True,
               "generated_at":output_provenance.utc_now(),"human_visual_review_required":True}
    receipt_path.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+"\n", encoding="utf-8")
    output_provenance.record_model_writes(project,[destination,receipt_path],family="openai",
        provider=source,model=model,role="conceptual-illustration",run_id="illustration-"+receipt["prompt_sha256"][:16])
    return {"figure":destination.relative_to(project).as_posix(),
            "receipt":receipt_path.relative_to(project).as_posix(),
            "status":"unregistered-pending-human-review", "not_experimental_evidence":True}


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True);p.add_argument("--paper",required=True)
    p.add_argument("--stem",required=True);p.add_argument("--prompt-file",type=Path,required=True)
    p.add_argument("--source",choices=("gpt-image-api","chatgpt-web"),required=True)
    p.add_argument("--model",required=True);p.add_argument("--source-file",type=Path)
    p.add_argument("--execute",action="store_true",help="legacy option; paid image generation currently fails closed")
    args=p.parse_args()
    print(json.dumps(prepare(PROJECTS_ROOT/args.project,args.paper,args.stem,
          args.prompt_file.read_text(encoding="utf-8"),args.source,args.model,
          source_file=args.source_file,execute=args.execute),indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
