from __future__ import annotations

import unittest
from unittest.mock import patch

from app.core.config import Settings
from app.core.container import AppContainer


class HealthyDependency:
    async def check_connection(self) -> None:
        return None


class FakeResponse:
    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None

    async def get(self, url: str, *, headers: dict[str, str]) -> FakeResponse:
        self.requests.append((url, headers))
        return FakeResponse()


class ContainerReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_readiness_checks_azure_openai_v1_with_api_key(self) -> None:
        settings = Settings(
            azure_openai_endpoint="https://example.openai.azure.com/",
            azure_openai_api_key="secret",
        )
        container = AppContainer(settings)
        container.users = HealthyDependency()  # type: ignore[assignment]
        container.robot = HealthyDependency()  # type: ignore[assignment]
        client = FakeHttpClient()

        with patch("app.core.container.httpx.AsyncClient", return_value=client):
            errors = await container._run_readiness_checks()

        self.assertEqual(errors, [])
        self.assertEqual(
            client.requests,
            [
                (
                    "https://example.openai.azure.com/openai/v1/models",
                    {"api-key": "secret"},
                )
            ],
        )


if __name__ == "__main__":
    unittest.main()
