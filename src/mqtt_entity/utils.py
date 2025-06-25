"""Utilities."""

from math import modf
from typing import Any

from attrs import Attribute


def required(_obj: Any, attr_obj: "Attribute[Any]", val: Any) -> None:
    """An attrs property validator, mostly used in child classes."""
    if val is None:
        raise TypeError(f"Argument '{getattr(attr_obj, 'name', '')} missing'")


BOOL_ON = "ON"
BOOL_OFF = "OFF"


def tostr(val: Any) -> str:
    """Convert a value to a string with maximum 3 decimal places."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return BOOL_ON if val else BOOL_OFF
    if not isinstance(val, float):
        return str(val)
    if modf(val)[0] == 0:
        return str(int(val))
    return f"{val:.3f}".rstrip("0")
