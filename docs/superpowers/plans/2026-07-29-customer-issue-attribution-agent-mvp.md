# Customer Issue Attribution Agent MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended) or superpowers:subagent-driven-development when explicitly needed for independent tasks. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web workbench that accepts overseas e-commerce customer service conversations and returns a Chinese analyst-style customer usage issue attribution report.

**Architecture:** Use a small FastAPI application with focused domain, ingestion, parsing, attribution, report, and storage modules. The first version uses deterministic rules for stable tests and preserves a clean boundary where a future LLM-backed analyzer can be swapped in with one low-concurrency request per analysis.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, Pydantic, openpyxl, pytest, httpx.

---

## Source Spec

- `docs/superpowers/specs/2026-07-29-customer-issue-attribution-agent-design.md`

## Scope Check

The approved spec covers one cohesive MVP: single-conversation analysis from manually supplied overseas e-commerce platform messages. Later features such as platform APIs, batch reporting, trend alerts, and product knowledge packs remain outside this plan.

## File Structure

- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/customer_issue_agent/__init__.py`
- Create: `src/customer_issue_agent/domain.py`
- Create: `src/customer_issue_agent/ingestion.py`
- Create: `src/customer_issue_agent/parser.py`
- Create: `src/customer_issue_agent/attribution.py`
- Create: `src/customer_issue_agent/report.py`
- Create: `src/customer_issue_agent/storage.py`
- Create: `src/customer_issue_agent/app.py`
- Create: `src/customer_issue_agent/templates/index.html`
- Create: `src/customer_issue_agent/static/styles.css`
- Create: `tests/conftest.py`
- Create: `tests/test_ingestion.py`
- Create: `tests/test_parser.py`
- Create: `tests/test_attribution.py`
- Create: `tests/test_report.py`
- Create: `tests/test_storage.py`
- Create: `tests/test_app.py`

## Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/customer_issue_agent/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write scaffold verification test**

Create `tests/conftest.py`:

```python
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

Create `tests/test_app.py` with only this test for now:

```python
def test_package_imports():
    import customer_issue_agent

    assert customer_issue_agent.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_package_imports -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'customer_issue_agent'`.

- [ ] **Step 3: Add package scaffold**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69"]
build-backend = "setuptools.build_meta"

[project]
name = "customer-issue-agent"
version = "0.1.0"
description = "Local workbench for overseas e-commerce customer usage issue attribution"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.111",
  "jinja2>=3.1",
  "openpyxl>=3.1",
  "pydantic>=2.7",
  "python-multipart>=0.0.9",
  "uvicorn[standard]>=0.30"
]

[project.optional-dependencies]
dev = [
  "httpx>=0.27",
  "pytest>=8.2"
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-data]
customer_issue_agent = ["templates/*.html", "static/*.css"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Create `README.md`:

```markdown
# 客户使用问题归因智能体

本项目是海外电商客服会话分析工作台。首版支持人工粘贴或上传客服会话，对单条会话输出中文分析结论，帮助运营和分析专员判断客户使用产品时遇到的问题、可能业务原因、优先责任方和下一步动作。

## 本地运行

```powershell
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e ".[dev]"
python -m uvicorn customer_issue_agent.app:create_app --factory --reload
```

打开 `http://127.0.0.1:8000`。

## 安全约束

首版不批量请求模型供应商，不进行压力测试，不自动循环重试。默认使用本地规则归因，后续接入模型时保持单会话、低并发、可人工复核。
```

Create `src/customer_issue_agent/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Install dependencies with domestic mirror**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e ".[dev]"
```

Expected: command exits with code 0.

- [ ] **Step 5: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_package_imports -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

Run:

```powershell
git add pyproject.toml README.md src/customer_issue_agent/__init__.py tests/conftest.py tests/test_app.py
git commit -m "chore: scaffold customer issue agent"
```

## Task 2: Domain Models

**Files:**
- Create: `src/customer_issue_agent/domain.py`
- Create: `tests/test_domain.py`

- [ ] **Step 1: Write failing domain model tests**

Create `tests/test_domain.py`:

```python
from customer_issue_agent.domain import (
    AnalysisRequest,
    EvidenceStrength,
    IssueCategory,
    Responsibility,
)


def test_analysis_request_trims_conversation_text():
    request = AnalysisRequest(
        platform="Shopee",
        conversation_text="  Customer: not working  ",
    )

    assert request.platform == "Shopee"
    assert request.conversation_text == "Customer: not working"


def test_domain_enums_keep_chinese_labels():
    assert IssueCategory.FUNCTION_USE.label == "功能不会用或设置失败"
    assert Responsibility.CUSTOMER_SERVICE_TRAINING.label == "客服培训"
    assert EvidenceStrength.INSUFFICIENT.label == "信息不足"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_domain.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing names from `customer_issue_agent.domain`.

- [ ] **Step 3: Add domain models**

Create `src/customer_issue_agent/domain.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_domain.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/domain.py tests/test_domain.py
git commit -m "feat: add attribution domain models"
```

## Task 3: Input Ingestion

**Files:**
- Create: `src/customer_issue_agent/ingestion.py`
- Create: `tests/test_ingestion.py`

- [ ] **Step 1: Write failing ingestion tests**

Create `tests/test_ingestion.py`:

```python
from customer_issue_agent.ingestion import extract_conversation_text


def test_extract_plain_text_upload():
    result = extract_conversation_text(
        filename="chat.txt",
        content=b"Customer: It does not connect\nAgent: Please restart it",
    )

    assert result == "Customer: It does not connect\nAgent: Please restart it"


def test_extract_csv_upload_combines_rows():
    content = "speaker,message\nCustomer,It does not connect\nAgent,Please restart it\n".encode("utf-8")

    result = extract_conversation_text(filename="chat.csv", content=content)

    assert "Customer: It does not connect" in result
    assert "Agent: Please restart it" in result


def test_extract_rejects_empty_upload():
    try:
        extract_conversation_text(filename="chat.txt", content=b"   ")
    except ValueError as exc:
        assert "没有可分析内容" in str(exc)
    else:
        raise AssertionError("empty upload should fail")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_ingestion.py -q
```

Expected: FAIL because `customer_issue_agent.ingestion` does not exist.

- [ ] **Step 3: Add ingestion module**

Create `src/customer_issue_agent/ingestion.py`:

```python
from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path

from openpyxl import load_workbook


def extract_conversation_text(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix in {".txt", ".log"}:
        text = _decode_text(content)
    elif suffix == ".csv":
        text = _extract_csv(content)
    elif suffix in {".xlsx", ".xlsm"}:
        text = _extract_xlsx(content)
    else:
        raise ValueError("仅支持 txt、log、csv、xlsx 或 xlsm 文件")

    cleaned = text.strip()
    if not cleaned:
        raise ValueError("没有可分析内容")
    return cleaned


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("文件编码无法识别，请使用 UTF-8 导出")


def _extract_csv(content: bytes) -> str:
    decoded = _decode_text(content)
    reader = csv.DictReader(StringIO(decoded))
    rows: list[str] = []
    for row in reader:
        speaker = _first_value(row, ("speaker", "role", "sender", "from", "角色", "发送方")) or "Unknown"
        message = _first_value(row, ("message", "text", "content", "body", "消息", "内容"))
        if message:
            rows.append(f"{speaker}: {message}")
    if rows:
        return "\n".join(rows)
    return decoded


def _extract_xlsx(content: bytes) -> str:
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return ""

    headers = [str(value).strip() if value is not None else "" for value in rows[0]]
    speaker_index = _first_index(headers, ("speaker", "role", "sender", "from", "角色", "发送方"))
    message_index = _first_index(headers, ("message", "text", "content", "body", "消息", "内容"))
    lines: list[str] = []

    for row in rows[1:]:
        values = ["" if value is None else str(value).strip() for value in row]
        if message_index is not None and message_index < len(values):
            speaker = values[speaker_index] if speaker_index is not None and speaker_index < len(values) else "Unknown"
            message = values[message_index]
            if message:
                lines.append(f"{speaker}: {message}")
        else:
            line = " ".join(value for value in values if value)
            if line:
                lines.append(line)
    return "\n".join(lines)


def _first_value(row: dict[str, str | None], keys: tuple[str, ...]) -> str | None:
    normalized = {key.strip().lower(): value for key, value in row.items() if key}
    for key in keys:
        value = normalized.get(key.lower())
        if value and value.strip():
            return value.strip()
    return None


def _first_index(headers: list[str], keys: tuple[str, ...]) -> int | None:
    lowered = [header.lower() for header in headers]
    for key in keys:
        if key.lower() in lowered:
            return lowered.index(key.lower())
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_ingestion.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/ingestion.py tests/test_ingestion.py
git commit -m "feat: ingest uploaded conversations"
```

## Task 4: Conversation Parser

**Files:**
- Create: `src/customer_issue_agent/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write failing parser tests**

Create `tests/test_parser.py`:

```python
from customer_issue_agent.parser import parse_conversation


def test_parse_detects_customer_and_agent_turns():
    parsed = parse_conversation(
        platform="Lazada",
        text="Customer: It will not connect\nAgent: Did you restart the device?",
    )

    assert parsed.platform == "Lazada"
    assert parsed.turns[0].speaker == "customer"
    assert parsed.turns[1].speaker == "agent"
    assert parsed.is_usage_related is True


def test_parse_marks_non_usage_logistics_question():
    parsed = parse_conversation(
        platform="Amazon",
        text="Customer: Where is my package?\nAgent: It is in transit.",
    )

    assert parsed.is_usage_related is False
    assert "物流或售前内容较多" in parsed.completeness_notes


def test_parse_flags_too_little_information():
    parsed = parse_conversation(platform="TikTok Shop", text="Customer: not working")

    assert "客户描述过短" in parsed.completeness_notes
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_parser.py -q
```

Expected: FAIL because `customer_issue_agent.parser` does not exist.

- [ ] **Step 3: Add parser module**

Create `src/customer_issue_agent/parser.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_parser.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/parser.py tests/test_parser.py
git commit -m "feat: parse platform conversations"
```

## Task 5: Attribution Engine

**Files:**
- Create: `src/customer_issue_agent/attribution.py`
- Create: `tests/test_attribution.py`

- [ ] **Step 1: Write failing attribution tests**

Create `tests/test_attribution.py`:

```python
from customer_issue_agent.attribution import analyze_attribution
from customer_issue_agent.domain import EvidenceStrength, IssueCategory, Responsibility, RootCause
from customer_issue_agent.parser import parse_conversation


def test_attribution_detects_connection_guidance_gap():
    parsed = parse_conversation(
        platform="Other",
        text=(
            "Customer: I followed the instructions but it still will not connect.\n"
            "Agent: Please try again later."
        ),
    )

    result = analyze_attribution(parsed)

    assert result.issue_category == IssueCategory.FUNCTION_USE
    assert RootCause.UNCLEAR_INSTRUCTIONS in result.root_causes
    assert RootCause.CUSTOMER_SERVICE_GAP in result.root_causes
    assert result.primary_responsibility == Responsibility.CUSTOMER_SERVICE_TRAINING
    assert result.evidence_strength == EvidenceStrength.LIKELY


def test_attribution_marks_quality_signal():
    parsed = parse_conversation(
        platform="Amazon",
        text="Customer: The device is broken and stopped working after one day.\nAgent: Sorry.",
    )

    result = analyze_attribution(parsed)

    assert result.issue_category == IssueCategory.PRODUCT_FAULT
    assert RootCause.QUALITY_SIGNAL in result.root_causes
    assert result.primary_responsibility == Responsibility.SUPPLY_CHAIN_QUALITY


def test_attribution_requests_more_information_for_short_case():
    parsed = parse_conversation(platform="Shopee", text="Customer: not working")

    result = analyze_attribution(parsed)

    assert result.evidence_strength == EvidenceStrength.INSUFFICIENT
    assert result.primary_responsibility == Responsibility.NEED_MORE_INFORMATION
    assert "具体使用步骤" in result.missing_information
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_attribution.py -q
```

Expected: FAIL because `customer_issue_agent.attribution` does not exist.

- [ ] **Step 3: Add attribution module**

Create `src/customer_issue_agent/attribution.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_attribution.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/attribution.py tests/test_attribution.py
git commit -m "feat: attribute customer usage issues"
```

## Task 6: Chinese Report Generator

**Files:**
- Create: `src/customer_issue_agent/report.py`
- Create: `tests/test_report.py`

- [ ] **Step 1: Write failing report tests**

Create `tests/test_report.py`:

```python
from customer_issue_agent.attribution import analyze_attribution
from customer_issue_agent.parser import parse_conversation
from customer_issue_agent.report import build_report


def test_report_contains_analyst_sections_in_chinese():
    parsed = parse_conversation(
        platform="Other",
        text=(
            "Customer: I followed the instructions but it still will not connect.\n"
            "Agent: Please try again later."
        ),
    )
    attribution = analyze_attribution(parsed)

    report = build_report(parsed, attribution)

    assert "客户问题" in report
    assert "判断依据" in report
    assert "优先责任方" in report
    assert "下一步建议" in report
    assert "客服培训" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_report.py -q
```

Expected: FAIL because `customer_issue_agent.report` does not exist.

- [ ] **Step 3: Add report module**

Create `src/customer_issue_agent/report.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_report.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/report.py tests/test_report.py
git commit -m "feat: render Chinese attribution reports"
```

## Task 7: Storage and Feedback Records

**Files:**
- Create: `src/customer_issue_agent/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_storage.py`:

```python
from customer_issue_agent.attribution import analyze_attribution
from customer_issue_agent.domain import AnalysisRequest, AnalysisResult
from customer_issue_agent.parser import parse_conversation
from customer_issue_agent.report import build_report
from customer_issue_agent.storage import AnalysisStore


def test_store_saves_analysis_jsonl(tmp_path):
    request = AnalysisRequest(platform="Other", conversation_text="Customer: not working")
    parsed = parse_conversation(request.platform, request.conversation_text)
    attribution = analyze_attribution(parsed)
    analysis = AnalysisResult(
        request=request,
        parsed=parsed,
        attribution=attribution,
        report=build_report(parsed, attribution),
    )
    store = AnalysisStore(tmp_path / "analyses.jsonl")

    record_id = store.save(analysis)
    records = store.list_records()

    assert record_id
    assert len(records) == 1
    assert records[0]["id"] == record_id
    assert records[0]["analysis"]["request"]["platform"] == "Other"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_storage.py -q
```

Expected: FAIL because `customer_issue_agent.storage` does not exist.

- [ ] **Step 3: Add storage module**

Create `src/customer_issue_agent/storage.py`:

```python
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from customer_issue_agent.domain import AnalysisResult


class AnalysisStore:
    def __init__(self, path: Path):
        self.path = path

    def save(self, analysis: AnalysisResult) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record_id = str(uuid4())
        payload = {
            "id": record_id,
            "created_at": datetime.now(UTC).isoformat(),
            "analysis": analysis.model_dump(mode="json"),
            "feedback": None,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return record_id

    def list_records(self) -> list[dict]:
        if not self.path.exists():
            return []
        records: list[dict] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped:
                    records.append(json.loads(stripped))
        return records
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_storage.py -q
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/customer_issue_agent/storage.py tests/test_storage.py
git commit -m "feat: store attribution analyses"
```

## Task 8: FastAPI Analysis Endpoint

**Files:**
- Create: `src/customer_issue_agent/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Replace app tests with endpoint tests**

Replace `tests/test_app.py`:

```python
from fastapi.testclient import TestClient

from customer_issue_agent import __version__
from customer_issue_agent.app import create_app


def test_package_imports():
    assert __version__ == "0.1.0"


def test_analyze_text_endpoint_returns_report(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post(
        "/api/analyze",
        data={
            "platform": "Other overseas platform",
            "conversation_text": (
                "Customer: I followed the instructions but it still will not connect.\n"
                "Agent: Please try again later."
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["record_id"]
    assert "客户问题" in payload["analysis"]["report"]
    assert payload["analysis"]["request"]["platform"] == "Other overseas platform"


def test_analyze_rejects_empty_text(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.post("/api/analyze", data={"platform": "Other", "conversation_text": "   "})

    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py -q
```

Expected: FAIL because `customer_issue_agent.app` does not exist.

- [ ] **Step 3: Add FastAPI app**

Create `src/customer_issue_agent/app.py`:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from customer_issue_agent.attribution import analyze_attribution
from customer_issue_agent.domain import AnalysisRequest, AnalysisResult
from customer_issue_agent.ingestion import extract_conversation_text
from customer_issue_agent.parser import parse_conversation
from customer_issue_agent.report import build_report
from customer_issue_agent.storage import AnalysisStore

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_STORAGE = Path("data") / "analyses.jsonl"


def create_app(storage_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="客户使用问题归因智能体")
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    static_dir = PACKAGE_DIR / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    store = AnalysisStore(storage_path or DEFAULT_STORAGE)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse("index.html", {"request": request, "records": store.list_records()[-10:]})

    @app.post("/api/analyze")
    async def analyze_text(
        platform: str = Form(default="Other overseas platform"),
        conversation_text: str = Form(default=""),
    ) -> dict:
        return _run_analysis(store, platform=platform, conversation_text=conversation_text)

    @app.post("/api/analyze-file")
    async def analyze_file(
        platform: str = Form(default="Other overseas platform"),
        file: UploadFile | None = None,
    ) -> dict:
        if file is None:
            raise HTTPException(status_code=422, detail="请上传客服会话文件")
        content = await file.read()
        try:
            text = extract_conversation_text(file.filename or "conversation.txt", content)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _run_analysis(store, platform=platform, conversation_text=text)

    return app


def _run_analysis(store: AnalysisStore, platform: str, conversation_text: str) -> dict:
    try:
        request = AnalysisRequest(platform=platform, conversation_text=conversation_text)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    parsed = parse_conversation(request.platform, request.conversation_text)
    attribution = analyze_attribution(parsed)
    result = AnalysisResult(
        request=request,
        parsed=parsed,
        attribution=attribution,
        report=build_report(parsed, attribution),
    )
    record_id = store.save(result)
    return {"record_id": record_id, "analysis": result.model_dump(mode="json")}


app = create_app()
```

- [ ] **Step 4: Run endpoint tests to verify they pass**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Run full test suite**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/customer_issue_agent/app.py tests/test_app.py
git commit -m "feat: expose analysis API"
```

## Task 9: Web Workbench UI

**Files:**
- Create: `src/customer_issue_agent/templates/index.html`
- Create: `src/customer_issue_agent/static/styles.css`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Add UI response test**

Append this test to `tests/test_app.py`:

```python
def test_index_renders_workbench(tmp_path):
    app = create_app(storage_path=tmp_path / "analyses.jsonl")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "客户使用问题归因智能体" in response.text
    assert "conversation_text" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_index_renders_workbench -q
```

Expected: FAIL because template and static directories do not exist.

- [ ] **Step 3: Add HTML template**

Create `src/customer_issue_agent/templates/index.html`:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>客户使用问题归因智能体</title>
    <link rel="stylesheet" href="/static/styles.css">
  </head>
  <body>
    <main class="shell">
      <section class="workbench">
        <header class="topbar">
          <div>
            <p class="eyebrow">海外电商 · 客服会话分析</p>
            <h1>客户使用问题归因智能体</h1>
          </div>
          <span class="status">本地规则模式</span>
        </header>

        <form class="panel" method="post" action="/api/analyze">
          <label for="platform">平台来源</label>
          <input id="platform" name="platform" value="Other overseas platform">

          <label for="conversation_text">客服会话</label>
          <textarea id="conversation_text" name="conversation_text" rows="12" placeholder="Customer: I followed the instructions but it still will not connect.&#10;Agent: Please try again later."></textarea>

          <button type="submit">分析会话</button>
        </form>

        <section class="history" aria-label="最近分析记录">
          <h2>最近记录</h2>
          {% if records %}
            {% for record in records|reverse %}
              <article class="record">
                <strong>{{ record.analysis.request.platform }}</strong>
                <p>{{ record.analysis.report }}</p>
              </article>
            {% endfor %}
          {% else %}
            <p class="empty">还没有分析记录。</p>
          {% endif %}
        </section>
      </section>
    </main>
  </body>
</html>
```

- [ ] **Step 4: Add CSS**

Create `src/customer_issue_agent/static/styles.css`:

```css
:root {
  --ink: #17211f;
  --muted: #65716d;
  --paper: #f7f5ef;
  --panel: #ffffff;
  --line: #d9ded5;
  --accent: #0f766e;
  --accent-strong: #115e59;
  --signal: #d97706;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  color: var(--ink);
  background:
    linear-gradient(135deg, rgba(15, 118, 110, 0.12), transparent 34%),
    linear-gradient(315deg, rgba(217, 119, 6, 0.12), transparent 30%),
    var(--paper);
  font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
}

.shell {
  min-height: 100vh;
  padding: 32px;
}

.workbench {
  max-width: 1120px;
  margin: 0 auto;
}

.topbar {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--line);
}

.eyebrow {
  margin: 0 0 8px;
  color: var(--accent-strong);
  font-size: 14px;
  font-weight: 700;
}

h1,
h2 {
  margin: 0;
  letter-spacing: 0;
}

h1 {
  font-size: 32px;
}

h2 {
  font-size: 18px;
}

.status {
  padding: 8px 12px;
  border: 1px solid var(--line);
  background: rgba(255, 255, 255, 0.7);
  color: var(--muted);
}

.panel,
.history {
  margin-top: 24px;
  padding: 20px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
}

label {
  display: block;
  margin: 16px 0 8px;
  font-weight: 700;
}

input,
textarea {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 12px;
  color: var(--ink);
  font: inherit;
}

textarea {
  resize: vertical;
}

button {
  margin-top: 16px;
  border: 0;
  border-radius: 6px;
  padding: 12px 18px;
  background: var(--accent);
  color: white;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

button:hover {
  background: var(--accent-strong);
}

.record {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  white-space: pre-line;
}

.record p,
.empty {
  color: var(--muted);
}

@media (max-width: 720px) {
  .shell {
    padding: 18px;
  }

  .topbar {
    align-items: flex-start;
    flex-direction: column;
  }

  h1 {
    font-size: 24px;
  }
}
```

- [ ] **Step 5: Run UI test to verify it passes**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest tests/test_app.py::test_index_renders_workbench -q
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/customer_issue_agent/templates/index.html src/customer_issue_agent/static/styles.css tests/test_app.py
git commit -m "feat: add local analysis workbench"
```

## Task 10: End-to-End Smoke Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add smoke test instructions**

Append this section to `README.md`:

```markdown
## 手动验收样例

平台来源填写 `Other overseas platform`，客服会话填写：

```text
Customer: I followed the instructions but it still will not connect.
Agent: Please try again later.
```

预期结果包含：

- 客户问题：连接、配对或设置失败。
- 业务原因：说明或引导不清，且客服排障引导不足。
- 优先责任方：客服培训。
- 下一步建议：补问设备型号、系统版本、连接方式和错误提示。
```

- [ ] **Step 2: Run full automated verification**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 3: Start local server**

Run:

```powershell
$OutputEncoding = [Console]::OutputEncoding
python -m uvicorn customer_issue_agent.app:create_app --factory --host 127.0.0.1 --port 8000
```

Expected: output includes `Uvicorn running on http://127.0.0.1:8000`.

- [ ] **Step 4: Manually submit sample**

Open `http://127.0.0.1:8000`, submit the README sample, and confirm the API response includes Chinese analysis text with `客户问题`、`业务原因`、`优先责任方`、`下一步建议`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add README.md
git commit -m "docs: add MVP smoke verification"
```

## Execution Notes

- Keep model-provider calls disabled during MVP implementation and tests.
- Do not run batch model probes, looped health checks, pressure tests, or concurrent agent calls against model providers.
- If a future task adds an LLM provider, require a dry-run mode and one manual single-conversation request before any repeated analysis.
- Keep `.superpowers/` untracked unless the team decides to preserve brainstorming browser artifacts.

## Self-Review Checklist

- Spec coverage: manual input, platform source, multi-language parsing marker, single-conversation analysis, issue recognition, business attribution, responsibility routing, evidence strength, Chinese report, storage, and manual review foundation are covered by Tasks 1 through 10.
- Deferred spec items: real platform API sync, batch trend reports, product knowledge packs, and model-provider integration are intentionally outside MVP scope.
- Placeholder scan: this plan contains no placeholder markers, no unspecified future implementation step, and no missing file path for planned code.
- Type consistency: `AnalysisRequest`, `ParsedConversation`, `AttributionResult`, `AnalysisResult`, `IssueCategory`, `RootCause`, `Responsibility`, and `EvidenceStrength` are introduced before later tasks use them.
