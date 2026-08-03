import pytest

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
