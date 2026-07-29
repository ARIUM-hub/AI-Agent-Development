from customer_issue_agent.ingestion import extract_conversation_text


def test_extract_plain_text_upload():
    result = extract_conversation_text(
        filename="chat.txt",
        content=b"Customer: It does not connect\nAgent: Please restart it",
    )

    assert result == "Customer: It does not connect\nAgent: Please restart it"


def test_extract_csv_upload_combines_rows():
    content = "speaker,message\nCustomer,It does not connect\nAgent,Please restart it\n".encode("utf-8")

    result = extract_conversation_text(filename="chat.csv", content=content)

    assert "Customer: It does not connect" in result
    assert "Agent: Please restart it" in result


def test_extract_rejects_empty_upload():
    try:
        extract_conversation_text(filename="chat.txt", content=b"   ")
    except ValueError as exc:
        assert "没有可分析内容" in str(exc)
    else:
        raise AssertionError("empty upload should fail")
