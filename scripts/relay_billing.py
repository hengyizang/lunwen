"""Read-only relay debit reconciliation; never generate, retry or authorize work.

The owner's relay settlement rule is numeric USD wallet units = CNY units.
That is not a market foreign-exchange conversion. Unknown or concurrent debits
retain the caller's full reservation; token estimates never release it here.
"""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

from scripts import ai_providers


class BillingReconciliationError(RuntimeError):
    """Metadata unavailable or debit cannot be uniquely attributed; keep hold."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> None:
        raise BillingReconciliationError("billing metadata redirect refused; retain reservation")


_CHEAP_DENOMINATION: dict[str, Any] | None = None
_CURRENCY_RULE = "owner-approved numeric USD wallet unit equals CNY1; not market FX"


def _get_json(url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    parts = urlsplit(url)
    allowed = {("cheapai.info", "/api/status"), ("cheapai.info", "/api/log/token"),
               ("codekey.ai", "/v1/usage")}
    if (parts.scheme != "https" or (parts.netloc, parts.path) not in allowed
            or parts.query or parts.fragment or parts.username or parts.password):
        raise BillingReconciliationError("billing metadata requires an exact configured HTTPS endpoint")
    request = urllib.request.Request(url, headers={**(headers or {}),
        "User-Agent": "lunwen-production-research/1.0", "Accept": "application/json"}, method="GET")
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=15) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise BillingReconciliationError("billing metadata exceeded size limit; retain reservation")
            value = json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BillingReconciliationError(f"billing metadata HTTP {exc.code}; retain reservation") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError):
        raise BillingReconciliationError("billing metadata unavailable; retain reservation") from None
    if not isinstance(value, dict) or value.get("success") is False or value.get("error"):
        raise BillingReconciliationError("billing metadata response invalid; retain reservation")
    return value


def _count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BillingReconciliationError(f"invalid {label} billing counter; retain reservation")
    return value


def _amount(value: Any) -> float:
    if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
        raise BillingReconciliationError("invalid actual-cost billing amount; retain reservation")
    return float(value)


def _spec(provider: str) -> dict[str, Any]:
    spec = ai_providers.PRODUCTION_PROVIDERS.get(provider)
    if spec is None:
        raise BillingReconciliationError("provider has no production debit meter")
    if spec.get("root") not in {"https://cheapai.info", "https://codekey.ai"}:
        raise BillingReconciliationError("production debit meter root is not allowlisted")
    return spec


def _fingerprint(row: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _debit_fingerprint(row: dict[str, Any]) -> str:
    # CheapAI's authenticated log assigns 1..N display positions afresh on
    # every response. A new first row shifts every historical ID. Preserve
    # that number for audit, but identify debits by their sanitized billing
    # fields and multiplicity, never by the display position.
    return _fingerprint({key: value for key, value in row.items() if key != "id"})


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > 1000:
        raise BillingReconciliationError("billing debit history is malformed; retain reservation")
    rows = []
    seen_ids = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise BillingReconciliationError("billing debit row is malformed; retain reservation")
        if raw.get("type") != 2:
            continue
        model = raw.get("model_name")
        if not isinstance(model, str) or not model or len(model) > 160 or any(ch.isspace() or ord(ch) < 32 for ch in model):
            raise BillingReconciliationError("billing debit model ID is malformed; retain reservation")
        row = {"model_name": model, "quota": _count(raw.get("quota"), "quota"),
               "created_at": _count(raw.get("created_at"), "created_at")}
        for field in ("prompt_tokens", "completion_tokens"):
            if field in raw:
                row[field] = _count(raw[field], field)
        # Some relay installations omit IDs or render them as non-integer
        # labels. They are not trusted identifiers; use the row fingerprint.
        if type(raw.get("id")) is int:
            row["id"] = _count(raw["id"], "debit ID")
            if row["id"] in seen_ids:
                raise BillingReconciliationError("duplicate billing debit ID; retain reservation")
            seen_ids.add(row["id"])
        rows.append(row)
    return rows


def read_meter(provider: str, environment=None) -> dict[str, Any]:
    """Read a sanitized pre/post meter once; never retry metadata failures."""
    global _CHEAP_DENOMINATION
    spec = _spec(provider)
    env = os.environ if environment is None else environment
    key = env.get(spec["key_setting"], "").strip()
    if not key or any(ch.isspace() or ord(ch) < 32 for ch in key):
        raise BillingReconciliationError(f"{spec['key_setting']} is not configured")
    headers = {"Authorization": f"Bearer {key}"}
    if spec["root"] == "https://codekey.ai":
        value = _get_json("https://codekey.ai/v1/usage", headers)
        usage = value.get("usage")
        total = usage.get("total") if isinstance(usage, dict) else None
        if not isinstance(total, dict):
            raise BillingReconciliationError("missing actual-cost billing counter; retain reservation")
        return {"provider": provider, "kind": "codekey_total_actual_cost",
                "requests": _count(total.get("requests"), "requests"),
                "cost_cny": _amount(total.get("actual_cost")), "currency_rule": _CURRENCY_RULE}
    if spec["root"] != "https://cheapai.info":
        raise BillingReconciliationError("production debit meter root is not allowlisted")
    if _CHEAP_DENOMINATION is None:
        data = _get_json("https://cheapai.info/api/status").get("data")
        if (not isinstance(data, dict) or type(data.get("quota_per_unit")) is not int
                or data["quota_per_unit"] != 500000 or data.get("quota_display_type") != "USD"):
            raise BillingReconciliationError("relay quota denomination changed; retain reservation")
        _CHEAP_DENOMINATION = {"quota_per_unit": 500000, "quota_display_type": "USD"}
    value = _get_json("https://cheapai.info/api/log/token", headers)
    return {"provider": provider, "kind": "cheapai_quota_history", "quota_per_unit": 500000,
            "rows": _rows(value.get("data")), "currency_rule": _CURRENCY_RULE}


def _new_cheapai_rows(before: list[dict], after: list[dict]) -> list[dict]:
    # Display IDs are not stable database identifiers. Core-field multisets
    # still reject altered/deleted historical debits and concurrent new rows.
    prior = Counter(_debit_fingerprint(row) for row in before)
    current = Counter(_debit_fingerprint(row) for row in after)
    fresh_counts, missing_counts = current - prior, prior - current
    fresh = []
    for row in after:
        fingerprint = _debit_fingerprint(row)
        if fresh_counts[fingerprint]:
            fresh.append(row)
            fresh_counts[fingerprint] -= 1
    if len(fresh) == 1 and before and fresh[0]["created_at"] < max(row["created_at"] for row in before):
        raise BillingReconciliationError("new debit predates prior history; retain reservation")
    missing = sum(missing_counts.values())
    if missing:
        # The relay returns a recent window, normally 100 rows. Permit a single
        # oldest-row rollover; never require a sum of the account's full history.
        if len(before) < 100 or len(after) != len(before) or missing != 1 or len(fresh) != 1:
            raise BillingReconciliationError("debit history continuity is ambiguous; retain reservation")
        omitted = [row for row in before if missing_counts[_debit_fingerprint(row)]]
        if not omitted or omitted[0]["created_at"] > min(row["created_at"] for row in after):
            raise BillingReconciliationError("debit history lost a recent row; retain reservation")
    return fresh


def settle(provider: str, model: str, before: dict[str, Any]) -> dict[str, Any]:
    """Match exactly one post-call debit, with at most three free lag polls.

    Call only after a complete, identity-checked generation receipt. A failure
    never supplies permission to replay the generation or release a hold.
    """
    spec = _spec(provider)
    if model not in spec["models"] or not isinstance(before, dict) or before.get("provider") != provider:
        raise BillingReconciliationError("debit reconciliation route/model binding differs")
    expected = "codekey_total_actual_cost" if spec["root"] == "https://codekey.ai" else "cheapai_quota_history"
    if before.get("kind") != expected:
        raise BillingReconciliationError("debit reconciliation meter kind differs")
    for attempt in range(3):
        after = read_meter(provider)
        if after.get("provider") != provider or after.get("kind") != expected:
            raise BillingReconciliationError("post-call meter route differs; retain reservation")
        if expected == "codekey_total_actual_cost":
            prior_requests = _count(before.get("requests"), "prior requests")
            next_requests = _count(after.get("requests"), "current requests")
            prior_cost, next_cost = _amount(before.get("cost_cny")), _amount(after.get("cost_cny"))
            difference = next_requests - prior_requests
            if difference < 0 or difference > 1 or next_cost < prior_cost:
                raise BillingReconciliationError("concurrent or reset gateway counters; retain reservation")
            if difference == 1:
                amount = float(Decimal(str(next_cost)) - Decimal(str(prior_cost)))
                return {"actual_cost_cny": amount, "debit_evidence": {
                    "source": "https://codekey.ai/v1/usage",
                    "before": {"requests": prior_requests, "cost_cny": prior_cost},
                    "after": {"requests": next_requests, "cost_cny": next_cost},
                    "exactly_one_new_gateway_request": True, "currency_rule": _CURRENCY_RULE}}
        else:
            if before.get("quota_per_unit") != 500000 or after.get("quota_per_unit") != 500000:
                raise BillingReconciliationError("relay quota denomination differs; retain reservation")
            if not isinstance(before.get("rows"), list) or not isinstance(after.get("rows"), list):
                raise BillingReconciliationError("missing debit history; retain reservation")
            if any(not isinstance(row, dict) for row in before["rows"] + after["rows"]):
                raise BillingReconciliationError("malformed debit history; retain reservation")
            # Revalidate persisted snapshots without introducing account metadata.
            prior_rows = _rows([dict(row, type=2) for row in before["rows"]])
            next_rows = _rows([dict(row, type=2) for row in after["rows"]])
            fresh = _new_cheapai_rows(prior_rows, next_rows)
            if len(fresh) > 1:
                raise BillingReconciliationError("multiple new gateway debits; retain reservation")
            if len(fresh) == 1:
                row = fresh[0]
                if row["model_name"] != model:
                    raise BillingReconciliationError("new gateway debit model differs; retain reservation")
                return {"actual_cost_cny": row["quota"] / 500000, "debit_evidence": {
                    "source": "https://cheapai.info/api/log/token", "unit_source": "https://cheapai.info/api/status",
                    "quota_per_unit": 500000, "row": row,
                    "row_identity_rule": "billing_fields_excluding_display_id",
                    "before_snapshot_sha256": _fingerprint({"rows": prior_rows}),
                    "after_snapshot_sha256": _fingerprint({"rows": next_rows}),
                    "exactly_one_new_gateway_request": True, "currency_rule": _CURRENCY_RULE}}
        if attempt < 2:
            time.sleep(2)
    raise BillingReconciliationError("gateway debit has not uniquely appeared; retain reservation")
