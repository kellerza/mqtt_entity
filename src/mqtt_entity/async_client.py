"""Async wrappings for mqtt client.

https://github.com/home-assistant/core/blob/dev/homeassistant/components/mqtt/async_client.py
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
from collections.abc import AsyncGenerator, Callable
from functools import lru_cache
from types import TracebackType
from typing import Any, Self, cast

import paho.mqtt.client as mqtt
from paho.mqtt.client import (
    CallbackOnPublish_v2,
    CallbackOnSocket,
    CallbackOnSubscribe_v2,
    CallbackOnUnsubscribe_v2,
    Client,
)
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

_LOG = logging.getLogger(__name__)

_MQTT_LOCK_COUNT = 7
_MAX_PACKETS_TO_READ = 500
_TIMEOUT_ACK = 10


class NullLock:
    """Null lock."""

    @lru_cache(maxsize=_MQTT_LOCK_COUNT)
    def __enter__(self) -> Self:
        """Enter the lock."""
        return self

    @lru_cache(maxsize=_MQTT_LOCK_COUNT)
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Exit the lock."""

    @lru_cache(maxsize=_MQTT_LOCK_COUNT)
    def acquire(self, blocking: bool = False, timeout: int = -1) -> None:
        """Acquire the lock."""

    @lru_cache(maxsize=_MQTT_LOCK_COUNT)
    def release(self) -> None:
        """Release the lock."""


class AClient(Client):
    """Async MQTT Client.

    Wrapper around paho.mqtt.client.Client to remove the locking
    that is not needed since we are running in an async event loop,
    and to drive the network loop via asyncio socket readers/writers.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize async MQTT client state."""
        super().__init__(*args, **kwargs)
        self._event_loop: asyncio.AbstractEventLoop | None = None
        self._misc_timer: asyncio.TimerHandle | None = None
        self._pending_operations: dict[int, asyncio.Future[None]] = {}
        self._connection_lock = asyncio.Lock()
        self._started = False
        self._socket_close_listener: Callable[[], None] | None = None
        self._chained_on_publish: CallbackOnPublish_v2 | None = None
        self._chained_on_subscribe: CallbackOnSubscribe_v2 | None = None
        self._chained_on_unsubscribe: CallbackOnUnsubscribe_v2 | None = None

    def _setup(self) -> None:
        """Set up the client.

        All the threading locks are replaced with NullLock
        since the client is running in an async event loop
        and will never run in multiple threads.
        """
        self._in_callback_mutex = NullLock()  # type: ignore[assignment]
        self._callback_mutex = NullLock()  # type: ignore[assignment]
        self._msgtime_mutex = NullLock()  # type: ignore[assignment]
        self._out_message_mutex = NullLock()  # type: ignore[assignment]
        self._in_message_mutex = NullLock()  # type: ignore[assignment]
        self._reconnect_delay_mutex = NullLock()  # type: ignore[assignment]
        self._mid_generate_mutex = NullLock()  # type: ignore[assignment]

    async def async_start(self, loop: asyncio.AbstractEventLoop) -> None:
        """Wire paho socket callbacks to the asyncio event loop."""
        if self._started:
            return
        self._setup()
        self._event_loop = loop
        self._chain_mid_callbacks()
        self.on_socket_close = cast(CallbackOnSocket, self._async_on_socket_close)
        self.on_socket_unregister_write = cast(
            CallbackOnSocket, self._async_on_socket_unregister_write
        )
        self.on_socket_open = cast(CallbackOnSocket, self._async_on_socket_open)
        self.on_socket_register_write = cast(
            CallbackOnSocket, self._async_on_socket_register_write
        )
        self._started = True

    async def async_stop(self) -> None:
        """Stop the asyncio network loop without disconnecting.

        Skipping disconnect allows the broker to publish the LWT message.
        """
        if not self._started or self._event_loop is None:
            return
        if self._misc_timer:
            self._misc_timer.cancel()
            self._misc_timer = None
        sock = self.socket()
        if sock is not None:
            fileno = sock.fileno()
            if fileno > -1:
                self._event_loop.remove_reader(sock)
                self._event_loop.remove_writer(sock)
        self._started = False

    async def async_connect(
        self,
        host: str,
        port: int = 1883,
        keepalive: int = 60,
    ) -> None:
        """Connect to the MQTT broker."""
        async with self._connection_lock, self._connect_in_executor():
            result = await asyncio.to_thread(self.connect, host, port, keepalive)
        if result != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(f"MQTT connect failed: {mqtt.error_string(result)}")

    async def async_publish(
        self,
        topic: str,
        payload: str | bytes | bytearray | float | None = None,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """Publish a MQTT message and wait for broker ACK."""
        msg_info = self.publish(topic, payload, qos, retain)
        await self._async_wait_for_mid_or_raise(msg_info.mid, msg_info.rc)

    async def async_subscribe(
        self,
        topic: str,
        qos: int = 0,
    ) -> None:
        """Subscribe to a topic and wait for broker ACK."""
        _result, mid = self.subscribe(topic, qos)
        await self._async_wait_for_mid_or_raise(mid, mqtt.MQTT_ERR_SUCCESS)

    async def async_unsubscribe(self, topic: str) -> None:
        """Unsubscribe from a topic and wait for broker ACK."""
        _result, mid = self.unsubscribe(topic)
        await self._async_wait_for_mid_or_raise(mid, mqtt.MQTT_ERR_SUCCESS)

    def _chain_mid_callbacks(self) -> None:
        """Wrap publish/subscribe callbacks to resolve pending mid futures."""
        if self.on_publish is not self._async_on_publish:
            self._chained_on_publish = cast(
                CallbackOnPublish_v2 | None, self.on_publish
            )
            self.on_publish = cast(CallbackOnPublish_v2, self._async_on_publish)
        if self.on_subscribe is not self._async_on_subscribe:
            self._chained_on_subscribe = cast(
                CallbackOnSubscribe_v2 | None, self.on_subscribe
            )
            self.on_subscribe = cast(CallbackOnSubscribe_v2, self._async_on_subscribe)
        if self.on_unsubscribe is not self._async_on_unsubscribe:
            self._chained_on_unsubscribe = cast(
                CallbackOnUnsubscribe_v2 | None, self.on_unsubscribe
            )
            self.on_unsubscribe = cast(
                CallbackOnUnsubscribe_v2, self._async_on_unsubscribe
            )

    @contextlib.asynccontextmanager
    async def _connect_in_executor(self) -> AsyncGenerator[None]:
        """Handle socket callbacks on the executor thread during connect."""
        try:
            self.on_socket_open = cast(
                CallbackOnSocket, self._on_socket_open_threadsafe
            )
            self.on_socket_register_write = cast(
                CallbackOnSocket, self._on_socket_register_write_threadsafe
            )
            yield
        finally:
            self.on_socket_open = cast(CallbackOnSocket, self._async_on_socket_open)
            self.on_socket_register_write = cast(
                CallbackOnSocket, self._async_on_socket_register_write
            )

    def _reader_callback(self) -> None:
        """Handle reading data from the socket."""
        if (status := self.loop_read(_MAX_PACKETS_TO_READ)) != mqtt.MQTT_ERR_SUCCESS:
            _LOG.warning(
                "MQTT: Error returned from loop_read: %s",
                mqtt.error_string(status),
            )

    def _writer_callback(self) -> None:
        """Handle writing data to the socket."""
        if (status := self.loop_write()) != mqtt.MQTT_ERR_SUCCESS:
            _LOG.warning(
                "MQTT: Error returned from loop_write: %s",
                mqtt.error_string(status),
            )

    def _start_misc_periodic(self) -> None:
        """Schedule loop_misc on the asyncio event loop."""
        if self._event_loop is None or self._misc_timer is not None:
            return

        def _async_misc() -> None:
            if self._event_loop is None:
                return
            if self.loop_misc() == mqtt.MQTT_ERR_SUCCESS:
                self._misc_timer = self._event_loop.call_at(
                    self._event_loop.time() + 1, _async_misc
                )

        self._misc_timer = self._event_loop.call_at(
            self._event_loop.time() + 1, _async_misc
        )

    def _on_socket_open_threadsafe(
        self, client: mqtt.Client, userdata: Any, sock: socket.socket
    ) -> None:
        """Handle socket open from the executor thread."""
        if self._event_loop is not None:
            self._event_loop.call_soon_threadsafe(
                self._async_on_socket_open, client, userdata, sock
            )

    def _on_socket_register_write_threadsafe(
        self, client: mqtt.Client, userdata: Any, sock: socket.socket
    ) -> None:
        """Register the socket for writing from the executor thread."""
        if self._event_loop is not None:
            self._event_loop.call_soon_threadsafe(
                self._async_on_socket_register_write, client, userdata, sock
            )

    def _async_on_socket_open(
        self, client: mqtt.Client, userdata: Any, sock: socket.socket
    ) -> None:
        """Handle socket open on the event loop."""
        if self._event_loop is None:
            return
        fileno = sock.fileno()
        if fileno > -1:
            self._event_loop.add_reader(sock, self._reader_callback)
            if not self._misc_timer:
                self._start_misc_periodic()
            self._reader_callback()

    def _async_on_socket_close(
        self, client: mqtt.Client, userdata: Any, sock: socket.socket
    ) -> None:
        """Handle socket close on the event loop."""
        if self._event_loop is None:
            return
        fileno = sock.fileno()
        if fileno > -1:
            self._event_loop.remove_reader(sock)
        if self._misc_timer:
            self._misc_timer.cancel()
            self._misc_timer = None
        if self._socket_close_listener:
            self._socket_close_listener()

    def _async_on_socket_register_write(
        self, client: mqtt.Client, userdata: Any, sock: socket.socket
    ) -> None:
        """Register the socket for writing on the event loop."""
        if self._event_loop is None:
            return
        fileno = sock.fileno()
        if fileno > -1:
            self._event_loop.add_writer(sock, self._writer_callback)

    def _async_on_socket_unregister_write(
        self, client: mqtt.Client, userdata: Any, sock: socket.socket
    ) -> None:
        """Unregister the socket for writing on the event loop."""
        if self._event_loop is None:
            return
        fileno = sock.fileno()
        if fileno > -1:
            self._event_loop.remove_writer(sock)

    def _async_on_publish(
        self,
        client: mqtt.Client,
        userdata: Any,
        mid: int,
        reason_code: ReasonCode,
        properties: Properties,
    ) -> None:
        """Publish callback."""
        self._resolve_mid(mid)
        if self._chained_on_publish:
            self._chained_on_publish(client, userdata, mid, reason_code, properties)

    def _async_on_subscribe(
        self,
        client: mqtt.Client,
        userdata: Any,
        mid: int,
        reason_code: list[ReasonCode],
        properties: Properties | None,
    ) -> None:
        """Subscribe callback."""
        self._resolve_mid(mid)
        if self._chained_on_subscribe:
            self._chained_on_subscribe(client, userdata, mid, reason_code, properties)

    def _async_on_unsubscribe(
        self,
        client: mqtt.Client,
        userdata: Any,
        mid: int,
        reason_code: list[ReasonCode],
        properties: Properties | None,
    ) -> None:
        """Unsubscribe callback."""
        self._resolve_mid(mid)
        if self._chained_on_unsubscribe:
            self._chained_on_unsubscribe(client, userdata, mid, reason_code, properties)

    def _resolve_mid(self, mid: int) -> None:
        """Resolve a pending mid future."""
        future = self._pending_operations.get(mid)
        if future is None or future.done():
            return
        future.set_result(None)

    def _get_mid_future(self, mid: int) -> asyncio.Future[None]:
        """Get or create the future for a mid."""
        if future := self._pending_operations.get(mid):
            return future
        if self._event_loop is None:
            raise RuntimeError("MQTT: async_start() must be called first")
        future = self._event_loop.create_future()
        self._pending_operations[mid] = future
        return future

    def _timeout_mid(self, future: asyncio.Future[None]) -> None:
        """Timeout waiting for a mid."""
        if not future.done():
            future.set_exception(TimeoutError())

    async def _async_wait_for_mid_or_raise(
        self, mid: int | None, result_code: int
    ) -> None:
        """Wait for ACK from broker or raise on error."""
        if result_code != mqtt.MQTT_ERR_SUCCESS:
            raise ConnectionError(
                f"MQTT broker error: {mqtt.error_string(result_code)}"
            )
        if mid is None:
            return
        future = self._get_mid_future(mid)
        if self._event_loop is None:
            raise RuntimeError("MQTT: async_start() must be called first")
        timer_handle = self._event_loop.call_later(
            _TIMEOUT_ACK, self._timeout_mid, future
        )
        try:
            await future
        except TimeoutError:
            _LOG.warning("MQTT: No ACK from broker in %ss (mid: %s)", _TIMEOUT_ACK, mid)
        finally:
            timer_handle.cancel()
            self._pending_operations.pop(mid, None)
