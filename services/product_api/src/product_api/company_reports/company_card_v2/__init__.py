"""Fail-closed Company Card v2 domain boundary.

This package deliberately has no provider, database, queue or HTTP dependency.
"""

from .decimal_transport import SourceDecimal, parse_source_decimal
from .models import (
    CompanyCardV2Snapshot,
    CompanyCardV2SnapshotV1,
    CompanyCardV2SnapshotV2,
    NarrativeEvidenceV1,
    PrimaryActivitySnapshotV1,
)
from .primary_activity import (
    PRIMARY_ACTIVITY_EVIDENCE_VERSION,
    PRIMARY_ACTIVITY_PARSER_VERSION,
    SOURCE_PROFILE_VERSION,
    PrimaryActivityV1,
    parse_primary_activity,
)

__all__ = [
    "CompanyCardV2Snapshot",
    "CompanyCardV2SnapshotV1",
    "CompanyCardV2SnapshotV2",
    "NarrativeEvidenceV1",
    "PRIMARY_ACTIVITY_EVIDENCE_VERSION",
    "PRIMARY_ACTIVITY_PARSER_VERSION",
    "PrimaryActivitySnapshotV1",
    "PrimaryActivityV1",
    "SOURCE_PROFILE_VERSION",
    "SourceDecimal",
    "parse_primary_activity",
    "parse_source_decimal",
]
