from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def filter_records(
    records: list[dict[str, Any]],
    *,
    platform: str = "",
    issue_category: str = "",
    responsibility: str = "",
    feedback_status: str = "",
    q: str = "",
    range: str = "all",
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    filters = {
        "platform": _clean(platform),
        "issue_category": _clean(issue_category),
        "responsibility": _clean(responsibility),
        "feedback_status": _clean(feedback_status),
        "q": _clean(q),
        "range": _range_value(range),
    }
    if not any(value for key, value in filters.items() if key != "range") and filters["range"] == "all":
        return records
    current_time = now or datetime.now(UTC)
    return [record for record in records if _matches(record, filters, current_time)]


def _matches(record: dict[str, Any], filters: dict[str, str], now: datetime) -> bool:
    analysis = record.get("analysis") or {}
    request = analysis.get("request") or {}
    attribution = analysis.get("attribution") or {}

    if filters["range"] != "all" and not _matches_range(record, filters["range"], now):
        return False
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


def _matches_range(record: dict[str, Any], range_value: str, now: datetime) -> bool:
    created_at = _parse_created_at(record.get("created_at"))
    if created_at is None:
        return False
    days = 7 if range_value == "7d" else 30
    return created_at >= now - timedelta(days=days)


def _parse_created_at(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _range_value(value: object) -> str:
    cleaned = _clean(value)
    return cleaned if cleaned in {"7d", "30d"} else "all"


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
