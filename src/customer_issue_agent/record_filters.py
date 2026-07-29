from __future__ import annotations

from typing import Any


def filter_records(
    records: list[dict[str, Any]],
    *,
    platform: str = "",
    issue_category: str = "",
    responsibility: str = "",
    feedback_status: str = "",
    q: str = "",
) -> list[dict[str, Any]]:
    filters = {
        "platform": _clean(platform),
        "issue_category": _clean(issue_category),
        "responsibility": _clean(responsibility),
        "feedback_status": _clean(feedback_status),
        "q": _clean(q),
    }
    if not any(filters.values()):
        return records
    return [record for record in records if _matches(record, filters)]


def _matches(record: dict[str, Any], filters: dict[str, str]) -> bool:
    analysis = record.get("analysis") or {}
    request = analysis.get("request") or {}
    attribution = analysis.get("attribution") or {}

    if filters["platform"] and filters["platform"] not in _clean(request.get("platform")):
        return False
    if filters["issue_category"] and filters["issue_category"] != _clean(attribution.get("issue_category")):
        return False
    if filters["responsibility"] and filters["responsibility"] != _clean(attribution.get("primary_responsibility")):
        return False
    if filters["feedback_status"] and filters["feedback_status"] != _feedback_status(record.get("feedback")):
        return False
    if filters["q"] and filters["q"] not in _search_text(record):
        return False
    return True


def _feedback_status(feedback: object) -> str:
    if not isinstance(feedback, dict):
        return "unreviewed"
    return "accepted" if feedback.get("accepted") else "corrected"


def _search_text(record: dict[str, Any]) -> str:
    analysis = record.get("analysis") or {}
    request = analysis.get("request") or {}
    attribution = analysis.get("attribution") or {}
    feedback = record.get("feedback") or {}
    values = [
        record.get("id"),
        request.get("platform"),
        analysis.get("report"),
        attribution.get("customer_problem"),
        attribution.get("issue_category"),
        attribution.get("primary_responsibility"),
        attribution.get("evidence_strength"),
        attribution.get("recommended_actions"),
        attribution.get("missing_information"),
        feedback.get("note"),
    ]
    return _clean(" ".join(_flatten(values)))


def _flatten(values: list[object]) -> list[str]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, list):
            flattened.extend(_flatten(value))
        elif value is not None:
            flattened.append(str(value))
    return flattened


def _clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()
