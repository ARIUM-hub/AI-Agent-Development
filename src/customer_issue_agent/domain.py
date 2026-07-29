from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LabeledEnum(StrEnum):
    @property
    def label(self) -> str:
        return _LABELS[self]


class IssueCategory(LabeledEnum):
    INSTALLATION = "installation"
    FUNCTION_USE = "function_use"
    EXPECTATION_GAP = "expectation_gap"
    PRODUCT_FAULT = "product_fault"
    COMPATIBILITY = "compatibility"
    ACCESSORY = "accessory"
    NON_USAGE = "non_usage"
    UNCLEAR = "unclear"


class RootCause(LabeledEnum):
    UNCLEAR_INSTRUCTIONS = "unclear_instructions"
    EXPECTATION_MISMATCH = "expectation_mismatch"
    CUSTOMER_SERVICE_GAP = "customer_service_gap"
    PRODUCT_DESIGN = "product_design"
    QUALITY_SIGNAL = "quality_signal"
    COMPATIBILITY_LIMIT = "compatibility_limit"
    CUSTOMER_OPERATION = "customer_operation"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    NON_USAGE_ISSUE = "non_usage_issue"


class Responsibility(LabeledEnum):
    OPERATIONS = "operations"
    CUSTOMER_SERVICE_TRAINING = "customer_service_training"
    PRODUCT = "product"
    SUPPLY_CHAIN_QUALITY = "supply_chain_quality"
    NEED_MORE_INFORMATION = "need_more_information"


class EvidenceStrength(LabeledEnum):
    CLEAR = "clear"
    LIKELY = "likely"
    INSUFFICIENT = "insufficient"


_LABELS = {
    IssueCategory.INSTALLATION: "安装、开箱或组装问题",
    IssueCategory.FUNCTION_USE: "功能不会用或设置失败",
    IssueCategory.EXPECTATION_GAP: "功能表现未达到预期",
    IssueCategory.PRODUCT_FAULT: "产品异常、失灵或疑似质量问题",
    IssueCategory.COMPATIBILITY: "设备、环境、规格或平台兼容性问题",
    IssueCategory.ACCESSORY: "配件缺失或使用条件不满足",
    IssueCategory.NON_USAGE: "非产品使用问题",
    IssueCategory.UNCLEAR: "信息不足，暂无法判断",
    RootCause.UNCLEAR_INSTRUCTIONS: "说明或引导不清",
    RootCause.EXPECTATION_MISMATCH: "页面承诺或客户预期与实际体验有落差",
    RootCause.CUSTOMER_SERVICE_GAP: "客服排障引导不足",
    RootCause.PRODUCT_DESIGN: "产品设计容易误用或学习成本高",
    RootCause.QUALITY_SIGNAL: "疑似产品质量异常",
    RootCause.COMPATIBILITY_LIMIT: "疑似兼容性限制",
    RootCause.CUSTOMER_OPERATION: "客户操作错误或前置条件未满足",
    RootCause.INSUFFICIENT_INFORMATION: "信息不足，暂无法判断",
    RootCause.NON_USAGE_ISSUE: "非产品使用问题",
    Responsibility.OPERATIONS: "运营",
    Responsibility.CUSTOMER_SERVICE_TRAINING: "客服培训",
    Responsibility.PRODUCT: "产品",
    Responsibility.SUPPLY_CHAIN_QUALITY: "供应链或质量",
    Responsibility.NEED_MORE_INFORMATION: "需要补充信息",
    EvidenceStrength.CLEAR: "较明确",
    EvidenceStrength.LIKELY: "倾向于",
    EvidenceStrength.INSUFFICIENT: "信息不足",
}


class MessageTurn(BaseModel):
    speaker: Literal["customer", "agent", "unknown"]
    text: str

    @field_validator("text")
    @classmethod
    def trim_text(cls, value: str) -> str:
        return value.strip()


class AnalysisRequest(BaseModel):
    platform: str = Field(default="Unknown")
    conversation_text: str

    @field_validator("platform", "conversation_text")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("字段不能为空")
        return stripped


class ParsedConversation(BaseModel):
    platform: str
    original_text: str
    detected_language: str
    turns: list[MessageTurn]
    relevant_text: str
    is_usage_related: bool
    completeness_notes: list[str] = Field(default_factory=list)


class AttributionResult(BaseModel):
    model_config = ConfigDict(use_enum_values=False)

    issue_category: IssueCategory
    root_causes: list[RootCause]
    primary_responsibility: Responsibility
    secondary_responsibility: Responsibility | None = None
    evidence_strength: EvidenceStrength
    customer_problem: str
    evidence: list[str]
    recommended_actions: list[str]
    missing_information: list[str]


class AnalysisResult(BaseModel):
    request: AnalysisRequest
    parsed: ParsedConversation
    attribution: AttributionResult
    report: str
