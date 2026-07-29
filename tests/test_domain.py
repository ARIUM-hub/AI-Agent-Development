from customer_issue_agent.domain import (
    AnalysisRequest,
    EvidenceStrength,
    IssueCategory,
    Responsibility,
)


def test_analysis_request_trims_conversation_text():
    request = AnalysisRequest(
        platform="Shopee",
        conversation_text="  Customer: not working  ",
    )

    assert request.platform == "Shopee"
    assert request.conversation_text == "Customer: not working"


def test_domain_enums_keep_chinese_labels():
    assert IssueCategory.FUNCTION_USE.label == "功能不会用或设置失败"
    assert Responsibility.CUSTOMER_SERVICE_TRAINING.label == "客服培训"
    assert EvidenceStrength.INSUFFICIENT.label == "信息不足"
