"""Test inheritance."""

from dataclasses import dataclass

import pytest


@dataclass
class Base:
    """Base class."""

    a: int = 0

    def __post_init__(self) -> None:
        """Post init."""
        if self.a < 0:
            raise ValueError("a must be non-negative")


@dataclass
class BaseB(Base):
    """Inherit A."""

    b: int = 0

    def __post_init__(self) -> None:
        """Post init."""
        super().__post_init__()  # Needs an explicit call to the parent __post_init__!
        if self.b < 0:
            raise ValueError("b must be non-negative")


def test_inheritance() -> None:
    """Test inheritance."""
    with pytest.raises(ValueError):
        Base(a=-1)
    Base(a=1)

    with pytest.raises(ValueError):
        BaseB(a=0, b=-1)
    with pytest.raises(ValueError):
        BaseB(a=-1)
    BaseB(a=1, b=2)
