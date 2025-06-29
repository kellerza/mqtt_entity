"""Test helpers."""

from unittest.mock import AsyncMock

import pytest

from mqtt_entity import MQTTSensorEntity, hass_default_rw_icon, hass_device_class


def test_helpers() -> None:
    """Test helpers."""
    assert hass_device_class(unit="kWh") == "energy"
    assert hass_default_rw_icon(unit="W") == "mdi:flash"


@pytest.mark.asyncio
async def test_set_attributes() -> None:
    """Test set_attributes."""
    e = MQTTSensorEntity(
        json_attributes_topic="blah",
        unique_id="a1",
        state_topic="/st",
        name="test1",
    )
    mc = AsyncMock()
    thea = {"the": "attr"}
    await e.send_json_attributes(mc, thea)
    assert mc.publish.call_count == 1
    assert mc.publish.call_args[1]["topic"] == "blah"
