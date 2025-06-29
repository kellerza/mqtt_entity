"""Options."""

import os
from unittest import mock

import pytest

from mqtt_entity.options import MQTTOptions

OPT = MQTTOptions()


def test_load() -> None:
    """Tests."""
    assert OPT.mqtt_port == 1883
    OPT.mqtt_port = 15

    OPT.load_dict({"MQTT_PORT": "123"})
    assert OPT.mqtt_port == 123


def test_load_env() -> None:
    """Tests."""
    OPT.mqtt_port = 15
    assert OPT.mqtt_port != 30
    test_environ = {
        "MQTT_PORT": "123",
    }

    with mock.patch.dict(os.environ, test_environ, clear=True):
        res = OPT.load_env()

    assert OPT.mqtt_port == 123
    assert res


def test_load_env_bad() -> None:
    """Tests."""
    OPT.mqtt_port = 15
    assert OPT.mqtt_port != 30
    test_environ = {
        "MQTT_PORT": "30seconds",
    }

    with pytest.raises(ValueError):
        with mock.patch.dict(os.environ, test_environ, clear=True):
            OPT.load_env()
