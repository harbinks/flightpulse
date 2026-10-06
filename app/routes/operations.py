"""
Operations and Synchronization routes for FlightPulse.
Provides endpoints for monitoring ingestion health and triggering on-demand sync.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg2.extensions import connection

from app.database import get_db
from app.schemas.operations import OperationsStatusResponse, OperationsSyncResponse
from app.services.operations_service import (
    get_operations_status,
    is_sync_in_progress,
    trigger_live_sync,
)

router = APIRouter(prefix="/operations", tags=["Operations"])


@router.get("/status", response_model=OperationsStatusResponse)
def get_status(conn: connection = Depends(get_db)) -> OperationsStatusResponse:
    """
    Retrieve operational health and source-level freshness metrics.
    Derived directly from the operations_sync_log table.
    """
    try:
        return get_operations_status(conn)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query operational status from telemetry logs.",
        )


@router.post("/sync", response_model=OperationsSyncResponse)
def run_sync(
    mode: str = Query("live", description="Sync mode: 'live' (default) or 'demo'"),
    airport: str = Query("KORD", description="Primary airport ICAO code for flight extraction"),
    dry_run: bool = Query(False, description="Simulate ingestion without writing to database"),
) -> OperationsSyncResponse:
    """
    Trigger on-demand multi-source synchronization.
    Serialized via in-process locking: rejects concurrent runs with HTTP 409 SYNC_IN_PROGRESS.
    """
    clean_mode = (mode or "live").strip().lower()
    if clean_mode not in ("live", "demo"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid sync mode '{mode}'. Must be 'live' or 'demo'.",
        )

    # Check if sync is actively running
    if is_sync_in_progress():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Synchronization is already in progress. Please wait for current run to complete.",
        )

    success, sync_response = trigger_live_sync(
        mode=clean_mode,
        airport_icao=airport.strip().upper(),
        dry_run=dry_run,
    )

    if not success or sync_response is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Synchronization is already in progress. Please wait for current run to complete.",
        )

    return sync_response
