"""Options."""

import os
from unittest import mock

import attrs
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
    environ = {"MQTT_PORT": "123"}
    with mock.patch.dict(os.environ, environ, clear=True):
        res = OPT.load_env()
    assert OPT.mqtt_port == 123
    assert res

    for environ in (
        {"LST": '["1", "2", "3"]', "NUM": "5"},
        {"LST": "1,2,3", "NUM": "5"},
    ):
        opt = LoadEnvClass()
        with mock.patch.dict(os.environ, environ, clear=True):
            opt.load_env()
        assert opt.lst == ["1", "2", "3"]
        assert opt.num == 5


def test_load_env_bad() -> None:
    """Tests."""
    environ = {"MQTT_PORT": "30seconds"}
    with pytest.raises(ValueError):
        with mock.patch.dict(os.environ, environ, clear=True):
            OPT.load_env()


@attrs.define()
class LoadEnvClass(MQTTOptions):
    """Test class."""

    lst: list = attrs.field(factory=list)
    num: int = 0
