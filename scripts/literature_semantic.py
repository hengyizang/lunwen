"""Explicit cloud CPU embeddings and cross-encoder ranking of authorized originals.

Pinned ONNX graphs and tokenizers execute no repository Python code. Every token
window is processed, original evidence remains unchanged, and scores stay reading
leads. The default lexical route and all paid-model routes remain unchanged.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from scripts import evidence_retrieval, literature_review, literature_workbench as wb
from scripts.research_artifacts import path_in, read, record, sha, write

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "integrations/literature-semantic.lock.json"
MODULE = "scripts/literature_semantic.py"
OUTPUT = "reports/literature-semantic"
MAX_BLOCKS = 300
MAX_WINDOWS = 4096


def _cloud():
    from scripts.figure_gallery import _cloud as require_cloud
    require_cloud()


def lock():
    value = read(LOCK)
    if value.get("schema_version") != "1.0":
        raise ValueError("invalid semantic model lock")
    for name in ("embedding", "reranker"):
        model = value.get(name, {})
        if (not re.fullmatch(r"[a-f0-9]{40}", model.get("revision", ""))
                or not re.fullmatch(r"[a-f0-9]{64}", model.get("weights", {}).get("sha256", ""))):
            raise ValueError("semantic model needs pinned commit and weight SHA256")
    return value


def provision(project):
    """Reuse the fixed ONNX/tokenizers extra, installed only on the cloud runner."""
    _cloud()
    from scripts.figure_gallery_semantic import provision as install_cpu_extra
    install_cpu_extra(project)
    for package, version in lock()["runtime"].items():
        if importlib.metadata.version(package) != version:
            raise ValueError("semantic runtime differs from fixed reviewed versions")


def _current(project, target):
    from scripts.output_provenance import current_origin
    origin = current_origin(project, target)
    return (origin.get("status") == "tracked" and origin.get("family") == "other"
            and origin.get("model") == MODULE)


class _HubRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not (host == "huggingface.co" or host.endswith(".huggingface.co") or host.endswith(".hf.co")):
            raise ValueError("model download redirect left the reviewed Hugging Face hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def assets(project, kind):
    """Fetch only immutable public graph/tokenizer assets; preserve actual hashes."""
    _cloud()
    model = lock()[kind]
    directory = ".cache/literature-semantic-models/" + model["revision"]
    paths, receipts = {}, []
    for label in ("weights", "tokenizer"):
        asset = model[label]
        target = path_in(project, directory + "/" + asset["path"], exists=False)
        receipt_path = target.with_suffix(target.suffix + ".receipt.json")
        expected = asset.get("sha256")
        cached = target.is_file()
        if cached:
            if not receipt_path.is_file() or not _current(project, receipt_path):
                raise ValueError("cached semantic asset needs current download provenance")
            old = read(receipt_path)
            if old.get("revision") != model["revision"] or old.get("path") != asset["path"] or old.get("sha256") != sha(target):
                raise ValueError("cached semantic asset changed")
        else:
            url = "https://huggingface.co/" + model["id"] + "/resolve/" + model["revision"] + "/" + asset["path"]
            maximum = asset.get("bytes", asset.get("max_bytes"))
            request = Request(url, headers={"User-Agent": "lunwen-literature-semantic/1.0"})
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".download")
            count = 0
            try:
                with build_opener(_HubRedirect()).open(request, timeout=90) as response, temporary.open("wb") as output:
                    while True:
                        chunk = response.read(min(1_048_576, maximum + 1 - count))
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > maximum:
                            raise ValueError("semantic asset exceeds fixed byte ceiling")
                        output.write(chunk)
                if ("bytes" in asset and count != asset["bytes"]) or (expected and sha(temporary) != expected):
                    raise ValueError("semantic asset hash or size differs from reviewed lock")
                temporary.replace(target)
            finally:
                if temporary.exists():
                    temporary.unlink()
            write(receipt_path, {"model": model["id"], "revision": model["revision"], "path": asset["path"],
                                 "sha256": sha(target), "bytes": target.stat().st_size,
                                 "source": url, "immutable_source_revision": True})
            record(project, [receipt_path], MODULE)
        digest = sha(target)
        if expected and digest != expected:
            raise ValueError("semantic asset hash differs from reviewed lock")
        if target.stat().st_size > asset.get("bytes", asset.get("max_bytes")):
            raise ValueError("semantic asset size exceeds reviewed lock")
        paths[label] = target
        receipts.append({"model": model["id"], "revision": model["revision"], "path": asset["path"],
                         "sha256": digest, "bytes": target.stat().st_size, "cache_hit": cached})
    return paths, receipts


class CpuEngine:
    """No trust_remote_code, Python model loading, GPU allocation or paid endpoint."""
    def __init__(self, project, kind):
        _cloud()
        provision(project)
        import onnxruntime as ort
        from tokenizers import Tokenizer
        paths, self.assets = assets(project, kind)
        self.model, self.kind = lock()[kind], kind
        self.tokenizer = Tokenizer.from_file(str(paths["tokenizer"]))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(paths["weights"]), sess_options=options,
                                            providers=["CPUExecutionProvider"])
        if self.session.get_providers() != ["CPUExecutionProvider"]:
            raise ValueError("semantic inference requires the CPU provider")
        self.executions = 0

    def _windows(self, text, pair=None):
        self.tokenizer.no_truncation()
        if pair is not None:
            query_tokens = len(self.tokenizer.encode(text).ids)
            if query_tokens + self.model["stride"] + 8 >= self.model["max_tokens"]:
                raise ValueError("reranker query leaves no complete passage window; shorten explicitly")
        self.tokenizer.enable_truncation(max_length=self.model["max_tokens"], stride=self.model["stride"],
                                         strategy="only_second" if pair is not None else "longest_first")
        encoded = self.tokenizer.encode(text, pair)
        windows = [encoded, *encoded.overflowing]
        if len(windows) > MAX_WINDOWS or self.executions + len(windows) > MAX_WINDOWS:
            raise ValueError("semantic request exceeds CPU window ceiling; declare a smaller source scope")
        return windows

    def _run(self, encoding):
        import numpy as np
        values = {"input_ids": np.asarray([encoding.ids], dtype=np.int64),
                  "attention_mask": np.asarray([encoding.attention_mask], dtype=np.int64),
                  "token_type_ids": np.asarray([encoding.type_ids], dtype=np.int64)}
        names = [item.name for item in self.session.get_inputs()]
        if not set(names) <= set(values) or "input_ids" not in names:
            raise ValueError("unexpected pinned semantic graph input contract")
        self.executions += 1
        output = self.session.run(None, {name: values[name] for name in names})[0]
        if not np.isfinite(output).all():
            raise ValueError("semantic graph returned nonfinite scores")
        return output

    def embed(self, text):
        import numpy as np
        windows = self._windows(text)
        total, weights = np.zeros(self.model["dimension"], dtype=np.float64), 0
        for window in windows:
            value = self._run(window)
            if value.shape != (1, len(window.ids), self.model["dimension"]):
                raise ValueError("pinned embedding graph shape changed")
            mask = np.asarray(window.attention_mask, dtype=np.float64)
            total += (value[0] * mask[:, None]).sum(axis=0)
            weights += int(mask.sum())
        vector = total / max(weights, 1)
        norm = np.linalg.norm(vector)
        if not np.isfinite(vector).all() or norm <= 0:
            raise ValueError("invalid pooled semantic vector")
        return (vector / norm).tolist(), {"windows": len(windows), "all_windows_processed": True,
            "pooling": "attention-masked mean across all overlapping windows then L2 normalization",
            "window_tokens_including_overlap": weights}

    def score(self, query, passage):
        windows = self._windows(query, passage)
        values = []
        for window in windows:
            output = self._run(window)
            if output.shape != (1, 1):
                raise ValueError("pinned cross-encoder graph shape changed")
            values.append(float(output[0, 0]))
        return max(values), {"windows": len(windows), "all_windows_processed": True,
                            "aggregation": "maximum window logit, not a support probability"}

    def receipt(self):
        return {"id": self.model["id"], "revision": self.model["revision"], "assets": self.assets,
                "provider": "CPUExecutionProvider", "onnx_executions": self.executions,
                "language_scope": self.model["language_scope"],
                "runtime": {name: importlib.metadata.version(name) for name in lock()["runtime"]}}


def _identity(row):
    return {key: row[key] for key in ("path", "sha256", "start_line", "end_line")}


def _spec(project, request):
    if (not isinstance(request, dict) or set(request) != {"schema_version", "retrieval", "rerank"}
            or request.get("schema_version") != "1.0" or type(request.get("rerank")) is not bool):
        raise ValueError("semantic request needs schema_version, retrieval and explicit rerank boolean")
    if not isinstance(request["retrieval"], dict) or any(key in request["retrieval"] for key in ("dense_cache", "rerank_cache")):
        raise ValueError("semantic operation generates its own bound dense cache")
    prepared = literature_review.prepare(project, request["retrieval"])
    baseline = evidence_retrieval.retrieve(project, prepared["spec"])
    chunks, searched = evidence_retrieval.corpus(project, prepared["spec"]["sources"])
    if len(chunks) > MAX_BLOCKS:
        raise ValueError("semantic corpus exceeds 300 blocks; select a smaller explicit corpus")
    return prepared, chunks, searched, baseline


def apply_rerank_cache(project, spec, selected):
    """Apply only an actual provenance-bound CPU score cache; never drop a block."""
    binding = spec["rerank_cache"]
    if (not isinstance(binding, dict) or set(binding) != {"path", "sha256"}
            or not isinstance(binding.get("path"), str)
            or not re.fullmatch(r"reports/literature-semantic/rerank/[a-f0-9]{24}\.json", binding["path"])):
        raise ValueError("rerank_cache needs an exact controlled CPU score cache")
    target = path_in(project, binding["path"])
    if sha(target) != binding["sha256"] or not _current(project, target):
        raise ValueError("rerank cache changed outside its controlled builder")
    cached = read(target)
    original_spec = {key: value for key, value in spec.items() if key != "rerank_cache"}
    expected = [{**_identity(row), "excerpt_sha256": hashlib.sha256(row["quote"].encode()).hexdigest()} for row in selected]
    if (cached.get("spec_sha256") != wb._digest(original_spec) or cached.get("blocks") != expected
            or cached.get("lock_sha256") != sha(LOCK) or cached.get("implementation_sha256") != sha(Path(__file__))):
        raise ValueError("rerank source, query, candidate or model scope changed")
    scores = cached.get("scores")
    coverage_rows = cached.get("coverage")
    if (not isinstance(scores, list) or len(scores) != len(selected)
            or any(type(value) not in (int, float) or not math.isfinite(value) for value in scores)):
        raise ValueError("rerank scores must be finite and cover every selected block")
    if (not isinstance(coverage_rows, list) or len(coverage_rows) != len(selected)
            or any(not isinstance(row, dict) or row.get("all_windows_processed") is not True
                   or type(row.get("windows")) is not int or row["windows"] < 1 for row in coverage_rows)):
        raise ValueError("rerank coverage must retain all windows of every selected block")
    for rank, (row, score, coverage) in enumerate(zip(selected, scores, coverage_rows), 1):
        row.update(pre_rerank_rank=rank, reranker_score=score, reranker_coverage=coverage)
    selected.sort(key=lambda row: (-row["reranker_score"], row["path"], row["start_line"]))
    return {**binding, "execution": cached["execution"],
            "scope": "every selected fused-retrieval block; no source exclusion"}


def _save(project, relative, data, *, compact=False):
    target = path_in(project, relative, exists=False)
    if target.exists() and not _current(project, target):
        raise ValueError("semantic output changed outside its controlled builder")
    if compact:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        if len(payload.encode()) > 4_000_000:
            raise ValueError("dense cache exceeds 4 MB; declare a smaller explicit corpus")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    else:
        write(target, data)
    record(project, [target], MODULE)
    return {"path": relative, "sha256": sha(target)}


def build(project, request):
    _cloud()
    project = Path(project).resolve()
    prepared, chunks, searched, baseline = _spec(project, request)
    model = lock()["embedding"]
    identities = [{**_identity(row), "excerpt_sha256": hashlib.sha256(row["quote"].encode()).hexdigest()} for row in chunks]
    corpus_binding = {"model": {k: model[k] for k in ("id", "revision")}, "blocks": identities,
                      "lock_sha256": sha(LOCK), "implementation_sha256": sha(Path(__file__))}
    index_id = wb._digest(corpus_binding)[:24]
    index_path = OUTPUT + "/indexes/" + index_id + ".json"
    index_target = path_in(project, index_path, exists=False)
    started = time.perf_counter()
    engine = None
    reused_index = index_target.is_file()
    if reused_index:
        if not _current(project, index_target):
            raise ValueError("semantic index changed outside its controlled builder")
        index = read(index_target)
        if index.get("binding") != corpus_binding:
            raise ValueError("semantic index source or model binding changed")
        for row in index.get("blocks", []):
            evidence_retrieval._vector(row.get("vector"), model["dimension"], "cached index block")
        if [{key: row[key] for key in identities[0]} for row in index.get("blocks", [])] != identities:
            raise ValueError("semantic index block inventory changed")
    else:
        engine = CpuEngine(project, "embedding")
        blocks = []
        for identity, chunk in zip(identities, chunks):
            vector, coverage = engine.embed(chunk["quote"])
            blocks.append({**identity, "vector": vector, "coverage": coverage})
        index = {"schema_version": "1.0", "binding": corpus_binding, "blocks": blocks,
                 "execution": engine.receipt(), "semantic_quality_verified": False}
        _save(project, index_path, index)
    query = prepared["spec"]["query"]
    query_id = wb._digest({"query": query, "index_sha256": sha(index_target)})[:24]
    dense_path = OUTPUT + "/dense/" + query_id + ".json"
    dense_target = path_in(project, dense_path, exists=False)
    query_cache_hit = dense_target.is_file()
    query_coverage = None
    if query_cache_hit:
        if not _current(project, dense_target):
            raise ValueError("semantic query cache changed outside its controlled builder")
        dense = read(dense_target)
    else:
        engine = engine or CpuEngine(project, "embedding")
        vector, query_coverage = engine.embed(query)
        dense = {"schema_version": "1.0", "model": corpus_binding["model"], "dimension": model["dimension"],
                 "query": {"text": query, "sha256": hashlib.sha256(query.encode()).hexdigest(), "vector": vector},
                 "sources": [{key: row[key] for key in ("path", "sha256", "ranges") if key in row} for row in searched],
                 "blocks": [{key: row[key] for key in (*identities[0], "vector")} for row in index["blocks"]]}
        _save(project, dense_path, dense, compact=True)
    bound_request = {**request["retrieval"], "dense_cache": {"path": dense_path, "sha256": sha(dense_target)}}
    result = literature_review.retrieve(project, bound_request)
    reranker = None
    rerank_binding = None
    if request["rerank"]:
        reranker = CpuEngine(project, "reranker")
        by_id = {(r["path"], r["start_line"], r["end_line"]): r for r in chunks}
        scores, windows, candidates = [], [], []
        for row in result["results"]:
            chunk = by_id[(row["path"], row["start_line"], row["end_line"])]
            score, coverage = reranker.score(query, chunk["quote"])
            scores.append(score)
            windows.append(coverage)
            candidates.append({**_identity(chunk), "excerpt_sha256": hashlib.sha256(chunk["quote"].encode()).hexdigest()})
        lowlevel = literature_review.prepare(project, bound_request)["spec"]
        rerank_id = wb._digest({"spec": lowlevel, "lock": sha(LOCK)})[:24]
        rerank_binding = _save(project, OUTPUT + "/rerank/" + rerank_id + ".json", {
            "spec_sha256": wb._digest(lowlevel), "blocks": candidates, "scores": scores,
            "coverage": windows, "execution": reranker.receipt(),
            "lock_sha256": sha(LOCK), "implementation_sha256": sha(Path(__file__))})
        bound_request["rerank_cache"] = rerank_binding
        result = literature_review.retrieve(project, bound_request)
    final_prepared = literature_review.prepare(project, request["retrieval"])
    if final_prepared != prepared:
        raise ValueError("authorized literature scope changed during semantic processing")
    report = {"schema_version": "1.0", "kind": "cloud_cpu_literature_semantic", "request": request,
        "source_binding": prepared, "baseline": baseline, "result": result, "retrieval_request": bound_request,
        "index": {"path": index_path, "sha256": sha(index_target)}, "dense_cache": bound_request["dense_cache"],
        "rerank_cache": rerank_binding,
        "corpus_index_cache_hit": reused_index, "query_cache_hit": query_cache_hit,
        "embedding_execution": engine.receipt() if engine else None,
        "query_embedding_coverage": query_coverage,
        "reranker_execution": reranker.receipt() if reranker else None,
        "index_execution": index["execution"], "elapsed_seconds": time.perf_counter() - started,
        "lock_sha256": sha(LOCK), "implementation_sha256": sha(Path(__file__)),
        "paid_calls": 0, "paid_cost_cny": "0", "cloud_compute_cost_verified": False,
        "scientific_validity_verified": False, "semantic_quality_verified": False,
        "automatic_route_promotion": False, "all_selected_counterevidence_retained": True}
    return report


def refresh(project, request_file="program/literature-semantic.json"):
    if not isinstance(request_file, str) or not request_file.startswith("program/"):
        raise ValueError("semantic request belongs under program/")
    source = wb._path(project, request_file)
    if source.stat().st_size > 1_000_000:
        raise ValueError("semantic request exceeds 1 MB")
    target = path_in(project, OUTPUT + "/latest.json", exists=False)
    if target.is_file() and _current(project, target):
        previous = read(target)
        if (previous.get("request_file") == {"path": request_file, "sha256": sha(source)}
                and previous.get("lock_sha256") == sha(LOCK)
                and previous.get("implementation_sha256") == sha(Path(__file__))):
            prepared, _, _, _ = _spec(project, wb._json(source.read_bytes()))
            if prepared == previous.get("source_binding"):
                checked = validate_saved_report(project, request_file)
                return {"report": OUTPUT + "/latest.json", **checked, "complete_result_cache_hit": True}
    report = build(project, wb._json(source.read_bytes()))
    report["request_file"] = {"path": request_file, "sha256": sha(source)}
    _save(project, OUTPUT + "/latest.json", report)
    return {"report": OUTPUT + "/latest.json", **report}


def validate_saved_report(project, request_file="program/literature-semantic.json"):
    source = wb._path(project, request_file)
    target = path_in(project, OUTPUT + "/latest.json")
    if not _current(project, target):
        raise ValueError("semantic report changed outside its controlled builder")
    report = read(target)
    if (report.get("request_file") != {"path": request_file, "sha256": sha(source)}
            or report.get("lock_sha256") != sha(LOCK) or report.get("implementation_sha256") != sha(Path(__file__))):
        raise ValueError("semantic request, implementation or model lock changed")
    prepared, _, _, _ = _spec(project, wb._json(source.read_bytes()))
    if prepared != report.get("source_binding"):
        raise ValueError("semantic source rights, original scope or source version changed")
    for binding in (report["index"], report["dense_cache"]):
        path = path_in(project, binding["path"])
        if sha(path) != binding["sha256"] or not _current(project, path):
            raise ValueError("semantic cache changed")
    literature_review.retrieve(project, report["retrieval_request"])
    return report
