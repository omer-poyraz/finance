
"""Scheduler helpers and job registration utilities."""

from __future__ import annotations

import logging
from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import settings


logger = logging.getLogger(__name__)


def build_scheduler() -> BackgroundScheduler:
	"""Create a background scheduler configured with project timezone."""

	return BackgroundScheduler(timezone=settings.timezone)


def register_weekday_job(
	scheduler: BackgroundScheduler,
	job: Callable[[], None],
	*,
	hour: int = 9,
	minute: int = 55,
	job_id: str = "daily_weekday_signal",
) -> None:
	"""Register a weekday cron job for the morning notification workflow."""

	trigger = CronTrigger(
		day_of_week="mon-fri",
		hour=hour,
		minute=minute,
		timezone=settings.timezone,
	)
	scheduler.add_job(job, trigger=trigger, id=job_id, replace_existing=True)
	logger.info("Registered scheduler job %s", job_id)


def register_interval_job(
	scheduler: BackgroundScheduler,
	job: Callable[[], None],
	*,
	minutes: int = 3,
	job_id: str = "interval_bist_monitor",
) -> None:
	"""Register a recurring interval job for live monitoring."""

	trigger = IntervalTrigger(minutes=max(1, int(minutes)), timezone=settings.timezone)
	scheduler.add_job(job, trigger=trigger, id=job_id, replace_existing=True)
	logger.info("Registered scheduler job %s", job_id)


def start_scheduler(scheduler: BackgroundScheduler) -> None:
	"""Start the scheduler if it is not already running."""

	if not scheduler.running:
		scheduler.start()
		logger.info("Scheduler started")


def stop_scheduler(scheduler: BackgroundScheduler) -> None:
	"""Shut down the scheduler if it is running."""

	if scheduler.running:
		scheduler.shutdown(wait=False)
		logger.info("Scheduler stopped")

