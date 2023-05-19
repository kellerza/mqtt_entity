"""MQTT entities."""
import inspect
import logging
from typing import Any, Callable, Optional, Sequence, Union

import attrs
from attrs import validators

from mqtt_entity.utils import BOOL_OFF, BOOL_ON, required

_LOGGER = logging.getLogger(__name__)

# pylint: disable=too-few-public-methods, too-many-instance-attributes


@attrs.define
class Device:
    """A Home Assistant Device, used to group entities."""

    identifiers: list[Union[str, tuple[str, Any]]] = attrs.field(
        validator=[validators.instance_of(list), validators.min_len(1)]
    )
    connections: list[str] = attrs.field(factory=list)
    configuration_url: str = attrs.field(default="")
    manufacturer: str = attrs.field(default="")
    model: str = attrs.field(default="")
    name: str = attrs.field(default="")
    suggested_area: str = attrs.field(default="")
    sw_version: str = attrs.field(default="")
    via_device: str = attrs.field(default="")

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """The device identifier."""
        return str(self.identifiers[0])


@attrs.define
class Availability:
    """Represent Home Assistant entity availability."""

    topic: str = attrs.field()
    payload_available: str = attrs.field(default="online")
    payload_not_available: str = attrs.field(default="offline")
    value_template: str = attrs.field(default="")


@attrs.define
class Entity:
    """A generic Home Assistant entity used as the base class for other entities."""

    unique_id: str = attrs.field()
    device: Device = attrs.field()
    state_topic: str = attrs.field()
    name: str = attrs.field()
    availability: list[Availability] = attrs.field(factory=list)
    availability_mode: str = attrs.field(default="")
    device_class: str = attrs.field(default="")
    unit_of_measurement: str = attrs.field(default="")
    state_class: str = attrs.field(default="")
    expire_after: int = attrs.field(default=0)
    """Unavailable if not updated."""
    enabled_by_default: bool = attrs.field(default=True)
    entity_category: str = attrs.field(default="")
    icon: str = attrs.field(default="")
    attributes_topic: str = attrs.field(default="")
    """Used by the set_attributes helper."""

    _path = ""

    def __attrs_post_init__(self) -> None:
        """Init the class."""
        if not self._path:
            raise TypeError(f"Do not instantiate {self.__class__.__name__} directly")
        if not self.state_class and self.device_class == "energy":
            self.state_class = "total_increasing"

    @property
    def asdict(self) -> dict:
        """Represent the entity as a dictionary, without empty values and defaults."""

        def _filter(atrb: attrs.Attribute, value: Any) -> bool:
            return (
                bool(value) and atrb.default != value and not inspect.isfunction(value)
            )

        return attrs.asdict(self, filter=_filter)

    @property
    def topic(self) -> str:
        """Discovery topic."""
        uid, did = self.unique_id, self.device.id
        if uid.startswith(did):
            uid = uid[len(did) :].strip("_")
        return f"homeassistant/{self._path}/{did}/{uid}/config"


@attrs.define
class SensorEntity(Entity):
    """A Home Assistant Sensor entity."""

    _path = "sensor"


@attrs.define
class BinarySensorEntity(Entity):
    """A Home Assistant Binary Sensor entity."""

    payload_on: str = attrs.field(default=BOOL_ON)
    payload_off: str = attrs.field(default=BOOL_OFF)

    _path = "binary_sensor"


@attrs.define
class RWEntity(Entity):
    """Read/Write entity base class.

    This will default to a text entity.
    """

    command_topic: str = attrs.field(
        default="", validator=(validators.instance_of(str), validators.min_len(2))
    )

    on_change: Optional[Callable] = attrs.field(default=None)

    _path = "text"


@attrs.define
class SelectEntity(RWEntity):
    """A HomeAssistant Select entity."""

    options: Sequence[str] = attrs.field(default=None, validator=required)

    _path = "select"


@attrs.define
class SwitchEntity(RWEntity):
    """A Home Assistant Switch entity."""

    payload_on: str = attrs.field(default=BOOL_ON)
    payload_off: str = attrs.field(default=BOOL_OFF)

    _path = "switch"


@attrs.define
class NumberEntity(RWEntity):
    """A HomeAssistant Number entity."""

    min: float = attrs.field(default=0.0)
    max: float = attrs.field(default=100.0)
    mode: str = attrs.field(default="auto")
    step: float = attrs.field(default=1.0)

    _path = "number"
