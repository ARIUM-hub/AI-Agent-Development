from customer_issue_agent.parser import parse_conversation


def test_parse_detects_customer_and_agent_turns():
    parsed = parse_conversation(
        platform="Lazada",
        text="Customer: It will not connect\nAgent: Did you restart the device?",
    )

    assert parsed.platform == "Lazada"
    assert parsed.turns[0].speaker == "customer"
    assert parsed.turns[1].speaker == "agent"
    assert parsed.is_usage_related is True


def test_parse_marks_non_usage_logistics_question():
    parsed = parse_conversation(
        platform="Amazon",
        text="Customer: Where is my package?\nAgent: It is in transit.",
    )

    assert parsed.is_usage_related is False
    assert "物流或售前内容较多" in parsed.completeness_notes


def test_parse_flags_too_little_information():
    parsed = parse_conversation(platform="TikTok Shop", text="Customer: not working")

    assert "客户描述过短" in parsed.completeness_notes
