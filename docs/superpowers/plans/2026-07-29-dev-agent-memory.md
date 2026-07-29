# 任务历史与检索底座 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现本地任务历史、经验提炼、关键词检索和向量检索接口，为研发助手后续召回历史经验提供可测试底座。

**Architecture:** 本阶段只做本地 JSONL 持久化和确定性检索，不调用真实云端 embedding 或模型 API。历史记录、经验记录、关键词索引和向量索引拆成独立小模块；CLI `history` 只负责展示和查询，不承载业务逻辑。

**Tech Stack:** Python 3.11+、dataclasses、pathlib、json、math、hashlib、pytest、Windows PowerShell、UTF-8 文本读写。

---

## Scope Check

本计划覆盖设计中的“任务历史记录与经验提炼”“关键词 + 向量混合检索接口”和 CLI `history` 基础入口。它不实现真实云端向量模型、不做自动改写项目规则、不接入 Web 控制台，也不把记忆检索接入完整智能体编排循环。

本计划完成后应满足：

- 可以把任务历史追加写入 `.agent/history/tasks.jsonl`，并保持中文可读。
- 可以从任务历史提炼明确经验，写入 `.agent/history/experiences.jsonl`。
- 可以用关键词检索任务和经验。
- 可以用本地 deterministic embedding 接口执行向量检索，后续可替换真实 provider。
- 可以合并关键词和向量结果并去重排序。
- 可以通过 CLI `history` 查看最近历史和搜索历史。

## File Structure

- Create: `src/dev_agent/memory/__init__.py`，导出记忆模块说明。
- Create: `src/dev_agent/memory/models.py`，定义 `TaskRecord`、`ExperienceRecord`、`MemoryHit`。
- Create: `src/dev_agent/memory/store.py`，实现 JSONL 历史读写。
- Create: `src/dev_agent/memory/extract.py`，从任务记录提炼明确经验。
- Create: `src/dev_agent/memory/keyword.py`，实现本地关键词检索。
- Create: `src/dev_agent/memory/vector.py`，实现 deterministic embedding 与内存向量索引。
- Create: `src/dev_agent/memory/retriever.py`，合并关键词和向量召回结果。
- Modify: `src/dev_agent/cli.py`，增加 `history` 子命令。
- Create: `tests/test_memory_store.py`，覆盖历史读写和经验提炼。
- Create: `tests/test_memory_retrieval.py`，覆盖关键词、向量和混合检索。
- Modify: `tests/test_cli.py`，覆盖 CLI `history`。

---

### Task 1: History Models and JSONL Store

**Files:**
- Create: `src/dev_agent/memory/__init__.py`
- Create: `src/dev_agent/memory/models.py`
- Create: `src/dev_agent/memory/store.py`
- Test: `tests/test_memory_store.py`

- [ ] **Step 1: Write failing history store tests**

Create `tests/test_memory_store.py`:

```python
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore


def test_memory_store_appends_and_lists_task_records(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    record = TaskRecord(
        task_id="task-1",
        title="修复 Windows 中文乱码",
        status="passed",
        summary="设置 PowerShell 与子进程 UTF-8 输出。",
        events=["发现 UnicodeDecodeError", "加入 PYTHONIOENCODING"],
        verification=["python -m pytest -v"],
        lessons=["Windows 子进程需要显式 UTF-8 环境。"],
    )

    store.append_task(record)

    loaded = store.list_tasks()
    assert loaded == [record]
    raw = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "修复 Windows 中文乱码" in raw


def test_memory_store_gets_task_by_id(tmp_path) -> None:
    store = MemoryStore(tmp_path)
    store.append_task(TaskRecord(task_id="task-1", title="第一项", status="passed"))
    store.append_task(TaskRecord(task_id="task-2", title="第二项", status="failed"))

    loaded = store.get_task("task-2")

    assert loaded is not None
    assert loaded.title == "第二项"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_memory_store.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.memory`.

- [ ] **Step 3: Implement memory models**

Create `src/dev_agent/memory/__init__.py`:

```python
"""Task history and retrieval helpers."""
```

Create `src/dev_agent/memory/models.py`:

```python
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    title: str
    status: str
    summary: str = ""
    events: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "TaskRecord":
        return cls(
            task_id=str(data["task_id"]),
            title=str(data["title"]),
            status=str(data["status"]),
            summary=str(data.get("summary", "")),
            events=[str(item) for item in data.get("events", [])],
            verification=[str(item) for item in data.get("verification", [])],
            lessons=[str(item) for item in data.get("lessons", [])],
        )


@dataclass(frozen=True)
class ExperienceRecord:
    experience_id: str
    source_task_id: str
    text: str
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ExperienceRecord":
        return cls(
            experience_id=str(data["experience_id"]),
            source_task_id=str(data["source_task_id"]),
            text=str(data["text"]),
            tags=[str(item) for item in data.get("tags", [])],
        )


@dataclass(frozen=True)
class MemoryHit:
    record_id: str
    kind: str
    text: str
    score: float
```

- [ ] **Step 4: Implement JSONL store**

Create `src/dev_agent/memory/store.py`:

```python
from pathlib import Path
import json

from dev_agent.encoding import UTF8
from dev_agent.memory.models import ExperienceRecord, TaskRecord


class MemoryStore:
    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.history_dir = repo_root / ".agent" / "history"
        self.tasks_path = self.history_dir / "tasks.jsonl"
        self.experiences_path = self.history_dir / "experiences.jsonl"

    def append_task(self, record: TaskRecord) -> None:
        self._append_jsonl(self.tasks_path, record.to_dict())

    def list_tasks(self) -> list[TaskRecord]:
        return [TaskRecord.from_dict(item) for item in self._read_jsonl(self.tasks_path)]

    def get_task(self, task_id: str) -> TaskRecord | None:
        for record in self.list_tasks():
            if record.task_id == task_id:
                return record
        return None

    def append_experience(self, record: ExperienceRecord) -> None:
        self._append_jsonl(self.experiences_path, record.to_dict())

    def list_experiences(self) -> list[ExperienceRecord]:
        return [ExperienceRecord.from_dict(item) for item in self._read_jsonl(self.experiences_path)]

    def _append_jsonl(self, path: Path, data: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding=UTF8, newline="\n") as handle:
            handle.write(json.dumps(data, ensure_ascii=False) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict[str, object]]:
        if not path.exists():
            return []
        rows: list[dict[str, object]] = []
        with path.open("r", encoding=UTF8) as handle:
            for line in handle:
                if line.strip():
                    rows.append(json.loads(line))
        return rows
```

- [ ] **Step 5: Run history store tests**

Run:

```powershell
python -m pytest tests/test_memory_store.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit history store**

Run:

```powershell
git add src/dev_agent/memory tests/test_memory_store.py
git commit -m "feat: add task history store"
```

Expected: commit succeeds.

---

### Task 2: Experience Extraction

**Files:**
- Modify: `src/dev_agent/memory/extract.py`
- Modify: `tests/test_memory_store.py`

- [ ] **Step 1: Add failing experience extraction tests**

Append to `tests/test_memory_store.py`:

```python
from dev_agent.memory.extract import extract_experiences


def test_extract_experiences_from_task_lessons() -> None:
    record = TaskRecord(
        task_id="task-1",
        title="修复编码",
        status="passed",
        lessons=["Windows 子进程需要显式 UTF-8 环境。", "提交前必须运行完整测试。"],
    )

    experiences = extract_experiences(record)

    assert [item.text for item in experiences] == [
        "Windows 子进程需要显式 UTF-8 环境。",
        "提交前必须运行完整测试。",
    ]
    assert experiences[0].source_task_id == "task-1"
    assert "修复编码" in experiences[0].tags


def test_extract_experiences_ignores_empty_lessons() -> None:
    record = TaskRecord(task_id="task-1", title="空任务", status="passed", lessons=["", "  "])

    assert extract_experiences(record) == []
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_memory_store.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.memory.extract`.

- [ ] **Step 3: Implement extraction**

Create `src/dev_agent/memory/extract.py`:

```python
from hashlib import sha256

from dev_agent.memory.models import ExperienceRecord, TaskRecord


def extract_experiences(record: TaskRecord) -> list[ExperienceRecord]:
    experiences: list[ExperienceRecord] = []
    for lesson in record.lessons:
        text = lesson.strip()
        if not text:
            continue
        digest = sha256(f"{record.task_id}:{text}".encode("utf-8")).hexdigest()[:16]
        experiences.append(
            ExperienceRecord(
                experience_id=f"exp-{digest}",
                source_task_id=record.task_id,
                text=text,
                tags=[record.title, record.status],
            )
        )
    return experiences
```

- [ ] **Step 4: Run memory store tests**

Run:

```powershell
python -m pytest tests/test_memory_store.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit extraction**

Run:

```powershell
git add src/dev_agent/memory/extract.py tests/test_memory_store.py
git commit -m "feat: extract task lessons into experiences"
```

Expected: commit succeeds.

---

### Task 3: Keyword Retrieval

**Files:**
- Create: `src/dev_agent/memory/keyword.py`
- Test: `tests/test_memory_retrieval.py`

- [ ] **Step 1: Write failing keyword retrieval tests**

Create `tests/test_memory_retrieval.py`:

```python
from dev_agent.memory.keyword import KeywordRetriever
from dev_agent.memory.models import ExperienceRecord, TaskRecord


def test_keyword_retriever_finds_task_by_chinese_terms() -> None:
    retriever = KeywordRetriever(
        tasks=[
            TaskRecord(
                task_id="task-1",
                title="修复 Windows 中文乱码",
                status="passed",
                summary="子进程输出需要 UTF-8。",
            )
        ],
        experiences=[],
    )

    hits = retriever.search("中文 乱码")

    assert len(hits) == 1
    assert hits[0].record_id == "task-1"
    assert hits[0].kind == "task"
    assert hits[0].score > 0


def test_keyword_retriever_finds_experience_by_text() -> None:
    retriever = KeywordRetriever(
        tasks=[],
        experiences=[
            ExperienceRecord(
                experience_id="exp-1",
                source_task_id="task-1",
                text="提交前必须运行完整测试。",
                tags=["验证"],
            )
        ],
    )

    hits = retriever.search("完整测试")

    assert hits[0].record_id == "exp-1"
    assert hits[0].kind == "experience"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_memory_retrieval.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.memory.keyword`.

- [ ] **Step 3: Implement keyword retriever**

Create `src/dev_agent/memory/keyword.py`:

```python
from dev_agent.memory.models import ExperienceRecord, MemoryHit, TaskRecord


def _terms(text: str) -> list[str]:
    return [part.casefold() for part in text.split() if part.strip()]


class KeywordRetriever:
    def __init__(self, tasks: list[TaskRecord], experiences: list[ExperienceRecord]) -> None:
        self.tasks = tasks
        self.experiences = experiences

    def search(self, query: str, limit: int = 5) -> list[MemoryHit]:
        query_terms = _terms(query)
        hits: list[MemoryHit] = []
        for task in self.tasks:
            text = " ".join([task.title, task.summary, *task.events, *task.lessons])
            score = self._score(query_terms, text)
            if score:
                hits.append(MemoryHit(record_id=task.task_id, kind="task", text=text, score=score))
        for experience in self.experiences:
            text = " ".join([experience.text, *experience.tags])
            score = self._score(query_terms, text)
            if score:
                hits.append(
                    MemoryHit(
                        record_id=experience.experience_id,
                        kind="experience",
                        text=text,
                        score=score,
                    )
                )
        return sorted(hits, key=lambda item: item.score, reverse=True)[:limit]

    def _score(self, query_terms: list[str], text: str) -> float:
        haystack = text.casefold()
        return float(sum(1 for term in query_terms if term in haystack))
```

- [ ] **Step 4: Run retrieval tests**

Run:

```powershell
python -m pytest tests/test_memory_retrieval.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit keyword retrieval**

Run:

```powershell
git add src/dev_agent/memory/keyword.py tests/test_memory_retrieval.py
git commit -m "feat: add keyword memory retrieval"
```

Expected: commit succeeds.

---

### Task 4: Deterministic Vector Retrieval Interface

**Files:**
- Create: `src/dev_agent/memory/vector.py`
- Modify: `tests/test_memory_retrieval.py`

- [ ] **Step 1: Add failing vector retrieval tests**

Append to `tests/test_memory_retrieval.py`:

```python
from dev_agent.memory.vector import HashEmbeddingProvider, VectorIndex


def test_vector_index_returns_nearest_text() -> None:
    provider = HashEmbeddingProvider(dimensions=32)
    index = VectorIndex(provider)
    index.add(record_id="exp-1", kind="experience", text="Windows UTF-8 编码修复")
    index.add(record_id="exp-2", kind="experience", text="Git 提交与推送流程")

    hits = index.search("UTF-8 编码", limit=1)

    assert hits[0].record_id == "exp-1"
    assert hits[0].kind == "experience"
    assert hits[0].score > 0
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_memory_retrieval.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.memory.vector`.

- [ ] **Step 3: Implement deterministic vector index**

Create `src/dev_agent/memory/vector.py`:

```python
from dataclasses import dataclass
from hashlib import sha256
import math
import re

from dev_agent.memory.models import MemoryHit


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9_+-]+|[一-鿿]", text.casefold())
    return words or [text.casefold()]


class HashEmbeddingProvider:
    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        length = math.sqrt(sum(value * value for value in vector))
        if not length:
            return vector
        return [value / length for value in vector]


@dataclass(frozen=True)
class _VectorItem:
    record_id: str
    kind: str
    text: str
    vector: list[float]


class VectorIndex:
    def __init__(self, provider: HashEmbeddingProvider) -> None:
        self.provider = provider
        self._items: list[_VectorItem] = []

    def add(self, record_id: str, kind: str, text: str) -> None:
        self._items.append(
            _VectorItem(
                record_id=record_id,
                kind=kind,
                text=text,
                vector=self.provider.embed(text),
            )
        )

    def search(self, query: str, limit: int = 5) -> list[MemoryHit]:
        query_vector = self.provider.embed(query)
        hits = [
            MemoryHit(
                record_id=item.record_id,
                kind=item.kind,
                text=item.text,
                score=_cosine(query_vector, item.vector),
            )
            for item in self._items
        ]
        return [hit for hit in sorted(hits, key=lambda item: item.score, reverse=True)[:limit] if hit.score > 0]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))
```

- [ ] **Step 4: Run retrieval tests**

Run:

```powershell
python -m pytest tests/test_memory_retrieval.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit vector retrieval**

Run:

```powershell
git add src/dev_agent/memory/vector.py tests/test_memory_retrieval.py
git commit -m "feat: add deterministic vector memory retrieval"
```

Expected: commit succeeds.

---

### Task 5: Hybrid Memory Retriever

**Files:**
- Create: `src/dev_agent/memory/retriever.py`
- Modify: `tests/test_memory_retrieval.py`

- [ ] **Step 1: Add failing hybrid retrieval test**

Append to `tests/test_memory_retrieval.py`:

```python
from dev_agent.memory.retriever import MemoryRetriever


def test_memory_retriever_combines_keyword_and_vector_hits_without_duplicates() -> None:
    tasks = [
        TaskRecord(
            task_id="task-1",
            title="修复 Windows 中文乱码",
            status="passed",
            summary="Windows UTF-8 编码修复",
        )
    ]
    experiences = [
        ExperienceRecord(
            experience_id="exp-1",
            source_task_id="task-1",
            text="提交前必须运行完整测试。",
        )
    ]

    hits = MemoryRetriever(tasks, experiences).search("UTF-8 编码 完整测试")

    assert [hit.record_id for hit in hits] == ["task-1", "exp-1"]
    assert hits[0].score >= hits[1].score
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_memory_retrieval.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.memory.retriever`.

- [ ] **Step 3: Implement hybrid retriever**

Create `src/dev_agent/memory/retriever.py`:

```python
from dev_agent.memory.keyword import KeywordRetriever
from dev_agent.memory.models import ExperienceRecord, MemoryHit, TaskRecord
from dev_agent.memory.vector import HashEmbeddingProvider, VectorIndex


class MemoryRetriever:
    def __init__(self, tasks: list[TaskRecord], experiences: list[ExperienceRecord]) -> None:
        self.tasks = tasks
        self.experiences = experiences

    def search(self, query: str, limit: int = 5) -> list[MemoryHit]:
        keyword_hits = KeywordRetriever(self.tasks, self.experiences).search(query, limit=limit)
        vector_index = VectorIndex(HashEmbeddingProvider())
        for task in self.tasks:
            vector_index.add(task.task_id, "task", " ".join([task.title, task.summary, *task.lessons]))
        for experience in self.experiences:
            vector_index.add(experience.experience_id, "experience", " ".join([experience.text, *experience.tags]))
        vector_hits = vector_index.search(query, limit=limit)

        merged: dict[tuple[str, str], MemoryHit] = {}
        for hit in [*keyword_hits, *vector_hits]:
            key = (hit.kind, hit.record_id)
            previous = merged.get(key)
            score = hit.score if previous is None else previous.score + hit.score
            merged[key] = MemoryHit(record_id=hit.record_id, kind=hit.kind, text=hit.text, score=score)
        return sorted(merged.values(), key=lambda item: item.score, reverse=True)[:limit]
```

- [ ] **Step 4: Run retrieval tests**

Run:

```powershell
python -m pytest tests/test_memory_retrieval.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit hybrid retrieval**

Run:

```powershell
git add src/dev_agent/memory/retriever.py tests/test_memory_retrieval.py
git commit -m "feat: add hybrid memory retriever"
```

Expected: commit succeeds.

---

### Task 6: CLI History Command

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing CLI history tests**

Append to `tests/test_cli.py`:

```python
def test_history_lists_task_records(tmp_path: Path) -> None:
    history_dir = tmp_path / ".agent" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "tasks.jsonl").write_text(
        '{"task_id":"task-1","title":"修复中文乱码","status":"passed","summary":"UTF-8 修复","events":[],"verification":[],"lessons":[]}\n',
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "history")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["tasks"][0]["title"] == "修复中文乱码"


def test_history_searches_memory(tmp_path: Path) -> None:
    history_dir = tmp_path / ".agent" / "history"
    history_dir.mkdir(parents=True)
    (history_dir / "tasks.jsonl").write_text(
        '{"task_id":"task-1","title":"修复中文乱码","status":"passed","summary":"UTF-8 修复","events":[],"verification":[],"lessons":["提交前运行完整测试"]}\n',
        encoding="utf-8",
    )

    result = run_cli(tmp_path, "history", "--query", "完整测试")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hits"][0]["record_id"] == "task-1"
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `history` command is not registered.

- [ ] **Step 3: Implement history command**

Modify `src/dev_agent/cli.py`:

```python
from dev_agent.memory.retriever import MemoryRetriever
from dev_agent.memory.store import MemoryStore
```

Add command function:

```python
def history_command(args: Namespace) -> int:
    store = MemoryStore(Path.cwd())
    tasks = store.list_tasks()
    experiences = store.list_experiences()
    if args.query:
        hits = MemoryRetriever(tasks, experiences).search(args.query)
        payload = {"hits": [hit.__dict__ for hit in hits]}
    else:
        payload = {"tasks": [task.to_dict() for task in tasks]}
    sys.stdout.write(_json(payload))
    return 0
```

Register parser:

```python
    history_parser = subparsers.add_parser("history")
    history_parser.add_argument("--query")
    history_parser.set_defaults(handler=history_command)
```

- [ ] **Step 4: Run CLI tests**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: all CLI tests pass.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit CLI history**

Run:

```powershell
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: add history CLI command"
```

Expected: commit succeeds.

---

### Task 7: Final Verification

**Files:**
- Verify: full test suite and CLI smoke commands.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI smoke commands**

Run:

```powershell
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli history
```

Expected: `doctor` outputs JSON with `"ok": true`; `scan` outputs project scan JSON; `history` outputs JSON with a `tasks` list.

- [ ] **Step 3: Inspect Git status**

Run:

```powershell
git status --short
```

Expected: no tracked implementation files remain unstaged.

---

## Self-Review

**Spec coverage:** This plan covers the approved spec sections for task history, explicit experience extraction, keyword retrieval, vector retrieval interface, and CLI `history`. It intentionally leaves real embedding providers, Web console history view, full task orchestration integration, and automatic preference rewriting for later plans.

**Placeholder scan:** No placeholder markers or open-ended implementation steps remain. Each task includes exact files, code, verification commands, and commit commands.

**Type consistency:** `TaskRecord`, `ExperienceRecord`, `MemoryHit`, `MemoryStore`, `KeywordRetriever`, `HashEmbeddingProvider`, `VectorIndex`, and `MemoryRetriever` are introduced before use and reused consistently across tests and implementation.
