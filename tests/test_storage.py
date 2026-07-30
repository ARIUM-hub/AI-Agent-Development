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


def test_store_merges_latest_feedback_into_records(tmp_path):
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

    feedback = store.save_feedback(
        record_id,
        {
            "accepted": False,
            "corrected_issue_category": "product_fault",
            "corrected_responsibility": "supply_chain_quality",
            "note": "用户明确提到设备完全失灵，需要质量侧复核。",
        },
    )
    records = store.list_records()

    assert feedback["accepted"] is False
    assert records[0]["feedback"]["corrected_issue_category"] == "product_fault"
    assert records[0]["feedback"]["corrected_responsibility"] == "supply_chain_quality"
    assert records[0]["feedback"]["note"] == "用户明确提到设备完全失灵，需要质量侧复核。"


def test_store_rejects_feedback_for_missing_record(tmp_path):
    store = AnalysisStore(tmp_path / "analyses.jsonl")

    try:
        store.save_feedback("missing", {"accepted": True})
    except KeyError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("missing record feedback should fail")
