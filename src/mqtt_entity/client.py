"""MQTTClient."""

from __future__ import annotations

import asyncio
import importlib.metadata
import inspect
import logging
import time
from collections.abc import Callable, Coroutine, Generator
from json import dumps
from typing import Any

import attrs
from paho.mqtt.client import Client, MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.matcher import MQTTMatcher
from paho.mqtt.reasoncodes import ReasonCode

from .device import MQTTDevice, MQTTOrigin
from .utils import load_json

HA_STATUS_TOPIC = "homeassistant/status"
_LOGGER = logging.getLogger(__name__)
MQTT_EXPLORER_LIMIT = 20000

type SyncTopicCallback = Callable[[str], None] | Callable[[str, str], None]
type AsyncTopicCallback = (
    Callable[[str], Coroutine[Any, Any, None]]
    | Callable[[str, str], Coroutine[Any, Any, None]]
)
type TopicCallback = SyncTopicCallback | AsyncTopicCallback


@attrs.define()
class MQTTAsyncClient:
    """Async MQTT Client."""

    availability_topic: str = ""
    client: Client = attrs.field(init=False, repr=False)
    suppress_exceptions: bool = True
    connect_time: float = attrs.field(init=False, repr=False)

    _on_message_filtered: MQTTMatcher2 = attrs.field(
        factory=lambda: MQTTMatcher2(), repr=False
    )
    _loop: asyncio.AbstractEventLoop = attrs.field(init=False, repr=False)

    def __attrs_post_init__(self) -> None:
        """Init."""
        self.connect_time = 0
        self.client = Client(callback_api_version=CallbackAPIVersion.VERSION2)
        self.client.on_connect = self._mqtt_on_connect
        self.client.on_message = self._mqtt_on_message

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
        if self.client.is_connected():
            _LOGGER.warning("MQTT: Client connected. Reconnecting...")
        await self.disconnect()  # "Connection Successful" triggered on re-connect
        self._loop = asyncio.get_running_loop()

        if options:
            username = getattr(options, "mqtt_username", username)
            password = getattr(options, "mqtt_password", password)
            host = getattr(options, "mqtt_host", host)
            port = getattr(options, "mqtt_port", port)
        self.client.username_pw_set(username=username, password=password)

        if self.availability_topic:
            self.client.will_set(self.availability_topic, "offline", retain=True)

        _LOGGER.info("MQTT: Connecting to %s@%s:%s", username, host, port)
        self.client.connect_async(host=host, port=port)
        self.client.loop_start()
        self.connect_time = time.time() + 5

        if wait_connected:
            await self.wait_connected()

    def _mqtt_on_connect(
        self,
        client: Client,
        data: Any,
        flags: Any,
        rc: ReasonCode,
        prop: Any = None,
    ) -> None:
        """MQTT on_connect callback."""
        if rc != 0:
            _LOGGER.error("MQTT: Connection failed with reason code %s", rc)
            self.connect_time = -1  # failed
            return
        _LOGGER.info("MQTT: Connected")
        # publish online (Last will sets offline on disconnect)
        if self.availability_topic:
            client.publish(self.availability_topic, "online", retain=True)
        # Subscribe to all existing change handlers (on connect/reconnect)
        for topic in self._on_message_filtered.keys():
            client.subscribe(topic)

    async def wait_connected(self) -> None:
        """Wait until connected."""
        if self.client.is_connected():
            return
        if self.connect_time == 0:
            raise RuntimeError("MQTT: Call connect first")
        _LOGGER.debug("MQTT: Waiting for connection...")
        while True:
            if self.client.is_connected():
                return
            await asyncio.sleep(0.1)
            if time.time() > self.connect_time:
                if self.connect_time < 0:
                    raise ConnectionError("MQTT: Connection failed")
                msg = "MQTT: Connection timeout (5s)"
                _LOGGER.error(msg)
                raise ConnectionError(msg)

    async def disconnect(self) -> None:
        """Stop the MQTT client."""

        def _stop() -> None:
            """Do not disconnect, allow the broker to publish LWT message."""
            self.client.loop_stop()

        await asyncio.get_running_loop().run_in_executor(None, _stop)

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
        _LOGGER.debug(
            "MQTT: Publish %s%s %s, %s", qos, "R" if retain else "", topic, payload
        )
        if payload and len(payload) > MQTT_EXPLORER_LIMIT:
            _LOGGER.info(
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
        await asyncio.get_running_loop().run_in_executor(
            None, self.client.publish, *args
        )

    def topic_unsubscribe(self, topic: str) -> None:
        """Remove a topic from the topic callbacks."""
        self.client.unsubscribe(topic)
        self._on_message_filtered.pop(topic)

    def topic_subscribe(self, topic: str, callback: TopicCallback) -> None:
        """Add a topic to the topic callbacks."""
        _LOGGER.debug("MQTT: Add callback for topic %s", topic)
        self._on_message_filtered[topic] = callback
        self.client.subscribe(topic)

    def _mqtt_on_message(self, c: Client, userdata: Any, message: MQTTMessage) -> None:
        """MQTT on_message fallback."""
        topic = message.topic
        payload = message.payload.decode("utf-8")
        if topic is None:
            _LOGGER.warning("MQTT: received empty topic, payload: %s", payload)
            return

        # split sync & async callbacks
        sync_cbs: list[tuple[SyncTopicCallback, list[str]]] = []
        async_cbs: list[tuple[AsyncTopicCallback, list[str]]] = []
        for cb in self._on_message_filtered.iter_match(topic):
            paramc = len(inspect.signature(cb).parameters)
            args = [payload] if paramc == 1 else [payload, message.topic]
            if inspect.iscoroutinefunction(cb):
                async_cbs.append((cb, args))
            else:
                sync_cbs.append((cb, args))  # type:ignore[arg-type]

        if not sync_cbs and not async_cbs:
            _LOGGER.warning(
                "MQTT: Unhandled msg received. Topic %s with payload %s", topic, payload
            )
            return None

        _LOGGER.debug(
            "MQTT: topic %s, async callbacks: %s, sync callbacks: %s",
            topic,
            [c[0].__name__ for c in async_cbs],
            [c[0].__name__ for c in sync_cbs],
        )

        for cb, args in sync_cbs:
            name = cb.__name__
            try:
                _LOGGER.debug("MQTT: Callback %s(%s, topic=%s)", name, payload, topic)
                cb(*args)
            except Exception as err:
                _LOGGER.error(
                    "MQTT: Exception in callback %s(topic=%s): %s", name, topic, err
                )
                if not self.suppress_exceptions:
                    raise

        if not async_cbs:
            return

        async def cbs() -> None:
            """Run async callbacks."""
            for cb, args in async_cbs:
                name = cb.__name__
                try:
                    _LOGGER.debug(
                        "MQTT: Callback async %s(%s, topic=%s)", name, payload, topic
                    )
                    await cb(*args)
                except Exception as err:
                    _LOGGER.error(
                        "MQTT: Exception in callback %s(topic=%s): %s", name, topic, err
                    )
                    if not self.suppress_exceptions:
                        raise

        self._loop.call_soon_threadsafe(lambda: self._loop.create_task(cbs()))


@attrs.define()
class MQTTClient(MQTTAsyncClient):
    """Home Assistant specific MQTT client."""

    devs: list[MQTTDevice] = attrs.field(factory=list)

    origin_name: str = "mqtt-entity"
    origin_version: str = attrs.field(
        factory=lambda: importlib.metadata.version("mqtt-entity")
    )
    origin_url: str = ""
    clean_entities: int = attrs.field(default=1)
    """Clean entities on discovery: 1=migrate, 2=remove, 0=none."""

    def monitor_homeassistant_status(self) -> None:
        """Monitor homeassistant/status & publish discovery info."""
        if HA_STATUS_TOPIC in self._on_message_filtered:
            return
        _loop = asyncio.get_running_loop()

        def _timeout() -> None:
            _LOGGER.warning(
                "MQTT: Timeout waiting for Home Assistant. The %s topic is empty.\n"
                "Configure the MQTT integration in Home Assistant to publish a "
                "last will & testament (online/offline) with the Retain flag set.",
                HA_STATUS_TOPIC,
            )
            _LOGGER.warning(
                "MQTT: Your entities will be unavailable if HA restarts",
            )
            _loop.create_task(self.publish_discovery_info())  # noqa: RUF006

        timeout = _loop.call_later(10, _timeout)

        async def _online_cb(payload_s: str) -> None:
            """Republish discovery info."""
            if payload_s != "online":
                _LOGGER.warning(
                    "MQTT: Home Assistant offline. %s = %s", HA_STATUS_TOPIC, payload_s
                )
                return
            timeout.cancel()
            _LOGGER.info(
                "MQTT: Home Assistant online. Publish discovery info for %s",
                [d.name for d in self.devs],
            )
            await self.publish_discovery_info()

        self.topic_subscribe(HA_STATUS_TOPIC, _online_cb)
        if self.connect_time == 0:
            raise ConnectionError()

    async def publish_discovery_info(self) -> None:
        """Publish discovery info immediately."""
        if not self.devs:
            _LOGGER.warning("MQTT: No devices to publish discovery info for")
            return

        if self.clean_entities:
            self._clean_entity_based_discovery()
            await asyncio.sleep(1)

        for ddev in self.devs:
            disco_topic, disco_dict = ddev.discovery_info(
                self.availability_topic,
                origin=MQTTOrigin(
                    name=self.origin_name,
                    sw=self.origin_version,
                    url=self.origin_url,
                ),
            )
            disco_payload = dumps(disco_dict)
            if len(disco_payload) > MQTT_EXPLORER_LIMIT:
                disco_payload = dumps(disco_dict, indent=None, separators=(",", ":"))
            await self.publish(disco_topic, disco_payload)

            # add topic callbacks
            tcb: dict[str, TopicCallback] = {}
            for ent in ddev.components.values():
                tcb.update(ent.topic_callbacks)
            for topic, cbk in tcb.items():
                self.topic_subscribe(topic, cbk)

    def _clean_entity_based_discovery(self) -> None:
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
            _LOGGER.info("MQTT MIGRATE topic %s with payload %s", topic, payload)
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
                    _LOGGER.warning(
                        "MQTT CLEAN: No unique_id in payload %s, cannot remove", payload
                    )
                    return
                uid = payload["unique_id"]
                if uid not in dev.components:
                    _LOGGER.info("MQTT: Removing unique ID %s", uid)
                    self.client.publish(topic=topic, payload=None, qos=1, retain=True)

            return _cb_remove

        if self.clean_entities == 0:
            return
        migrate = self.clean_entities == 1
        self.clean_entities = 0
        for dev in self.devs:
            topic = f"homeassistant/+/{dev.id}/+/config"
            self.topic_subscribe(topic, cb_migrate if migrate else cb_remove(dev))
            asyncio.get_running_loop().call_later(10, self.topic_unsubscribe, topic)


class MQTTMatcher2(MQTTMatcher):
    """Extend MQTTMatcher to return all keys."""

    def keys(self) -> Generator[str, None, None]:
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
