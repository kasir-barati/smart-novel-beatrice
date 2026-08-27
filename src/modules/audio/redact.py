"""
Presigned URL redaction for logs — the query string on a presigned URL carries the
signature/credentials, so it must never appear in plaintext logs.
"""

from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit


_logger = logging.getLogger(__name__)


def redact_presigned_url(url: str) -> str:
    """
    Strip the query string (signature, credentials, expiry, ...) from a presigned URL,
    keeping the scheme/host/path visible for debugging. Falls back to the plain URL —
    logging a warning — if redaction itself fails, so a bug here never silently
    swallows the log line it was supposed to protect.
    """

    try:
        parsed = urlsplit(url)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except Exception as exc:
        _logger.warning(
            "Failed to redact presigned URL for logging; logging it unredacted",
            extra={"exception_type": type(exc).__name__, "exception_message": str(exc)},
            exc_info=exc,
        )
        return url
