from __future__ import annotations

import csv
from io import StringIO
from typing import Any

CSV_HEADERS = [
    "记录 ID",
    "创建时间",
    "平台",
    "客户问题",
    "问题类型",
    "业务原因",
    "优先责任方",
    "证据强度",
    "下一步建议",
    "需要补充",
    "是否认可",
    "修正问题类型",
    "修正责任方",
    "人工备注",
]


def build_records_csv(records: list[dict[str, Any]]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=CSV_HEADERS)
    writer.writeheader()
    for record in records:
        writer.writerow(_record_to_row(record))
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


def _record_to_row(record: dict[str, Any]) -> dict[str, str]:
    analysis = record.get("analysis") or {}
    request = analysis.get("request") or {}
    attribution = analysis.get("attribution") or {}
    feedback = record.get("feedback") or {}

    return {
        "记录 ID": _text(record.get("id")),
        "创建时间": _text(record.get("created_at")),
        "平台": _text(request.get("platform")),
        "客户问题": _text(attribution.get("customer_problem")),
        "问题类型": _text(attribution.get("issue_category")),
        "业务原因": _join(attribution.get("root_causes")),
        "优先责任方": _text(attribution.get("primary_responsibility")),
        "证据强度": _text(attribution.get("evidence_strength")),
        "下一步建议": _join(attribution.get("recommended_actions")),
        "需要补充": _join(attribution.get("missing_information")),
        "是否认可": _accepted_label(feedback),
        "修正问题类型": _text(feedback.get("corrected_issue_category")),
        "修正责任方": _text(feedback.get("corrected_responsibility")),
        "人工备注": _text(feedback.get("note")),
    }


def _join(value: object) -> str:
    if isinstance(value, list):
        return "；".join(_text(item) for item in value if _text(item))
    return _text(value)


def _accepted_label(feedback: dict[str, Any]) -> str:
    if "accepted" not in feedback or feedback.get("accepted") is None:
        return ""
    return "是" if feedback.get("accepted") else "否"


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
