from customer_issue_agent.attribution import analyze_attribution
from customer_issue_agent.parser import parse_conversation
from customer_issue_agent.report import build_report


def test_report_contains_analyst_sections_in_chinese():
    parsed = parse_conversation(
        platform="Other",
        text=(
            "Customer: I followed the instructions but it still will not connect.\n"
            "Agent: Please try again later."
        ),
    )
    attribution = analyze_attribution(parsed)

    report = build_report(parsed, attribution)

    assert "客户问题" in report
    assert "判断依据" in report
    assert "优先责任方" in report
    assert "下一步建议" in report
    assert "客服培训" in report
