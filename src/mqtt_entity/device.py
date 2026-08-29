"""HASS MQTT Device, used for device based discovery."""

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from json import dumps
from typing import Any, Literal

from .entities import MQTTBaseEntity
from .helpers import DEVREG_ABBREVIATE, ORIGIN_ABBREVIATE, as_dict, hass_abbreviate
from .utils import slug

_DISCOVERY_DEBOUNCE_S = 5.0


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

    identifiers: list[str | tuple[str, Any]] = field(metadata=M_DEV)

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

    _discovery_cache: tuple[str, str] | None = field(
        default=None, repr=False, compare=False
    )
    _discovery_flag_at: float | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Post init."""
        if not self.identifiers:
            raise ValueError("MQTTDevice must have at least one identifier.")

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

    def flag_discovery(self) -> None:
        """Mark discovery as possibly stale.

        The memo is dropped after a short debounce so rapid entity rebuilds
        batch into one ``discovery_info()`` rebuild.
        """
        self._discovery_flag_at = time.monotonic() + _DISCOVERY_DEBOUNCE_S

    def discovery_info(
        self,
        *,
        availability_topic: str = "",
        origin: MQTTOrigin,
    ) -> tuple[str, str]:
        """Return topic and compact JSON payload (memoized).

        Call :meth:`flag_discovery` after mutating components. ``availability_topic``
        and ``origin`` are not part of the cache key; they must stay stable (or
        flag after they change).
        """
        if (
            self._discovery_flag_at is not None
            and time.monotonic() >= self._discovery_flag_at
        ):
            self._discovery_cache = None
            self._discovery_flag_at = None
        if self._discovery_cache is not None:
            return self._discovery_cache

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

        topic = f"homeassistant/device/{self.id}/config"
        payload = dumps(disco_json, indent=None, separators=(",", ":"))
        self._discovery_cache = (topic, payload)
        return self._discovery_cache
