"""Test helpers."""
from mqtt_entity.helpers import hass_default_rw_icon, hass_device_class


def test_helpers():
    """Test helpers."""
    assert hass_device_class(unit="kWh") == "energy"
    assert hass_default_rw_icon(unit="W") == "mdi:flash"
