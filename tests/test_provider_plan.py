import pytest

from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.execution.provider_plan import parse_provider_execution_plan


def test_parse_provider_execution_plan_accepts_strict_json_object() -> None:
    plan = parse_provider_execution_plan(
        '{"summary":"创建说明","operations":[{"action":"create_text","path":"docs/provider.md","content":"来自 provider\\n"}]}'
    )

    assert plan.summary == "创建说明"
    assert plan.operations[0].action == "create_text"
    assert plan.operations[0].path == "docs/provider.md"
    assert plan.operations[0].content == "来自 provider\n"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "计划：创建说明文件。",
        '[{"action":"create_text","path":"docs/provider.md","content":"x"}]',
        '"not an object"',
        '{"summary":"缺少 operations"}',
        '{"summary":"坏 action","operations":[{"action":"delete_file","path":"README.md","content":""}]}',
        '{"summary":',
    ],
)
def test_parse_provider_execution_plan_rejects_invalid_provider_text(text: str) -> None:
    with pytest.raises(ExecutionPlanError, match="无法解析 provider 执行计划"):
        parse_provider_execution_plan(text)
