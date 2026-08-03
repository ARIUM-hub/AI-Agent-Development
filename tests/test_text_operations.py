import pytest

from dev_agent.execution.models import ExecutionOperation
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.execution.text_operations import apply_replace_text


def operation(old_text: str, new_text: str) -> ExecutionOperation:
    return ExecutionOperation(
        action="replace_text",
        path="src/app.py",
        old_text=old_text,
        new_text=new_text,
    )


def test_apply_replace_text_replaces_one_chinese_fragment() -> None:
    assert apply_replace_text(operation("旧片段", "新片段"), "前旧片段后", True) == (
        "前新片段后"
    )


def test_apply_replace_text_allows_empty_new_text() -> None:
    assert apply_replace_text(operation("删除", ""), "保留删除结尾", True) == "保留结尾"


@pytest.mark.parametrize(
    ("current", "old_text", "new_text", "exists", "message"),
    [
        ("内容", "PRIVATE_OLD", "PRIVATE_NEW", False, "目标文件不存在"),
        ("内容", "", "PRIVATE_NEW", True, "old_text 不能为空"),
        ("PRIVATE_SAME", "PRIVATE_SAME", "PRIVATE_SAME", True, "不能相同"),
        ("内容", "MISSING_FRAGMENT", "PRIVATE_NEW", True, "实际 0 处"),
        (
            "PRIVATE_DUP / PRIVATE_DUP",
            "PRIVATE_DUP",
            "PRIVATE_NEW",
            True,
            "实际 2 处",
        ),
        ("aaa", "aa", "PRIVATE_NEW", True, "实际 2 处"),
    ],
)
def test_apply_replace_text_rejects_unsafe_semantics_without_echoing_fragments(
    current: str,
    old_text: str,
    new_text: str,
    exists: bool,
    message: str,
) -> None:
    with pytest.raises(ExecutionPlanError, match=message) as error:
        apply_replace_text(operation(old_text, new_text), current, exists)

    if old_text:
        assert old_text not in str(error.value)
    if new_text:
        assert new_text not in str(error.value)


def test_apply_replace_text_rejects_wrong_action() -> None:
    wrong = ExecutionOperation("append_text", "src/app.py", "内容")

    with pytest.raises(ExecutionPlanError, match="unsupported action"):
        apply_replace_text(wrong, "内容", True)


@pytest.mark.parametrize(
    ("old_text", "new_text", "message"),
    [
        (None, "PRIVATE_NEW", "old_text 必须是字符串"),
        ("PRIVATE_OLD", None, "new_text 必须是字符串"),
    ],
)
def test_apply_replace_text_rejects_non_string_fragments(
    old_text: str | None,
    new_text: str | None,
    message: str,
) -> None:
    invalid = ExecutionOperation(
        action="replace_text",
        path="src/app.py",
        old_text=old_text,
        new_text=new_text,
    )

    with pytest.raises(ExecutionPlanError, match=message):
        apply_replace_text(invalid, "PRIVATE_OLD", True)
