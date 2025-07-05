"""Test helpers."""

from mqtt_entity import MQTTSensorEntity
from mqtt_entity.helpers import (
    MQTTEntityOptions,
    hass_default_rw_icon,
    hass_device_class,
)


def test_helpers() -> None:
    """Test helpers."""
    assert hass_device_class(unit="kWh") == "energy"
    assert hass_default_rw_icon(unit="W") == "mdi:flash"


def test_type() -> None:
    """Typedict"""
    res: MQTTEntityOptions = {
        "name": "aa",
        "unique_id": "abc123",
        "state_topic": "/top",
    }
    MQTTSensorEntity(**res)
