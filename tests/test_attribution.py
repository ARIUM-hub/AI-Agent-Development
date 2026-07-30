from customer_issue_agent.attribution import analyze_attribution
from customer_issue_agent.domain import EvidenceStrength, IssueCategory, Responsibility, RootCause
from customer_issue_agent.parser import parse_conversation


def test_attribution_detects_connection_guidance_gap():
    parsed = parse_conversation(
        platform="Other",
        text=(
            "Customer: I followed the instructions but it still will not connect.\n"
            "Agent: Please try again later."
        ),
    )

    result = analyze_attribution(parsed)

    assert result.issue_category == IssueCategory.FUNCTION_USE
    assert RootCause.UNCLEAR_INSTRUCTIONS in result.root_causes
    assert RootCause.CUSTOMER_SERVICE_GAP in result.root_causes
    assert result.primary_responsibility == Responsibility.CUSTOMER_SERVICE_TRAINING
    assert result.evidence_strength == EvidenceStrength.LIKELY


def test_attribution_marks_quality_signal():
    parsed = parse_conversation(
        platform="Amazon",
        text="Customer: The device is broken and stopped working after one day.\nAgent: Sorry.",
    )

    result = analyze_attribution(parsed)

    assert result.issue_category == IssueCategory.PRODUCT_FAULT
    assert RootCause.QUALITY_SIGNAL in result.root_causes
    assert result.primary_responsibility == Responsibility.SUPPLY_CHAIN_QUALITY


def test_attribution_requests_more_information_for_short_case():
    parsed = parse_conversation(platform="Shopee", text="Customer: not working")

    result = analyze_attribution(parsed)

    assert result.evidence_strength == EvidenceStrength.INSUFFICIENT
    assert result.primary_responsibility == Responsibility.NEED_MORE_INFORMATION
    assert "具体使用步骤" in result.missing_information
