#!/usr/bin/env python3
"""Validate that G0 contains explicit, usable human constraints."""
from __future__ import annotations

from typing import Any


WEIGHT_FIELDS = (
    "novelty_and_doctoral_depth",
    "feasibility_without_lab",
    "funded_position_supply",
    "competition",
    "job_market_and_salary",
    "background_fit",
)


def _nonempty_text(value: Any, field: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} must be an explicit non-empty string")


def _string_list(value: Any, field: str, errors: list[str], minimum: int = 0) -> None:
    if not isinstance(value, list) or len(value) < minimum:
        errors.append(f"{field} must contain at least {minimum} item(s)")
    elif any(not isinstance(item, str) or not item.strip() for item in value):
        errors.append(f"{field} must contain only non-empty strings")


def _number(
    value: Any,
    field: str,
    errors: list[str],
    *,
    minimum: float,
    maximum: float | None = None,
) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{field} must be a number")
        return
    if value < minimum or (maximum is not None and value > maximum):
        upper = f" and <= {maximum:g}" if maximum is not None else ""
        errors.append(f"{field} must be >= {minimum:g}{upper}")


def validate_constraints(value: dict[str, Any]) -> list[str]:
    """Return G0 errors; no material feasibility value may remain implicit."""

    errors: list[str] = []
    if value.get("schema_version") != "1.1":
        errors.append("schema_version must be 1.1")
    if value.get("status") != "ready_for_review":
        errors.append("status must be ready_for_review")
    _nonempty_text(value.get("research_goal"), "research_goal", errors)
    _nonempty_text(value.get("researcher_background"), "researcher_background", errors)
    _string_list(value.get("available_skills"), "available_skills", errors, 1)
    _string_list(value.get("preferred_domains"), "preferred_domains", errors, 1)
    _string_list(
        value.get("candidate_application_routes"),
        "candidate_application_routes",
        errors,
        1,
    )
    _number(value.get("time_horizon_years"), "time_horizon_years", errors, minimum=0.25, maximum=10)
    _number(value.get("weekly_hours"), "weekly_hours", errors, minimum=1, maximum=100)
    _number(value.get("cash_budget_usd"), "cash_budget_usd", errors, minimum=0)
    _number(
        value.get("cloud_compute_budget_usd"),
        "cloud_compute_budget_usd",
        errors,
        minimum=0,
    )

    compute = value.get("local_compute")
    if not isinstance(compute, dict):
        errors.append("local_compute must be an object")
    else:
        _nonempty_text(compute.get("gpu"), "local_compute.gpu", errors)
        _number(compute.get("ram_gb"), "local_compute.ram_gb", errors, minimum=1)
        _number(compute.get("storage_gb"), "local_compute.storage_gb", errors, minimum=1)
    _nonempty_text(value.get("equipment"), "equipment", errors)
    _nonempty_text(value.get("data_constraint"), "data_constraint", errors)

    weights = value.get("ranking_weights")
    if not isinstance(weights, dict):
        errors.append("ranking_weights must be an object")
    else:
        for field in WEIGHT_FIELDS:
            _number(weights.get(field), f"ranking_weights.{field}", errors, minimum=0, maximum=1)
        numeric = [weights.get(field) for field in WEIGHT_FIELDS]
        if all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in numeric):
            total = sum(float(item) for item in numeric)
            if abs(total - 1.0) > 1e-6:
                errors.append(f"ranking_weights must sum to 1.0, found {total:g}")

    _string_list(value.get("excluded_domains"), "excluded_domains", errors)
    _string_list(
        value.get("ethics_or_legal_constraints"),
        "ethics_or_legal_constraints",
        errors,
    )
    _string_list(value.get("notes"), "notes", errors)
    if value.get("human_review_required") is not True:
        errors.append("human_review_required must be true")
    return errors
