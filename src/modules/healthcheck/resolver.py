from __future__ import annotations

from importlib.metadata import version

import strawberry

from src.utils import get_settings, spectaql_example


@strawberry.type(description="Snapshot of service liveness and configured model.")
class HealthCheck:
    is_running: bool = strawberry.field(
        description="Always true when this resolver executes.",
        directives=[spectaql_example(True)],
    )
    model: str = strawberry.field(
        description="LLM model this service is currently configured to use.",
        directives=[spectaql_example("qwen2.5:3b")],
    )
    version: str = strawberry.field(
        description=(
            "Service version — matches the Docker Hub image tag published from the same commit."
        ),
        directives=[spectaql_example("1.0.1")],
    )


def healthcheck() -> HealthCheck:
    """Healthcheck resolver for the GraphQL API"""
    settings = get_settings()

    return HealthCheck(
        is_running=True,
        model=settings.llm.model,
        version=version(settings.app_name),
    )
