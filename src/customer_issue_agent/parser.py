from __future__ import annotations

import re

from customer_issue_agent.domain import MessageTurn, ParsedConversation

USAGE_KEYWORDS = (
    "not working",
    "doesn't work",
    "does not work",
    "cannot",
    "can't",
    "connect",
    "pair",
    "setup",
    "install",
    "broken",
    "defective",
    "missing",
    "error",
    "failed",
    "manual",
    "instruction",
    "不会",
    "不能",
    "无法",
    "连接",
    "安装",
    "设置",
    "故障",
    "坏了",
    "缺少",
)

NON_USAGE_KEYWORDS = (
    "shipping",
    "delivery",
    "package",
    "tracking",
    "discount",
    "coupon",
    "price",
    "物流",
    "快递",
    "包裹",
    "优惠",
    "价格",
)


def parse_conversation(platform: str, text: str) -> ParsedConversation:
    turns = [_parse_line(line) for line in text.splitlines() if line.strip()]
    if not turns:
        turns = [MessageTurn(speaker="unknown", text=text)]

    relevant_text = "\n".join(turn.text for turn in turns)
    lowered = relevant_text.lower()
    usage_hits = _count_hits(lowered, USAGE_KEYWORDS)
    non_usage_hits = _count_hits(lowered, NON_USAGE_KEYWORDS)
    notes = _completeness_notes(turns, usage_hits, non_usage_hits)

    return ParsedConversation(
        platform=platform,
        original_text=text,
        detected_language=_detect_language(text),
        turns=turns,
        relevant_text=relevant_text,
        is_usage_related=usage_hits > 0 and usage_hits >= non_usage_hits,
        completeness_notes=notes,
    )


def _parse_line(line: str) -> MessageTurn:
    normalized = line.strip()
    match = re.match(r"^(customer|buyer|user|agent|seller|support|客服|客户|买家|卖家)\s*[:：]\s*(.+)$", normalized, re.I)
    if not match:
        return MessageTurn(speaker="unknown", text=normalized)

    raw_speaker, text = match.groups()
    speaker = raw_speaker.lower()
    if speaker in {"customer", "buyer", "user", "客户", "买家"}:
        return MessageTurn(speaker="customer", text=text)
    if speaker in {"agent", "seller", "support", "客服", "卖家"}:
        return MessageTurn(speaker="agent", text=text)
    return MessageTurn(speaker="unknown", text=text)


def _detect_language(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh_or_mixed"
    if re.search(r"[áéíóúñü¿¡]", text, re.I):
        return "es_or_mixed"
    if re.search(r"[äöüß]", text, re.I):
        return "de_or_mixed"
    return "en_or_mixed"


def _count_hits(text: str, keywords: tuple[str, ...]) -> int:
    return sum(1 for keyword in keywords if keyword.lower() in text)


def _completeness_notes(turns: list[MessageTurn], usage_hits: int, non_usage_hits: int) -> list[str]:
    notes: list[str] = []
    customer_text = " ".join(turn.text for turn in turns if turn.speaker == "customer").strip()
    if len(customer_text.split()) < 4 and len(customer_text) < 20:
        notes.append("客户描述过短")
    if non_usage_hits > usage_hits:
        notes.append("物流或售前内容较多")
    if not any(turn.speaker == "agent" for turn in turns):
        notes.append("缺少客服回应")
    return notes
