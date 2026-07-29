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
