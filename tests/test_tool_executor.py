import sys

from dev_agent.tools.executor import CommandExecutor


def test_command_executor_captures_success_output(tmp_path) -> None:
    executor = CommandExecutor(cwd=tmp_path)

    result = executor.run([sys.executable, "-c", "print('中文输出')"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "中文输出"
    assert result.stderr == ""
    assert result.duration_ms >= 0
    assert result.command[0] == sys.executable


def test_command_executor_captures_failure_output(tmp_path) -> None:
    executor = CommandExecutor(cwd=tmp_path)

    result = executor.run([sys.executable, "-c", "import sys; print('错误', file=sys.stderr); sys.exit(7)"])

    assert result.exit_code == 7
    assert result.stdout == ""
    assert result.stderr.strip() == "错误"
