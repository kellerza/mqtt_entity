"""MQTT entities."""

import inspect
import logging
from typing import Any, Callable, Sequence

import attrs
from attrs import validators

from mqtt_entity.utils import BOOL_OFF, BOOL_ON, required

_LOGGER = logging.getLogger(__name__)

# pylint: disable=too-few-public-methods, too-many-instance-attributes


@attrs.define()
class Device:
    """A Home Assistant Device, used to group entities."""

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
        """The device identifier."""
        return str(self.identifiers[0])


@attrs.define()
class Availability:
    """Represent Home Assistant entity availability."""

    topic: str
    payload_available: str = "online"
    payload_not_available: str = "offline"
    value_template: str = ""


@attrs.define()
class DiscoveryEntity:
    """Base class for entities that support MQTT Discovery."""

    @property
    def discovery_topic(self) -> str:
        """Discovery topic."""
        raise NotImplementedError("Subclasses must implement discovery_topic")

    def discovery_final(self, result: dict[str, Any]) -> None:
        """Return the final discovery dictionary."""

    @property
    def asdict(self) -> dict[str, Any]:
        """Represent the entity as a dictionary, without empty values and defaults."""

        def _filter(atrb: attrs.Attribute, value: Any) -> bool:
            if atrb.name in ("discovery_extra", "discovery_topic", "_path"):
                return False
            return (
                bool(value) and atrb.default != value and not inspect.isfunction(value)
            )

        res = attrs.asdict(self, filter=_filter)

        extra = getattr(self, "discovery_extra", None)
        if extra:
            keys = {
                key: extra[key]
                for key in extra
                if key in res and res[key] != extra[key]
            }
            _LOGGER.debug("Overwriting %s", keys)
            res.update(extra)

        self.discovery_final(res)
        return res


@attrs.define()
class Entity(DiscoveryEntity):
    """A generic Home Assistant entity used as the base class for other entities."""

    unique_id: str
    device: Device
    state_topic: str
    name: str
    availability: list[Availability] = attrs.field(factory=list)
    availability_mode: str = ""
    device_class: str = ""
    unit_of_measurement: str = ""
    state_class: str = ""
    expire_after: int = 0
    """Unavailable if not updated."""
    enabled_by_default: bool = True
    entity_category: str = ""
    icon: str = ""
    json_attributes_topic: str = ""
    """Used by the set_attributes helper."""

    discovery_extra: dict[str, Any] = attrs.field(factory=dict)
    """Additional MQTT Discovery attributes."""

    _path = ""

    def __attrs_post_init__(self) -> None:
        """Init the class."""
        if not self._path:
            raise TypeError(f"Do not instantiate {self.__class__.__name__} directly")
        if not self.state_class and self.device_class == "energy":
            self.state_class = "total_increasing"

    @property
    def discovery_topic(self) -> str:
        """Discovery topic."""
        uid, did = self.unique_id, self.device.id
        if uid.startswith(did):
            uid = uid[len(did) :].strip("_")
        return f"homeassistant/{self._path}/{did}/{uid}/config"


@attrs.define()
class SensorEntity(Entity):
    """A Home Assistant Sensor entity."""

    _path = "sensor"


@attrs.define()
class BinarySensorEntity(Entity):
    """A Home Assistant Binary Sensor entity."""

    payload_on: str = BOOL_ON
    payload_off: str = BOOL_OFF

    _path = "binary_sensor"


@attrs.define()
class DeviceTrigger(DiscoveryEntity):
    """A Home Assistant Device trigger.

    https://www.home-assistant.io/integrations/device_trigger.mqtt/
    """

    device: Device
    """Topic to publish the trigger to."""
    type: str
    subtype: str
    payload: str
    topic: str

    _path = "device_automation"

    def discovery_final(self, result: dict[str, Any]) -> None:
        """Return the final discovery dictionary."""
        result["automation_type"] = "trigger"
        result["platform"] = "device_automation"

    discovery_extra: dict[str, Any] = attrs.field(factory=dict)
    """Additional MQTT Discovery attributes."""

    @property
    def name(self) -> str:
        """Return the name of the trigger."""
        return f"{self.device.name} {self.type} {self.subtype}".strip()

    @property
    def discovery_topic(self) -> str:
        """Discovery topic."""
        did = self.device.id
        return f"homeassistant/{self._path}/{did}/{self.type}_{self.subtype}/config"


@attrs.define()
class RWEntity(Entity):
    """Read/Write entity base class.

    This will default to a text entity.
    """

    command_topic: str = attrs.field(
        default="", validator=(validators.instance_of(str), validators.min_len(2))
    )

    on_change: Callable | None = None

    _path = "text"


@attrs.define()
class SelectEntity(RWEntity):
    """A HomeAssistant Select entity."""

    options: Sequence[str] = attrs.field(default=None, validator=required)

    _path = "select"


@attrs.define()
class SwitchEntity(RWEntity):
    """A Home Assistant Switch entity."""

    payload_on: str = BOOL_ON
    payload_off: str = BOOL_OFF

    _path = "switch"


@attrs.define()
class NumberEntity(RWEntity):
    """A HomeAssistant Number entity."""

    min: float = 0.0
    max: float = 100.0
    mode: str = "auto"
    step: float = 1.0

    _path = "number"
