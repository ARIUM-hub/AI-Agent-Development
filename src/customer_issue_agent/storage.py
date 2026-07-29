from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from customer_issue_agent.domain import AnalysisResult


class AnalysisStore:
    def __init__(self, path: Path):
        self.path = path

    def save(self, analysis: AnalysisResult) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record_id = str(uuid4())
        payload = {
            "id": record_id,
            "created_at": datetime.now(UTC).isoformat(),
            "analysis": analysis.model_dump(mode="json"),
            "feedback": None,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return record_id

    def save_feedback(self, record_id: str, feedback: dict) -> dict:
        if not self.get_record(record_id):
            raise KeyError(record_id)

        cleaned = _clean_feedback(feedback)
        event = {
            "type": "feedback",
            "record_id": record_id,
            "updated_at": datetime.now(UTC).isoformat(),
            "feedback": cleaned,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        return cleaned

    def get_record(self, record_id: str) -> dict | None:
        for record in self.list_records():
            if record["id"] == record_id:
                return record
        return None

    def list_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        records: list[dict] = []
        feedback_by_record: dict[str, dict] = {}
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if payload.get("type") == "feedback":
                    feedback_by_record[payload["record_id"]] = payload["feedback"]
                else:
                    records.append(payload)

        for record in records:
            if record["id"] in feedback_by_record:
                record["feedback"] = feedback_by_record[record["id"]]
        return records


def _clean_feedback(feedback: dict) -> dict:
    return {
        "accepted": bool(feedback.get("accepted")),
        "corrected_issue_category": _optional_text(feedback.get("corrected_issue_category")),
        "corrected_responsibility": _optional_text(feedback.get("corrected_responsibility")),
        "note": _optional_text(feedback.get("note")),
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None
