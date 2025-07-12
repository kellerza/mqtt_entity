"""MQTT entities."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from json import dumps
from typing import TYPE_CHECKING, Any

import attrs
from attrs import validators

from .helpers import as_dict
from .utils import BOOL_OFF, BOOL_ON, required, tostr

if TYPE_CHECKING:
    from .client import MQTTAsyncClient, TopicCallback


@attrs.define()
class MQTTBaseEntity:
    """Base class for entities that support MQTT Discovery."""

    @property
    def topic_callbacks(self) -> dict[str, TopicCallback]:
        """Append topics and callbacks."""
        return {}

    @property
    def as_discovery_dict(self) -> dict[str, Any]:
        """Discovery dict."""
        return as_dict(self)


@attrs.define()
class MQTTEntity(MQTTBaseEntity):
    """A generic Home Assistant entity used as the base class for other entities."""

    name: str
    unique_id: str
    """An ID that uniquely identifies this sensor. If two sensors have the same unique ID,
      Home Assistant will raise an exception. Required when used with device-based discovery."""
    state_topic: str
    object_id: str = ""
    """Used instead of name for automatic generation of entity_id."""

    device_class: str = ""
    """The type/class of the sensor to set the icon in the frontend. The device_class can be null."""
    enabled_by_default: bool = True
    """Flag which defines if the entity should be enabled when first added."""
    entity_category: str = ""
    """The category of the entity. When set, the entity category must be diagnostic for sensors."""
    entity_picture: str = ""
    """Picture URL for the entity."""
    expire_after: int = 0
    """If set, it defines the number of seconds after the sensor's state expires,
    if it's not updated. After expiry, the sensor's state becomes unavailable.
    Default the sensors state never expires."""
    icon: str = ""
    json_attributes_topic: str = ""
    state_class: str = ""
    """https://developers.home-assistant.io/docs/core/entity/sensor/#available-state-classes"""
    unit_of_measurement: str = ""
    """Defines the units of measurement of the sensor, if any. The unit_of_measurement can be null."""

    discovery_extra: dict[str, Any] = attrs.field(factory=dict)
    """Additional MQTT Discovery attributes."""

    platform = ""

    async def send_state(
        self, client: MQTTAsyncClient, payload: Any, *, retain: bool = False
    ) -> None:
        """Publish the state to the MQTT state topic."""
        await client.publish(self.state_topic, tostr(payload), retain=retain)

    async def send_json_attributes(
        self,
        client: MQTTAsyncClient,
        attributes: dict[str, Any],
        *,
        retain: bool = True,
    ) -> None:
        """Publish the attributes to the MQTT JSON attributes topic."""
        await client.publish(
            topic=self.json_attributes_topic, payload=dumps(attributes), retain=retain
        )

    def __attrs_post_init__(self) -> None:
        """Init the class."""
        if not self.platform:
            raise TypeError(f"Do not instantiate {self.__class__.__name__} directly")
        if not self.state_class and self.device_class == "energy":
            self.state_class = "total_increasing"

    @property
    def as_discovery_dict(self) -> dict[str, Any]:
        """Discovery dict."""
        res = super().as_discovery_dict
        res.setdefault("platform", self.platform)
        return res


@attrs.define()
class MQTTDeviceTrigger(MQTTBaseEntity):
    """A Home Assistant Device trigger.

    https://www.home-assistant.io/integrations/device_trigger.mqtt/
    """

    type: str
    subtype: str
    payload: str
    topic: str

    @property
    def name(self) -> str:
        """Return the name of the trigger."""
        return f"{self.type} {self.subtype}".strip()

    async def send_trigger(self, client: MQTTAsyncClient) -> None:
        """Publish the state to the MQTT state topic."""
        await client.publish(self.topic, self.payload or "1")

    discovery_extra: dict[str, Any] = attrs.field(factory=dict)
    """Additional MQTT Discovery attributes."""

    @property
    def as_discovery_dict(self) -> dict[str, Any]:
        """Return the final discovery dictionary."""
        result = super().as_discovery_dict
        result["automation_type"] = "trigger"
        result["platform"] = "device_automation"
        return result


@attrs.define()
class MQTTRWEntity(MQTTEntity):
    """Read/Write entity base class.

    This will default to a text entity.
    """

    command_topic: str = attrs.field(
        default="", validator=(validators.instance_of(str), validators.min_len(2))
    )
    on_command: Callable | None = None

    platform = "text"

    @property
    def topic_callbacks(self) -> dict[str, TopicCallback]:
        """Return a dictionary of topic callbacks."""
        result = super().topic_callbacks
        if self.command_topic and self.on_command:
            result[self.command_topic] = self.on_command
        return result


@attrs.define()
class MQTTSensorEntity(MQTTEntity):
    """A Home Assistant Sensor entity."""

    force_update: bool = False
    """Sends update events even if the value hasn't changed. Useful if you want to have
    meaningful value graphs in history."""
    suggested_display_precision: int = 0
    """The number of decimals which should be used in the sensor's state after rounding."""

    platform = "sensor"


@attrs.define()
class MQTTBinarySensorEntity(MQTTEntity):
    """A Home Assistant Binary Sensor entity."""

    payload_on: str = BOOL_ON
    payload_off: str = BOOL_OFF

    platform = "binary_sensor"


@attrs.define()
class MQTTSelectEntity(MQTTRWEntity):
    """A HomeAssistant Select entity."""

    options: Sequence[str] = attrs.field(default=None, validator=required)

    platform = "select"


@attrs.define()
class MQTTSwitchEntity(MQTTRWEntity):
    """A Home Assistant Switch entity."""

    payload_on: str = BOOL_ON
    payload_off: str = BOOL_OFF

    platform = "switch"


@attrs.define()
class MQTTTextEntity(MQTTRWEntity):
    """A Home Assistant Switch entity."""

    platform = "text"


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

    platform = "light"

    async def send_brightness(
        self, client: MQTTAsyncClient, brightness: int, *, retain: bool = False
    ) -> None:
        """Publish the brightness to the MQTT brightness command topic."""
        await client.publish(
            self.brightness_state_topic,
            str(brightness),
            retain=retain,
        )

    async def send_effect(
        self, client: MQTTAsyncClient, effect: str, *, retain: bool = False
    ) -> None:
        """Publish the effect to the MQTT effect command topic."""
        await client.publish(
            self.effect_state_topic,
            effect,
            retain=retain,
        )

    async def send_hs(
        self, client: MQTTAsyncClient, hs: tuple[float, float], *, retain: bool = False
    ) -> None:
        """Publish the hue and saturation to the MQTT hs command topic."""
        await client.publish(
            self.hs_state_topic,
            f"{hs[0]},{hs[1]}",
            retain=retain,
        )

    @property
    def topic_callbacks(self) -> dict[str, TopicCallback]:
        """Return a dictionary of topic callbacks."""
        result = super().topic_callbacks
        if self.brightness_command_topic and self.on_brightness_change:
            result[self.brightness_command_topic] = self.on_brightness_change
        if self.effect_command_topic and self.on_effect_change:
            result[self.effect_command_topic] = self.on_effect_change
        if self.hs_command_topic and self.on_hs_change:
            result[self.hs_command_topic] = self.on_hs_change
        return result


@attrs.define()
class MQTTNumberEntity(MQTTRWEntity):
    """A HomeAssistant Number entity."""

    min: float = 0.0
    max: float = 100.0
    mode: str = "auto"
    step: float = 1.0

    suggested_display_precision: int = 0
    """The number of decimals which should be used in the sensor's state after rounding."""

    platform = "number"
