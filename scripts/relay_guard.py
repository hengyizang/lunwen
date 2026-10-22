"""Shared credential-level unknown-charge and single-POST guard across cloud jobs."""
from __future__ import annotations

import base64
from contextvars import ContextVar
import hashlib
import json
import math
import os
import re
import subprocess
from urllib.parse import quote
import uuid

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
        tree = self.api("git/trees/" + quote(branch, safe=""), missing=branch == BRANCH)
        if tree is None:
            return None, None
        item = next((x for x in tree["tree"] if x["path"] == directory), None)
        if item is None:
            return None, None
        subtree = self.api("git/trees/" + item["sha"])
        blob = next((x for x in subtree["tree"] if x["path"] == name), None)
        if blob is None:
            return None, None
        data = self.api("git/blobs/" + blob["sha"])
        raw = base64.b64decode(data["content"])
        actual = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if actual != blob["sha"]:
            raise RelayGuardError("shared relay blob identity mismatch")
        return json.loads(raw), blob["sha"]

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
        actual, new_sha = self.read(BRANCH, "relay-guard", name)
        if actual != value or new_sha != response["content"]["sha"]:
            raise RelayGuardError("shared relay write readback failed")
        return new_sha


def source_holds(provider, store):
    found = []
    for branch, name in SOURCES:
        value, blob = store.read(branch, "trial-state", name)
        if not isinstance(value, dict) or not isinstance(value.get("entries"), list):
            raise RelayGuardError("legacy relay ledger unavailable; unknown charges cannot be ignored")
        for entry in value["entries"]:
            group = entry.get("provider") or str(entry.get("call_id", "")).split("|")[0]
            if name.endswith("argon-base-probe.json"):
                group = "codekey-gemini"
            group = ALIASES.get(group, group)
            if group != provider:
                continue
            settled = entry.get("billing_status") == "settled" or entry.get("status") == "gateway_debit_verified"
            if settled and entry.get("debit_evidence"):
                continue
            identifier = hashlib.sha256((branch + "\0" + name + "\0" + entry["call_id"]).encode()).hexdigest()
            found.append({"id": identifier, "provider": provider, "branch": branch, "name": name,
                          "call_id": entry["call_id"], "source_blob_sha": blob,
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
                        value["legacy_holds"][hold["id"]] = hold
    return store, name, value, expected


def inspect(provider, *, store=None):
    _, _, value, _ = load(provider, store=store)
    return {"provider": provider, "legacy_holds": list(value["legacy_holds"].values()),
            "active": value["active"], "inference_eligible": not value["legacy_holds"] and value["active"] is None,
            "catalog_access_does_not_release_holds": True}


def begin(provider, *, scope, max_cost_cny, store=None):
    if type(max_cost_cny) not in (int, float) or not math.isfinite(max_cost_cny) or max_cost_cny <= 0:
        raise RelayGuardError("shared relay reservation needs a positive bounded amount")
    store, name, value, expected = load(provider, store=store)
    if value["legacy_holds"] or value["active"]:
        # Import historical unknown holds durably, even though no new POST is allowed.
        store.write(name, value, expected)
        raise RelayGuardError("credential has an unresolved historical or concurrent charge; no new paid call")
    ticket = {"id": uuid.uuid4().hex, "provider": provider, "credential_sha256": value["credential_sha256"],
              "scope": scope, "max_cost_cny": max_cost_cny, "run_id": os.environ.get("GITHUB_RUN_ID")}
    value["active"] = ticket
    store.write(name, value, expected)
    _TICKET.set({**ticket, "sent": False})
    return ticket


def authorize_transport(url, headers):
    from urllib.parse import urlsplit
    ticket = _TICKET.get()
    key = headers.get("x-api-key") or headers.get("x-goog-api-key") or headers.get("Authorization", "").removeprefix("Bearer ")
    key_id = hashlib.sha256(("https://" + urlsplit(url).netloc + "\0" + key).encode()).hexdigest()
    if not ticket or ticket["credential_sha256"] != key_id or ticket["sent"] or not ticket.get("meter_bound"):
        raise RelayGuardError("production POST requires its unused durable shared credential reservation")
    ticket["sent"] = True


def bind_meter(ticket, provider_model, before, *, store=None):
    store, name, value, expected = load(ticket["provider"], store=store, import_legacy=False)
    if value["active"] != ticket or not before:
        raise RelayGuardError("cannot bind meter to a different shared reservation")
    value["active_meter"] = {"model": provider_model, "before": before}
    store.write(name, value, expected)
    live = _TICKET.get()
    if not live or live["id"] != ticket["id"]:
        raise RelayGuardError("local ticket changed before meter binding")
    live["meter_bound"] = True


def finish(ticket, settlement=None, *, not_sent=False, store=None):
    store, name, value, expected = load(ticket["provider"], store=store, import_legacy=False)
    if value["active"] != ticket:
        raise RelayGuardError("shared relay active reservation changed")
    live = _TICKET.get()
    if not_sent:
        if not live or live["id"] != ticket["id"] or live["sent"]:
            raise RelayGuardError("cannot cancel a possibly sent production request")
        event = {"ticket": ticket, "status": "not_sent"}
    else:
        if not live or live["id"] != ticket["id"] or not live["sent"]:
            raise RelayGuardError("cannot settle an unsent or different shared request")
        amount = settlement.get("actual_cost_cny") if isinstance(settlement, dict) else None
        if (type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0
                or amount > ticket["max_cost_cny"] or not settlement.get("debit_evidence")):
            raise RelayGuardError("unknown or excessive debit retains the shared reservation")
        validate_debit(value.get("active_meter"), settlement)
        event = {"ticket": ticket, "status": "settled", "settlement": settlement}
    value["events"].append(event)
    value["active"] = None
    value.pop("active_meter", None)
    store.write(name, value, expected)
    _TICKET.set(None)


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
        old, _ = store.read(BRANCH, "relay-guard", old_id + ".json")
        if (not old or not (old["legacy_holds"] or old["active"])
                or proposal.get("attestation") != "Different newly issued credential; prior charges remain held on the original credential."):
            raise RelayGuardError("new credential needs explicit owner attestation and the retained old hold")
    elif proposal.get("kind") == "settled_active":
        from scripts import model_spend, relay_billing
        active, meter = value.get("active"), value.get("active_meter")
        if not active or proposal.get("ticket_id") != active["id"] or not meter:
            raise RelayGuardError("select the exact shared active ticket and retained meter")
        scope = active["scope"]
        if not isinstance(scope, dict) or scope.get("project") != project.name:
            raise RelayGuardError("settle the outstanding call in its original project")
        settled = relay_billing.settle(provider, meter["model"], meter["before"])
        control = model_spend.read(project, required=True)
        if scope.get("reservation_id") in control["reservations"]:
            raise RelayGuardError("reconcile the original project budget before releasing its shared hold")
        matching = [r for r in control["reconciliation_events"] + control.get("settlement_events", []) if r["receipt_id"] == scope.get("reservation_id")
                    and r["actual_cost_cny"] == settled["actual_cost_cny"]]
        if len(matching) != 1 or settled["actual_cost_cny"] > active["max_cost_cny"]:
            raise RelayGuardError("independent debit does not match the original project reconciliation")
        proposal = {**proposal, "independent_settlement": settled}
    elif proposal.get("kind") == "settled_legacy":
        ids = proposal.get("hold_ids")
        if not isinstance(ids, list) or not ids or not set(ids) <= set(value["legacy_holds"]):
            raise RelayGuardError("select exact retained legacy hold IDs")
        unresolved = {r["id"] for r in source_holds(provider, store)}
        if set(ids) & unresolved:
            raise RelayGuardError("legacy ledger still lacks independent debit evidence; no release")
    else:
        raise RelayGuardError("select independently settled legacy holds or a genuinely different new credential")
    return proposal, store, name, value, expected


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
    else:
        for identifier in proposal["hold_ids"]:
            del value["legacy_holds"][identifier]
        value.setdefault("reconciled_legacy_ids", []).extend(proposal["hold_ids"])
    value["events"].append({"status": "owner_reconciliation", **authority})
    store.write(name, value, expected)
