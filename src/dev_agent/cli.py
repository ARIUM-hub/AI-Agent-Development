from argparse import ArgumentParser, Namespace
from pathlib import Path
import json
import sys

from dev_agent import __version__
from dev_agent.encoding import UTF8, utf8_environment_hint, write_text_utf8
from dev_agent.project.scanner import scan_project


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


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="dev-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.set_defaults(handler=init_command)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.set_defaults(handler=doctor_command)

    scan_parser = subparsers.add_parser("scan")
    scan_parser.set_defaults(handler=scan_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
