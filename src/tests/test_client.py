"""Test MQTT class."""

import asyncio
import logging
import time
from os import getenv
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from paho.mqtt.client import Client
from paho.mqtt.enums import CallbackAPIVersion

from mqtt_entity import MQTTClient, MQTTDevice, MQTTSelectEntity, MQTTSensorEntity
from mqtt_entity.client import HA_STATUS_TOPIC, MQTTMatcher2
from mqtt_entity.options import MQTTOptions

_LOG = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.mqtt
async def test_mqtt_server() -> None:
    """Test MQTT."""
    select_id = "t_select_1"
    select_id2 = "t_select_2"
    sense_id = "t_sense_1"

    select_ent = MQTTSelectEntity(
        name="Test select entity",
        unique_id=select_id,
        command_topic=f"test/{select_id}_set",
        options=["opt 1", "opt 2", "opt 3", "opt 4", "only 1"],
        state_topic=f"test/{select_id}",
    )
    select_ent2 = MQTTSelectEntity(
        name="Test select entity 3",
        unique_id=select_id2,
        command_topic=f"test/{select_id2}_set",
        options=["opt 1", "opt 2", "opt 3", "opt 4", "only 2"],
        state_topic=f"test/{select_id2}",
    )
    sense_ent = MQTTSensorEntity(
        name="Test sensor entity",
        unique_id=sense_id,
        state_topic=f"test/{sense_id}",
    )

    mqc = MQTTClient(
        availability_topic="test/available",
        origin_name="Test Origin",
    )
    loop = asyncio.get_running_loop()
    tasks = list[asyncio.Task]()

    async def select_select(msg: str, _: str) -> None:
        _LOG.error("onchange start: %s", msg)
        await sense_ent.send_state(mqc, f"select 1={msg} --> 2")
        await select_ent2.send_state(mqc, msg)

    def select_select2(msg: str, _: str) -> None:
        _LOG.error("onchange no async: %s", msg)
        nonlocal tasks
        tasks = [
            loop.create_task(sense_ent.send_state(mqc, f"select 2={msg} --> 1")),
            loop.create_task(select_ent.send_state(mqc, msg)),
        ]

    select_ent.on_command = select_select
    select_ent2.on_command = select_select2
    mqc.devs = [
        MQTTDevice(
            identifiers=["test456"],
            name="Test Device",
            components={e.unique_id: e for e in [select_ent, select_ent2, sense_ent]},
        ),
        MQTTDevice(
            identifiers=["test789"],
            name="Test Device 2",
            components={},
        ),
    ]

    await mqc.connect(
        username=getenv("MQTT_USERNAME", ""),
        password=getenv("MQTT_PASSWORD", ""),
        host=getenv("MQTT_HOST", ""),
    )

    mqc.monitor_homeassistant_status()
    await asyncio.sleep(0.5)

    await select_ent.send_state(mqc, "opt2")
    await select_ent2.send_state(mqc, "opt 3")
    await sense_ent.send_state(mqc, "yay!")
    for _ in range(100):
        await asyncio.sleep(0.5)
    await mqc.disconnect()
    await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_connect(caplog: pytest.LogCaptureFixture) -> None:
    """Test connect."""
    with patch("mqtt_entity.client.Client") as paho_client_class:  # patch paho Client
        # return a mock when you instantiate
        cmock = paho_client_class.return_value = MagicMock(
            spec=Client(callback_api_version=CallbackAPIVersion.VERSION2)
        )
        mqc = MQTTClient(availability_topic="test/status")

        ok_seconds = time.time() + 0.3

        def is_connected() -> bool:
            """Return if the client is connected."""
            nonlocal ok_seconds
            if time.time() < ok_seconds:
                return False
            if ok_seconds:
                mqc._mqtt_on_connect(cmock, None, None, 0)  # type:ignore[arg-type]
                ok_seconds = 0
            return True

        cmock.is_connected.side_effect = is_connected

        # ensure client was enabled
        assert isinstance(mqc.client, Mock), "mock is not in place"
        assert cmock.on_connect == mqc._mqtt_on_connect
        assert cmock.on_message == mqc._mqtt_on_message
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
            MQTTDevice(
                identifiers=["test123"],
                name="Test Device",
                components={},
            )
        ]

        await mqc.publish_discovery_info()
        assert cmock.publish.call_count == 2


def test_mqttmatcher() -> None:
    """Test MQTTMatcher."""
    m = MQTTMatcher2()
    m["test/123"] = "a"
    m["test/456"] = "b"
    m["/test/789"] = "b"

    assert list(m.iter_match("test/123")) == ["a"]
    assert list(m.iter_match("/test/123")) == []

    assert list(m.keys()) == ["test/123", "test/456", "/test/789"]

    assert "/test/789" in m
    assert "test/789" not in m


@pytest.mark.asyncio
async def test_reconnect_after_broker_restart(caplog: pytest.LogCaptureFixture) -> None:
    """Test that wait_connected() survives a broker restart.

    Simulates: initial connect succeeds, broker goes down (connect_time
    deadline expires), then paho auto-reconnect restores the connection.
    wait_connected() should grant a fresh window and succeed.
    """
    with patch("mqtt_entity.client.Client") as paho_client_class:
        cmock = paho_client_class.return_value = MagicMock(
            spec=Client(callback_api_version=CallbackAPIVersion.VERSION2)
        )
        mqc = MQTTClient(availability_topic="test/status")

        # Phase 1: initial connect succeeds immediately
        cmock.is_connected.return_value = True
        await mqc.connect(username="u", password="p", host="localhost")
        mqc._mqtt_on_connect(cmock, None, None, 0)  # type: ignore[arg-type]
        await mqc.wait_connected()  # should pass

        # Phase 2: broker goes down — simulate stale connect_time
        cmock.is_connected.return_value = False
        mqc.connect_time = time.time() - 100  # deadline long expired

        # Phase 3: paho auto-reconnect will restore in 0.3s
        reconnect_at = time.time() + 0.3

        def delayed_reconnect() -> bool:
            if time.time() >= reconnect_at:
                return True
            return False

        cmock.is_connected.side_effect = delayed_reconnect

        # wait_connected() should detect stale deadline, grant fresh window,
        # and wait for auto-reconnect instead of failing immediately
        await mqc.wait_connected()
        assert "Connection lost. Waiting for reconnect" in caplog.text


@pytest.mark.asyncio
async def test_on_connect_resets_connect_time() -> None:
    """Test that _mqtt_on_connect resets connect_time on reconnect."""
    with patch("mqtt_entity.client.Client") as paho_client_class:
        cmock = paho_client_class.return_value = MagicMock(
            spec=Client(callback_api_version=CallbackAPIVersion.VERSION2)
        )
        mqc = MQTTClient(availability_topic="test/status")

        # Simulate expired connect_time (as after hours of uptime)
        mqc.connect_time = time.time() - 3600

        mqc._mqtt_on_connect(cmock, None, None, 0)  # type: ignore[arg-type]

        # connect_time should be refreshed to ~now + 5
        assert mqc.connect_time > time.time()
        assert mqc.connect_time <= time.time() + 6


def test_on_connect_snapshots_keys_for_resubscribe() -> None:
    """Test that _mqtt_on_connect is safe against concurrent topic changes.

    The keys() generator traverses MQTTMatcher2's internal tree. If
    topic_subscribe()/topic_unsubscribe() runs concurrently (from the
    asyncio thread), mutating the tree mid-iteration would crash with
    RuntimeError. Using list() to snapshot prevents this.
    """
    with patch("mqtt_entity.client.Client") as paho_client_class:
        cmock = paho_client_class.return_value = MagicMock(
            spec=Client(callback_api_version=CallbackAPIVersion.VERSION2)
        )
        mqc = MQTTClient()

        # Pre-populate subscriptions
        mqc._on_message_filtered["topic/a"] = lambda p: None
        mqc._on_message_filtered["topic/b"] = lambda p: None

        subscribed: list[str] = []
        original_subscribe = cmock.subscribe

        def track_and_mutate(topic: str) -> None:
            """Track subscribes and mutate the tree mid-iteration."""
            subscribed.append(topic)
            # Simulate concurrent topic_subscribe from asyncio thread —
            # this would crash a bare keys() generator
            if topic == "topic/a":
                mqc._on_message_filtered["topic/c"] = lambda p: None

        cmock.subscribe.side_effect = track_and_mutate

        # Should NOT raise RuntimeError: dictionary changed size during iteration
        mqc._mqtt_on_connect(cmock, None, None, 0)  # type: ignore[arg-type]

        assert "topic/a" in subscribed
        assert "topic/b" in subscribed


@pytest.mark.asyncio
async def test_ha_status_topic(caplog: pytest.LogCaptureFixture) -> None:
    """Test connect."""
    with patch("mqtt_entity.client.Client") as paho_client_class:  # patch paho Client
        # return a mock when you instantiate
        cmock = paho_client_class.return_value = MagicMock(
            spec=Client(callback_api_version=CallbackAPIVersion.VERSION2)
        )
        mqc = MQTTClient(availability_topic="test/status")

        cmock.is_connected.return_value = True
        mqc.connect_time = 1

        assert HA_STATUS_TOPIC == "homeassistant/status"

        assert HA_STATUS_TOPIC not in mqc._on_message_filtered
        mqc.monitor_homeassistant_status()
        assert HA_STATUS_TOPIC in mqc._on_message_filtered

        assert "MQTT: Home Assistant online" not in caplog.text
        await mqc._on_message_filtered[HA_STATUS_TOPIC]("online", "")
        assert "MQTT: Home Assistant online" in caplog.text
        await asyncio.sleep(0.1)
        assert "Timeout waiting for Home Assistant" not in caplog.text
