"""Explicit CNY billing contracts; never select models or execute tools.

Version 2 quotes bind the transport route and billing plan/group/mode separately
from inference settings. Context brackets are inclusive at both endpoints and
must cover every non-negative length exactly once. Full-request context counts
cached input before applying any cache discount; an uncached-input basis is
allowed only when the quote explicitly declares it. Tool charges require a
bounded authorization and a complete, typed provider/gateway usage receipt.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


class BillingQuoteError(ValueError):
    """A quote or billed receipt is unknown, ambiguous or malformed."""


IDENTITY_FIELDS = ("plan", "group", "mode")
RATE_FIELDS = ("input_per_million", "output_per_million", "cache_read_per_million", "cache_write_per_million")
CONTEXT_BASES = {"full_request_input_tokens", "uncached_input_tokens"}


def number(value: Any, label: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BillingQuoteError(f"{label} must be a numeric CNY value")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise BillingQuoteError(f"{label} must be finite and {'positive' if positive else 'non-negative'}")
    return float(value)


def count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BillingQuoteError(f"{label} must be a non-negative integer")
    return value


def identity(value: Any = None) -> dict[str, str]:
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - set(IDENTITY_FIELDS):
        raise BillingQuoteError("billing identity permits only plan, group and mode")
    result = {}
    for key in IDENTITY_FIELDS:
        item = value.get(key, "")
        if not isinstance(item, str) or "|" in item or item != item.strip():
            raise BillingQuoteError(f"billing {key} must be an exact string without a pipe")
        result[key] = item
    return result


def quote_digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _rates(value: dict, *, cache_required: bool) -> dict:
    if any(field not in value for field in RATE_FIELDS[:2]):
        raise BillingQuoteError("quote needs input/output CNY rates per million")
    result = {field: number(value[field], field) for field in RATE_FIELDS if field in value}
    if cache_required and any(field not in result for field in RATE_FIELDS[2:]):
        raise BillingQuoteError("conditional quotes need explicit cache read/write rates, including zero")
    return result


def _route(value: dict) -> tuple[str, str, str]:
    result = tuple(value.get(key) for key in ("provider", "endpoint", "model"))
    if any(not isinstance(item, str) or not item or "|" in item for item in result):
        raise BillingQuoteError("quote needs exact provider, endpoint and model strings")
    if not result[1].startswith("https://"):
        raise BillingQuoteError("conditional billing endpoint must use HTTPS")
    return result


def _normalize(value: Any) -> dict:
    if not isinstance(value, dict):
        raise BillingQuoteError("each quote must be an object")
    allowed = {"provider", "endpoint", "model", *IDENTITY_FIELDS, "currency", "price_version", "context_basis", "context_brackets", "tool_fees", *RATE_FIELDS}
    if set(value) - allowed:
        raise BillingQuoteError("unknown conditional quote fields")
    if any(field not in value for field in IDENTITY_FIELDS):
        raise BillingQuoteError("conditional quote must explicitly declare plan/group/mode; use an empty string only when not applicable")
    route = _route(value)
    billing_identity = identity({key: value.get(key, "") for key in IDENTITY_FIELDS})
    if value.get("currency") != "CNY":
        raise BillingQuoteError("conditional quote currency must explicitly be CNY")
    version = value.get("price_version")
    if not isinstance(version, str) or not version.strip():
        raise BillingQuoteError("conditional quote needs an explicit price_version")
    result = {"quote_schema": "2.0", "provider": route[0], "endpoint": route[1], "model": route[2],
              "billing_identity": billing_identity, "currency": "CNY", "price_version": version}
    brackets = value.get("context_brackets")
    if brackets is None:
        if "context_basis" in value:
            raise BillingQuoteError("context_basis without context_brackets is ambiguous")
        result.update(_rates(value, cache_required=True))
    else:
        if any(field in value for field in RATE_FIELDS):
            raise BillingQuoteError("bracket rates cannot be mixed with top-level token rates")
        basis = value.get("context_basis")
        if not isinstance(basis, str) or basis not in CONTEXT_BASES:
            raise BillingQuoteError("context_basis must explicitly name full request or uncached input tokens")
        if not isinstance(brackets, list) or not brackets:
            raise BillingQuoteError("context_brackets must be a non-empty array")
        normalized = []
        next_minimum = 0
        for index, bracket in enumerate(brackets):
            if not isinstance(bracket, dict) or set(bracket) - {"min_input_tokens", "max_input_tokens", *RATE_FIELDS}:
                raise BillingQuoteError("unknown or malformed context bracket")
            minimum = count(bracket.get("min_input_tokens"), "min_input_tokens")
            maximum = bracket.get("max_input_tokens")
            if "max_input_tokens" not in bracket:
                raise BillingQuoteError("max_input_tokens is required; null is the final open bracket")
            if maximum is not None:
                maximum = count(maximum, "max_input_tokens")
            if minimum != next_minimum or (maximum is not None and maximum < minimum):
                raise BillingQuoteError("context brackets must be ordered, contiguous and non-overlapping from zero")
            if (maximum is None) != (index == len(brackets) - 1):
                raise BillingQuoteError("only the last context bracket must have an open upper bound")
            normalized.append({"min_input_tokens": minimum, "max_input_tokens": maximum,
                               **_rates(bracket, cache_required=True)})
            next_minimum = maximum + 1 if maximum is not None else minimum
        result["context_basis"] = basis
        result["context_brackets"] = normalized
    tools = value.get("tool_fees", {})
    if not isinstance(tools, dict):
        raise BillingQuoteError("tool_fees must be an object")
    normalized_tools = {}
    for name, fee in tools.items():
        if not isinstance(name, str) or not name or not isinstance(fee, dict):
            raise BillingQuoteError("tool fee needs a named object")
        if set(fee) != {"billing", "unit", "price_cny"} or not isinstance(fee["billing"], str) or fee["billing"] not in {"flat_per_call", "per_unit"}:
            raise BillingQuoteError("tool fee needs billing, unit and price_cny")
        if not isinstance(fee["unit"], str) or not fee["unit"].strip():
            raise BillingQuoteError("tool fee unit must be explicit")
        normalized_tools[name] = {**fee, "price_cny": number(fee["price_cny"], f"tool {name} price_cny")}
    result["tool_fees"] = normalized_tools
    result["quote_sha256"] = quote_digest(result)
    return result


def select(document: dict, provider: str, endpoint: str, model: str, billing_identity: dict | None = None) -> dict:
    if set(document) != {"schema_version", "quotes"} or document.get("schema_version") != "2.0":
        raise BillingQuoteError("unsupported conditional pricing schema")
    if not isinstance(document["quotes"], list) or not document["quotes"]:
        raise BillingQuoteError("conditional pricing needs a non-empty quotes array")
    requested = identity(billing_identity)
    quotes = [_normalize(value) for value in document["quotes"]]
    identities = [(item["provider"], item["endpoint"], item["model"], tuple(item["billing_identity"].values())) for item in quotes]
    if len(identities) != len(set(identities)):
        raise BillingQuoteError("ambiguous duplicate route/billing identity quotes")
    matches = [item for item in quotes if (item["provider"], item["endpoint"], item["model"]) == (provider, endpoint, model)
               and item["billing_identity"] == requested]
    if len(matches) != 1:
        raise BillingQuoteError("an exact route/plan/group/mode quote is required; no price fallback")
    return matches[0]


def tool_limits(quote: dict, value: Any = None) -> dict[str, int]:
    fees = quote.get("tool_fees", {})
    if fees and value is None:
        raise BillingQuoteError("every quoted tool requires an explicit maximum, including zero")
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise BillingQuoteError("declared_tool_limits must map tool names to integer maximum units")
    if set(value) - set(fees):
        raise BillingQuoteError("authorized tool has no exact fee quote")
    if set(fees) - set(value):
        raise BillingQuoteError("every quoted tool requires an explicit maximum, including zero")
    return {key: count(maximum, f"tool {key} maximum units") for key, maximum in value.items()}


def reserve_cost(quote: dict, input_ceiling: int, output_ceiling: int, tools: dict | None = None) -> float:
    count(input_ceiling, "input ceiling")
    count(output_ceiling, "output ceiling")
    limits = tool_limits(quote, tools)
    tiers = quote.get("context_brackets", [quote])
    # Reserving every declared tier is intentionally conservative when tokenization
    # and gateway context accounting cannot be known exactly before transport.
    input_rate = max(tier.get(field, 0) for tier in tiers for field in ("input_per_million", "cache_read_per_million", "cache_write_per_million"))
    output_rate = max(tier["output_per_million"] for tier in tiers)
    fee = sum(value["price_cny"] * (int(limits.get(name, 0) > 0) if value["billing"] == "flat_per_call" else limits.get(name, 0))
              for name, value in quote.get("tool_fees", {}).items())
    return round((input_ceiling * input_rate + output_ceiling * output_rate) / 1_000_000 + fee, 8)


def token_parts(usage: dict, input_tokens: int, output_tokens: int, *, anthropic: bool) -> dict:
    if not isinstance(usage, dict):
        raise BillingQuoteError("usage must be an object; reconcile the outstanding reservation")
    count(input_tokens, "input_tokens")
    count(output_tokens, "output_tokens")
    detail = usage.get("input_tokens_details", usage.get("prompt_tokens_details", {}))
    if not isinstance(detail, dict):
        raise BillingQuoteError("input token details are malformed; reconcile the outstanding reservation")
    cached = count(usage.get("cache_read_input_tokens", detail.get("cached_tokens", 0)), "cache read input tokens")
    created = count(usage.get("cache_creation_input_tokens", 0), "cache creation input tokens")
    if "cache_read_input_tokens" in usage and "cached_tokens" in detail and cached != detail["cached_tokens"]:
        raise BillingQuoteError("conflicting cached-token receipts")
    if not anthropic and (cached > input_tokens or created > input_tokens - cached):
        raise BillingQuoteError("cache counters exceed total input tokens")
    output_detail = usage.get("output_tokens_details", usage.get("completion_tokens_details", {}))
    if not isinstance(output_detail, dict):
        raise BillingQuoteError("output token details are malformed")
    if "reasoning_tokens" in output_detail and count(output_detail["reasoning_tokens"], "reasoning_tokens") > output_tokens:
        raise BillingQuoteError("reasoning tokens exceed total output; no guessed surcharge")
    ordinary = input_tokens if anthropic else input_tokens - cached - created
    full_input = ordinary + cached + created
    return {"ordinary_input_tokens": ordinary, "cache_read_tokens": cached, "cache_write_tokens": created,
            "full_request_input_tokens": full_input, "uncached_input_tokens": ordinary + created,
            "output_tokens_including_reasoning": output_tokens}


def _tool_charge(quote: dict, usage: dict, limits: dict, request_id: str | None) -> tuple[float, list[dict]]:
    fees = quote.get("tool_fees", {})
    raw = usage.get("tool_usage")
    if raw is None:
        if fees or any(limits.values()):
            raise BillingQuoteError("authorized tools need a complete typed usage receipt, including explicit zero use")
        server_usage = usage.get("server_tool_use", {})
        if not isinstance(server_usage, dict):
            raise BillingQuoteError("server tool usage is malformed")
        if any(count(value, "server tool usage") != 0 for value in server_usage.values()):
            raise BillingQuoteError("unquoted server tool use needs billing reconciliation")
        return 0.0, []
    if (not isinstance(raw, dict) or set(raw) != {"schema_version", "complete", "source", "receipt_id", "request_id", "items"}
            or raw["schema_version"] != "1.0" or raw["complete"] is not True
            or not isinstance(raw["source"], str) or raw["source"] not in {"provider_usage", "gateway_billing"}
            or not isinstance(raw["receipt_id"], str) or not raw["receipt_id"].strip()
            or not isinstance(raw["request_id"], str) or not raw["request_id"].strip()
            or not isinstance(raw["items"], list)):
        raise BillingQuoteError("tool usage needs a complete typed provider/gateway receipt")
    if not request_id or raw["request_id"] != request_id:
        raise BillingQuoteError("tool usage receipt must match the response request_id")
    result = []
    names = set()
    total = 0.0
    for item in raw["items"]:
        if not isinstance(item, dict) or set(item) != {"tool", "unit", "units"}:
            raise BillingQuoteError("tool usage item needs exact tool/unit/units fields")
        name = item["tool"]
        if not isinstance(name, str) or name in names or name not in fees:
            raise BillingQuoteError("unknown or duplicated billed tool")
        names.add(name)
        fee = fees[name]
        units = count(item["units"], "tool billed units")
        if item["unit"] != fee["unit"] or units > limits.get(name, 0):
            raise BillingQuoteError("tool receipt exceeds its quoted unit or authorized maximum")
        cost = fee["price_cny"] * (int(units > 0) if fee["billing"] == "flat_per_call" else units)
        total += cost
        result.append({**item, "billing": fee["billing"], "price_cny": fee["price_cny"], "cost_cny": round(cost, 8)})
    return round(total, 8), result


def bill(quote: dict, usage: dict, input_tokens: int, output_tokens: int, *, anthropic: bool,
         tools: dict | None = None, request_id: str | None = None) -> tuple[float, bool, dict]:
    parts = token_parts(usage, input_tokens, output_tokens, anthropic=anthropic)
    rates = quote
    tier = None
    if "context_brackets" in quote:
        context = parts[quote["context_basis"]]
        matches = [value for value in quote["context_brackets"] if value["min_input_tokens"] <= context
                   and (value["max_input_tokens"] is None or context <= value["max_input_tokens"])]
        if len(matches) != 1:
            raise BillingQuoteError("actual input length has no unique context quote")
        rates = matches[0]
        tier = {"basis": quote["context_basis"], "input_tokens": context,
                "min_input_tokens": rates["min_input_tokens"], "max_input_tokens": rates["max_input_tokens"]}
    limits = tool_limits(quote, tools)
    tool_cost, tool_receipts = _tool_charge(quote, usage, limits, request_id)
    unknown = bool((parts["cache_read_tokens"] and "cache_read_per_million" not in rates)
                   or (parts["cache_write_tokens"] and "cache_write_per_million" not in rates))
    token_cost = (parts["ordinary_input_tokens"] * rates["input_per_million"]
                  + parts["cache_read_tokens"] * rates.get("cache_read_per_million", rates["input_per_million"])
                  + parts["cache_write_tokens"] * rates.get("cache_write_per_million", 2 * rates["input_per_million"])
                  + output_tokens * rates["output_per_million"]) / 1_000_000
    details = {**parts, "rates": rates, "quote_sha256": quote.get("quote_sha256"),
               "billing_identity": quote.get("billing_identity", identity()), "context_tier": tier,
               "unknown_cache_price": unknown, "tool_receipts": tool_receipts, "tool_cost_cny": tool_cost,
               "token_cost_cny": round(token_cost, 8)}
    return round(token_cost + tool_cost, 8), unknown, details
