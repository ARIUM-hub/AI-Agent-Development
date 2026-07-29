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

    def list_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        records: list[dict] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
        return records
