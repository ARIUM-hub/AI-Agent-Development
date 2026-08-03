# Readable Execution Diff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为执行计划生成按文件聚合、可截断、带过期指纹的 unified diff，并在 CLI、Web 审批和执行审计中安全展示。

**Architecture:** 将路径与计划校验提取为执行层共享验证器，新增纯内存 `ExecutionPlanDiffer` 模拟最终文件内容并生成 Diff。执行器、运行时、CLI 和 Web API 只传递结构化 Diff 与指纹；Web 使用独立 `diff-view.js` 渲染“文件导航 + 单一 Diff”视图，apply 必须回传并校验预览指纹。

**Tech Stack:** Python 3.11+、标准库 `dataclasses`/`difflib`/`hashlib`/`json`、pytest、原生 JavaScript、Node.js 内建测试、HTML/CSS、Windows PowerShell、UTF-8。

---

## Scope Check

本规格虽然跨执行层、CLI 和 Web，但所有改动围绕同一个 `file_diffs + preview_fingerprint` 契约，不能拆成独立交付而仍保持审批安全。计划按数据契约、纯计算、执行集成、API、安全路由和前端展示顺序推进，每个任务都产生可测试的中间状态。

## File Structure

- Create: `src/dev_agent/execution/validation.py`，集中路径解析、禁止目录和全计划预校验。
- Create: `src/dev_agent/execution/diff.py`，内存模拟、unified diff、统计、截断、换行元数据和 SHA-256 指纹。
- Modify: `src/dev_agent/execution/models.py`，新增 `ExecutionFileDiff` 与结果字段。
- Modify: `src/dev_agent/execution/plan.py`，新增过期预览错误类型。
- Modify: `src/dev_agent/execution/applier.py`，复用验证器，预览和 apply 接入 Diff 与指纹。
- Modify: `src/dev_agent/runtime/models.py`，传递预期指纹与结构化 Diff。
- Modify: `src/dev_agent/runtime/runner.py`，在执行前使用已审批指纹并回传 Diff。
- Modify: `src/dev_agent/cli.py`，保持 JSON 输出并增加稳定字段。
- Modify: `src/dev_agent/web/api.py`，扩展 preview/apply payload 并检查指纹。
- Modify: `src/dev_agent/web/server.py`，读取 apply 指纹并将过期错误映射为 409。
- Create: `src/dev_agent/web/static/diff-view.js`，独立渲染文件导航和当前 Diff。
- Modify: `src/dev_agent/web/static/index.html`，增加预览/审计 Diff 容器并加载脚本。
- Modify: `src/dev_agent/web/static/app.js`，串联 Diff 视图、指纹和 409 状态。
- Modify: `src/dev_agent/web/static/styles.css`，桌面、移动端、可访问性和 Diff 行样式。
- Create: `tests/test_execution_diff.py`，覆盖纯 Diff 计算和指纹。
- Modify: `tests/test_execution_applier.py`，覆盖预览、apply 和过期保护。
- Modify: `tests/test_runtime_runner.py`，覆盖运行时结果透传。
- Modify: `tests/test_cli.py`，覆盖 CLI 稳定 JSON 契约。
- Modify: `tests/test_web_api.py`，覆盖 API 字段、缺失指纹和过期保护。
- Modify: `tests/test_web_server.py`，覆盖 HTTP 400/409、静态资源和 Node 测试入口。
- Create: `tests/web_diff_view.test.mjs`，覆盖 DOM 安全、导航、截断和空状态。

## PowerShell Test Prefix

所有 Python 验证命令从功能工作树根目录运行，并显式绑定当前源码，避免本机可编辑安装指向其他工作树：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
```

### Task 1: Diff Result Contract And Shared Validation

**Files:**
- Modify: `src/dev_agent/execution/models.py:42-70`
- Create: `src/dev_agent/execution/validation.py`
- Modify: `src/dev_agent/execution/applier.py:1-110`
- Modify: `tests/test_execution_applier.py`

- [ ] **Step 1: Write the failing result-contract test**

Add this test to `tests/test_execution_applier.py`:

```python
from dev_agent.execution.models import ExecutionFileDiff, ExecutionResult


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
```

- [ ] **Step 2: Run the contract test and verify RED**

Run:

```powershell
python -m pytest tests/test_execution_applier.py::test_execution_result_serializes_file_diffs -v
```

Expected: collection fails because `ExecutionFileDiff` does not exist.

- [ ] **Step 3: Add the public Diff model and stable result defaults**

Add to `src/dev_agent/execution/models.py` before `ExecutionResult`:

```python
@dataclass(frozen=True)
class ExecutionFileDiff:
    path: str
    status: str
    diff_text: str
    additions: int
    deletions: int
    diff_line_count: int
    diff_char_count: int
    displayed_line_count: int
    displayed_char_count: int
    truncated: bool
    before_line_ending: str
    after_line_ending: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

Extend `ExecutionResult` with:

```python
    file_diffs: list[ExecutionFileDiff] = field(default_factory=list)
    preview_fingerprint: str = ""

    def file_diffs_as_dicts(self) -> list[dict[str, object]]:
        return [file_diff.to_dict() for file_diff in self.file_diffs]
```

- [ ] **Step 4: Extract the existing safety rules without changing behavior**

Create `src/dev_agent/execution/validation.py` with `FORBIDDEN_ROOTS`, `FORBIDDEN_ROOT_NAMES` and this public internal API:

```python
from pathlib import Path

from dev_agent.execution.models import ExecutionPlan, SUPPORTED_ACTIONS
from dev_agent.execution.plan import ExecutionPlanError


FORBIDDEN_ROOTS = {".git", ".worktrees", ".superpowers"}
FORBIDDEN_ROOT_NAMES = {name.casefold() for name in FORBIDDEN_ROOTS}


class ExecutionPlanValidator:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def resolve_target(self, raw_path: str) -> Path:
        if not raw_path.strip():
            raise ExecutionPlanError("path must not be empty")
        relative = Path(raw_path)
        if relative.is_absolute():
            raise ExecutionPlanError(f"path must be relative: {raw_path}")
        target = (self.repo_root / relative).resolve()
        try:
            target.relative_to(self.repo_root)
        except ValueError as exc:
            raise ExecutionPlanError(f"path escapes repository: {raw_path}") from exc
        relative_parts = target.relative_to(self.repo_root).parts
        if any(part.casefold() in FORBIDDEN_ROOT_NAMES for part in relative_parts):
            raise ExecutionPlanError(f"path is not allowed: {raw_path}")
        return target

    def validate(self, plan: ExecutionPlan) -> None:
        planned_files: set[Path] = set()
        for operation in plan.operations:
            if operation.action not in SUPPORTED_ACTIONS:
                raise ExecutionPlanError(f"unsupported action: {operation.action}")
            target = self.resolve_target(operation.path)
            self._validate_parent_directories(target, planned_files)
            if target.exists() and target.is_dir():
                raise ExecutionPlanError(f"path is a directory: {operation.path}")
            if operation.action == "create_text" and (target.exists() or target in planned_files):
                raise ExecutionPlanError(f"path already exists: {operation.path}")
            planned_files.add(target)

    def _validate_parent_directories(self, target: Path, planned_files: set[Path]) -> None:
        for parent in target.parents:
            if parent == self.repo_root:
                return
            if parent.exists() and not parent.is_dir():
                relative = parent.relative_to(self.repo_root)
                raise ExecutionPlanError(f"parent path is not a directory: {relative}")
            if parent in planned_files:
                relative = parent.relative_to(self.repo_root)
                raise ExecutionPlanError(f"parent path is not a directory: {relative}")
```

In `ExecutionPlanApplier.__init__`, construct `self.validator = ExecutionPlanValidator(repo_root)`. Replace `_validate_operations(plan)` with `self.validator.validate(plan)`, replace `_resolve_target(path)` with `self.validator.resolve_target(path)`, and remove the duplicated constants and private validation methods.

- [ ] **Step 5: Run the model and safety regression tests**

Run:

```powershell
python -m pytest tests/test_execution_applier.py tests/test_execution_plan.py -q
```

Expected: all tests pass, including unsafe paths and parent conflicts.

- [ ] **Step 6: Commit the contract and validation refactor**

```powershell
git add -- src/dev_agent/execution/models.py src/dev_agent/execution/validation.py src/dev_agent/execution/applier.py tests/test_execution_applier.py
git commit -m "refactor: share execution plan validation"
```

### Task 2: Pure In-Memory Diff Builder

**Files:**
- Create: `src/dev_agent/execution/diff.py`
- Create: `tests/test_execution_diff.py`

- [ ] **Step 1: Write failing tests for creation, aggregation and fingerprinting**

Create `tests/test_execution_diff.py` with these initial tests:

```python
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
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
python -m pytest tests/test_execution_diff.py -v
```

Expected: collection fails because `dev_agent.execution.diff` does not exist.

- [ ] **Step 3: Implement ordered simulation and basic unified diff**

Create `src/dev_agent/execution/diff.py`. Use these constants and entry point:

```python
from dataclasses import dataclass
from difflib import unified_diff
import hashlib
import json
from pathlib import Path

from dev_agent.encoding import UTF8, read_text_utf8
from dev_agent.execution.models import ExecutionFileDiff, ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError
from dev_agent.execution.validation import ExecutionPlanValidator


DIFF_MAX_LINES = 200
DIFF_MAX_CHARS = 20_000


@dataclass
class _SimulatedFile:
    raw_path: str
    target: Path
    before_exists: bool
    before_content: str
    after_content: str


class ExecutionPlanDiffer:
    def __init__(self, repo_root: Path, validator: ExecutionPlanValidator) -> None:
        self.repo_root = repo_root.resolve()
        self.validator = validator

    def build(self, plan: ExecutionPlan) -> tuple[list[ExecutionFileDiff], str]:
        self.validator.validate(plan)
        files = self._simulate(plan)
        file_diffs = [self._build_file_diff(item) for item in files]
        fingerprint = self._fingerprint(plan, files)
        return file_diffs, fingerprint
```

Add these methods to `ExecutionPlanDiffer`:

```python
    def _simulate(self, plan: ExecutionPlan) -> list[_SimulatedFile]:
        by_target: dict[Path, _SimulatedFile] = {}
        ordered: list[_SimulatedFile] = []
        for operation in plan.operations:
            target = self.validator.resolve_target(operation.path)
            item = by_target.get(target)
            if item is None:
                before_exists = target.exists()
                try:
                    before_content = read_text_utf8(target) if before_exists else ""
                except UnicodeDecodeError as exc:
                    raise ExecutionPlanError(
                        f"文件不是有效 UTF-8：{operation.path}"
                    ) from exc
                item = _SimulatedFile(
                    raw_path=operation.path,
                    target=target,
                    before_exists=before_exists,
                    before_content=before_content,
                    after_content=before_content,
                )
                by_target[target] = item
                ordered.append(item)
            if operation.action in {"create_text", "overwrite_text"}:
                item.after_content = operation.content
            elif operation.action == "append_text":
                item.after_content += operation.content
            else:
                raise ExecutionPlanError(f"unsupported action: {operation.action}")
        return ordered

    def _build_file_diff(self, item: _SimulatedFile) -> ExecutionFileDiff:
        if item.before_content == item.after_content:
            full_diff = ""
        else:
            old_label = f"a/{item.raw_path}" if item.before_exists else "/dev/null"
            new_label = f"b/{item.raw_path}"
            lines = list(
                unified_diff(
                    item.before_content.splitlines(),
                    item.after_content.splitlines(),
                    fromfile=old_label,
                    tofile=new_label,
                    lineterm="",
                )
            )
            full_diff = "\n".join(lines) + ("\n" if lines else "")
        additions = sum(
            1 for line in full_diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        deletions = sum(
            1 for line in full_diff.splitlines()
            if line.startswith("-") and not line.startswith("---")
        )
        status = "added" if not item.before_exists else "modified"
        if item.before_content == item.after_content:
            status = "unchanged"
        return ExecutionFileDiff(
            path=item.raw_path,
            status=status,
            diff_text=full_diff,
            additions=additions,
            deletions=deletions,
            diff_line_count=len(full_diff.splitlines()),
            diff_char_count=len(full_diff),
            displayed_line_count=len(full_diff.splitlines()),
            displayed_char_count=len(full_diff),
            truncated=False,
            before_line_ending=self._line_ending(item.before_content),
            after_line_ending=self._line_ending(item.after_content),
        )

    def _line_ending(self, text: str) -> str:
        if "\r\n" in text and "\n" not in text.replace("\r\n", ""):
            return "crlf"
        if "\r\n" in text or "\r" in text:
            return "mixed"
        if "\n" in text:
            return "lf"
        return "none"

    def _fingerprint(self, plan: ExecutionPlan, files: list[_SimulatedFile]) -> str:
        state = {
            "plan": plan.to_dict(),
            "files": [
                {
                    "path": item.raw_path,
                    "before_exists": item.before_exists,
                    "before_sha256": hashlib.sha256(
                        item.before_content.encode(UTF8)
                    ).hexdigest(),
                    "after_sha256": hashlib.sha256(
                        item.after_content.encode(UTF8)
                    ).hexdigest(),
                }
                for item in files
            ],
        }
        encoded = json.dumps(
            state,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode(UTF8)
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
```

- [ ] **Step 4: Run Diff tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_execution_diff.py -q
```

Expected: 3 tests pass and no target file is created.

- [ ] **Step 5: Commit the pure Diff builder**

```powershell
git add -- src/dev_agent/execution/diff.py tests/test_execution_diff.py
git commit -m "feat: build readable execution diffs"
```

### Task 3: UTF-8, Newline, Truncation And Fingerprint Edges

**Files:**
- Modify: `src/dev_agent/execution/diff.py`
- Modify: `tests/test_execution_diff.py`

本任务明确覆盖非 UTF-8 文件：严格解码失败必须阻止预览与执行，不能用替换字符继续，也不能改变原始字节。每个文件的展示 Diff 最多 200 行或 20,000 字符，任一上限先到即截断，但完整统计保持不变。

- [ ] **Step 1: Add failing edge-case tests**

Append tests that assert these exact behaviors:

```python
import pytest

from dev_agent.execution.plan import ExecutionPlanError


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
    assert "\\ No newline at end of file" in file_diff.diff_text


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
```

- [ ] **Step 2: Run edge tests and verify RED**

Run:

```powershell
python -m pytest tests/test_execution_diff.py -q
```

Expected: basic tests pass; newline marker and both hard-limit assertions fail until helpers are complete.

- [ ] **Step 3: Implement exact newline metadata and bounded display output**

Add `_line_ending(text)` returning only `lf`, `crlf`, `mixed` or `none`. Treat lone carriage returns as `mixed`. Render unified diff from `splitlines(keepends=True)` and, for any body line without a terminator, append a separate `\\ No newline at end of file\n` marker. Normalize all rendered output terminators to LF.

After full output and statistics are computed, apply:

```python
full_lines = full_diff.splitlines(keepends=True)
line_limited = "".join(full_lines[:DIFF_MAX_LINES])
display_text = line_limited[:DIFF_MAX_CHARS]
truncated = display_text != full_diff
```

Set total counts from `full_diff`, display counts from `display_text`, and never append a synthetic truncation line to `diff_text`.

- [ ] **Step 4: Run all Diff tests and existing encoding tests**

Run:

```powershell
python -m pytest tests/test_execution_diff.py tests/test_encoding.py -q
```

Expected: all tests pass; Chinese remains literal UTF-8.

- [ ] **Step 5: Commit edge hardening**

```powershell
git add -- src/dev_agent/execution/diff.py tests/test_execution_diff.py
git commit -m "fix: bound and fingerprint execution diffs"
```

### Task 4: Applier, Runtime And CLI Integration

**Files:**
- Modify: `src/dev_agent/execution/plan.py:4`
- Modify: `src/dev_agent/execution/applier.py:22-68`
- Modify: `src/dev_agent/runtime/models.py:25-45`
- Modify: `src/dev_agent/runtime/runner.py:26-110`
- Modify: `src/dev_agent/cli.py:111-199`
- Modify: `tests/test_execution_applier.py`
- Modify: `tests/test_runtime_runner.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing applier stale-state tests**

Add to `tests/test_execution_applier.py`:

```python
from dev_agent.execution.plan import StaleExecutionPreviewError


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
```

- [ ] **Step 2: Run stale tests and verify RED**

Run:

```powershell
python -m pytest tests/test_execution_applier.py -q
```

Expected: import or signature failure for `StaleExecutionPreviewError` and `expected_fingerprint`.

- [ ] **Step 3: Integrate Diff generation and stale checks into the applier**

Add to `src/dev_agent/execution/plan.py`:

```python
class StaleExecutionPreviewError(ExecutionPlanError):
    pass
```

In `ExecutionPlanApplier.preview()`, call `ExecutionPlanDiffer(self.repo_root, self.validator).build(plan)` and populate `file_diffs` and `preview_fingerprint`.

Change apply to this contract:

```python
def apply(self, plan: ExecutionPlan, *, expected_fingerprint: str) -> ExecutionResult:
    file_diffs, current_fingerprint = ExecutionPlanDiffer(
        self.repo_root,
        self.validator,
    ).build(plan)
    if current_fingerprint != expected_fingerprint:
        raise StaleExecutionPreviewError("文件状态已变化，请重新预览后再执行")
```

Continue with the existing write loop only after the comparison, then include the same `file_diffs` and `current_fingerprint` in the returned `ExecutionResult`. Update direct applier tests to preview first and pass the returned fingerprint.

- [ ] **Step 4: Add failing runtime and CLI payload assertions**

In the existing runtime apply success test, assert `result.file_diffs[0]["path"]` and a `sha256:` fingerprint. In `tests/test_cli.py::test_run_previews_plan_file_without_apply` and the apply success test, add:

```python
assert payload["file_diffs"][0]["path"] == "docs/preview.md"
assert payload["file_diffs"][0]["status"] == "added"
assert payload["preview_fingerprint"].startswith("sha256:")
```

In `test_run_applies_plan_file_and_reports_changes`, use the exact assertion `payload["file_diffs"][0]["path"] == "docs/execution.md"`. Also assert plain dry-run responses use `file_diffs == []` and `preview_fingerprint == ""`.

- [ ] **Step 5: Run runtime and CLI tests and verify RED**

Run:

```powershell
python -m pytest tests/test_runtime_runner.py tests/test_cli.py -q
```

Expected: new payload fields are absent.

- [ ] **Step 6: Propagate the approved preview through runtime and CLI**

Extend `TaskRunOptions` with `expected_preview_fingerprint: str | None = None`. Extend `TaskRunResult` with `file_diffs: list[dict[str, object]]` and `preview_fingerprint: str` defaults.

In `LocalTaskRunner.run()`, keep the `_execution_preview()` result and pass either `options.expected_preview_fingerprint` or that result's fingerprint into `_apply_execution_plan()`. Every success and execution-failure `TaskRunResult` must include `execution_result.file_diffs_as_dicts()` and `execution_result.preview_fingerprint`.

Change CLI `_preview_execution_plan()` to return the whole `ExecutionResult`, not only preview changes. `_preview_payload()` and the final payload must include:

```python
"preview_changes": preview_result.preview_changes_as_dicts(),
"file_diffs": preview_result.file_diffs_as_dicts(),
"preview_fingerprint": preview_result.preview_fingerprint,
```

When CLI applies, pass `preview_result.preview_fingerprint` as `TaskRunOptions.expected_preview_fingerprint`. Keep all output inside the existing JSON document.

- [ ] **Step 7: Run execution, runtime and CLI tests**

Run:

```powershell
python -m pytest tests/test_execution_applier.py tests/test_runtime_runner.py tests/test_cli.py -q
```

Expected: all tests pass and both preview/apply JSON payloads contain stable fields.

- [ ] **Step 8: Commit execution integration**

```powershell
git add -- src/dev_agent/execution/plan.py src/dev_agent/execution/applier.py src/dev_agent/runtime/models.py src/dev_agent/runtime/runner.py src/dev_agent/cli.py tests/test_execution_applier.py tests/test_runtime_runner.py tests/test_cli.py
git commit -m "feat: expose execution diffs in cli"
```

### Task 5: Web API Fingerprint Contract And HTTP 409

**Files:**
- Modify: `src/dev_agent/web/api.py:82-193`
- Modify: `src/dev_agent/web/server.py:33-78`
- Modify: `tests/test_web_api.py:123-215`
- Modify: `tests/test_web_server.py:320-450`

- [ ] **Step 1: Write failing Web API contract tests**

Update the preview test to assert a file Diff and fingerprint. Change apply tests to preview first and pass the returned fingerprint. Add:

```python
from dev_agent.execution.plan import StaleExecutionPreviewError


def test_apply_provider_plan_task_requires_fresh_fingerprint(tmp_path) -> None:
    write_text_utf8(tmp_path / "target.md", "版本一\n")
    response = provider_plan_json(path="target.md", content="批准内容\n")
    preview = preview_provider_plan_task(
        repo_root=tmp_path,
        request_text="预览覆盖",
        fake_response=response,
    )
    write_text_utf8(tmp_path / "target.md", "版本二\n")

    with pytest.raises(StaleExecutionPreviewError, match="重新预览"):
        apply_provider_plan_task(
            repo_root=tmp_path,
            home_dir=tmp_path,
            request_text="确认覆盖",
            fake_response=response,
            preview_fingerprint=preview["preview_fingerprint"],
        )

    assert (tmp_path / "target.md").read_text(encoding="utf-8") == "版本二\n"
    assert not (tmp_path / ".agent").exists()
```

Add a separate test passing `preview_fingerprint=""` and expect `ValueError("preview_fingerprint is required")`.

- [ ] **Step 2: Run Web API tests and verify RED**

Run:

```powershell
python -m pytest tests/test_web_api.py -q
```

Expected: preview fields and apply parameter are missing.

- [ ] **Step 3: Implement API fields and pre-run stale validation**

Extend `_provider_plan_payload()` with:

```python
"file_diffs": preview_result.file_diffs_as_dicts(),
"preview_fingerprint": preview_result.preview_fingerprint,
```

Change `apply_provider_plan_task()` to require `preview_fingerprint: str`. Reject an empty value with `ValueError("preview_fingerprint is required")`. Call `_provider_preview()` before constructing `LocalTaskRunner`; compare the current preview fingerprint with the supplied value and raise `StaleExecutionPreviewError("文件状态已变化，请重新预览后再执行")` on mismatch. Pass the supplied value into `TaskRunOptions.expected_preview_fingerprint`.

Return `file_diffs: []` and `preview_fingerprint: ""` from `run_dry_run_task()`.

- [ ] **Step 4: Add failing HTTP route tests for required and stale fingerprints**

Modify the successful route test to call preview first, then include its fingerprint in the apply request. Add a stale route test that previews an `overwrite_text` plan, changes the target file, and applies with the old fingerprint:

```python
assert status == HTTPStatus.CONFLICT
assert payload["ok"] is False
assert "重新预览" in payload["error"]
assert (tmp_path / "target.md").read_text(encoding="utf-8") == "版本二\n"
```

Add a missing-fingerprint route assertion for `HTTPStatus.BAD_REQUEST`.

- [ ] **Step 5: Map stale preview errors to HTTP 409**

Import `StaleExecutionPreviewError` in `src/dev_agent/web/server.py`. Pass `str(body.get("preview_fingerprint", ""))` into apply. Add this handler before the existing `ValueError` handler:

```python
except StaleExecutionPreviewError as exc:
    self._send_json(HTTPStatus.CONFLICT, {"ok": False, "error": str(exc)})
```

- [ ] **Step 6: Run API and route tests**

Run:

```powershell
python -m pytest tests/test_web_api.py tests/test_web_server.py -q
```

Expected: preview is side-effect free, missing fingerprint returns 400, stale fingerprint returns 409, and fresh apply succeeds.

- [ ] **Step 7: Commit the Web safety contract**

```powershell
git add -- src/dev_agent/web/api.py src/dev_agent/web/server.py tests/test_web_api.py tests/test_web_server.py
git commit -m "feat: require fresh web diff previews"
```

### Task 6: Navigable Web Diff View

**Files:**
- Create: `src/dev_agent/web/static/diff-view.js`
- Modify: `src/dev_agent/web/static/index.html:69-77`
- Modify: `src/dev_agent/web/static/app.js:489-821`
- Modify: `src/dev_agent/web/static/styles.css:500-850`
- Create: `tests/web_diff_view.test.mjs`
- Modify: `tests/test_web_server.py:199-310`

- [ ] **Step 1: Create a failing Node behavior test**

Create `tests/web_diff_view.test.mjs` with this complete fake DOM and behavior suite:

```javascript
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(
  new URL("../src/dev_agent/web/static/diff-view.js", import.meta.url),
  "utf8",
);

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.className = "";
    this.textContent = "";
    this.attributes = new Map();
    this.listeners = new Map();
    this.type = "";
  }

  set innerHTML(_value) {
    throw new Error("动态内容不得通过 innerHTML 渲染");
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = [...children];
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }
}

const findAll = (root, tagName) => [
  ...(root.tagName === tagName ? [root] : []),
  ...root.children.flatMap((child) => findAll(child, tagName)),
];

const elementText = (root) => [
  root.textContent,
  ...root.children.map(elementText),
].join(" ");

const sandbox = {
  document: { createElement: (tagName) => new FakeElement(tagName) },
  window: {},
};
vm.runInNewContext(source, sandbox);
const api = sandbox.window.DevAgentDiffView;

const payloadWithTwoChangedFiles = () => ({
  file_diffs: [
    {
      path: "first.md",
      status: "modified",
      diff_text: "-第一版\n+第二版\n",
      additions: 1,
      deletions: 1,
      diff_line_count: 2,
      displayed_line_count: 2,
      truncated: false,
      before_line_ending: "lf",
      after_line_ending: "lf",
    },
    {
      path: "large.md",
      status: "modified",
      diff_text: "+截断内容\n",
      additions: 485,
      deletions: 1,
      diff_line_count: 486,
      displayed_line_count: 200,
      truncated: true,
      before_line_ending: "crlf",
      after_line_ending: "lf",
    },
  ],
});

test("renders safe file navigation and selects the first changed file", () => {
  const root = new FakeElement("div");
  api.renderExecutionDiffs(root, {
    file_diffs: [
      { path: "same.md", status: "unchanged", diff_text: "" },
      {
        path: '<img src=x onerror="alert(1)">',
        status: "modified",
        diff_text: "-旧内容\n+新内容\n",
        additions: 1,
        deletions: 1,
        diff_line_count: 2,
        displayed_line_count: 2,
        truncated: false,
        before_line_ending: "crlf",
        after_line_ending: "lf",
      },
    ],
  });

  assert.match(elementText(root), /<img src=x onerror="alert\(1\)">/);
  assert.match(elementText(root), /-旧内容/);
  assert.match(elementText(root), /CRLF → LF/);
  const buttons = findAll(root, "button");
  assert.equal(buttons[1].getAttribute("aria-selected"), "true");
});

test("switches files and announces truncation", () => {
  const root = new FakeElement("div");
  api.renderExecutionDiffs(root, payloadWithTwoChangedFiles());
  const buttons = findAll(root, "button");

  buttons[1].listeners.get("click")();

  assert.equal(buttons[1].getAttribute("aria-selected"), "true");
  assert.match(elementText(root), /已显示 200\/486 行，内容已截断/);
});

test("renders a readable empty state for malformed payloads", () => {
  const root = new FakeElement("div");

  api.renderExecutionDiffs(root, { file_diffs: "invalid" });

  assert.match(elementText(root), /没有可显示的文件 Diff/);
});
```

- [ ] **Step 2: Run the Node test and verify RED**

Run:

```powershell
node --test tests/web_diff_view.test.mjs
```

Expected: failure because `diff-view.js` does not exist.

- [ ] **Step 3: Implement the standalone safe renderer**

Create `src/dev_agent/web/static/diff-view.js` as an IIFE assigning one API:

```javascript
(() => {
  const appendText = (parent, tagName, className, text) => {
    const element = document.createElement(tagName);
    element.className = className;
    element.textContent = text;
    parent.appendChild(element);
    return element;
  };

  const renderExecutionDiffs = (root, payload) => {
    root.replaceChildren();
    const diffs = Array.isArray(payload?.file_diffs) ? payload.file_diffs : [];
    if (diffs.length === 0) {
      appendText(root, "div", "diff-empty-state", "没有可显示的文件 Diff。");
      return;
    }
    let selectedIndex = diffs.findIndex((item) => item?.status !== "unchanged");
    if (selectedIndex < 0) selectedIndex = 0;
    const shell = document.createElement("div");
    shell.className = "diff-browser";
    const navigation = document.createElement("div");
    navigation.className = "diff-file-navigation";
    navigation.setAttribute("role", "tablist");
    const panel = document.createElement("div");
    panel.className = "diff-current-panel";

    const renderCurrent = () => {
      panel.replaceChildren();
      const current = diffs[selectedIndex] || {};
      appendText(panel, "h4", "diff-current-path", current.path || "未命名路径");
      if (current.truncated === true) {
        appendText(
          panel,
          "div",
          "diff-truncation-note",
          `已显示 ${current.displayed_line_count || 0}/${current.diff_line_count || 0} 行，内容已截断`,
        );
      }
      appendText(panel, "pre", "execution-diff", current.diff_text || "没有净变更。");
    };

    const buttons = diffs.map((item, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "diff-file-button";
      button.textContent = `${item.path || "未命名路径"}  +${item.additions || 0} -${item.deletions || 0}`;
      button.addEventListener("click", () => {
        selectedIndex = index;
        buttons.forEach((entry, entryIndex) => {
          entry.setAttribute("aria-selected", String(entryIndex === selectedIndex));
        });
        renderCurrent();
      });
      navigation.appendChild(button);
      return button;
    });
    buttons.forEach((button, index) => {
      button.setAttribute("aria-selected", String(index === selectedIndex));
    });
    renderCurrent();
    shell.append(navigation, panel);
    root.appendChild(shell);
  };

  window.DevAgentDiffView = { renderExecutionDiffs };
})();
```

Extend `renderCurrent()` to show status labels and `before_line_ending → after_line_ending` using explicit label maps. Keep every dynamic value in `textContent`.

- [ ] **Step 4: Run Node tests and verify GREEN**

Run:

```powershell
node --test tests/web_diff_view.test.mjs
```

Expected: all Diff view behavior tests pass.

- [ ] **Step 5: Wire containers, fingerprint and stale-state handling**

In `index.html`, add `provider-preview-diffs` after preview cards and `provider-audit-diffs` after audit cards. Load `/static/diff-view.js` before `/static/app.js`.

In `server.py`, serve `/static/diff-view.js` with `text/javascript; charset=utf-8`.

In `app.js`:

- Render preview diffs after `renderProviderPreviewCards(payload)`.
- Send `lastProviderPreview.preview_fingerprint` in apply JSON.
- Render audit diffs after `renderProviderAuditCards(payload)`.
- Clear both Diff roots on reset, preview failure and apply failure.
- Attach `response.status` to errors created by `postJson()`.
- On status 409, set status text to “文件状态已变化，请重新预览”, clear `lastProviderPreview`, disable confirmation and preserve the error in the `role="alert"` node.

Use this error shape:

```javascript
if (!response.ok) {
  const error = new Error(body.error || "请求失败，请检查本地服务是否仍在运行。");
  error.status = response.status;
  throw error;
}
```

- [ ] **Step 6: Add responsive and accessible CSS**

Add selectors with these minimum behaviors:

```css
.diff-browser {
  display: grid;
  grid-template-columns: minmax(12rem, 0.34fr) minmax(0, 1fr);
  gap: 1rem;
}

.diff-file-navigation {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-width: 0;
}

.diff-file-button {
  min-height: 44px;
  overflow-wrap: anywhere;
  text-align: left;
}

.diff-file-button[aria-selected="true"] {
  border-color: var(--moss);
  background: var(--moss-soft);
}

.execution-diff {
  overflow-x: auto;
  white-space: pre;
  tab-size: 2;
}

.diff-truncation-note {
  position: sticky;
  top: 0;
  z-index: 1;
}

@media (max-width: 860px) {
  .diff-browser { grid-template-columns: minmax(0, 1fr); }
  .diff-file-navigation {
    flex-direction: row;
    overflow-x: auto;
    max-width: 100%;
  }
  .diff-file-button { flex: 0 0 auto; }
}
```

Use existing moss/terracotta CSS variables and focus styles; do not introduce a new visual theme.

- [ ] **Step 7: Add static integration assertions and pytest Node invocation**

In `tests/test_web_server.py`, assert both new containers, the new script route, key CSS selectors, `preview_fingerprint` in `app.js`, and `textContent` in `diff-view.js`. Add a pytest test that runs:

```python
completed = subprocess.run(
    [node, "--test", str(Path(__file__).with_name("web_diff_view.test.mjs"))],
    check=False,
    capture_output=True,
    text=True,
    encoding="utf-8",
)
assert completed.returncode == 0, completed.stdout + completed.stderr
```

- [ ] **Step 8: Run Web static and behavior tests**

Run:

```powershell
node --check src/dev_agent/web/static/diff-view.js
node --check src/dev_agent/web/static/app.js
node --test tests/web_diff_view.test.mjs
python -m pytest tests/test_web_server.py -q
```

Expected: JavaScript syntax is valid, Node behavior tests pass, and all Web server tests pass.

- [ ] **Step 9: Commit navigable Diff UI**

```powershell
git add -- src/dev_agent/web/static/diff-view.js src/dev_agent/web/static/index.html src/dev_agent/web/static/app.js src/dev_agent/web/static/styles.css src/dev_agent/web/server.py tests/web_diff_view.test.mjs tests/test_web_server.py
git commit -m "feat: render navigable execution diffs"
```

### Task 7: Full Verification And Browser Acceptance

**Files:**
- Verify only; modify implementation or tests only if a verification step exposes a concrete defect.

- [ ] **Step 1: Run the focused safety suite**

```powershell
python -m pytest tests/test_execution_diff.py tests/test_execution_applier.py tests/test_runtime_runner.py tests/test_cli.py tests/test_web_api.py tests/test_web_server.py -q
```

Expected: all focused tests pass with no skipped Python safety tests.

- [ ] **Step 2: Run the complete automated suite**

```powershell
python -m pytest -q
```

Expected: all tests pass; record the exact count in the completion report.

- [ ] **Step 3: Run syntax, service and whitespace checks**

```powershell
node --check src/dev_agent/web/static/app.js
node --check src/dev_agent/web/static/diff-view.js
python -m dev_agent.cli serve --port 0 --check
git diff --check
git status --short --branch
```

Expected: both syntax checks exit 0, serve JSON contains `"ok": true`, `git diff --check` has no errors, and the worktree is clean after all commits.

- [ ] **Step 4: Perform local browser acceptance without Provider calls**

Start one local server process only:

```powershell
python -m dev_agent.cli serve --port 8765
```

Use a local fake provider plan with at least three files, one truncated Diff and one unchanged file. Verify:

- desktop shows left file navigation and one current Diff panel;
- default selection is the first changed file;
- switching files updates `aria-selected` and visible Diff;
- truncation warning appears above the Diff;
- after changing a target file between preview and apply, the UI receives 409, disables confirmation and requires re-preview;
- 375px layout has horizontal file buttons, 44px targets, no page-level horizontal overflow and only the Diff body scrolls horizontally;
- malicious path and Diff text render literally;
- browser console has no errors.

Stop the local server and confirm port 8765 is free.

- [ ] **Step 5: Review final scope and history**

Run:

```powershell
git log --oneline codex/dev-agent-web-history-cards..HEAD
git diff --stat codex/dev-agent-web-history-cards...HEAD
```

Expected: only the readable Diff specification, plan, execution/API changes, Web renderer and tests are present; no real Provider configuration, dependency or unrelated refactor appears.

## Execution Notes

- Keep execution single-session and low-concurrency. Do not start subagents unless the user explicitly selects the subagent-driven option.
- 测试和浏览器验收不调用真实模型供应商，只使用本地 fake provider plan。
- Do not batch retry failed network or Provider requests.
- Preserve direct Chinese text in UTF-8; do not replace it with Unicode escape sequences.
- If any RED test fails for a reason different from the expected missing behavior, stop and diagnose before implementing.
