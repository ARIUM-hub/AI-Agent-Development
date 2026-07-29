import json

from dev_agent.execution.models import ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan


def parse_provider_execution_plan(text: str) -> ExecutionPlan:
    try:
        data = json.loads(text.strip())
        return parse_execution_plan(data)
    except (json.JSONDecodeError, ExecutionPlanError) as exc:
        raise ExecutionPlanError(f"无法解析 provider 执行计划：{exc}") from exc
