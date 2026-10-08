"""HTTP API for the frontend. A thin layer: it validates input and calls StewardshipService,
which calls evaluate_episode(). No clinical logic lives here."""

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ValidationError

from . import config
from .audit import JsonlAuditLog
from .ddi import DrugBankDDIProvider
from .drugs import Catalog
from .evidence import build_store
from .intake import EpisodeRequest, IntakeError, parse_prescription_text
from .renal import RenalDosing
from .review import ReviewError
from .rulepack import YamlRulePack
from .schemas import Episode, Trigger
from .service import (
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


def default_service() -> StewardshipService:
    """Production wiring: real Catalog, real NCDC rule pack, real renal table, JSONL audit log,
    and the DrugBank pair index for drug-drug interaction lookups (lazy; built once from the
    local XML export on first use, and degraded to CANNOT_ASSESS if the source is absent)."""
    pack = YamlRulePack()
    path = str(config.CHROMA_DIR) if config.CHROMA_DIR.exists() else None
    return StewardshipService(
        catalog=Catalog.load(),
        rulepack=pack,
        renal=RenalDosing.load(),
        audit=JsonlAuditLog(config.AUDIT_LOG_PATH),
        retriever=build_store(pack, path=path),
        ddi=DrugBankDDIProvider(),
    )


def create_app(service: StewardshipService | None = None) -> FastAPI:
    svc = service or default_service()
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
