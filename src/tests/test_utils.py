"""Test utils."""

import pytest

from mqtt_entity.utils import load_json, required, slug, tostr


def test_load_dict() -> None:
    """Test load dict."""
    assert {} == load_json("")
    assert {} == load_json(None)
    assert {"a": 1} == load_json('{"a":1}')
    assert '{"a":"1}' == load_json('{"a":"1}')


def test_required() -> None:
    """Test required."""
    with pytest.raises(TypeError):
        required(None, None, None)  # type:ignore[arg-type]


def test_slug() -> None:
    """Test slug."""
    assert slug("Test Name") == "test_name"
    assert slug("Another-Test") == "another_test"


def test_tostr() -> None:
    """Test to string."""
    assert tostr(1) == "1"
    assert tostr("1") == "1"
    assert tostr(1.1) == "1.1"
    assert tostr(True) == "ON"
    assert tostr(False) == "OFF"
