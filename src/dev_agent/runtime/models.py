from dataclasses import dataclass, field

from dev_agent.config.models import ProjectConfig, UserPreferences
from dev_agent.execution.models import ExecutionPlan
from dev_agent.memory.models import MemoryHit
from dev_agent.project.scanner import ProjectScan
from dev_agent.providers.models import ModelResponse, ProviderUsage
from dev_agent.tools.git import GitSnapshot
from dev_agent.verification.planner import VerificationPlan
from dev_agent.verification.runner import VerificationResult


@dataclass(frozen=True)
class RuntimeContext:
    user_request: str
    project: ProjectConfig
    preferences: UserPreferences
    rules_text: str
    scan: ProjectScan
    git: GitSnapshot
    memory_hits: list[MemoryHit]
    verification_plan: VerificationPlan


@dataclass(frozen=True)
class TaskRunOptions:
    dry_run: bool = True
    run_verification: bool = False
    apply_changes: bool = False
    execution_plan: ExecutionPlan | None = None
    expected_preview_fingerprint: str | None = None
    prepared_response: ModelResponse | None = None
    provider_model: str | None = None
    history_plan_text: str | None = None


@dataclass(frozen=True)
class TaskRunResult:
    task_id: str
    plan_text: str
    dry_run: bool
    memory_hit_count: int
    verification_steps: list[list[str]]
    provider: str
    model: str | None
    provider_usage: ProviderUsage
    verification_result: VerificationResult | None = None
    events: list[str] = field(default_factory=list)
    planned_changes: list[dict[str, object]] = field(default_factory=list)
    applied_changes: list[dict[str, object]] = field(default_factory=list)
    diff_stat: str = ""
    execution_error: str | None = None
    file_diffs: list[dict[str, object]] = field(default_factory=list)
    preview_fingerprint: str = ""
