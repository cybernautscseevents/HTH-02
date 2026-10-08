"""HTTP API for the frontend. A thin layer: it validates input and calls StewardshipService,
which calls evaluate_episode(). No clinical logic lives here."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from prescription_ocr.orders import read_orders
from prescription_ocr.pipeline import ENGINES, OcrEngine, build_engine

from . import config
from .audit import JsonlAuditLog
from .drugs import Catalog
from .evidence import build_store
from .intake import EpisodeRequest, IntakeError, medicine_text, parse_prescription_text
from .renal import RenalDosing
from .review import ReviewError
from .rulepack import YamlRulePack
from .schemas import Episode, Review, Trigger
from .service import (
    DashboardStats,
    EvaluationReport,
    NotFoundError,
    OrderView,
    ReviewRequest,
    StewardshipService,
    _order_view,
)


class ParseRequest(BaseModel):
    text: str


class ParseResponse(BaseModel):
    orders: tuple[OrderView, ...]
    warnings: tuple[str, ...]


class OcrDrug(BaseModel):
    id: str
    raw_text: str
    generic: str | None
    norm_status: str
    norm_candidates: tuple[str, ...]
    dose_mg: float | None
    freq_per_day: float | None
    route: str | None
    duration_days: int | None


class OcrResponse(BaseModel):
    success: bool
    raw_text: str
    drugs: tuple[OcrDrug, ...]
    processing_time_ms: int
    model: str
    warnings: tuple[str, ...] = ()


def default_service() -> StewardshipService:
    """Production wiring: real Catalog, real NCDC rule pack, real renal table, JSONL audit log."""
    pack = YamlRulePack()
    path = str(config.CHROMA_DIR) if config.CHROMA_DIR.exists() else None
    return StewardshipService(
        catalog=Catalog.load(),
        rulepack=pack,
        renal=RenalDosing.load(),
        audit=JsonlAuditLog(config.AUDIT_LOG_PATH),
        retriever=build_store(pack, path=path),
    )


def create_app(
    service: StewardshipService | None = None,
    *,
    ocr_engines: dict[str, OcrEngine] | None = None,
) -> FastAPI:
    svc = service or default_service()
    loaded_engines = dict(ocr_engines or {})
    ocr_lock = Lock()
    app = FastAPI(title="Antibiotic Stewardship Copilot")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(IntakeError)
    @app.exception_handler(ReviewError)
    async def _rejected(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def _invalid(request, exc):
        """Input that passed the request schema but could not become a valid episode or order.
        It is rejected like any other inconsistent input, never answered with a server error."""
        from fastapi.responses import JSONResponse

        errors = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return JSONResponse(
            status_code=422, content={"detail": f"Input could not be read: {errors}"}
        )

    @app.exception_handler(NotFoundError)
    async def _missing(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": str(exc.args[0])})

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "ruleset_version": svc.rulepack.version}

    @app.get("/api/stats", response_model=DashboardStats)
    def stats() -> DashboardStats:
        return svc.dashboard_stats()

    @app.post("/api/ocr", response_model=OcrResponse)
    async def ocr(
        file: Annotated[UploadFile, File()], engine: str = "glm"
    ) -> OcrResponse:
        if engine not in ENGINES:
            raise HTTPException(
                status_code=422, detail=f"Unknown OCR engine '{engine}'. Choose glm or qwen."
            )
        if file.content_type not in {"image/jpeg", "image/png", "image/tiff", "image/webp"}:
            raise HTTPException(
                status_code=415, detail="Upload a JPEG, PNG, TIFF, or WebP image."
            )
        content = await file.read(15 * 1024 * 1024 + 1)
        if len(content) > 15 * 1024 * 1024:
            raise HTTPException(
                status_code=413, detail="Prescription image must be 15 MB or smaller."
            )
        suffix = Path(file.filename or "prescription.png").suffix or ".png"

        def transcribe():
            with ocr_lock:
                selected = loaded_engines.get(engine)
                if selected is None:
                    selected = build_engine(engine)
                    loaded_engines[engine] = selected
                with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
                    temporary.write(content)
                    path = Path(temporary.name)
                try:
                    return selected.transcribe(path)
                finally:
                    path.unlink(missing_ok=True)

        try:
            result = await run_in_threadpool(transcribe)
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail=f"{engine.upper()} OCR failed: {exc}"
            ) from exc
        parsed_result = replace(result, text=medicine_text(result.text))
        reading = read_orders(parsed_result, svc.catalog, started_at=datetime.now(UTC))
        drugs = tuple(
            OcrDrug(
                id=item.order.id,
                raw_text=item.order.raw_text,
                generic=item.order.generic,
                norm_status=item.order.norm_status.value,
                norm_candidates=item.order.norm_candidates,
                dose_mg=item.order.dose_mg,
                freq_per_day=item.order.freq_per_day,
                route=item.order.route.value if item.order.route else None,
                duration_days=item.order.duration_days,
            )
            for item in reading.readings
        )
        return OcrResponse(
            success=True,
            raw_text=result.text,
            drugs=drugs,
            processing_time_ms=round(result.elapsed_seconds * 1000),
            model=f"{result.model_id}@{result.model_revision}",
            warnings=reading.warnings,
        )

    @app.get("/api/syndromes")
    def syndromes() -> list[dict]:
        """The only syndrome codes the engine accepts, with the guideline source of each."""
        out = []
        for code in svc.rulepack.codes():
            s = svc.rulepack.syndrome(code)
            out.append(
                {
                    "code": code,
                    "name": s.name,
                    "antibiotics_indicated": s.antibiotics_indicated,
                    "culture_required": s.culture_required,
                    "source": s.evidence.title,
                    "page": s.evidence.page,
                }
            )
        return out

    @app.post("/api/parse-prescription")
    def parse_prescription(body: ParseRequest) -> ParseResponse:
        readings, warnings = parse_prescription_text(
            body.text, svc.catalog, started_at=datetime.now(UTC)
        )
        return ParseResponse(
            orders=tuple(_order_view(r.order, r.reason) for r in readings), warnings=warnings
        )

    @app.post("/api/evaluate")
    def evaluate(body: EpisodeRequest) -> EvaluationReport:
        return svc.evaluate_request(body)

    @app.get("/api/episodes")
    def list_episodes(has_culture: bool = False) -> tuple[Episode, ...]:
        episodes = svc.list_episodes()
        if has_culture:
            episodes = tuple(episode for episode in episodes if episode.specimens)
        return episodes

    @app.post("/api/episodes")
    def create_episode(body: EpisodeRequest) -> Episode:
        return svc.create_episode(body)

    @app.get("/api/episodes/{episode_id}")
    def get_episode(episode_id: str) -> Episode:
        return svc.get_episode(episode_id)

    @app.post("/api/episodes/{episode_id}/evaluate")
    def evaluate_episode_route(
        episode_id: str, trigger: Trigger = Trigger.NEW_PRESCRIPTION
    ) -> EvaluationReport:
        return svc.evaluate(episode_id, trigger)

    @app.get("/api/evaluations/{evaluation_id}")
    def get_evaluation(evaluation_id: str) -> EvaluationReport:
        return svc.get_evaluation(evaluation_id)

    @app.get("/api/evaluations/{evaluation_id}/reviews")
    def get_evaluation_reviews(evaluation_id: str) -> tuple[Review, ...]:
        return svc.reviews_for_evaluation(evaluation_id)

    @app.post("/api/reviews")
    def review(body: ReviewRequest):
        return svc.review(body)

    @app.get("/api/audit")
    def audit(entity_id: str | None = None):
        return svc.audit.list(entity_id)

    @app.get("/api/timeout-due")
    def timeout_due() -> list[dict]:
        return svc.timeout_due()

    return app
