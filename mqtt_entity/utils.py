"""Utilities."""
from typing import Any


def required(_obj: Any, attr_obj: Any, val: Any) -> None:
    """An attrs property validator, mostly used in child classes."""
    if val is None:
        raise TypeError(f"Argument '{getattr(attr_obj, 'name', '')} missing'")
