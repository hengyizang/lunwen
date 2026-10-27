"""Owner-authorized writing comparison; metadata never generates or releases holds."""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from scripts import gateway_trial, model_comparison_clarified, production_readiness, relay_billing, relay_guard

ROOT = Path(__file__).resolve().parents[1]
TRIAL = "writing-comparison-20261027"
BRANCH = "codex/" + TRIAL
STATE = "cloud-state/" + TRIAL
AUTHORIZATION = TRIAL + "-owner-paid"
PROVIDERS = ("codekey-gemini", "cheapai-gpt-pro")


class State(gateway_trial.CloudState):
    """Exact file compare-and-swap and immutable readback, as in existing trials."""

    def __init__(self, token, branch=STATE):
        super().__init__(token, branch)
        self.expected = {}

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
        reply = self.api("contents/trial-state/" + name, body, "PUT")
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


def main():
    env = os.environ
    if (env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REPOSITORY") != gateway_trial.REPO
            or env.get("GITHUB_REF") != "refs/heads/" + BRANCH
            or env.get("GITHUB_EVENT_NAME") not in {"push", "workflow_dispatch"}):
        raise ValueError("exact authorized repository cloud branch required")
    report = metadata()
    state = State(env["GH_TOKEN"])
    name = "metadata-" + env["GITHUB_RUN_ID"] + ".json"
    if state.load(name) is not None:
        raise ValueError("existing metadata run cannot be replaced")
    state.save(name, report)
    output = ROOT / ".runtime/writing-comparison-metadata.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"generation_calls": 0, "state_branch": STATE, "report": name}))


if __name__ == "__main__":
    main()
