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
