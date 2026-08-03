# Web Tool Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把当前仓库升级为一个单用户、本地优先的网页工具型智能体，支持聊天、多轮历史、网页搜索、本地文件读取、知识库上传检索，以及可见的工具执行记录。

**Architecture:** 保留现有 `dev_agent` 包结构，在 `web` 层从 `http.server` 切换到 `FastAPI`，新增 `chat` 和 `storage` 模块承接会话编排与 SQLite 持久化，在 `tools` 中扩展搜索、文件、知识库三类工具。编排层优先使用规则驱动的工具选择，保证第一版行为稳定、可调试，再由现有 provider 负责最终回答生成。

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLite, FAISS, httpx, BeautifulSoup4, pytest, 原生 HTML/CSS/JavaScript

---

## File Structure

### Create

- `src/dev_agent/chat/__init__.py`
- `src/dev_agent/chat/models.py`
- `src/dev_agent/chat/prompts.py`
- `src/dev_agent/chat/planner.py`
- `src/dev_agent/chat/orchestrator.py`
- `src/dev_agent/chat/session_service.py`
- `src/dev_agent/storage/__init__.py`
- `src/dev_agent/storage/models.py`
- `src/dev_agent/storage/sqlite_store.py`
- `src/dev_agent/tools/registry.py`
- `src/dev_agent/tools/file_reader.py`
- `src/dev_agent/tools/web_search.py`
- `src/dev_agent/tools/knowledge_search.py`
- `tests/test_storage_sqlite_store.py`
- `tests/test_tools_file_reader.py`
- `tests/test_tools_web_search.py`
- `tests/test_tools_knowledge_search.py`
- `tests/test_chat_orchestrator.py`
- `tests/test_web_chat_api.py`
- `tests/web_chat_shell.test.mjs`

### Modify

- `pyproject.toml`
- `src/dev_agent/encoding.py`
- `src/dev_agent/memory/models.py`
- `src/dev_agent/memory/vector.py`
- `src/dev_agent/web/api.py`
- `src/dev_agent/web/server.py`
- `src/dev_agent/web/static/index.html`
- `src/dev_agent/web/static/app.js`
- `src/dev_agent/web/static/styles.css`
- `tests/test_web_server.py`

## Task 1: 切换到 FastAPI Web 壳层

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/dev_agent/web/server.py`
- Modify: `tests/test_web_server.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: 先写 FastAPI app 工厂的失败测试**

```python
from fastapi.testclient import TestClient

from dev_agent.web.server import build_app


def test_build_app_serves_index_and_health(tmp_path) -> None:
    app = build_app(repo_root=tmp_path, home_dir=tmp_path)
    client = TestClient(app)

    health = client.get("/api/health")
    index = client.get("/")

    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert index.status_code == 200
    assert "研发助手控制台" in index.text
```

- [ ] **Step 2: 运行测试，确认当前实现失败**

Run: `python -m pytest tests/test_web_server.py::test_build_app_serves_index_and_health -v`  
Expected: FAIL，提示 `cannot import name 'build_app'` 或 `AttributeError`

- [ ] **Step 3: 最小实现 FastAPI app 工厂并保留静态资源服务**

```python
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dev_agent.web.api import build_health_payload


STATIC_DIR = Path(__file__).with_name("static")


def build_app(repo_root: Path, home_dir: Path) -> FastAPI:
    app = FastAPI(title="dev-agent-web", version="0.1.0")
    app.state.repo_root = repo_root
    app.state.home_dir = home_dir
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return build_health_payload(repo_root)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    return app
```

```toml
[project]
dependencies = [
  "PyYAML>=6.0.2",
  "fastapi>=0.115.0",
  "uvicorn>=0.30.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "httpx>=0.27.0",
]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_web_server.py::test_build_app_serves_index_and_health -v`  
Expected: PASS

- [ ] **Step 5: 提交这一小步**

```bash
git add pyproject.toml src/dev_agent/web/server.py tests/test_web_server.py
git commit -m "feat: add fastapi web app shell"
```

## Task 2: 建立 SQLite 会话与消息存储

**Files:**
- Create: `src/dev_agent/storage/models.py`
- Create: `src/dev_agent/storage/sqlite_store.py`
- Create: `tests/test_storage_sqlite_store.py`
- Test: `tests/test_storage_sqlite_store.py`

- [ ] **Step 1: 先写会话和消息持久化失败测试**

```python
from dev_agent.storage.sqlite_store import SQLiteStore


def test_sqlite_store_creates_session_and_messages(tmp_path) -> None:
    store = SQLiteStore(tmp_path / ".agent" / "chat.db")
    session = store.create_session(title="项目问答")
    store.append_message(session.session_id, role="user", content="你好")
    store.append_message(session.session_id, role="assistant", content="你好，我可以帮你查看项目。")

    sessions = store.list_sessions()
    messages = store.list_messages(session.session_id)

    assert sessions[0].title == "项目问答"
    assert [item.role for item in messages] == ["user", "assistant"]
```

- [ ] **Step 2: 运行测试，确认 `SQLiteStore` 尚不存在**

Run: `python -m pytest tests/test_storage_sqlite_store.py::test_sqlite_store_creates_session_and_messages -v`  
Expected: FAIL，提示 `ModuleNotFoundError: No module named 'dev_agent.storage'`

- [ ] **Step 3: 写最小可用的 SQLite 数据模型与存储实现**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatSession:
    session_id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChatMessage:
    message_id: str
    session_id: str
    role: str
    content: str
    tool_name: str | None = None
    tool_payload_json: str | None = None
    created_at: str = ""
```

```python
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
import uuid

from dev_agent.storage.models import ChatMessage, ChatSession


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def create_session(self, title: str) -> ChatSession:
        now = datetime.now(UTC).isoformat()
        session = ChatSession(
            session_id=uuid.uuid4().hex,
            title=title,
            created_at=now,
            updated_at=now,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "insert into chat_sessions(session_id, title, created_at, updated_at) values (?, ?, ?, ?)",
                (session.session_id, session.title, session.created_at, session.updated_at),
            )
        return session

    def append_message(self, session_id: str, role: str, content: str) -> ChatMessage:
        message = ChatMessage(
            message_id=uuid.uuid4().hex,
            session_id=session_id,
            role=role,
            content=content,
            created_at=datetime.now(UTC).isoformat(),
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "insert into chat_messages(message_id, session_id, role, content, tool_name, tool_payload_json, created_at) values (?, ?, ?, ?, ?, ?, ?)",
                (message.message_id, message.session_id, message.role, message.content, message.tool_name, message.tool_payload_json, message.created_at),
            )
            conn.execute(
                "update chat_sessions set updated_at = ? where session_id = ?",
                (message.created_at, session_id),
            )
        return message

    def list_sessions(self) -> list[ChatSession]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "select session_id, title, created_at, updated_at from chat_sessions order by updated_at desc"
            ).fetchall()
        return [ChatSession(*row) for row in rows]

    def list_messages(self, session_id: str) -> list[ChatMessage]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "select message_id, session_id, role, content, tool_name, tool_payload_json, created_at from chat_messages where session_id = ? order by created_at asc",
                (session_id,),
            ).fetchall()
        return [ChatMessage(*row) for row in rows]

    def _initialize(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(
                '''
                create table if not exists chat_sessions (
                    session_id text primary key,
                    title text not null,
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists chat_messages (
                    message_id text primary key,
                    session_id text not null,
                    role text not null,
                    content text not null,
                    tool_name text null,
                    tool_payload_json text null,
                    created_at text not null,
                    foreign key(session_id) references chat_sessions(session_id)
                );
                '''
            )
```

- [ ] **Step 4: 跑存储测试确认通过**

Run: `python -m pytest tests/test_storage_sqlite_store.py -v`  
Expected: PASS

- [ ] **Step 5: 提交这一小步**

```bash
git add src/dev_agent/storage tests/test_storage_sqlite_store.py
git commit -m "feat: add sqlite chat persistence"
```

## Task 3: 增加编码安全的文件读取工具与工具注册表

**Files:**
- Modify: `src/dev_agent/encoding.py`
- Create: `src/dev_agent/tools/registry.py`
- Create: `src/dev_agent/tools/file_reader.py`
- Create: `tests/test_tools_file_reader.py`
- Test: `tests/test_tools_file_reader.py`

- [ ] **Step 1: 先写白名单和中文编码读取的失败测试**

```python
from pathlib import Path

import pytest

from dev_agent.tools.file_reader import FileReaderTool


def test_file_reader_reads_gb18030_text_inside_workspace(tmp_path) -> None:
    source = tmp_path / "docs" / "说明.txt"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes("你好，工具型智能体".encode("gb18030"))

    tool = FileReaderTool(allowed_roots=[tmp_path])
    result = tool.run(path=str(source))

    assert result.ok is True
    assert "工具型智能体" in result.payload["content"]


def test_file_reader_rejects_path_outside_workspace(tmp_path) -> None:
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("不应访问", encoding="utf-8")

    tool = FileReaderTool(allowed_roots=[tmp_path])

    with pytest.raises(ValueError, match="白名单目录"):
        tool.run(path=str(outside))
```

- [ ] **Step 2: 运行测试，确认工具文件尚未实现**

Run: `python -m pytest tests/test_tools_file_reader.py -v`  
Expected: FAIL，提示 `ModuleNotFoundError`

- [ ] **Step 3: 先补编码探测函数，再实现只读文件工具和注册接口**

```python
from pathlib import Path


UTF8 = "utf-8"
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5")


def read_text_auto(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    last_error: UnicodeDecodeError | None = None
    for encoding in TEXT_ENCODINGS:
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            last_error = exc
    raise UnicodeDecodeError(
        last_error.encoding if last_error else "unknown",
        last_error.object if last_error else b"",
        last_error.start if last_error else 0,
        last_error.end if last_error else 1,
        "文件编码无法安全解析",
    )
```

```python
from dataclasses import dataclass
from pathlib import Path

from dev_agent.encoding import read_text_auto


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    payload: dict[str, object]


class FileReaderTool:
    name = "file_reader"

    def __init__(self, allowed_roots: list[Path]) -> None:
        self.allowed_roots = [root.resolve() for root in allowed_roots]

    def run(self, path: str) -> ToolResult:
        target = Path(path).resolve()
        if not any(root == target or root in target.parents for root in self.allowed_roots):
            raise ValueError("目标路径不在允许的白名单目录内")
        content, encoding = read_text_auto(target)
        return ToolResult(
            ok=True,
            payload={
                "path": str(target),
                "encoding": encoding,
                "content": content,
            },
        )
```

```python
from collections.abc import Callable


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Callable[..., object]] = {}

    def register(self, name: str, tool: Callable[..., object]) -> None:
        self._tools[name] = tool

    def get(self, name: str) -> Callable[..., object]:
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)
```

- [ ] **Step 4: 跑文件工具测试确认通过**

Run: `python -m pytest tests/test_tools_file_reader.py -v`  
Expected: PASS

- [ ] **Step 5: 提交这一小步**

```bash
git add src/dev_agent/encoding.py src/dev_agent/tools/registry.py src/dev_agent/tools/file_reader.py tests/test_tools_file_reader.py
git commit -m "feat: add safe file reader tool"
```

## Task 4: 接入知识库索引与网页搜索工具

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/dev_agent/memory/models.py`
- Modify: `src/dev_agent/memory/vector.py`
- Create: `src/dev_agent/tools/knowledge_search.py`
- Create: `src/dev_agent/tools/web_search.py`
- Create: `tests/test_tools_knowledge_search.py`
- Create: `tests/test_tools_web_search.py`
- Test: `tests/test_tools_knowledge_search.py`
- Test: `tests/test_tools_web_search.py`

- [ ] **Step 1: 先写知识库与搜索工具的失败测试**

```python
from dev_agent.tools.knowledge_search import KnowledgeSearchTool


def test_knowledge_search_returns_relevant_chunks(tmp_path) -> None:
    tool = KnowledgeSearchTool(index_root=tmp_path / ".agent" / "kb")
    document = tmp_path / "架构说明.md"
    document.write_text("# 架构\n\n系统使用 FastAPI 和 SQLite。", encoding="utf-8")

    tool.ingest(document_path=document)
    result = tool.run(query="项目使用什么 Web 框架？")

    assert result.ok is True
    assert result.payload["hits"][0]["text"].startswith("# 架构")
```

```python
import httpx

from dev_agent.tools.web_search import WebSearchTool


def test_web_search_extracts_titles_from_search_results(monkeypatch) -> None:
    html = """
    <html><body>
      <a class="result__a" href="https://example.com/doc">FastAPI 文档</a>
    </body></html>
    """

    def fake_get(self, url, params=None, headers=None, timeout=None):
        return httpx.Response(200, text=html)

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    tool = WebSearchTool()
    result = tool.run(query="FastAPI 文档")

    assert result.ok is True
    assert result.payload["results"][0]["title"] == "FastAPI 文档"
```

- [ ] **Step 2: 运行测试，确认两个工具都还不存在**

Run: `python -m pytest tests/test_tools_knowledge_search.py tests/test_tools_web_search.py -v`  
Expected: FAIL，提示缺少模块或类

- [ ] **Step 3: 实现最小可用知识库索引和单次搜索工具**

```toml
[project]
dependencies = [
  "PyYAML>=6.0.2",
  "fastapi>=0.115.0",
  "uvicorn>=0.30.0",
  "faiss-cpu>=1.8.0",
  "beautifulsoup4>=4.12.3",
  "httpx>=0.27.0",
  "python-multipart>=0.0.9",
]
```

```python
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class KnowledgeHit:
    record_id: str
    text: str
    score: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
```

```python
from pathlib import Path
import json

import faiss
import numpy as np

from dev_agent.memory.vector import HashEmbeddingProvider
from dev_agent.tools.file_reader import ToolResult


class KnowledgeSearchTool:
    name = "knowledge_search"

    def __init__(self, index_root: Path) -> None:
        self.index_root = index_root
        self.index_root.mkdir(parents=True, exist_ok=True)
        self._embedder = HashEmbeddingProvider(dimensions=64)
        self._index_path = self.index_root / "docs.faiss"
        self._meta_path = self.index_root / "docs.json"

    def ingest(self, document_path: Path) -> None:
        text = document_path.read_text(encoding="utf-8")
        chunks = [chunk.strip() for chunk in text.split("\n\n") if chunk.strip()]
        vectors = np.array([self._embedder.embed(chunk) for chunk in chunks], dtype="float32")
        index = faiss.IndexFlatIP(vectors.shape[1])
        index.add(vectors)
        faiss.write_index(index, str(self._index_path))
        self._meta_path.write_text(
            json.dumps([{"record_id": f"{document_path.name}-{i}", "text": chunk} for i, chunk in enumerate(chunks)], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def run(self, query: str) -> ToolResult:
        index = faiss.read_index(str(self._index_path))
        rows = json.loads(self._meta_path.read_text(encoding="utf-8"))
        query_vector = np.array([self._embedder.embed(query)], dtype="float32")
        scores, ids = index.search(query_vector, 3)
        hits = [
            {"record_id": rows[item_id]["record_id"], "text": rows[item_id]["text"], "score": float(scores[0][offset])}
            for offset, item_id in enumerate(ids[0])
            if item_id >= 0
        ]
        return ToolResult(ok=True, payload={"hits": hits})
```

```python
from bs4 import BeautifulSoup
import httpx

from dev_agent.tools.file_reader import ToolResult


class WebSearchTool:
    name = "web_search"

    def __init__(self, endpoint: str = "https://duckduckgo.com/html/") -> None:
        self.endpoint = endpoint

    def run(self, query: str) -> ToolResult:
        with httpx.Client(follow_redirects=True) as client:
            response = client.get(
                self.endpoint,
                params={"q": query},
                headers={"User-Agent": "dev-agent/0.1"},
                timeout=10.0,
            )
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        results = []
        for link in soup.select(".result__a")[:3]:
            results.append({"title": link.get_text(" ", strip=True), "url": link.get("href", "")})
        return ToolResult(ok=True, payload={"results": results})
```

- [ ] **Step 4: 运行工具测试确认通过**

Run: `python -m pytest tests/test_tools_knowledge_search.py tests/test_tools_web_search.py -v`  
Expected: PASS

- [ ] **Step 5: 提交这一小步**

```bash
git add pyproject.toml src/dev_agent/memory src/dev_agent/tools/knowledge_search.py src/dev_agent/tools/web_search.py tests/test_tools_knowledge_search.py tests/test_tools_web_search.py
git commit -m "feat: add knowledge and web search tools"
```

## Task 5: 编排聊天流程并暴露聊天 API

**Files:**
- Create: `src/dev_agent/chat/models.py`
- Create: `src/dev_agent/chat/prompts.py`
- Create: `src/dev_agent/chat/planner.py`
- Create: `src/dev_agent/chat/orchestrator.py`
- Create: `src/dev_agent/chat/session_service.py`
- Modify: `src/dev_agent/web/api.py`
- Modify: `src/dev_agent/web/server.py`
- Create: `tests/test_chat_orchestrator.py`
- Create: `tests/test_web_chat_api.py`
- Test: `tests/test_chat_orchestrator.py`
- Test: `tests/test_web_chat_api.py`

- [ ] **Step 1: 先写聊天编排和 HTTP 接口的失败测试**

```python
from pathlib import Path

from dev_agent.chat.orchestrator import ChatOrchestrator
from dev_agent.providers.base import FakeProvider
from dev_agent.storage.sqlite_store import SQLiteStore
from dev_agent.tools.file_reader import FileReaderTool
from dev_agent.tools.registry import ToolRegistry


def test_chat_orchestrator_records_tool_trace(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("# 示例项目", encoding="utf-8")
    store = SQLiteStore(tmp_path / ".agent" / "chat.db")
    tools = ToolRegistry()
    tools.register("file_reader", FileReaderTool([tmp_path]))
    orchestrator = ChatOrchestrator(
        store=store,
        provider=FakeProvider(name="fake-chat", responses=["这是 README 摘要。"]),
        tools=tools,
        repo_root=tmp_path,
    )

    reply = orchestrator.reply(session_id=None, user_message="请读取 README.md 并总结")

    assert reply.tool_traces[0]["tool_name"] == "file_reader"
    assert "README.md" in reply.tool_traces[0]["payload"]["path"]
```

```python
from fastapi.testclient import TestClient

from dev_agent.web.server import build_app


def test_chat_api_returns_assistant_message_and_traces(tmp_path) -> None:
    app = build_app(repo_root=tmp_path, home_dir=tmp_path)
    client = TestClient(app)

    response = client.post("/api/chat", json={"message": "你好"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant"]["role"] == "assistant"
    assert "tool_traces" in payload
```

- [ ] **Step 2: 运行测试，确认缺少聊天模块与路由**

Run: `python -m pytest tests/test_chat_orchestrator.py tests/test_web_chat_api.py -v`  
Expected: FAIL，提示缺少 `dev_agent.chat` 或 `/api/chat` 返回 404

- [ ] **Step 3: 实现最小聊天编排、会话服务和 `/api/chat`**

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ChatReply:
    session_id: str
    assistant_text: str
    tool_traces: list[dict[str, object]]


@dataclass(frozen=True)
class ChatServices:
    orchestrator: object
    session_service: object
    knowledge_tool: object
```

```python
from pathlib import Path

from dev_agent.chat.models import ChatReply


class ChatOrchestrator:
    def __init__(self, store, provider, tools, repo_root: Path) -> None:
        self.store = store
        self.provider = provider
        self.tools = tools
        self.repo_root = repo_root

    def reply(self, session_id: str | None, user_message: str) -> ChatReply:
        session = self.store.create_session(title=user_message[:20]) if session_id is None else None
        active_session_id = session.session_id if session else session_id
        self.store.append_message(active_session_id, "user", user_message)

        tool_traces: list[dict[str, object]] = []
        prompt_parts = [f"用户问题：{user_message}"]
        if "README" in user_message.upper():
            result = self.tools.get("file_reader").run(path=str(self.repo_root / "README.md"))
            tool_traces.append({"tool_name": "file_reader", "payload": result.payload})
            prompt_parts.append(f"工具结果：{result.payload['content']}")

        response = self.provider.complete(type("Request", (), {"prompt": "\n".join(prompt_parts), "system_prompt": None, "task_id": active_session_id})())
        self.store.append_message(active_session_id, "assistant", response.text)
        return ChatReply(session_id=active_session_id, assistant_text=response.text, tool_traces=tool_traces)
```

```python
from fastapi import Request

from dev_agent.chat.models import ChatServices
from dev_agent.chat.orchestrator import ChatOrchestrator
from dev_agent.chat.session_service import SessionService
from dev_agent.providers.base import FakeProvider
from dev_agent.tools.knowledge_search import KnowledgeSearchTool
from dev_agent.storage.sqlite_store import SQLiteStore
from dev_agent.tools.file_reader import FileReaderTool
from dev_agent.tools.registry import ToolRegistry


def build_chat_services(repo_root):
    store = SQLiteStore(repo_root / ".agent" / "chat.db")
    tools = ToolRegistry()
    tools.register("file_reader", FileReaderTool([repo_root]))
    knowledge_tool = KnowledgeSearchTool(repo_root / ".agent" / "kb")
    tools.register("knowledge_search", knowledge_tool)
    provider = FakeProvider(name="fake-chat", responses=["你好，我已经收到请求。"])
    session_service = SessionService(store)
    orchestrator = ChatOrchestrator(store=store, provider=provider, tools=tools, repo_root=repo_root)
    return ChatServices(
        orchestrator=orchestrator,
        session_service=session_service,
        knowledge_tool=knowledge_tool,
    )


def register_routes(app) -> None:
    @app.post("/api/chat")
    def chat(request: Request, body: dict[str, object]) -> dict[str, object]:
        services = build_chat_services(request.app.state.repo_root)
        reply = services.orchestrator.reply(
            session_id=body.get("session_id"),
            user_message=str(body.get("message", "")),
        )
        return {
            "session_id": reply.session_id,
            "assistant": {"role": "assistant", "content": reply.assistant_text},
            "tool_traces": reply.tool_traces,
        }
```

- [ ] **Step 4: 跑编排和聊天接口测试确认通过**

Run: `python -m pytest tests/test_chat_orchestrator.py tests/test_web_chat_api.py -v`  
Expected: PASS

- [ ] **Step 5: 提交这一小步**

```bash
git add src/dev_agent/chat src/dev_agent/web/api.py tests/test_chat_orchestrator.py tests/test_web_chat_api.py
git commit -m "feat: add chat orchestration and api"
```

## Task 6: 补全会话列表、文档上传和工具可见前端

**Files:**
- Modify: `src/dev_agent/web/api.py`
- Modify: `src/dev_agent/web/server.py`
- Modify: `src/dev_agent/web/static/index.html`
- Modify: `src/dev_agent/web/static/app.js`
- Modify: `src/dev_agent/web/static/styles.css`
- Create: `tests/web_chat_shell.test.mjs`
- Test: `tests/web_chat_shell.test.mjs`

- [ ] **Step 1: 先写页面结构和关键交互的失败测试**

```javascript
import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

test("chat shell contains sidebar composer and tool traces", async () => {
  const html = await readFile("src/dev_agent/web/static/index.html", "utf8");

  assert.match(html, /id="chat-session-list"/);
  assert.match(html, /id="chat-messages"/);
  assert.match(html, /id="chat-form"/);
  assert.match(html, /id="tool-trace-list"/);
  assert.match(html, /id="upload-form"/);
});
```

- [ ] **Step 2: 运行前端测试，确认现有页面还是控制台布局**

Run: `node --test tests/web_chat_shell.test.mjs`  
Expected: FAIL，提示找不到 `chat-session-list` 等节点

- [ ] **Step 3: 用轻量网页聊天壳替换现有控制台，并接好会话/上传/聊天请求**

```html
<main class="chat-app">
  <aside class="chat-sidebar">
    <header>
      <p class="eyebrow">Local Dev Agent</p>
      <h1>工具型个人智能体</h1>
      <button id="new-session-button" type="button">新建会话</button>
    </header>
    <section>
      <h2>历史会话</h2>
      <div id="chat-session-list"></div>
    </section>
    <section>
      <h2>知识库</h2>
      <form id="upload-form">
        <input id="upload-file" name="file" type="file" accept=".txt,.md" required />
        <button type="submit">上传文档</button>
      </form>
    </section>
  </aside>
  <section class="chat-main">
    <div id="chat-messages" class="chat-messages" aria-live="polite"></div>
    <form id="chat-form" class="chat-composer">
      <textarea id="chat-input" name="message" required placeholder="输入问题，例如：读取 README.md 并结合知识库解释启动流程"></textarea>
      <button type="submit">发送</button>
    </form>
  </section>
  <aside class="chat-trace-panel">
    <h2>工具记录</h2>
    <div id="tool-trace-list"></div>
    <p id="chat-error" class="danger" hidden></p>
  </aside>
</main>
```

```javascript
let activeSessionId = null;

const postJson = async (path, payload) => {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json();
  if (!response.ok) {
    throw new Error(body.error || "请求失败");
  }
  return body;
};

async function submitChat(event) {
  event.preventDefault();
  const input = document.getElementById("chat-input");
  const payload = await postJson("/api/chat", {
    session_id: activeSessionId,
    message: input.value,
  });
  activeSessionId = payload.session_id;
  renderAssistant(payload.assistant.content);
  renderToolTraces(payload.tool_traces);
  input.value = "";
}

async function submitUpload(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const body = new FormData(form);
  const response = await fetch("/api/documents", { method: "POST", body });
  if (!response.ok) {
    throw new Error("上传失败");
  }
}

document.getElementById("chat-form").addEventListener("submit", submitChat);
document.getElementById("upload-form").addEventListener("submit", submitUpload);
```

```css
.chat-app {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 320px;
  min-height: 100vh;
  background: linear-gradient(160deg, #f4efe7 0%, #fffaf3 42%, #e8f1ee 100%);
}

.chat-messages {
  padding: 24px;
  overflow-y: auto;
}

.chat-composer {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 120px;
  gap: 12px;
  padding: 20px 24px 24px;
}

.trace-card {
  border: 1px solid #d9d2c7;
  border-radius: 16px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.72);
}
```

- [ ] **Step 4: 跑前端测试确认页面骨架就绪**

Run: `node --test tests/web_chat_shell.test.mjs`  
Expected: PASS

- [ ] **Step 5: 提交这一小步**

```bash
git add src/dev_agent/web/static/index.html src/dev_agent/web/static/app.js src/dev_agent/web/static/styles.css tests/web_chat_shell.test.mjs
git commit -m "feat: add chat shell ui"
```

## Task 7: 打通上传、会话列表和端到端验证

**Files:**
- Modify: `src/dev_agent/chat/orchestrator.py`
- Modify: `src/dev_agent/chat/session_service.py`
- Modify: `src/dev_agent/tools/knowledge_search.py`
- Modify: `src/dev_agent/web/api.py`
- Modify: `src/dev_agent/web/server.py`
- Modify: `src/dev_agent/web/static/app.js`
- Modify: `tests/test_web_chat_api.py`
- Modify: `tests/test_chat_orchestrator.py`
- Test: `tests/test_web_chat_api.py`
- Test: `tests/test_chat_orchestrator.py`

- [ ] **Step 1: 先写上传文档和会话列表的失败测试**

```python
from fastapi.testclient import TestClient

from dev_agent.web.server import build_app


def test_upload_document_and_list_sessions(tmp_path) -> None:
    app = build_app(repo_root=tmp_path, home_dir=tmp_path)
    client = TestClient(app)

    upload = client.post(
        "/api/documents",
        files={"file": ("guide.md", "# 使用说明\n\n知识库入口。".encode("utf-8"), "text/markdown")},
    )
    chat = client.post("/api/chat", json={"message": "请结合知识库回答"})
    sessions = client.get("/api/sessions")

    assert upload.status_code == 200
    assert chat.status_code == 200
    assert any(item["title"] for item in sessions.json()["sessions"])
```

- [ ] **Step 2: 运行测试，确认上传和会话列表路由还未实现**

Run: `python -m pytest tests/test_web_chat_api.py::test_upload_document_and_list_sessions -v`  
Expected: FAIL，提示 `/api/documents` 或 `/api/sessions` 返回 404

- [ ] **Step 3: 实现上传、会话列表和知识库参与对话的最小闭环**

```python
from pathlib import Path
import shutil


class SessionService:
    def __init__(self, store) -> None:
        self.store = store

    def list_sessions(self) -> list[dict[str, object]]:
        return [
            {
                "session_id": session.session_id,
                "title": session.title,
                "updated_at": session.updated_at,
            }
            for session in self.store.list_sessions()
        ]

    def list_messages(self, session_id: str) -> list[dict[str, object]]:
        return [
            {
                "message_id": message.message_id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in self.store.list_messages(session_id)
        ]


def save_uploaded_document(repo_root: Path, filename: str, source) -> Path:
    target = repo_root / ".agent" / "documents" / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        shutil.copyfileobj(source, handle)
    return target
```

```python
from fastapi import Request, UploadFile


@app.get("/api/sessions")
def list_sessions(request: Request) -> dict[str, object]:
    services = build_chat_services(request.app.state.repo_root)
    return {"sessions": services.session_service.list_sessions()}


@app.get("/api/sessions/{session_id}/messages")
def list_messages(request: Request, session_id: str) -> dict[str, object]:
    services = build_chat_services(request.app.state.repo_root)
    return {"messages": services.session_service.list_messages(session_id)}


@app.post("/api/documents")
def upload_document(request: Request, file: UploadFile) -> dict[str, object]:
    services = build_chat_services(request.app.state.repo_root)
    saved = save_uploaded_document(request.app.state.repo_root, file.filename, file.file)
    services.knowledge_tool.ingest(saved)
    return {"ok": True, "filename": file.filename, "path": str(saved)}
```

```python
if "知识库" in user_message or "文档" in user_message:
    result = self.tools.get("knowledge_search").run(query=user_message)
    tool_traces.append({"tool_name": "knowledge_search", "payload": result.payload})
    prompt_parts.append(f"知识库结果：{result.payload['hits']}")
```

```javascript
async function loadSessions() {
  const payload = await fetch("/api/sessions").then((response) => response.json());
  renderSessionList(payload.sessions);
}

async function selectSession(sessionId) {
  activeSessionId = sessionId;
  const payload = await fetch(`/api/sessions/${sessionId}/messages`).then((response) => response.json());
  renderMessageList(payload.messages);
}
```

- [ ] **Step 4: 运行端到端接口测试和主要单元测试**

Run: `python -m pytest tests/test_chat_orchestrator.py tests/test_web_chat_api.py tests/test_storage_sqlite_store.py -v`  
Expected: PASS

- [ ] **Step 5: 跑一次完整验证并提交**

Run: `python -m pytest`  
Expected: PASS，所有 Python 测试通过

Run: `node --test tests/web_chat_shell.test.mjs`  
Expected: PASS

```bash
git add src/dev_agent/chat src/dev_agent/tools/knowledge_search.py src/dev_agent/web/api.py src/dev_agent/web/server.py tests/test_chat_orchestrator.py tests/test_web_chat_api.py
git commit -m "feat: complete web tool agent mvp"
```

## Dependency Install Notes

在国内网络环境下先配置安装源，再执行依赖安装：

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pip install -U pip -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m pip install -e .[dev] -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## Verification Checklist

- `python -m pytest tests/test_web_server.py -v`
- `python -m pytest tests/test_storage_sqlite_store.py -v`
- `python -m pytest tests/test_tools_file_reader.py tests/test_tools_knowledge_search.py tests/test_tools_web_search.py -v`
- `python -m pytest tests/test_chat_orchestrator.py tests/test_web_chat_api.py -v`
- `python -m pytest`
- `node --test tests/web_chat_shell.test.mjs`
