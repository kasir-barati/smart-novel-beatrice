"""
Single owner of the status-callback HTTP call for the audio module — both the
`generateAudio` resolver (`queued`) and the worker (`generating`/`uploading`/
`completed`/`failed`) call `report` instead of each building their own
`httpx.AsyncClient`.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.modules.audio.callback_urls import CallbackUrlNotAllowedError, validate_callback_url


_logger = logging.getLogger(__name__)

_PROGRESS_BY_STATUS = {"queued": 1, "generating": 2, "uploading": 3}


async def report(
    status_callback_url: str,
    status: str,
    *,
    job_id: str,
    client_context_id: str | None,
    authorization: str | None,
    revalidate: bool = False,
    **extra: Any,
) -> None:
    """
    Best-effort — a failed delivery is logged and swallowed, never raised, so it can't
    fail the mutation or job processing.

    `revalidate=True` re-checks `status_callback_url` against the host allow-list
    first: the worker's call crossed a RabbitMQ hop since the resolver's own
    `validate_callback_url` call, so it can't trust that check carried across:
    the resolver's own call doesn't need this, since nothing crossed a queue hop.
    """

    if revalidate:
        try:
            validate_callback_url(status_callback_url)
        except CallbackUrlNotAllowedError as exc:
            _logger.warning(
                "Refusing to call statusCallbackUrl: failed allow-list re-validation",
                extra={"job_id": job_id, "status": status, "exception_message": str(exc)},
            )
            return

    body: dict[str, Any] = {"status": status, "jobId": job_id, **extra}
    progress_rank = _PROGRESS_BY_STATUS.get(status)
    if progress_rank is not None:
        body["progress"] = progress_rank
    if client_context_id is not None:
        body["clientContextId"] = client_context_id
    headers = {"authorization": authorization} if authorization is not None else {}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(status_callback_url, json=body, headers=headers)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        _logger.warning(
            "Failed to call statusCallbackUrl",
            extra={
                "job_id": job_id,
                "status": status,
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
            },
            exc_info=exc,
        )
