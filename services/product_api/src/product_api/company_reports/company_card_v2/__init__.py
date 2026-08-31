"""Fail-closed Company Card v2 domain boundary.

This package deliberately has no provider, database, queue or HTTP dependency.
"""

from .decimal_transport import SourceDecimal, parse_source_decimal
from .models import CompanyCardV2Snapshot

__all__ = ["CompanyCardV2Snapshot", "SourceDecimal", "parse_source_decimal"]
