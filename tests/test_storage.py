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
