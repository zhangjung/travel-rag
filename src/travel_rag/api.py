from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from travel_rag.config import Settings, get_settings
from travel_rag.domain.models import (
    KnowledgeCreateResponse,
    KnowledgeListResponse,
    KnowledgeRecordCreate,
    PlanResponse,
    SavedPlanDetail,
    SavedPlanListResponse,
    SavedPlanSaveResponse,
    TravelRequest,
)
from travel_rag.exporters.markdown import markdown_filename, render_plan_markdown
from travel_rag.observability import configure_logging
from travel_rag.persistence.plans import SavedPlanRepository
from travel_rag.rag.catalog import (
    KnowledgeCatalog,
    KnowledgeConflictError,
    KnowledgeIndexError,
)
from travel_rag.workflow import TravelWorkflow, create_workflow

LOGGER = logging.getLogger(__name__)
PACKAGE_DIR = Path(__file__).resolve().parent


def create_app(
    settings: Settings | None = None,
    workflow: TravelWorkflow | None = None,
    mode: str | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_mode = mode or resolved_settings.app_mode
    configure_logging(resolved_settings.log_dir, resolved_settings.log_level)

    app = FastAPI(
        title="Travel RAG API",
        version="0.1.0",
        description="Multi-Agent personalized travel planning with local RAG.",
    )
    app.state.mode = resolved_mode
    app.state.settings = resolved_settings
    app.state.workflow = workflow
    app.state.knowledge_catalog = None
    app.state.saved_plan_repository = None
    app.mount(
        "/static",
        StaticFiles(directory=PACKAGE_DIR / "static"),
        name="static",
    )
    templates = Jinja2Templates(directory=PACKAGE_DIR / "templates")

    def get_workflow() -> TravelWorkflow:
        if app.state.workflow is None:
            app.state.workflow = create_workflow(resolved_settings, resolved_mode)
        return app.state.workflow

    def get_knowledge_catalog() -> KnowledgeCatalog:
        if app.state.knowledge_catalog is None:
            app.state.knowledge_catalog = KnowledgeCatalog(
                get_workflow().knowledge_base,
                resolved_settings.knowledge_source_dir,
            )
        return app.state.knowledge_catalog

    def get_saved_plan_repository() -> SavedPlanRepository:
        if app.state.saved_plan_repository is None:
            app.state.saved_plan_repository = SavedPlanRepository(
                resolved_settings.plans_db_path
            )
        return app.state.saved_plan_repository

    def markdown_response(payload: PlanResponse) -> Response:
        content = render_plan_markdown(payload)
        filename = markdown_filename(payload)
        encoded_filename = quote(filename)
        return Response(
            content=content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": (
                    'attachment; filename="travel-plan.md"; '
                    f"filename*=UTF-8''{encoded_filename}"
                )
            },
        )

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"mode": resolved_mode},
        )

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": resolved_mode}

    @app.get("/api/v1/ready")
    async def ready() -> dict[str, object]:
        try:
            current = get_workflow()
            knowledge_base = current.knowledge_base
            counts = {
                "cases": knowledge_base.count("cases"),
                "experiences": knowledge_base.count("experiences"),
            }
            if not all(counts.values()):
                raise RuntimeError("知识库为空，请先执行 ingest-demo。")
            return {"status": "ready", "mode": resolved_mode, "collections": counts}
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/v1/knowledge", response_model=KnowledgeListResponse)
    async def list_knowledge(
        kind: Literal["all", "cases", "experiences"] = "all",
        query: str = Query(default="", max_length=200),
        destination: str | None = Query(default=None, min_length=1, max_length=50),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> KnowledgeListResponse:
        def browse() -> tuple[list[dict[str, object]], int]:
            knowledge_base = get_knowledge_catalog().knowledge_base
            kinds = ("cases", "experiences") if kind == "all" else (kind,)
            records = [
                record
                for collection_kind in kinds
                for record in knowledge_base.browse(
                    collection_kind,
                    query=query,
                    destination=destination,
                )
            ]
            records.sort(
                key=lambda record: (
                    str(record["metadata"].get("destination", "")),
                    str(record["title"]),
                )
            )
            return records[offset : offset + limit], len(records)

        try:
            items, total = await run_in_threadpool(browse)
            return KnowledgeListResponse(
                mode=resolved_mode,
                total=total,
                offset=offset,
                limit=limit,
                items=items,
            )
        except Exception as exc:
            LOGGER.exception(
                "knowledge_list_failed",
                extra={"event": {"mode": resolved_mode, "error_type": type(exc).__name__}},
            )
            raise HTTPException(
                status_code=500,
                detail="知识库读取失败，详情已写入结构化日志。",
            ) from exc

    @app.post(
        "/api/v1/knowledge",
        response_model=KnowledgeCreateResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_knowledge(payload: KnowledgeRecordCreate) -> KnowledgeCreateResponse:
        try:
            record = await run_in_threadpool(get_knowledge_catalog().add, payload)
            return KnowledgeCreateResponse(
                mode=resolved_mode,
                source_saved=True,
                indexed=True,
                record=record,
            )
        except KnowledgeConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except KnowledgeIndexError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except Exception as exc:
            LOGGER.exception(
                "knowledge_create_failed",
                extra={
                    "event": {
                        "mode": resolved_mode,
                        "kind": payload.kind,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            raise HTTPException(
                status_code=500,
                detail="知识记录新增失败，未执行静默降级；详情已写入结构化日志。",
            ) from exc

    @app.post("/api/v1/plans", response_model=PlanResponse)
    async def create_plan(payload: TravelRequest) -> PlanResponse:
        try:
            return await run_in_threadpool(get_workflow().run, payload)
        except Exception as exc:
            LOGGER.exception(
                "plan_request_failed",
                extra={"event": {"mode": resolved_mode, "error_type": type(exc).__name__}},
            )
            raise HTTPException(
                status_code=500,
                detail=f"规划失败：{type(exc).__name__}。详情已写入结构化日志。",
            ) from exc

    @app.post("/api/v1/plans/export/markdown")
    async def export_plan_markdown(payload: PlanResponse) -> Response:
        return markdown_response(payload)

    @app.post("/api/v1/saved-plans", response_model=SavedPlanSaveResponse)
    async def save_plan(payload: PlanResponse) -> SavedPlanSaveResponse:
        try:
            return await run_in_threadpool(get_saved_plan_repository().save, payload)
        except Exception as exc:
            LOGGER.exception(
                "saved_plan_create_failed",
                extra={
                    "event": {
                        "request_id": payload.research.request_id,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            raise HTTPException(
                status_code=500,
                detail="行程保存失败，详情已写入结构化日志。",
            ) from exc

    @app.get("/api/v1/saved-plans", response_model=SavedPlanListResponse)
    async def list_saved_plans(
        query: str = Query(default="", max_length=200),
        destination: str | None = Query(default=None, min_length=1, max_length=50),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> SavedPlanListResponse:
        try:
            return await run_in_threadpool(
                get_saved_plan_repository().list,
                query=query,
                destination=destination,
                offset=offset,
                limit=limit,
            )
        except Exception as exc:
            LOGGER.exception(
                "saved_plan_list_failed",
                extra={"event": {"error_type": type(exc).__name__}},
            )
            raise HTTPException(
                status_code=500,
                detail="行程库读取失败，详情已写入结构化日志。",
            ) from exc

    @app.get("/api/v1/saved-plans/{plan_id}", response_model=SavedPlanDetail)
    async def get_saved_plan(plan_id: str) -> SavedPlanDetail:
        try:
            item = await run_in_threadpool(get_saved_plan_repository().get, plan_id)
        except Exception as exc:
            LOGGER.exception(
                "saved_plan_get_failed",
                extra={
                    "event": {
                        "plan_id": plan_id,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            raise HTTPException(
                status_code=500,
                detail="行程读取失败，详情已写入结构化日志。",
            ) from exc
        if item is None:
            raise HTTPException(status_code=404, detail="未找到该行程。")
        return item

    @app.post("/api/v1/saved-plans/{plan_id}/export/markdown")
    async def export_saved_plan_markdown(plan_id: str) -> Response:
        try:
            item = await run_in_threadpool(get_saved_plan_repository().get, plan_id)
        except Exception as exc:
            LOGGER.exception(
                "saved_plan_export_failed",
                extra={
                    "event": {
                        "plan_id": plan_id,
                        "error_type": type(exc).__name__,
                    }
                },
            )
            raise HTTPException(
                status_code=500,
                detail="行程导出失败，详情已写入结构化日志。",
            ) from exc
        if item is None:
            raise HTTPException(status_code=404, detail="未找到该行程。")
        return markdown_response(item.plan)

    return app


app = create_app()
