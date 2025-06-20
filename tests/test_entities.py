"""Test entities."""

import pytest

from mqtt_entity import (
    Availability,
    Device,
    DeviceTrigger,
    Entity,
    NumberEntity,
    SensorEntity,
)


def test_ent() -> None:
    """Test entity."""
    with pytest.raises(TypeError) as err:
        Entity()  # type: ignore
    assert "unique_id" in str(err)
    assert "device" in str(err)
    assert "state_topic" in str(err)
    assert "name" in str(err)
    kwa = {
        "unique_id": "1",
        "device": Device(identifiers=["d"]),
        "state_topic": "/top",
        "name": "a",
    }
    with pytest.raises(TypeError) as err:
        Entity(**kwa)  # type: ignore
        assert " Entity directly" in str(err)
    # with pytest.raises(TypeError) as err:
    #     RWEntity(command_topic="/a", **kwa)  # type: ignore
    #     assert " RWEntity directly" in str(err)
    with pytest.raises(ValueError) as err2:
        NumberEntity(**kwa)  # type: ignore
        assert "command_topic" in str(err2)
        assert "mzzzissingx" in str(err2)
    NumberEntity(command_topic="/a", **kwa)  # type: ignore


def test_dev() -> None:
    """Test device."""
    with pytest.raises(TypeError):
        Device()  # type: ignore
    with pytest.raises(ValueError):
        Device(identifiers=[])
    Device(identifiers=["123"])


def test_mqtt_entity() -> None:
    """Test MQTT."""
    dev = Device(identifiers=["123"])

    ava = Availability(topic="/blah")

    ent = SensorEntity(
        name="test1",
        unique_id="789",
        device=dev,
        availability=[ava],
        state_topic="/test/a",
    )
    assert ent.asdict == {
        "name": "test1",
        "unique_id": "789",
        "device": {"identifiers": ["123"]},
        "availability": [{"topic": "/blah"}],
        "state_topic": "/test/a",
    }

    assert ent.discovery_topic == "homeassistant/sensor/123/789/config"


def test_discovery_extra() -> None:
    """Test discovery_extra."""
    dev = Device(identifiers=["123"])

    ava = Availability(topic="/blah")

    ent = SensorEntity(
        name="test1",
        unique_id="789",
        device=dev,
        availability=[ava],
        state_topic="/test/a",
        json_attributes_topic="/test/f",
        discovery_extra={"a": "b", "state_topic": "c"},
    )
    assert ent.asdict == {
        "name": "test1",
        "unique_id": "789",
        "device": {"identifiers": ["123"]},
        "availability": [{"topic": "/blah"}],
        "json_attributes_topic": "/test/f",
        "state_topic": "c",
        "a": "b",
    }

    assert ent.discovery_topic == "homeassistant/sensor/123/789/config"


def test_device_trigger() -> None:
    """Test device trigger.

    Examples from: https://www.home-assistant.io/integrations/device_trigger.mqtt/
    """
    dev = Device(identifiers=["123", "456"])

    trig = DeviceTrigger(
        device=dev,
        type="action",
        subtype="arrow_left_click",
        payload="arrow_left_click",
        topic="zigbee2mqtt/0x90fd9ffffedf1266/action",
    )
    assert trig.asdict == {
        "automation_type": "trigger",
        "device": {"identifiers": ["123", "456"]},
        "topic": "zigbee2mqtt/0x90fd9ffffedf1266/action",
        "type": "action",
        "subtype": "arrow_left_click",
        "payload": "arrow_left_click",
        "platform": "device_automation",
    }

    assert (
        trig.discovery_topic
        == "homeassistant/device_automation/123/action_arrow_left_click/config"
    )
