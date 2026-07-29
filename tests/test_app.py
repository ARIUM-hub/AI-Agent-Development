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


def test_styles_cover_enhanced_workbench_components(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    css = response.text
    assert ".workspace-grid" in css
    assert ".tabs" in css
    assert ".result-grid" in css
    assert ".result-card" in css
    assert ".form-message.is-visible" in css
    assert "@media (max-width: 720px)" in css


def test_analyze_batch_file_returns_multiple_records(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post(
        "/api/analyze-batch-file",
        data={"platform": "Other overseas platform"},
        files={
            "file": (
                "batch.txt",
                "Customer: It will not connect\n\n---\n\nCustomer: Missing cable",
                "text/plain",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["batch_id"]
    assert payload["count"] == 2
    assert len(payload["records"]) == 2
    assert payload["records"][0]["record_id"]
    assert payload["records"][1]["analysis"]["request"]["platform"] == "Other overseas platform"


def test_feedback_endpoint_updates_record_feedback(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    analysis_response = client.post(
        "/api/analyze",
        data={"platform": "Other", "conversation_text": "Customer: not working"},
    )
    record_id = analysis_response.json()["record_id"]

    response = client.post(
        f"/api/records/{record_id}/feedback",
        data={
            "accepted": "false",
            "corrected_issue_category": "product_fault",
            "corrected_responsibility": "supply_chain_quality",
            "note": "需要质量团队复核。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_id"] == record_id
    assert payload["feedback"]["accepted"] is False
    assert payload["feedback"]["corrected_issue_category"] == "product_fault"
    assert payload["feedback"]["corrected_responsibility"] == "supply_chain_quality"
    assert payload["feedback"]["note"] == "需要质量团队复核。"


def test_feedback_endpoint_returns_404_for_missing_record(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post("/api/records/missing/feedback", data={"accepted": "true"})

    assert response.status_code == 404


def test_index_contains_batch_upload_and_feedback_controls(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'data-tab-target="batch-panel"' in html
    assert 'id="batch-form"' in html
    assert 'data-endpoint="/api/analyze-batch-file"' in html
    assert 'id="batch-results"' in html
    assert 'data-feedback-template' in html


def test_static_app_js_contains_batch_and_feedback_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "submitBatchForm" in script
    assert "renderBatchResults" in script
    assert "bindFeedbackForms" in script
    assert "submitFeedbackForm" in script


def test_export_records_csv_endpoint_returns_bom_csv_with_feedback(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    analysis_response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    record_id = analysis_response.json()["record_id"]
    client.post(
        f"/api/records/{record_id}/feedback",
        data={
            "accepted": "false",
            "corrected_issue_category": "product_fault",
            "corrected_responsibility": "supply_chain_quality",
            "note": "需要质量团队复核。",
        },
    )

    response = client.get("/api/records/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "customer-issue-records.csv" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    assert "记录 ID,创建时间,平台" in text
    assert "Amazon" in text
    assert "需要质量团队复核。" in text


def test_export_records_csv_endpoint_returns_header_when_empty(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/api/records/export.csv")

    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    assert text.startswith("记录 ID,创建时间,平台")


def test_index_contains_export_csv_link(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'href="/api/records/export.csv"' in response.text
    assert "导出 CSV" in response.text


def test_index_contains_recent_record_filter_controls(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="record-filter"' in html
    assert 'id="record-search"' in html
    assert 'id="issue-filter"' in html
    assert 'id="responsibility-filter"' in html
    assert 'id="feedback-filter"' in html
    assert 'id="filter-count"' in html
    assert 'id="filter-empty"' in html
    assert 'data-filter-reset' in html


def test_recent_records_include_filter_data_attributes(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    record_id = response.json()["record_id"]
    client.post(f"/api/records/{record_id}/feedback", data={"accepted": "true"})

    html = client.get("/").text

    assert 'data-record-id="' in html
    assert 'data-platform="Amazon"' in html
    assert 'data-issue-category="' in html
    assert 'data-responsibility="' in html
    assert 'data-feedback-status="accepted"' in html
    assert 'data-search-text="' in html


def test_static_app_js_contains_recent_record_filter_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindRecordFilters" in script
    assert "applyRecordFilters" in script
    assert "resetRecordFilters" in script
    assert "recordMatchesFilters" in script


def test_styles_cover_recent_record_filter_components(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    css = response.text
    assert ".record-filter" in css
    assert ".filter-field" in css
    assert ".filter-count" in css
    assert ".filter-empty" in css
