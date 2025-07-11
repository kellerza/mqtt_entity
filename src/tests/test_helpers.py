"""Test helpers."""

from mqtt_entity import MQTTSensorEntity
from mqtt_entity.helpers import (
    MQTTEntityOptions,
    hass_abbreviate,
    hass_default_rw_icon,
    hass_device_class,
)


def test_hass_abbreviate() -> None:
    """Test discovery_dict."""
    obj = MQTTSensorEntity(
        name="test1",
        unique_id="789",
        state_topic="/test/a",
        json_attributes_topic="/test/f",
        discovery_extra={"a": "b", "state_topic": "xx"},
    )
    res = obj.as_discovery_dict
    assert res == {
        "name": "test1",
        "unique_id": "789",
        "state_topic": "xx",
        "json_attributes_topic": "/test/f",
        "a": "b",
        "platform": "sensor",
    }
    res = hass_abbreviate(res)
    assert res == {
        "name": "test1",
        "uniq_id": "789",
        "stat_t": "xx",
        "json_attr_t": "/test/f",
        "a": "b",
        "p": "sensor",
    }


def test_helpers() -> None:
    """Test helpers."""
    assert hass_device_class(unit="kWh") == "energy"
    assert hass_default_rw_icon(unit="W") == "mdi:flash"


def test_type() -> None:
    """Typedict."""
    res: MQTTEntityOptions = {
        "name": "aa",
        "unique_id": "abc123",
        "state_topic": "/top",
    }
    MQTTSensorEntity(**res)
