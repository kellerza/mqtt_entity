"""HASS MQTT Device, used for device based discovery."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from .entities import MQTTBaseEntity
from .helpers import DEVREG_ABBREVIATE, ORIGIN_ABBREVIATE, as_dict, hass_abbreviate
from .utils import slug


def unique_str(topics: Iterable[str]) -> list[str]:
    """Return unique strings in first-seen order, omitting falsey values."""
    out: list[str] = []
    for t in topics:
        if t and t not in out:
            out.append(t)
    return out


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

AvailabilityMode = Literal["", "all", "any", "latest"]


@dataclass
class MQTTDevice:
    """Base class for MQTT Device Discovery. A Home Assistant Device groups entities."""

    identifiers: list[tuple[str, Any]] = field(metadata=M_DEV)

    components: dict[str, MQTTBaseEntity]
    """MQTT component entities."""
    remove_components: dict[str, str] = field(default_factory=dict)
    """Components to be removed on discovery. object_id and the platform name."""

    # device options
    connections: list[tuple[str, str]] = field(default_factory=list, metadata=M_DEV)
    configuration_url: str = field(default="", metadata=M_DEV)
    manufacturer: str = field(default="", metadata=M_DEV)
    model: str = field(default="", metadata=M_DEV)
    model_id: str = field(default="", metadata=M_DEV)
    hw_version: str = field(default="", metadata=M_DEV)
    serial_number: str = field(default="", metadata=M_DEV)
    name: str = field(default="", metadata=M_DEV)
    suggested_area: str = field(default="", metadata=M_DEV)
    sw_version: str = field(default="", metadata=M_DEV)
    via_device: str = field(default="", metadata=M_DEV)

    # shared options
    state_topic: str = field(default="", metadata=M_SHARED)
    command_topic: str = field(default="", metadata=M_SHARED)
    qos: int | None = field(default=None, metadata=M_SHARED)

    availability_topics: list[str] = field(default_factory=list)
    """Additional availability topics for the device.

    The client's ``availability_topic`` can still be merged in with these during discovery info.
    MQTT last-will only applies only to the MQTTClient's primary ``availability_topic``.
    """

    availability_mode: AvailabilityMode = ""
    """When several availability topics are used: ``all``, ``any``, or ``latest`` (HA default if omitted)."""

    def __post_init__(self) -> None:
        """Post init."""
        if not self.identifiers:
            raise ValueError("MQTTDevice must have at least one identifier.")

        for idx in range(len(self.identifiers)):
            _id = self.identifiers[idx]
            if not isinstance(_id, tuple):
                self.identifiers[idx] = ("serial", str(_id))

        if self.availability_mode not in ("", "all", "any", "latest"):
            raise ValueError(
                "availability_mode must be '', 'all', 'any', or 'latest', "
                f"not {self.availability_mode!r}"
            )

    @property
    def id(self) -> str:
        """The device identifier. Also object_id."""
        _id = self.identifiers[0]
        return slug(str(_id[1] if isinstance(_id, tuple) else _id))

    def discovery_info(
        self,
        *,
        availability_topic: str = "",
        origin: MQTTOrigin,
    ) -> tuple[str, dict[str, Any]]:
        """Return the discovery dictionary for the MQTT device.

        An optional ``availability_topic`` will be added to the device's
        :attr:`availability_topics`.
        """
        cmps = {
            k: hass_abbreviate(v.as_discovery_dict) for k, v in self.components.items()
        }
        for key, platform in self.remove_components.items():
            cmps[key] = {"p": cmps[key]["p"] if key in cmps else platform}

        disco_json: dict[str, Any] = {
            "dev": hass_abbreviate(
                as_dict(self, metadata_key="dev"), abbreviations=DEVREG_ABBREVIATE
            ),
            "o": hass_abbreviate(as_dict(origin), abbreviations=ORIGIN_ABBREVIATE),
        }
        if shared := as_dict(self, metadata_key="shared"):
            disco_json.update(shared)

        av_topics = unique_str((*self.availability_topics, availability_topic))
        if len(av_topics) == 1:
            disco_json["avty"] = {"topic": av_topics[0]}
        elif len(av_topics) > 1:
            disco_json["avty"] = [{"topic": t} for t in av_topics]
            effective_mode = self.availability_mode or "latest"
            if effective_mode in ("all", "any"):
                disco_json["avty_mode"] = effective_mode

        disco_json["cmps"] = cmps

        return f"homeassistant/device/{self.id}/config", disco_json
