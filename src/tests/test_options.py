"""Options."""

import os
from dataclasses import dataclass, field
from unittest import mock

import pytest

from mqtt_entity.options import MQTTOptions, safe_load

OPT = MQTTOptions()


def test_yaml_safe_load() -> None:
    """YAML options extra uses yamlrocks (PyYAML-compatible safe_load)."""
    assert safe_load is not None
    assert safe_load("mqtt_port: 123\n")["mqtt_port"] == 123


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
    with pytest.raises(ValueError), mock.patch.dict(os.environ, environ, clear=True):
        OPT.load_env()


@dataclass
class LoadEnvClass(MQTTOptions):
    """Test class."""

    lst: list = field(default_factory=list)
    num: int = 0


@dataclass
class OptionalListOptions(MQTTOptions):
    """Sunsynk-style optional sensor override configuration."""

    sensor_overrides: list[str] | None = None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('["battery_current.factor=0.1"]', ["battery_current.factor=0.1"]),
        (
            "battery_current.factor=0.1,day_pv_energy.factor=0.1",
            ["battery_current.factor=0.1", "day_pv_energy.factor=0.1"],
        ),
        ("[]", []),
        ("null", None),
    ],
)
def test_load_env_optional_list(value: str, expected: list[str] | None) -> None:
    """Optional list settings use the same JSON/CSV parsing as other lists."""
    opt = OptionalListOptions()
    with mock.patch.dict(os.environ, {"SENSOR_OVERRIDES": value}, clear=True):
        assert opt.load_env()
    assert opt.sensor_overrides == expected


def test_load_env_optional_list_unset() -> None:
    """An absent optional setting does not overwrite an existing value."""
    opt = OptionalListOptions(sensor_overrides=["battery_current.factor=0.1"])
    with mock.patch.dict(os.environ, {}, clear=True):
        assert not opt.load_env()
    assert opt.sensor_overrides == ["battery_current.factor=0.1"]
