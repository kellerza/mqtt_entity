"""Helpers."""
from json import dumps
from typing import Any

from mqtt_entity.client import MQTTClient
from mqtt_entity.entities import Entity


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


async def set_attributes(
    attributes: dict[str, Any],
    *,
    entity: Entity,
    client: MQTTClient,
    retain: bool = False,
) -> None:
    """Set attributes helper."""
    if not entity.attributes_topic:
        raise ValueError(f"Entity '{entity.name}' needs an attributes_topic.")
    await client.publish(
        topic=entity.attributes_topic,
        payload=dumps(attributes),
        retain=retain,
    )
