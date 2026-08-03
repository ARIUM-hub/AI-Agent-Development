from dev_agent.execution.models import ExecutionOperation
from dev_agent.execution.plan import ExecutionPlanError


def _overlapping_match_indexes(text: str, fragment: str) -> list[int]:
    indexes: list[int] = []
    start = 0
    while True:
        index = text.find(fragment, start)
        if index < 0:
            return indexes
        indexes.append(index)
        start = index + 1


def apply_replace_text(
    operation: ExecutionOperation,
    current_content: str,
    current_exists: bool,
) -> str:
    if operation.action != "replace_text":
        raise ExecutionPlanError(f"unsupported action: {operation.action}")
    if not current_exists:
        raise ExecutionPlanError(
            f"replace_text 目标文件不存在：{operation.path}"
        )
    old_text = operation.old_text
    new_text = operation.new_text
    if not isinstance(old_text, str):
        raise ExecutionPlanError(
            f"replace_text 的 old_text 必须是字符串：{operation.path}"
        )
    if not isinstance(new_text, str):
        raise ExecutionPlanError(
            f"replace_text 的 new_text 必须是字符串：{operation.path}"
        )
    if not old_text:
        raise ExecutionPlanError(
            f"replace_text 的 old_text 不能为空：{operation.path}"
        )
    if old_text == new_text:
        raise ExecutionPlanError(
            f"replace_text 的 old_text 与 new_text 不能相同：{operation.path}"
        )
    indexes = _overlapping_match_indexes(current_content, old_text)
    if len(indexes) != 1:
        raise ExecutionPlanError(
            f"replace_text 需要唯一匹配：{operation.path}（实际 {len(indexes)} 处）"
        )
    index = indexes[0]
    return (
        current_content[:index]
        + new_text
        + current_content[index + len(old_text) :]
    )
