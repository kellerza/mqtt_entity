"""Home Assistant Supervisor helpers."""

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urljoin

from aiohttp import ClientSession

_LOG = logging.getLogger(__name__)

MQFAIL = "Supervisor: Failed to get service details from the Supervisor"


def token(warn: bool = True, fail: bool = False) -> str | None:
    """Get the SUPERVISOR_TOKEN.

    Requires:
        hassio_api: true
        services: ["mqtt:need"]
    """
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token and warn:
        _LOG.error("Supervisor: No SUPERVISOR_TOKEN. Check addon config.")
        if not fail:
            return None
        raise ValueError("Supervisor: No SUPERVISOR_TOKEN. Check addon config.")
    return token


async def get(url: str, log_only: bool = True) -> dict[str, Any] | None:
    """Get json data from the HA Supervisor."""
    url = urljoin("http://supervisor", url)
    head = {
        "Authorization": f"Bearer {token(fail=True)}",
        "content-type": "application/json",
    }
    try:
        async with asyncio.timeout(10):
            async with ClientSession() as session:
                async with session.get(url, headers=head) as res:
                    if res.status == 200:
                        return await res.json()
                    _LOG.warning("Supervisor: get %s, status %s", url, res.status)
    except TimeoutError:
        msg = f"Supervisor: Timeout getting {url}"
        _LOG.warning(msg)
        if not log_only:
            raise TimeoutError(msg) from None
    except Exception as err:
        msg = f"Supervisor: Error getting {url}, {err.__class__.__name__}: {err}"
        _LOG.error(msg)
        if not log_only:
            raise
    return None
