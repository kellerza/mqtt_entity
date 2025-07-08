"""Test MQTT class."""

import asyncio
import logging
from json import dumps
from os import getenv
from unittest.mock import MagicMock, Mock, patch

import pytest

import mqtt_entity
from mqtt_entity.client import _mqtt_on_connect

_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.mqtt
async def test_mqtt_server() -> None:
    """Test MQTT."""
    mqc: mqtt_entity.MQTTClient

    async def select_select(msg: str) -> None:
        _LOGGER.error("onchange start: %s", msg)
        await mqc.publish(f"test/{select_id2}", "opt 4")
        await mqc.publish(f"test/{select_id}", msg)
        _LOGGER.error("onchange done: %s", msg)

    _loop = asyncio.get_running_loop()

    def select_select2(msg: str) -> None:
        _LOGGER.error("onchange no async: %s", msg)
        _loop.create_task(mqc.publish(f"test/{select_id2}", msg))
        _LOGGER.error("onchange no async done: %s", msg)

    select_id = "t_select_1"
    select_id2 = "t_select_2"
    sense_id = "t_sense_1"

    dev1 = mqtt_entity.MQTTDevice(
        identifiers=["test456"],
        components={
            e.unique_id: e
            for e in [
                mqtt_entity.MQTTSelectEntity(
                    name="Test select entity",
                    unique_id=select_id,
                    command_topic=f"test/{select_id}_set",
                    options=["opt 1", "opt 2"],
                    on_command=select_select,
                    state_topic=f"test/{select_id}",
                ),
                mqtt_entity.MQTTSelectEntity(
                    name="Test select entity 3",
                    unique_id=select_id2,
                    command_topic=f"test/{select_id2}_set",
                    options=["opt 3", "opt 4"],
                    on_command=select_select2,
                    state_topic=f"test/{select_id2}",
                ),
                mqtt_entity.MQTTSensorEntity(
                    name="Test sensor entity",
                    unique_id=sense_id,
                    state_topic=f"test/{sense_id}",
                ),
            ]
        },
    )
    dev2 = mqtt_entity.MQTTDevice(
        identifiers=["test789"],
        components={},
    )

    mqc = mqtt_entity.MQTTClient(
        devs=[dev1, dev2],
        availability_topic="test/available",
        origin_name="Test Origin",
    )

    await mqc.connect(
        username=getenv("MQTT_USERNAME", ""),
        password=getenv("MQTT_PASSWORD", ""),
        host=getenv("MQTT_HOST", ""),
    )

    _LOGGER.info("Publishing discovery info for test device")
    await mqc.publish(
        "homeassistant/blah/test456/zz/config",
        dumps({"unique_id": "zz"}),
        retain=True,
    )

    _LOGGER.info("Start & Publishing discovery info")
    mqc.publish_discovery_info_when_online()
    # mqc.migrate_entities = False
    # await mqc._publish_discovery_info()
    await asyncio.sleep(0.1)

    await mqc.publish(f"test/{select_id}", "opt 2")
    await mqc.publish(f"test/{select_id2}", "opt 3")
    await mqc.publish(f"test/{sense_id}", "yay!")
    for _ in range(100):
        await asyncio.sleep(0.5)
    # await mqc.migrate_discovery_info()

    await mqc.disconnect()
    await asyncio.sleep(0.1)

    assert False


# @pytest.mark.asyncio
# @pytest.mark.mqtt
# async def test_mqtt_discovery() -> None:
#     """Test MQTT."""
#     root = "test2"
#     sensor_id = [f"sen{i}" for i in range(3)]

#     entities = [
#         mqtt_entity.MQTTSensorEntity(
#             name="Test select entity",
#             unique_id=id,
#             state_topic=f"{root}/{id}",
#         )
#         for id in sensor_id
#     ]
#     dev = mqtt_entity.MQTTDevice(
#         identifiers=[f"id_{root}"],
#         components={e.unique_id: e for e in entities},
#     )
#     mqc = mqtt_entity.MQTTClient(devs=[dev])
#     mqc.availability_topic = f"{root}/available"
#     await mqc.connect(username=MQTT_USER, password=MQTT_PASS, host=MQTT_HOST)

#     await mqc.publish_discovery_info()
#     await asyncio.sleep(0.1)

#     # Remove the first entiry
#     entities.pop(1)

#     with patch("mqtt_entity.client._LOGGER") as mock_log:
#         await mqc.publish_discovery_info()
#         mock_log.info.assert_called_with(
#             "Removing HASS MQTT discovery info %s",
#             f"homeassistant/sensor/id_{root}/sen1/config",
#         )

#         mock_log.info.reset_mock()

#         entities.pop(1)
#         await mqc.migrate_discovery_info()
#         assert mock_log.info.call_count == 2
#         mock_log.info.assert_any_call(
#             "Removing HASS MQTT discovery info %s",
#             f"homeassistant/sensor/id_{root}/sen0/config",
#         )
#         mock_log.info.assert_any_call(
#             "Removing HASS MQTT discovery info %s",
#             f"homeassistant/sensor/id_{root}/sen2/config",
#         )

#     await mqc.disconnect()
#     await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_connect(caplog: pytest.LogCaptureFixture) -> None:
    """Test connect."""
    with patch("mqtt_entity.client.Client") as client:  # patch paho Client
        cmock = client.return_value = MagicMock()
        cmock.is_connected.side_effect = [False, False, True]
        mqc = mqtt_entity.MQTTClient(devs=[])
        assert not cmock.is_connected()
        assert isinstance(mqc.client, Mock)
        await mqc.connect(None)
        assert 3 == cmock.is_connected.call_count  # retry: 2 fail, 3rd ok
        cmock.is_connected.assert_called()
        assert "Connection" not in caplog.text
        _mqtt_on_connect(client, None, None, 0)  # type:ignore
        assert "Connection" in caplog.text
