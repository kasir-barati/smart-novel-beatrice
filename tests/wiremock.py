"""
Minimal WireMock admin API client for stubbing and inspecting callback requests
(``statusCallbackUrl``, ``genUploadUrl``) in integration tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class WireMockClient:
    admin_base_url: str

    def stub(
        self,
        method: str,
        url_path_pattern: str,
        status: int = 200,
        json_body: dict[str, Any] | None = None,
    ) -> None:
        """Register a stub mapping. Matches are additive until ``reset_all`` is called."""

        response: dict[str, Any] = {"status": status}
        if json_body is not None:
            response["jsonBody"] = json_body

        httpx.post(
            f"{self.admin_base_url}/__admin/mappings",
            json={
                "request": {"method": method.upper(), "urlPathPattern": url_path_pattern},
                "response": response,
            },
        ).raise_for_status()

    def requests_for(self, url_path_pattern: str) -> list[dict[str, Any]]:
        """Return the recorded requests matching the given path pattern, in order received."""

        result = httpx.post(
            f"{self.admin_base_url}/__admin/requests/find",
            json={"method": "ANY", "urlPathPattern": url_path_pattern},
        )
        result.raise_for_status()
        return result.json()["requests"]

    def reset_all(self) -> None:
        """Clear all stub mappings and the request journal — call between tests."""

        httpx.post(f"{self.admin_base_url}/__admin/reset").raise_for_status()
