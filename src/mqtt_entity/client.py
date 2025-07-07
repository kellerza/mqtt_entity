"""MQTTClient."""

import asyncio
import importlib.metadata
import inspect
import logging
import sys
from json import dumps
from typing import Any

import attrs
from paho.mqtt.client import Client, MQTTMessage
from paho.mqtt.enums import CallbackAPIVersion
from paho.mqtt.reasoncodes import ReasonCode

from .device import MQTTDevice, MQTTOrigin, TopicCallback
from .utils import load_json

_LOGGER = logging.getLogger(__name__)


@attrs.define()
class MQTTClient:
    """Basic MQTT Client."""

    devs: list[MQTTDevice]
    availability_topic: str = ""
    origin: MQTTOrigin = attrs.field(
        factory=lambda: MQTTOrigin(
            name="mqtt-entity", sw=importlib.metadata.version("mqtt-entity")
        )
    )
    client: Client = attrs.field(init=False, repr=False)
    topics_subscribed: set[str] = attrs.field(init=False, repr=False)
    """All topic we subscribed to."""
    clean_entities: int = attrs.field(default=1)
    """Clean entities on discovery: 1=migrate, 2=remove, 0=none."""

    def __attrs_post_init__(self) -> None:
        """Init MQTT Client."""
        self.topics_subscribed = set()
        self.client = Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.origin.name,
        )
        self.client.on_connect = _mqtt_on_connect
        self.client.on_message = _mqtt_on_message

    async def connect(
        self,
        options: Any = None,
        *,
        username: str | None = None,
        password: str | None = None,
        host: str = "core-mosquitto",
        port: int = 1883,
    ) -> None:
        """Connect to MQTT server specified as attributes of the options."""
        if self.client.is_connected():
            return
        # Disconnect so that we trigger "Connection Successful" on re-connect
        await self.disconnect()

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

        retry = 10
        while retry and not self.client.is_connected():
            await asyncio.sleep(0.5)
            retry -= 0
        if not retry:
            raise ConnectionError(
                f"MQTT: Could not connect to {username}@{host}:{port}"
            )
        # publish online (Last will sets offline on disconnect)
        if self.availability_topic:
            await self.publish(self.availability_topic, "online", retain=True)

        # Ensure we subscribe all existing change handlers (after a reconnect)
        for topic in self.topics_subscribed:
            self.client.subscribe(topic)

    async def disconnect(self) -> None:
        """Stop the MQTT client."""

        def _stop() -> None:
            """Do not disconnect, we want the broker to always publish will."""
            self.client.loop_stop()

        await asyncio.get_running_loop().run_in_executor(None, _stop)

    async def publish(
        self,
        topic: str,
        payload: str | None = None,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """Publish a MQTT message."""
        if not topic:
            raise ValueError(f"MQTT: Cannot publish to empty topic (payload={payload})")
        if not isinstance(qos, int):
            qos = 0
        if retain:
            qos = 1
        _LOGGER.debug(
            "MQTT: Publish %s%s %s, %s", qos, "R" if retain else "", topic, payload
        )
        if payload and len(payload) > 20000:
            _LOGGER.warning("Payload >20000: %s", len(payload))
        await asyncio.get_running_loop().run_in_executor(
            None, self.client.publish, topic, payload, qos, bool(retain)
        )

    def publish_discovery_info(self) -> None:
        """Publish discovery info if HA is online."""

        def _timeout() -> None:
            """Timeout for Home Assistant online check."""
            _LOGGER.error(
                "MQTT: Home Assistant not online. Topic homeassistant/status is empty"
            )
            sys.exit(1)

        timeout = asyncio.get_running_loop().call_later(10, _timeout)

        async def _online_cb(payload_s: str) -> None:
            """Republish discovery info."""
            if payload_s != "online":
                _LOGGER.warning(
                    "MQTT: Home Assistant offline. homeassistant/status = %s",
                    payload_s,
                )
                return

            timeout.cancel()
            _LOGGER.info(
                "MQTT: Home Assistant online. Publish discovery info for %s",
                [d.name for d in self.devs],
            )
            await self.publish_discovery_info_now()

        if not self.client.is_connected():
            raise ConnectionError()

        self.topic_subscribe("homeassistant/status", _online_cb)

    async def publish_discovery_info_now(self) -> None:
        """Publish discovery info immediately."""
        if self.clean_entities:
            self.clean_entity_based_discovery()
            await asyncio.sleep(1)

        for ddev in self.devs:
            disco_topic, disco_dict = ddev.discovery_info(
                self.availability_topic, origin=self.origin
            )
            disco_payload = dumps(disco_dict)
            if len(disco_payload) > 20000:  # 20000 is the MQTT Explorer limit
                disco_payload = dumps(disco_dict, indent=None, separators=(",", ":"))
            await self.publish(disco_topic, disco_payload)

            # add topic callbacks
            tcb: dict[str, TopicCallback] = {}
            for ent in ddev.components.values():
                ent.topic_callbacks(tcb)
            for topic, cbk in tcb.items():
                self.topic_subscribe(topic, cbk)

    def clean_entity_based_discovery(self) -> None:
        """Remove entity based discovery.

        https://www.home-assistant.io/docs/mqtt/discovery/
        Publish discovery topics on "homeassistant/device/{device_id}/{sensor_id}/config"
        Publish discovery topics on "homeassistant/(sensor|switch)/{device_id}/{sensor_id}/config"
        """

        async def cb_migrate(payload_s: str, topic: str) -> None:
            """Callback to remove the device."""
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

    def topic_unsubscribe(self, topic: str) -> None:
        """Remove a topic from the topic callbacks."""
        self.client.unsubscribe(topic)
        self.client.message_callback_remove(topic)
        self.topics_subscribed.discard(topic)

    def topic_subscribe(self, topic: str, callback: TopicCallback) -> None:
        """Add a topic to the topic callbacks."""

        paramc = len(inspect.signature(callback).parameters)
        loop = asyncio.get_running_loop()

        def cb(_client: Client, _userdata: Any, message: MQTTMessage) -> None:
            """Callback for the topic."""
            payload = message.payload.decode("utf-8")
            _LOGGER.debug(
                "MQTT Callback for topic %s, payload %s",
                message.topic,
                payload or '""',
            )
            args = (payload,) if paramc == 1 else (payload, message.topic)
            if inspect.iscoroutinefunction(callback):
                coro = callback(*args)
                loop.call_soon_threadsafe(lambda: loop.create_task(coro))
            else:
                callback(*args)

        _LOGGER.debug("MQTT add callback for topic %s", topic)
        self.client.subscribe(topic)
        self.client.message_callback_add(topic, cb)
        self.topics_subscribed.add(topic)


def _mqtt_on_connect(
    _client: Client,
    _userdata: Any,
    _flags: Any,
    _rc: ReasonCode,
    _prop: Any = None,
) -> None:
    """MQTT on_connect callback."""
    if _rc == 0:
        _LOGGER.info("MQTT: Connection successful")
        return
    _LOGGER.error("MQTT: Connection failed with reason code %s", _rc)


def _mqtt_on_message(
    _client: Client,
    _userdata: Any,
    message: MQTTMessage,
) -> None:
    """MQTT on_message callback."""
    topic = message.topic
    payload = message.payload.decode("utf-8")
    _LOGGER.warning(
        "MQTT: Unhandled msg received on topic %s with payload %s", topic, payload
    )
