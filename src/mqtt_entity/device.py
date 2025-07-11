"""HASS MQTT Device, used for device based discovery."""

from typing import Any

import attrs
from attrs import validators

from .entities import MQTTBaseEntity
from .helpers import as_dict, hass_abbreviate


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

    identifiers: list[str | tuple[str, Any]] = attrs.field(
        validator=[validators.instance_of(list), validators.min_len(1)]
    )

    components: dict[str, MQTTBaseEntity]
    """MQTT component entities."""
    remove_components: dict[str, str] = attrs.field(factory=dict)
    """Components to be removed on discovery. object_id and the platform name."""

    connections: list[str] = attrs.field(factory=list)
    configuration_url: str = ""
    manufacturer: str = ""
    model: str = ""
    name: str = ""
    suggested_area: str = ""
    sw_version: str = ""
    via_device: str = ""

    @property
    def id(self) -> str:
        """The device identifier. Also object_id."""
        return str(self.identifiers[0])

    def discovery_info(
        self, availability_topic: str, *, origin: MQTTOrigin
    ) -> tuple[str, dict[str, Any]]:
        """Return the discovery dictionary for the MQTT device."""
        cmps = {
            k: hass_abbreviate(v.as_discovery_dict) for k, v in self.components.items()
        }
        for key, platform in self.remove_components.items():
            cmps[key] = {"p": cmps[key]["p"] if key in cmps else platform}

        return (
            f"homeassistant/device/{self.id}/config",
            {
                "dev": as_dict(self, exclude=["components", "remove_components"]),
                "o": as_dict(origin),
                "avty": {"topic": availability_topic},
                "cmps": cmps,
            },
        )
