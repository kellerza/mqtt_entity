"""HASS MQTT Device, used for device based discovery."""

from typing import Any, Callable, Coroutine

import attrs
from attrs import validators

from .helpers import discovery_dict

type TopicCallback = (
    Callable[[str], None]
    | Callable[[str, str], None]
    | Callable[[str], Coroutine[Any, Any, None]]
    | Callable[[str, str], Coroutine[Any, Any, None]]
)


@attrs.define()
class MQTTBaseEntity:
    """Base class for entities that support MQTT Discovery."""

    def discovery_dict(self, result: dict[str, Any]) -> None:
        """Post-process the discovery dictionary."""

    def topic_callbacks(self, result: dict[str, TopicCallback]) -> None:
        """Append topics and callbacks."""


@attrs.define()
class MQTTOrigin:
    """Represent the origin of an MQTT message."""

    name: str
    sw: str = ""
    """ws_version"""
    url: str = ""
    """support_url"""


@attrs.define()
class MQTTDevice:
    """Base class for MQTT Device Discovery. A Home Assistant Device groups entities."""

    components: dict[str, MQTTBaseEntity]
    """MQTT component entities."""

    identifiers: list[str | tuple[str, Any]] = attrs.field(
        validator=[validators.instance_of(list), validators.min_len(1)]
    )
    connections: list[str] = attrs.field(factory=list)
    configuration_url: str = ""
    manufacturer: str = ""
    model: str = ""
    name: str = ""
    suggested_area: str = ""
    sw_version: str = ""
    via_device: str = ""

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """The device identifier. Also object_id."""
        return str(self.identifiers[0])

    def discovery_info(
        self, availability_topic: str, *, origin: MQTTOrigin
    ) -> tuple[str, dict[str, Any]]:
        """Return the discovery dictionary for the MQTT device."""
        return (
            f"homeassistant/device/{self.id}/config",
            {
                "dev": discovery_dict(self, exclude=["components"]),
                "o": discovery_dict(origin),
                "avty": {
                    "topic": availability_topic,
                },
                "cmps": {k: discovery_dict(v) for k, v in self.components.items()},
            },
        )
