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
        ".GIT/config",
        ".worktrees/other/file.md",
        "docs/.git/config",
        "docs/.WorkTrees/file.md",
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


def test_applier_validates_all_operations_before_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "README.md", "# existing\n")
    plan = ExecutionPlan(
        summary="atomic validation",
        operations=[
            ExecutionOperation("create_text", "docs/first.md", "first\n"),
            ExecutionOperation("create_text", "README.md", "# new\n"),
        ],
    )

    with pytest.raises(ExecutionPlanError, match="already exists"):
        ExecutionPlanApplier(tmp_path).apply(plan)

    assert not (tmp_path / "docs" / "first.md").exists()
    assert read_text_utf8(tmp_path / "README.md") == "# existing\n"


def test_applier_preview_reports_target_state_bytes_and_risk(tmp_path) -> None:
    write_text_utf8(tmp_path / "existing.md", "旧内容\n")
    plan = ExecutionPlan(
        summary="预览",
        operations=[
            ExecutionOperation("create_text", "docs/new.md", "# 新文件\n"),
            ExecutionOperation("overwrite_text", "existing.md", "新内容\n"),
            ExecutionOperation("append_text", "logs/new.md", "追加\n"),
            ExecutionOperation("append_text", "existing.md", "继续追加\n"),
        ],
    )

    result = ExecutionPlanApplier(tmp_path).preview(plan)

    assert result.applied is False
    assert result.preview_changes_as_dicts() == [
        {
            "action": "create_text",
            "path": "docs/new.md",
            "exists": False,
            "content_bytes": len("# 新文件\n".encode("utf-8")),
            "risk": "create",
        },
        {
            "action": "overwrite_text",
            "path": "existing.md",
            "exists": True,
            "content_bytes": len("新内容\n".encode("utf-8")),
            "risk": "overwrite",
        },
        {
            "action": "append_text",
            "path": "logs/new.md",
            "exists": False,
            "content_bytes": len("追加\n".encode("utf-8")),
            "risk": "append_create",
        },
        {
            "action": "append_text",
            "path": "existing.md",
            "exists": True,
            "content_bytes": len("继续追加\n".encode("utf-8")),
            "risk": "append",
        },
    ]
    assert not (tmp_path / "docs" / "new.md").exists()
    assert read_text_utf8(tmp_path / "existing.md") == "旧内容\n"


def test_applier_preview_rejects_create_conflict_without_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "README.md", "# existing\n")
    plan = ExecutionPlan(
        summary="冲突",
        operations=[
            ExecutionOperation("create_text", "docs/first.md", "first\n"),
            ExecutionOperation("create_text", "README.md", "# new\n"),
        ],
    )

    with pytest.raises(ExecutionPlanError, match="already exists"):
        ExecutionPlanApplier(tmp_path).preview(plan)

    assert not (tmp_path / "docs" / "first.md").exists()
    assert read_text_utf8(tmp_path / "README.md") == "# existing\n"
