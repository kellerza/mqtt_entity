"""HASS MQTT Device, used for device based discovery."""

from typing import Any

import attrs
from attrs import validators

from .entities import MQTTBaseEntity
from .helpers import DEVREG_ABBREVIATE, ORIGIN_ABBREVIATE, as_dict, hass_abbreviate


@attrs.define()
class MQTTOrigin:
    """Represent the origin of an MQTT message."""

    name: str
    sw: str = ""
    """ws_version"""
    url: str = ""
    """support_url"""


M_SHARED = {"shared": True}
M_DEV = {"dev": True}


@attrs.define()
class MQTTDevice:
    """Base class for MQTT Device Discovery. A Home Assistant Device groups entities."""

    identifiers: list[str | tuple[str, Any]] = attrs.field(
        validator=[validators.instance_of(list), validators.min_len(1)], metadata=M_DEV
    )

    components: dict[str, MQTTBaseEntity]
    """MQTT component entities."""
    remove_components: dict[str, str] = attrs.field(factory=dict)
    """Components to be removed on discovery. object_id and the platform name."""

    # device options
    connections: list[str] = attrs.field(factory=list, metadata=M_DEV)
    configuration_url: str = attrs.field(default="", metadata=M_DEV)
    manufacturer: str = attrs.field(default="", metadata=M_DEV)
    model: str = attrs.field(default="", metadata=M_DEV)
    name: str = attrs.field(default="", metadata=M_DEV)
    suggested_area: str = attrs.field(default="", metadata=M_DEV)
    sw_version: str = attrs.field(default="", metadata=M_DEV)
    via_device: str = attrs.field(default="", metadata=M_DEV)

    # shared options
    state_topic: str = attrs.field(default="", metadata=M_SHARED)
    command_topic: str = attrs.field(default="", metadata=M_SHARED)
    qos: str = attrs.field(default="", metadata=M_SHARED)

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

        disco_json = {
            "dev": hass_abbreviate(
                as_dict(self, metadata_key="dev"), abbreviations=DEVREG_ABBREVIATE
            ),
            "o": hass_abbreviate(as_dict(origin), abbreviations=ORIGIN_ABBREVIATE),
        }
        if shared := as_dict(self, metadata_key="shared"):
            disco_json.update(shared)

        if availability_topic:
            disco_json["avty"] = {"topic": availability_topic}
        disco_json["cmps"] = cmps

        return f"homeassistant/device/{self.id}/config", disco_json
