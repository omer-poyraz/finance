"""Database bootstrap script."""

from __future__ import annotations

import logging

from database.connection import Base
from database.connection import engine

import database.models  # noqa: F401 - ensure ORM models are registered


logger = logging.getLogger(__name__)


def initialize_database() -> None:
	"""Create database schema for all registered models."""

	Base.metadata.create_all(bind=engine)
	logger.info("Database schema created.")


if __name__ == "__main__":
	initialize_database()
