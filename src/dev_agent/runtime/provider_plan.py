from dataclasses import dataclass
from pathlib import Path

from dev_agent.execution.applier import ExecutionPlanApplier
from dev_agent.execution.models import ExecutionPlan, ExecutionResult
from dev_agent.execution.provider_plan import parse_provider_execution_plan
from dev_agent.providers.base import ModelProvider
from dev_agent.providers.budget import (
    BudgetConfig,
    CircuitBreaker,
    ProtectedProvider,
)
from dev_agent.providers.models import ModelRequest, ModelResponse
from dev_agent.runtime.context import resolve_runtime_context
from dev_agent.runtime.prompts import (
    STRICT_EXECUTION_PLAN_SYSTEM_PROMPT,
    build_provider_plan_prompt,
)
from dev_agent.runtime.source_context import SourceContextBundle


@dataclass(frozen=True)
class ProviderPlanPreparation:
    provider_name: str
    model: str
    response: ModelResponse
    execution_plan: ExecutionPlan
    preview_result: ExecutionResult
    source_context: SourceContextBundle | None


def prepare_provider_execution_plan(
    repo_root: Path,
    home_dir: Path,
    user_request: str,
    provider: ModelProvider,
    model: str,
    source_context: SourceContextBundle | None = None,
) -> ProviderPlanPreparation:
    context = resolve_runtime_context(repo_root, home_dir, user_request)
    prompt = build_provider_plan_prompt(context, source_context)
    protected = ProtectedProvider(
        provider,
        CircuitBreaker(
            BudgetConfig(
                max_requests=1,
                max_failures=1,
                max_output_chars=20_000,
            )
        ),
    )
    response = protected.complete(
        ModelRequest(
            prompt=prompt,
            system_prompt=STRICT_EXECUTION_PLAN_SYSTEM_PROMPT,
        )
    )
    execution_plan = parse_provider_execution_plan(response.text)
    preview_result = ExecutionPlanApplier(repo_root).preview(execution_plan)
    return ProviderPlanPreparation(
        provider_name=response.provider,
        model=model,
        response=response,
        execution_plan=execution_plan,
        preview_result=preview_result,
        source_context=source_context,
    )
