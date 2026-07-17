"""Application entrypoint for the Finance Intelligence Engine."""

from __future__ import annotations

from shared.app import create_app
from shared.logging import configure_logging


configure_logging()
app = create_app()


def main() -> None:
	"""Run the ASGI application with Uvicorn."""

	try:
		import uvicorn
	except ModuleNotFoundError as exc:
		raise RuntimeError(
			"uvicorn is required to run the API. Install project dependencies first."
		) from exc

	uvicorn.run(
		app,
		host="0.0.0.0",
		port=8000,
		reload=False,
	)


if __name__ == "__main__":
	main()