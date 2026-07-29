from pathlib import Path

from dev_agent.tasks.state import TaskStatus, create_task, load_task, update_task_status


def test_creates_and_loads_task_state(tmp_path: Path) -> None:
    task = create_task(tmp_path, "实现登录接口")

    loaded = load_task(tmp_path, task.task_id)

    assert loaded.task_id == task.task_id
    assert loaded.title == "实现登录接口"
    assert loaded.status == TaskStatus.PLANNED
    assert loaded.events[0] == "task_created"


def test_updates_task_status(tmp_path: Path) -> None:
    task = create_task(tmp_path, "修复测试失败")

    updated = update_task_status(tmp_path, task.task_id, TaskStatus.RUNNING, "started_execution")

    assert updated.status == TaskStatus.RUNNING
    assert updated.events[-1] == "started_execution"


def test_task_json_keeps_chinese_readable(tmp_path: Path) -> None:
    task = create_task(tmp_path, "实现中文规则")
    task_file = tmp_path / ".agent" / "tasks" / f"{task.task_id}.json"

    assert "实现中文规则" in task_file.read_text(encoding="utf-8")
