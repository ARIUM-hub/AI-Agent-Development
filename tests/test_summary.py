from customer_issue_agent.summary import build_records_summary


def test_build_records_summary_counts_totals_and_dimensions():
    records = [
        {
            "analysis": {
                "request": {"platform": "Amazon"},
                "attribution": {
                    "issue_category": "function_use",
                    "primary_responsibility": "customer_service_training",
                    "evidence_strength": "likely",
                }
            },
            "feedback": {"accepted": True},
        },
        {
            "analysis": {
                "request": {"platform": "TikTok Shop"},
                "attribution": {
                    "issue_category": "function_use",
                    "primary_responsibility": "product",
                    "evidence_strength": "clear",
                }
            },
            "feedback": {"accepted": False},
        },
        {
            "analysis": {
                "request": {"platform": "Amazon"},
                "attribution": {
                    "issue_category": "product_fault",
                    "primary_responsibility": "product",
                    "evidence_strength": "likely",
                }
            },
            "feedback": None,
        },
    ]

    summary = build_records_summary(records)

    assert summary["total_records"] == 3
    assert summary["reviewed_records"] == 2
    assert summary["corrected_records"] == 1
    assert summary["platforms"] == [
        {"value": "Amazon", "count": 2},
        {"value": "TikTok Shop", "count": 1},
    ]
    assert summary["issue_categories"] == [
        {"value": "function_use", "count": 2},
        {"value": "product_fault", "count": 1},
    ]
    assert summary["responsibilities"] == [
        {"value": "product", "count": 2},
        {"value": "customer_service_training", "count": 1},
    ]
    assert summary["evidence_strengths"] == [
        {"value": "likely", "count": 2},
        {"value": "clear", "count": 1},
    ]
    assert summary["feedback_statuses"] == [
        {"value": "accepted", "count": 1},
        {"value": "corrected", "count": 1},
        {"value": "unreviewed", "count": 1},
    ]


def test_build_records_summary_handles_empty_and_unknown_values():
    assert build_records_summary([]) == {
        "total_records": 0,
        "reviewed_records": 0,
        "corrected_records": 0,
        "platforms": [],
        "issue_categories": [],
        "responsibilities": [],
        "evidence_strengths": [],
        "feedback_statuses": [],
    }

    summary = build_records_summary(
        [
            {"analysis": {"request": {}, "attribution": {}}, "feedback": None},
            {"analysis": {"request": {"platform": "   "}, "attribution": {}}, "feedback": None},
        ]
    )

    assert summary["platforms"] == [{"value": "unknown", "count": 2}]
    assert summary["issue_categories"] == [{"value": "unknown", "count": 2}]
    assert summary["responsibilities"] == [{"value": "unknown", "count": 2}]
    assert summary["evidence_strengths"] == [{"value": "unknown", "count": 2}]
    assert summary["feedback_statuses"] == [{"value": "unreviewed", "count": 2}]
