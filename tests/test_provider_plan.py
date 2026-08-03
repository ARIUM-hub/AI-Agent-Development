import pytest

from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.execution.provider_plan import (
    build_execution_plan_history_text,
    parse_provider_execution_plan,
)


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


def test_build_execution_plan_history_text_hashes_bodies_without_storing_them() -> None:
    plan = ExecutionPlan(
        summary="安全替换",
        operations=[
            ExecutionOperation("create_text", "docs/new.md", "CONTENT_SECRET_MARKER"),
            ExecutionOperation(
                action="replace_text",
                path="src/app.py",
                old_text="OLD_SOURCE_MARKER",
                new_text="NEW_SOURCE_MARKER",
            ),
        ],
    )

    history_text = build_execution_plan_history_text(plan)

    assert "安全替换" in history_text
    assert "create_text" in history_text
    assert "replace_text" in history_text
    assert "docs/new.md" in history_text
    assert "src/app.py" in history_text
    assert str(len("OLD_SOURCE_MARKER".encode("utf-8"))) in history_text
    assert history_text.count("sha256:") == 3
    assert "CONTENT_SECRET_MARKER" not in history_text
    assert "OLD_SOURCE_MARKER" not in history_text
    assert "NEW_SOURCE_MARKER" not in history_text
