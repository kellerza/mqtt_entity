"""Tests for MQTTAsyncClient reconnect behavior."""

import asyncio
import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mqtt_entity.client import MQTTAsyncClient


@pytest.mark.asyncio
async def test_reconnect_loop_started_on_socket_close() -> None:
    """Socket close starts a background reconnect loop."""
    mqc = MQTTAsyncClient()
    loop = asyncio.get_running_loop()
    mqc._loop = loop
    mqc._should_reconnect = True
    await mqc.client.async_start(loop)
    mqc.client._socket_close_listener = mqc._on_connection_lost

    sock = MagicMock(spec=socket.socket)
    sock.fileno.return_value = 1
    mqc.client._async_on_socket_close(mqc.client, None, sock)

    assert mqc._reconnect_task is not None
    mqc._cancel_reconnect()


@pytest.mark.asyncio
async def test_reconnect_cancelled_on_successful_connect() -> None:
    """Successful on_connect cancels the reconnect loop."""
    mqc = MQTTAsyncClient()
    mqc._loop = asyncio.get_running_loop()
    mqc._reconnect_task = mqc._loop.create_task(asyncio.sleep(60))

    mqc._mqtt_on_connect(mqc.client, None, MagicMock(), 0)

    assert mqc._reconnect_task is None


@pytest.mark.asyncio
async def test_disconnect_disables_reconnect() -> None:
    """disconnect prevents reconnect attempts after shutdown."""
    mqc = MQTTAsyncClient()
    loop = asyncio.get_running_loop()
    mqc._loop = loop
    mqc._should_reconnect = True
    await mqc.client.async_start(loop)
    mqc._reconnect_task = loop.create_task(asyncio.sleep(60))

    await mqc.disconnect()

    assert mqc._should_reconnect is False
    assert mqc._reconnect_task is None


@pytest.mark.asyncio
async def test_reconnect_loop_calls_reconnect() -> None:
    """Reconnect loop calls paho reconnect while disconnected."""
    mqc = MQTTAsyncClient()
    loop = asyncio.get_running_loop()
    mqc._loop = loop
    mqc._should_reconnect = True
    await mqc.client.async_start(loop)

    async def stop_after_one(_delay: float) -> None:
        mqc._should_reconnect = False

    with patch.object(mqc.client, "is_connected", return_value=False):
        with patch(
            "mqtt_entity.client.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=0,
        ) as to_thread:
            with patch("mqtt_entity.client.asyncio.sleep", side_effect=stop_after_one):
                await mqc._reconnect_loop()

    to_thread.assert_awaited_once_with(mqc.client.reconnect)
