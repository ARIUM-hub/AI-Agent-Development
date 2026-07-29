from dev_agent.memory.keyword import KeywordRetriever
from dev_agent.memory.models import ExperienceRecord, TaskRecord
from dev_agent.memory.vector import HashEmbeddingProvider, VectorIndex


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


def test_vector_index_returns_nearest_text() -> None:
    provider = HashEmbeddingProvider(dimensions=32)
    index = VectorIndex(provider)
    index.add(record_id="exp-1", kind="experience", text="Windows UTF-8 编码修复")
    index.add(record_id="exp-2", kind="experience", text="Git 提交与推送流程")

    hits = index.search("UTF-8 编码", limit=1)

    assert hits[0].record_id == "exp-1"
    assert hits[0].kind == "experience"
    assert hits[0].score > 0
