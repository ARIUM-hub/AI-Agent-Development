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
                if isinstance(operation, dict) and set(operation) != {
                    "action",
                    "path",
                    "content",
                }:
                    raise ExecutionPlanError(
                        "provider operation fields must be exactly action, path and content"
                    )
        return parse_execution_plan(data)
    except (json.JSONDecodeError, ExecutionPlanError) as exc:
        raise ExecutionPlanError(f"无法解析 provider 执行计划：{exc}") from exc
