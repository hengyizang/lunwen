#!/usr/bin/env python3
"""Static portability probe: can a GitHub project run in this environment?

Read-only and optional. It never installs anything, writes project state, or
requires registration. Use it when deciding whether to patch an upstream, and
ignore it whenever you prefer to just try running the thing.
"""
from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import sys
from pathlib import Path

SERVICE_WORDS = ("redis", "postgres", "mysql", "mongo", "rabbitmq", "kafka",
                 "elasticsearch", "qdrant", "weaviate", "chroma", "milvus",
                 "nginx", "ollama", "celery", "minio", "etcd")
GPU_WORDS = ("cuda", "nvidia", "--gpus", "nvidia-docker", "cu118", "cu121",
             "cu124", "pytorch", "tensorflow", "triton")
GUI_WORDS = ("electron", "playwright", "puppeteer", "selenium", "xvfb",
             "tauri", "pyqt", "tkinter", "x11")
COMPILE_WORDS = ("ext_modules", "cython", "cmake", "cmakelists",
                 "setuptools.extension", "rustc", "cargo build", "pybind11")
APT_MARKERS = ("apt-get install", "apt install", "apk add", "yum install",
               "dnf install")
MANIFEST_NAMES = ("requirements", "pyproject.toml", "setup.py", "setup.cfg",
                  "package.json", "environment.yml", "pipfile", "dockerfile",
                  "compose", "makefile", "cmakelists.txt", "containerfile")
IMPORT_ALIAS = {"pymupdf": "fitz", "pyyaml": "yaml", "pillow": "PIL",
                "beautifulsoup4": "bs4", "python-docx": "docx",
                "scikit-learn": "sklearn", "opencv-python": "cv2"}


def capabilities() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.system(),
        "compiler": any(shutil.which(x) for x in ("gcc", "cl", "g++", "cc")),
        "container_engine": any(shutil.which(x) for x in ("docker", "podman")),
        "node": bool(shutil.which("node")),
        "gpu": bool(shutil.which("nvidia-smi")),
        "pip": True,
    }


def _hits(words: tuple[str, ...], text: str) -> list[str]:
    """Whole-word matches only, so 'redistributed' is not a redis service."""
    return sorted({w for w in words
                   if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text)})


def missing_imports(dep_lines: list[str]) -> list[str]:
    import importlib.util
    missing = []
    for line in dep_lines:
        name = re.split(r"[<>=!~\[; ]", line.strip(), maxsplit=1)[0].strip()
        if not name:
            continue
        module = IMPORT_ALIAS.get(name.lower(), name.lower().replace("-", "_"))
        try:
            found = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            found = False
        if not found:
            missing.append(name)
    return missing


def scan(root: Path) -> dict:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.stat().st_size < 2_000_000:
            files.append(path)
    names = [p.name.lower() for p in files]
    manifest = []
    for p in files:
        n = p.name.lower()
        if any(k in n for k in MANIFEST_NAMES):
            try:
                manifest.append(p.read_text(encoding="utf-8", errors="replace")[:200_000])
            except OSError:
                continue
    low = "\n".join(manifest).lower()
    deps = _dep_lines(root)
    return {
        "files": [str(p.relative_to(root)) for p in files],
        "has_requirements": any("requirements" in n and n.endswith(".txt") for n in names),
        "has_pyproject": "pyproject.toml" in names,
        "has_setup_py": "setup.py" in names,
        "has_package_json": "package.json" in names,
        "has_dockerfile": any(n.startswith("dockerfile") or n == "containerfile" for n in names),
        "has_compose": any("compose" in n for n in names),
        "services": _hits(SERVICE_WORDS, low),
        "gpu": _hits(GPU_WORDS, low),
        "gui": _hits(GUI_WORDS, low),
        "apt": [w for w in APT_MARKERS if w in low],
        "compile": _hits(COMPILE_WORDS, low),
        "python_dep_lines": deps,
        "missing_imports": missing_imports(deps),
        "c_sources": sum(1 for n in names if n.endswith((".c", ".cpp", ".cc", ".cu", ".rs"))),
    }


def _dep_lines(root: Path) -> list[str]:
    out: list[str] = []
    for pattern in ("requirements*.txt",):
        for path in sorted(root.glob(pattern)):
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith(("#", "-", "git+")):
                    out.append(line)
    return out[:40]


def judge(root: Path, caps: dict) -> dict:
    s = scan(root)
    blockers: list[str] = []
    patches: list[str] = []
    verdict = "runs_now"

    if s["python_dep_lines"]:
        if s["missing_imports"]:
            verdict = "pip_install"
            patches.append("Missing locally: " + ", ".join(s["missing_imports"])
                           + f". Install with: python -m pip install -r {root / 'requirements.txt'}")
        else:
            verdict = "runs_now"
            patches.append("All declared Python imports are already available locally; "
                           "call the entrypoint directly.")
    if s["has_pyproject"] or s["has_setup_py"]:
        patches.append("Try `python -m pip install -e .` (or `.[<extra>]`) before editing anything.")

    if s["has_dockerfile"] and not s["services"] and not s["gpu"] and not s["apt"]:
        verdict = "small_patch"
        patches.append("Docker looks like packaging only. Translate `RUN pip install ...` "
                       "from the Dockerfile into a host pip command and call the entrypoint directly.")
    if s["apt"]:
        verdict = "small_patch"
        patches.append("System packages are requested. Find pip equivalents "
                       "(poppler -> pypdf/PyMuPDF, tesseract -> OCR API or skip) "
                       "or delete the optional feature that needs them.")
    if s["services"]:
        verdict = "major_rewrite"
        blockers.append("Service stack detected: " + ", ".join(s["services"]))
        patches.append("Replace compose services with in-process equivalents "
                       "(fakeredis/dict, sqlite/files, in-memory queue), or point the "
                       "adapter at an external endpoint. Keep the call interface unchanged.")
    if s["gui"]:
        if verdict != "major_rewrite":
            verdict = "small_patch"
        patches.append("Extract a CLI/headless entrypoint; avoid the desktop shell. "
                       "A dots cloud computer can host the GUI if a headless path is impossible.")
    if s["gpu"] and not caps["gpu"]:
        verdict = "needs_other_machine"
        blockers.append("GPU/CUDA signals with no local GPU: " + ", ".join(s["gpu"]))
        patches.append("Remove `--gpus all`, switch inference to CPU/onnxruntime if available, "
                       "or extract the model call behind a remote API. Training-scale work "
                       "belongs on a GPU VM or a paid larger runner.")
    if (s["compile"] or s["c_sources"] > 3) and not caps["compiler"]:
        if verdict != "needs_other_machine":
            verdict = "needs_other_machine"
        blockers.append("Native compilation signals with no C/C++ toolchain on this host")
        patches.append("Use a prebuilt wheel for this Python/ABI, replace the extension "
                       "with a pure-Python equivalent, or build on a machine with a compiler.")
    if s["has_compose"] and s["has_dockerfile"] and not caps["container_engine"]:
        if verdict == "runs_now":
            verdict = "small_patch"
        patches.append("No local Docker daemon. Do not run compose; flatten it into "
                       "direct process calls, or use the GitHub Actions runner / a root VM.")
    if s["has_package_json"] and not caps["node"]:
        blockers.append("Node project but node is not installed")
        patches.append("Install Node or rewrite the needed logic in Python.")

    if verdict == "runs_now" and not s["python_dep_lines"] and not (s["has_pyproject"] or s["has_setup_py"]):
        patches.append("No dependency declaration found; just try calling its entrypoint.")

    return {
        "path": str(root),
        "verdict": verdict,
        "blockers": blockers,
        "patches": patches,
        "signals": {k: v for k, v in s.items() if k != "files" and v},
        "file_count": len(s["files"]),
        "capabilities": caps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="local project directories")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    caps = capabilities()
    results = []
    for raw in args.paths:
        root = Path(raw).resolve()
        if not root.is_dir():
            print("ERROR not a directory: " + raw, file=sys.stderr)
            return 1
        results.append(judge(root, caps))
    if args.json:
        print(json.dumps({"schema_version": "1.0", "results": results},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"Local: Python {caps['python']} on {caps['platform']} | "
          f"compiler={caps['compiler']} docker={caps['container_engine']} "
          f"node={caps['node']} gpu={caps['gpu']}\n")
    for r in results:
        print(f"{Path(r['path']).name}: {r['verdict'].upper()} ({r['file_count']} files)")
        for b in r["blockers"]:
            print("  blocker: " + b)
        for p in r["patches"]:
            print("  patch:   " + p)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
