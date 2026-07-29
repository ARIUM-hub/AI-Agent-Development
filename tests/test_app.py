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


def test_index_renders_workbench(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "客户使用问题归因智能体" in response.text
    assert "conversation_text" in response.text


def test_analyze_text_response_exposes_fields_for_ui(tmp_path):
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
    attribution = payload["analysis"]["attribution"]
    assert payload["record_id"]
    assert attribution["customer_problem"]
    assert attribution["issue_category"] == "function_use"
    assert attribution["primary_responsibility"] == "customer_service_training"
    assert attribution["evidence_strength"] == "likely"
    assert attribution["recommended_actions"]
    assert attribution["missing_information"]


def test_analyze_file_upload_returns_report(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post(
        "/api/analyze-file",
        data={"platform": "Other overseas platform"},
        files={
            "file": (
                "conversation.txt",
                (
                    "Customer: I followed the instructions but it still will not connect.\n"
                    "Agent: Please try again later."
                ),
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_id"]
    assert "客户问题" in payload["analysis"]["report"]
    assert payload["analysis"]["request"]["platform"] == "Other overseas platform"


def test_index_contains_tabs_forms_result_region_and_script(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'data-tab-target="paste-panel"' in html
    assert 'data-tab-target="upload-panel"' in html
    assert 'id="paste-form"' in html
    assert 'id="upload-form"' in html
    assert 'id="analysis-result"' in html
    assert 'id="recent-records"' in html
    assert 'role="alert"' in html
    assert '<script src="/static/app.js" defer></script>' in html


def test_static_app_js_contains_progressive_enhancement_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindTabs" in script
    assert "submitAnalysisForm" in script
    assert "renderAnalysisResult" in script
    assert "prependRecentRecord" in script
    assert "fetch(form.dataset.endpoint" in script
