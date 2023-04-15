"""MQTT entities."""
import inspect
import logging
from typing import Any, Callable, Sequence, Union

import attr

from mqtt_entity.utils import required

_LOGGER = logging.getLogger(__name__)

# pylint: disable=too-few-public-methods, too-many-instance-attributes


@attr.define
class Device:
    """A Home Assistant Device, used to group entities."""

    identifiers: list[Union[str, tuple[str, Any]]] = attr.field(validator=required)
    connections: list[str] = attr.field(factory=list)
    configuration_url: str = attr.field(default="")
    manufacturer: str = attr.field(default="")
    model: str = attr.field(default="")
    name: str = attr.field(default="")
    suggested_area: str = attr.field(default="")
    sw_version: str = attr.field(default="")
    via_device: str = attr.field(default="")

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """The device identifier."""
        return str(self.identifiers[0])


@attr.define
class Availability:
    """Represent Home Assistant entity availability."""

    topic: str = attr.field()
    payload_available: str = attr.field(default="online")
    payload_not_available: str = attr.field(default="offline")
    value_template: str = attr.field(default="")


@attr.define
class Entity:
    """A generic Home Assistant entity used as the base class for other entities."""

    unique_id: str = attr.field()
    device: Device = attr.field()
    state_topic: str = attr.field()
    name: str = attr.field()
    availability: list[Availability] = attr.field(factory=list)
    availability_mode: str = attr.field(default="")
    device_class: str = attr.field(default="")
    unit_of_measurement: str = attr.field(default="")
    state_class: str = attr.field(default="")
    expire_after: int = attr.field(default=0)
    """Unavailable if not updated."""
    enabled_by_default: bool = attr.field(default=True)
    entity_category: str = attr.field(default="")
    icon: str = attr.field(default="")

    _path = ""

    def __attrs_post_init__(self) -> None:
        """Init the class."""
        if not self.state_class and self.device_class == "energy":
            self.state_class = "total_increasing"

    @property
    def asdict(self) -> dict:
        """Represent the entity as a dictionary, without empty values and defaults."""

        def _filter(atrb: attr.Attribute, value: Any) -> bool:
            return (
                bool(value) and atrb.default != value and not inspect.isfunction(value)
            )

        return attr.asdict(self, filter=_filter)

    @property
    def topic(self) -> str:
        """Discovery topic."""
        uid, did = self.unique_id, self.device.id
        if uid.startswith(did):
            uid = uid[len(did) :].strip("_")
        return f"homeassistant/{self._path}/{did}/{uid}/config"


@attr.define
class SensorEntity(Entity):
    """A Home Assistant Sensor entity."""

    _path = "sensor"


@attr.define
class BinarySensorEntity(Entity):
    """A Home Assistant Binary Sensor entity."""

    payload_on: str = attr.field(default="ON")
    payload_off: str = attr.field(default="OFF")

    _path = "binary_sensor"


@attr.define
class SelectEntity(Entity):
    """A HomeAssistant Select entity."""

    command_topic: str = attr.field(default=None, validator=required)
    options: Sequence[str] = attr.field(default=None, validator=required)

    on_change: Callable = attr.field(default=None)

    _path = "select"


@attr.define
class SwitchEntity(Entity):
    """A Home Assistant Binary Sensor entity."""

    payload_on: Union[str, int] = attr.field(default=1)
    payload_off: Union[str, int] = attr.field(default=0)
    command_topic: str = attr.field(default=None, validator=required)

    on_change: Callable = attr.field(default=None)
    _path = "switch"


@attr.define
class NumberEntity(Entity):
    """A HomeAssistant Number entity."""

    command_topic: str = attr.field(default=None, validator=required)
    min: float = attr.field(default=0.0)
    max: float = attr.field(default=100.0)
    mode: str = attr.field(default="auto")
    step: float = attr.field(default=1.0)

    on_change: Callable = attr.field(default=None)

    _path = "number"


def hass_device_class(*, unit: str) -> str:
    """Get the HASS device_class from the unit."""
    return {
        "W": "power",
        "kW": "power",
        "kVA": "apparent_power",
        "V": "voltage",
        "kWh": "energy",
        "kVah": "",  # Not energy
        "A": "current",
        "°C": "temperature",
        "%": "battery",
    }.get(unit, "")


def hass_default_rw_icon(*, unit: str) -> str:
    """Get the HASS default icon from the unit."""
    return {
        "W": "mdi:flash",
        "V": "mdi:sine-wave",
        "A": "mdi:current-ac",
        "%": "mdi:battery-lock",
    }.get(unit, "")
