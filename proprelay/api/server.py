"""Server-side token issuing, system health, and operations observability API."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from proprelay import __version__
from proprelay.auth.tokens import LiveKitTokenService, TokenConfig
from proprelay.config import AppProfile, get_config
from proprelay.events.journal import read_filtered
from proprelay.events.schemas import DomainEvent
from proprelay.observability.store import MetricsStore

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 65536  # 64 KB limit to prevent oversized payload attacks


class TokenRequest(BaseModel):
    """Request payload for WebRTC room connection token with strict bounds."""

    model_config = ConfigDict(extra="ignore")

    identity: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.-]*$",
        description="Optional participant identity",
    )
    name: str | None = Field(
        default=None, max_length=100, description="Optional participant display name"
    )
    room_name: str | None = Field(
        default=None,
        max_length=64,
        pattern=r"^[A-Za-z0-9_.-]*$",
        description="Optional target room identifier",
    )


class TokenResponse(BaseModel):
    """Response payload containing WebRTC access credentials."""

    token: str
    url: str
    room_name: str
    identity: str


class HealthResponse(BaseModel):
    """System services liveness and component connectivity status."""

    status: str
    version: str = __version__
    profile: str
    livekit: bool
    ollama: bool
    kokoro: bool


class ReadinessResponse(BaseModel):
    """Formal readiness verification for voice orchestration."""

    status: str  # "ready" or "degraded"
    version: str = __version__
    profile: str
    ready: bool
    checks: dict[str, bool]
    details: dict[str, str]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan managing startup readiness logging and graceful resource release."""
    cfg = get_config()
    logger.info(
        "PropRelay API starting [version=%s, profile=%s, port=%d]",
        __version__,
        cfg.profile,
        cfg.api_port,
    )
    yield
    logger.info("PropRelay API shutting down gracefully.")


def create_api_app(
    token_service: LiveKitTokenService | None = None,
    events_path: Path | None = None,
    metrics_store: MetricsStore | None = None,
    evaluations_path: Path | None = None,
) -> FastAPI:
    """Construct configured FastAPI app for tokens, health, and operations observability."""
    cfg = get_config()
    svc = token_service or LiveKitTokenService(
        TokenConfig(
            api_key=cfg.livekit_api_key,
            api_secret=cfg.livekit_api_secret,
            default_ttl_seconds=cfg.token_ttl_seconds,
        )
    )
    ev_file = events_path or Path("data/events.jsonl")
    store = metrics_store or MetricsStore()
    eval_file = evaluations_path or Path("reports/evaluation/latest.json")

    app = FastAPI(
        title="PropRelay WebRTC & Token API",
        description="Issues participant tokens and provides system health, readiness, and observability",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS Review & Policy Enforcement
    if cfg.profile == AppProfile.PRODUCTION_LIKE_LOCAL:
        allowed_origins = [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
    else:
        allowed_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Security Headers & Request Limit Middleware
    @app.middleware("http")
    async def security_and_limit_middleware(request: Request, call_next: Any) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_BYTES:
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=413,
                content={"detail": "Payload exceeds maximum allowed limit (64 KB)"},
            )

        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: ws: http:;"
        )
        return response

    @app.post("/api/token", response_model=TokenResponse)
    async def request_token(req: TokenRequest) -> TokenResponse:
        """Issue a cryptographically signed LiveKit WebRTC access token."""
        opaque_id = f"user-{uuid.uuid4().hex[:8]}"
        opaque_room = f"room-{uuid.uuid4().hex[:8]}"

        identity = (req.identity.strip() if req.identity else None) or opaque_id
        room_name = (req.room_name.strip() if req.room_name else None) or opaque_room
        participant_name = (req.name.strip() if req.name else None) or "Renter"

        try:
            jwt_token = svc.generate_token(
                identity=identity,
                room_name=room_name,
                participant_name=participant_name,
                ttl_seconds=cfg.token_ttl_seconds,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        except Exception as e:
            logger.error("Failed to generate token: %s", e)
            raise HTTPException(status_code=500, detail="Token generation error") from e

        livekit_url = cfg.livekit_url
        agent_name = cfg.livekit_agent_name

        # Automatically dispatch agent to the room
        try:
            from livekit import api

            lk_api = api.LiveKitAPI(livekit_url, svc.config.api_key, svc.config.api_secret)
            try:
                await lk_api.agent_dispatch.create_dispatch(
                    api.CreateAgentDispatchRequest(
                        room=room_name,
                        agent_name=agent_name,
                    )
                )
                logger.info("Dispatched agent '%s' to room '%s'", agent_name, room_name)
            finally:
                await lk_api.aclose()
        except Exception as e:
            logger.warning("Could not create agent dispatch for room '%s': %s", room_name, e)

        return TokenResponse(
            token=jwt_token,
            url=livekit_url,
            room_name=room_name,
            identity=identity,
        )

    @app.get("/api/config")
    async def get_public_config() -> dict[str, str]:
        """Return public runtime configuration (strictly zero secrets)."""
        return {
            "version": __version__,
            "profile": cfg.profile.value,
            "livekit_url": cfg.livekit_url,
        }

    @app.get("/api/health", response_model=HealthResponse)
    async def check_health() -> HealthResponse:
        """Liveness probe: verifies process is alive and reports connectivity to subsystems."""
        livekit_ok = False
        ollama_ok = False
        kokoro_ok = False

        async with httpx.AsyncClient(timeout=1.5) as client:
            try:
                lk_res = await client.get("http://127.0.0.1:7880")
                livekit_ok = lk_res.status_code == 200
            except Exception:
                livekit_ok = False

            try:
                ol_res = await client.get(f"{cfg.ollama_host}/api/tags")
                ollama_ok = ol_res.status_code == 200
            except Exception:
                ollama_ok = False

            try:
                kk_res = await client.get(f"{cfg.kokoro_url}/health")
                kokoro_ok = kk_res.status_code == 200
            except Exception:
                kokoro_ok = False

        overall = "healthy" if (livekit_ok and ollama_ok and kokoro_ok) else "degraded"
        return HealthResponse(
            status=overall,
            version=__version__,
            profile=cfg.profile.value,
            livekit=livekit_ok,
            ollama=ollama_ok,
            kokoro=kokoro_ok,
        )

    @app.get("/api/readiness", response_model=ReadinessResponse)
    async def check_readiness() -> ReadinessResponse:
        """Readiness probe: validates all dependencies, fixtures, and local storage required for voice sessions."""
        checks: dict[str, bool] = {}
        details: dict[str, str] = {}

        # 1. LiveKit Server
        async with httpx.AsyncClient(timeout=2.0) as client:
            try:
                lk_res = await client.get("http://127.0.0.1:7880")
                checks["livekit"] = lk_res.status_code == 200
                details["livekit"] = "LiveKit server responding on port 7880"
            except Exception as e:
                checks["livekit"] = False
                details["livekit"] = f"LiveKit unavailable: {e}"

            # 2. Ollama & required model
            try:
                ol_res = await client.get(f"{cfg.ollama_host}/api/tags")
                if ol_res.status_code == 200:
                    models = [m.get("name") for m in ol_res.json().get("models", [])]
                    has_model = any(cfg.ollama_model in str(m) for m in models)
                    checks["ollama"] = True
                    checks["ollama_model"] = has_model
                    details["ollama"] = f"Ollama active with models: {models}"
                    details["ollama_model"] = (
                        f"Target model '{cfg.ollama_model}' resident"
                        if has_model
                        else f"Model '{cfg.ollama_model}' missing"
                    )
                else:
                    checks["ollama"] = False
                    checks["ollama_model"] = False
                    details["ollama"] = f"Ollama HTTP {ol_res.status_code}"
            except Exception as e:
                checks["ollama"] = False
                checks["ollama_model"] = False
                details["ollama"] = f"Ollama connection error: {e}"

            # 3. Kokoro TTS
            try:
                kk_res = await client.get(f"{cfg.kokoro_url}/health")
                checks["kokoro"] = kk_res.status_code == 200
                details["kokoro"] = "Kokoro ONNX TTS server operational"
            except Exception as e:
                checks["kokoro"] = False
                details["kokoro"] = f"Kokoro TTS unavailable: {e}"

        # 4. Catalog & Showing Fixtures
        listings_file = Path("data/listings.json")
        showings_file = Path("data/showings.json")
        fixtures_ok = listings_file.exists() and showings_file.exists()
        checks["fixtures"] = fixtures_ok
        details["fixtures"] = (
            "Listings and showings fixtures available"
            if fixtures_ok
            else "Missing data/listings.json or data/showings.json"
        )

        # 5. Local Storage Writable
        storage_ok = False
        try:
            test_file = Path("data/.readiness_probe")
            test_file.parent.mkdir(parents=True, exist_ok=True)
            test_file.write_text("probe", encoding="utf-8")
            test_file.unlink()
            storage_ok = True
            details["storage"] = "data/ directory writable"
        except Exception as e:
            details["storage"] = f"Storage write error: {e}"
        checks["storage"] = storage_ok

        is_ready = all(checks.values())
        return ReadinessResponse(
            status="ready" if is_ready else "not_ready",
            version=__version__,
            profile=cfg.profile.value,
            ready=is_ready,
            checks=checks,
            details=details,
        )

    @app.get("/api/events")
    async def list_events(
        session_id: str | None = None,
        workflow_id: str | None = None,
        event_type: str | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        """Query persisted events with optional filtering and bounded page limit."""
        if not ev_file.exists():
            return []
        events = read_filtered(
            ev_file,
            session_id=session_id,
            workflow_id=workflow_id,
            event_type=event_type,
            limit=limit,
        )
        return [e.model_dump(mode="json") for e in events[:limit]]

    @app.get("/api/events/{event_id}")
    async def get_event(event_id: str) -> dict[str, Any]:
        """Fetch a single event by event_id."""
        if not ev_file.exists():
            raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")
        events = read_filtered(ev_file)
        for ev in events:
            if ev.event_id == event_id:
                return ev.model_dump(mode="json")
        raise HTTPException(status_code=404, detail=f"Event '{event_id}' not found")

    @app.get("/api/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str) -> dict[str, Any]:
        """Fetch all events and metadata for a specific workflow."""
        if not ev_file.exists():
            raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")
        events = read_filtered(ev_file, workflow_id=workflow_id)
        if not events:
            raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' not found")

        session_id = events[0].session_id
        started_at = events[0].timestamp.isoformat()
        completed_at = events[-1].timestamp.isoformat()
        duration_ms = max(0.0, (events[-1].timestamp - events[0].timestamp).total_seconds() * 1000)

        status = "IN_PROGRESS"
        for ev in reversed(events):
            if ev.event_type == "workflow.completed":
                status = "COMPLETED"
                break
            elif ev.event_type == "workflow.abandoned":
                status = "ABANDONED"
                break
            elif ev.event_type == "showing.booked":
                status = "BOOKED"
                break

        return {
            "workflow_id": workflow_id,
            "session_id": session_id,
            "status": status,
            "started_at": started_at,
            "completed_at": completed_at,
            "duration_ms": round(duration_ms, 2),
            "events_count": len(events),
            "events": [e.model_dump(mode="json") for e in events],
        }

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        """Fetch session trace including workflows, events, turn metrics, and errors."""
        events: list[DomainEvent] = []
        if ev_file.exists():
            events = read_filtered(ev_file, session_id=session_id)

        all_turns = store.get_turn_metrics()
        session_turns = [t for t in all_turns if t.session_id == session_id]

        all_errors = store.get_errors()
        session_errors = [e for e in all_errors if e.session_id == session_id]

        if not events and not session_turns and not session_errors:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

        workflow_ids = list(
            dict.fromkeys(
                [e.workflow_id for e in events if e.workflow_id]
                + [t.workflow_id for t in session_turns if t.workflow_id]
                + [err.workflow_id for err in session_errors if err.workflow_id]
            )
        )

        return {
            "session_id": session_id,
            "workflow_ids": workflow_ids,
            "events_count": len(events),
            "turns_count": len(session_turns),
            "errors_count": len(session_errors),
            "events": [e.model_dump(mode="json") for e in events],
            "turns": [t.model_dump(mode="json") for t in session_turns],
            "errors": [err.model_dump(mode="json") for err in session_errors],
        }

    @app.get("/api/metrics/summary")
    async def get_metrics_summary() -> dict[str, Any]:
        """Return system metrics summary with sample counts and statistical percentiles."""
        return store.get_metrics_summary()

    @app.get("/api/evaluations/latest")
    async def get_latest_evaluation() -> dict[str, Any]:
        """Return the latest scenario evaluation results report."""
        if not eval_file.exists():
            raise HTTPException(status_code=404, detail="No evaluation reports found")
        try:
            with open(eval_file, encoding="utf-8") as f:
                return cast(dict[str, Any], json.load(f))
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error reading evaluation report: {e}"
            ) from e

    # Optionally serve compiled frontend if built
    dist_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dist_path.exists():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=dist_path, html=True), name="static")

    return app


def main() -> None:
    """Run standalone token and health API service."""
    import uvicorn

    cfg = get_config()
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting PropRelay Token & Health API on http://%s:%d", cfg.api_host, cfg.api_port)

    app = create_api_app()
    uvicorn.run(app, host=cfg.api_host, port=cfg.api_port)


if __name__ == "__main__":
    main()
