"""Cloud CPU CLIP retrieval against pinned public figure embeddings, no paid API."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import sys
from urllib.request import Request, build_opener

from scripts import figure_gallery as gallery
from scripts.research_artifacts import path_in, record, sha, write

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "integrations/figure-gallery-semantic.lock.json"
MODULE = "scripts/figure_gallery_semantic.py"


def lock():
    value = gallery._json(LOCK.read_bytes())
    if (value.get("repository") != "qwdwqfwq/topconf-paper-figure-gallery"
            or value.get("commit") != gallery._lock()["commit"]
            or value.get("dimension") != 512 or value.get("max_tokens") != 77
            or len(value.get("assets", [])) != 5):
        raise ValueError("semantic lock differs from the metadata snapshot")
    return value


def verify_bytes(data, asset):
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if len(data) != asset["bytes"] or actual != asset["git_blob_sha1"]:
        raise ValueError("pinned semantic asset byte/hash mismatch: " + asset["path"])
    return hashlib.sha256(data).hexdigest()


def provision(project):
    """Install only the fixed reviewed CPU extra, on demand in the cloud."""
    gallery._cloud()
    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        from scripts.cloud_retry import run
        result = run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                      ".[figure-retrieval]"], cwd=ROOT, operation="figure-retrieval-runtime",
                     receipt=project / "state/cloud-retry.jsonl", timeout=300)
        if result.returncode:
            raise RuntimeError("fixed cloud CPU figure-retrieval dependencies could not be installed")
    expected = {"onnxruntime": "1.23.2", "tokenizers": "0.22.1"}
    if any(importlib.metadata.version(name) != version for name, version in expected.items()):
        raise ValueError("cloud semantic runtime must match the reviewed pinned versions")


def assets(project):
    gallery._cloud()
    fixed = lock()
    paths, receipts = {}, []
    for asset in fixed["assets"]:
        # Cache identity is derived only from the reviewed lock, never requests.
        relative = ".cache/figure-gallery-models/" + fixed["commit"] + "/" + asset["path"]
        target = path_in(project, relative, exists=False)
        if target.is_file():
            if target.stat().st_size != asset["bytes"]:
                raise ValueError("cached semantic asset size mismatch")
            data = target.read_bytes()
        else:
            url = "https://raw.githubusercontent.com/" + fixed["repository"] + "/" + fixed["commit"] + "/" + asset["path"]
            request = Request(url, headers={"User-Agent": "lunwen-figure-retrieval/1.0"})
            with build_opener(gallery._NoRedirect).open(request, timeout=60) as response:
                if response.geturl() != url:
                    raise ValueError("semantic asset redirect forbidden")
                data = response.read(asset["bytes"] + 1)
            verify_bytes(data, asset)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        digest = verify_bytes(data, asset)
        paths[asset["path"]] = target
        receipts.append({**asset, "sha256": digest})
    return paths, receipts


def clip_text(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 2000:
        raise ValueError("query must be bounded nonempty text")
    # CLIP's English vocabulary needs explicit, reviewable Chinese concept
    # expansion. Unrecognized Chinese is retained, not pretended translated.
    phrases = [gallery.CONCEPTS[key][0] for key in gallery.concepts(query)]
    phrases += [gallery.STRUCTURES[key][0] for key in gallery.concepts(query, gallery.STRUCTURES)]
    return " ".join(dict.fromkeys(phrases + [query.strip()]))


def embed(query, paths):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(str(paths["forge/models/clip-vit-base-patch32/tokenizer.json"]))
    # The original context must never silently disappear. Oversized semantic
    # queries fail clearly; the separate lexical search still accepts 2000 chars.
    tokenizer.no_truncation()
    tokenizer.no_padding()
    text = clip_text(query)
    encoded = tokenizer.encode(text)
    if len(encoded.ids) > 77:
        raise ValueError("CLIP query exceeds 77 tokens; use a shorter explicit visual query")
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(paths["forge/models/clip-vit-base-patch32/onnx/text_model_quantized.onnx"]),
                                   sess_options=options, providers=["CPUExecutionProvider"])
    if session.get_providers() != ["CPUExecutionProvider"]:
        raise ValueError("CPU-only semantic provider required")
    allowed = {"input_ids": np.asarray([encoded.ids], dtype=np.int64),
               "attention_mask": np.asarray([encoded.attention_mask], dtype=np.int64)}
    names = [item.name for item in session.get_inputs()]
    if not set(names) <= set(allowed) or "input_ids" not in names:
        raise ValueError("unexpected pinned ONNX input contract")
    if "text_embeds" not in {item.name for item in session.get_outputs()}:
        raise ValueError("pinned model lacks projected text_embeds")
    vector = np.asarray(session.run(["text_embeds"], {name: allowed[name] for name in names})[0], dtype=np.float32)
    if vector.shape != (1, 512) or not np.isfinite(vector).all() or np.linalg.norm(vector) <= 0:
        raise ValueError("invalid CPU query embedding")
    vector = vector[0] / np.linalg.norm(vector[0])
    return vector, {"provider": "CPUExecutionProvider", "onnx_executions": 1,
                    "token_count": len(encoded.ids), "clip_query": text,
                    "query_embedding_sha256": hashlib.sha256(vector.tobytes()).hexdigest(),
                    "runtime": {name: importlib.metadata.version(name) for name in ("onnxruntime", "tokenizers", "numpy")}}


def matrices(paths, ids):
    import numpy as np
    shipped = gallery._json(paths["forge/data/ids.json"].read_bytes())
    if shipped != ids or len(ids) != lock()["row_count"]:
        raise ValueError("semantic embedding row order does not match pinned metadata")
    arrays = []
    for name in ("image_emb", "text_emb"):
        values = np.fromfile(paths["forge/data/" + name + ".bin"], dtype="<f4")
        if values.size != len(ids) * 512 or not np.isfinite(values).all():
            raise ValueError("invalid semantic embedding matrix")
        values = values.reshape(len(ids), 512)
        norms = np.linalg.norm(values, axis=1)
        if (norms <= 0).any():
            raise ValueError("zero semantic embedding row")
        arrays.append(values / norms[:, None])
    return arrays


def _payload(report):
    return {key: report[key] for key in ("query", "filters", "top_k", "source", "snapshot_binding",
                                        "corpus_count", "filtered_count", "matched_count", "candidates")}


def validate_report(project, report):
    from scripts.output_provenance import current_origin
    binding = report.get("retrieval", {}).get("semantic_evidence", {})
    if (report.get("retrieval", {}).get("method") != "cpu_clip_bm25"
            or report.get("retrieval", {}).get("semantic_image_search") is not True):
        raise ValueError("semantic method must identify actual CPU retrieval")
    relative = binding.get("path", "")
    if not re.fullmatch(r"reports/figure-gallery-semantic/[a-f0-9]{24}\.json", relative):
        raise ValueError("semantic search needs a protected CPU execution receipt")
    target = path_in(project, relative)
    origin = current_origin(project, target)
    evidence = gallery._json(target.read_bytes())
    expected = lock()
    if (sha(target) != binding.get("sha256") or origin.get("status") != "tracked"
            or origin.get("family") != "other"
            or origin.get("model") != MODULE or origin.get("provider") != "deterministic-control-plane"
            or evidence.get("implementation_sha256") != sha(Path(__file__))
            or evidence.get("lock_sha256") != sha(LOCK)
            or evidence.get("payload_sha256") != gallery.digest(_payload(report))
            or evidence.get("provider") != "CPUExecutionProvider" or evidence.get("onnx_executions") != 1):
        raise ValueError("semantic execution receipt is missing, stale or inconsistent")
    assets_evidence = evidence.get("assets", [])
    if len(assets_evidence) != len(expected["assets"]):
        raise ValueError("semantic asset evidence is incomplete")
    for actual, pinned in zip(assets_evidence, expected["assets"]):
        if any(actual.get(key) != value for key, value in pinned.items()) or not gallery.HASH.fullmatch(actual.get("sha256", "")):
            raise ValueError("semantic asset evidence differs from reviewed lock")


def search(project, query, *, top_k=8, venues=None, years=None, tiers=None, patterns=None, topics=None):
    gallery._cloud()
    if type(top_k) is not int or not 1 <= top_k <= gallery.MAX_TOP_K:
        raise ValueError("top_k must be 1 through 20")
    clip_text(query)  # Reject malformed requests before any asset download.
    index = gallery.load_index(project)
    filters = gallery.normalize_filters({"venues": venues, "years": years, "tiers": tiers, "patterns": patterns, "topics": topics})
    selected = gallery.matching_figures(index, filters)
    # A semantic request always executes the real model or fails; no fake fallback.
    paths, receipts = assets(project)
    vector, execution = embed(query, paths)
    image, text = matrices(paths, [row["id"] for row in index["figures"]])
    image_scores, text_scores = image @ vector, text @ vector
    lexical = {row["id"]: row for row in gallery.lexical_rank(selected, query)}
    positions = {row["id"]: i for i, row in enumerate(index["figures"])}
    ranked = []
    for row in selected:
        i = positions[row["id"]]
        lex = lexical.get(row["id"], {})
        value = lex.get("score", 0)
        a, b = float(image_scores[i]), float(text_scores[i])
        score = .40 * a + .25 * b + .35 * value / (value + 8)
        if not math.isfinite(score):
            raise ValueError("nonfinite semantic rank")
        ranked.append({**row, "score": round(score, 8), "score_is_probability": False,
                       "image_cosine": a, "text_cosine": b,
                       "reasons": ["CPU CLIP image cosine: %.5f; text cosine: %.5f (retrieval relevance, not correctness)" % (a, b)] + lex.get("reasons", [])})
    ranked.sort(key=lambda row: (-row["score"], row["id"]))
    report = {"schema_version": "1.0", "query": query, "filters": filters, "top_k": top_k,
              "source": index["source"], "snapshot_binding": index["snapshot_binding"],
              "corpus_count": len(index["figures"]), "filtered_count": len(selected),
              "matched_count": len(ranked), "candidates": ranked[:top_k]}
    evidence = {"schema_version": "1.0", **execution, "assets": receipts,
                "implementation_sha256": sha(Path(__file__)), "lock_sha256": sha(LOCK),
                "payload_sha256": gallery.digest(_payload(report)), "paid_api_calls": 0}
    relative = "reports/figure-gallery-semantic/" + gallery.digest(evidence)[:24] + ".json"
    target = path_in(project, relative, exists=False)
    write(target, evidence)
    record(project, [target], MODULE)
    report["retrieval"] = {"method": "cpu_clip_bm25", "semantic_image_search": True,
                            "semantic_evidence": {"path": relative, "sha256": sha(target)},
                            "topic_filter_basis": "title_bilingual_concept_inference",
                            "score_is_probability": False, "image_inspection": False,
                            "limitations": "English CLIP with explicit bilingual concept expansion; embeddings are upstream supplied. No visual or scientific approval."}
    validate_report(project, report)
    return gallery.write_report(project, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    provision(args.project)
    print(json.dumps(search(args.project, args.query), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
