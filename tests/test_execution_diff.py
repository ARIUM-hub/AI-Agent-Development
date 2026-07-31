from dev_agent.encoding import write_text_utf8
from dev_agent.execution.diff import ExecutionPlanDiffer
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.execution.validation import ExecutionPlanValidator


def build_diff(tmp_path, operations):
    plan = ExecutionPlan(summary="可读 Diff", operations=operations)
    validator = ExecutionPlanValidator(tmp_path)
    return ExecutionPlanDiffer(tmp_path, validator).build(plan)


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
