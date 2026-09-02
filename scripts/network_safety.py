#!/usr/bin/env python3
"""Small network-safety helpers for public research metadata and downloads."""

from __future__ import annotations

import ipaddress
import json
import socket
import urllib.parse
import urllib.request
from typing import Any, Callable


DEFAULT_JSON_LIMIT = 8 * 1024 * 1024


class NetworkSafetyError(RuntimeError):
    """Raised when a URL or response violates the public-network policy."""


class PublicHTTPSRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject unsafe redirect targets before urllib connects to them."""

    def __init__(
        self,
        resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
    ) -> None:
        super().__init__()
        self.resolver = resolver

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> Any:
        require_public_https_url(newurl, "redirected URL", resolver=self.resolver)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_https_url(value: Any, field: str = "url") -> str:
    if not isinstance(value, str) or not value.strip():
        raise NetworkSafetyError(f"{field} must be a non-empty string")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise NetworkSafetyError(f"{field} must use HTTPS")
    if parsed.username or parsed.password:
        raise NetworkSafetyError(f"{field} must not contain credentials")
    if parsed.fragment:
        value = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.query, "")
        )
    return value


def _resolved_addresses(
    hostname: str,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> set[str]:
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            answers = resolver(hostname, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise NetworkSafetyError(f"Cannot resolve public host {hostname!r}: {exc}") from exc
        addresses = {answer[4][0].split("%", 1)[0] for answer in answers}
        if not addresses:
            raise NetworkSafetyError(f"Host {hostname!r} resolved to no addresses")
        return addresses
    return {str(literal)}


def require_public_https_url(
    value: Any,
    field: str = "url",
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> str:
    """Require HTTPS and reject loopback, private, reserved, or link-local hosts."""

    url = validate_https_url(value, field)
    hostname = urllib.parse.urlsplit(url).hostname
    assert hostname is not None
    lowered = hostname.rstrip(".").lower()
    if lowered == "localhost" or lowered.endswith((".localhost", ".local")):
        raise NetworkSafetyError(f"{field} must resolve to a public Internet host")
    for address in _resolved_addresses(lowered, resolver=resolver):
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError as exc:
            raise NetworkSafetyError(f"Invalid resolved address for {field}: {address}") from exc
        if not parsed.is_global:
            raise NetworkSafetyError(
                f"{field} resolves to a non-public address ({parsed.compressed})"
            )
    return url


def read_bounded_response(response: Any, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise NetworkSafetyError("max_bytes must be positive")
    length = response.headers.get("Content-Length") if response.headers else None
    if length:
        try:
            if int(length) > max_bytes:
                raise NetworkSafetyError("Response Content-Length exceeds the configured limit")
        except ValueError as exc:
            raise NetworkSafetyError("Response has an invalid Content-Length") from exc
    payload = response.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise NetworkSafetyError("Response exceeded the configured byte limit")
    return payload


def fetch_json(
    url: str,
    *,
    timeout: int = 30,
    max_bytes: int = DEFAULT_JSON_LIMIT,
    headers: dict[str, str] | None = None,
    method: str = "GET",
    json_body: Any | None = None,
    opener: Callable[..., Any] | None = None,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> Any:
    """Fetch bounded JSON from a public HTTPS endpoint and validate redirects."""

    public_url = require_public_https_url(url, resolver=resolver)
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "DoctoralResearchOS/0.2 (+research metadata discovery)",
    }
    request_headers.update(headers or {})
    normalized_method = method.upper()
    if normalized_method not in {"GET", "POST"}:
        raise NetworkSafetyError("JSON requests support only GET or POST")
    data = None
    if json_body is not None:
        if normalized_method != "POST":
            raise NetworkSafetyError("json_body requires POST")
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        public_url,
        data=data,
        headers=request_headers,
        method=normalized_method,
    )
    open_url = opener or urllib.request.build_opener(
        PublicHTTPSRedirectHandler(resolver)
    ).open
    try:
        with open_url(request, timeout=timeout) as response:
            final_url = response.geturl() if hasattr(response, "geturl") else public_url
            require_public_https_url(final_url, "redirected URL", resolver=resolver)
            payload = read_bounded_response(response, max_bytes)
    except NetworkSafetyError:
        raise
    except OSError as exc:
        raise NetworkSafetyError(f"Request failed for {public_url}: {exc}") from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NetworkSafetyError(f"Endpoint did not return valid UTF-8 JSON: {exc}") from exc
