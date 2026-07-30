import csv
from io import StringIO

from customer_issue_agent.export import CSV_HEADERS, build_records_csv


def test_build_records_csv_includes_bom_headers_and_feedback():
    records = [
        {
            "id": "record-1",
            "created_at": "2026-07-29T00:00:00+00:00",
            "analysis": {
                "request": {"platform": "Amazon"},
                "attribution": {
                    "customer_problem": "连接失败",
                    "issue_category": "function_use",
                    "root_causes": ["unclear_instructions", "customer_service_gap"],
                    "primary_responsibility": "customer_service_training",
                    "evidence_strength": "likely",
                    "recommended_actions": ["补问设备型号", "补问错误提示"],
                    "missing_information": ["设备型号"],
                },
            },
            "feedback": {
                "accepted": False,
                "corrected_issue_category": "product_fault",
                "corrected_responsibility": "supply_chain_quality",
                "note": "需要质量团队复核。",
            },
        }
    ]

    output = build_records_csv(records)

    assert output.startswith(b"\xef\xbb\xbf")
    text = output.decode("utf-8-sig")
    rows = list(csv.DictReader(StringIO(text)))
    assert CSV_HEADERS[:3] == ["记录 ID", "创建时间", "平台"]
    assert rows[0]["记录 ID"] == "record-1"
    assert rows[0]["平台"] == "Amazon"
    assert rows[0]["客户问题"] == "连接失败"
    assert rows[0]["业务原因"] == "unclear_instructions；customer_service_gap"
    assert rows[0]["是否认可"] == "否"
    assert rows[0]["修正责任方"] == "supply_chain_quality"
    assert rows[0]["人工备注"] == "需要质量团队复核。"


def test_build_records_csv_exports_header_when_empty():
    output = build_records_csv([])

    text = output.decode("utf-8-sig")
    rows = list(csv.reader(StringIO(text)))
    assert rows == [CSV_HEADERS]
