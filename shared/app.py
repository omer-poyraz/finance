"""FastAPI application factory for the finance intelligence engine."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi import HTTPException

from config import settings
from scheduler.jobs import build_scheduler
from scheduler.jobs import register_interval_job
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
        pipeline_service.update_history_performance()
        gemini = pipeline_service.gemini_health()
        logger.info(
            "Gemini status on startup: enabled=%s healthy=%s",
            gemini["enabled"],
            gemini["healthy"],
        )
        if settings.gemini_required and not (gemini["enabled"] and gemini["healthy"]):
            raise RuntimeError(
                "Gemini is required but not healthy. Verify SDK installation and GEMINI_API_KEY configuration."
            )
        if settings.scheduler_bist_enabled:
            register_weekday_job(
                scheduler,
                pipeline_service.send_bist_daily_report,
                hour=settings.scheduler_bist_hour,
                minute=settings.scheduler_bist_minute,
                job_id="weekday_bist_report",
            )

        if settings.scheduler_bist_live_enabled:
            register_interval_job(
                scheduler,
                pipeline_service.run_bist_live_monitoring,
                minutes=settings.scheduler_bist_live_interval_minutes,
                job_id="interval_bist_monitor",
            )

        if settings.scheduler_us_enabled:
            register_weekday_job(
                scheduler,
                pipeline_service.send_us_daily_report,
                hour=settings.scheduler_us_hour,
                minute=settings.scheduler_us_minute,
                job_id="weekday_us_report",
            )

        if settings.scheduler_portfolio_enabled:
            register_weekday_job(
                scheduler,
                pipeline_service.send_portfolio_update,
                hour=settings.scheduler_portfolio_hour,
                minute=settings.scheduler_portfolio_minute,
                job_id="weekday_portfolio_update",
            )

        start_scheduler(scheduler)

    @app.get("/", tags=["health"])
    async def root() -> dict[str, str]:
        """Return a minimal service status response."""

        return {"status": "ok", "service": "Finance Intelligence Engine"}

    @app.get("/health", tags=["health"])
    async def health_check() -> dict[str, object]:
        """Return a health-check payload for orchestration tools."""

        gemini = pipeline_service.gemini_health()
        return {
            "status": "healthy",
            "gemini_enabled": bool(gemini["enabled"]),
            "gemini_healthy": bool(gemini["healthy"]),
        }

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

    @app.get("/performance", tags=["history"])
    async def performance() -> dict[str, object]:
        """Return paper trading performance statistics."""

        return pipeline_service.get_performance()

    @app.get("/portfolio", tags=["portfolio"])
    async def portfolio() -> list[dict[str, object]]:
        """Return current portfolio positions."""

        return pipeline_service.storage.load("portfolio.json", default=[])

    @app.get("/portfolio/analyze", tags=["portfolio"])
    async def portfolio_analyze() -> list[dict[str, object]]:
        """Re-evaluate open portfolio positions with V2 decision set."""

        try:
            return pipeline_service.analyze_portfolio_positions()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/run/bist", tags=["scheduler"])
    async def run_bist_now() -> dict[str, object]:
        """Manually trigger BIST report flow."""

        try:
            return pipeline_service.send_bist_daily_report()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/run/us", tags=["scheduler"])
    async def run_us_now() -> dict[str, object]:
        """Manually trigger US report flow."""

        try:
            return pipeline_service.send_us_daily_report()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/run/portfolio", tags=["scheduler"])
    async def run_portfolio_now() -> dict[str, object]:
        """Manually trigger portfolio update flow."""

        try:
            return pipeline_service.send_portfolio_update()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    return app
