"""Utilities."""

import logging
from json import loads
from json.decoder import JSONDecodeError
from math import modf
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import attrs

BOOL_ON = "ON"
BOOL_OFF = "OFF"


def load_json(msg: str | None) -> dict[str, Any] | str:
    """Load a JSON string into a dictionary."""
    if not msg:
        return {}
    try:
        res = loads(msg)
        if isinstance(res, dict):
            return res
    except JSONDecodeError:
        pass
    return str(msg)


def logging_color(*, debug: bool = False, force: bool = True) -> None:
    """Enable color logging."""
    try:
        import colorlog  # noqa: PLC0415

        handler = colorlog.StreamHandler()
        handler.setFormatter(
            colorlog.ColoredFormatter(
                "[%(asctime)s] %(log_color)s%(levelname)-7s%(reset)s %(message)s",
                datefmt="%H:%M:%S",
                reset=False,
            )
        )
        logging.basicConfig(
            level=logging.DEBUG if debug else logging.INFO,
            handlers=[handler],
            force=force,
        )
    except ModuleNotFoundError:
        logging.basicConfig(
            format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
            level=logging.DEBUG if debug else logging.INFO,
            force=force,
        )


def required(_obj: Any, attr_obj: "attrs.Attribute[Any]", val: Any) -> None:
    """Ensure an attrs.field is present."""
    if val is None:
        raise TypeError(f"Argument '{getattr(attr_obj, 'name', '')}' missing")


def slug(name: str) -> str:
    """Create a slug."""
    return name.lower().replace(" ", "_").replace("-", "_")


def tostr(val: Any) -> str:
    """Convert a value to a string with maximum 3 decimal places."""
    if isinstance(val, str):
        return val
    if val is None:
        return ""
    if isinstance(val, bool):
        return BOOL_ON if val else BOOL_OFF
    if not isinstance(val, float):
        return str(val)
    if modf(val)[0] == 0:
        return str(int(val))
    return f"{val:.3f}".rstrip("0")
