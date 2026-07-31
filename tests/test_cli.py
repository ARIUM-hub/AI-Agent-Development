from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import subprocess
import sys
from pathlib import Path
import threading

import pytest


def run_cli(
    repo: Path,
    *args: str,
    home: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    project_src = Path(__file__).resolve().parents[1] / "src"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(project_src)
    if home is not None:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
    if extra_env is not None:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "dev_agent.cli", *args],
        cwd=repo,
        env=env,
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
    )


class CliProviderServer(HTTPServer):
    request_count: int
    requests: list[dict[str, object]]
    response_body: bytes
    response_status: int

    @property
    def base_url(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}"


class CliProviderHandler(BaseHTTPRequestHandler):
    server: CliProviderServer

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.request_count += 1
        self.server.requests.append(
            {
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "json": json.loads(body.decode("utf-8")),
            }
        )
        self.send_response(self.server.response_status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(self.server.response_body)))
        self.end_headers()
        self.wfile.write(self.server.response_body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def provider_server_factory() -> Iterator:
    servers: list[tuple[CliProviderServer, threading.Thread]] = []

    def start(content: str, *, status: int = 200) -> CliProviderServer:
        payload = {"choices": [{"message": {"content": content}}]}
        server = CliProviderServer(("127.0.0.1", 0), CliProviderHandler)
        server.request_count = 0
        server.requests = []
        server.response_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        server.response_status = status
        thread = threading.Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        thread.start()
        servers.append((server, thread))
        return server

    yield start

    for server, thread in servers:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def write_provider_config(home: Path, base_url: str) -> None:
    path = home / ".dev-agent" / "provider.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "openai_compatible:",
                f"  base_url: {base_url}/v1",
                "  model: model-name",
                "  api_key_env: DEV_AGENT_API_KEY",
                "  timeout_seconds: 5",
                "",
            ]
        ),
        encoding="utf-8",
    )


def strict_cli_plan() -> str:
    return json.dumps(
        {
            "summary": "创建 CLI 说明",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/cli-provider.md",
                    "content": "CLI 中文\n",
                }
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def test_init_creates_agent_files(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "init")

    assert result.returncode == 0
    assert (tmp_path / ".agent" / "project.yaml").exists()
    assert (tmp_path / ".agent" / "rules.md").read_text(encoding="utf-8").startswith("# 项目规则")
    assert "initialized" in result.stdout


def test_doctor_outputs_json(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "doctor")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["encoding"] == "utf-8"
    assert payload["capabilities"] == {
        "provider_interface": True,
        "budget_protection": True,
        "command_executor": True,
        "git_reader": True,
        "verification_runner": True,
        "runtime_context": True,
        "local_task_runner": True,
        "web_console": True,
    }


def test_scan_outputs_project_languages(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
    (tmp_path / "tsconfig.json").write_text("{}\n", encoding="utf-8")

    result = run_cli(tmp_path, "scan")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["languages"] == ["node", "typescript"]


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


def test_run_uses_fake_response_and_records_history(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"sample\"\n", encoding="utf-8")

    result = run_cli(
        tmp_path,
        "run",
        "实现 history 查询",
        "--fake-response",
        "计划：读取文件并运行测试。",
        "--dry-run",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["plan_text"] == "计划：读取文件并运行测试。"
    assert payload["dry_run"] is True
    assert payload["verification_steps"] == [["python", "-m", "pytest"]]
    assert payload["provider"] == "fake"
    assert payload["model"] is None
    assert payload["provider_usage"]["request_count"] == 1
    assert payload["file_diffs"] == []
    assert payload["preview_fingerprint"] == ""
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(encoding="utf-8")
    assert "实现 history 查询" in history


def test_serve_check_outputs_local_url(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "serve", "--host", "127.0.0.1", "--port", "0", "--check")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["host"] == "127.0.0.1"
    assert isinstance(payload["port"], int)
    assert payload["url"].startswith("http://127.0.0.1:")


def test_run_applies_plan_file_and_reports_changes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"sample\"\n", encoding="utf-8")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "创建说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/execution.md",
                        "content": "执行闭环\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "创建说明",
        "--fake-response",
        "计划：创建说明文件。",
        "--plan-file",
        str(plan_file),
        "--apply",
        "--yes",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["execution_error"] is None
    assert payload["applied_changes"][0]["path"] == "docs/execution.md"
    assert payload["file_diffs"][0]["path"] == "docs/execution.md"
    assert payload["file_diffs"][0]["status"] == "added"
    assert payload["preview_fingerprint"].startswith("sha256:")
    assert (tmp_path / "docs" / "execution.md").read_text(encoding="utf-8") == "执行闭环\n"


def test_run_previews_plan_file_without_apply(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "预览说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/preview.md",
                        "content": "只预览\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览计划",
        "--fake-response",
        "计划：只预览。",
        "--plan-file",
        str(plan_file),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["planned_changes"][0]["path"] == "docs/preview.md"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["preview_changes"][0]["content_bytes"] == len("只预览\n".encode("utf-8"))
    assert payload["file_diffs"][0]["path"] == "docs/preview.md"
    assert payload["file_diffs"][0]["status"] == "added"
    assert payload["preview_fingerprint"].startswith("sha256:")
    assert payload["applied_changes"] == []
    assert not (tmp_path / ".agent").exists()
    assert not (tmp_path / "docs" / "preview.md").exists()


def test_run_preview_outputs_preview_changes_without_writing(tmp_path: Path) -> None:
    write_target = tmp_path / "docs" / "preview.md"
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "预览说明",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/preview.md",
                        "content": "预览中文\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览计划",
        "--fake-response",
        "计划：只预览。",
        "--plan-file",
        str(plan_file),
        "--preview",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["preview_changes"] == [
        {
            "action": "create_text",
            "path": "docs/preview.md",
            "exists": False,
            "content_bytes": len("预览中文\n".encode("utf-8")),
            "risk": "create",
            "content_preview": "预览中文\n",
            "content_preview_truncated": False,
            "content_preview_line_count": 1,
            "content_preview_char_count": len("预览中文\n"),
        }
    ]
    assert payload["applied_changes"] == []
    assert not (tmp_path / ".agent").exists()
    assert not write_target.exists()


def test_run_accepts_plan_file_with_utf8_bom(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        "\ufeff"
        + json.dumps(
            {
                "summary": "BOM 计划",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/bom.md",
                        "content": "兼容 Windows UTF-8 BOM\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "读取 BOM 计划",
        "--fake-response",
        "计划：兼容 BOM。",
        "--plan-file",
        str(plan_file),
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["planned_changes"][0]["path"] == "docs/bom.md"
    assert payload["applied_changes"] == []


def test_run_apply_requires_plan_file(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "缺少计划",
        "--fake-response",
        "计划：失败。",
        "--apply",
    )

    assert result.returncode == 2
    assert "--plan-file or --use-provider-plan is required when --apply is used" in result.stderr


def test_run_reports_missing_plan_file_as_cli_error(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "缺少计划文件",
        "--fake-response",
        "计划：失败。",
        "--plan-file",
        str(tmp_path / "missing.json"),
        "--apply",
    )

    assert result.returncode == 2
    assert "无法读取执行计划" in result.stderr


def test_run_apply_without_confirmation_rejects_and_does_not_write(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "需要确认",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/needs-confirmation.md",
                        "content": "不应写入\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "未确认执行",
        "--fake-response",
        "计划：需要确认。",
        "--plan-file",
        str(plan_file),
        "--apply",
    )

    assert result.returncode == 2
    assert "应用执行计划需要确认" in result.stderr
    assert not (tmp_path / "docs" / "needs-confirmation.md").exists()


def test_run_preview_rejects_create_conflict_without_writing(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# existing\n", encoding="utf-8")
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "冲突预览",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "README.md",
                        "content": "# new\n",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览冲突",
        "--fake-response",
        "计划：冲突。",
        "--plan-file",
        str(plan_file),
        "--preview",
    )

    assert result.returncode == 2
    assert "执行计划预览失败" in result.stderr
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "# existing\n"


def test_run_use_provider_plan_previews_provider_json_without_side_effects(tmp_path: Path) -> None:
    provider_plan = json.dumps(
        {
            "summary": "创建 provider 说明",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/provider.md",
                    "content": "来自 provider\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "预览 provider 计划",
        "--fake-response",
        provider_plan,
        "--use-provider-plan",
        "--preview",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["task_id"] is None
    assert payload["planned_changes"][0]["path"] == "docs/provider.md"
    assert payload["preview_changes"][0]["risk"] == "create"
    assert payload["preview_changes"][0]["content_preview"] == "来自 provider\n"
    assert payload["preview_changes"][0]["content_preview_truncated"] is False
    assert payload["preview_changes"][0]["content_preview_line_count"] == 1
    assert payload["preview_changes"][0]["content_preview_char_count"] == len("来自 provider\n")
    assert payload["applied_changes"] == []
    assert not (tmp_path / ".agent").exists()
    assert not (tmp_path / "docs" / "provider.md").exists()


def test_run_without_use_provider_plan_keeps_fake_response_as_plain_text(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"sample\"\n", encoding="utf-8")
    provider_plan = json.dumps(
        {
            "summary": "不应解析",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/plain.md",
                    "content": "不应写入\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "普通 dry-run",
        "--fake-response",
        provider_plan,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["plan_text"] == provider_plan
    assert payload["planned_changes"] == []
    assert payload["preview_changes"] == []
    assert (tmp_path / ".agent").exists()
    assert not (tmp_path / "docs" / "plain.md").exists()


def test_run_use_provider_plan_apply_requires_confirmation(tmp_path: Path) -> None:
    provider_plan = json.dumps(
        {
            "summary": "需要确认",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/provider-confirm.md",
                    "content": "不应写入\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "未确认 provider plan",
        "--fake-response",
        provider_plan,
        "--use-provider-plan",
        "--apply",
    )

    assert result.returncode == 2
    assert "应用执行计划需要确认" in result.stderr
    assert not (tmp_path / "docs" / "provider-confirm.md").exists()


def test_run_use_provider_plan_apply_yes_writes_file(tmp_path: Path) -> None:
    provider_plan = json.dumps(
        {
            "summary": "确认写入",
            "operations": [
                {
                    "action": "create_text",
                    "path": "docs/provider-apply.md",
                    "content": "确认写入\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "确认 provider plan",
        "--fake-response",
        provider_plan,
        "--use-provider-plan",
        "--apply",
        "--yes",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["applied_changes"][0]["path"] == "docs/provider-apply.md"
    assert (tmp_path / "docs" / "provider-apply.md").read_text(encoding="utf-8") == "确认写入\n"


def test_run_use_provider_plan_rejects_malformed_json_without_writing(tmp_path: Path) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "坏 provider plan",
        "--fake-response",
        '{"summary":',
        "--use-provider-plan",
        "--preview",
    )

    assert result.returncode == 2
    assert "无法解析 provider 执行计划" in result.stderr
    assert not (tmp_path / ".agent").exists()


def test_run_use_provider_plan_rejects_dangerous_path_without_writing(tmp_path: Path) -> None:
    provider_plan = json.dumps(
        {
            "summary": "危险路径",
            "operations": [
                {
                    "action": "create_text",
                    "path": "../escape.md",
                    "content": "不应写入\n",
                }
            ],
        },
        ensure_ascii=False,
    )

    result = run_cli(
        tmp_path,
        "run",
        "危险 provider plan",
        "--fake-response",
        provider_plan,
        "--use-provider-plan",
        "--preview",
    )

    assert result.returncode == 2
    assert "执行计划预览失败" in result.stderr
    assert not (tmp_path.parent / "escape.md").exists()


def test_run_rejects_plan_file_with_use_provider_plan(tmp_path: Path) -> None:
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps(
            {
                "summary": "文件计划",
                "operations": [
                    {
                        "action": "create_text",
                        "path": "docs/file.md",
                        "content": "file\n",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = run_cli(
        tmp_path,
        "run",
        "来源歧义",
        "--fake-response",
        "{}",
        "--plan-file",
        str(plan_file),
        "--use-provider-plan",
    )

    assert result.returncode == 2
    assert "--plan-file 不能与 --use-provider-plan 同时使用" in result.stderr
    assert not (tmp_path / "docs" / "file.md").exists()


def test_run_defaults_to_fake_and_requires_fake_response(tmp_path: Path) -> None:
    result = run_cli(tmp_path, "run", "离线请求")

    assert result.returncode == 2
    assert "fake 模式必须传入 --fake-response" in result.stderr


@pytest.mark.parametrize(
    "conflicting_args",
    [
        ("--fake-response", "{}"),
        ("--use-provider-plan",),
        ("--plan-file", "plan.json"),
    ],
)
def test_openai_compatible_rejects_fake_inputs_before_network(
    tmp_path: Path,
    conflicting_args: tuple[str, ...],
) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "冲突",
        "--provider",
        "openai-compatible",
        *conflicting_args,
        home=tmp_path,
    )

    assert result.returncode == 2
    assert "openai-compatible 不能与" in result.stderr
    assert not (tmp_path / ".agent").exists()


def test_openai_compatible_preview_requests_once_and_does_not_write(
    tmp_path: Path,
    provider_server_factory,
) -> None:
    home = tmp_path / "home"
    server = provider_server_factory(strict_cli_plan())
    write_provider_config(home, server.base_url)

    result = run_cli(
        tmp_path,
        "run",
        "创建说明",
        "--provider",
        "openai-compatible",
        home=home,
        extra_env={"DEV_AGENT_API_KEY": "cli-secret-key"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["provider"] == "openai-compatible"
    assert payload["model"] == "model-name"
    assert payload["provider_usage"]["request_count"] == 1
    assert payload["preview_changes"][0]["path"] == "docs/cli-provider.md"
    assert payload["file_diffs"][0]["status"] == "added"
    assert payload["task_id"] is None
    assert server.request_count == 1
    assert server.requests[0]["path"] == "/v1/chat/completions"
    assert server.requests[0]["authorization"] == "Bearer cli-secret-key"
    assert set(server.requests[0]["json"]) == {"model", "messages"}
    assert not (tmp_path / "docs" / "cli-provider.md").exists()
    assert not (tmp_path / ".agent").exists()
    assert "cli-secret-key" not in result.stdout
    assert "cli-secret-key" not in result.stderr


def test_openai_compatible_apply_yes_reuses_one_response(
    tmp_path: Path,
    provider_server_factory,
) -> None:
    home = tmp_path / "home"
    server = provider_server_factory(strict_cli_plan())
    write_provider_config(home, server.base_url)

    result = run_cli(
        tmp_path,
        "run",
        "创建说明",
        "--provider",
        "openai-compatible",
        "--apply",
        "--yes",
        home=home,
        extra_env={"DEV_AGENT_API_KEY": "cli-secret-key"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["provider_usage"]["request_count"] == 1
    assert payload["applied_changes"][0]["path"] == "docs/cli-provider.md"
    assert server.request_count == 1
    assert (tmp_path / "docs" / "cli-provider.md").read_text(
        encoding="utf-8"
    ) == "CLI 中文\n"
    history = (tmp_path / ".agent" / "history" / "tasks.jsonl").read_text(
        encoding="utf-8"
    )
    assert "cli-secret-key" not in history


def test_openai_compatible_missing_config_fails_before_network(
    tmp_path: Path,
) -> None:
    result = run_cli(
        tmp_path,
        "run",
        "请求",
        "--provider",
        "openai-compatible",
        home=tmp_path,
        extra_env={"DEV_AGENT_API_KEY": "cli-secret-key"},
    )

    assert result.returncode == 2
    assert "Provider 配置文件不存在" in result.stderr
    assert "cli-secret-key" not in result.stderr


def test_openai_compatible_missing_key_fails_before_network(
    tmp_path: Path,
    provider_server_factory,
) -> None:
    home = tmp_path / "home"
    server = provider_server_factory(strict_cli_plan())
    write_provider_config(home, server.base_url)
    env = os.environ.copy()
    env.pop("DEV_AGENT_API_KEY", None)

    result = run_cli(
        tmp_path,
        "run",
        "请求",
        "--provider",
        "openai-compatible",
        home=home,
        extra_env={"DEV_AGENT_API_KEY": ""},
    )

    assert result.returncode == 2
    assert "环境变量 DEV_AGENT_API_KEY" in result.stderr
    assert server.request_count == 0


def test_openai_compatible_429_is_not_retried_or_leaked(
    tmp_path: Path,
    provider_server_factory,
) -> None:
    home = tmp_path / "home"
    server = provider_server_factory("ignored", status=429)
    write_provider_config(home, server.base_url)

    result = run_cli(
        tmp_path,
        "run",
        "请求",
        "--provider",
        "openai-compatible",
        home=home,
        extra_env={"DEV_AGENT_API_KEY": "cli-secret-key"},
    )

    assert result.returncode == 2
    assert "HTTP 429" in result.stderr
    assert "cli-secret-key" not in result.stderr
    assert server.request_count == 1


def test_openai_compatible_malformed_plan_does_not_write(
    tmp_path: Path,
    provider_server_factory,
) -> None:
    home = tmp_path / "home"
    server = provider_server_factory("不是 JSON 计划")
    write_provider_config(home, server.base_url)

    result = run_cli(
        tmp_path,
        "run",
        "请求",
        "--provider",
        "openai-compatible",
        home=home,
        extra_env={"DEV_AGENT_API_KEY": "cli-secret-key"},
    )

    assert result.returncode == 2
    assert "无法解析 provider 执行计划" in result.stderr
    assert server.request_count == 1
    assert not (tmp_path / ".agent").exists()
