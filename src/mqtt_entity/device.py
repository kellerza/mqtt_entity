"""HASS MQTT Device, used for device based discovery."""

from dataclasses import dataclass, field
from typing import Any

from .entities import MQTTBaseEntity
from .helpers import DEVREG_ABBREVIATE, ORIGIN_ABBREVIATE, as_dict, hass_abbreviate


@dataclass
class MQTTOrigin:
    """Represent the origin of an MQTT message."""

    name: str
    sw: str = ""
    """ws_version"""
    url: str = ""
    """support_url"""


M_SHARED = {"shared": True}
M_DEV = {"dev": True}


@dataclass
class MQTTDevice:
    """Base class for MQTT Device Discovery. A Home Assistant Device groups entities."""

    identifiers: list[str | tuple[str, Any]] = field(metadata=M_DEV)

    components: dict[str, MQTTBaseEntity]
    """MQTT component entities."""
    remove_components: dict[str, str] = field(default_factory=dict)
    """Components to be removed on discovery. object_id and the platform name."""

    # device options
    connections: list[str] = field(default_factory=list, metadata=M_DEV)
    configuration_url: str = field(default="", metadata=M_DEV)
    manufacturer: str = field(default="", metadata=M_DEV)
    model: str = field(default="", metadata=M_DEV)
    name: str = field(default="", metadata=M_DEV)
    suggested_area: str = field(default="", metadata=M_DEV)
    sw_version: str = field(default="", metadata=M_DEV)
    via_device: str = field(default="", metadata=M_DEV)

    # shared options
    state_topic: str = field(default="", metadata=M_SHARED)
    command_topic: str = field(default="", metadata=M_SHARED)
    qos: str = field(default="", metadata=M_SHARED)

    def __post_init__(self) -> None:
        """Post init."""
        if not self.identifiers:
            raise ValueError("MQTTDevice must have at least one identifier.")

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
