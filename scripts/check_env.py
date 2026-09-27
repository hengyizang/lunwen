#!/usr/bin/env python3
"""Report the local environment needed by the research workflow."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path


def version_output(command: str) -> str | None:
    return shutil.which(command)


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soft", action="store_true", help="Always return success")
    parser.add_argument("--mode", choices=("api", "cli", "all"), default="api")
    parser.add_argument("--install-root", help="required repository/runtime WSL path")
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
        for name in ["latexmk", "pandoc", "docker", "podman", "quarto", "Rscript", "pqa", "tu", "ref-verify"]
    }
    repository_root = Path(__file__).resolve().parents[1]
    install_root_ok = not args.install_root or repository_root.resolve() == Path(args.install_root).resolve()
    docker_root = None
    if optional.get("docker"):
        try:
            docker_root = subprocess.run(["docker","info","--format","{{json .DockerRootDir}}"],capture_output=True,text=True,timeout=15,check=False).stdout.strip().strip('"') or None
        except (OSError,subprocess.TimeoutExpired):
            pass
    receipt = repository_root/".runtime"/"docker-location.json";docker_d_drive_verified=False
    if receipt.is_file():
        try:
            value=json.loads(receipt.read_text(encoding="utf-8-sig"));configured=str(value.get("configured_path","")).lower().rstrip("\\")
            expected=r"d:\ad\lunwen\.runtime\docker-desktop"
            docker_d_drive_verified=value.get("verified") is True and (configured==expected or configured.startswith(expected+"\\"))
        except (OSError,json.JSONDecodeError):
            pass
    report = {
        "python": {
            "version": platform.python_version(),
            "ok": sys.version_info >= (3, 10),
        },
        "platform": platform.platform(),
        "wsl": in_wsl,
        "mode": args.mode,
        "repository_root": str(repository_root),
        "required_install_root": args.install_root,
        "install_root_ok": install_root_ok,
        "docker_root": docker_root,
        "docker_location_receipt": str(receipt),
        "docker_d_drive_verified": docker_d_drive_verified,
        "required_commands": required,
        "optional_commands": optional,
        "optional_ai4science_packages": {
            "paper-qa": package_version("paper-qa"),
            "tooluniverse": package_version("tooluniverse"),
        },
        "optional_reference_packages": {
            "ref-verify": package_version("ref-verify"),
        },
        "recommendations": [],
    }
    if not in_wsl and platform.system() == "Linux":
        report["recommendations"].append(
            "Native Linux is supported; WSL is only required on Windows."
        )
    elif not in_wsl:
        report["recommendations"].append(
            f"On Windows 11, use WSL2 Ubuntu and keep this project under {args.install_root or '/mnt/d/ad/lunwen'}."
        )
    if args.install_root and not install_root_ok:
        report["recommendations"].append(f"Move the repository and runtime to {args.install_root}.")
    if args.install_root and optional.get("docker") and not docker_d_drive_verified:
        report["recommendations"].append("Docker Desktop disk image is not verified under D:\\ad\\lunwen\\.runtime\\docker-desktop.")
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
    okay = report["python"]["ok"] and all(required.values()) and install_root_ok
    return 0 if okay or args.soft else 2


if __name__ == "__main__":
    raise SystemExit(main())
