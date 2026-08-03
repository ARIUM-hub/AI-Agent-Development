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


@pytest.mark.parametrize(
    "text",
    [
        '{"operations":[{"action":"create_text","path":"docs/a.md","content":"x"}]}',
        '{"summary":"额外顶层字段","operations":[{"action":"create_text","path":"docs/a.md","content":"x"}],"extra":true}',
        '{"summary":"额外操作字段","operations":[{"action":"create_text","path":"docs/a.md","content":"x","mode":"unsafe"}]}',
    ],
)
def test_parse_provider_execution_plan_requires_exact_fields(text: str) -> None:
    with pytest.raises(ExecutionPlanError, match="无法解析 provider 执行计划"):
        parse_provider_execution_plan(text)


def test_parse_provider_execution_plan_accepts_replace_schema() -> None:
    plan = parse_provider_execution_plan(
        '{"summary":"替换","operations":[{"action":"replace_text",'
        '"path":"src/app.py","old_text":"旧","new_text":"新"}]}'
    )

    assert plan.operations[0].to_dict() == {
        "action": "replace_text",
        "path": "src/app.py",
        "old_text": "旧",
        "new_text": "新",
    }


@pytest.mark.parametrize(
    "text",
    [
        '{"summary":"错字段","operations":[{"action":"replace_text","path":"a.py","content":"x"}]}',
        '{"summary":"混入 content","operations":[{"action":"replace_text","path":"a.py","old_text":"a","new_text":"b","content":"x"}]}',
        '{"summary":"现有动作混入 old","operations":[{"action":"append_text","path":"a.py","content":"x","old_text":"a"}]}',
        '{"summary":"额外字段","operations":[{"action":"replace_text","path":"a.py","old_text":"a","new_text":"b","mode":"unsafe"}]}',
    ],
)
def test_parse_provider_execution_plan_rejects_action_specific_field_mismatch(
    text: str,
) -> None:
    with pytest.raises(ExecutionPlanError, match="无法解析 provider 执行计划"):
        parse_provider_execution_plan(text)
