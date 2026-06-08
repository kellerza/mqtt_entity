"""Test entities."""

from unittest.mock import AsyncMock

import pytest

from mqtt_entity import (
    MQTTDevice,
    MQTTDeviceTrigger,
    MQTTEntity,
    MQTTNumberEntity,
    MQTTSensorEntity,
)
from mqtt_entity.client import MQTTAsyncClient
from mqtt_entity.device import MQTTOrigin


def test_ent() -> None:
    """Test entity."""
    with pytest.raises(TypeError) as err:
        MQTTEntity()  # type: ignore[call-arg]
    assert "unique_id" in str(err)
    assert "state_topic" in str(err)
    assert "name" in str(err)
    kwa = {
        "unique_id": "1",
        "state_topic": "/top",
        "name": "a",
    }
    with pytest.raises(TypeError) as err:
        MQTTEntity(**kwa)  # type: ignore[arg-type]
    assert " MQTTEntity directly" in str(err)
    # with pytest.raises(TypeError) as err:
    #     RWEntity(command_topic="/a", **kwa)  # type: ignore[arg-type]
    #     assert " RWEntity directly" in str(err)
    with pytest.raises(ValueError) as err2:
        MQTTNumberEntity(**kwa)  # type: ignore[arg-type]
    assert "command_topic" in str(err2)
    MQTTNumberEntity(command_topic="/a", **kwa)  # type: ignore[arg-type]


def test_dev() -> None:
    """Test device."""
    with pytest.raises(TypeError):
        MQTTDevice()  # type: ignore[call-arg]
    with pytest.raises(ValueError):
        MQTTDevice(identifiers=[], components={})
    MQTTDevice(identifiers=["123"], components={})


def test_mqtt_entity() -> None:
    """Test MQTT."""
    ent = MQTTSensorEntity(
        name="test1",
        unique_id="789",
        state_topic="/test/a",
    )

    dev = MQTTDevice(identifiers=["123"], components={"789": ent})
    origin = MQTTOrigin(name="Test Origin")
    d_topic, d_dict = dev.discovery_info(availability_topic="/blah", origin=origin)

    assert d_topic == "homeassistant/device/123/config"
    assert d_dict == {
        "dev": {"ids": ["123"]},
        "o": {"name": "Test Origin"},
        "avty": {"topic": "/blah"},
        "cmps": {
            "789": {
                "name": "test1",
                "p": "sensor",
                "uniq_id": "789",
                "stat_t": "/test/a",
            }
        },
    }


def test_discovery_extra() -> None:
    """Test discovery_extra."""
    ent = MQTTSensorEntity(
        name="test1",
        unique_id="789",
        state_topic="/test/a",
        json_attributes_topic="/test/f",
        discovery_extra={"a": "b", "state_topic": "c"},
    )

    dev = MQTTDevice(identifiers=["123"], components={"789": ent})
    origin = MQTTOrigin(name="Test Origin")
    d_topic, d_dict = dev.discovery_info(availability_topic="/blah", origin=origin)

    assert d_topic == "homeassistant/device/123/config"
    assert d_dict == {
        "dev": {"ids": ["123"]},
        "o": {"name": "Test Origin"},
        "avty": {"topic": "/blah"},
        "cmps": {
            "789": {
                "name": "test1",
                "uniq_id": "789",
                "json_attr_t": "/test/f",
                "stat_t": "c",
                "a": "b",
                "p": "sensor",
            }
        },
    }


def test_device_trigger() -> None:
    """Test device trigger.

    Examples from: https://www.home-assistant.io/integrations/device_trigger.mqtt/
    """
    trig = MQTTDeviceTrigger(
        type="action",
        subtype="arrow_left_click",
        payload="arrow_left_click",
        topic="zigbee2mqtt/0x90fd9ffffedf1266/action",
    )

    dev = MQTTDevice(identifiers=["123", "456"], components={"trigger1": trig})
    origin = MQTTOrigin(name="Test Origin")
    d_topic, d_dict = dev.discovery_info(availability_topic="/blah", origin=origin)

    assert d_topic == "homeassistant/device/123/config"
    assert d_dict == {
        "dev": {
            "ids": [
                "123",
                "456",
            ],
        },
        "o": {
            "name": "Test Origin",
        },
        "avty": {
            "topic": "/blah",
        },
        "cmps": {
            "trigger1": {
                "atype": "trigger",
                "t": "zigbee2mqtt/0x90fd9ffffedf1266/action",
                "type": "action",
                "stype": "arrow_left_click",
                "pl": "arrow_left_click",
                "p": "device_automation",
            }
        },
    }


def test_mqtt_device_discovery_registry_fields() -> None:
    """Device registry fields and shared ``qos`` appear in discovery (abbreviated ``dev``)."""
    ent = MQTTSensorEntity(
        name="s",
        unique_id="u1",
        state_topic="/st",
    )
    dev = MQTTDevice(
        identifiers=["dev1"],
        components={"c1": ent},
        connections=[("mac", "02:aa:bb:cc:dd:01")],
        hw_version="1.0",
        model_id="SKU-1",
        serial_number="SN-99",
        qos=1,
    )
    origin = MQTTOrigin(name="Origin")
    _topic, d_dict = dev.discovery_info(availability_topic="/av", origin=origin)

    assert d_dict["dev"]["ids"] == ["dev1"]
    assert d_dict["dev"]["cns"] == [("mac", "02:aa:bb:cc:dd:01")]
    assert d_dict["dev"]["hw"] == "1.0"
    assert d_dict["dev"]["mdl_id"] == "SKU-1"
    assert d_dict["dev"]["sn"] == "SN-99"
    assert d_dict["qos"] == 1


def test_mqtt_device_discovery_multi_availability_mode() -> None:
    """Multiple ``avty`` topics: default omits ``avty_mode`` (HA ``latest``); ``any`` is set."""
    ent = MQTTSensorEntity(name="s", unique_id="u1", state_topic="/st")
    origin = MQTTOrigin(name="O")

    dev_default = MQTTDevice(
        identifiers=["d1"],
        components={"c1": ent},
        availability_topics=["t1", "t2"],
    )
    _, d0 = dev_default.discovery_info(origin=origin)
    assert d0["avty"] == [{"topic": "t1"}, {"topic": "t2"}]
    assert "avty_mode" not in d0

    dev_any = MQTTDevice(
        identifiers=["d2"],
        components={"c1": ent},
        availability_topics=["t1", "t2"],
        availability_mode="any",
    )
    _, d1 = dev_any.discovery_info(origin=origin)
    assert d1["avty_mode"] == "any"


@pytest.mark.asyncio
async def test_set_attributes() -> None:
    """Test set_attributes."""
    e = MQTTSensorEntity(
        json_attributes_topic="blah",
        unique_id="a1",
        state_topic="/st",
        name="test1",
    )
    mc = AsyncMock(spec=MQTTAsyncClient)
    thea = {"the": "attr"}
    await e.send_json_attributes(mc, thea)
    assert mc.publish.call_count == 1
    assert mc.publish.call_args[1]["topic"] == "blah"
