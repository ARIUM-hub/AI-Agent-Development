from customer_issue_agent.record_filters import filter_records


def _record(
    record_id: str,
    *,
    platform: str = "Amazon",
    issue_category: str = "function_use",
    responsibility: str = "customer_service_training",
    evidence_strength: str = "likely",
    report: str = "客户反馈无法连接，客服需要补问设备型号。",
    feedback: dict | None = None,
) -> dict:
    return {
        "id": record_id,
        "analysis": {
            "request": {"platform": platform},
            "attribution": {
                "customer_problem": report,
                "issue_category": issue_category,
                "primary_responsibility": responsibility,
                "evidence_strength": evidence_strength,
                "recommended_actions": ["补问设备型号"],
                "missing_information": ["错误提示截图"],
            },
            "report": report,
        },
        "feedback": feedback,
    }


def test_filter_records_returns_all_when_no_filters():
    records = [_record("one"), _record("two", platform="TikTok Shop")]

    assert filter_records(records) == records


def test_filter_records_matches_platform_keyword_case_insensitively():
    records = [_record("one", platform="Amazon"), _record("two", platform="TikTok Shop")]

    filtered = filter_records(records, platform="amazon")

    assert [record["id"] for record in filtered] == ["one"]


def test_filter_records_matches_enums_and_feedback_status():
    records = [
        _record("one", issue_category="function_use", responsibility="customer_service_training"),
        _record(
            "two",
            issue_category="product_fault",
            responsibility="product",
            feedback={"accepted": False, "note": "质量团队复核"},
        ),
        _record("three", issue_category="product_fault", responsibility="product", feedback={"accepted": True}),
    ]

    filtered = filter_records(
        records,
        issue_category="product_fault",
        responsibility="product",
        feedback_status="corrected",
    )

    assert [record["id"] for record in filtered] == ["two"]


def test_filter_records_searches_record_text_and_feedback_note():
    records = [
        _record("one", report="客户反馈安装失败"),
        _record("two", report="客户反馈缺少配件", feedback={"accepted": False, "note": "需要配件补发"}),
    ]

    assert [record["id"] for record in filter_records(records, q="安装")] == ["one"]
    assert [record["id"] for record in filter_records(records, q="补发")] == ["two"]


def test_filter_records_unknown_feedback_status_matches_nothing():
    records = [_record("one"), _record("two", feedback={"accepted": True})]

    assert filter_records(records, feedback_status="archived") == []
