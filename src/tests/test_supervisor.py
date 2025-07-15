"""Test supervisor."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from mqtt_entity import supervisor
from mqtt_entity.options import MQTTOptions


def test_token() -> None:
    """Test token."""
    assert supervisor.token() is None

    environ = {"SUPERVISOR_TOKEN": "123"}
    with patch.dict(os.environ, environ, clear=True):
        assert supervisor.token() == "123"

    with pytest.raises(ValueError) as err:
        supervisor.token(fail=True)
    assert "Check addon" in str(err)


async def test_get_supervisor() -> None:
    """Test supervisor get."""
    environ = {"SUPERVISOR_TOKEN": "123", "MQTT_HOST": "envh"}

    with (
        patch("aiohttp.ClientSession.get") as mock_get,
        patch.dict(os.environ, environ, clear=True),
        patch("logging.basicConfig"),
    ):
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={
                "data": {"username": "me", "password": "x", "host": "local", "port": 1}
            }
        )
        mock_get.return_value.__aenter__.return_value.status = 200

        res = await supervisor.get("/abc")
        assert res == {
            "data": {"username": "me", "password": "x", "host": "local", "port": 1}
        }

        opt = MQTTOptions()
        await opt.init_addon()

        assert opt.mqtt_username == "me"
        assert opt.mqtt_password == "x"
        assert opt.mqtt_host == "local"
        assert opt.mqtt_port == 1

        # Return code
        res = await supervisor.get("/abc")
        assert res is not None
        mock_get.return_value.__aenter__.return_value.status = 401
        res = await supervisor.get("/abc")
        assert await supervisor.get("/abc") is None
