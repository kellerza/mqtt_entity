"""MQTTClient."""

from __future__ import annotations

import asyncio
import importlib.metadata
import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Coroutine, Generator
from dataclasses import dataclass, field
from json import dumps
from typing import Any, cast

import paho.mqtt.client as mqtt
from paho.mqtt.client import (
    CallbackOnConnect_v2,
    CallbackOnDisconnect_v2,
    CallbackOnMessage,
    ConnectFlags,
    DisconnectFlags,
    MQTTMessage,
)
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.matcher import MQTTMatcher
from paho.mqtt.properties import Properties
from paho.mqtt.reasoncodes import ReasonCode

from .async_client import AClient
from .device import MQTTDevice, MQTTOrigin
from .utils import load_json

HA_STATUS_TOPIC = "homeassistant/status"
_LOG = logging.getLogger(__name__)
MQTT_EXPLORER_LIMIT = 20000
_RECONNECT_INTERVAL_SECONDS = 10
_DISCOVERY_INTERVAL_SECONDS = 5

type TopicCallback = (
    Callable[[str, str], Coroutine[Any, Any, None]]
    | Callable[[str], Coroutine[Any, Any, None]]
)


@dataclass()
class MQTTAsyncClient:
    """Async MQTT Client."""

    availability_topic: str = ""
    client: AClient = field(init=False, repr=False)
    suppress_exceptions: bool = True
    connect_time: float = field(init=False, repr=False)

    _on_message_filtered: MQTTMatcher2 = field(
        default_factory=lambda: MQTTMatcher2(),  # noqa: PLW0108
        repr=False,
    )
    _loop: asyncio.AbstractEventLoop = field(init=False, repr=False)
    _should_reconnect: bool = field(init=False, repr=False)
    _reconnect_task: asyncio.Task[None] | None = field(init=False, repr=False)
    _connect_host: str = field(init=False, repr=False)
    _connect_port: int = field(init=False, repr=False)
    _connect_keepalive: int = field(init=False, repr=False)
    _subscribe_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _broker_topics: set[str] = field(default_factory=set, repr=False)
    """Topics successfully SUBSCRIBEd on the current broker connection."""
    _ha_online: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        """Init."""
        self.connect_time = 0
        self._should_reconnect = False
        self._reconnect_task = None
        self._connect_host = ""
        self._connect_port = 1883
        self._connect_keepalive = 60
        self.client = AClient(
            callback_api_version=CallbackAPIVersion.VERSION2,
            reconnect_on_failure=False,
        )
        self.client.on_connect = cast(CallbackOnConnect_v2, self._mqtt_on_connect)
        self.client.on_disconnect = cast(
            CallbackOnDisconnect_v2, self._mqtt_on_disconnect
        )
        self.client.on_message = cast(CallbackOnMessage, self._mqtt_on_message)

    async def connect(
        self,
        options: Any = None,
        *,
        username: str = "",
        password: str = "",
        host: str = "core-mosquitto",
        port: int = 1883,
        wait_connected: bool = False,
    ) -> None:
        """Connect to MQTT server specified as attributes of the options."""
        reconnecting = self.client.is_connected()
        if reconnecting:
            _LOG.warning("MQTT: Client connected. Reconnecting...")
        await self.disconnect()  # "Connection Successful" triggered on re-connect
        if reconnecting and self.client.is_connected():
            await asyncio.to_thread(self.client.disconnect)
        self._loop = asyncio.get_running_loop()

        if options:
            username = getattr(options, "mqtt_username", username)
            password = getattr(options, "mqtt_password", password)
            host = getattr(options, "mqtt_host", host)
            port = getattr(options, "mqtt_port", port)
        self.client.username_pw_set(username=username, password=password)

        if self.availability_topic:
            self.client.will_set(self.availability_topic, "offline", retain=True)

        _LOG.info("MQTT: Connecting to %s@%s:%s", username, host, port)
        self._connect_host = host
        self._connect_port = port
        self._connect_keepalive = 60
        self._should_reconnect = True
        self._cancel_reconnect()
        await self.client.async_start(self._loop)
        self.client._socket_close_listener = self._on_connection_lost
        self.connect_time = time.time() + 5
        try:
            await self.client.async_connect(host=host, port=port)
        except ConnectionError:
            self.connect_time = -1
            raise

        if wait_connected:
            await self.wait_connected()

    def _on_connection_lost(self) -> None:
        """Start reconnect after the broker connection is lost."""
        if self._should_reconnect and not self._reconnect_task:
            self._reconnect_task = self._loop.create_task(self._reconnect_loop())

    def _cancel_reconnect(self) -> None:
        """Cancel the reconnect loop."""
        if self._reconnect_task is None:
            return
        self._reconnect_task.cancel()
        self._reconnect_task = None

    async def _reconnect_loop(self) -> None:
        """Reconnect to the MQTT broker until connected or stopped."""
        try:
            while self._should_reconnect:
                if not self.client.is_connected():
                    try:
                        async with (
                            self.client._connection_lock,
                            self.client._connect_in_executor(),
                        ):
                            result = await asyncio.to_thread(self.client.reconnect)
                        if result != mqtt.MQTT_ERR_SUCCESS:
                            _LOG.debug(
                                "MQTT: Reconnect failed: %s",
                                mqtt.error_string(result),
                            )
                    except (OSError, ValueError, mqtt.WebsocketConnectionError) as err:
                        _LOG.debug("MQTT: Reconnect error: %s", err)
                await asyncio.sleep(_RECONNECT_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            return
        finally:
            self._reconnect_task = None

    def _mqtt_on_disconnect(
        self,
        _client: AClient,
        _userdata: Any,
        _disconnect_flags: DisconnectFlags,
        _reason_code: ReasonCode,
        _properties: Properties | None = None,
    ) -> None:
        """MQTT on_disconnect callback."""
        self._ha_online = False
        self._on_connection_lost()

    def _mqtt_on_connect(
        self,
        client: AClient,
        userdata: Any,
        flags: ConnectFlags,
        reason_code: ReasonCode,
        properties: Properties | None = None,
    ) -> None:
        """MQTT on_connect callback."""
        if reason_code != 0:
            _LOG.error("MQTT: Connection failed with reason code %s", reason_code)
            self.connect_time = -1  # failed
            return
        self._cancel_reconnect()
        _LOG.info("MQTT: Connected")
        # Broker drops subscriptions on a new session; clear before any
        # concurrent topic_subscribe() can race with _resubscribe_topics().
        self._broker_topics.clear()
        # Do not clear _ha_online here: a second CONNACK / resubscribe would
        # redeliver retained homeassistant/status and republish discovery.
        # Offline is tracked via the status topic (and disconnect below).
        # publish online (Last will sets offline on disconnect)
        if self.availability_topic:
            client.publish(self.availability_topic, "online", retain=True)
        # Subscribe to all existing change handlers (on connect/reconnect).
        self._loop.create_task(self._resubscribe_topics())

    async def wait_connected(self) -> None:
        """Wait until connected."""
        if self.client.is_connected():
            return
        if self.connect_time == 0:
            raise RuntimeError("MQTT: Call connect first")
        # If the original deadline has already passed, the reconnect loop
        # may be in progress. Give it a fresh window instead of failing
        # immediately with a stale deadline from the initial connect().
        if self.connect_time > 0 and time.time() > self.connect_time:
            _LOG.warning("MQTT: Connection lost. Waiting for reconnect...")
            self.connect_time = time.time() + 30
        _LOG.debug("MQTT: Waiting for connection...")
        while True:
            if self.client.is_connected():
                return
            await asyncio.sleep(0.1)
            if time.time() > self.connect_time:
                if self.connect_time < 0:
                    raise ConnectionError("MQTT: Connection failed")
                msg = "MQTT: Connection timeout (30s)"
                _LOG.error(msg)
                raise ConnectionError(msg)

    async def disconnect(self) -> None:
        """Stop the MQTT client."""
        self._should_reconnect = False
        self._cancel_reconnect()
        self.client._socket_close_listener = None
        await self.client.async_stop()

    async def _resubscribe_topics(self) -> None:
        """Re-subscribe all registered topics after connect/reconnect."""
        # Snapshot keys to avoid RuntimeError from concurrent modification.
        # Skip topics already SUBSCRIBEd by a concurrent topic_subscribe() so
        # retained messages (e.g. homeassistant/status) are not delivered twice.
        async with self._subscribe_lock:
            for topic in list(self._on_message_filtered.keys()):
                if topic in self._broker_topics:
                    continue
                await self.client.async_subscribe(topic)
                self._broker_topics.add(topic)

    def publish_args(
        self, topic: str, payload: str | None, qos: int, retain: bool
    ) -> tuple[str, str | None, int, bool]:
        """Prep publish parameters."""
        if not topic:
            raise ValueError(f"MQTT: Cannot publish to empty topic (payload={payload})")
        if not isinstance(qos, int):
            qos = 0
        if retain:
            qos = 1
        _LOG.debug(
            "MQTT: Publish %s%s %s, %s", qos, "R" if retain else "", topic, payload
        )
        if payload and len(payload) > MQTT_EXPLORER_LIMIT:
            _LOG.info(
                "MQTT: Payload >%s: %s (MQTTExplorer will truncate the message)",
                MQTT_EXPLORER_LIMIT,
                len(payload),
            )
        return (topic, payload, qos, bool(retain))

    async def publish(
        self,
        topic: str,
        payload: str | None = None,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """Publish a MQTT message."""
        args = self.publish_args(topic, payload, qos, retain)
        await self.wait_connected()
        await self.client.async_publish(*args)

    async def topic_unsubscribe(self, topic: str) -> None:
        """Remove a topic from the topic callbacks."""
        await self.wait_connected()
        async with self._subscribe_lock:
            await self.client.async_unsubscribe(topic)
            self._broker_topics.discard(topic)
        self._on_message_filtered.pop(topic)

    async def topic_subscribe(self, topic: str, callback: TopicCallback) -> None:
        """Add a topic to the topic callbacks."""
        _LOG.debug("MQTT: Add callback for topic %s", topic)
        self._on_message_filtered[topic] = callback
        await self.wait_connected()
        async with self._subscribe_lock:
            if topic in self._broker_topics:
                return
            await self.client.async_subscribe(topic)
            self._broker_topics.add(topic)

    def _mqtt_on_message(
        self, client: AClient, userdata: Any, message: MQTTMessage
    ) -> None:
        """MQTT on_message fallback."""
        topic = message.topic
        payload = message.payload.decode("utf-8")
        if not topic:
            _LOG.warning("MQTT: received empty topic, payload: %s", payload)
            return

        matched = list[tuple[TopicCallback, tuple[str, ...]]]()
        for cb in self._on_message_filtered.iter_match(topic):
            cnt = len(inspect.signature(cb).parameters)
            args: tuple[str, ...] = (payload,) if cnt == 1 else (payload, message.topic)
            matched.append((cb, args))

        if not matched:
            _LOG.warning(
                "MQTT: Unhandled msg received. Topic %s with payload %s", topic, payload
            )
            return

        async def run() -> None:
            """Dispatch topic callbacks."""
            for cb, args in matched:
                name = cb.__name__
                try:
                    _LOG.debug("MQTT: Callback %s(%s, topic=%s)", name, payload, topic)
                    await cb(*args)
                except Exception as err:
                    _LOG.error(
                        "MQTT: Exception in callback %s(topic=%s): %s", name, topic, err
                    )
                    if not self.suppress_exceptions:
                        raise

        self._loop.create_task(run())


@dataclass()
class MQTTClient(MQTTAsyncClient):
    """Home Assistant specific MQTT client."""

    devs: list[MQTTDevice] = field(default_factory=list)

    origin_name: str = "mqtt-entity"
    origin_version: str = field(
        default_factory=lambda: importlib.metadata.version("mqtt-entity")
    )
    origin_url: str = ""
    clean_entities: int = 1
    """Clean entities on discovery: 1=migrate, 2=remove, 0=none."""

    on_ha_connected: Callable[[], Awaitable[None]] | None = None
    """Callback to be called when the client & Home Assistant are connected."""

    _clean_unsubscribe_task: asyncio.Task[None] | None = field(
        default=None,
        repr=False,
    )
    _discovery_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _discovery_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _last_discovery: dict[str, str] = field(default_factory=dict, repr=False)
    """Last published discovery payload per topic."""

    def _mqtt_on_disconnect(
        self,
        _client: AClient,
        _userdata: Any,
        _disconnect_flags: DisconnectFlags,
        _reason_code: ReasonCode,
        _properties: Properties | None = None,
    ) -> None:
        """MQTT on_disconnect callback."""
        self._cancel_discovery_loop()
        self._last_discovery.clear()
        super()._mqtt_on_disconnect(
            _client, _userdata, _disconnect_flags, _reason_code, _properties
        )

    async def disconnect(self) -> None:
        """Stop the MQTT client."""
        self._cancel_discovery_loop()
        await super().disconnect()

    def _cancel_discovery_loop(self) -> None:
        """Stop the HA-online discovery poll."""
        if self._discovery_task is None:
            return
        self._discovery_task.cancel()
        self._discovery_task = None

    def _start_discovery_loop(self) -> None:
        """Poll for changed discovery while Home Assistant is online."""
        if self._discovery_task is not None and not self._discovery_task.done():
            return
        self._discovery_task = asyncio.get_running_loop().create_task(
            self._discovery_loop()
        )

    async def _discovery_loop(self) -> None:
        """Republish discovery when a device payload changes."""
        try:
            while self._ha_online:
                await asyncio.sleep(_DISCOVERY_INTERVAL_SECONDS)
                if not self._ha_online:
                    return
                async with self._discovery_lock:
                    await self._publish_device_config()
        except asyncio.CancelledError:
            return
        finally:
            self._discovery_task = None

    async def monitor_homeassistant_status(self) -> None:
        """Monitor homeassistant/status & publish discovery info."""
        if HA_STATUS_TOPIC in self._on_message_filtered:
            return

        async def _timeout() -> None:
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                return
            _LOG.warning(
                "MQTT: Timeout waiting for Home Assistant. The %s topic is empty.\n"
                "Configure the MQTT integration in Home Assistant to publish a "
                "last will & testament (online/offline) with the Retain flag set.",
                HA_STATUS_TOPIC,
            )
            _LOG.warning(
                "MQTT: Your entities will be unavailable if HA restarts",
            )
            await self.publish_discovery_info()

        timeout = asyncio.create_task(_timeout())

        async def _online_cb(payload_s: str, _: str) -> None:
            """Republish discovery info."""
            if payload_s != "online":
                self._ha_online = False
                self._cancel_discovery_loop()
                self._last_discovery.clear()
                _LOG.warning(
                    "MQTT: Home Assistant offline. %s = %s", HA_STATUS_TOPIC, payload_s
                )
                return
            timeout.cancel()
            # Check+set under the discovery lock so concurrent retained
            # redeliveries cannot both pass a unlocked _ha_online guard.
            async with self._discovery_lock:
                if self._ha_online:
                    return
                self._ha_online = True
                _LOG.info(
                    "MQTT: Home Assistant online. Publish discovery info for %s",
                    [d.name for d in self.devs],
                )
                await self._publish_discovery_info_locked()
                self._start_discovery_loop()

        await self.topic_subscribe(HA_STATUS_TOPIC, _online_cb)
        if self.connect_time == 0:
            raise ConnectionError()

    async def publish_discovery_info(self) -> None:
        """Publish discovery info immediately."""
        async with self._discovery_lock:
            await self._publish_discovery_info_locked()

    async def _subscribe_device_commands(self, ddev: MQTTDevice) -> None:
        tcb = dict[str, TopicCallback]()
        for ent in ddev.components.values():
            tcb.update(ent.topic_callbacks)
        for topic, cbk in tcb.items():
            await self.topic_subscribe(topic, cbk)

    async def _publish_device_config(self) -> None:
        """Publish discovery for each device, skipping unchanged payloads."""
        origin = MQTTOrigin(
            name=self.origin_name,
            sw=self.origin_version,
            url=self.origin_url,
        )
        for ddev in self.devs:
            disco_topic, disco_payload = ddev.discovery_info(
                availability_topic=self.availability_topic,
                origin=origin,
            )
            if self._last_discovery.get(disco_topic) == disco_payload:
                _LOG.debug("MQTT: Skip unchanged discovery %s", disco_topic)
            else:
                self._last_discovery[disco_topic] = disco_payload
                try:
                    await self.publish(disco_topic, disco_payload)
                except Exception:
                    self._last_discovery.pop(disco_topic)
                    raise
            await self._subscribe_device_commands(ddev)

    async def _publish_discovery_info_locked(self) -> None:
        """Publish discovery info (caller holds ``_discovery_lock``)."""
        if not self.devs:
            _LOG.warning("MQTT: No devices to publish discovery info for")
            return

        if self.clean_entities:
            await self._clean_entity_based_discovery()
            await asyncio.sleep(1)

        await self._publish_device_config()

        await self.publish_availability(self.availability_topic, True, retain=True)
        if self.on_ha_connected:
            await self.on_ha_connected()

    async def publish_availability(
        self, topic: str, online: bool, retain: bool = False
    ) -> None:
        """Publish availability topic."""
        await self.publish(topic, "online" if online else "offline", retain=retain)

    async def _clean_entity_based_discovery(self) -> None:
        """Remove entity based discovery as part of discovery info.

        https://www.home-assistant.io/docs/mqtt/discovery/
        Publish discovery topics on "homeassistant/device/{device_id}/{sensor_id}/config"
        Publish discovery topics on "homeassistant/(sensor|switch)/{device_id}/{sensor_id}/config"
        """

        async def cb_migrate(payload_s: str, topic: str) -> None:
            """Migrate to device based discovery."""
            if not payload_s:
                return
            payload = load_json(payload_s)
            _LOG.info("MQTT MIGRATE topic %s with payload %s", topic, payload)
            migrate_ok = payload == {"migrate_discovery": True}
            _pl = None if migrate_ok else dumps({"migrate_discovery": True})
            if migrate_ok:
                await asyncio.sleep(5)
            await self.publish(topic=topic, payload=_pl, qos=1, retain=True)

        def cb_remove(dev: MQTTDevice) -> TopicCallback:
            """Create a callback for the device."""

            async def _cb_remove(payload_s: str, topic: str) -> None:
                if not payload_s:
                    return
                payload = load_json(payload_s)
                # if not part of this device, remove the topic
                if not isinstance(payload, dict) or "unique_id" not in payload:
                    _LOG.warning(
                        "MQTT CLEAN: No unique_id in payload %s, cannot remove", payload
                    )
                    return
                uid = payload["unique_id"]
                if uid not in dev.components:
                    _LOG.info("MQTT: Removing unique ID %s", uid)
                    await self.publish(topic=topic, payload=None, qos=1, retain=True)

            return _cb_remove

        if self.clean_entities == 0:
            return
        migrate = self.clean_entities == 1
        self.clean_entities = 0
        clean_topics: list[str] = []
        for dev in self.devs:
            topic = f"homeassistant/+/{dev.id}/+/config"
            await self.topic_subscribe(topic, cb_migrate if migrate else cb_remove(dev))
            clean_topics.append(topic)

        if not clean_topics:
            return

        async def _delayed_unsubscribe() -> None:
            await asyncio.sleep(10)
            for topic in clean_topics:
                await self.topic_unsubscribe(topic)

        self._clean_unsubscribe_task = asyncio.create_task(_delayed_unsubscribe())


class MQTTMatcher2(MQTTMatcher):
    """Extend MQTTMatcher to return all keys."""

    def keys(self) -> Generator[str]:
        """Return all keys."""

        def iterall(
            prefix: tuple[str, ...], n: MQTTMatcher.Node
        ) -> Generator[str, None, None]:
            """Yield node & children."""
            if n._content is not None:
                yield "/".join(prefix)
            for key, child in n._children.items():
                yield from iterall((*prefix, key), child)

        yield from iterall(tuple[str](), self._root)

    def __contains__(self, topic: str) -> bool:
        """Check whether a topic is actively subscribed."""
        try:
            next(self.iter_match(topic))
            return True
        except StopIteration:
            return False

    def pop(self, topic: str) -> None:
        """Remove a topic from the active subscriptions."""
        try:
            del self[topic]
        except KeyError:  # no such subscription
            pass

    def iter_match(self, topic: str) -> Generator[TopicCallback]:
        """Return an iterator on all values associated with filters that match the :topic."""
        yield from super().iter_match(topic)
