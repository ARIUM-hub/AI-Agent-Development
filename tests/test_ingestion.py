from customer_issue_agent.ingestion import extract_batch_conversation_texts, extract_conversation_text


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


def test_extract_batch_text_upload_splits_on_explicit_separator():
    content = (
        "Customer: It will not connect\nAgent: Please restart it\n"
        "\n---\n"
        "Customer: Missing cable\nAgent: We can send a replacement"
    ).encode("utf-8")

    result = extract_batch_conversation_texts(filename="batch.txt", content=content)

    assert result == [
        "Customer: It will not connect\nAgent: Please restart it",
        "Customer: Missing cable\nAgent: We can send a replacement",
    ]


def test_extract_batch_csv_upload_uses_one_row_per_conversation():
    content = (
        "platform,conversation\n"
        "Amazon,\"Customer: It will not connect\"\n"
        "TikTok Shop,\"Customer: Missing cable\"\n"
    ).encode("utf-8")

    result = extract_batch_conversation_texts(filename="batch.csv", content=content)

    assert result == ["Customer: It will not connect", "Customer: Missing cable"]


def test_extract_batch_rejects_more_than_limit():
    conversations = "\n---\n".join(f"Customer: issue {index}" for index in range(51))

    try:
        extract_batch_conversation_texts(filename="batch.txt", content=conversations.encode("utf-8"))
    except ValueError as exc:
        assert "单次最多分析 50 条" in str(exc)
    else:
        raise AssertionError("batch over limit should fail")
