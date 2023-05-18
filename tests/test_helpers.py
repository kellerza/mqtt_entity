"""Test helpers."""
from unittest.mock import AsyncMock

import pytest

from mqtt_entity import Device, SensorEntity
from mqtt_entity.helpers import hass_default_rw_icon, hass_device_class, set_attributes


def test_helpers():
    """Test helpers."""
    assert hass_device_class(unit="kWh") == "energy"
    assert hass_default_rw_icon(unit="W") == "mdi:flash"


@pytest.mark.asyncio
async def test_set_attributes():
    """Test set_attributes."""
    dev = Device(identifiers=["test123"])
    e = SensorEntity(
        attributes_topic="blah",
        unique_id="a1",
        device=dev,
        state_topic="/st",
        name="test1",
    )
    mc = AsyncMock()
    thea = {"the": "attr"}
    await set_attributes(thea, entity=e, client=mc)
    assert mc.publish.call_count == 1
    assert mc.publish.call_args[1]["topic"] == "blah"
