#!/usr/bin/env python3
"""Inspect and safely ingest a local publisher template ZIP archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


MAX_MEMBERS = 5000
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024
ALLOWED_SUFFIXES = {
    ".bib",
    ".bst",
    ".cfg",
    ".cls",
    ".def",
    ".doc",
    ".docx",
    ".dtx",
    ".eps",
    ".gif",
    ".ins",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".rtf",
    ".sty",
    ".tex",
    ".txt",
}


class TemplateError(RuntimeError):
    pass


def normalize_member(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or any(":" in part for part in path.parts)
    ):
        raise TemplateError(f"Unsafe archive path: {name!r}")
    return path


def inspect_archive(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".zip":
        raise TemplateError("Only ZIP template archives are supported")
    if not path.is_file():
        raise TemplateError(f"Archive not found: {path}")

    members: list[dict[str, Any]] = []
    total = 0
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise TemplateError("Archive contains too many members")
        for info in infos:
            member_path = normalize_member(info.filename)
            if info.flag_bits & 0x1:
                raise TemplateError(f"Encrypted archive member is not allowed: {info.filename}")
            unix_mode = info.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise TemplateError(f"Symlink archive member is not allowed: {info.filename}")
            if info.is_dir():
                continue
            suffix = member_path.suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                raise TemplateError(
                    f"Unexpected template file type {suffix or '<none>'}: {info.filename}"
                )
            total += info.file_size
            if total > MAX_UNCOMPRESSED_BYTES:
                raise TemplateError("Archive is too large after decompression")
            members.append(
                {
                    "path": member_path.as_posix(),
                    "bytes": info.file_size,
                    "compressed_bytes": info.compress_size,
                }
            )
    return {
        "archive": str(path),
        "archive_sha256": sha256_file(path),
        "member_count": len(members),
        "uncompressed_bytes": total,
        "members": members,
        "detected": {
            "classes": sorted(m["path"] for m in members if m["path"].endswith(".cls")),
            "latex_samples": sorted(
                m["path"] for m in members if m["path"].endswith(".tex")
            ),
            "word_files": sorted(
                m["path"]
                for m in members
                if m["path"].endswith((".doc", ".docx"))
            ),
            "bibliography_styles": sorted(
                m["path"] for m in members if m["path"].endswith(".bst")
            ),
        },
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest_archive(archive_path: Path, destination: Path) -> dict[str, Any]:
    inventory = inspect_archive(archive_path)
    if destination.exists():
        raise TemplateError(f"Destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent)
    )
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                member_path = normalize_member(info.filename)
                if info.is_dir():
                    (temporary / Path(*member_path.parts)).mkdir(
                        parents=True, exist_ok=True
                    )
                    continue
                target = temporary / Path(*member_path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)

        file_hashes = {}
        for path in sorted(temporary.rglob("*")):
            if path.is_file():
                file_hashes[path.relative_to(temporary).as_posix()] = sha256_file(path)
        inventory["extracted_file_sha256"] = file_hashes
        inventory["ingest_note"] = (
            "Publisher template retained locally; verify its terms and current version at G5."
        )
        (temporary / "template-inventory.json").write_text(
            json.dumps(inventory, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
        return inventory
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = sub.add_parser("inspect")
    inspect_cmd.add_argument("archive", type=Path)
    ingest_cmd = sub.add_parser("ingest")
    ingest_cmd.add_argument("archive", type=Path)
    ingest_cmd.add_argument("destination", type=Path)
    args = parser.parse_args()

    try:
        if args.command == "inspect":
            result = inspect_archive(args.archive)
        else:
            result = ingest_archive(args.archive, args.destination)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (TemplateError, OSError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

