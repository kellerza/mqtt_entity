"""Test MQTT class."""
import asyncio
import logging
from unittest.mock import MagicMock, Mock, patch

import pytest

import mqtt_entity
from mqtt_entity.client import _mqtt_on_connect

_LOGGER = logging.getLogger(__name__)

MQTT_HOST = "192.168.1.8"
MQTT_PASS = "hass123"
MQTT_USER = "hass"


@pytest.mark.asyncio
@pytest.mark.mqtt
async def test_mqtt_server():
    """Test MQTT."""
    mqc = mqtt_entity.MQTTClient()
    mqc.availability_topic = "test/available"
    await mqc.connect(username="hass", password="hass123", host="192.168.1.8")
    dev = mqtt_entity.Device(identifiers=["test123"])
    dev2 = mqtt_entity.Device(identifiers=["test789"])

    select_id = "t_select_1"
    select_id2 = "t_select_2"
    sense_id = "t_sense_1"

    async def select_select(msg):
        _LOGGER.error("onchange start: %s", msg)
        await mqc.publish(f"test/{select_id2}", "opt 4")
        await mqc.publish(f"test/{select_id}", msg)
        _LOGGER.error("onchange done: %s", msg)

    _loop = asyncio.get_running_loop()

    def select_select2(msg):
        _LOGGER.error("onchange no async: %s", msg)
        _loop.create_task(mqc.publish(f"test/{select_id2}", msg))
        _LOGGER.error("onchange no async done: %s", msg)

    ent = [
        mqtt_entity.SelectEntity(
            name="Test select entity",
            unique_id=select_id,
            device=dev,
            command_topic=f"test/{select_id}_set",
            options=["opt 1", "opt 2"],
            on_change=select_select,
            state_topic=f"test/{select_id}",
        ),
        mqtt_entity.SelectEntity(
            name="Test select entity 2",
            unique_id=select_id2,
            device=dev,
            command_topic=f"test/{select_id2}_set",
            options=["opt 3", "opt 4"],
            on_change=select_select2,
            state_topic=f"test/{select_id2}",
        ),
        mqtt_entity.SensorEntity(
            name="Test sensor entity",
            unique_id=sense_id,
            device=dev2,
            state_topic=f"test/{sense_id}",
        ),
    ]
    await mqc.publish_discovery_info(entities=ent)
    await asyncio.sleep(0.1)

    await mqc.publish(f"test/{select_id}", "opt 2")
    await mqc.publish(f"test/{select_id2}", "opt 3")
    await mqc.publish(f"test/{sense_id}", "yay!")
    for i in range(100):
        await asyncio.sleep(0.5)
    await mqc.remove_discovery_info(device_ids=[dev.id, dev2.id], keep_topics=[])

    await mqc.disconnect()
    await asyncio.sleep(0.1)

    assert False


@pytest.mark.asyncio
@pytest.mark.mqtt
async def test_mqtt_discovery():
    """Test MQTT."""
    root = "test2"
    mqc = mqtt_entity.MQTTClient()
    mqc.availability_topic = f"{root}/available"
    await mqc.connect(username=MQTT_USER, password=MQTT_PASS, host=MQTT_HOST)
    dev = mqtt_entity.Device(identifiers=[f"id_{root}"])

    sensor_id = [f"sen{i}" for i in range(3)]

    entities = [
        mqtt_entity.SensorEntity(
            name="Test select entity",
            unique_id=id,
            device=dev,
            state_topic=f"{root}/{id}",
        )
        for id in sensor_id
    ]

    await mqc.publish_discovery_info(entities=entities)
    await asyncio.sleep(0.1)

    # Remove the first entiry
    entities.pop(1)

    with patch("mqtt_entity.client._LOGGER") as mock_log:
        await mqc.publish_discovery_info(entities=entities)
        mock_log.info.assert_called_with(
            "Removing HASS MQTT discovery info %s",
            f"homeassistant/sensor/id_{root}/sen1/config",
        )

        mock_log.info.reset_mock()

        entities.pop(1)
        await mqc.remove_discovery_info(device_ids=[f"id_{root}"], keep_topics=[])
        assert mock_log.info.call_count == 2
        mock_log.info.assert_any_call(
            "Removing HASS MQTT discovery info %s",
            f"homeassistant/sensor/id_{root}/sen0/config",
        )
        mock_log.info.assert_any_call(
            "Removing HASS MQTT discovery info %s",
            f"homeassistant/sensor/id_{root}/sen2/config",
        )

    await mqc.disconnect()
    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_connect(caplog):
    """Test connect."""
    with patch("mqtt_entity.client.Client") as client:
        mmock = MagicMock()
        mmock.is_connected.side_effect = [False, False, True]

        client.return_value = mmock
        mqc = mqtt_entity.MQTTClient()

        # assert not mmock.is_connected()
        # assert not cl._client.is_connected()
        # assert cl._client == cmock

        _LOGGER.error(dir(client))
        assert isinstance(mqc._client, Mock)

        await mqc.connect(None)

        assert 3 == mmock.is_connected.call_count

        mmock.is_connected.assert_called()

        assert "Connection" not in caplog.text
        _mqtt_on_connect(None, None, None, 1)
        # assert "Connection" in caplog.text
