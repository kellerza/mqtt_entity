"""Test MQTT class."""

import asyncio
import importlib.metadata
import json
import logging
import time
from os import getenv
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest
from paho.mqtt.client import Client
from paho.mqtt.enums import CallbackAPIVersion

from mqtt_entity import MQTTClient, MQTTDevice, MQTTSelectEntity, MQTTSensorEntity
from mqtt_entity.client import HA_STATUS_TOPIC, MQTTMatcher2
from mqtt_entity.options import MQTTOptions

_LOG = logging.getLogger(__name__)


def _mock_paho_client() -> MagicMock:
    """Return a mock AsyncMQTTClient with async transport methods."""
    cmock = MagicMock(spec=Client(callback_api_version=CallbackAPIVersion.VERSION2))
    cmock.async_start = AsyncMock()
    cmock.async_connect = AsyncMock()
    cmock.async_stop = AsyncMock()
    cmock.async_publish = AsyncMock()
    cmock.async_subscribe = AsyncMock()
    cmock.async_unsubscribe = AsyncMock()
    cmock.disconnect = MagicMock()
    return cmock


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

    async def select_select(msg: str, _: str) -> None:
        _LOG.error("onchange start: %s", msg)
        await sense_ent.send_state(mqc, f"select 1={msg} --> 2")
        await select_ent2.send_state(mqc, msg)

    async def select_select2(msg: str, _: str) -> None:
        _LOG.error("onchange: %s", msg)
        await sense_ent.send_state(mqc, f"select 2={msg} --> 1")
        await select_ent.send_state(mqc, msg)

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

    await mqc.monitor_homeassistant_status()
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
    with patch("mqtt_entity.client.AClient") as paho_client_class:  # patch paho Client
        # return a mock when you instantiate
        cmock = paho_client_class.return_value = _mock_paho_client()
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
        assert cmock.async_start.call_count == 1
        assert cmock.async_connect.call_args_list == [
            call(host="core-mosquitto", port=1883)
        ]
        assert cmock.username_pw_set.call_args_list == [
            call(username="me", password="secret")
        ]
        assert cmock.will_set.call_args_list == [
            call("test/status", "offline", retain=True)
        ]

        assert not cmock.is_connected()

        await mqc.monitor_homeassistant_status()

        assert "MQTT: Connected" in caplog.text
        assert mqc.connect_time != 0
        assert cmock.async_subscribe.call_args_list == [call(HA_STATUS_TOPIC)]

        await mqc.wait_connected()
        assert cmock.is_connected()

        await mqc.publish_discovery_info()
        assert "No devices" in caplog.text
        assert cmock.publish.call_count == 1
        assert cmock.publish.call_args_list == [
            call("test/status", "online", retain=True),
        ]

        mqc.devs = [
            MQTTDevice(
                identifiers=[("serial", "test123")],
                name="Test Device",
                components={},
            )
        ]

        await mqc.publish_discovery_info()
        assert cmock.async_publish.call_count == 2

        pkg_version = importlib.metadata.version("mqtt-entity")
        disco_info = json.dumps(
            {
                "dev": {"ids": [("serial", "test123")], "name": "Test Device"},
                "o": {"name": "mqtt-entity", "sw": pkg_version},
                "avty": {"topic": "test/status"},
                "cmps": {},
            },
            indent=None,
            separators=(",", ":"),
        )

        assert cmock.async_publish.call_args_list == [
            call("homeassistant/device/test123/config", disco_info, 0, False),
            call("test/status", "online", 1, True),
        ]


def _discovery_device_config_payloads(cmock: MagicMock) -> list[dict[str, object]]:
    """Decode JSON discovery configs published under homeassistant/device/.../config."""
    out: list[dict[str, object]] = []
    for args, kwargs in cmock.async_publish.call_args_list:
        topic = args[0] if args else kwargs.get("topic")
        payload = args[1] if len(args) > 1 else kwargs.get("payload")
        if (
            not isinstance(topic, str)
            or not topic.startswith("homeassistant/device/")
            or not topic.endswith("/config")
            or not isinstance(payload, str)
            or not payload.startswith("{")
        ):
            continue
        out.append(json.loads(payload))
    return out


@pytest.mark.asyncio
async def test_publish_discovery_merges_client_availability_topic() -> None:
    """Client ``availability_topic`` is merged into each device's discovery ``avty``."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
        ok_seconds = time.time() + 0.3

        def is_connected() -> bool:
            nonlocal ok_seconds
            if time.time() < ok_seconds:
                return False
            if ok_seconds:
                mqc._mqtt_on_connect(cmock, None, None, 0)  # type:ignore[arg-type]
                ok_seconds = 0
            return True

        cmock.is_connected.side_effect = is_connected

        mqc = MQTTClient(
            availability_topic="addon/client_status",
            clean_entities=0,
        )
        await mqc.connect(MQTTOptions(mqtt_username="me", mqtt_password="secret"))
        await mqc.wait_connected()

        mqc.devs = [
            MQTTDevice(
                identifiers=[("serial", "merge-test")],
                name="Merge",
                components={},
                availability_topics=["inverter/present"],
            ),
        ]
        await mqc.publish_discovery_info()

        configs = _discovery_device_config_payloads(cmock)
        assert len(configs) == 1
        assert configs[0]["avty"] == [
            {"topic": "inverter/present"},
            {"topic": "addon/client_status"},
        ]
        assert "avty_mode" not in configs[0]


@pytest.mark.asyncio
async def test_publish_discovery_availability_mode_all() -> None:
    """``availability_mode`` ``all`` is emitted when set (HA requires all topics online)."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
        ok_seconds = time.time() + 0.3

        def is_connected() -> bool:
            nonlocal ok_seconds
            if time.time() < ok_seconds:
                return False
            if ok_seconds:
                mqc._mqtt_on_connect(cmock, None, None, 0)  # type:ignore[arg-type]
                ok_seconds = 0
            return True

        cmock.is_connected.side_effect = is_connected

        mqc = MQTTClient(
            availability_topic="addon/client_status",
            clean_entities=0,
        )
        await mqc.connect(MQTTOptions(mqtt_username="me", mqtt_password="secret"))
        await mqc.wait_connected()

        mqc.devs = [
            MQTTDevice(
                identifiers=[("serial", "merge-test-all")],
                name="Merge all",
                components={},
                availability_topics=["inverter/present"],
                availability_mode="all",
            ),
        ]
        await mqc.publish_discovery_info()

        configs = _discovery_device_config_payloads(cmock)
        assert len(configs) == 1
        assert configs[0]["avty_mode"] == "all"


@pytest.mark.asyncio
async def test_publish_discovery_client_availability_topic_only() -> None:
    """With no per-device topics, discovery ``avty`` is only the client's availability topic."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
        ok_seconds = time.time() + 0.3

        def is_connected() -> bool:
            nonlocal ok_seconds
            if time.time() < ok_seconds:
                return False
            if ok_seconds:
                mqc._mqtt_on_connect(cmock, None, None, 0)  # type:ignore[arg-type]
                ok_seconds = 0
            return True

        cmock.is_connected.side_effect = is_connected

        mqc = MQTTClient(
            availability_topic="addon/only",
            clean_entities=0,
        )
        await mqc.connect(MQTTOptions(mqtt_username="me", mqtt_password="secret"))
        await mqc.wait_connected()

        mqc.devs = [
            MQTTDevice(
                identifiers=[("serial", "client-only")],
                name="Client only",
                components={},
            ),
        ]
        await mqc.publish_discovery_info()

        configs = _discovery_device_config_payloads(cmock)
        assert len(configs) == 1
        assert configs[0]["avty"] == {"topic": "addon/only"}
        assert "avty_mode" not in configs[0]


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
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
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
async def test_connect_reconnect_disconnects_previous_session() -> None:
    """Reconnect tears down the previous socket before opening a new connection."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
        mqc = MQTTClient()

        cmock.is_connected.return_value = False
        await mqc.connect(username="u", password="p", host="localhost")

        cmock.is_connected.return_value = True
        await mqc.connect(username="u", password="p", host="localhost")

        cmock.disconnect.assert_called_once()


def test_on_connect_snapshots_keys_for_resubscribe() -> None:
    """Test that _mqtt_on_connect is safe against concurrent topic changes.

    The keys() generator traverses MQTTMatcher2's internal tree. If
    topic_subscribe()/topic_unsubscribe() runs concurrently (from another
    coroutine), mutating the tree mid-iteration would crash with
    RuntimeError. Using list() to snapshot prevents this.
    """
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
        mqc = MQTTClient()
        mqc._loop = asyncio.new_event_loop()

        # Pre-populate subscriptions
        mqc._on_message_filtered["topic/a"] = lambda p: None
        mqc._on_message_filtered["topic/b"] = lambda p: None

        subscribed: list[str] = []

        async def track_and_mutate(topic: str, qos: int = 0) -> None:
            """Track subscribes and mutate the tree mid-iteration."""
            subscribed.append(topic)
            # Simulate concurrent topic_subscribe from another coroutine —
            # this would crash a bare keys() generator
            if topic == "topic/a":
                mqc._on_message_filtered["topic/c"] = lambda p: None

        cmock.async_subscribe.side_effect = track_and_mutate

        # Should NOT raise RuntimeError: dictionary changed size during iteration
        mqc._mqtt_on_connect(cmock, None, None, 0)  # type: ignore[arg-type]
        mqc._loop.run_until_complete(asyncio.sleep(0))

        assert "topic/a" in subscribed
        assert "topic/b" in subscribed


@pytest.mark.asyncio
async def test_mqtt_on_message_runs_async_callback() -> None:
    """Incoming MQTT messages are dispatched to async topic callbacks."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        paho_client_class.return_value = _mock_paho_client()
        mqc = MQTTClient()
        mqc._loop = asyncio.get_running_loop()
        seen: list[tuple[str, str]] = []

        async def on_cmd(payload: str, topic: str) -> None:
            seen.append((payload, topic))

        mqc._on_message_filtered["cmd"] = on_cmd
        msg = MagicMock()
        msg.topic = "cmd"
        msg.payload = b"ON"
        mqc._mqtt_on_message(mqc.client, None, msg)
        await asyncio.sleep(0)
        assert seen == [("ON", "cmd")]


@pytest.mark.asyncio
async def test_topic_subscribe_skips_broker_duplicate() -> None:
    """topic_subscribe + concurrent _resubscribe_topics SUBSCRIBEs once."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
        mqc = MQTTClient()
        cmock.is_connected.return_value = True
        mqc.connect_time = 1

        topic = "homeassistant/status"
        gate = asyncio.Event()
        entered = asyncio.Event()

        async def slow_subscribe(t: str, qos: int = 0) -> None:
            entered.set()
            await gate.wait()

        cmock.async_subscribe.side_effect = slow_subscribe

        async def noop(_p: str, _t: str) -> None:
            return

        sub_task = asyncio.create_task(mqc.topic_subscribe(topic, noop))
        await entered.wait()
        # Concurrent reconnect resubscribe while first SUBSCRIBE is in flight
        resub_task = asyncio.create_task(mqc._resubscribe_topics())
        await asyncio.sleep(0)
        gate.set()
        await asyncio.gather(sub_task, resub_task)

        assert cmock.async_subscribe.await_count == 1
        assert cmock.async_subscribe.await_args_list == [call(topic)]
        assert topic in mqc._broker_topics


@pytest.mark.asyncio
async def test_ha_online_dedupes_concurrent_status(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Concurrent retained homeassistant/status online only publishes discovery once."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
        mqc = MQTTClient(availability_topic="test/status", clean_entities=0)
        mqc.devs.append(MQTTDevice(identifiers=["inv1"], name="ss", components={}))
        cmock.is_connected.return_value = True
        mqc.connect_time = 1

        await mqc.monitor_homeassistant_status()
        online = mqc._on_message_filtered[HA_STATUS_TOPIC]

        await asyncio.gather(online("online", ""), online("online", ""))

        assert caplog.text.count("MQTT: Home Assistant online") == 1
        assert cmock.async_publish.await_count >= 1
        # device discovery + availability
        disco_publishes = [
            c
            for c in cmock.async_publish.await_args_list
            if c.args and str(c.args[0]).endswith("/config")
        ]
        assert len(disco_publishes) == 1
        mqc._cancel_discovery_loop()


@pytest.mark.asyncio
async def test_publish_discovery_skips_unchanged_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """HA online + immediate publish_discovery_info must not republish same config."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:
        cmock = paho_client_class.return_value = _mock_paho_client()
        mqc = MQTTClient(availability_topic="test/status", clean_entities=0)
        mqc.devs.append(MQTTDevice(identifiers=["inv1"], name="ss", components={}))
        cmock.is_connected.return_value = True
        mqc.connect_time = 1

        await mqc.monitor_homeassistant_status()
        await mqc._on_message_filtered[HA_STATUS_TOPIC]("online", "")
        await mqc.publish_discovery_info()

        disco_publishes = [
            c
            for c in cmock.async_publish.await_args_list
            if c.args and str(c.args[0]).endswith("/config")
        ]
        assert len(disco_publishes) == 1
        assert "Skip unchanged discovery" in caplog.text

        await mqc._publish_device_config()
        disco_publishes = [
            c
            for c in cmock.async_publish.await_args_list
            if c.args and str(c.args[0]).endswith("/config")
        ]
        assert len(disco_publishes) == 1

        # HA offline clears cache; next online must publish again
        await mqc._on_message_filtered[HA_STATUS_TOPIC]("offline", "")
        await mqc._on_message_filtered[HA_STATUS_TOPIC]("online", "")
        disco_publishes = [
            c
            for c in cmock.async_publish.await_args_list
            if c.args and str(c.args[0]).endswith("/config")
        ]
        assert len(disco_publishes) == 2
        mqc._cancel_discovery_loop()


@pytest.mark.asyncio
async def test_ha_status_topic(caplog: pytest.LogCaptureFixture) -> None:
    """Test connect."""
    with patch("mqtt_entity.client.AClient") as paho_client_class:  # patch paho Client
        # return a mock when you instantiate
        cmock = paho_client_class.return_value = _mock_paho_client()
        mqc = MQTTClient(availability_topic="test/status")

        cmock.is_connected.return_value = True
        mqc.connect_time = 1

        assert HA_STATUS_TOPIC == "homeassistant/status"

        assert HA_STATUS_TOPIC not in mqc._on_message_filtered
        await mqc.monitor_homeassistant_status()
        assert HA_STATUS_TOPIC in mqc._on_message_filtered

        assert "MQTT: Home Assistant online" not in caplog.text
        await mqc._on_message_filtered[HA_STATUS_TOPIC]("online", "")
        assert "MQTT: Home Assistant online" in caplog.text
        await asyncio.sleep(0.1)
        assert "Timeout waiting for Home Assistant" not in caplog.text
        mqc._cancel_discovery_loop()
