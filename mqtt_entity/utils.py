"""Utilities."""
from typing import Any


def required(_obj: Any, attr_obj: Any, val: Any) -> None:
    """An attrs property validator, mostly used in child classes."""
    assert (
        val is not None
    ), f"Attribute '{getattr(attr_obj, 'name', '')}' must be defined (not None)"
