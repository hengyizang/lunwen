#!/usr/bin/env python3
"""Shared JCR portfolio policy for the six-paper doctoral programme.

Quartiles are always JCR/JIF category-year quartiles.  They are venue targets,
not substitutes for the scientific quality gates applied to every paper.
"""
from __future__ import annotations

from typing import Any, Iterable


QUARTILE_RANK = {"Q1": 1, "Q2": 2}
DEFAULT_MINIMUM_Q1_PAPERS = 3
DEFAULT_FLOOR = "Q2"


def normalize_quartile(value: Any) -> str | None:
    result = str(value or "").strip().upper()
    return result if result in QUARTILE_RANK else None


def meets_target(actual: Any, target: Any) -> bool:
    actual_q = normalize_quartile(actual)
    target_q = normalize_quartile(target)
    return bool(
        actual_q
        and target_q
        and QUARTILE_RANK[actual_q] <= QUARTILE_RANK[target_q]
    )


def default_target(index: int, paper_count: int, minimum_q1: int = DEFAULT_MINIMUM_Q1_PAPERS) -> str:
    """Assign the first required papers to Q1 and every remainder to Q2."""

    if index < 1 or paper_count < 1 or index > paper_count:
        raise ValueError("paper index must be within the configured portfolio")
    return "Q1" if index <= min(minimum_q1, paper_count) else DEFAULT_FLOOR


def validate_portfolio(
    papers: Iterable[dict[str, Any]],
    *,
    minimum_q1: int = DEFAULT_MINIMUM_Q1_PAPERS,
    expected_count: int | None = None,
) -> list[str]:
    """Require at least three Q1-targeted papers and no target below Q2."""

    values = list(papers)
    errors: list[str] = []
    if expected_count is not None and len(values) != expected_count:
        errors.append(f"venue portfolio must contain exactly {expected_count} papers")
    seen: set[str] = set()
    q1_count = 0
    for index, paper in enumerate(values, 1):
        paper_id = str(paper.get("paper_id") or "")
        if paper_id:
            if paper_id in seen:
                errors.append(f"venue portfolio repeats {paper_id}")
            seen.add(paper_id)
        target = normalize_quartile(paper.get("target_jcr_quartile"))
        if target is None:
            errors.append(
                f"papers[{index - 1}].target_jcr_quartile must be Q1 or Q2"
            )
        elif target == "Q1":
            q1_count += 1
    required = min(minimum_q1, expected_count or len(values))
    if q1_count < required:
        errors.append(
            f"venue portfolio requires at least {required} Q1-targeted papers; found {q1_count}"
        )
    return errors


def target_from_contract(contract: Any, default: str = "Q1") -> str:
    """Read a paper target while keeping old Q1-only projects safe."""

    if isinstance(contract, dict):
        target = normalize_quartile(contract.get("target_jcr_quartile"))
        if target:
            return target
    return default
