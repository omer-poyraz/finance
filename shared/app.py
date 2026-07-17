"""FastAPI application factory for the finance intelligence engine."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi import HTTPException

from config import settings
from scheduler.jobs import build_scheduler
from scheduler.jobs import register_weekday_job
from scheduler.jobs import start_scheduler
from services import FinancePipelineService


logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    pipeline_service = FinancePipelineService()
    scheduler = build_scheduler()

    app = FastAPI(
        title="Finance Intelligence Engine",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.pipeline_service = pipeline_service
    app.state.scheduler = scheduler

    @app.on_event("startup")
    async def on_startup() -> None:
        logger.info("Application starting with timezone=%s", settings.timezone)
        register_weekday_job(
            scheduler,
            pipeline_service.collect_all,
            hour=8,
            minute=30,
            job_id="collect_and_analyze",
        )
        register_weekday_job(
            scheduler,
            pipeline_service.send_daily_recommendations,
            hour=9,
            minute=55,
            job_id="send_daily_whatsapp",
        )
        register_weekday_job(
            scheduler,
            pipeline_service.archive_today,
            hour=17,
            minute=0,
            job_id="archive_daily_recommendations",
        )
        start_scheduler(scheduler)

    @app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        """Return a minimal service status response."""

        return {"status": "ok", "service": "Finance Intelligence Engine"}

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, str]:
        """Return a health-check payload for orchestration tools."""

        return {"status": "healthy"}

    @app.get("/collect/news", tags=["collectors"])
    async def collect_news() -> dict[str, object]:
        """Collect and persist normalized news."""

        try:
            items = pipeline_service.collect_news()
            return {"status": "ok", "count": len(items), "items": items}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/collect/kap", tags=["collectors"])
    async def collect_kap() -> dict[str, object]:
        """Collect and persist normalized KAP announcements."""

        try:
            items = pipeline_service.collect_kap()
            return {"status": "ok", "count": len(items), "items": items}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/collect/market", tags=["collectors"])
    async def collect_market() -> dict[str, object]:
        """Collect and persist normalized market data."""

        try:
            items = pipeline_service.collect_market()
            return {"status": "ok", "count": len(items), "items": items}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/analyze", tags=["analysis"])
    async def analyze() -> dict[str, object]:
        """Run analyzers and persist analysis output."""

        try:
            return pipeline_service.analyze()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/analyze/news", tags=["analysis"])
    async def analyze_news() -> dict[str, int]:
        """Run rule-based news intelligence analysis and return sentiment summary."""

        try:
            return pipeline_service.analyze_news()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/analyze/tickers", tags=["analysis"])
    async def analyze_tickers() -> dict[str, int]:
        """Aggregate analyzed news by ticker and return sentiment distribution."""

        try:
            return pipeline_service.analyze_tickers()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/analyze/market", tags=["analysis"])
    async def analyze_market() -> dict[str, int]:
        """Run market intelligence analysis and return trend summary."""

        try:
            return pipeline_service.analyze_market()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/recommendations", tags=["decision"])
    async def recommendations() -> list[dict[str, object]]:
        """Generate and return recommendation list."""

        try:
            return pipeline_service.generate_recommendations()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/history", tags=["history"])
    async def history() -> list[dict[str, object]]:
        """Return recommendation archive history."""

        return pipeline_service.get_history()

    return app
