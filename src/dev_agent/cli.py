from argparse import ArgumentParser, Namespace
from pathlib import Path
import json
import sys

from dev_agent import __version__
from dev_agent.encoding import UTF8, read_text_utf8, utf8_environment_hint, write_text_utf8
from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan
from dev_agent.memory.retriever import MemoryRetriever
from dev_agent.memory.store import MemoryStore
from dev_agent.project.scanner import scan_project
from dev_agent.providers.base import FakeProvider
from dev_agent.runtime.models import TaskRunOptions
from dev_agent.runtime.runner import LocalTaskRunner
from dev_agent.web.server import create_server


def _json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def init_command(args: Namespace) -> int:
    root = Path.cwd()
    write_text_utf8(
        root / ".agent" / "project.yaml",
        f"name: {root.name}\ntech_stack: []\n",
    )
    write_text_utf8(
        root / ".agent" / "commands.yaml",
        "test:\nlint:\ntypecheck:\nbuild:\n",
    )
    write_text_utf8(
        root / ".agent" / "rules.md",
        "# 项目规则\n\n所有文本文件默认使用 UTF-8。包含中文时直接写中文字符。\n",
    )
    sys.stdout.write("initialized .agent configuration\n")
    return 0


def doctor_command(args: Namespace) -> int:
    payload = {
        "ok": True,
        "version": __version__,
        "encoding": UTF8,
        "powershell_utf8_hint": utf8_environment_hint(),
        "capabilities": {
            "provider_interface": True,
            "budget_protection": True,
            "command_executor": True,
            "git_reader": True,
            "verification_runner": True,
            "runtime_context": True,
            "local_task_runner": True,
            "web_console": True,
        },
    }
    sys.stdout.write(_json(payload))
    return 0


def scan_command(args: Namespace) -> int:
    scan = scan_project(Path.cwd())
    payload = {
        "root": str(scan.root),
        "languages": scan.languages,
        "markers": scan.markers,
        "suggested_commands": {
            "test": scan.suggested_commands.test,
            "lint": scan.suggested_commands.lint,
            "typecheck": scan.suggested_commands.typecheck,
            "build": scan.suggested_commands.build,
        },
    }
    sys.stdout.write(_json(payload))
    return 0


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


def _load_execution_plan(path: str | None):
    if path is None:
        return None
    try:
        return parse_execution_plan(json.loads(read_text_utf8(Path(path)).lstrip("\ufeff")))
    except (OSError, json.JSONDecodeError, ExecutionPlanError) as exc:
        raise ValueError(f"无法读取执行计划：{exc}") from exc


def run_command(args: Namespace) -> int:
    if args.apply and args.plan_file is None:
        sys.stderr.write("--plan-file is required when --apply is used\n")
        return 2
    try:
        execution_plan = _load_execution_plan(args.plan_file)
    except ValueError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    runner = LocalTaskRunner(
        repo_root=Path.cwd(),
        home_dir=Path.home(),
        provider=FakeProvider(name="fake-main", responses=[args.fake_response]),
    )
    result = runner.run(
        args.request,
        TaskRunOptions(
            dry_run=args.dry_run,
            run_verification=args.verify,
            apply_changes=args.apply,
            execution_plan=execution_plan,
        ),
    )
    payload = {
        "task_id": result.task_id,
        "plan_text": result.plan_text,
        "dry_run": result.dry_run,
        "memory_hit_count": result.memory_hit_count,
        "verification_steps": result.verification_steps,
        "verification_passed": None if result.verification_result is None else result.verification_result.passed,
        "events": result.events,
        "planned_changes": result.planned_changes,
        "applied_changes": result.applied_changes,
        "diff_stat": result.diff_stat,
        "execution_error": result.execution_error,
    }
    sys.stdout.write(_json(payload))
    return 1 if result.execution_error else 0


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


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="dev-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.set_defaults(handler=init_command)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.set_defaults(handler=doctor_command)

    scan_parser = subparsers.add_parser("scan")
    scan_parser.set_defaults(handler=scan_command)

    history_parser = subparsers.add_parser("history")
    history_parser.add_argument("--query")
    history_parser.set_defaults(handler=history_command)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("request")
    run_parser.add_argument("--fake-response", required=True)
    run_parser.add_argument("--dry-run", action="store_true", default=True)
    run_parser.add_argument("--verify", action="store_true")
    run_parser.add_argument("--plan-file")
    run_parser.add_argument("--apply", action="store_true")
    run_parser.set_defaults(handler=run_command)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--check", action="store_true")
    serve_parser.set_defaults(handler=serve_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
