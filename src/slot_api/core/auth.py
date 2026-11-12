"""API-key authentication for every endpoint.

Clients must send the expected key in the ``X-API-Key`` header.  The key is
read from configuration (``API_KEY``).  Missing or incorrect keys get a 401.
"""

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from slot_api.core.config import settings


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="slot not found"
    )


async def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    """Dependency applied globally; raises 401 when the key is absent/wrong."""
    if x_api_key is None or not secrets.compare_digest(x_api_key, settings.api_key):
        raise _unauthorized()
