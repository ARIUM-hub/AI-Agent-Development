from fastapi.testclient import TestClient

from customer_issue_agent import __version__
from customer_issue_agent.app import create_app


def test_package_imports():
    assert __version__ == "0.1.0"


def test_analyze_text_endpoint_returns_report(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post(
        "/api/analyze",
        data={
            "platform": "Other overseas platform",
            "conversation_text": (
                "Customer: I followed the instructions but it still will not connect.\n"
                "Agent: Please try again later."
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_id"]
    assert "客户问题" in payload["analysis"]["report"]
    assert payload["analysis"]["request"]["platform"] == "Other overseas platform"


def test_analyze_rejects_empty_text(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post("/api/analyze", data={"platform": "Other", "conversation_text": "   "})

    assert response.status_code == 422
