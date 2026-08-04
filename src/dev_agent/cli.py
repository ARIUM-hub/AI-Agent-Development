from argparse import ArgumentParser, Namespace
from dataclasses import asdict
from pathlib import Path
import json
import os
import sys

from dev_agent import __version__
from dev_agent.config.provider import (
    ProviderConfigError,
    load_openai_compatible_config,
    resolve_openai_compatible_api_key,
)
from dev_agent.encoding import UTF8, read_text_utf8, utf8_environment_hint, write_text_utf8
from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionPlan, ExecutionResult
from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan
from dev_agent.execution.provider_plan import (
    build_execution_plan_history_text,
    parse_provider_execution_plan,
)
from dev_agent.memory.retriever import MemoryRetriever
from dev_agent.memory.store import MemoryStore
from dev_agent.project.scanner import scan_project
from dev_agent.providers.base import FakeProvider
from dev_agent.providers.budget import BudgetExceeded
from dev_agent.providers.models import ProviderError, ProviderUsage
from dev_agent.providers.openai_compatible import OpenAICompatibleProvider
from dev_agent.runtime.models import TaskRunOptions
from dev_agent.runtime.provider_plan import (
    ProviderPlanPreparation,
    prepare_provider_execution_plan,
)
from dev_agent.runtime.runner import LocalTaskRunner
from dev_agent.runtime.source_context import (
    SourceContextBundle,
    SourceContextError,
    build_source_context,
)
from dev_agent.web.server import create_server
from dev_agent.git.commit_guard import validate_commit_message
from dev_agent.git.models import GitCommitPreflightError, GitCommitRequest


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


def _resolve_execution_plan(args: Namespace) -> ExecutionPlan | None:
    if args.plan_file and args.use_provider_plan:
        raise ValueError("--plan-file 不能与 --use-provider-plan 同时使用")
    if args.use_provider_plan:
        return parse_provider_execution_plan(args.fake_response)
    return _load_execution_plan(args.plan_file)


def _preview_execution_plan(execution_plan) -> ExecutionResult:
    if execution_plan is None:
        return ExecutionResult(applied=False, planned_changes=[])
    return ExecutionPlanApplier(Path.cwd()).preview(execution_plan)


def _preview_payload(
    args: Namespace,
    execution_plan,
    preview_result: ExecutionResult,
) -> dict[str, object]:
    planned_changes = [] if execution_plan is None else [operation.to_dict() for operation in execution_plan.operations]
    return {
        "task_id": None,
        "plan_text": args.fake_response,
        "dry_run": True,
        "memory_hit_count": 0,
        "verification_steps": [],
        "verification_passed": None,
        "events": ["execution_previewed"],
        "planned_changes": planned_changes,
        "preview_changes": preview_result.preview_changes_as_dicts(),
        "applied_changes": [],
        "diff_stat": "",
        "execution_error": None,
        "file_diffs": preview_result.file_diffs_as_dicts(),
        "preview_fingerprint": preview_result.preview_fingerprint,
        "source_context": None,
        "git_commit": None,
        "commit_error": None,
        **_provider_metadata("fake", None, None),
    }


def _provider_metadata(
    provider: str,
    model: str | None,
    usage: ProviderUsage | None,
) -> dict[str, object]:
    return {
        "provider": provider,
        "model": model,
        "provider_usage": None if usage is None else asdict(usage),
    }


def _source_context_metadata(
    source_context: SourceContextBundle | None,
) -> dict[str, object] | None:
    if source_context is None:
        return None
    return source_context.to_metadata()


def _prepared_preview_payload(
    prepared: ProviderPlanPreparation,
) -> dict[str, object]:
    preview = prepared.preview_result
    return {
        "task_id": None,
        "plan_text": prepared.response.text,
        "dry_run": True,
        "memory_hit_count": 0,
        "verification_steps": [],
        "verification_passed": None,
        "events": ["execution_previewed"],
        "planned_changes": [
            operation.to_dict()
            for operation in prepared.execution_plan.operations
        ],
        "preview_changes": preview.preview_changes_as_dicts(),
        "applied_changes": [],
        "diff_stat": "",
        "execution_error": None,
        "file_diffs": preview.file_diffs_as_dicts(),
        "preview_fingerprint": preview.preview_fingerprint,
        "source_context": _source_context_metadata(prepared.source_context),
        "git_commit": None,
        "commit_error": None,
        **_provider_metadata(
            prepared.provider_name,
            prepared.model,
            prepared.response.usage,
        ),
    }


def _confirm_apply(args: Namespace) -> bool:
    if not args.apply:
        return True
    if args.yes:
        return True
    if not sys.stdin.isatty():
        return False
    sys.stderr.write("应用执行计划需要确认。输入 yes 继续：")
    answer = sys.stdin.readline().strip()
    return answer == "yes"


def _confirm_commit(args: Namespace, request: GitCommitRequest, paths: tuple[str, ...]) -> bool:
    if args.yes:
        return True
    if not sys.stdin.isatty():
        return False
    sys.stderr.write(
        f"验证已通过。提交信息：{request.message}；文件：{', '.join(paths)}。输入 yes 创建提交："
    )
    return sys.stdin.readline().strip() == "yes"


def _validate_commit_arguments(args: Namespace) -> None:
    if not args.commit:
        if args.commit_message is not None:
            raise ValueError("--commit-message 只能与 --commit 同时使用")
        return
    if not args.apply:
        raise ValueError("--commit 必须与 --apply 同时使用")
    if not args.verify:
        raise ValueError("--commit 必须与 --verify 同时使用")
    if args.commit_message is None:
        raise ValueError("--commit 必须提供 --commit-message")
    try:
        validate_commit_message(args.commit_message)
    except GitCommitPreflightError as exc:
        raise ValueError(str(exc)) from exc


def _validate_run_arguments(args: Namespace) -> None:
    if args.provider == "fake":
        if args.context_file:
            raise ValueError("--context-file 只能用于 openai-compatible")
        if args.fake_response is None:
            raise ValueError("fake 模式必须传入 --fake-response")
        if args.apply and args.plan_file is None and not args.use_provider_plan:
            raise ValueError(
                "--plan-file or --use-provider-plan is required when --apply is used"
            )
        return
    conflicts: list[str] = []
    if args.fake_response is not None:
        conflicts.append("--fake-response")
    if args.use_provider_plan:
        conflicts.append("--use-provider-plan")
    if args.plan_file is not None:
        conflicts.append("--plan-file")
    if conflicts:
        raise ValueError(
            f"openai-compatible 不能与 {', '.join(conflicts)} 同时使用"
        )


def _result_payload(
    result,
    preview_result: ExecutionResult,
    source_context: SourceContextBundle | None = None,
) -> dict[str, object]:
    return {
        "task_id": result.task_id,
        "plan_text": result.plan_text,
        "dry_run": result.dry_run,
        "memory_hit_count": result.memory_hit_count,
        "verification_steps": result.verification_steps,
        "verification_passed": (
            None
            if result.verification_result is None
            else result.verification_result.passed
        ),
        "events": result.events,
        "planned_changes": result.planned_changes,
        "preview_changes": preview_result.preview_changes_as_dicts(),
        "applied_changes": result.applied_changes,
        "diff_stat": result.diff_stat,
        "execution_error": result.execution_error,
        "file_diffs": result.file_diffs,
        "preview_fingerprint": result.preview_fingerprint,
        "source_context": _source_context_metadata(source_context),
        "git_commit": None if result.git_commit is None else result.git_commit.to_dict(),
        "commit_error": result.commit_error,
        **_provider_metadata(
            result.provider,
            result.model,
            result.provider_usage,
        ),
    }


def _run_fake_command(args: Namespace) -> int:
    try:
        execution_plan = _resolve_execution_plan(args)
    except ValueError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    except ExecutionPlanError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    try:
        preview_result = _preview_execution_plan(execution_plan)
    except ExecutionPlanError as exc:
        sys.stderr.write(f"执行计划预览失败：{exc}\n")
        return 2
    if execution_plan is not None and not args.apply:
        sys.stdout.write(_json(_preview_payload(args, execution_plan, preview_result)))
        return 0
    if not _confirm_apply(args):
        sys.stderr.write("应用执行计划需要确认；请传入 --yes 或在交互式终端输入 yes。\n")
        return 2
    runner = LocalTaskRunner(
        repo_root=Path.cwd(),
        home_dir=Path.home(),
        provider=FakeProvider(name="fake", responses=[args.fake_response]),
    )
    result = runner.run(
        args.request,
        TaskRunOptions(
            dry_run=args.dry_run,
            run_verification=args.verify,
            apply_changes=args.apply,
            execution_plan=execution_plan,
            expected_preview_fingerprint=preview_result.preview_fingerprint or None,
            commit_request=GitCommitRequest(args.commit_message) if args.commit else None,
            confirm_commit=(lambda request, paths: _confirm_commit(args, request, paths)) if args.commit else None,
        ),
    )
    payload = _result_payload(result, preview_result)
    sys.stdout.write(_json(payload))
    return _result_exit_code(result)


def _run_openai_compatible_command(args: Namespace) -> int:
    try:
        source_context = (
            build_source_context(Path.cwd(), args.context_file)
            if args.context_file
            else None
        )
        config = load_openai_compatible_config(Path.home())
        api_key = resolve_openai_compatible_api_key(config, os.environ)
        provider = OpenAICompatibleProvider(config, api_key)
        prepared = prepare_provider_execution_plan(
            repo_root=Path.cwd(),
            home_dir=Path.home(),
            user_request=args.request,
            provider=provider,
            model=config.model,
            source_context=source_context,
        )
    except (
        SourceContextError,
        ProviderConfigError,
        ProviderError,
        BudgetExceeded,
        ExecutionPlanError,
    ) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    if not args.apply:
        sys.stdout.write(_json(_prepared_preview_payload(prepared)))
        return 0
    if not _confirm_apply(args):
        sys.stderr.write(
            "应用执行计划需要确认；请传入 --yes 或在交互式终端输入 yes。\n"
        )
        return 2
    runner = LocalTaskRunner(
        repo_root=Path.cwd(),
        home_dir=Path.home(),
        provider=provider,
    )
    result = runner.run(
        args.request,
        TaskRunOptions(
            dry_run=args.dry_run,
            run_verification=args.verify,
            apply_changes=True,
            execution_plan=prepared.execution_plan,
            expected_preview_fingerprint=(
                prepared.preview_result.preview_fingerprint
            ),
            prepared_response=prepared.response,
            provider_model=prepared.model,
            history_plan_text=build_execution_plan_history_text(
                prepared.execution_plan
            ),
            commit_request=GitCommitRequest(args.commit_message) if args.commit else None,
            confirm_commit=(lambda request, paths: _confirm_commit(args, request, paths)) if args.commit else None,
        ),
    )
    sys.stdout.write(
        _json(
            _result_payload(
                result,
                prepared.preview_result,
                prepared.source_context,
            )
        )
    )
    return _result_exit_code(result)


def _result_exit_code(result) -> int:
    if result.commit_declined:
        return 2
    if result.execution_error or result.commit_error:
        return 1
    if result.verification_result is not None and not result.verification_result.passed:
        return 1
    return 0


def run_command(args: Namespace) -> int:
    try:
        _validate_commit_arguments(args)
        _validate_run_arguments(args)
    except ValueError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2
    try:
        if args.provider == "openai-compatible":
            return _run_openai_compatible_command(args)
        return _run_fake_command(args)
    except GitCommitPreflightError as exc:
        sys.stderr.write(str(exc) + "\n")
        return 2


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
    run_parser.add_argument(
        "--provider",
        choices=["fake", "openai-compatible"],
        default="fake",
    )
    run_parser.add_argument("--fake-response")
    run_parser.add_argument("--context-file", action="append", default=[])
    run_parser.add_argument("--dry-run", action="store_true", default=True)
    run_parser.add_argument("--verify", action="store_true")
    run_parser.add_argument("--plan-file")
    run_parser.add_argument("--use-provider-plan", action="store_true")
    run_parser.add_argument("--preview", action="store_true")
    run_parser.add_argument("--apply", action="store_true")
    run_parser.add_argument("--yes", action="store_true")
    run_parser.add_argument("--commit", action="store_true")
    run_parser.add_argument("--commit-message")
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
