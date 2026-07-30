import json
from datetime import UTC, datetime, timedelta

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
    assert 'id="platform-filter"' in html
    assert 'name="platform"' in html
    assert 'id="platform-filter" name="platform" list="platform-presets"' in html
    assert 'id="issue-filter"' in html
    assert 'id="responsibility-filter"' in html
    assert 'id="feedback-filter"' in html
    assert 'id="filter-count"' in html
    assert 'id="filter-empty"' in html
    assert 'data-filter-reset' in html
    assert 'id="export-filter-summary"' in html
    assert 'class="export-filter-summary"' in html
    assert 'aria-live="polite"' in html
    assert "将导出全部记录" in html


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
    assert "platform-filter" in script
    assert "matchesPlatform" in script
    assert "filters.platform" in script
    assert "updateExportFilterSummary" in script
    assert "export-filter-summary" in script
    assert "将导出全部记录" in script
    assert "筛选导出将应用" in script
    assert "updateExportFilterSummary();" in script
    assert 'labelFor("issue_category", issue)' in script


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


def test_records_summary_endpoint_returns_counts(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    analysis_response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    record_id = analysis_response.json()["record_id"]
    client.post(f"/api/records/{record_id}/feedback", data={"accepted": "false"})

    response = client.get("/api/records/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 1
    assert payload["reviewed_records"] == 1
    assert payload["corrected_records"] == 1
    assert payload["platforms"] == [{"value": "Amazon", "count": 1}]
    assert payload["issue_categories"]
    assert payload["responsibilities"]
    assert payload["evidence_strengths"]
    assert payload["feedback_statuses"] == [{"value": "corrected", "count": 1}]


def test_records_summary_endpoint_returns_empty_summary(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/api/records/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 0
    assert payload["reviewed_records"] == 0
    assert payload["corrected_records"] == 0
    assert payload["platforms"] == []
    assert payload["issue_categories"] == []


def test_index_contains_summary_dashboard_region(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="records-summary"' in html
    assert 'id="summary-content"' in html
    assert "运营概览" in html
    assert "概览加载中..." in html


def test_static_app_js_contains_summary_dashboard_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "loadRecordsSummary" in script
    assert "renderRecordsSummary" in script
    assert "summaryMetric" in script
    assert "summaryDistribution" in script
    assert "平台分布" in script
    assert "summary.platforms" in script
    assert "bindSummaryPlatformFilters" in script
    assert "applySummaryPlatformFilter" in script
    assert "data-summary-platform-filter" in script
    assert "scrollIntoView" in script


def test_styles_cover_summary_dashboard_components(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    css = response.text
    assert ".summary-dashboard" in css
    assert ".summary-metrics" in css
    assert ".summary-card" in css
    assert ".distribution-list" in css
    assert ".summary-filter-link" in css


def test_export_records_csv_endpoint_filters_by_query_params(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    amazon_response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    tiktok_response = client.post(
        "/api/analyze",
        data={"platform": "TikTok Shop", "conversation_text": "Customer: missing cable"},
    )
    client.post(
        f"/api/records/{amazon_response.json()['record_id']}/feedback",
        data={"accepted": "false", "note": "需要产品团队复核"},
    )
    client.post(
        f"/api/records/{tiktok_response.json()['record_id']}/feedback",
        data={"accepted": "true"},
    )

    response = client.get(
        "/api/records/export.csv",
        params={"platform": "amazon", "feedback_status": "corrected", "q": "产品团队"},
    )

    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    assert "Amazon" in text
    assert "TikTok Shop" not in text
    assert "需要产品团队复核" in text


def test_export_records_csv_endpoint_filtered_empty_returns_header(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )

    response = client.get("/api/records/export.csv", params={"feedback_status": "archived"})

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8-sig")
    lines = [line for line in text.splitlines() if line]
    assert len(lines) == 1


def test_index_contains_filtered_export_button(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert "导出筛选 CSV" in html
    assert "data-filter-export" in html


def test_static_app_js_contains_filtered_export_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindFilteredExport" in script
    assert "buildFilteredExportUrl" in script
    assert "data-filter-export" in script
    assert "feedback_status" in script
    assert "platform-filter" in script
    assert 'params.set("platform", platform)' in script
    assert "时间" in script
    assert "最近 7 天" in script
    assert "最近 30 天" in script


def _stored_record(record_id: str, *, platform: str, created_at: datetime, issue_category: str = "function_use") -> dict:
    return {
        "id": record_id,
        "created_at": created_at.isoformat(),
        "analysis": {
            "request": {"platform": platform, "conversation_text": "Customer: not working"},
            "attribution": {
                "customer_problem": f"{platform} 客户反馈无法使用",
                "issue_category": issue_category,
                "root_causes": ["unclear_instructions"],
                "primary_responsibility": "customer_service_training",
                "evidence_strength": "likely",
                "recommended_actions": ["补问设备型号"],
                "missing_information": ["错误提示截图"],
            },
            "report": f"{platform} 客户反馈无法使用",
        },
        "feedback": None,
    }


def _write_jsonl_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def test_records_summary_endpoint_filters_by_time_range(tmp_path):
    storage_path = tmp_path / "analyses.jsonl"
    now = datetime.now(UTC)
    _write_jsonl_records(
        storage_path,
        [
            _stored_record("recent", platform="Amazon", created_at=now - timedelta(days=2)),
            _stored_record("old", platform="TikTok Shop", created_at=now - timedelta(days=40)),
        ],
    )
    app = create_app(storage_path=storage_path)
    client = TestClient(app)

    response = client.get("/api/records/summary", params={"range": "7d"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_records"] == 1
    assert payload["platforms"] == [{"value": "Amazon", "count": 1}]
    assert payload["issue_categories"] == [{"value": "function_use", "count": 1}]


def test_export_records_csv_endpoint_filters_by_time_range_and_query(tmp_path):
    storage_path = tmp_path / "analyses.jsonl"
    now = datetime.now(UTC)
    _write_jsonl_records(
        storage_path,
        [
            _stored_record("recent-amazon", platform="Amazon", created_at=now - timedelta(days=2)),
            _stored_record("recent-tiktok", platform="TikTok Shop", created_at=now - timedelta(days=2)),
            _stored_record("old-amazon", platform="Amazon", created_at=now - timedelta(days=40)),
        ],
    )
    app = create_app(storage_path=storage_path)
    client = TestClient(app)

    response = client.get("/api/records/export.csv", params={"range": "30d", "platform": "amazon"})

    assert response.status_code == 200
    text = response.content.decode("utf-8-sig")
    assert "recent-amazon" in text
    assert "recent-tiktok" not in text
    assert "old-amazon" not in text


def test_index_contains_summary_range_selector(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="summary-range"' in html
    assert 'value="7d"' in html
    assert 'value="30d"' in html
    assert "最近 7 天" in html


def test_static_app_js_contains_summary_range_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindSummaryRange" in script
    assert "summary-range" in script
    assert 'params.set("range", range)' in script
    assert 'params.set("range", summaryRange)' in script
    assert "updateExportFilterSummary();" in script


def test_recent_records_include_expandable_detail_markup(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)
    response = client.post(
        "/api/analyze",
        data={"platform": "Amazon", "conversation_text": "Customer: not working"},
    )
    record_id = response.json()["record_id"]
    client.post(
        f"/api/records/{record_id}/feedback",
        data={"accepted": "false", "note": "需要复核安装步骤"},
    )

    html = client.get("/").text

    assert "查看详情" in html
    assert "data-record-detail-toggle" in html
    assert 'aria-expanded="false"' in html
    assert 'aria-controls="record-detail-' in html
    assert 'class="record-detail"' in html
    assert "复制详情" in html
    assert "data-record-copy" in html
    assert "data-record-copy-status" in html
    assert 'aria-live="polite"' in html
    assert "客户问题" in html
    assert "下一步建议" in html
    assert "人工备注" in html
    assert "需要复核安装步骤" in html


def test_static_app_js_contains_record_detail_hooks(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/app.js")

    assert response.status_code == 200
    script = response.text
    assert "bindRecordDetails" in script
    assert "toggleRecordDetail" in script
    assert "recordDetailHtml" in script
    assert "data-record-detail-toggle" in script
    assert "data-record-copy" in script
    assert "data-record-copy-status" in script
    assert "aria-expanded" in script
    assert "收起详情" in script
    assert "bindRecordCopyActions" in script
    assert "copyRecordDetails" in script
    assert "buildRecordDetailCopyText" in script
    assert "navigator.clipboard.writeText" in script
    assert "已复制详情" in script
    assert "复制失败，请手动选择详情文本" in script
    assert "bindRecordCopyActions(article)" in script


def test_styles_cover_record_detail_components(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/static/styles.css")

    assert response.status_code == 200
    css = response.text
    assert ".record-detail-toggle" in css
    assert ".record-detail" in css
    assert ".record-detail-grid" in css
    assert ".record-detail-grid dt" in css
    assert ".record-copy-action" in css
    assert ".record-copy-status" in css


def test_index_contains_platform_presets_for_all_platform_inputs(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="platform-presets"' in html
    assert 'id="paste-platform" name="platform" list="platform-presets"' in html
    assert 'id="upload-platform" name="platform" list="platform-presets"' in html
    assert 'id="batch-platform" name="platform" list="platform-presets"' in html
    assert 'value="Amazon"' in html
    assert 'value="TikTok Shop"' in html
    assert 'value="Shopee"' in html
    assert 'value="Walmart Marketplace"' in html
    assert 'value="eBay"' in html
    assert 'value="Shopify"' in html
    assert 'value="AliExpress"' in html
    assert 'value="Lazada"' in html
    assert 'value="Temu"' in html
    assert 'value="Shein"' in html
    assert 'value="Other overseas platform"' in html
