"""Utilities."""

from json import loads
from json.decoder import JSONDecodeError
from math import modf
from typing import Any

from attrs import Attribute

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


def required(_obj: Any, attr_obj: "Attribute[Any]", val: Any) -> None:
    """Ensure an attrs.field is present."""
    if val is None:
        raise TypeError(f"Argument '{getattr(attr_obj, 'name', '')}' missing")


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
