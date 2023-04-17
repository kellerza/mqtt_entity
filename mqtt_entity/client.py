"""MQTTClient."""
import asyncio
import inspect
import logging
from json import dumps
from typing import Any, Callable, Optional, Sequence, Union

from paho.mqtt.client import Client, MQTTMessage  # type: ignore

from mqtt_entity.entities import Availability, Entity

_LOGGER = logging.getLogger(__name__)


class MQTTClient:
    """Basic MQTT Client."""

    availability_topic: str = ""
    topic_on_change: dict[str, Callable] = {}

    def __init__(self) -> None:
        """Init MQTT Client."""
        self._client = Client()

    async def connect(
        self,
        options: Any = None,
        *,
        username: Optional[str] = None,
        password: Optional[str] = None,
        host: Optional[str] = None,
        port: int = 1883,
    ) -> None:
        """Connect to MQTT server specified as attributes of the options."""
        if self._client.is_connected():
            return
        # Disconnect so that we trigger "Connection Successful" on re-connect
        await self.disconnect()
        self._client.on_connect = _mqtt_on_connect

        username = getattr(options, "mqtt_username", username)
        password = getattr(options, "mqtt_password", password)
        host = getattr(options, "mqtt_host", host)
        port = getattr(options, "mqtt_port", port)
        self._client.username_pw_set(username=username, password=password)

        if self.availability_topic:
            self._client.will_set(self.availability_topic, "offline", retain=True)

        _LOGGER.info("MQTT: Connecting to %s@%s:%s", username, host, port)
        self._client.connect_async(host=host, port=port)
        self._client.loop_start()

        retry = 10
        while retry and not self._client.is_connected():
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
        if self.topic_on_change:
            _LOGGER.debug(
                "MQTT: Re-subscribe to %s", ", ".join(self.topic_on_change.keys())
            )
            for topic in self.topic_on_change:
                self._client.subscribe(topic)

    async def disconnect(self) -> None:
        """Stop the MQTT client."""

        def _stop() -> None:
            # Do not disconnect, we want the broker to always publish will
            self._client.loop_stop()

        await asyncio.get_running_loop().run_in_executor(None, _stop)

    async def publish(
        self,
        topic: Union[str | Entity],
        payload: Optional[str],
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """Publish a MQTT message."""
        # async with self._paho_lock:
        if isinstance(topic, Entity):
            topic = topic.state_topic
        if not isinstance(qos, int):
            qos = 0
        if retain:
            qos = 1
        _LOGGER.debug(
            "MQTT: Publish %s%s %s, %s", qos, "R" if retain else "", topic, payload
        )
        await asyncio.get_running_loop().run_in_executor(
            None, self._client.publish, topic, payload, qos, bool(retain)
        )

    async def publish_discovery_info(
        self, entities: Sequence[Entity], remove_entities: bool = True
    ) -> None:
        """Home Assistant MQTT discovery helper.

        https://www.home-assistant.io/docs/mqtt/discovery/
        Publish discovery topics on "homeassistant/(sensor|switch)/{device_id}/{sensor_id}/config"
        """
        if not self._client.is_connected():
            raise ConnectionError()

        await self.on_change_handler(entities=entities)

        task_remove = None
        if remove_entities:
            _LOGGER.debug(
                "MQTT: Remove entities %s", [e.name if e else str(e) for e in entities]
            )
            task_remove = asyncio.create_task(
                self.remove_discovery_info(
                    device_ids=list(set(e.device.id for e in entities)),
                    keep_topics=[e.topic for e in entities],
                )
            )

        for ent in entities:
            if self.availability_topic and not ent.availability:
                ent.availability = [Availability(topic=self.availability_topic)]
            _LOGGER.debug("MQTT: Publish %s", ent.topic)
            await self.publish(ent.topic, payload=dumps(ent.asdict), retain=True)

        await asyncio.sleep(0.01)

        if task_remove:
            await task_remove

    async def remove_discovery_info(
        self, device_ids: Sequence[str], keep_topics: Sequence[str], sleep: float = 0.5
    ) -> None:
        """Remove previously discovered entities."""

        def __on_message(client: Client, _userdata: Any, message: MQTTMessage) -> None:
            if not message.retain:
                return
            topic = str(message.topic)
            device = topic.split("/")[-3]
            _LOGGER.debug("MQTT: Rx retained msg: topic=%s -- device=%s", topic, device)
            if device not in device_ids or topic in keep_topics:
                return
            _LOGGER.info("MQTT: Removing HASS MQTT discovery info %s", topic)
            # Not in the event loop, execute directly
            client.publish(topic=topic, payload=None, qos=1, retain=True)

        self._client.on_message = __on_message

        subs = [f"homeassistant/+/{did}/+/config" for did in device_ids]
        for sub in subs:
            self._client.subscribe(sub)
        await asyncio.sleep(sleep)  # Wait for all retained messages to be reported
        for sub in subs:
            self._client.unsubscribe(sub)

        # re-assign the correct on_message handler
        # self._client.on_message = None
        await self.on_change_handler()

    async def on_change_handler(
        self, entities: Optional[Sequence[Entity]] = None
    ) -> None:
        """Assign the MQTT on_message handler for entities' on_change."""
        _loop = asyncio.get_running_loop()

        def _on_change_handler(
            _client: Client, _userdata: Any, message: MQTTMessage
        ) -> None:
            handler = self.topic_on_change.get(str(message.topic))
            if not handler:
                return
            payload = message.payload.decode("utf-8")
            if inspect.iscoroutinefunction(handler):
                coro = handler(payload)
                _loop.call_soon_threadsafe(lambda: _loop.create_task(coro))
            else:
                handler(payload)

        self._client.on_message = _on_change_handler

        if not entities:
            return

        for ent in entities:
            handler = getattr(ent, "on_change", None)
            topic = getattr(ent, "command_topic", None)
            if topic and handler:
                self.topic_on_change[topic] = handler
                self._client.subscribe(topic)


def _mqtt_on_connect(
    _client: Client, _userdata: Any, _flags: Any, _rc: int, _prop: Any = None
) -> None:
    msg = {
        0: "successful",
        1: "refused - incorrect protocol version",
        2: "refused - invalid client identifier",
        3: "refused - server unavailable",
        4: "refused - bad username or password",
        5: "refused - not authorised",
    }.get(_rc, f"refused - {_rc}")
    _LOGGER.info("MQTT: Connection %s", msg)
