import json

from dev_agent.execution.models import ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan


def parse_provider_execution_plan(text: str) -> ExecutionPlan:
    try:
        data = json.loads(text.strip())
        if not isinstance(data, dict):
            raise ExecutionPlanError("provider plan must be a JSON object")
        if set(data) != {"summary", "operations"}:
            raise ExecutionPlanError(
                "provider plan fields must be exactly summary and operations"
            )
        operations = data["operations"]
        if isinstance(operations, list):
            for operation in operations:
                if not isinstance(operation, dict):
                    continue
                expected = (
                    {"action", "path", "old_text", "new_text"}
                    if operation.get("action") == "replace_text"
                    else {"action", "path", "content"}
                )
                if set(operation) != expected:
                    raise ExecutionPlanError(
                        "provider operation fields do not match its action schema"
                    )
        return parse_execution_plan(data)
    except (json.JSONDecodeError, ExecutionPlanError) as exc:
        raise ExecutionPlanError(f"无法解析 provider 执行计划：{exc}") from exc
