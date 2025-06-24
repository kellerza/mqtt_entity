"""MQTT entities."""

from __future__ import annotations

from json import dumps
from typing import TYPE_CHECKING, Any, Callable, Sequence

import attrs
from attrs import validators

from .device import MQTTBaseEntity, TopicCallback
from .utils import BOOL_OFF, BOOL_ON, required

if TYPE_CHECKING:
    from .client import MQTTClient

# pylint: disable=too-few-public-methods, too-many-instance-attributes


@attrs.define()
class MQTTEntity(MQTTBaseEntity):
    """A generic Home Assistant entity used as the base class for other entities."""

    unique_id: str
    # device: MQTTDevice
    state_topic: str
    name: str
    object_id: str = ""
    # availability: list[MQTTAvailability] = attrs.field(factory=list)
    # availability_mode: str = ""
    device_class: str = ""
    unit_of_measurement: str = ""
    state_class: str = ""
    expire_after: int = 0
    """Unavailable if not updated."""
    enabled_by_default: bool = True
    entity_category: str = ""
    entity_picture: str = ""
    icon: str = ""
    json_attributes_topic: str = ""
    """Used by the set_attributes helper."""

    discovery_extra: dict[str, Any] = attrs.field(factory=dict)
    """Additional MQTT Discovery attributes."""

    _path = ""

    async def send_state(
        self, client: MQTTClient, payload: str, *, retain: bool = False
    ) -> None:
        """Publish the state to the MQTT state topic."""
        await client.publish(self.state_topic, payload, retain=retain)

    async def send_json_attributes(
        self, client: MQTTClient, attributes: dict[str, Any], *, retain: bool = True
    ) -> None:
        """Publish the attributes to the MQTT attributes topic."""
        await client.publish(
            topic=self.json_attributes_topic, payload=dumps(attributes), retain=retain
        )

    def __attrs_post_init__(self) -> None:
        """Init the class."""
        if not self._path:
            raise TypeError(f"Do not instantiate {self.__class__.__name__} directly")
        if not self.state_class and self.device_class == "energy":
            self.state_class = "total_increasing"


@attrs.define()
class MQTTDeviceTrigger(MQTTBaseEntity):
    """A Home Assistant Device trigger.

    https://www.home-assistant.io/integrations/device_trigger.mqtt/
    """

    type: str
    subtype: str
    payload: str
    topic: str

    _path = "device_automation"

    @property
    def name(self) -> str:
        """Return the name of the trigger."""
        return f"{self.type} {self.subtype}".strip()

    async def send_trigger(self, client: MQTTClient) -> None:
        """Publish the state to the MQTT state topic."""
        await client.publish(self.topic, self.payload or "1")

    discovery_extra: dict[str, Any] = attrs.field(factory=dict)
    """Additional MQTT Discovery attributes."""

    def discovery_dict(self, result: dict[str, Any]) -> None:
        """Return the final discovery dictionary."""
        super().discovery_dict(result)
        result["automation_type"] = "trigger"
        result["platform"] = "device_automation"

    # on_trigger: Callable | None = None
    # """Callable to call when triggered."""

    # def topic_callbacks(self, result: dict[str, TopicCallback]) -> None:
    #     """Return a dictionary of topic callbacks."""
    #     super().topic_callbacks(result)
    #     if self.topic and self.on_trigger:
    #         result[self.topic] = self.on_trigger


@attrs.define()
class MQTTRWEntity(MQTTEntity):
    """Read/Write entity base class.

    This will default to a text entity.
    """

    command_topic: str = attrs.field(
        default="", validator=(validators.instance_of(str), validators.min_len(2))
    )
    on_command: Callable | None = None

    _path = "text"

    def topic_callbacks(self, result: dict[str, TopicCallback]) -> None:
        """Return a dictionary of topic callbacks."""
        super().topic_callbacks(result)
        if self.command_topic and self.on_command:
            result[self.command_topic] = self.on_command


@attrs.define()
class MQTTSensorEntity(MQTTEntity):
    """A Home Assistant Sensor entity."""

    _path = "sensor"


@attrs.define()
class MQTTBinarySensorEntity(MQTTEntity):
    """A Home Assistant Binary Sensor entity."""

    payload_on: str = BOOL_ON
    payload_off: str = BOOL_OFF

    _path = "binary_sensor"


@attrs.define()
class MQTTSelectEntity(MQTTRWEntity):
    """A HomeAssistant Select entity."""

    options: Sequence[str] = attrs.field(default=None, validator=required)

    _path = "select"


@attrs.define()
class MQTTSwitchEntity(MQTTRWEntity):
    """A Home Assistant Switch entity."""

    payload_on: str = BOOL_ON
    payload_off: str = BOOL_OFF

    _path = "switch"


@attrs.define()
class MQTTText(MQTTRWEntity):
    """A Home Assistant Switch entity."""

    _path = "text"


@attrs.define()
class MQTTLightEntity(MQTTRWEntity):
    """A Home Assistant Switch entity."""

    payload_on: str = BOOL_ON
    payload_off: str = BOOL_OFF

    brightness_state_topic: str = ""
    brightness_command_topic: str = ""
    on_brightness_change: TopicCallback | None = None

    effect_state_topic: str = ""
    effect_command_topic: str = ""
    on_effect_change: TopicCallback | None = None
    effect_list: list[str] | None = None

    hs_state_topic: str = ""
    hs_command_topic: str = ""
    on_hs_change: TopicCallback | None = None

    _path = "light"

    async def send_brightness(
        self, client: MQTTClient, brightness: int, *, retain: bool = False
    ) -> None:
        """Publish the brightness to the MQTT brightness command topic."""
        await client.publish(
            self.brightness_state_topic,
            str(brightness),
            retain=retain,
        )

    async def send_effect(
        self, client: MQTTClient, effect: str, *, retain: bool = False
    ) -> None:
        """Publish the effect to the MQTT effect command topic."""
        await client.publish(
            self.effect_state_topic,
            effect,
            retain=retain,
        )

    async def send_hs(
        self, client: MQTTClient, hs: tuple[float, float], *, retain: bool = False
    ) -> None:
        """Publish the hue and saturation to the MQTT hs command topic."""
        await client.publish(
            self.hs_state_topic,
            f"{hs[0]},{hs[1]}",
            retain=retain,
        )

    def topic_callbacks(self, result: dict[str, TopicCallback]) -> None:
        """Return a dictionary of topic callbacks."""
        super().topic_callbacks(result)
        if self.brightness_command_topic and self.on_brightness_change:
            result[self.brightness_command_topic] = self.on_brightness_change
        if self.effect_command_topic and self.on_effect_change:
            result[self.effect_command_topic] = self.on_effect_change
        if self.hs_command_topic and self.on_hs_change:
            result[self.hs_command_topic] = self.on_hs_change


@attrs.define()
class MQTTNumberEntity(MQTTRWEntity):
    """A HomeAssistant Number entity."""

    min: float = 0.0
    max: float = 100.0
    mode: str = "auto"
    step: float = 1.0

    _path = "number"
