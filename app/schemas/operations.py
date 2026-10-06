"""
Pydantic schemas for FlightPulse Operations and Synchronization API.
Represents ingestion source status, operational freshness, on-demand synchronization results,
and system-level sync states without fabricating timestamps.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SourceStatusDetail(BaseModel):
    """Operational status and latest sync telemetry for a single ingestion source."""
    status: str = Field(description="Operational status: 'SUCCESS', 'FAILED', or 'NEVER_SYNCED'")
    last_attempt: Optional[datetime] = Field(default=None, description="Timestamp of the most recent sync attempt")
    last_success: Optional[datetime] = Field(default=None, description="Timestamp of the most recent successful sync")
    records_extracted: int = Field(default=0, description="Records extracted during latest sync attempt")
    records_inserted: int = Field(default=0, description="Records inserted during latest sync attempt")
    records_updated: int = Field(default=0, description="Records updated during latest sync attempt")
    duration_ms: float = Field(default=0.0, description="Execution latency in milliseconds for latest attempt")
    error_message: Optional[str] = Field(default=None, description="Error message if the latest sync attempt failed")


class OperationsStatusResponse(BaseModel):
    """Aggregate system health and source-level freshness summary from operations_sync_log."""
    overall_status: str = Field(description="'HEALTHY', 'PARTIAL', 'FAILED', or 'NEVER_SYNCED'")
    last_sync: Optional[datetime] = Field(default=None, description="Timestamp of the most recent sync attempt across all sources")
    sources: Dict[str, SourceStatusDetail] = Field(description="Individual source metrics keyed by source name (opensky, openmeteo, faa)")


class SourceSyncResultDetail(BaseModel):
    """Execution metrics for an individual ingestion source in a sync run."""
    source_name: str
    status: str  # 'SUCCESS', 'FAILED', 'SKIPPED'
    records_extracted: int = 0
    records_transformed: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_skipped: int = 0
    errors: int = 0
    error_message: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: datetime


class OperationsSyncResponse(BaseModel):
    """Structured response from POST /operations/sync."""
    status: str = Field(description="Overall sync run outcome: 'SUCCESS', 'PARTIAL', 'FAILED', or 'SYNC_IN_PROGRESS'")
    overall_status: str = Field(description="Alias for status matching orchestration schema")
    duration_ms: float = Field(description="Total sync execution duration in milliseconds")
    timestamp: datetime = Field(description="Timestamp when orchestration completed or was initiated")
    sources: Dict[str, SourceSyncResultDetail] = Field(default_factory=dict, description="Per-source execution breakdown")
