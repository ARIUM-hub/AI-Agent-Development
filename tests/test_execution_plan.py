import pytest

from dev_agent.execution.models import ExecutionOperation
from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan


def test_parse_execution_plan_accepts_text_operations() -> None:
    plan = parse_execution_plan(
        {
            "summary": "创建说明",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/local-execution.md",
                    "content": "# 本地执行\n",
                },
                {
                    "action": "append_text",
                    "path": "README.md",
                    "content": "补充说明\n",
                },
            ],
        }
    )

    assert plan.summary == "创建说明"
    assert plan.operations[0].action == "create_text"
    assert plan.operations[0].path == "docs/local-execution.md"
    assert plan.operations[0].content == "# 本地执行\n"
    assert plan.operations[1].action == "append_text"


def test_parse_execution_plan_rejects_missing_operations() -> None:
    with pytest.raises(ExecutionPlanError, match="operations"):
        parse_execution_plan({"summary": "缺少操作"})


def test_parse_execution_plan_rejects_unknown_action() -> None:
    with pytest.raises(ExecutionPlanError, match="unsupported action"):
        parse_execution_plan(
            {
                "summary": "危险操作",
                "operations": [
                    {
                        "action": "delete_file",
                        "path": "README.md",
                        "content": "",
                    }
                ],
            }
        )


def test_parse_execution_plan_rejects_non_string_content() -> None:
    with pytest.raises(ExecutionPlanError, match="content"):
        parse_execution_plan(
            {
                "summary": "内容类型错误",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "README.md",
                        "content": 123,
                    }
                ],
            }
        )


def test_execution_operation_serializes_fields_for_each_action() -> None:
    existing = ExecutionOperation("append_text", "README.md", "追加\n")
    replace = ExecutionOperation(
        action="replace_text",
        path="src/app.py",
        old_text="旧片段",
        new_text="新片段",
    )

    assert existing.to_dict() == {
        "action": "append_text",
        "path": "README.md",
        "content": "追加\n",
    }
    assert replace.to_dict() == {
        "action": "replace_text",
        "path": "src/app.py",
        "old_text": "旧片段",
        "new_text": "新片段",
    }


def test_parse_execution_plan_accepts_strict_replace_operation() -> None:
    plan = parse_execution_plan(
        {
            "summary": "局部替换",
            "operations": [
                {
                    "action": "replace_text",
                    "path": "src/app.py",
                    "old_text": "旧片段",
                    "new_text": "新片段",
                }
            ],
        }
    )

    assert plan.operations[0].to_dict() == {
        "action": "replace_text",
        "path": "src/app.py",
        "old_text": "旧片段",
        "new_text": "新片段",
    }


@pytest.mark.parametrize(
    "operation",
    [
        {"action": "replace_text", "path": "a.py", "new_text": "新"},
        {"action": "replace_text", "path": "a.py", "old_text": "旧"},
        {
            "action": "replace_text",
            "path": "a.py",
            "old_text": 1,
            "new_text": "新",
        },
        {
            "action": "replace_text",
            "path": "a.py",
            "old_text": "旧",
            "new_text": 1,
        },
        {
            "action": "replace_text",
            "path": "a.py",
            "old_text": "旧",
            "new_text": "新",
            "content": "禁止",
        },
        {
            "action": "replace_text",
            "path": "a.py",
            "old_text": "旧",
            "new_text": "新",
            "extra": True,
        },
    ],
)
def test_parse_execution_plan_rejects_invalid_replace_fields(
    operation: dict[str, object],
) -> None:
    with pytest.raises(ExecutionPlanError):
        parse_execution_plan({"summary": "拒绝", "operations": [operation]})
