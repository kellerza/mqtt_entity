"""Helpers."""


def hass_default_rw_icon(*, unit: str) -> str:
    """Get the HASS default icon from the unit."""
    return {
        "W": "mdi:flash",
        "V": "mdi:sine-wave",
        "A": "mdi:current-ac",
        "%": "mdi:battery-lock",
    }.get(unit, "")


def hass_device_class(*, unit: str) -> str:
    """Get the HASS device_class from the unit."""
    return {
        "W": "power",
        "kW": "power",
        "kVA": "apparent_power",
        "VA": "apparent_power",
        "V": "voltage",
        "kWh": "energy",
        "kVAh": "",  # Not energy
        "A": "current",
        "°C": "temperature",
        "%": "battery",
    }.get(unit, "")
