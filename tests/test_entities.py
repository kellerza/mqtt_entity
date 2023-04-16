"""Test entities."""
import pytest

from mqtt_entity import (
    Availability,
    Device,
    Entity,
    NumberEntity,
    RWEntity,
    SensorEntity,
)


def test_ent():
    """Test entity."""
    with pytest.raises(TypeError) as err:
        Entity()
        assert "unique_id" in err
        assert "device" in err
        assert "state_topic" in err
        assert "name" in err
    kwa = {
        "unique_id": "1",
        "device": Device(identifiers=["d"]),
        "state_topic": "/top",
        "name": "a",
    }
    with pytest.raises(TypeError) as err:
        Entity(**kwa)
        assert " Entity directly" in err
    with pytest.raises(TypeError) as err:
        RWEntity(command_topic="/a", **kwa)
        assert " RWEntity directly" in err
    with pytest.raises(ValueError) as err:
        NumberEntity(**kwa)
        assert "command_topic" in err
        assert "mzzzissingx" in err
    NumberEntity(command_topic="/a", **kwa)


def test_dev():
    """Test device."""
    with pytest.raises(TypeError):
        Device()
    with pytest.raises(ValueError):
        Device(identifiers=[])
    Device(identifiers=["123"])


def test_mqtt_entity():
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

    assert ent.topic == "homeassistant/sensor/123/789/config"
