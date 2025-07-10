"""Test MQTT class."""

import asyncio
import logging
import time
from os import getenv
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from paho.mqtt.client import Client

import mqtt_entity
from mqtt_entity.options import MQTTOptions

_LOGGER = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.mqtt
async def test_mqtt_server() -> None:
    """Test MQTT."""
    select_id = "t_select_1"
    select_id2 = "t_select_2"
    sense_id = "t_sense_1"

    select_ent = mqtt_entity.MQTTSelectEntity(
        name="Test select entity",
        unique_id=select_id,
        command_topic=f"test/{select_id}_set",
        options=["opt 1", "opt 2", "opt 3", "opt 4", "only 1"],
        state_topic=f"test/{select_id}",
    )
    select_ent2 = mqtt_entity.MQTTSelectEntity(
        name="Test select entity 3",
        unique_id=select_id2,
        command_topic=f"test/{select_id2}_set",
        options=["opt 1", "opt 2", "opt 3", "opt 4", "only 2"],
        state_topic=f"test/{select_id2}",
    )
    sense_ent = mqtt_entity.MQTTSensorEntity(
        name="Test sensor entity",
        unique_id=sense_id,
        state_topic=f"test/{sense_id}",
    )

    mqc = mqtt_entity.MQTTClient(
        availability_topic="test/available",
        origin_name="Test Origin",
    )
    _loop = asyncio.get_running_loop()

    async def select_select(msg: str) -> None:
        _LOGGER.error("onchange start: %s", msg)
        await sense_ent.send_state(
            mqc, f"select entity 1 changed to {msg}. making 2 follow"
        )
        await select_ent2.send_state(mqc, msg)
        _LOGGER.error("onchange done: %s", msg)

    select_ent.on_command = select_select

    async def work2(msg: str) -> None:
        await sense_ent.send_state(
            mqc, f"select entity 2 changed to {msg}. making 1 follow"
        )
        await select_ent.send_state(mqc, msg)

    def select_select2(msg: str) -> None:
        _LOGGER.error("onchange no async: %s", msg)
        _loop.create_task(work2(msg))
        _LOGGER.error("onchange no async done: %s", msg)

    select_ent2.on_command = select_select2

    dev1 = mqtt_entity.MQTTDevice(
        identifiers=["test456"],
        name="Test Device",
        components={e.unique_id: e for e in [select_ent, select_ent2, sense_ent]},
    )
    dev2 = mqtt_entity.MQTTDevice(
        identifiers=["test789"],
        name="Test Device 2",
        components={},
    )

    mqc.devs = [dev1, dev2]

    _LOGGER.fatal("TEST: connect")
    await mqc.connect(
        username=getenv("MQTT_USERNAME", ""),
        password=getenv("MQTT_PASSWORD", ""),
        host=getenv("MQTT_HOST", ""),
    )

    _LOGGER.fatal("TEST: check status")
    mqc.monitor_homeassistant_status()
    # mqc.migrate_entities = False
    # await mqc._publish_discovery_info()
    await asyncio.sleep(0.5)

    await mqc.publish(f"test/{select_id}", "opt 2")
    await mqc.publish(f"test/{select_id2}", "opt 3")
    await mqc.publish(f"test/{sense_id}", "yay!")
    for _ in range(100):
        await asyncio.sleep(0.5)
    # await mqc.migrate_discovery_info()

    await mqc.disconnect()
    await asyncio.sleep(0.1)

    assert False


@pytest.mark.asyncio
async def test_connect(caplog: pytest.LogCaptureFixture) -> None:
    """Test connect."""
    # pylint: disable=protected-access
    with patch("mqtt_entity.client.Client") as paho_client_class:  # patch paho Client
        # return a mock when you instantiate
        cmock = paho_client_class.return_value = MagicMock(spec=Client())
        mqc = mqtt_entity.MQTTClient(availability_topic="test/status")

        ok_seconds = time.time() + 0.3

        def is_connected() -> bool:
            """Return if the client is connected."""
            nonlocal ok_seconds
            if time.time() < ok_seconds:
                return False
            if ok_seconds:
                mqc._mqtt_on_connect(cmock, None, None, 0)  # type:ignore
                ok_seconds = 0
            return True

        cmock.is_connected.side_effect = is_connected

        # ensure client was enabled
        assert isinstance(mqc.client, Mock), "mock is not in place"
        assert cmock.on_connect == mqc._mqtt_on_connect  # pylint: disable=comparison-with-callable
        assert cmock.on_message == mqc._mqtt_on_message  # pylint: disable=comparison-with-callable
        assert mqc.connect_time == 0
        assert not cmock.is_connected()

        await mqc.connect(MQTTOptions(mqtt_username="me", mqtt_password="secret"))

        assert cmock.is_connected.called
        assert cmock.loop_start.call_count == 1
        assert cmock.connect_async.call_args_list == [
            call(host="core-mosquitto", port=1883)
        ]
        assert cmock.username_pw_set.call_args_list == [
            call(username="me", password="secret")
        ]
        assert cmock.will_set.call_args_list == [
            call("test/status", "offline", retain=True)
        ]

        assert not cmock.is_connected()

        mqc.monitor_homeassistant_status()

        assert "MQTT: Connected" not in caplog.text
        assert mqc.connect_time != 0

        await mqc.wait_connected()
        assert "MQTT: Connected" in caplog.text
        assert cmock.is_connected()

        await mqc.publish_discovery_info()
        assert "No devices" in caplog.text
        assert cmock.publish.call_count == 1

        mqc.devs = [
            mqtt_entity.MQTTDevice(
                identifiers=["test123"],
                name="Test Device",
                components={},
            )
        ]

        await mqc.publish_discovery_info()
        assert cmock.publish.call_count == 2
