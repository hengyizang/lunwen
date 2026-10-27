"""Owner-authorized writing comparison; metadata never generates or releases holds."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from scripts import ai_providers, gateway_trial, model_comparison_clarified, model_runtime, model_spend
from scripts import model_comparison, output_provenance, production_readiness, relay_billing, relay_guard, review_packets

ROOT = Path(__file__).resolve().parents[1]
TRIAL = "writing-comparison-20261027"
BRANCH = "codex/" + TRIAL
STATE = "cloud-state/" + TRIAL
AUTHORIZATION = TRIAL + "-owner-paid-with-legacy-holds"
PROVIDERS = ("codekey-gemini", "cheapai-gpt-pro")
LIMIT = 30.0
OLD_HOLD = 9.5836104
ROUTES = (
    {"id": "argon-native-high", "provider": "codekey-gemini", "model": "gemini-4-argon-high"},
    {"id": "sol-high", "provider": "cheapai-gpt-pro", "model": "gpt-6.1-sol"},
    {"id": "astra-high", "provider": "cheapai-gpt-pro", "model": "gpt-6-astra"},
)
REVIEWED_BASE_FAILURE = "7cedd3713aa45202c23c95051c31dfb60b658a5e"
REVIEWED_HIGH_FAILURE = "2f59ecce09431cad59fbce15755f3411bc6b56e4"


class State(gateway_trial.CloudState):
    """Exact file compare-and-swap and immutable readback, as in existing trials."""

    def __init__(self, token, branch=STATE, directory="trial-state"):
        super().__init__(token, branch)
        self.expected = {}
        self.directory = directory

    def read(self, name):
        tree = self.api("git/trees/" + urllib.parse.quote(self.branch, safe=""))
        for segment in self.directory.split("/"):
            item = next((row for row in tree["tree"] if row["path"] == segment), None)
            if item is None:
                return None, None
            tree = self.api("git/trees/" + item["sha"])
        item = next((row for row in tree["tree"] if row["path"] == name), None)
        if item is None:
            return None, None
        return model_comparison_clarified.blob_json(self.api("git/blobs/" + item["sha"]), item["sha"]), item["sha"]

    def load(self, name):
        value, sha = self.read(name)
        self.expected[name] = sha
        return value

    def save(self, name, value):
        if name not in self.expected:
            raise ValueError("read state before writing")
        raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        body = {"message": TRIAL + ": preserve " + name, "branch": self.branch,
                "content": base64.b64encode(raw).decode()}
        if self.expected[name]:
            body["sha"] = self.expected[name]
        reply = self.api("contents/" + self.directory + "/" + name, body, "PUT")
        sha = reply["content"]["sha"]
        if model_comparison_clarified.blob_json(self.api("git/blobs/" + sha), sha) != value:
            raise ValueError("comparison state readback mismatch")
        self.expected[name] = sha


def metadata():
    """Authenticated GETs only; sanitized counters never certify exact old debits."""
    report = {"trial_id": TRIAL, "at": datetime.now(timezone.utc).isoformat(),
              "run_id": os.environ.get("GITHUB_RUN_ID"), "code_sha": os.environ.get("GITHUB_SHA"),
              "mode": "metadata", "generation_calls": 0, "production_routing_changed": False,
              "scientific_equivalence_verified": False, "providers": {}}
    for provider in PROVIDERS:
        row = report["providers"][provider] = {}
        try:
            row["catalog"] = sorted(production_readiness.catalog(provider, dict(os.environ)))
        except ValueError as exc:
            row["catalog_error"] = str(exc)
        try:
            row["meter"] = relay_billing.read_meter(provider)
        except relay_billing.BillingReconciliationError as exc:
            row["meter_error"] = str(exc)
        try:
            row["shared_guard"] = relay_guard.inspect(provider)
        except (ValueError, OSError, KeyError):
            row["guard_error"] = "shared credential state unavailable; no generation permitted"
    # Do not attempt to attribute a shared aggregate delta to either of two old
    # Argon calls. Both original source ledgers remain immutable and held.
    return report


def digest(value):
    return gateway_trial.digest(value)


def prompt(plan, case):
    source = case["source"]
    return (case["instruction"] + "\n\nSOURCE LABEL: [" + source["id"] + "]\n"
            + source["title"] + "; " + source["authors"] + "; DOI: " + source["doi"]
            + "; published: " + source["published_on"] + "\nBEGIN SOURCE DATA\n"
            + source["text"] + "\nEND SOURCE DATA")


def validate_plan(plan):
    if plan.get("trial_id") != TRIAL or len(plan.get("cases", [])) != 6:
        raise ValueError("exact six-case writing trial required")
    sources = [row["source"]["text_sha256"] for row in plan["cases"]]
    if (len(set(sources)) != 6 or len({row["id"] for row in plan["cases"]}) != 6
            or len({row["source"]["doi"] for row in plan["cases"]}) != 6
            or len({row["source"]["id"] for row in plan["cases"]}) != 6):
        raise ValueError("six independent source cases required")
    partitions = [row["partition"] for row in plan["cases"]]
    if partitions.count("holdout") != 3 or partitions.count("calibration") != 3:
        raise ValueError("three calibration and three frozen holdouts required")
    for row in plan["cases"]:
        source = row["source"]
        if (source["license"] != "CC-BY-4.0"
                or hashlib.sha256(source["text"].encode()).hexdigest() != source["text_sha256"]):
            raise ValueError("source rights or excerpt hash changed")
    return plan


def freeze_scope(plan):
    quotes = {route["id"]: model_runtime.pricing(route["provider"], route["model"]) for route in ROUTES}
    ceilings = {route["id"] + "|" + case["id"]: model_runtime.reservation_bound(
        route["provider"], prompt(plan, case), plan["common_instruction"], 8192,
        quotes[route["id"]], {}, controlled=True)
        for case in plan["cases"] for route in ROUTES}
    # Preserve the billed base-ID failure inside the same18-call allowance.
    # The separately advertised exact high-ID contract is not an accepted alias.
    del ceilings["astra-high|intro-seaborn"]
    quotes["argon-high"] = model_runtime.pricing("codekey-gemini", "gemini-4-argon")
    first = plan["cases"][0]
    ceilings["argon-high|intro-seaborn"] = model_runtime.reservation_bound(
        "codekey-gemini", prompt(plan, first), plan["common_instruction"], 8192,
        quotes["argon-high"], {}, controlled=True)
    if len(ceilings) != 18 or sum(ceilings.values()) > LIMIT:
        raise ValueError("fixed request scope exceeds eighteen calls or CNY30")
    return {"authorization": AUTHORIZATION, "plan_sha256": digest(plan), "max_calls": 18,
            "new_call_limit_cny": LIMIT, "retained_legacy_hold_cny": OLD_HOLD,
            "project": "my-phd", "project_ceiling_cny": 500,
            "routes": ROUTES, "quotes": quotes, "call_ceilings_cny": ceilings,
            "rubric": rubric(), "minimum_human_raters": 2,
            "production_routing_changed": False, "automatic_promotion": False}


def reviewed_transport_amendment(ledger, scope, current_sha):
    if (current_sha != REVIEWED_BASE_FAILURE or ledger.get("status") != "stopped"
            or len(ledger.get("entries", [])) != 1
            or ledger["entries"][0].get("call_id") != "argon-high|intro-seaborn"
            or ledger["entries"][0].get("billing_status") != "settled"
            or ledger["entries"][0].get("generation_status") != "failed"
            or "model ID missing or mismatched" not in ledger["entries"][0].get("diagnostic", "")
            or ledger["scope"].get("plan_sha256") != scope["plan_sha256"]):
        raise ValueError("frozen trial scope changed; never reset allowance")
    ledger["original_scope"] = ledger["scope"]
    ledger["scope"] = scope
    ledger["transport_amendment"] = {"reviewed_ledger_blob": current_sha,
        "reason": "Base identity failed; test the distinct advertised high-ID. Preserve the failure and cost; omit one never-sent Astra calibration task to retain18/CNY30.",
        "base_alias_accepted": False, "old_request_retried": False,
        "review_run_id": os.environ.get("GITHUB_RUN_ID")}
    ledger.update(status="running")


def continue_independent_routes(ledger, current_sha):
    """Continue only never-sent GPT tasks after two settled identity failures."""
    if (current_sha != REVIEWED_HIGH_FAILURE or ledger.get("status") != "stopped"
            or [row["call_id"] for row in ledger["entries"]] != [
                "argon-high|intro-seaborn", "argon-native-high|intro-seaborn"]
            or any(row.get("billing_status") != "settled" or row.get("generation_status") != "failed"
                   or "model ID missing or mismatched" not in row.get("diagnostic", "")
                   for row in ledger["entries"])):
        raise ValueError("exact independently billed identity failures required; no new permission or replay")
    ledger["independent_continuation"] = {"reviewed_ledger_blob": current_sha,
        "previous_stop_reason": ledger.get("stop_reason"), "provider_quarantined": "codekey-gemini",
        "reason": "Both Argon contracts failed identity; continue only already-authorized never-sent GPT tasks, with no Argon retries or new judge calls."}
    ledger.update(status="running", quarantined_providers=["codekey-gemini"])
    ledger.pop("stop_reason", None)


class Budget:
    def __init__(self, token):
        self.state = State(token, "cloud-state/my-phd", "projects/my-phd/state")
        self.root = ROOT / ".runtime/writing-budget"

    def refresh(self):
        value = self.state.load("model-spend-control.json")
        if value is None or value.get("authorized_ceiling_cny") != 500:
            raise ValueError("existing CNY500 project authorization required")
        model_spend.write(self.root, value)
        return model_spend.read(self.root, required=True)

    def persist(self):
        self.state.save("model-spend-control.json", model_spend.read(self.root, required=True))

    def reserve(self, amount, *, kind="new_call", call_id=None):
        control = self.refresh()
        if kind == "retained_legacy":
            found = [(identifier, row) for identifier, row in control["reservations"].items()
                     if row.get("writing_trial") == TRIAL and row.get("kind") == kind]
            if found:
                if len(found) != 1 or found[0][1]["max_cost_cny"] != OLD_HOLD:
                    raise ValueError("retained old trial reservation differs; no allowance reset")
                return found[0][0]
        identifier = model_spend.reserve(self.root, max_cost_cny=amount, paper_id=None,
            paper_limit_cny=500, run_id=os.environ["GITHUB_RUN_ID"])
        control = model_spend.read(self.root, required=True)
        control["reservations"][identifier].update(writing_trial=TRIAL, kind=kind, call_id=call_id)
        model_spend.write(self.root, control)
        self.persist()
        return identifier

    def settle(self, identifier, amount):
        self.refresh()
        try:
            model_spend.settle(self.root, identifier, actual_cost_cny=amount)
        finally:
            # settle records an overage before raising; preserve that actual
            # debit remotely as well, even though all further work stops.
            self.persist()


def rubric():
    dimensions = {
        "evidence_fidelity": "Every factual statement follows the supplied source and its conditions.",
        "argument": "A clear question, concrete contribution and evidence-linked explanation.",
        "naturalness": "Natural academic English without filler, repetitive hedging or forced transitions.",
        "precision": "Concise wording preserves distinctions and warranted uncertainty.",
        "revision_effort": "Usability with little substantive correction (5 means least correction).",
    }
    return {"dimensions": [{"id": key, "description": value, "value_type": "integer", "min": 1, "max": 5}
                           for key, value in dimensions.items()],
            "critical_errors": [
                {"id": "invented", "criterion": "Invented fact, experiment, quantitative result or citation."},
                {"id": "scope", "criterion": "Changed causal meaning, applicability, attribution or necessary condition."},
                {"id": "numeric", "criterion": "Incorrect number, unit, interval or direction."}]}


def export_review(plan, ledger):
    project = ROOT / ".runtime/writing-review"
    packet = {"id": TRIAL, "kind": "calibration", "rubric": ledger["scope"]["rubric"], "cases": [],
              "analysis": {"minimum_raters": 2, "qualification_thresholds": {
                  key["id"]: 4 for key in rubric()["dimensions"]},
                  "case_partitions": {}, "cost_run_ids": [], "additional_cost_receipts": []}}
    for case in plan["cases"]:
        entries = [entry for entry in ledger["entries"] if entry["case_id"] == case["id"]]
        if not entries:
            continue
        source_path = project / "sources" / (case["id"] + ".txt")
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(prompt(plan, case), encoding="utf-8")
        row = {"id": case["id"], "sources": [{"path": source_path.relative_to(project).as_posix(),
            "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(), "locator": case["source"]["locator"]}],
            "candidates": []}
        for entry in entries:
            status = "success" if entry["generation_status"] == "completed" else "failed"
            target = project / "candidates" / (entry["call_id"].replace("|", "-") + ".txt")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(entry.get("text", "No completed text; inspect the failed attempt receipt."), encoding="utf-8")
            if status == "success":
                output_provenance.record_model_writes(project, [target],
                    family=ai_providers.provider_family(entry["provider"]), provider=entry["provider"],
                    model=entry["requested_model"], role="internal-writing-evaluation", run_id=entry["run_id"])
            candidate = {"id": entry["candidate_id"], "author_id": entry["requested_model"],
                "model": entry["requested_model"], "channel": entry["provider"],
                "authorized_for_internal_review": True, "authorization_note": AUTHORIZATION,
                "status": status, "run_ids": [entry["run_id"]],
                "artifact": {"path": target.relative_to(project).as_posix(),
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "locator": "entire candidate"}}
            if status == "failed":
                failure = target.with_suffix(".json")
                failure.write_text(json.dumps({key: value for key, value in entry.items() if key != "text"}), encoding="utf-8")
                candidate.update(failure_reason="No complete validated response; do not infer ability from missing text.",
                    failure_receipt={"path": failure.relative_to(project).as_posix(),
                        "sha256": hashlib.sha256(failure.read_bytes()).hexdigest(), "locator": "entire failed receipt"})
            row["candidates"].append(candidate)
        packet["cases"].append(row)
        packet["analysis"]["case_partitions"][case["id"]] = case["partition"]
    if packet["cases"]:
        target = project / review_packets.INPUT
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"schema_version": "1.0", "packets": [packet]}, indent=2), encoding="utf-8")
        result = review_packets.refresh(project)
        if result["errors"]:
            raise ValueError("blind packet preparation failed: " + str(result["errors"]))


def execute(plan, state):
    if (os.environ.get("GITHUB_ACTOR") != "hengyizang"
            or os.environ.get("WRITING_COMPARISON_AUTHORIZATION") != AUTHORIZATION):
        raise ValueError("exact owner paid-writing and retained-holds authorization required")
    scope = json.loads(json.dumps(freeze_scope(validate_plan(plan))))
    ledger = state.load("ledger.json")
    budget = Budget(os.environ["GH_TOKEN"])
    if ledger is None:
        # The old unknown amount is occupied in the existing central budget,
        # never relabeled as an independently confirmed actual debit.
        old_receipt = budget.reserve(OLD_HOLD, kind="retained_legacy")
        ledger = {"trial_id": TRIAL, "scope": scope, "status": "running", "entries": [],
                  "legacy_budget_reservation_id": old_receipt,
                  "authorization_note": "Owner explicitly authorized this finite exception in chat on 2026-10-27; preserve both old Argon holds in full, new18/CNY30 within totalCNY500.",
                  "scientific_equivalence_verified": False, "production_routing_changed": False}
        state.save("ledger.json", ledger)
    if ledger["scope"] != json.loads(json.dumps(scope)):
        reviewed_transport_amendment(ledger, scope, state.expected.get("ledger.json"))
        state.save("ledger.json", ledger)
    if ledger.get("status") == "stopped" and state.expected.get("ledger.json") == REVIEWED_HIGH_FAILURE:
        continue_independent_routes(ledger, state.expected["ledger.json"])
        state.save("ledger.json", ledger)
    if ledger["status"] != "running":
        return ledger
    if any(entry["billing_status"] != "settled" for entry in ledger["entries"]):
        raise ValueError("unsettled new trial request stops all further paid work")
    inventory = {provider: production_readiness.catalog(provider, dict(os.environ)) for provider in PROVIDERS}
    if any(route["model"] not in inventory[route["provider"]] for route in ROUTES):
        raise ValueError("exact trial model missing from authenticated catalog")
    for index, case in enumerate(plan["cases"]):
        order = ROUTES[index % 3:] + ROUTES[:index % 3]
        for route in order:
            call_id = route["id"] + "|" + case["id"]
            if route["provider"] in ledger.get("quarantined_providers", []):
                continue
            if call_id not in scope["call_ceilings_cny"]:
                continue
            if any(entry["call_id"] == call_id for entry in ledger["entries"]):
                continue
            ceiling = scope["call_ceilings_cny"][call_id]
            committed = sum(entry.get("actual_cost_cny", entry["reserved_ceiling_cny"]) for entry in ledger["entries"])
            if len(ledger["entries"]) >= 18 or committed + ceiling > LIMIT:
                raise ValueError("bounded trial allowance prevents new call")
            before = model_comparison.read_meter(route["provider"])
            receipt = budget.reserve(ceiling, call_id=call_id)
            entry = {"call_id": call_id, "candidate_id": route["id"], "case_id": case["id"],
                "case_sha256": digest(case), "provider": route["provider"], "requested_model": route["model"],
                "requested_effort": "high", "reserved_ceiling_cny": ceiling, "billing_status": "reserved",
                "generation_status": "not_sent", "project_reservation_id": receipt, "meter_before": before,
                "run_id": os.environ["GITHUB_RUN_ID"], "code_sha": os.environ["GITHUB_SHA"]}
            ledger["entries"].append(entry)
            state.save("ledger.json", ledger)
            ticket = relay_guard.begin(route["provider"], scope={"trial": TRIAL, "call_id": call_id,
                "authorization": AUTHORIZATION, "project_reservation_id": receipt,
                "legacy_budget_reservation_id": ledger["legacy_budget_reservation_id"]},
                max_cost_cny=ceiling, writing_trial_exception=route["provider"] == "codekey-gemini")
            relay_guard.bind_meter(ticket, route["model"], before)
            started = time.monotonic()
            try:
                result = ai_providers.call_production(route["provider"], prompt(plan, case),
                    model=route["model"], system=plan["common_instruction"], max_output_tokens=8192,
                    timeout=300, reasoning_effort="high")
                credentials = [os.environ.get(spec["key_setting"], "") for spec in ai_providers.PRODUCTION_PROVIDERS.values()]
                entry.update(generation_status="completed", text=gateway_trial.safe_text(result.text, credentials),
                    reported_model=result.reported_model, usage=gateway_trial.receipt_numbers(result.usage),
                    request_id=gateway_trial.safe_text(result.request_id or "", credentials),
                    response_sha256=hashlib.sha256(result.text.encode()).hexdigest(),
                    completion_status=result.completion_status)
            except ai_providers.ProviderError as exc:
                entry.update(generation_status="failed", diagnostic=gateway_trial.safe_text(str(exc)))
                if hasattr(exc, "reported_model"):
                    entry["reported_model_unverified"] = gateway_trial.safe_text(exc.reported_model or "missing")
            entry["duration_seconds"] = round(time.monotonic() - started, 4)
            state.save("ledger.json", ledger)
            try:
                settlement = relay_billing.settle(route["provider"], route["model"], before)
                entry.update(billing_status="settled", **settlement)
                state.save("ledger.json", ledger)
                budget.settle(receipt, settlement["actual_cost_cny"])
                relay_guard.finish(ticket, settlement)
            except (relay_billing.BillingReconciliationError, model_spend.SpendControlError, relay_guard.RelayGuardError) as exc:
                ledger.update(status="stopped", stop_reason=str(exc))
                state.save("ledger.json", ledger)
                return ledger
            print(json.dumps({"call_id": call_id, "generation": entry["generation_status"],
                              "actual_cost_cny": entry["actual_cost_cny"]}), flush=True)
            if entry["generation_status"] != "completed":
                ledger.update(status="stopped", stop_reason="failed generation retained; no paid retry authorized")
                state.save("ledger.json", ledger)
                return ledger
    ledger.update(status="closed", completed_at=datetime.now(timezone.utc).isoformat())
    ledger["unattempted_unknown"] = sorted(set(scope["call_ceilings_cny"]) - {row["call_id"] for row in ledger["entries"]})
    state.save("ledger.json", ledger)
    return ledger


def main():
    env = os.environ
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != gateway_trial.REPO
            or env.get("GITHUB_REF") != "refs/heads/" + BRANCH
            or env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}):
        raise ValueError("exact authorized repository cloud branch required")
    state = State(env["GH_TOKEN"])
    mode = env.get("WRITING_COMPARISON_MODE", "metadata")
    if mode == "execute":
        plan = json.loads((ROOT / "config/writing-comparison-20261027.json").read_text(encoding="utf-8"))
        try:
            report = execute(plan, state)
        finally:
            saved = state.load("ledger.json")
            if saved is not None:
                snapshot = ROOT / ".runtime/writing-comparison/execute.json"
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot.write_text(json.dumps(saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                if {row["case_id"] for row in saved["entries"] if row["generation_status"] == "completed"} == {row["id"] for row in plan["cases"]}:
                    export_review(plan, saved)
    elif mode == "metadata":
        report = metadata()
        name = "metadata-" + env["GITHUB_RUN_ID"] + ".json"
        if state.load(name) is not None:
            raise ValueError("existing metadata run cannot be replaced")
        state.save(name, report)
        saved = state.load("ledger.json")
        if saved is not None and saved.get("status") == "closed":
            plan = json.loads((ROOT / "config/writing-comparison-20261027.json").read_text(encoding="utf-8"))
            export_review(plan, saved)
    else:
        raise ValueError("unknown trial mode")
    output = ROOT / ".runtime/writing-comparison" / (mode + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": mode, "state_branch": STATE,
                      "new_attempts": len(report.get("entries", []))}))


if __name__ == "__main__":
    main()
