from __future__ import annotations

from customer_issue_agent.domain import AttributionResult, EvidenceStrength, ParsedConversation


def build_report(parsed: ParsedConversation, attribution: AttributionResult) -> str:
    confidence_sentence = _confidence_sentence(attribution.evidence_strength)
    evidence = "；".join(attribution.evidence) if attribution.evidence else "会话中没有足够明确的事实片段。"
    actions = "；".join(attribution.recommended_actions)
    missing = "；".join(attribution.missing_information) if attribution.missing_information else "暂无必须补充的信息。"
    secondary = (
        f"，次责任方可关注：{attribution.secondary_responsibility.label}"
        if attribution.secondary_responsibility
        else ""
    )

    return (
        f"客户问题：{attribution.customer_problem}\n\n"
        f"判断依据：{evidence}\n\n"
        f"业务原因：{confidence_sentence}{_join_labels(attribution.root_causes)}。\n\n"
        f"优先责任方：{attribution.primary_responsibility.label}{secondary}。\n\n"
        f"下一步建议：{actions}\n\n"
        f"需要补充：{missing}\n\n"
        f"平台来源：{parsed.platform}；识别语言：{parsed.detected_language}。"
    )


def _confidence_sentence(strength: EvidenceStrength) -> str:
    if strength == EvidenceStrength.CLEAR:
        return "当前判断较明确，更可能是"
    if strength == EvidenceStrength.INSUFFICIENT:
        return "当前信息不足，只能判断为"
    return "当前更倾向于"


def _join_labels(items: list) -> str:
    return " + ".join(item.label for item in items)
