import hashlib
import json

from dev_agent.encoding import UTF8
from dev_agent.execution.models import ExecutionOperation, ExecutionPlan
from dev_agent.execution.plan import ExecutionPlanError, parse_execution_plan


def _text_digest(value: str) -> dict[str, object]:
    encoded = value.encode(UTF8)
    return {
        "utf8_bytes": len(encoded),
        "sha256": f"sha256:{hashlib.sha256(encoded).hexdigest()}",
    }


def _history_operation(operation: ExecutionOperation) -> dict[str, object]:
    item: dict[str, object] = {
        "action": operation.action,
        "path": operation.path,
    }
    if operation.action == "replace_text":
        if not isinstance(operation.old_text, str) or not isinstance(
            operation.new_text, str
        ):
            raise ExecutionPlanError("replace_text history fields must be strings")
        item["old_text"] = _text_digest(operation.old_text)
        item["new_text"] = _text_digest(operation.new_text)
    else:
        if not isinstance(operation.content, str):
            raise ExecutionPlanError("content history field must be a string")
        item["content"] = _text_digest(operation.content)
    return item


def build_execution_plan_history_text(plan: ExecutionPlan) -> str:
    return json.dumps(
        {
            "summary": plan.summary,
            "operations": [_history_operation(item) for item in plan.operations],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


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
