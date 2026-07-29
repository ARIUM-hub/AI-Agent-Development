from __future__ import annotations

from customer_issue_agent.domain import (
    AttributionResult,
    EvidenceStrength,
    IssueCategory,
    ParsedConversation,
    Responsibility,
    RootCause,
)


def analyze_attribution(parsed: ParsedConversation) -> AttributionResult:
    text = parsed.relevant_text.lower()

    if not parsed.is_usage_related:
        return AttributionResult(
            issue_category=IssueCategory.NON_USAGE,
            root_causes=[RootCause.NON_USAGE_ISSUE],
            primary_responsibility=Responsibility.OPERATIONS,
            evidence_strength=EvidenceStrength.CLEAR,
            customer_problem="当前会话更像物流、价格、优惠或售前咨询，不属于产品使用问题。",
            evidence=_evidence(parsed, ("shipping", "delivery", "package", "price", "物流", "价格")),
            recommended_actions=["将该会话排除出产品使用问题归因池，必要时交给对应运营流程处理。"],
            missing_information=[],
        )

    if "客户描述过短" in parsed.completeness_notes:
        return AttributionResult(
            issue_category=IssueCategory.UNCLEAR,
            root_causes=[RootCause.INSUFFICIENT_INFORMATION],
            primary_responsibility=Responsibility.NEED_MORE_INFORMATION,
            evidence_strength=EvidenceStrength.INSUFFICIENT,
            customer_problem="客户表达了使用异常，但现有描述不足以判断具体问题。",
            evidence=_evidence(parsed, ("not working", "不能", "无法")),
            recommended_actions=["先补问关键使用信息，再判断责任方。"],
            missing_information=["具体使用步骤", "设备或环境信息", "错误提示或截图", "是否首次使用"],
        )

    if _has_any(text, ("broken", "defective", "stopped working", "坏了", "故障", "失灵")):
        return AttributionResult(
            issue_category=IssueCategory.PRODUCT_FAULT,
            root_causes=[RootCause.QUALITY_SIGNAL],
            primary_responsibility=Responsibility.SUPPLY_CHAIN_QUALITY,
            evidence_strength=EvidenceStrength.LIKELY,
            customer_problem="客户反馈产品出现损坏、失灵或短期异常，存在质量相关信号。",
            evidence=_evidence(parsed, ("broken", "defective", "stopped working", "坏了", "故障", "失灵")),
            recommended_actions=["优先核对批次、质检记录和同类会话频率，必要时升级供应链或质量团队。"],
            missing_information=["订单批次", "使用时长", "异常照片或视频"],
        )

    if _has_any(text, ("connect", "pair", "setup", "install", "manual", "instruction", "连接", "配对", "安装", "说明")):
        root_causes = [RootCause.UNCLEAR_INSTRUCTIONS]
        responsibility = Responsibility.OPERATIONS
        if _agent_under_asked(parsed):
            root_causes.append(RootCause.CUSTOMER_SERVICE_GAP)
            responsibility = Responsibility.CUSTOMER_SERVICE_TRAINING
        return AttributionResult(
            issue_category=IssueCategory.FUNCTION_USE,
            root_causes=root_causes,
            primary_responsibility=responsibility,
            secondary_responsibility=Responsibility.OPERATIONS if responsibility != Responsibility.OPERATIONS else None,
            evidence_strength=EvidenceStrength.LIKELY,
            customer_problem="客户卡在安装、连接、配对或功能设置过程，尚未看到完整排障闭环。",
            evidence=_evidence(parsed, ("connect", "pair", "setup", "install", "manual", "instruction", "连接", "配对", "安装", "说明")),
            recommended_actions=["补充标准排障话术，并检查页面说明、说明书或 FAQ 是否覆盖该失败场景。"],
            missing_information=["设备型号", "系统版本", "连接方式", "错误提示截图"],
        )

    return AttributionResult(
        issue_category=IssueCategory.EXPECTATION_GAP,
        root_causes=[RootCause.EXPECTATION_MISMATCH],
        primary_responsibility=Responsibility.OPERATIONS,
        evidence_strength=EvidenceStrength.LIKELY,
        customer_problem="客户对产品实际使用效果或操作路径存在落差。",
        evidence=_evidence(parsed, tuple()),
        recommended_actions=["复核商品页表达和客服解释口径，确认是否存在预期管理不足。"],
        missing_information=["客户预期来源", "实际使用场景", "期望效果描述"],
    )


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _agent_under_asked(parsed: ParsedConversation) -> bool:
    agent_text = " ".join(turn.text.lower() for turn in parsed.turns if turn.speaker == "agent")
    useful_questions = ("model", "version", "screenshot", "error", "steps", "型号", "截图", "错误", "步骤")
    return bool(agent_text) and not _has_any(agent_text, useful_questions)


def _evidence(parsed: ParsedConversation, keywords: tuple[str, ...]) -> list[str]:
    matched: list[str] = []
    for turn in parsed.turns:
        line = turn.text.strip()
        if not line:
            continue
        if not keywords or _has_any(line.lower(), keywords):
            matched.append(line)
        if len(matched) == 3:
            break
    return matched
