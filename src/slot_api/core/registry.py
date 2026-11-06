"""
Registers all model modules against Base.metadata by importing them.
Call register() before any DDL or migration code runs.
"""

from slot_api.models import booking as _booking_module
from slot_api.models import slot as _slot_module


def register() -> None:
    """No-op callable that exists purely to make the import explicit."""
    _ = _slot_module
    _ = _booking_module
