import pytest

from dev_agent.encoding import read_text_utf8, write_text_utf8
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError


def test_applier_creates_overwrites_and_appends_utf8_text(tmp_path) -> None:
    write_text_utf8(tmp_path / "existing.md", "旧内容\n")
    plan = ExecutionPlan(
        summary="写入中文文本",
        operations=[
            ExecutionOperation("create_text", "docs/new.md", "# 新文件\n"),
            ExecutionOperation("overwrite_text", "existing.md", "新内容\n"),
            ExecutionOperation("append_text", "logs/run.md", "追加中文\n"),
        ],
    )

    result = ExecutionPlanApplier(tmp_path).apply(plan)

    assert result.applied is True
    assert [change.path for change in result.changes] == ["docs/new.md", "existing.md", "logs/run.md"]
    assert read_text_utf8(tmp_path / "docs" / "new.md") == "# 新文件\n"
    assert read_text_utf8(tmp_path / "existing.md") == "新内容\n"
    assert read_text_utf8(tmp_path / "logs" / "run.md") == "追加中文\n"


def test_applier_rejects_create_when_file_exists(tmp_path) -> None:
    write_text_utf8(tmp_path / "README.md", "# existing\n")
    plan = ExecutionPlan(
        summary="冲突",
        operations=[ExecutionOperation("create_text", "README.md", "# new\n")],
    )

    with pytest.raises(ExecutionPlanError, match="already exists"):
        ExecutionPlanApplier(tmp_path).apply(plan)

    assert read_text_utf8(tmp_path / "README.md") == "# existing\n"


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        "../escape.md",
        ".git/config",
        ".worktrees/other/file.md",
        ".superpowers/cache.md",
    ],
)
def test_applier_rejects_unsafe_paths(tmp_path, unsafe_path: str) -> None:
    plan = ExecutionPlan(
        summary="拒绝危险路径",
        operations=[ExecutionOperation("overwrite_text", unsafe_path, "内容\n")],
    )

    with pytest.raises(ExecutionPlanError):
        ExecutionPlanApplier(tmp_path).apply(plan)
