"""Shared credential-level unknown-charge and single-POST guard across cloud jobs."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from contextvars import ContextVar
from functools import partial
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

from scripts.research_artifacts import json_digest

REPOSITORY = "hengyizang/lunwen"
BRANCH = "cloud-state/relay-guard"
SOURCES = (
    ("cloud-state/relay-acceptance-20261019", "ledger.json"),
    ("cloud-state/model-comparison-20261020", "model-comparison-20261020.json"),
    ("cloud-state/model-comparison-20261020", "model-comparison-clarified-20261020.json"),
    ("cloud-state/model-comparison-20261020", "model-comparison-20261020-argon-base-probe.json"),
)
ALIASES = {"cheapai-kiro": "cheapai-kiro-discount", "codekey-codex-pure": "codekey-codex-pro"}
_TICKET = ContextVar("relay_generation_ticket", default=None)
TRIAL_SOURCES = {name.removesuffix(".json"): (branch, name) for branch, name in SOURCES[1:3]}
EVALUATION_TRIAL = "model-evaluation-20261029"
EVALUATION_ORIGINAL_BLOB = "65406a6cd6344c20ba4ec608ca12b0b8602c1a50"
EVALUATION_TICKET = "381830bce3954c0fbc628b548e2b031e"
TRIAL_SOURCES[EVALUATION_TRIAL] = ("cloud-state/" + EVALUATION_TRIAL, "ledger.json")
# Independently inspected originals: neither proposals nor moving branches can
# select a different request, response or authorization for a retired trial.
TRIAL_ORIGINALS = {
    "model-comparison-20261020": "63ee401edc29539bfa065e820b57dc4d025adbd9",
    "model-comparison-clarified-20261020": "07d3cdeb16e4ff06f29dcfe4624d9c8298faf177",
    EVALUATION_TRIAL: EVALUATION_ORIGINAL_BLOB,
}
ROOT = Path(__file__).resolve().parents[1]
_digest = partial(json_digest, allow_nan=False)
REQUEST_FIELDS = ("call_id", "provider", "model", "requested_model", "candidate_id", "effort", "case_id",
                  "case_sha256", "quote_sha256", "meter_before", "gateway_meter_before", "run_id", "reserved_ceiling_cny")


class RelayGuardError(ValueError):
    pass


def fingerprint(provider, environment=None):
    from scripts.ai_providers import PRODUCTION_PROVIDERS
    env = os.environ if environment is None else environment
    spec = PRODUCTION_PROVIDERS[provider]
    key = env.get(spec["key_setting"], "").strip()
    if not key or any(c.isspace() or ord(c) < 32 for c in key):
        raise RelayGuardError("shared relay guard requires the configured credential")
    return hashlib.sha256((spec["root"] + "\0" + key).encode()).hexdigest()


class CloudStore:
    """GitHub contents SHA compare-and-swap; errors never permit generation."""
    def api(self, path, payload=None, method="GET", *, missing=False):
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
            raise RelayGuardError("shared relay state is restricted to the repository cloud runner")
        command = ["gh", "api", "--method", method, "repos/" + REPOSITORY + "/" + path]
        if method == "GET":
            command += ["-H", "Cache-Control: no-cache"]
        if payload is not None:
            command += ["--input", "-"]
        environment = dict(os.environ)
        environment["GH_TOKEN"] = environment.get("GH_TOKEN") or environment.get("COMPARISON_GITHUB_TOKEN", "")
        reply = subprocess.run(command, input=json.dumps(payload) if payload is not None else None, env=environment,
                               text=True, capture_output=True, timeout=60, check=False)
        if reply.returncode:
            if missing and "HTTP 404" in reply.stderr:
                return None
            raise RelayGuardError("shared relay state unavailable or CAS conflict; no generation authorized")
        try:
            return json.loads(reply.stdout)
        except ValueError:
            raise RelayGuardError("shared relay state response invalid") from None

    def read(self, branch, directory, name):
        # Resolve the current file through contents, rather than a cached tree
        # addressed by a mutable branch name. Then validate immutable bytes.
        item = self.api("contents/" + directory + "/" + name + "?ref=" + quote(branch, safe=""),
            missing=branch == BRANCH)
        if item is None:
            return None, None
        blob_sha = item.get("sha") if isinstance(item, dict) else None
        return self.read_blob(blob_sha), blob_sha

    def read_blob(self, blob_sha):
        """Read the exact immutable historical ledger, never a moving ref."""
        if not isinstance(blob_sha, str) or not re.fullmatch(r"[a-f0-9]{40}", blob_sha):
            raise RelayGuardError("shared relay blob identity mismatch")
        data = self.api("git/blobs/" + blob_sha)
        if not isinstance(data, dict) or data.get("sha") != blob_sha or data.get("encoding") != "base64":
            raise RelayGuardError("shared relay blob identity mismatch")
        raw = base64.b64decode(data["content"])
        actual = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if actual != blob_sha:
            raise RelayGuardError("shared relay blob identity mismatch")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RelayGuardError("shared relay immutable ledger is malformed")
        return value

    def write(self, name, value, expected):
        if self.api("git/ref/heads/" + BRANCH, missing=True) is None:
            main = self.api("git/ref/heads/main")
            self.api("git/refs", {"ref": "refs/heads/" + BRANCH, "sha": main["object"]["sha"]}, "POST")
        raw = (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()
        body = {"branch": BRANCH, "message": "Preserve shared relay spending guard",
                "content": base64.b64encode(raw).decode()}
        if expected:
            body["sha"] = expected
        response = self.api("contents/relay-guard/" + name, body, "PUT")
        new_sha = response["content"]["sha"]
        if self.read_blob(new_sha) != value:
            raise RelayGuardError("shared relay write readback failed")
        return new_sha


def _entry_provider(entry, name):
    group = entry.get("provider") or str(entry.get("call_id", "")).split("|")[0]
    if name.endswith("argon-base-probe.json") and not entry.get("provider"):
        group = "codekey-gemini"
    return ALIASES.get(group, group)


def _number(value, field, *, integer=False):
    if (type(value) not in ((int,) if integer else (int, float))
            or not math.isfinite(value) or value < 0):
        raise RelayGuardError("invalid independent debit " + field)
    return value


def _before(entry, provider):
    before = entry.get("meter_before", entry.get("gateway_meter_before"))
    if not isinstance(before, dict):
        raise RelayGuardError("settled source lacks its original before meter")
    if before.get("provider", provider) != provider:
        raise RelayGuardError("source before meter belongs to another provider")
    before = {**before, "provider": provider}
    if before.get("kind") == "cheapai_quota_history":
        rows = before.get("rows")
        if not isinstance(rows, list):
            raise RelayGuardError("settled source before meter lacks debit rows")
        before["rows"] = [{("model_name" if k == "model" else k): v for k, v in row.items()}
                          for row in rows if isinstance(row, dict)]
        if len(before["rows"]) != len(rows):
            raise RelayGuardError("settled source before meter has malformed debit rows")
    return before


def _row(evidence):
    row = evidence.get("row", evidence)
    model = row.get("model_name", row.get("model"))
    if not isinstance(model, str) or not model:
        raise RelayGuardError("independent debit row lacks an exact model")
    result = {"model_name": model, "quota": _number(row.get("quota"), "quota", integer=True),
              "created_at": _number(row.get("created_at"), "created_at", integer=True)}
    for field in ("prompt_tokens", "completion_tokens"):
        if row.get(field) is not None:
            result[field] = _number(row[field], field, integer=True)
    return result


def _settled_receipt(entry, provider, name, ledger):
    """Validate retained native formats; a status flag alone proves nothing."""
    from scripts import ai_providers, relay_billing
    old = entry.get("status") == "gateway_debit_verified"
    if not old and entry.get("billing_status") != "settled":
        raise RelayGuardError("source call still lacks independent debit evidence")
    amount = _number(entry.get("gateway_debit_cny") if old else entry.get("actual_cost_cny"), "amount")
    ceiling = _number(entry.get("reserved_ceiling_cny"), "reservation")
    if amount > ceiling:
        raise RelayGuardError("independent debit exceeds the original reservation")
    model = entry.get("model", entry.get("requested_model"))
    if old:
        parts = str(entry.get("call_id", "")).split("|")
        model = parts[1] if len(parts) >= 3 else None
    if not isinstance(model, str) or not model:
        raise RelayGuardError("settled source lacks an exact model")
    evidence = entry.get("debit_evidence")
    if not isinstance(evidence, dict):
        raise RelayGuardError("source call lacks independent debit evidence")
    root = ai_providers.PRODUCTION_PROVIDERS[provider]["root"]
    before = None
    normalized = dict(evidence)
    if root == "https://codekey.ai":
        before = _before(entry, provider)
        for key in ("before", "after"):
            meter = evidence.get(key)
            if not isinstance(meter, dict):
                raise RelayGuardError("independent debit lacks gateway counters")
            normalized[key] = {"requests": _number(meter.get("requests"), "requests", integer=True),
                               "cost_cny": _number(meter.get("cost_cny"), "cost")}
    elif root == "https://cheapai.info":
        row = _row(evidence)
        if (evidence.get("source") != root + "/api/log/token"
                or evidence.get("quota_per_unit", 500000) != 500000
                or row["model_name"] != model or abs(row["quota"] / 500000 - amount) > 1e-8):
            raise RelayGuardError("independent source debit does not match its model/amount")
        if old and evidence.get("all_key_debits_match_attempt_count") is True:
            # The original paused acceptance trial matched the entire dedicated
            # key history rather than a per-call delta. Later incremental calls
            # do not belong to that original batch; bind its complete prefix to
            # the first incremental call's retained before snapshot instead.
            related = [r for r in ledger["entries"] if _entry_provider(r, name) == provider]
            prefix = []
            for index, item in enumerate(related):
                if item.get("debit_evidence", {}).get("all_key_debits_match_attempt_count") is True:
                    if index != len(prefix):
                        raise RelayGuardError("original whole-key debit match is not a contiguous prefix")
                    prefix.append(item)
            identities = []
            for item in prefix:
                proof = item.get("debit_evidence", {})
                parts = str(item.get("call_id", "")).split("|")
                if (item.get("status") != "gateway_debit_verified" or len(parts) < 3
                        or proof.get("source") != root + "/api/log/token"
                        or proof.get("all_key_debits_match_attempt_count") is not True
                        or proof.get("no_generation_retry") is not True or proof.get("quota_per_unit") != 500000):
                    raise RelayGuardError("original whole-key debit match is incomplete")
                other = _row(proof)
                cost = _number(item.get("gateway_debit_cny"), "amount")
                if (other["model_name"] != parts[1] or abs(other["quota"] / 500000 - cost) > 1e-8
                        or cost > _number(item.get("reserved_ceiling_cny"), "reservation")):
                    raise RelayGuardError("original whole-key debit binding changed")
                identities.append(relay_billing._fingerprint(other))
            if len(set(identities)) != len(identities):
                raise RelayGuardError("original whole-key debit match is ambiguous")
            if len(prefix) < len(related):
                first_incremental = _before(related[len(prefix)], provider)
                if (first_incremental.get("kind") != "cheapai_quota_history"
                        or first_incremental.get("quota_per_unit") != 500000
                        or sorted(relay_billing._fingerprint(_row(r)) for r in first_incremental["rows"])
                        != sorted(identities)):
                    raise RelayGuardError("original whole-key prefix differs from the first incremental before meter")
            return {"actual_cost_cny": amount, "debit_evidence": evidence}
        before = _before(entry, provider)
        if old:
            normalized.update(row=row, before_snapshot_sha256=relay_billing._fingerprint({"rows": before["rows"]}))
            if before.get("quota_per_unit") != 500000 or row in before["rows"]:
                raise RelayGuardError("source debit already appeared in its before meter")
    settlement = {"actual_cost_cny": amount, "debit_evidence": normalized}
    validate_debit({"model": model, "before": before}, settlement)
    return settlement


def _source_entry(store, branch, name, call_id, provider, *, trial=False):
    if (branch, name) not in (TRIAL_SOURCES.values() if trial else SOURCES):
        raise RelayGuardError("source ledger is not an allowlisted original trial")
    value, blob = store.read(branch, "trial-state", name)
    if not isinstance(value, dict) or not isinstance(value.get("entries"), list) or not blob:
        raise RelayGuardError("original source ledger unavailable")
    rows = [r for r in value["entries"] if isinstance(r, dict) and r.get("call_id") == call_id]
    if len(rows) != 1 or _entry_provider(rows[0], name) != provider:
        raise RelayGuardError("original source call missing, duplicated or assigned to another provider")
    return value, rows[0], blob


def source_holds(provider, store):
    found = []
    for branch, name in SOURCES:
        value, blob = store.read(branch, "trial-state", name)
        if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
            raise RelayGuardError("legacy relay ledger unavailable; unknown charges cannot be ignored")
        call_ids = [r.get("call_id") for r in value["entries"] if isinstance(r, dict)]
        duplicates = {identifier for identifier in call_ids if call_ids.count(identifier) > 1}
        for entry in value["entries"]:
            group = _entry_provider(entry, name)
            if group != provider:
                continue
            try:
                if entry.get("call_id") in duplicates:
                    raise RelayGuardError("duplicate original source calls cannot establish a unique debit")
                _settled_receipt(entry, provider, name, value)
            except (RelayGuardError, KeyError, TypeError, ValueError):
                pass
            else:
                continue
            identifier = hashlib.sha256((branch + "\0" + name + "\0" + entry["call_id"]).encode()).hexdigest()
            found.append({"id": identifier, "provider": provider, "branch": branch, "name": name,
                          "call_id": entry["call_id"], "source_blob_sha": blob,
                          "request_binding": {key: entry[key] for key in REQUEST_FIELDS if key in entry},
                          "reserved_ceiling_cny": entry["reserved_ceiling_cny"]})
    return found


def load(provider, *, store=None, import_legacy=True):
    store = store or CloudStore()
    key_id = fingerprint(provider)
    name = key_id + ".json"
    value, expected = store.read(BRANCH, "relay-guard", name)
    if value is None:
        value = {"schema_version": "1.0", "credential_sha256": key_id, "legacy_holds": {}, "active": None, "events": []}
    if value.get("credential_sha256") != key_id or value.get("schema_version") != "1.0":
        raise RelayGuardError("shared relay credential binding invalid")
    if import_legacy:
        from scripts.ai_providers import PRODUCTION_PROVIDERS
        for group in PRODUCTION_PROVIDERS:
            try:
                same_key = fingerprint(group) == key_id
            except RelayGuardError:
                continue
            if same_key and group not in value.get("rotated_provider_credentials", {}):
                for hold in source_holds(group, store):
                    if hold["id"] not in value.get("reconciled_legacy_ids", []):
                        value["legacy_holds"].setdefault(hold["id"], hold)
    return store, name, value, expected


def inspect(provider, *, store=None):
    _, _, value, _ = load(provider, store=store)
    return {"provider": provider, "legacy_holds": list(value["legacy_holds"].values()),
            "active": value["active"], "inference_eligible": not value["legacy_holds"] and value["active"] is None,
            "catalog_access_does_not_release_holds": True}


@contextmanager
def project_transport(project, receipt_id, provider, model, *, max_cost_cny, paper_id, run_id):
    """One operation-local POST on an already authorized cumulative reservation."""
    from scripts import ai_providers, model_spend
    from scripts.cloud_checkpoint import sync_billing
    if _TICKET.get() is not None:
        raise RelayGuardError("a model transport lease is already active in this operation")
    binding = {"provider": provider, "model": model, "endpoint": ai_providers.production_endpoint(provider, model),
               "credential_sha256": fingerprint(provider)}
    claimed = model_spend.claim_transport(project, receipt_id, max_cost_cny=max_cost_cny,
                                         paper_id=paper_id, run_id=run_id, binding=binding)
    sync_billing(project)
    current = model_spend.read(project, required=True)["reservations"].get(receipt_id)
    if _digest(current) != _digest(claimed) or fingerprint(provider) != binding["credential_sha256"]:
        raise RelayGuardError("synced model transport differs from its exact project reservation")
    ticket = {**binding, "id": claimed["transport"]["lease_id"], "sent": False, "meter_bound": True,
              "native_google": ai_providers.PRODUCTION_PROVIDERS[provider]["protocol"] == "gemini_generate_content"}
    token = _TICKET.set(ticket)
    try:
        yield ticket
    finally:
        _TICKET.reset(token)


def authorize_transport(url, headers, *, payload=None):
    from urllib.parse import urlsplit
    ticket = _TICKET.get()
    key = headers.get("x-api-key") or headers.get("x-goog-api-key") or headers.get("Authorization", "").removeprefix("Bearer ")
    key_id = hashlib.sha256(("https://" + urlsplit(url).netloc + "\0" + key).encode()).hexdigest()
    if not ticket or ticket["credential_sha256"] != key_id or ticket["sent"] or not ticket.get("meter_bound"):
        raise RelayGuardError("production POST requires its unused durable shared credential reservation")
    if ticket.get("endpoint") and (url != ticket["endpoint"] or not isinstance(payload, dict)
            or ("model" in payload if ticket["native_google"] else payload.get("model") != ticket["model"])):
        raise RelayGuardError("production POST differs from its exact selected endpoint/model")
    ticket["sent"] = True


def validate_debit(meter, settlement):
    from scripts import relay_billing
    if not isinstance(meter, dict):
        raise RelayGuardError("shared reservation has no independently retained before meter")
    before = meter["before"]
    evidence = settlement["debit_evidence"]
    if not isinstance(evidence, dict) or evidence.get("exactly_one_new_gateway_request") is not True:
        raise RelayGuardError("independent debit must identify exactly one gateway request")
    if before.get("kind") == "codekey_total_actual_cost":
        if (evidence.get("source") != "https://codekey.ai/v1/usage"
                or evidence.get("before") != {"requests": before["requests"], "cost_cny": before["cost_cny"]}
                or evidence.get("after", {}).get("requests") != before["requests"] + 1
                or abs(evidence["after"].get("cost_cny", -1) - before["cost_cny"] - settlement["actual_cost_cny"]) > 1e-8):
            raise RelayGuardError("independent debit belongs to a different before meter")
    elif before.get("kind") == "cheapai_quota_history":
        if (evidence.get("source") != "https://cheapai.info/api/log/token"
                or evidence.get("before_snapshot_sha256") != relay_billing._fingerprint({"rows": before["rows"]})
                or evidence.get("row", {}).get("model_name") != meter["model"]
                or abs(evidence["row"].get("quota", -1) / 500000 - settlement["actual_cost_cny"]) > 1e-8):
            raise RelayGuardError("independent debit belongs to a different before meter/model")
    else:
        raise RelayGuardError("unrecognized independent debit meter")


def _immutable_trial_source(store, trial, ledger, entry):
    """Only an originally reserved target may gain explicit settlement fields."""
    original = store.read_blob(TRIAL_ORIGINALS[trial])
    originals = [row for row in original.get("entries", [])
                 if isinstance(row, dict) and row.get("call_id") == entry["call_id"]]
    if original.get("trial_id") != trial or len(originals) != 1:
        raise RelayGuardError("immutable original trial/call identity mismatch")
    billing = {"billing_status", "actual_cost_cny", "debit_evidence", "reconciled_at"} if originals[0].get("billing_status") == "reserved" else set()
    def preserved(value):
        rows = value.get("entries")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise RelayGuardError("immutable trial source entries are malformed")
        return {**value, "entries": [{key: item for key, item in row.items() if key not in billing}
                if row.get("call_id") == entry["call_id"] else row for row in rows]}
    if _digest(preserved(ledger)) != _digest(preserved(original)):
        raise RelayGuardError("trial source differs from the immutable original request/response/scope")
    return original


def _evaluation_source(active, original, entry):
    """Bind Oct29's shared ticket to its frozen project, plan and request."""
    frozen = original["scope"]
    plan = json.loads((ROOT / "config/model-evaluation-20261029.json").read_text(encoding="utf-8"))
    prices = (ROOT / "config/model-evaluation-pricing-20261029.json").read_bytes()
    if (_digest(plan) != frozen["plan_sha256"] or hashlib.sha256(prices).hexdigest() != frozen["prices_sha256"]
            or _digest(plan["routes"]) != _digest(frozen["routes"])):
        raise RelayGuardError("evaluation plan, prices or frozen routes changed")
    def select(rows, key, value):
        found = [row for row in rows if isinstance(row, dict) and row.get(key) == value]
        if len(found) != 1:
            raise RelayGuardError("evaluation request needs its exact unique route/case binding")
        return found[0]
    request = select(frozen["queue"], "call_id", entry["call_id"])
    route = select(plan["routes"], "id", request["route_id"])
    case = select(plan["cases"], "id", request["case_id"])
    expected = {key: request[key] for key in ("call_id", "route_id", "case_id", "case_sha256", "reserved_ceiling_cny")}
    expected.update(provider=route["provider"], requested_model=route["model"], requested_effort=route["effort"],
                    task_class=case["task_class"], partition=case["partition"], code_sha=frozen["code_sha"])
    scope = {"trial": EVALUATION_TRIAL, "call_id": entry["call_id"], "authorization": frozen["authorization"],
             "project_reservation_id": entry["project_reservation_id"],
             "legacy_budget_reservation_id": original["legacy_budget_reservations"]["gemini"]}
    if (active.get("id") != EVALUATION_TICKET or case["partition"] not in {"calibration", "holdout"}
            or _digest(case) != request["case_sha256"]
            or request["case_id"] not in route.get("case_ids", [row["id"] for row in plan["cases"]])
            or request["max_output_tokens"] != route.get("max_output_tokens", plan["max_output_tokens"])
            or request["timeout"] != route.get("timeout", 300)
            or _digest({key: entry[key] for key in expected}) != _digest(expected)
            or _digest(active["scope"]) != _digest(scope)):
        raise RelayGuardError("evaluation route/case/partition or exact shared ticket binding changed")
    return frozen["project"]


def _project_settlement(project, reservation, settled):
    from scripts import model_spend
    if not isinstance(reservation, str) or not reservation:
        raise RelayGuardError("shared ticket lacks its original project reservation")
    control = model_spend.read(project, required=True)
    if reservation in control["reservations"]:
        raise RelayGuardError("reconcile the original project budget before releasing its shared hold")
    matching = [row for row in control["reconciliation_events"] + control.get("settlement_events", [])
                if row.get("receipt_id") == reservation and row.get("actual_cost_cny") == settled["actual_cost_cny"]]
    if len(matching) != 1:
        raise RelayGuardError("independent debit does not match the original project reconciliation")
    return matching[0]


def _trial_settlement(store, active, meter, project=None):
    """Reconcile a frozen historical call without its retired generator."""
    from scripts import relay_billing
    scope = active.get("scope")
    if not isinstance(scope, dict) or scope.get("trial") not in TRIAL_SOURCES or not scope.get("call_id"):
        raise RelayGuardError("shared ticket does not name an allowlisted original comparison")
    branch, name = TRIAL_SOURCES[scope["trial"]]
    ledger, entry, blob = _source_entry(store, branch, name, scope["call_id"], active["provider"], trial=True)
    original_parent_blob = None
    evaluation = scope["trial"] == EVALUATION_TRIAL
    try:
        original = _immutable_trial_source(store, scope["trial"], ledger, entry)
        if evaluation:
            owner_project = _evaluation_source(active, original, entry)
            if project is None or project.name != owner_project:
                raise RelayGuardError("settle the evaluation in its original project")
        else:
            if _digest(scope) != _digest({"trial": scope["trial"], "call_id": entry["call_id"]}):
                raise RelayGuardError("comparison exact shared ticket scope changed")
            if scope["trial"] == "model-comparison-clarified-20261020":
                contract = original["scope"]
                original_parent_blob = contract["parent_blob_sha"]
                if original_parent_blob != TRIAL_ORIGINALS["model-comparison-20261020"]:
                    raise RelayGuardError("clarified comparison original parent blob mismatch")
                parent = store.read_blob(original_parent_blob)
                if (parent.get("trial_id") != "model-comparison-20261020"
                        or _digest(parent) != contract["parent_ledger_sha256"]
                        or parent["plan_sha256"] != contract["parent_plan_sha256"]):
                    raise RelayGuardError("clarified comparison original parent contract changed")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        raise RelayGuardError("historical trial source binding is invalid: " + str(exc)) from exc
    if _digest({"model": entry.get("model", entry.get("requested_model")), "before": entry["meter_before"],
                "run_id": entry["run_id"], "ceiling": entry["reserved_ceiling_cny"]}) != _digest({
                "model": meter["model"], "before": meter["before"], "run_id": active["run_id"], "ceiling": active["max_cost_cny"]}):
        raise RelayGuardError("comparison call differs from the exact shared ticket and before meter")
    recorded = _settled_receipt(entry, active["provider"], name, ledger)
    event = _project_settlement(project, entry["project_reservation_id"], recorded) if evaluation else None
    current = relay_billing.settle(active["provider"], meter["model"], meter["before"])
    validate_debit(meter, current)
    if (current.get("actual_cost_cny") != recorded["actual_cost_cny"]
            or current["actual_cost_cny"] > active["max_cost_cny"]):
        raise RelayGuardError("independent debit differs from the original accounted trial cost")
    result = {"branch": branch, "name": name, "call_id": scope["call_id"], "source_blob_sha": blob,
            "original_trial_blob_sha": TRIAL_ORIGINALS[scope["trial"]],
            "original_parent_blob_sha": original_parent_blob,
            "hold_id": hashlib.sha256((branch + "\0" + name + "\0" + scope["call_id"]).encode()).hexdigest(),
            "entry_sha256": relay_billing._fingerprint(entry), "recorded_settlement": recorded,
            "independent_settlement": current}
    if evaluation:
        result["project_reconciliation_sha256"] = relay_billing._fingerprint(event)
    return result


def prepare_reconciliation(project, source, actor, *, store=None):
    from scripts.primary_recovery import path_in, read
    proposal = read(path_in(project, source))
    provider = proposal.get("provider")
    store, name, value, expected = load(provider, store=store)
    if not actor or proposal.get("credential_sha256") != value["credential_sha256"]:
        raise RelayGuardError("owner reconciliation must name the exact credential fingerprint")
    if proposal.get("kind") == "new_credential":
        old_id = proposal.get("previous_credential_sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", old_id) or old_id == value["credential_sha256"]:
            raise RelayGuardError("new credential must be distinct from the recorded previous credential")
        old, old_blob = store.read(BRANCH, "relay-guard", old_id + ".json")
        if (not old or not (old["legacy_holds"] or old["active"])
                or proposal.get("attestation") != "Different newly issued credential; prior charges remain held on the original credential."):
            raise RelayGuardError("new credential needs explicit owner attestation and the retained old hold")
        proposal = {**proposal, "previous_shared_blob_sha": old_blob,
                    "previous_shared_state_sha256": hashlib.sha256(json.dumps(old, sort_keys=True, allow_nan=False).encode()).hexdigest()}
    elif proposal.get("kind") == "settled_active":
        from scripts import relay_billing
        active, meter = value.get("active"), value.get("active_meter")
        if not active or proposal.get("ticket_id") != active["id"] or not meter:
            raise RelayGuardError("select the exact shared active ticket and retained meter")
        scope = active["scope"]
        if not isinstance(scope, dict) or scope.get("project") != project.name:
            raise RelayGuardError("settle the outstanding call in its original project")
        settled = relay_billing.settle(provider, meter["model"], meter["before"])
        _project_settlement(project, scope.get("reservation_id"), settled)
        if settled["actual_cost_cny"] > active["max_cost_cny"]:
            raise RelayGuardError("independent debit does not match the original project reconciliation")
        proposal = {**proposal, "independent_settlement": settled}
    elif proposal.get("kind") == "settled_trial":
        active, meter = value.get("active"), value.get("active_meter")
        if not active or proposal.get("ticket_id") != active["id"] or not meter:
            raise RelayGuardError("select the exact shared comparison ticket and retained meter")
        proposal = {**proposal, "resolved_trial": _trial_settlement(store, active, meter, project)}
    elif proposal.get("kind") == "settled_legacy":
        ids = proposal.get("hold_ids")
        if not isinstance(ids, list) or not ids or not set(ids) <= set(value["legacy_holds"]):
            raise RelayGuardError("select exact retained legacy hold IDs")
        if len(set(ids)) != len(ids):
            raise RelayGuardError("select unique retained legacy hold IDs")
        resolved = []
        from scripts import relay_billing
        for identifier in ids:
            hold = value["legacy_holds"][identifier]
            ledger, entry, blob = _source_entry(store, hold["branch"], hold["name"], hold["call_id"], hold["provider"])
            if any(entry.get(key) != original for key, original in hold.get("request_binding", {}).items()):
                raise RelayGuardError("original held request/model/before-meter binding changed")
            try:
                settlement = _settled_receipt(entry, hold["provider"], hold["name"], ledger)
            except (RelayGuardError, KeyError, TypeError, ValueError):
                raise RelayGuardError("legacy ledger still lacks independent debit evidence; no release") from None
            if (entry.get("reserved_ceiling_cny") != hold["reserved_ceiling_cny"]
                    or settlement["actual_cost_cny"] > hold["reserved_ceiling_cny"]):
                raise RelayGuardError("legacy debit differs from the retained original reservation")
            resolved.append({"hold_id": identifier, "branch": hold["branch"], "name": hold["name"],
                             "call_id": hold["call_id"], "provider": hold["provider"], "source_blob_sha": blob,
                             "entry_sha256": relay_billing._fingerprint(entry), "settlement": settlement})
        proposal = {**proposal, "resolved_legacy": resolved}
    else:
        raise RelayGuardError("select independently settled legacy holds or a genuinely different new credential")
    return proposal, store, name, value, expected


def reconciliation_snapshot(project, source, actor, *, store=None):
    """Bind every remote source and resolved debit into the human review digest."""
    proposal, _, _, value, blob = prepare_reconciliation(project, source, actor, store=store)
    return {"blob_sha": blob, "state": value, "resolved_proposal": proposal}


def reconcile(project, source, actor, review_sha256, run_id, note):
    proposal, store, name, value, expected = prepare_reconciliation(project, source, actor)
    authority = {"actor": actor, "review_sha256": review_sha256, "run_id": run_id, "note": note, "proposal": proposal}
    if proposal["kind"] == "new_credential":
        if value["active"]:
            raise RelayGuardError("new credential also has an active charge")
        value.setdefault("rotated_provider_credentials", {})[proposal["provider"]] = authority
        value["legacy_holds"] = {k: v for k, v in value["legacy_holds"].items() if v["provider"] != proposal["provider"]}
    elif proposal["kind"] == "settled_active":
        value["events"].append({"status": "owner_settled_active", "ticket": value["active"],
                                "settlement": proposal["independent_settlement"]})
        value["active"] = None
        value.pop("active_meter", None)
    elif proposal["kind"] == "settled_trial":
        value["events"].append({"status": "owner_settled_trial", "ticket": value["active"],
                                "settlement": proposal["resolved_trial"]})
        value["active"] = None
        value.pop("active_meter", None)
        identifier = proposal["resolved_trial"]["hold_id"]
        if identifier in value["legacy_holds"]:
            del value["legacy_holds"][identifier]
            value.setdefault("reconciled_legacy_ids", []).append(identifier)
    else:
        for identifier in proposal["hold_ids"]:
            del value["legacy_holds"][identifier]
        value.setdefault("reconciled_legacy_ids", []).extend(proposal["hold_ids"])
    value["events"].append({"status": "owner_reconciliation", **authority})
    store.write(name, value, expected)

