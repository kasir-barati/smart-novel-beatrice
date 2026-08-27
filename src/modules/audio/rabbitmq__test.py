from __future__ import annotations

import json
from typing import Any

import pytest

from src.modules.audio import rabbitmq as rabbitmq_module
from src.modules.audio.rabbitmq import publish_generate_audio_job
from src.utils import RabbitMq


class _FakeQueue:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeExchange:
    def __init__(self, published: list[dict[str, Any]]) -> None:
        self._published = published

    async def publish(self, message: Any, *, routing_key: str) -> None:
        self._published.append(
            {
                "routing_key": routing_key,
                "body": message.body,
                "headers": message.headers,
                "content_type": message.content_type,
            }
        )


class _FakeChannel:
    def __init__(
        self, declared_queues: list[dict[str, Any]], published: list[dict[str, Any]]
    ) -> None:
        self._declared_queues = declared_queues
        self.default_exchange = _FakeExchange(published)

    async def declare_queue(
        self, name: str, *, durable: bool, arguments: dict[str, Any]
    ) -> _FakeQueue:
        self._declared_queues.append({"name": name, "durable": durable, "arguments": arguments})
        return _FakeQueue(name)


class _FakeConnection:
    def __init__(
        self, declared_queues: list[dict[str, Any]], published: list[dict[str, Any]]
    ) -> None:
        self._declared_queues = declared_queues
        self._published = published
        self.closed = False

    async def channel(self) -> _FakeChannel:
        return _FakeChannel(self._declared_queues, self._published)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_connection(monkeypatch: pytest.MonkeyPatch) -> tuple[_FakeConnection, list, list]:
    declared_queues: list[dict[str, Any]] = []
    published: list[dict[str, Any]] = []
    connection = _FakeConnection(declared_queues, published)

    async def _fake_connect_robust(url: str) -> _FakeConnection:
        return connection

    monkeypatch.setattr(rabbitmq_module.aio_pika, "connect_robust", _fake_connect_robust)

    return connection, declared_queues, published


async def test_publish_declares_a_durable_quorum_queue(
    fake_connection: tuple[_FakeConnection, list, list],
) -> None:
    _connection, declared_queues, _published = fake_connection

    await publish_generate_audio_job(
        settings=RabbitMq(), body={"jobId": "abc"}, headers={"timestamp": "now"}
    )

    assert declared_queues == [
        {
            "name": "beatrice.generate_audio",
            "durable": True,
            "arguments": {"x-queue-type": "quorum"},
        }
    ]


async def test_publish_sends_body_and_headers(
    fake_connection: tuple[_FakeConnection, list, list],
) -> None:
    _connection, _declared_queues, published = fake_connection

    await publish_generate_audio_job(
        settings=RabbitMq(),
        body={"jobId": "abc", "text": "hi"},
        headers={"timestamp": "2024-01-01T00:00:00Z", "authorization": "Bearer x"},
    )

    assert len(published) == 1
    assert json.loads(published[0]["body"]) == {"jobId": "abc", "text": "hi"}
    assert published[0]["headers"] == {
        "timestamp": "2024-01-01T00:00:00Z",
        "authorization": "Bearer x",
    }
    assert published[0]["routing_key"] == "beatrice.generate_audio"


async def test_publish_closes_the_connection(
    fake_connection: tuple[_FakeConnection, list, list],
) -> None:
    connection, _declared_queues, _published = fake_connection

    await publish_generate_audio_job(settings=RabbitMq(), body={}, headers={})

    assert connection.closed is True
