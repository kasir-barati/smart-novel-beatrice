from __future__ import annotations

import os


def _sanitize_env_for_tests() -> None:
    """Force OTel off and drop stale exporter endpoints from a dev ``.env``."""

    os.environ["OTEL__ENABLED"] = "false"
    for key in list(os.environ):
        if key.startswith("OTEL__EXPORTER_"):
            os.environ.pop(key, None)


_sanitize_env_for_tests()
