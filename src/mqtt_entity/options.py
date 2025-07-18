"""Example Options for HASS addon. Extend Options."""

import logging
import os
import typing as t
from json import load, loads
from json.decoder import JSONDecodeError
from pathlib import Path

import attrs
from cattrs import Converter, transform_error
from cattrs.gen import make_dict_structure_fn
from yaml import safe_load

from . import supervisor
from .utils import logging_color

_LOGGER = logging.getLogger(__name__)


@attrs.define()
class AddonOptions:
    """HASS Addon Options."""

    def load_dict(
        self, value: dict, log_lvl: int = logging.DEBUG, log_msg: str = ""
    ) -> None:
        """Structure and copy result to self."""
        try:
            _LOGGER.log(log_lvl, "%s: %s", log_msg or "Loading config", value)
            val = CONVERTER.structure(value, self.__class__)
        except Exception as exc:
            msg = "Error loading config: " + "\n".join(transform_error(exc))
            _LOGGER.error(msg)
            raise ValueError(msg) from None
        for key in value:
            setattr(self, key.lower(), getattr(val, key.lower()))

    def load_env(self) -> bool:
        """Get attrs fields from the environment."""
        res = {}
        atts: tuple[attrs.Attribute, ...] = attrs.fields(
            attrs.resolve_types(self.__class__)
        )
        for att in atts:
            val = os.getenv(att.name.upper())
            if not val:
                continue
            name = att.name.lower()
            if att.type is list or t.get_origin(att.type) is list:
                try:
                    res[name] = loads(val)
                except JSONDecodeError:
                    res[name] = val.split(",")
                continue
            res[name] = val
        if res:
            self.load_dict(
                res,
                logging.INFO,
                "Loading config from environment variables",
            )
        return bool(res)

    async def init_addon(self) -> None:
        """Initialize options from environment variables and config files & setup the logger."""
        logging_color()

        env_ok = self.load_env()

        cfg_names = (
            "/data/options.json",  # HA OS config location
            "/data/options.yaml",  # Recommended for standalone deployment
            ".data/options.yaml",  # Pytest
        )
        cfg_files = [f for f in (Path(s) for s in cfg_names) if f.exists()]
        if not cfg_files and not env_ok:
            _LOGGER.error("No config file or environment variables found.")
            os._exit(1)

        for fpath in cfg_files:
            _LOGGER.info("Loading config: %s", fpath)
            with fpath.open("r", encoding="utf-8") as fptr:
                opt = load(fptr) if fpath.suffix == ".json" else safe_load(fptr)
                self.load_dict(opt)

        if getattr(self, "debug", 0):
            logging_color(debug=True)


MQFAIL = "MQTT: Failed to get MQTT service details from the Supervisor"


@attrs.define()
class MQTTOptions(AddonOptions):
    """MQTT Options for HASS Addon."""

    mqtt_host: str = "core-mosquitto"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""

    async def init_addon(self) -> None:
        """Initialize MQTT options from environment variables and config files."""
        await super().init_addon()

        # Don't warn if MQTT password is set
        if not supervisor.token(warn=False):
            _LOGGER.log(
                logging.DEBUG if self.mqtt_password else logging.WARNING, MQFAIL
            )
            return

        data = await supervisor.get("/services/mqtt")
        if not data:
            return

        try:
            data = t.cast(dict[str, t.Any], data["data"])
            self.mqtt_host = data["host"]
            self.mqtt_port = data["port"]
            self.mqtt_username = data["username"]
            self.mqtt_password = data["password"]
        except KeyError as err:
            _LOGGER.warning("%s: %s %s", MQFAIL, err, data)


CONVERTER = Converter(forbid_extra_keys=True)


def structure_ensure_lowercase_keys(cls: type) -> t.Callable[[t.Any, t.Any], t.Any]:
    """Convert any uppercase keys to lowercase."""
    struct = make_dict_structure_fn(cls, CONVERTER)  # type: ignore[var-annotated]

    def structure(d: dict[str, t.Any], cl: t.Any) -> t.Any:
        lower = [k for k in d if k.lower() != k]
        for k in lower:
            if k.lower() in d:
                _LOGGER.warning("Key %s already exists in lowercase", k.lower())
            d[k.lower()] = d.pop(k)
        return struct(d, cl)

    return structure


CONVERTER.register_structure_hook_factory(attrs.has, structure_ensure_lowercase_keys)
