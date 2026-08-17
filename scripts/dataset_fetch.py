#!/usr/bin/env python3
"""Validate and safely download a licensed public dataset over HTTPS."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Callable

try:
    from scripts.network_safety import (
        NetworkSafetyError,
        PublicHTTPSRedirectHandler,
        require_public_https_url,
        validate_https_url,
    )
except ModuleNotFoundError:  # Direct execution from scripts/.
    from network_safety import (  # type: ignore[no-redef]
        NetworkSafetyError,
        PublicHTTPSRedirectHandler,
        require_public_https_url,
        validate_https_url,
    )


DEFAULT_MAX_BYTES = 5 * 1024 * 1024 * 1024


class DatasetError(RuntimeError):
    pass


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetError(f"Cannot read manifest {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise DatasetError("Manifest must be a JSON object")
    return value


def https_url(value: Any, field: str) -> str:
    try:
        return validate_https_url(value, field)
    except NetworkSafetyError as exc:
        raise DatasetError(str(exc)) from exc


def validate_manifest(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = [
        "schema_version",
        "dataset_id",
        "title",
        "provider",
        "source_url",
        "version",
        "accessed_at",
        "license",
        "download",
        "provenance",
        "unit_of_analysis",
        "split_strategy",
        "known_limitations",
    ]
    for key in required:
        if key not in value:
            errors.append(f"missing field: {key}")

    try:
        https_url(value.get("source_url"), "source_url")
    except DatasetError as exc:
        errors.append(str(exc))

    license_value = value.get("license")
    if not isinstance(license_value, dict):
        errors.append("license must be an object")
    else:
        for key in [
            "name",
            "url",
            "research_use_allowed",
            "redistribution_allowed",
            "confirmed_by_human",
        ]:
            if key not in license_value:
                errors.append(f"missing license field: {key}")
        try:
            https_url(license_value.get("url"), "license.url")
        except DatasetError as exc:
            errors.append(str(exc))
        if license_value.get("research_use_allowed") is not True:
            errors.append("license.research_use_allowed must be true")

    download = value.get("download")
    if not isinstance(download, dict):
        errors.append("download must be an object")
    else:
        try:
            https_url(download.get("url"), "download.url")
        except DatasetError as exc:
            errors.append(str(exc))
        checksum = download.get("sha256")
        if checksum != "pending" and (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(char not in "0123456789abcdefABCDEF" for char in checksum)
        ):
            errors.append("download.sha256 must be 64 hex characters or pending")
        expected = download.get("expected_bytes")
        if expected is not None and (not isinstance(expected, int) or expected < 0):
            errors.append("download.expected_bytes must be null or a non-negative integer")

    if not isinstance(value.get("known_limitations"), list):
        errors.append("known_limitations must be an array")
    return errors


def safe_filename(manifest: dict[str, Any]) -> str:
    download = manifest["download"]
    candidate = download.get("filename")
    if not candidate:
        from urllib.parse import urlparse

        candidate = Path(urlparse(download["url"]).path).name
    if not candidate or Path(candidate).name != candidate or candidate in {".", ".."}:
        raise DatasetError("download filename is missing or unsafe")
    return candidate


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_dataset(
    manifest_path: Path,
    destination: Path,
    accept_license: bool,
    max_bytes: int,
    overwrite: bool,
    *,
    opener: Callable[..., Any] | None = None,
    resolver: Callable[..., list[tuple[Any, ...]]] | None = None,
) -> Path:
    manifest = load_manifest(manifest_path)
    errors = validate_manifest(manifest)
    if errors:
        raise DatasetError("; ".join(errors))
    license_value = manifest["license"]
    if not accept_license or license_value.get("confirmed_by_human") is not True:
        raise DatasetError(
            "Human license confirmation is required in the manifest and via --accept-license"
        )

    url = manifest["download"]["url"]
    try:
        public_url = require_public_https_url(
            url,
            "download.url",
            **({"resolver": resolver} if resolver is not None else {}),
        )
    except NetworkSafetyError as exc:
        raise DatasetError(str(exc)) from exc
    filename = safe_filename(manifest)
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / filename
    expected_hash = manifest["download"]["sha256"].lower()

    if target.exists() and not overwrite:
        if expected_hash != "pending" and file_sha256(target) == expected_hash:
            return target
        raise DatasetError(f"Target exists: {target}; use --overwrite only after review")

    request = urllib.request.Request(
        public_url,
        headers={"User-Agent": "DoctoralResearchOS/0.2 (+research data acquisition)"},
    )
    temp_name: str | None = None
    try:
        open_url = opener or urllib.request.build_opener(
            PublicHTTPSRedirectHandler(resolver) if resolver is not None else PublicHTTPSRedirectHandler()
        ).open
        with open_url(request, timeout=60) as response:
            final_url = response.geturl()
            try:
                require_public_https_url(
                    final_url,
                    "redirected download URL",
                    **({"resolver": resolver} if resolver is not None else {}),
                )
            except NetworkSafetyError as exc:
                raise DatasetError(str(exc)) from exc
            content_length = response.headers.get("Content-Length")
            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError as exc:
                    raise DatasetError("Server returned an invalid Content-Length") from exc
                if declared_size > max_bytes:
                    raise DatasetError("Server Content-Length exceeds the configured limit")

            digest = hashlib.sha256()
            total = 0
            with tempfile.NamedTemporaryFile(
                "wb", dir=destination, prefix=f".{filename}.", delete=False
            ) as handle:
                temp_name = handle.name
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise DatasetError("Download exceeded the configured byte limit")
                    digest.update(chunk)
                    handle.write(chunk)

        actual_hash = digest.hexdigest()
        expected_bytes = manifest["download"].get("expected_bytes")
        if expected_bytes is not None and total != expected_bytes:
            raise DatasetError(
                f"Size mismatch: expected {expected_bytes}, downloaded {total}"
            )
        if expected_hash != "pending" and actual_hash != expected_hash:
            raise DatasetError(
                f"SHA-256 mismatch: expected {expected_hash}, downloaded {actual_hash}"
            )
        os.replace(temp_name, target)
        temp_name = None
        print(
            json.dumps(
                {
                    "path": str(target),
                    "bytes": total,
                    "sha256": actual_hash,
                    "source_url": public_url,
                },
                indent=2,
            )
        )
        if expected_hash == "pending":
            print(
                "warning: record this SHA-256 in a reviewed manifest before G3",
                file=sys.stderr,
            )
        return target
    finally:
        if temp_name:
            Path(temp_name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("manifest", type=Path)

    download = sub.add_parser("download")
    download.add_argument("manifest", type=Path)
    download.add_argument("destination", type=Path)
    download.add_argument("--accept-license", action="store_true")
    download.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    download.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "validate":
            errors = validate_manifest(load_manifest(args.manifest))
            if errors:
                raise DatasetError("; ".join(errors))
            print("Dataset manifest is structurally valid.")
        else:
            if args.max_bytes <= 0:
                raise DatasetError("--max-bytes must be positive")
            download_dataset(
                args.manifest,
                args.destination,
                args.accept_license,
                args.max_bytes,
                args.overwrite,
            )
        return 0
    except (DatasetError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
