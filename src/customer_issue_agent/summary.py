from __future__ import annotations

from collections import Counter
from typing import Any


def build_records_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    issue_categories: Counter[str] = Counter()
    responsibilities: Counter[str] = Counter()
    evidence_strengths: Counter[str] = Counter()
    feedback_statuses: Counter[str] = Counter()
    reviewed_records = 0
    corrected_records = 0

    for record in records:
        attribution = ((record.get("analysis") or {}).get("attribution") or {})
        issue_categories[_value(attribution.get("issue_category"))] += 1
        responsibilities[_value(attribution.get("primary_responsibility"))] += 1
        evidence_strengths[_value(attribution.get("evidence_strength"))] += 1

        status = _feedback_status(record.get("feedback"))
        feedback_statuses[status] += 1
        if status != "unreviewed":
            reviewed_records += 1
        if status == "corrected":
            corrected_records += 1

    return {
        "total_records": len(records),
        "reviewed_records": reviewed_records,
        "corrected_records": corrected_records,
        "issue_categories": _rank(issue_categories),
        "responsibilities": _rank(responsibilities),
        "evidence_strengths": _rank(evidence_strengths),
        "feedback_statuses": _rank(feedback_statuses),
    }


def _feedback_status(feedback: object) -> str:
    if not isinstance(feedback, dict):
        return "unreviewed"
    return "accepted" if feedback.get("accepted") else "corrected"


def _rank(counter: Counter[str]) -> list[dict[str, int | str]]:
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _value(value: object) -> str:
    if value is None:
        return "unknown"
    stripped = str(value).strip()
    return stripped or "unknown"
