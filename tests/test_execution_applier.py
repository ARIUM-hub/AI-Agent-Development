import pytest

from dev_agent.encoding import read_text_utf8, write_text_utf8
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionFileDiff, ExecutionOperation, ExecutionPlan, ExecutionResult
from dev_agent.execution.plan import ExecutionPlanError, StaleExecutionPreviewError


def apply_plan(repo_root, plan: ExecutionPlan):
    applier = ExecutionPlanApplier(repo_root)
    preview = applier.preview(plan)
    return applier.apply(plan, expected_fingerprint=preview.preview_fingerprint)


def replace(path: str, old_text: str, new_text: str) -> ExecutionOperation:
    return ExecutionOperation(
        action="replace_text",
        path=path,
        old_text=old_text,
        new_text=new_text,
    )


def test_execution_result_serializes_file_diffs() -> None:
    file_diff = ExecutionFileDiff(
        path="docs/example.md",
        status="added",
        diff_text="--- /dev/null\n+++ b/docs/example.md\n",
        additions=1,
        deletions=0,
        diff_line_count=2,
        diff_char_count=42,
        displayed_line_count=2,
        displayed_char_count=42,
        truncated=False,
        before_line_ending="none",
        after_line_ending="lf",
    )
    result = ExecutionResult(
        applied=False,
        planned_changes=[],
        file_diffs=[file_diff],
        preview_fingerprint="sha256:abc",
    )

    assert result.file_diffs_as_dicts() == [file_diff.to_dict()]
    assert result.preview_fingerprint == "sha256:abc"


def test_applier_returns_approved_diffs_after_apply(tmp_path) -> None:
    plan = ExecutionPlan(
        summary="创建文件",
        operations=[ExecutionOperation("create_text", "docs/new.md", "新内容\n")],
    )
    applier = ExecutionPlanApplier(tmp_path)
    preview = applier.preview(plan)

    result = applier.apply(plan, expected_fingerprint=preview.preview_fingerprint)

    assert result.file_diffs_as_dicts() == preview.file_diffs_as_dicts()
    assert result.preview_fingerprint == preview.preview_fingerprint
    assert read_text_utf8(tmp_path / "docs" / "new.md") == "新内容\n"


def test_applier_rejects_stale_fingerprint_before_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "target.md", "版本一\n")
    plan = ExecutionPlan(
        summary="覆盖文件",
        operations=[ExecutionOperation("overwrite_text", "target.md", "批准内容\n")],
    )
    applier = ExecutionPlanApplier(tmp_path)
    preview = applier.preview(plan)
    write_text_utf8(tmp_path / "target.md", "版本二\n")

    with pytest.raises(StaleExecutionPreviewError, match="重新预览"):
        applier.apply(plan, expected_fingerprint=preview.preview_fingerprint)

    assert read_text_utf8(tmp_path / "target.md") == "版本二\n"


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

    result = apply_plan(tmp_path, plan)

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
        apply_plan(tmp_path, plan)

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
        apply_plan(tmp_path, plan)


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
        apply_plan(tmp_path, plan)

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
            "content_preview": "# 新文件\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("# 新文件\n"),
        },
        {
            "action": "overwrite_text",
            "path": "existing.md",
            "exists": True,
            "content_bytes": len("新内容\n".encode("utf-8")),
            "risk": "overwrite",
            "content_preview": "新内容\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("新内容\n"),
        },
        {
            "action": "append_text",
            "path": "logs/new.md",
            "exists": False,
            "content_bytes": len("追加\n".encode("utf-8")),
            "risk": "append_create",
            "content_preview": "追加\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("追加\n"),
        },
        {
            "action": "append_text",
            "path": "existing.md",
            "exists": True,
            "content_bytes": len("继续追加\n".encode("utf-8")),
            "risk": "append",
            "content_preview": "继续追加\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("继续追加\n"),
        },
    ]
    assert not (tmp_path / "docs" / "new.md").exists()
    assert read_text_utf8(tmp_path / "existing.md") == "旧内容\n"


def test_applier_preview_truncates_content_preview_by_lines(tmp_path) -> None:
    content = "一\n二\n三\n四\n五\n六\n七\n"
    plan = ExecutionPlan(
        summary="按行截断",
        operations=[ExecutionOperation("create_text", "docs/lines.md", content)],
    )

    result = ExecutionPlanApplier(tmp_path).preview(plan)

    preview = result.preview_changes_as_dicts()[0]
    assert preview["content_preview"] == "一\n二\n三\n四\n五\n六\n"
    assert preview["content_preview_truncated"] is True
    assert preview["content_preview_line_count"] == 7
    assert preview["content_preview_char_count"] == len(content)
    assert not (tmp_path / "docs" / "lines.md").exists()


def test_applier_preview_truncates_content_preview_by_characters(tmp_path) -> None:
    content = "中" * 601
    plan = ExecutionPlan(
        summary="按字符截断",
        operations=[ExecutionOperation("create_text", "docs/chars.md", content)],
    )

    result = ExecutionPlanApplier(tmp_path).preview(plan)

    preview = result.preview_changes_as_dicts()[0]
    assert preview["content_preview"] == "中" * 600
    assert preview["content_preview_truncated"] is True
    assert preview["content_preview_line_count"] == 1
    assert preview["content_preview_char_count"] == 601
    assert not (tmp_path / "docs" / "chars.md").exists()


def test_applier_preview_reports_empty_content_preview(tmp_path) -> None:
    plan = ExecutionPlan(
        summary="空内容",
        operations=[ExecutionOperation("append_text", "empty.md", "")],
    )

    result = ExecutionPlanApplier(tmp_path).preview(plan)

    preview = result.preview_changes_as_dicts()[0]
    assert preview["content_preview"] == ""
    assert preview["content_preview_truncated"] is False
    assert preview["content_preview_line_count"] == 0
    assert preview["content_preview_char_count"] == 0


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


@pytest.mark.parametrize("first_action", ["overwrite_text", "append_text"])
def test_applier_rejects_create_after_planned_write_creates_same_target(tmp_path, first_action: str) -> None:
    plan = ExecutionPlan(
        summary="计划内目标冲突",
        operations=[
            ExecutionOperation(first_action, "docs/same.md", "first\n"),
            ExecutionOperation("create_text", "docs/same.md", "second\n"),
        ],
    )

    with pytest.raises(ExecutionPlanError, match="already exists"):
        ExecutionPlanApplier(tmp_path).preview(plan)
    with pytest.raises(ExecutionPlanError, match="already exists"):
        apply_plan(tmp_path, plan)

    assert not (tmp_path / "docs" / "same.md").exists()


def test_applier_rejects_parent_path_that_is_file_before_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "blocker", "not a directory\n")
    plan = ExecutionPlan(
        summary="父路径冲突",
        operations=[
            ExecutionOperation("create_text", "docs/first.md", "first\n"),
            ExecutionOperation("create_text", "blocker/child.md", "child\n"),
        ],
    )

    with pytest.raises(ExecutionPlanError, match="parent path is not a directory"):
        apply_plan(tmp_path, plan)

    assert not (tmp_path / "docs" / "first.md").exists()
    assert read_text_utf8(tmp_path / "blocker") == "not a directory\n"


def test_applier_previews_and_applies_replace_metadata(tmp_path) -> None:
    write_text_utf8(tmp_path / "target.md", "旧内容\n")
    plan = ExecutionPlan("替换", [replace("target.md", "旧内容", "新内容")])
    applier = ExecutionPlanApplier(tmp_path)

    preview = applier.preview(plan)
    result = applier.apply(plan, expected_fingerprint=preview.preview_fingerprint)

    assert preview.preview_changes_as_dicts() == [
        {
            "action": "replace_text",
            "path": "target.md",
            "exists": True,
            "content_bytes": len("新内容".encode("utf-8")),
            "risk": "replace",
            "content_preview": "新内容",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("新内容"),
        }
    ]
    assert result.changes_as_dicts() == [
        {
            "action": "replace_text",
            "path": "target.md",
            "before_exists": True,
            "after_exists": True,
            "bytes_written": len("新内容".encode("utf-8")),
        }
    ]
    assert (tmp_path / "target.md").read_bytes() == "新内容\n".encode("utf-8")


@pytest.mark.parametrize(
    ("original", "old_text", "new_text", "expected"),
    [
        (
            b"\xef\xbb\xbfhead\r\nold\r\ntail",
            "old",
            "new",
            b"\xef\xbb\xbfhead\r\nnew\r\ntail",
        ),
        (b"head\nold\ntail\n", "old", "new", b"head\nnew\ntail\n"),
        (b"head\r\nold\ntail\r", "old", "new", b"head\r\nnew\ntail\r"),
        (b"head-old-tail", "old", "", b"head--tail"),
    ],
)
def test_applier_replace_preserves_unmodified_utf8_bytes(
    tmp_path,
    original: bytes,
    old_text: str,
    new_text: str,
    expected: bytes,
) -> None:
    target = tmp_path / "bytes.txt"
    target.write_bytes(original)

    apply_plan(
        tmp_path,
        ExecutionPlan("字节保真", [replace("bytes.txt", old_text, new_text)]),
    )

    assert target.read_bytes() == expected


def test_applier_prevalidates_all_replacements_before_any_write(tmp_path) -> None:
    write_text_utf8(tmp_path / "target.md", "第一处\n")
    plan = ExecutionPlan(
        "原子预校验",
        [
            replace("target.md", "第一处", "已替换"),
            replace("target.md", "缺失", "不会执行"),
        ],
    )

    with pytest.raises(ExecutionPlanError, match="实际 0 处"):
        apply_plan(tmp_path, plan)

    assert (tmp_path / "target.md").read_text(encoding="utf-8") == "第一处\n"


def test_applier_replace_rejects_non_utf8_without_writing(tmp_path) -> None:
    target = tmp_path / "legacy.txt"
    original = b"\xff\xfe\x00"
    target.write_bytes(original)
    plan = ExecutionPlan("拒绝非 UTF-8", [replace("legacy.txt", "旧", "新")])

    with pytest.raises(ExecutionPlanError, match="不是有效 UTF-8"):
        apply_plan(tmp_path, plan)

    assert target.read_bytes() == original
