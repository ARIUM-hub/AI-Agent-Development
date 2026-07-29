from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from customer_issue_agent.attribution import analyze_attribution
from customer_issue_agent.domain import AnalysisRequest, AnalysisResult
from customer_issue_agent.export import build_records_csv
from customer_issue_agent.ingestion import extract_batch_conversation_texts, extract_conversation_text
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
        return templates.TemplateResponse(request, "index.html", {"records": store.list_records()[-10:]})

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

    @app.post("/api/analyze-batch-file")
    async def analyze_batch_file(
        platform: str = Form(default="Other overseas platform"),
        file: UploadFile | None = None,
    ) -> dict:
        if file is None:
            raise HTTPException(status_code=422, detail="请上传批量客服会话文件")
        content = await file.read()
        try:
            conversations = extract_batch_conversation_texts(file.filename or "batch.txt", content)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        records = [
            _run_analysis(store, platform=platform, conversation_text=conversation)
            for conversation in conversations
        ]
        return {"batch_id": str(uuid4()), "count": len(records), "records": records}

    @app.post("/api/records/{record_id}/feedback")
    async def save_feedback(
        record_id: str,
        accepted: bool = Form(default=True),
        corrected_issue_category: str = Form(default=""),
        corrected_responsibility: str = Form(default=""),
        note: str = Form(default=""),
    ) -> dict:
        try:
            feedback = store.save_feedback(
                record_id,
                {
                    "accepted": accepted,
                    "corrected_issue_category": corrected_issue_category,
                    "corrected_responsibility": corrected_responsibility,
                    "note": note,
                },
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="记录不存在或已被清理，请刷新页面后重试") from exc
        return {"record_id": record_id, "feedback": feedback}

    @app.get("/api/records/export.csv")
    async def export_records_csv() -> Response:
        return Response(
            content=build_records_csv(store.list_records()),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=customer-issue-records.csv"},
        )

    return app


def _run_analysis(store: AnalysisStore, platform: str, conversation_text: str) -> dict:
    try:
        request = AnalysisRequest(platform=platform, conversation_text=conversation_text)
    except ValidationError as exc:
        detail = [{"loc": error["loc"], "msg": error["msg"]} for error in exc.errors()]
        raise HTTPException(status_code=422, detail=detail) from exc

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
