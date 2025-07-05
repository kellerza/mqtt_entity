"""Helpers."""

from typing import Any, NotRequired, TypedDict


def hass_default_rw_icon(*, unit: str) -> str:
    """Get the HASS default icon from the unit."""
    return {
        "W": "mdi:flash",
        "V": "mdi:sine-wave",
        "A": "mdi:current-ac",
        "%": "mdi:battery-lock",
    }.get(unit, "")


def hass_device_class(*, unit: str) -> str:
    """Get the HASS device_class from the unit."""
    return {
        "W": "power",
        "kW": "power",
        "kVA": "apparent_power",
        "VA": "apparent_power",
        "V": "voltage",
        "kWh": "energy",
        "kVAh": "",  # Not energy
        "A": "current",
        "°C": "temperature",
        "%": "battery",
    }.get(unit, "")


class MQTTEntityOptions(TypedDict):
    """Shared MQTTEntity options."""

    name: str
    unique_id: str
    state_topic: str
    object_id: NotRequired[str]

    device_class: NotRequired[str]
    enabled_by_default: NotRequired[bool]
    entity_category: NotRequired[str]
    entity_picture: NotRequired[str]
    expire_after: NotRequired[int]
    icon: NotRequired[str]
    json_attributes_topic: NotRequired[str]
    state_class: NotRequired[str]
    unit_of_measurement: NotRequired[str]

    discovery_extra: NotRequired[dict[str, Any]]
