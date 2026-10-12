"""Bounded, offline assessment of one explicitly configured greenlist watermark.

This is neither a generic AI detector nor a certificate of watermark absence.
Unknown schemes stay unknown. No text, model choice, approval or budget is edited.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

from scripts import manuscript_hygiene, output_provenance, watermark_cleanup
from scripts.research_artifacts import path_in, read, sha, write

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "reports/statistical-watermarks"
PROVIDER = "deterministic-statistical-watermark-assessment"
DETECTOR = "hf-greenlist-v1"
DEPENDENCIES = {"transformers": "4.57.1", "torch": "2.8.0", "tokenizers": "0.22.1"}
ASSET_NAMES = {"tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "config.json", "added_tokens.json"}
MAX_ASSET_BYTES = 100_000_000
MAX_TOKENS = 8192
MAX_VOCAB = 65536
WORKER_SECONDS = 45
LIMITS = {"watermark_absence_verified": False, "ai_authorship_verified": False,
          "all_watermark_types_assessed": False, "statistical_watermark_removal_verified": False,
          "paid_calls": 0, "network_calls": 0, "gpu_used": False,
          "random_sentence_shuffling": False, "synonym_rotation": False,
          "human_scientific_review_required": True}


def _cloud() -> None:
    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true" and os.environ.get("DR_OS_CLOUD_EXECUTOR") != "1":
        raise ValueError("statistical watermark assessment requires cloud execution")


def _paper(project: Path, paper_id: str) -> Path:
    if not re.fullmatch(r"P[0-9]{2}", str(paper_id)):
        raise ValueError("invalid statistical watermark paper ID")
    paper = path_in(project, f"papers/{paper_id}", exists=False)
    if not paper.is_dir():
        raise ValueError("statistical watermark paper is missing")
    return paper


def _implementation() -> dict:
    return {"adapter": DETECTOR, "dependencies": DEPENDENCIES,
            "files": [{"path": name, "sha256": sha(ROOT / name)} for name in (
                "scripts/statistical_watermarks.py", "scripts/manuscript_hygiene.py", "scripts/watermark_cleanup.py")]}


def _versions() -> dict:
    result = {}
    for name in DEPENDENCIES:
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = "missing"
    return result


def runtime_available() -> bool:
    return all(_versions()[name].split("+", 1)[0] == expected for name, expected in DEPENDENCIES.items())


def _canonical(project: Path, paper_id: str) -> tuple[list[str], str, str]:
    paper = _paper(project, paper_id)
    candidates = [path_in(project, f"papers/{paper_id}/manuscript/main{suffix}", exists=False)
                  for suffix in (".tex", ".docx")]
    candidates = [target for target in candidates if target.is_file()]
    if len(candidates) != 1:
        raise ValueError("configured assessment requires exactly one canonical main.tex or main.docx")
    canonical = candidates[0]
    if canonical.suffix == ".docx":
        if canonical.stat().st_size > watermark_cleanup.MAX_SOURCE_BYTES:
            raise ValueError("canonical Word source exceeds the assessment bound")
        _, _, text, _ = watermark_cleanup._process(canonical.read_bytes(), ".docx")
        return [canonical.relative_to(project).as_posix()], text, "Word body/table paragraph text; headers, fields and image pixels are outside this detector"
    seen: set[str] = set()
    expanded_bytes = 0
    def expand(target: Path, stack: tuple[str, ...]) -> str:
        nonlocal expanded_bytes
        relative = target.relative_to(project).as_posix()
        target = path_in(project, relative)
        if not target.is_relative_to(paper / "manuscript") or target.suffix != ".tex":
            raise ValueError("canonical TeX include escapes its manuscript source tree")
        if relative in stack or len(stack) >= 32:
            raise ValueError("cyclic or over-nested canonical TeX include")
        seen.add(relative)
        if len(seen) > 200 or target.stat().st_size > watermark_cleanup.MAX_TEXT_BYTES:
            raise ValueError("canonical TeX source exceeds the assessment bound")
        text = re.sub(r"(?m)(?<!\\)%.*$", "", target.read_text(encoding="utf-8"))
        expanded_bytes += len(text.encode("utf-8"))
        if expanded_bytes > watermark_cleanup.MAX_TEXT_BYTES:
            raise ValueError("expanded canonical TeX exceeds the assessment bound")
        def include(match):
            child = Path(match.group(1))
            if child.is_absolute() or ".." in child.parts or "\\" in str(child) or ":" in str(child):
                raise ValueError("unsafe canonical TeX include")
            if not child.suffix:
                child = child.with_suffix(".tex")
            return expand(paper / "manuscript" / child, (*stack, relative))
        return re.sub(r"\\(?:input|include)\{([^}]+)\}", include, text)
    text = expand(canonical, ())
    return sorted(seen), text, "complete literal TeX include expansion with comments removed; remaining TeX markup is retained"


def _number(value, lower: float, upper: float) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and lower <= value <= upper


def _prepare(project: Path, paper_id: str) -> tuple[dict, dict, str]:
    relative = f"papers/{paper_id}/watermark-assessment.json"
    profile_path = path_in(project, relative)
    if profile_path.stat().st_size > 100_000:
        raise ValueError("statistical watermark profile exceeds the bound")
    profile = read(profile_path)
    required = {"schema_version", "detector", "applicability", "assets_dir", "asset_sha256", "key_env", "key_version",
                "watermark", "z_threshold", "min_scored_tokens", "sources"}
    if set(profile) != required or profile.get("schema_version") != "1.0" or profile.get("detector") != DETECTOR:
        raise ValueError("unsupported statistical watermark profile or detector")
    applicability = profile["applicability"]
    if (not isinstance(applicability, dict) or set(applicability) != {"scheme", "generation_device", "tokenizer_and_config_match", "evidence"}
            or applicability.get("scheme") != "hf-greenlist" or applicability.get("generation_device") != "cpu"
            or applicability.get("tokenizer_and_config_match") is not True):
        raise ValueError("assessment requires the applicable CPU greenlist scheme and matching generation configuration")
    evidence = applicability["evidence"]
    if not isinstance(evidence, dict) or set(evidence) != {"path", "sha256", "locator"}:
        raise ValueError("applicability needs a source-bound human evidence record")
    evidence_path = path_in(project, evidence["path"])
    evidence_origin = output_provenance.current_origin(project, evidence_path)
    if (sha(evidence_path) != evidence["sha256"] or not isinstance(evidence["locator"], str)
            or not 1 <= len(evidence["locator"]) <= 500 or evidence_origin.get("status") != "tracked"
            or evidence_origin.get("provider") != "human-attestation"):
        raise ValueError("applicability evidence must have a current human attestation, hash and locator")
    key_env = profile["key_env"]
    if not isinstance(key_env, str) or not re.fullmatch(r"DR_OS_WATERMARK_KEY_[A-Z0-9_]{1,48}", key_env):
        raise ValueError("watermark key requires a dedicated secret environment variable")
    if not isinstance(profile["key_version"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", profile["key_version"]):
        raise ValueError("watermark key requires a non-secret version label")
    watermark = profile["watermark"]
    if (not isinstance(watermark, dict) or set(watermark) != {"greenlist_ratio", "bias", "seeding_scheme", "context_width"}
            or not _number(watermark["greenlist_ratio"], 0.01, 0.99) or not _number(watermark["bias"], 0.01, 10)
            or watermark["seeding_scheme"] != "lefthash" or type(watermark["context_width"]) is not int
            or not 1 <= watermark["context_width"] <= 8):
        raise ValueError("only the fixed lefthash greenlist adapter and bounded explicit settings are supported")
    if (not _number(profile["z_threshold"], 2, 10) or type(profile["min_scored_tokens"]) is not int
            or not 100 <= profile["min_scored_tokens"] <= MAX_TOKENS):
        raise ValueError("explicit bounded threshold and minimum scored-token count are required")
    source_paths, text, scope = _canonical(project, paper_id)
    if (not isinstance(profile["sources"], list) or not all(isinstance(row, str) for row in profile["sources"])
            or sorted(profile["sources"]) != source_paths):
        raise ValueError("assessment sources must cover the entire current canonical manuscript source tree")
    assets = path_in(project, profile["assets_dir"], exists=False)
    if not assets.is_dir() or assets == project:
        raise ValueError("watermark assets require a dedicated project-local directory")
    rows, total = [], 0
    for target in sorted(assets.iterdir()):
        path_in(project, target.relative_to(project).as_posix(), exists=False)
        if target.name not in ASSET_NAMES or not target.is_file():
            raise ValueError("watermark assets contain an unsupported file, directory or executable")
        total += target.stat().st_size
        if total > MAX_ASSET_BYTES:
            raise ValueError("watermark tokenizer/config cache exceeds the bound")
        value = read(target)
        if "auto_map" in value or "custom_pipelines" in value:
            raise ValueError("custom remote model or tokenizer code is forbidden")
        rows.append({"path": target.relative_to(project).as_posix(), "sha256": sha(target)})
    expected = profile["asset_sha256"]
    if (not isinstance(expected, dict) or not {"config.json", "tokenizer.json"}.issubset(expected)
            or expected != {Path(row["path"]).name: row["sha256"] for row in rows}):
        raise ValueError("complete cached tokenizer/config hashes must match the applicable profile")
    safe = {"path": relative, "sha256": sha(profile_path), "detector": DETECTOR,
            "key_version": profile["key_version"], "assets": rows, "applicability_evidence": evidence,
            "applicability_evidence_origin": evidence_origin, "source_paths": source_paths,
            "extraction_scope": scope, "extracted_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "z_threshold": profile["z_threshold"], "min_scored_tokens": profile["min_scored_tokens"]}
    return profile, safe, text


def _secret(profile: dict) -> int:
    value = os.environ.get(profile["key_env"], "")
    if not re.fullmatch(r"[0-9]{1,20}", value) or not 1 <= int(value) < 2**64:
        raise ValueError("applicable watermark secret is missing or invalid; no key values are reported")
    return int(value)


def _detect_cached(project: Path, paper_id: str) -> dict:
    """Worker-only real HF detector. No model weights, network or remote code."""
    profile, safe, text = _prepare(project, paper_id)
    key = _secret(profile)
    if not runtime_available():
        raise ValueError("fixed offline detector dependencies are unavailable")
    import torch
    from transformers import AutoConfig, AutoTokenizer, WatermarkDetector
    torch.set_num_threads(1)
    assets = path_in(project, profile["assets_dir"], exists=False)
    config = AutoConfig.from_pretrained(str(assets), local_files_only=True, trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(str(assets), local_files_only=True, trust_remote_code=False, use_fast=True)
    if (getattr(config, "is_encoder_decoder", True) or type(config.vocab_size) is not int
            or not 4 <= config.vocab_size <= MAX_VOCAB or tokenizer.vocab_size != config.vocab_size
            or len(tokenizer) != config.vocab_size or not tokenizer.is_fast):
        raise ValueError("cached tokenizer and decoder-only model configuration do not match the supported vocabulary bound")
    ids = tokenizer(text, add_special_tokens=False, return_attention_mask=False, truncation=False)["input_ids"]
    if len(ids) > MAX_TOKENS:
        raise ValueError("entire canonical manuscript exceeds the detector token bound; no truncation is allowed")
    if any(type(value) is not int or not 0 <= value < config.vocab_size for value in ids):
        raise ValueError("cached tokenizer returned invalid token IDs")
    if len(ids) <= profile["watermark"]["context_width"]:
        return {"status": "insufficient_length", "token_count": len(ids), "scored_tokens": 0}
    detector = WatermarkDetector(model_config=config, device="cpu",
        watermarking_config={**profile["watermark"], "hashing_key": key}, ignore_repeated_ngrams=True)
    with torch.inference_mode():
        outcome = detector(torch.tensor([ids], dtype=torch.long, device="cpu"),
                           z_threshold=profile["z_threshold"], return_dict=True)
    scored = int(outcome.num_tokens_scored[0])
    green = int(outcome.num_green_tokens[0])
    z_score = float(outcome.z_score[0])
    if not math.isfinite(z_score):
        raise ValueError("watermark detector returned a non-finite score")
    result = {"status": "detected" if bool(outcome.prediction[0]) else "not_detected",
              "token_count": len(ids), "scored_tokens": scored, "green_tokens": green,
              "green_fraction": float(outcome.green_fraction[0]), "z_score": z_score,
              "null_tail_probability": 0.5 * math.erfc(z_score / math.sqrt(2)),
              "threshold": profile["z_threshold"], "ignore_repeated_ngrams": True}
    if scored < profile["min_scored_tokens"]:
        result["status"] = "insufficient_length"
    # Cache/profile/source hashes are checked again in the parent after this run.
    return result


def _execute(project: Path, paper_id: str) -> dict:
    environment = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                   "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false",
                   "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "1"}
    try:
        result = subprocess.run([sys.executable, "-m", "scripts.statistical_watermarks", "--worker", str(project), paper_id],
            cwd=ROOT, env=environment, capture_output=True, text=True, timeout=WORKER_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        raise ValueError("offline watermark detector exceeded its fixed CPU time bound") from None
    if result.returncode or len(result.stdout) > 10_000:
        raise ValueError("offline watermark detector failed; dependency/cache/configuration review is required")
    try:
        value = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ValueError("offline watermark detector returned an invalid bounded result") from None
    allowed = {"status", "token_count", "scored_tokens", "green_tokens", "green_fraction", "z_score",
               "null_tail_probability", "threshold", "ignore_repeated_ngrams"}
    if not isinstance(value, dict) or not set(value).issubset(allowed) or value.get("status") not in {"detected", "not_detected", "insufficient_length"}:
        raise ValueError("offline watermark detector returned an unsupported result")
    return value


def _inventory(project: Path, paper_id: str) -> list[dict]:
    return [{"path": target.relative_to(project).as_posix(), "sha256": sha(target),
             "origin": output_provenance.current_origin(project, target)}
            for target in manuscript_hygiene.inventory(project, paper_id)]


def audit(project: Path, paper_id: str) -> dict:
    """Recompute assessment; missing configuration is explicitly unknown."""
    project = project.resolve()
    _paper(project, paper_id)
    files = _inventory(project, paper_id)
    report = {"schema_version": "1.0", "paper_id": paper_id, "status": "unknown", "errors": [],
              "warnings": ["Unknown statistical/vendor schemes and media watermarks are not assessed; no universal absence claim is possible."],
              "files": files, "implementation": _implementation(), "profile": None, "runtime": None,
              "result": {"status": "unknown", "reason": "no applicable detector configuration supplied"},
              "coverage": {"hf_greenlist": "unknown", "SynthID_Text": "unknown_no_applicable_detector_configuration",
                           "unknown_vendor_schemes": "unknown", "image_watermarks": "not_assessed",
                           "C2PA_EXIF_PDF_objects": "not_assessed", "unassessed_files": [row["path"] for row in files]},
              "negative_result_meaning": "Not detected means only this configured scheme, key and extracted canonical text at this threshold; it does not establish absence or human authorship.",
              "remediation": "A detected signal blocks release. Use the existing evidence-preserving writer/remediator pass, retain originals and required disclosures, then rerun. Do not add paid loops, change models, randomly shuffle or spin synonyms.",
              **LIMITS}
    relative = f"papers/{paper_id}/watermark-assessment.json"
    profile_path = path_in(project, relative, exists=False)
    if not profile_path.exists():
        return report
    report["profile"] = {"path": relative, "sha256": sha(profile_path)}
    try:
        profile, safe, text = _prepare(project, paper_id)
        report["profile"] = safe
        _secret(profile)
        report["runtime"] = _versions()
        if not runtime_available():
            raise ValueError("configured watermark assessment requires the fixed optional offline CPU dependencies")
        result = _execute(project, paper_id)
        if _prepare(project, paper_id)[1] != safe or _inventory(project, paper_id) != files:
            raise ValueError("watermark sources, applicability evidence or cache changed during assessment")
        report["result"] = result
        report["status"] = result["status"]
        report["coverage"]["hf_greenlist"] = "assessed_exact_configured_canonical_text"
        report["coverage"]["unassessed_files"] = [row["path"] for row in files if row["path"] not in safe["source_paths"]]
        if result["status"] == "detected":
            report["errors"].append("Configured greenlist watermark signal detected; preserve evidence, revise and rescan before release.")
        elif result["status"] == "insufficient_length":
            report["errors"].append("Configured watermark detector has insufficient independent scored tokens; absence cannot be assessed.")
    except (ValueError, OSError, KeyError, TypeError, AttributeError, ImportError, RuntimeError, RecursionError):
        # Never print dependency exceptions, secret values, tokenizer contents or
        # exception reprs. The fixed diagnostic cannot leak them into model input.
        report["status"] = "error"
        report["result"] = {"status": "error", "reason": "configured detector could not safely assess current canonical text"}
        report["errors"].append("Configured statistical watermark assessment failed: check applicable human evidence, complete canonical sources, pinned runtime, secret and bounded local cache; no absence result was established.")
    return report


def refresh(project: Path, paper_id: str) -> dict:
    _cloud()
    project = project.resolve()
    value = audit(project, paper_id)
    value["execution"] = {"mode": "cloud", "receipt_id": str(os.environ.get("GITHUB_RUN_ID") or
        os.environ.get("DR_OS_CLOUD_EXECUTION_RECEIPT_ID") or "authorized-cloud")}
    target = path_in(project, f"{PREFIX}/{paper_id}/latest.json", exists=False)
    write(target, value)
    output_provenance.record_model_writes(project, [target], family="other", provider=PROVIDER,
        model=DETECTOR, role="bounded-watermark-assessment-not-authorship-attestation", run_id="scan-" + uuid.uuid4().hex)
    return value


def validate_saved_report(project: Path, paper_id: str) -> list[str]:
    try:
        target = path_in(project, f"{PREFIX}/{paper_id}/latest.json")
        saved = read(target)
        origin = output_provenance.current_origin(project, target)
        if origin.get("status") != "tracked" or origin.get("provider") != PROVIDER or origin.get("family") != "other":
            raise ValueError("statistical watermark report lacks protected control-plane provenance")
        if saved.get("execution", {}).get("mode") != "cloud" or not saved["execution"].get("receipt_id"):
            raise ValueError("statistical watermark report lacks cloud execution identity")
        actual = audit(project, paper_id)
        if any(saved.get(key) != value for key, value in actual.items()):
            raise ValueError("statistical watermark report is stale or differs from full source/cache recomputation")
        return actual["errors"]
    except (ValueError, OSError, KeyError, TypeError, AttributeError, RuntimeError):
        return ["Statistical watermark report is missing, stale, modified, untrusted or currently blocking release."]


def review_binding(project: Path, paper_id: str) -> dict:
    target = path_in(project, f"{PREFIX}/{paper_id}/latest.json", exists=False)
    return {"path": target.relative_to(project).as_posix(), "sha256": sha(target) if target.is_file() else None,
            "implementation": _implementation()}


def prompt_feedback(project: Path, paper_id: str) -> str:
    target = path_in(project, f"{PREFIX}/{paper_id}/latest.json", exists=False)
    value = read(target) if target.is_file() else {"status": "unknown", "errors": ["assessment not yet refreshed"]}
    return json.dumps({"report": target.relative_to(project).as_posix(), "status": value.get("status"),
        "errors": value.get("errors", []), "warnings": value.get("warnings", []),
        "watermark_absence_verified": False, "all_watermark_types_assessed": False,
        "instruction": "Preserve evidence and mandatory disclosures. Resolve configured positive/error findings within existing passes; unknown coverage is not watermark absence."}, separators=(",", ":"))


def _worker() -> int:
    try:
        _cloud()
        if len(sys.argv) != 4 or sys.argv[1] != "--worker":
            return 2
        print(json.dumps(_detect_cached(Path(sys.argv[2]).resolve(), sys.argv[3]), allow_nan=False))
        return 0
    except Exception:
        # Raw exceptions from third-party imports/configuration may contain secrets.
        return 2


if __name__ == "__main__":
    raise SystemExit(_worker())
