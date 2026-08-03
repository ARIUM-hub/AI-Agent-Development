from dev_agent.execution.models import ExecutionOperation, ExecutionPlan, SUPPORTED_ACTIONS


class ExecutionPlanError(ValueError):
    pass


class StaleExecutionPreviewError(ExecutionPlanError):
    pass


def parse_execution_plan(data: dict[str, object]) -> ExecutionPlan:
    if not isinstance(data, dict):
        raise ExecutionPlanError("execution plan must be a JSON object")
    operations_data = data.get("operations")
    if not isinstance(operations_data, list) or not operations_data:
        raise ExecutionPlanError("operations must be a non-empty list")
    summary = data.get("summary", "")
    if not isinstance(summary, str):
        raise ExecutionPlanError("summary must be a string")
    operations = [_parse_operation(item) for item in operations_data]
    return ExecutionPlan(summary=summary, operations=operations)


def _parse_operation(data: object) -> ExecutionOperation:
    if not isinstance(data, dict):
        raise ExecutionPlanError("operation must be an object")
    action = data.get("action")
    path = data.get("path")
    if not isinstance(action, str):
        raise ExecutionPlanError("action must be a string")
    if action not in SUPPORTED_ACTIONS:
        raise ExecutionPlanError(f"unsupported action: {action}")
    if not isinstance(path, str):
        raise ExecutionPlanError("path must be a string")
    if action == "replace_text":
        return _parse_replace_operation(data, path)
    content = data.get("content")
    if not isinstance(content, str):
        raise ExecutionPlanError("content must be a string")
    return ExecutionOperation(action=action, path=path, content=content)


def _parse_replace_operation(
    data: dict[str, object],
    path: str,
) -> ExecutionOperation:
    expected = {"action", "path", "old_text", "new_text"}
    if set(data) != expected:
        raise ExecutionPlanError(
            "replace_text fields must be exactly action, path, old_text and new_text"
        )
    old_text = data.get("old_text")
    new_text = data.get("new_text")
    if not isinstance(old_text, str):
        raise ExecutionPlanError("old_text must be a string")
    if not isinstance(new_text, str):
        raise ExecutionPlanError("new_text must be a string")
    return ExecutionOperation(
        action="replace_text",
        path=path,
        old_text=old_text,
        new_text=new_text,
    )
