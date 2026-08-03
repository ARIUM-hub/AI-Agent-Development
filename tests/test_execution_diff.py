import pytest

from dev_agent.encoding import write_text_utf8
from dev_agent.execution.diff import ExecutionPlanDiffer
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.execution.validation import ExecutionPlanValidator


def build_diff(tmp_path, operations):
    plan = ExecutionPlan(summary="可读 Diff", operations=operations)
    validator = ExecutionPlanValidator(tmp_path)
    return ExecutionPlanDiffer(tmp_path, validator).build(plan)


def replace(path: str, old_text: str, new_text: str) -> ExecutionOperation:
    return ExecutionOperation(
        action="replace_text",
        path=path,
        old_text=old_text,
        new_text=new_text,
    )


def test_diff_builder_renders_added_utf8_file_without_writing(tmp_path) -> None:
    file_diffs, fingerprint = build_diff(
        tmp_path,
        [ExecutionOperation("create_text", "docs/说明.md", "第一行\n第二行\n")],
    )

    assert len(file_diffs) == 1
    assert file_diffs[0].path == "docs/说明.md"
    assert file_diffs[0].status == "added"
    assert "--- /dev/null" in file_diffs[0].diff_text
    assert "+++ b/docs/说明.md" in file_diffs[0].diff_text
    assert "+第一行" in file_diffs[0].diff_text
    assert file_diffs[0].additions == 2
    assert file_diffs[0].deletions == 0
    assert fingerprint.startswith("sha256:")
    assert not (tmp_path / "docs" / "说明.md").exists()


def test_diff_builder_aggregates_operations_for_same_file(tmp_path) -> None:
    write_text_utf8(tmp_path / "notes.md", "旧内容\n")

    file_diffs, _fingerprint = build_diff(
        tmp_path,
        [
            ExecutionOperation("overwrite_text", "notes.md", "新内容\n"),
            ExecutionOperation("append_text", "notes.md", "继续追加\n"),
        ],
    )

    assert len(file_diffs) == 1
    assert file_diffs[0].status == "modified"
    assert "-旧内容" in file_diffs[0].diff_text
    assert "+新内容" in file_diffs[0].diff_text
    assert "+继续追加" in file_diffs[0].diff_text


def test_diff_builder_reports_unchanged_net_content(tmp_path) -> None:
    write_text_utf8(tmp_path / "same.md", "保持不变\n")

    file_diffs, _fingerprint = build_diff(
        tmp_path,
        [ExecutionOperation("overwrite_text", "same.md", "保持不变\n")],
    )

    assert file_diffs[0].status == "unchanged"
    assert file_diffs[0].diff_text == ""


def test_diff_builder_rejects_non_utf8_without_writing(tmp_path) -> None:
    target = tmp_path / "legacy.txt"
    original = b"\xff\xfe\x00"
    target.write_bytes(original)

    with pytest.raises(ExecutionPlanError, match="不是有效 UTF-8"):
        build_diff(
            tmp_path,
            [ExecutionOperation("overwrite_text", "legacy.txt", "新内容\n")],
        )

    assert target.read_bytes() == original


def test_diff_builder_marks_line_endings_and_missing_final_newline(tmp_path) -> None:
    (tmp_path / "line.txt").write_bytes("旧行\r\n".encode("utf-8"))

    file_diffs, _fingerprint = build_diff(
        tmp_path,
        [ExecutionOperation("overwrite_text", "line.txt", "新行")],
    )

    file_diff = file_diffs[0]
    assert file_diff.before_line_ending == "crlf"
    assert file_diff.after_line_ending == "none"
    assert r"\ No newline at end of file" in file_diff.diff_text


def test_diff_builder_truncates_at_two_hard_limits(tmp_path) -> None:
    lines = "".join(f"新增 {index}\n" for index in range(250))
    line_diffs, _fingerprint = build_diff(
        tmp_path,
        [ExecutionOperation("create_text", "many.txt", lines)],
    )
    char_diffs, _fingerprint = build_diff(
        tmp_path,
        [ExecutionOperation("create_text", "long.txt", "中" * 20_100)],
    )

    assert line_diffs[0].truncated is True
    assert line_diffs[0].displayed_line_count == 200
    assert line_diffs[0].diff_line_count > 200
    assert char_diffs[0].truncated is True
    assert char_diffs[0].displayed_char_count == 20_000
    assert char_diffs[0].diff_char_count > 20_000


def test_diff_fingerprint_changes_with_plan_or_file_state(tmp_path) -> None:
    write_text_utf8(tmp_path / "state.md", "版本一\n")
    operations = [ExecutionOperation("append_text", "state.md", "追加\n")]
    _diffs, first = build_diff(tmp_path, operations)
    _diffs, same = build_diff(tmp_path, operations)
    write_text_utf8(tmp_path / "state.md", "版本二\n")
    _diffs, changed_file = build_diff(tmp_path, operations)
    _diffs, changed_plan = build_diff(
        tmp_path,
        [ExecutionOperation("append_text", "state.md", "不同追加\n")],
    )

    assert same == first
    assert changed_file != first
    assert changed_plan != changed_file


def test_diff_builder_applies_consecutive_replacements_to_simulated_content(
    tmp_path,
) -> None:
    write_text_utf8(tmp_path / "notes.md", "甲乙丙\n")

    file_diffs, _fingerprint = build_diff(
        tmp_path,
        [replace("notes.md", "甲乙", "甲丁"), replace("notes.md", "丁丙", "戊丙")],
    )

    assert len(file_diffs) == 1
    assert "-甲乙丙" in file_diffs[0].diff_text
    assert "+甲戊丙" in file_diffs[0].diff_text
    assert (tmp_path / "notes.md").read_text(encoding="utf-8") == "甲乙丙\n"


def test_diff_builder_mixes_create_append_and_replace_in_order(tmp_path) -> None:
    file_diffs, _fingerprint = build_diff(
        tmp_path,
        [
            ExecutionOperation("create_text", "new.md", "开始\n"),
            ExecutionOperation("append_text", "new.md", "旧结尾\n"),
            replace("new.md", "旧结尾", "新结尾"),
        ],
    )

    assert "+新结尾" in file_diffs[0].diff_text
    assert "旧结尾" not in file_diffs[0].diff_text
    assert not (tmp_path / "new.md").exists()


def test_diff_builder_rejects_later_replace_without_writing(tmp_path) -> None:
    write_text_utf8(tmp_path / "target.md", "第一处\n")

    with pytest.raises(ExecutionPlanError, match="实际 0 处"):
        build_diff(
            tmp_path,
            [
                replace("target.md", "第一处", "已替换"),
                replace("target.md", "不存在", "不会执行"),
            ],
        )

    assert (tmp_path / "target.md").read_text(encoding="utf-8") == "第一处\n"


def test_diff_fingerprint_changes_with_replace_fragments(tmp_path) -> None:
    write_text_utf8(tmp_path / "state.md", "旧值\n")
    _diffs, first = build_diff(tmp_path, [replace("state.md", "旧值", "新值")])
    _diffs, changed_old = build_diff(tmp_path, [replace("state.md", "旧", "新值")])
    _diffs, changed_new = build_diff(
        tmp_path,
        [replace("state.md", "旧值", "另一个值")],
    )

    assert first != changed_old
    assert first != changed_new
