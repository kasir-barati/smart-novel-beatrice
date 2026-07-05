"""FastAPI application entry point"""

from __future__ import annotations

import logging
from importlib.metadata import version

import uvicorn
from fastapi import FastAPI
from strawberry.fastapi import GraphQLRouter

from src.schema import schema
from src.utils import Settings, get_settings, instrument_fastapi, setup_observability


_logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully-wired FastAPI application"""

    settings = settings or get_settings()
    service_version = version(settings.app_name)

    setup_observability(settings, version=service_version)

    app = FastAPI(
        title=settings.service_name,
        version=service_version,
        description="LLM-powered assistant used in smart-novel",
    )
    graphql_router: GraphQLRouter[None, None] = GraphQLRouter(schema)

    app.include_router(graphql_router, prefix="/graphql")
    instrument_fastapi(app)

    _logger.info(
        "%s ready",
        settings.service_name,
        extra={
            "service_name": settings.service_name,
            "service_version": service_version,
            "llm_model": settings.llm.model,
            "otel_enabled": settings.otel.enabled,
        },
    )

    return app


app = create_app() if __name__ != "__main__" else None


def main() -> None:
    """Entry point for ``python -m src.main`` / ``python src/main.py``."""

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=settings.port,
        log_config=None,  # we configure logging ourselves in setup_observability
        access_log=True,
    )


if __name__ == "__main__":
    main()
