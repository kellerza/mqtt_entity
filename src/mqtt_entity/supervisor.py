"""Home Assistant Supervisor helpers."""

import logging
import os
from typing import Any
from urllib.parse import urljoin

from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

MQFAIL = "Supervisor: Failed to get service details from the Supervisor"


def token(warn: bool = True, fail: bool = False) -> str | None:
    """Get the SUPERVISOR_TOKEN.

    Requires:
        hassio_api: true
        services: ["mqtt:need"]
    """
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token and warn:
        _LOGGER.error("Supervisor: No SUPERVISOR_TOKEN. Check addon config.")
        if not fail:
            return None
        raise ValueError("Supervisor: No SUPERVISOR_TOKEN. Check addon config.")
    return token


async def get(url: str) -> dict[str, Any] | None:
    """Get json data from the HA Supervisor."""
    url = urljoin("http://supervisor", url)
    head = {
        "Authorization": f"Bearer {token(fail=True)}",
        "content-type": "application/json",
    }
    async with ClientSession() as session:
        async with session.get(url, headers=head) as res:
            if res.status != 200:
                _LOGGER.warning("Supervisor: get %s, response %s", url, res.status)
                return None
            return await res.json()
