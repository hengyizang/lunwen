"""Persist owner-approved model spending ceilings across cloud research jobs.

Only aggregate CNY estimates and pending reservations are committed to the
project state branch. Prompts, responses and the detailed usage ledger stay out
of Git. A reservation left by a failed or interrupted call remains charged
against the approved ceiling until a human reconciles the provider bill.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any


STEP_CNY = 300
FILE = Path("state/model-spend-control.json")


class SpendControlError(RuntimeError):
    pass


def initial() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "currency": "CNY",
        "tranche_cny": STEP_CNY,
        "authorized_ceiling_cny": 0,
        "spent_cny": 0.0,
        "paper_spent_cny": {},
        "reservations": {},
        "authorization_events": [],
        "reconciliation_events": [],
    }


def _amount(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise SpendControlError(f"{label} must be a non-negative finite number")
    return float(value)


def read(project_root: Path, *, required: bool = False) -> dict[str, Any] | None:
    path = project_root / FILE
    if not path.is_file():
        if required:
            raise SpendControlError("model spending authorization state is missing; no paid call is allowed")
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpendControlError("model spending authorization state is unreadable") from exc
    if not isinstance(state, dict) or state.get("schema_version") != "1.0" or state.get("currency") != "CNY" or state.get("tranche_cny") != STEP_CNY:
        raise SpendControlError("model spending authorization state has an invalid schema")
    ceiling = state.get("authorized_ceiling_cny")
    if type(ceiling) is not int or ceiling < 0:
        raise SpendControlError("authorized ceiling must be a non-negative integer")
    spent = _amount(state.get("spent_cny"), "spent_cny")
    papers = state.get("paper_spent_cny")
    reservations = state.get("reservations")
    events = state.get("authorization_events")
    reconciliations = state.get("reconciliation_events")
    if not isinstance(papers, dict) or not isinstance(reservations, dict) or not isinstance(events, list) or not isinstance(reconciliations, list):
        raise SpendControlError("model spending authorization state is malformed")
    if any(not isinstance(key, str) or not key.startswith("P") for key in papers):
        raise SpendControlError("paper spending keys are invalid")
    for value in papers.values():
        _amount(value, "paper_spent_cny")
    for reservation in reservations.values():
        if not isinstance(reservation, dict) or not isinstance(reservation.get("paper_id"), (str, type(None))):
            raise SpendControlError("model spending reservation is malformed")
        _amount(reservation.get("max_cost_cny"), "reservation.max_cost_cny")
    # A provider can report usage above a pre-call reservation. Retain that
    # overage as a negative remaining balance, so the next call is blocked.
    # Old grant records remain valid and retain their exact +300 semantics.
    # A separately authorized operating amendment may choose an exact ceiling;
    # every later grant still adds precisely +300 to that amended ceiling.
    recorded_ceiling = 0
    for item in events:
        if (not isinstance(item, dict) or not isinstance(item.get("run_id"), str)
                or not item["run_id"].strip() or type(item.get("ceiling_cny")) is not int):
            raise SpendControlError("authorization events do not match the current ceiling")
        kind = item.get("kind")
        if kind is None:
            valid = item["ceiling_cny"] == recorded_ceiling + STEP_CNY
        elif kind == "ceiling_amendment":
            valid = (
                type(item.get("previous_ceiling_cny")) is int
                and item["previous_ceiling_cny"] == recorded_ceiling
                and item["ceiling_cny"] > 0
                and item["ceiling_cny"] != recorded_ceiling
                and isinstance(item.get("actor"), str) and bool(item["actor"].strip())
                and isinstance(item.get("authorization_note"), str)
                and bool(item["authorization_note"].strip())
            )
        else:
            valid = False
        if not valid:
            raise SpendControlError("authorization events do not match the current ceiling")
        recorded_ceiling = item["ceiling_cny"]
    if recorded_ceiling != ceiling:
        raise SpendControlError("authorization events do not match the current ceiling")
    return state


def write(project_root: Path, state: dict[str, Any]) -> None:
    path = project_root / FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def grant(project_root: Path, *, new_ceiling_cny: int, actor: str, run_id: str) -> dict[str, Any]:
    state = read(project_root, required=True)
    assert state is not None
    if type(new_ceiling_cny) is not int or new_ceiling_cny != state["authorized_ceiling_cny"] + STEP_CNY:
        raise SpendControlError("a new owner approval can add exactly CNY 300 to the existing ceiling")
    if not actor.strip() or not run_id.strip():
        raise SpendControlError("a named owner and a GitHub run are required")
    state["authorized_ceiling_cny"] = new_ceiling_cny
    state["authorization_events"].append({
        "ceiling_cny": new_ceiling_cny,
        "actor": actor.strip(),
        "run_id": run_id,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    write(project_root, state)
    return state


def amend_ceiling(project_root: Path, *, new_ceiling_cny: int, actor: str,
                  run_id: str, authorization_note: str) -> dict[str, Any]:
    """Record an explicit owner amendment without resetting spending history.

    This primitive does not authenticate an owner or grant a scientific gate.
    Its caller must enforce the hash-bound owner review, serialization and
    idempotent request contract before invoking it. Unlike ``grant``, it records
    an exact cumulative ceiling rather than approving another standard tranche.
    Outstanding reservations remain held and count toward the minimum ceiling.
    """
    state = read(project_root, required=True)
    assert state is not None
    if type(new_ceiling_cny) is not int or new_ceiling_cny <= 0:
        raise SpendControlError("an amended ceiling must be a positive integer CNY amount")
    if any(not isinstance(value, str) or not value.strip()
           for value in (actor, run_id, authorization_note)):
        raise SpendControlError("named owner, GitHub run and explicit authorization note are required")
    previous = state["authorized_ceiling_cny"]
    if new_ceiling_cny == previous:
        raise SpendControlError("an operating amendment must change the existing ceiling")
    # Compare the recorded amounts exactly; rounding a legacy charge down here
    # could authorize a ceiling below commitments by a fractional currency unit.
    committed = Decimal(str(state["spent_cny"])) + sum(
        (Decimal(str(item["max_cost_cny"])) for item in state["reservations"].values()),
        Decimal(0),
    )
    if new_ceiling_cny < committed:
        raise SpendControlError("an amended ceiling cannot be below spent plus reserved CNY")
    state["authorized_ceiling_cny"] = new_ceiling_cny
    state["authorization_events"].append({
        "kind": "ceiling_amendment",
        "previous_ceiling_cny": previous,
        "ceiling_cny": new_ceiling_cny,
        "actor": actor.strip(),
        "run_id": run_id.strip(),
        "authorization_note": authorization_note.strip(),
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    write(project_root, state)
    return state


def reserved(state: dict[str, Any], paper_id: str | None = None) -> float:
    return round(sum(float(item["max_cost_cny"]) for item in state["reservations"].values()
                     if paper_id is None or item["paper_id"] == paper_id), 8)


def reserve(project_root: Path, *, max_cost_cny: float, paper_id: str | None, paper_limit_cny: float, run_id: str) -> str:
    state = read(project_root, required=True)
    assert state is not None
    maximum = _amount(max_cost_cny, "max_cost_cny")
    if maximum <= 0:
        raise SpendControlError("model call needs a positive cost reservation")
    if state["spent_cny"] + reserved(state) + maximum > state["authorized_ceiling_cny"] + 1e-8:
        raise SpendControlError("the next model call would cross the approved CNY tranche")
    if paper_id and state["paper_spent_cny"].get(paper_id, 0.0) + reserved(state, paper_id) + maximum > paper_limit_cny + 1e-8:
        raise SpendControlError(f"the next model call would cross {paper_id}'s hard budget")
    receipt_id = uuid.uuid4().hex
    state["reservations"][receipt_id] = {
        "max_cost_cny": round(maximum, 8),
        "paper_id": paper_id,
        "run_id": run_id,
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    write(project_root, state)
    return receipt_id


def cancel_unsent(project_root: Path, receipt_id: str, *, reason: str) -> None:
    """Only the pre-transport control path may withdraw a never-sent reservation."""
    state = read(project_root, required=True)
    reservation = state["reservations"].pop(receipt_id)
    state.setdefault("unsent_events", []).append({"receipt_id": receipt_id, "reservation": reservation,
                                                "reason": reason, "generation_sent": False})
    write(project_root, state)


def settle(project_root: Path, receipt_id: str, *, actual_cost_cny: float) -> None:
    state = read(project_root, required=True)
    assert state is not None
    reservation = state["reservations"].get(receipt_id)
    if reservation is None:
        raise SpendControlError("model call reservation is missing")
    cost = _amount(actual_cost_cny, "actual_cost_cny")
    over_estimate = cost > reservation["max_cost_cny"] + 1e-8
    state["spent_cny"] = round(state["spent_cny"] + cost, 8)
    paper_id = reservation["paper_id"]
    if paper_id:
        state["paper_spent_cny"][paper_id] = round(state["paper_spent_cny"].get(paper_id, 0.0) + cost, 8)
    del state["reservations"][receipt_id]
    state.setdefault("settlement_events", []).append({"receipt_id": receipt_id, "actual_cost_cny": cost})
    write(project_root, state)
    if over_estimate or state["spent_cny"] + reserved(state) > state["authorized_ceiling_cny"] + 1e-8:
        raise SpendControlError("provider usage exceeded the reserved estimate or approved ceiling; actual estimated spend was recorded and further calls are blocked")


def reconcile(project_root: Path, receipt_id: str, *, actual_cost_cny: float,
              actor: str, run_id: str, evidence_note: str) -> dict[str, Any]:
    state = read(project_root, required=True)
    assert state is not None
    if receipt_id not in state["reservations"]:
        raise SpendControlError("there is no outstanding reservation with that receipt ID")
    if not actor.strip() or not run_id.strip() or not evidence_note.strip():
        raise SpendControlError("named owner, GitHub run and bill reconciliation note are required")
    cost = _amount(actual_cost_cny, "actual_cost_cny")
    reservation = state["reservations"].pop(receipt_id)
    state["spent_cny"] = round(state["spent_cny"] + cost, 8)
    paper_id = reservation["paper_id"]
    if paper_id:
        state["paper_spent_cny"][paper_id] = round(state["paper_spent_cny"].get(paper_id, 0.0) + cost, 8)
    state["reconciliation_events"].append({
        "receipt_id": receipt_id,
        "actual_cost_cny": cost,
        "actor": actor.strip(),
        "run_id": run_id,
        "evidence_note": evidence_note.strip(),
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    })
    write(project_root, state)
    return state
