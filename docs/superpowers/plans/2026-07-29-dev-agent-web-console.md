# 本地 Web 控制台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个 Windows 优先、无新增运行时依赖的本地 Web 控制台，用于查看环境上下文、任务历史，并通过 dry-run 提交本地任务。

**Architecture:** 本阶段新增 `dev_agent.web` 包，使用 Python 标准库 `http.server` 暴露本地 JSON API 和静态前端资源。Web API 只调用现有 scan/history/runtime dry-run 能力，不连接真实模型、不做后台并发轮询、不执行 Git push；前端为静态 HTML/CSS/JS，默认从同源 `/api/*` 拉取数据。

**Tech Stack:** Python 3.11+、http.server、json、pathlib、argparse、pytest、HTML/CSS/JavaScript、Windows PowerShell、UTF-8 文本读写。

---

## Scope Check

本计划覆盖设计中的“本地 Web 控制台”第一条可运行纵切片：启动本地服务、查看健康状态、查看仓库上下文、查看历史任务、提交 fake provider dry-run 任务，并展示任务计划结果。

本计划不实现真实云端模型调用、审批队列、实时日志流、自动代码修改、Git commit/push、复杂权限系统或多用户远程访问。服务默认绑定 `127.0.0.1`，避免意外暴露到局域网。

完成后应满足：

- `python -m dev_agent.cli serve --port 0 --check` 可以创建本地服务对象并用于测试。
- `/api/health` 返回版本、工作目录、UTF-8 编码和 Web 能力。
- `/api/context` 返回项目扫描、Git 状态、规则摘要和建议验证命令。
- `/api/history` 返回已有任务历史。
- `/api/run` 只接受显式 `fake_response`，执行 dry-run 并写入任务历史。
- `/`、`/static/styles.css`、`/static/app.js` 返回可用控制台页面。
- 全量测试通过，并通过 CLI smoke 命令验证 `serve` 已注册。

## File Structure

- Create: `src/dev_agent/web/__init__.py`，Web 包说明。
- Create: `src/dev_agent/web/api.py`，纯函数 API 处理层，负责 health/context/history/run 的数据结构。
- Create: `src/dev_agent/web/server.py`，标准库 HTTP handler 与本地 server 创建逻辑。
- Create: `src/dev_agent/web/static/index.html`，控制台页面结构。
- Create: `src/dev_agent/web/static/styles.css`，响应式界面、颜色、排版与状态样式。
- Create: `src/dev_agent/web/static/app.js`，前端数据加载和 dry-run 表单提交。
- Modify: `src/dev_agent/cli.py`，新增 `serve` 命令和 doctor Web 能力标记。
- Create: `tests/test_web_api.py`，覆盖纯函数 API。
- Create: `tests/test_web_server.py`，覆盖 HTTP 路由与静态资源。
- Modify: `tests/test_cli.py`，覆盖 CLI `serve` 注册和 doctor capabilities。

---

### Task 1: Web API Functions

**Files:**
- Create: `src/dev_agent/web/__init__.py`
- Create: `src/dev_agent/web/api.py`
- Test: `tests/test_web_api.py`

- [ ] **Step 1: Write failing Web API tests**

Create `tests/test_web_api.py`:

```python
import subprocess

from dev_agent.encoding import write_text_utf8
from dev_agent.memory.models import TaskRecord
from dev_agent.memory.store import MemoryStore
from dev_agent.web.api import build_context_payload, build_health_payload, build_history_payload, run_dry_run_task


def git(cwd, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def test_build_health_payload_reports_local_web_capability(tmp_path) -> None:
    payload = build_health_payload(tmp_path)

    assert payload["ok"] is True
    assert payload["encoding"] == "UTF-8"
    assert payload["cwd"] == str(tmp_path)
    assert payload["capabilities"]["web_console"] is True
    assert payload["capabilities"]["dry_run_only"] is True


def test_build_context_payload_combines_scan_git_rules_and_verification(tmp_path) -> None:
    write_text_utf8(tmp_path / ".agent" / "rules.md", "# 项目规则\n\n所有文件使用 UTF-8。\n")
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    git(tmp_path, "init")
    git(tmp_path, "config", "user.name", "tester")
    git(tmp_path, "config", "user.email", "tester@example.com")
    write_text_utf8(tmp_path / "README.md", "# 示例\n")
    git(tmp_path, "add", "README.md")
    git(tmp_path, "commit", "-m", "initial")

    payload = build_context_payload(tmp_path, tmp_path)

    assert payload["scan"]["languages"] == ["python"]
    assert payload["git"]["recent_log"]
    assert payload["rules_text"] == "# 项目规则\n\n所有文件使用 UTF-8。\n"
    assert payload["verification_steps"] == [{"name": "test", "command": ["python", "-m", "pytest"]}]


def test_build_history_payload_lists_tasks(tmp_path) -> None:
    MemoryStore(tmp_path).append_task(
        TaskRecord(
            task_id="task-1",
            title="实现 Web 控制台",
            status="passed",
            summary="已完成 dry-run 页面",
        )
    )

    payload = build_history_payload(tmp_path)

    assert payload["tasks"][0]["task_id"] == "task-1"
    assert payload["tasks"][0]["title"] == "实现 Web 控制台"


def test_run_dry_run_task_requires_fake_response_and_records_history(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")

    payload = run_dry_run_task(
        repo_root=tmp_path,
        home_dir=tmp_path,
        request_text="生成实现计划",
        fake_response="计划：先看上下文，再跑测试。",
    )

    assert payload["plan_text"] == "计划：先看上下文，再跑测试。"
    assert payload["dry_run"] is True
    assert payload["verification_steps"] == [["python", "-m", "pytest"]]
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "生成实现计划" in history
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pytest tests/test_web_api.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.web`.

- [ ] **Step 3: Implement Web API functions**

Create `src/dev_agent/web/__init__.py`:

```python
"""Local Web console support."""
```

Create `src/dev_agent/web/api.py`:

```python
from pathlib import Path

from dev_agent import __version__
from dev_agent.config.loader import load_agent_context
from dev_agent.encoding import UTF8
from dev_agent.memory.store import MemoryStore
from dev_agent.project.scanner import scan_project
from dev_agent.providers.base import FakeProvider
from dev_agent.runtime.models import TaskRunOptions
from dev_agent.runtime.runner import LocalTaskRunner
from dev_agent.tools.git import GitReader
from dev_agent.verification.planner import build_verification_plan


def build_health_payload(repo_root: Path) -> dict[str, object]:
    return {
        "ok": True,
        "version": __version__,
        "cwd": str(repo_root),
        "encoding": UTF8,
        "capabilities": {
            "web_console": True,
            "dry_run_only": True,
            "real_model_calls": False,
        },
    }


def build_context_payload(repo_root: Path, home_dir: Path) -> dict[str, object]:
    agent_context = load_agent_context(repo_root, home_dir)
    scan = scan_project(repo_root)
    git = GitReader(repo_root).snapshot()
    verification_plan = build_verification_plan(agent_context.commands, scan)
    return {
        "project": {
            "name": agent_context.project.name,
            "tech_stack": agent_context.project.tech_stack,
        },
        "preferences": {
            "language": agent_context.preferences.language,
            "approval_mode": agent_context.preferences.approval_mode,
        },
        "rules_text": agent_context.rules_text,
        "scan": {
            "root": str(scan.root),
            "languages": scan.languages,
            "markers": scan.markers,
            "suggested_commands": {
                "test": scan.suggested_commands.test,
                "lint": scan.suggested_commands.lint,
                "typecheck": scan.suggested_commands.typecheck,
                "build": scan.suggested_commands.build,
            },
        },
        "git": {
            "status": git.status,
            "diff_stat": git.diff_stat,
            "recent_log": git.recent_log,
        },
        "verification_steps": [
            {"name": step.name, "command": step.command}
            for step in verification_plan.steps
        ],
    }


def build_history_payload(repo_root: Path) -> dict[str, object]:
    tasks = MemoryStore(repo_root).list_tasks()
    return {"tasks": [task.to_dict() for task in tasks]}


def run_dry_run_task(repo_root: Path, home_dir: Path, request_text: str, fake_response: str) -> dict[str, object]:
    if not request_text.strip():
        raise ValueError("request_text is required")
    if not fake_response.strip():
        raise ValueError("fake_response is required for Web dry-run")
    runner = LocalTaskRunner(
        repo_root=repo_root,
        home_dir=home_dir,
        provider=FakeProvider(name="fake-web", responses=[fake_response]),
    )
    result = runner.run(
        request_text,
        TaskRunOptions(dry_run=True, run_verification=False),
    )
    return {
        "task_id": result.task_id,
        "plan_text": result.plan_text,
        "dry_run": result.dry_run,
        "memory_hit_count": result.memory_hit_count,
        "verification_steps": result.verification_steps,
        "events": result.events,
    }
```

- [ ] **Step 4: Run Web API tests**

Run:

```powershell
python -m pytest tests/test_web_api.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit Web API functions**

Run:

```powershell
git add src/dev_agent/web tests/test_web_api.py
git commit -m "feat: add local web API payloads"
```

Expected: commit succeeds.

---

### Task 2: HTTP Server Routes

**Files:**
- Create: `src/dev_agent/web/server.py`
- Test: `tests/test_web_server.py`

- [ ] **Step 1: Write failing HTTP route tests**

Create `tests/test_web_server.py`:

```python
import json
from http import HTTPStatus
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dev_agent.encoding import write_text_utf8
from dev_agent.web.server import create_server


def start_server(tmp_path):
    server = create_server(repo_root=tmp_path, home_dir=tmp_path, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def get_json(url):
    with urlopen(url, timeout=5) as response:
        return response.status, response.headers["Content-Type"], json.loads(response.read().decode("utf-8"))


def post_json(url, payload):
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, response.headers["Content-Type"], json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        return exc.code, exc.headers["Content-Type"], json.loads(exc.read().decode("utf-8"))


def test_health_route_returns_json(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/health")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["capabilities"]["web_console"] is True


def test_context_route_returns_project_context(tmp_path) -> None:
    write_text_utf8(tmp_path / "pyproject.toml", "[project]\nname = \"sample\"\n")
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/context")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["scan"]["languages"] == ["python"]


def test_history_route_returns_json(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = get_json(f"{base_url}/api/history")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "application/json; charset=utf-8"
    assert payload["tasks"] == []


def test_run_route_rejects_missing_fake_response(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, payload = post_json(f"{base_url}/api/run", {"request": "生成计划"})
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.BAD_REQUEST
    assert content_type == "application/json; charset=utf-8"
    assert payload["ok"] is False
    assert "fake_response" in payload["error"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_web_server.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `dev_agent.web.server`.

- [ ] **Step 3: Implement HTTP server routes**

Create `src/dev_agent/web/server.py`:

```python
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
from pathlib import Path
from urllib.parse import urlparse

from dev_agent.web.api import build_context_payload, build_health_payload, build_history_payload, run_dry_run_task


STATIC_DIR = Path(__file__).with_name("static")


class DevAgentHttpHandler(SimpleHTTPRequestHandler):
    repo_root: Path
    home_dir: Path

    def do_GET(self) -> None:
        self.handle_request()

    def do_POST(self) -> None:
        self.handle_request()

    def log_message(self, format: str, *args: object) -> None:
        return None

    def handle_request(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self._send_json(HTTPStatus.OK, build_health_payload(self.repo_root))
            elif path == "/api/context":
                self._send_json(HTTPStatus.OK, build_context_payload(self.repo_root, self.home_dir))
            elif path == "/api/history":
                self._send_json(HTTPStatus.OK, build_history_payload(self.repo_root))
            elif path == "/api/run" and self.command == "POST":
                body = self._read_json_body()
                payload = run_dry_run_task(
                    repo_root=self.repo_root,
                    home_dir=self.home_dir,
                    request_text=str(body.get("request", "")),
                    fake_response=str(body.get("fake_response", "")),
                )
                self._send_json(HTTPStatus.OK, payload)
            elif path == "/":
                self._send_static("index.html", "text/html; charset=utf-8")
            elif path == "/static/styles.css":
                self._send_static("styles.css", "text/css; charset=utf-8")
            elif path == "/static/app.js":
                self._send_static("app.js", "text/javascript; charset=utf-8")
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def _read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static(self, filename: str, content_type: str) -> None:
        body = (STATIC_DIR / filename).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(repo_root: Path, home_dir: Path, host: str = "127.0.0.1", port: int = 8765) -> HTTPServer:
    class BoundHandler(DevAgentHttpHandler):
        pass

    BoundHandler.repo_root = repo_root
    BoundHandler.home_dir = home_dir
    return HTTPServer((host, port), BoundHandler)
```

- [ ] **Step 4: Run HTTP server tests**

Run:

```powershell
python -m pytest tests/test_web_server.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit HTTP server routes**

Run:

```powershell
git add src/dev_agent/web/server.py tests/test_web_server.py
git commit -m "feat: serve local web API routes"
```

Expected: commit succeeds.

---

### Task 3: Static Web Console UI

**Files:**
- Create: `src/dev_agent/web/static/index.html`
- Create: `src/dev_agent/web/static/styles.css`
- Create: `src/dev_agent/web/static/app.js`
- Modify: `tests/test_web_server.py`

- [ ] **Step 1: Add failing static asset assertions**

Append to `tests/test_web_server.py`:

```python
from urllib.request import urlopen


def get_text(url):
    with urlopen(url, timeout=5) as response:
        return response.status, response.headers["Content-Type"], response.read().decode("utf-8")


def test_static_index_route_returns_html(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        status, content_type, body = get_text(f"{base_url}/")
    finally:
        server.shutdown()
        server.server_close()

    assert status == HTTPStatus.OK
    assert content_type == "text/html; charset=utf-8"
    assert "研发助手控制台" in body


def test_static_assets_include_console_interactions(tmp_path) -> None:
    server, base_url = start_server(tmp_path)
    try:
        css_status, css_type, css_body = get_text(f"{base_url}/static/styles.css")
        js_status, js_type, js_body = get_text(f"{base_url}/static/app.js")
    finally:
        server.shutdown()
        server.server_close()

    assert css_status == HTTPStatus.OK
    assert css_type == "text/css; charset=utf-8"
    assert "--ink" in css_body
    assert "@media" in css_body
    assert js_status == HTTPStatus.OK
    assert js_type == "text/javascript; charset=utf-8"
    assert "loadContext" in js_body
    assert "submitRun" in js_body
```

- [ ] **Step 2: Run static asset tests to verify failure**

Run:

```powershell
python -m pytest tests/test_web_server.py::test_static_assets_include_console_interactions -v
```

Expected: FAIL because static files do not exist.

- [ ] **Step 3: Create index HTML**

Create `src/dev_agent/web/static/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>研发助手控制台</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <main class="shell">
      <section class="hero">
        <p class="eyebrow">Local Dev Agent</p>
        <h1>研发助手控制台</h1>
        <p class="lede">在本机查看上下文、历史和 dry-run 计划。默认不触发真实模型请求，也不执行远程 Git 操作。</p>
      </section>
      <section class="grid">
        <article class="panel">
          <h2>环境</h2>
          <pre id="health">加载中...</pre>
        </article>
        <article class="panel">
          <h2>上下文</h2>
          <pre id="context">加载中...</pre>
        </article>
        <article class="panel">
          <h2>历史</h2>
          <pre id="history">加载中...</pre>
        </article>
        <article class="panel run-panel">
          <h2>提交 dry-run</h2>
          <form id="run-form">
            <label for="request">任务</label>
            <textarea id="request" name="request" required>整理当前项目状态，并给出下一步开发计划。</textarea>
            <label for="fake-response">Fake response</label>
            <textarea id="fake-response" name="fake_response" required>计划：读取上下文、检查历史、运行测试。</textarea>
            <button type="submit">生成计划</button>
          </form>
          <pre id="run-result">等待提交...</pre>
        </article>
      </section>
    </main>
    <script src="/static/app.js"></script>
  </body>
</html>
```

- [ ] **Step 4: Create CSS**

Create `src/dev_agent/web/static/styles.css`:

```css
:root {
  --paper: #f4efe4;
  --ink: #1d261f;
  --muted: #5d665f;
  --moss: #526b4a;
  --clay: #c9704a;
  --line: rgba(29, 38, 31, 0.16);
  --panel: rgba(255, 252, 244, 0.84);
  --shadow: 0 24px 70px rgba(31, 45, 33, 0.16);
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  color: var(--ink);
  font-family: Georgia, "Times New Roman", "Microsoft YaHei", serif;
  background:
    radial-gradient(circle at 12% 10%, rgba(201, 112, 74, 0.2), transparent 32rem),
    radial-gradient(circle at 80% 0%, rgba(82, 107, 74, 0.26), transparent 28rem),
    linear-gradient(135deg, #fbf7ec 0%, var(--paper) 46%, #d9dfca 100%);
}

.shell {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 48px 0;
}

.hero {
  padding: 34px;
  border: 1px solid var(--line);
  border-radius: 28px;
  background: rgba(255, 252, 244, 0.72);
  box-shadow: var(--shadow);
}

.eyebrow {
  margin: 0 0 12px;
  color: var(--clay);
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
}

h1 {
  max-width: 760px;
  font-size: clamp(2.6rem, 7vw, 5.6rem);
  line-height: 0.9;
}

.lede {
  max-width: 680px;
  margin: 20px 0 0;
  color: var(--muted);
  font-size: 1.08rem;
  line-height: 1.7;
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
  margin-top: 18px;
}

.panel {
  min-height: 260px;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: var(--panel);
  box-shadow: 0 18px 40px rgba(31, 45, 33, 0.08);
}

.run-panel {
  grid-column: span 3;
}

pre,
textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 16px;
  color: var(--ink);
  background: rgba(255, 255, 255, 0.56);
  font: 0.92rem/1.55 Consolas, "Microsoft YaHei UI", monospace;
}

pre {
  min-height: 150px;
  margin: 14px 0 0;
  padding: 14px;
  overflow: auto;
}

label {
  display: block;
  margin: 14px 0 8px;
  color: var(--muted);
  font-weight: 700;
}

textarea {
  min-height: 92px;
  padding: 12px;
  resize: vertical;
}

button {
  margin-top: 14px;
  border: 0;
  border-radius: 999px;
  padding: 12px 20px;
  color: #fffaf0;
  background: linear-gradient(135deg, var(--moss), #263d2d);
  font-weight: 800;
  cursor: pointer;
}

button:focus-visible,
textarea:focus-visible {
  outline: 3px solid rgba(201, 112, 74, 0.42);
  outline-offset: 3px;
}

@media (max-width: 860px) {
  .shell {
    width: min(100% - 20px, 680px);
    padding: 20px 0;
  }

  .hero,
  .panel {
    border-radius: 20px;
    padding: 18px;
  }

  .grid {
    grid-template-columns: 1fr;
  }

  .run-panel {
    grid-column: auto;
  }
}
```

- [ ] **Step 5: Create JavaScript**

Create `src/dev_agent/web/static/app.js`:

```javascript
const renderJson = (id, value) => {
  document.getElementById(id).textContent = JSON.stringify(value, null, 2);
};

const getJson = async (path) => {
  const response = await fetch(path);
  return response.json();
};

async function loadHealth() {
  renderJson("health", await getJson("/api/health"));
}

async function loadContext() {
  renderJson("context", await getJson("/api/context"));
}

async function loadHistory() {
  renderJson("history", await getJson("/api/history"));
}

async function submitRun(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const response = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      request: form.request.value,
      fake_response: form.fake_response.value,
    }),
  });
  renderJson("run-result", await response.json());
  await loadHistory();
}

document.getElementById("run-form").addEventListener("submit", submitRun);
loadHealth();
loadContext();
loadHistory();
```

- [ ] **Step 6: Run static asset tests**

Run:

```powershell
python -m pytest tests/test_web_server.py -v
```

Expected: all Web server tests pass.

- [ ] **Step 7: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit static Web UI**

Run:

```powershell
git add src/dev_agent/web/static tests/test_web_server.py
git commit -m "feat: add local web console UI"
```

Expected: commit succeeds.

---

### Task 4: CLI Serve Command

**Files:**
- Modify: `src/dev_agent/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add failing CLI serve tests**

Append to `tests/test_cli.py`:

```python
def test_serve_check_outputs_local_url(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "serve", "--host", "127.0.0.1", "--port", "0", "--check")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["host"] == "127.0.0.1"
    assert isinstance(payload["port"], int)
    assert payload["url"].startswith("http://127.0.0.1:")


def test_doctor_reports_web_console_capability(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "doctor")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["capabilities"]["web_console"] is True
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli.py -v
```

Expected: FAIL because `serve` command and doctor capability are not registered.

- [ ] **Step 3: Implement CLI serve command**

Modify imports in `src/dev_agent/cli.py`:

```python
from dev_agent.web.server import create_server
```

Add command function:

```python
def serve_command(args: Namespace) -> int:
    server = create_server(
        repo_root=Path.cwd(),
        home_dir=Path.home(),
        host=args.host,
        port=args.port,
    )
    host, port = server.server_address
    payload = {
        "ok": True,
        "host": host,
        "port": port,
        "url": f"http://{host}:{port}/",
    }
    if args.check:
        server.server_close()
        sys.stdout.write(_json(payload))
        return 0
    sys.stdout.write(_json(payload))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0
```

Add doctor capability:

```python
            "web_console": True,
```

Register parser:

```python
    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--check", action="store_true")
    serve_parser.set_defaults(handler=serve_command)
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

- [ ] **Step 6: Commit CLI serve command**

Run:

```powershell
git add src/dev_agent/cli.py tests/test_cli.py
git commit -m "feat: add local web console serve command"
```

Expected: commit succeeds.

---

### Task 5: Final Verification and Console Smoke

**Files:**
- Verify: full test suite and CLI smoke commands.

- [ ] **Step 1: Run full verification**

Run:

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
python -m pytest -v
$env:PYTHONPATH=(Resolve-Path 'src').Path
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
python -m dev_agent.cli doctor
python -m dev_agent.cli scan
python -m dev_agent.cli history
python -m dev_agent.cli run "验证 Web dry-run" --fake-response "计划：检查上下文并打开本地控制台。" --dry-run
python -m dev_agent.cli serve --port 0 --check
git status --short
```

Expected: tests pass; `doctor` includes `web_console`; `serve --check` prints a local URL; `git status --short` only shows expected tracked files or is clean after commits.

- [ ] **Step 2: Inspect recent commits**

Run:

```powershell
git log --oneline --decorate -5
```

Expected: the latest commits are the Web API, HTTP server, static UI, and serve CLI commits.

- [ ] **Step 3: Push branch**

Run:

```powershell
git push -u origin codex/dev-agent-web-console
```

Expected: branch pushes successfully. This is a remote operation; if credentials or network fail, report the failure and leave the branch local.

---

## Self-Review

**Spec coverage:** This plan implements the approved Web 控制台 first slice: local service, context view, history view, task submission via dry-run, and a static UI.

**Safety coverage:** The Web run endpoint requires `fake_response`, uses existing `LocalTaskRunner` with dry-run options, does not call real model providers, does not run verification automatically, does not push Git, and binds to `127.0.0.1` by default.

**Placeholder scan:** The plan contains exact files, test code, implementation code, commands, expected results, and commit commands. It avoids unfinished-marker language.

**Type consistency:** `build_health_payload`, `build_context_payload`, `build_history_payload`, `run_dry_run_task`, `DevAgentHttpHandler`, and `create_server` are introduced before CLI and tests use them.
