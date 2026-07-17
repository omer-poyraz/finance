"""Repository pattern for persistence access."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generic, TypeVar

from sqlalchemy import Select
from sqlalchemy import select
from sqlalchemy.orm import Session

from database.connection import SessionLocal
from database.models import CollectorRun
from database.models import NewsArticle
from database.models import Stock
from shared.exceptions import RepositoryError


TModel = TypeVar("TModel")


@contextmanager
def session_scope() -> Session:
	"""Provide a transactional session boundary."""

	session = SessionLocal()
	try:
		yield session
		session.commit()
	except Exception:
		session.rollback()
		raise
	finally:
		session.close()


class Repository(Generic[TModel]):
	"""Generic SQLAlchemy repository."""

	def __init__(self, model: type[TModel], session: Session | None = None) -> None:
		self._model = model
		self._session = session

	def _current_session(self) -> Session:
		if self._session is not None:
			return self._session
		return SessionLocal()

	def add(self, entity: TModel) -> TModel:
		session = self._current_session()
		try:
			session.add(entity)
			session.flush()
			session.refresh(entity)
			return entity
		except Exception as exc:
			session.rollback()
			raise RepositoryError(f"Could not persist {self._model.__name__}: {exc}") from exc
		finally:
			if self._session is None:
				session.close()

	def get(self, entity_id: Any) -> TModel | None:
		session = self._current_session()
		try:
			return session.get(self._model, entity_id)
		except Exception as exc:
			raise RepositoryError(f"Could not load {self._model.__name__}: {exc}") from exc
		finally:
			if self._session is None:
				session.close()

	def list(self, statement: Select[Any] | None = None) -> list[TModel]:
		session = self._current_session()
		try:
			query = statement or select(self._model)
			return list(session.scalars(query).all())
		except Exception as exc:
			raise RepositoryError(f"Could not list {self._model.__name__}: {exc}") from exc
		finally:
			if self._session is None:
				session.close()

	def delete(self, entity: TModel) -> None:
		session = self._current_session()
		try:
			session.delete(entity)
			session.flush()
		except Exception as exc:
			session.rollback()
			raise RepositoryError(f"Could not delete {self._model.__name__}: {exc}") from exc
		finally:
			if self._session is None:
				session.close()


class NewsRepository(Repository[NewsArticle]):
	"""Repository for news articles."""

	def __init__(self, session: Session | None = None) -> None:
		super().__init__(NewsArticle, session=session)


class StockRepository(Repository[Stock]):
	"""Repository for stocks."""

	def __init__(self, session: Session | None = None) -> None:
		super().__init__(Stock, session=session)


class CollectorRunRepository(Repository[CollectorRun]):
	"""Repository for collector run audit records."""

	def __init__(self, session: Session | None = None) -> None:
		super().__init__(CollectorRun, session=session)

