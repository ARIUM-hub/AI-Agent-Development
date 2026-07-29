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
