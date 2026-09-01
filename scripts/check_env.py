#!/usr/bin/env python3
"""Report the local environment needed by the research workflow."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sys
from pathlib import Path


def version_output(command: str) -> str | None:
    return shutil.which(command)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soft", action="store_true", help="Always return success")
    parser.add_argument("--mode", choices=("api", "cli", "all"), default="api")
    args = parser.parse_args()

    in_wsl = (
        "microsoft" in platform.release().lower()
        or "microsoft" in platform.version().lower()
        or Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists()
    )
    required_names=["git"]+(["claude","codex"] if args.mode in {"cli","all"} else [])
    required = {name: version_output(name) for name in required_names}
    optional = {
        name: version_output(name)
        for name in ["latexmk", "pandoc", "docker", "quarto", "Rscript"]
    }
    report = {
        "python": {
            "version": platform.python_version(),
            "ok": sys.version_info >= (3, 10),
        },
        "platform": platform.platform(),
        "wsl": in_wsl,
        "mode": args.mode,
        "required_commands": required,
        "optional_commands": optional,
        "recommendations": [],
    }
    if not in_wsl and platform.system() == "Linux":
        report["recommendations"].append(
            "Native Linux is supported; WSL is only required on Windows."
        )
    elif not in_wsl:
        report["recommendations"].append(
            "On Windows 11, use WSL2 Ubuntu and keep the repo under ~/code."
        )
    for name, path in required.items():
        if path is None:
            report["recommendations"].append(f"Install or expose {name} on PATH.")
    if args.mode in {"api","all"}:
        configured={name:bool(os.environ.get(name)) for name in ("UUAPI_API_KEY","UUAPI_BASE_URL","UUAPI_ANTHROPIC_MODEL","UUAPI_OPENAI_MODEL")}
        report["uuapi_api_configuration"]=configured
        if not all(configured.values()):report["recommendations"].append("Set the four UUAPI_* environment variables before live API use.")
    if optional["latexmk"] is None:
        report["recommendations"].append(
            "Install TeX Live/latexmk before validating LaTeX journal templates."
        )
    if optional["pandoc"] is None:
        report["recommendations"].append(
            "Install pandoc for optional document conversions."
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    okay = report["python"]["ok"] and all(required.values())
    return 0 if okay or args.soft else 2


if __name__ == "__main__":
    raise SystemExit(main())
