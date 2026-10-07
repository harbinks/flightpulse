"""
Operations service for FlightPulse.
Handles querying operations_sync_log for system status and safely executing
on-demand live orchestration with concurrency serialization.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from psycopg2.extensions import connection

from app.schemas.operations import (
    OperationsStatusResponse,
    OperationsSyncResponse,
    SourceStatusDetail,
    SourceSyncResultDetail,
)
from pipeline.orchestrator import orchestrate_ingestion

logger = logging.getLogger("flightpulse.operations")

# In-process lock to prevent concurrent ingestion dogpiling
_SYNC_LOCK = threading.Lock()
_SYNC_IN_PROGRESS = False


def is_sync_in_progress() -> bool:
    """Check if a synchronization run is actively executing."""
    return _SYNC_IN_PROGRESS


def get_operations_status(conn: connection) -> OperationsStatusResponse:
    """
    Query operations_sync_log to construct authoritative health & freshness metrics.
    Does not fabricate timestamps or health states.
    Sources tracked:
      - opensky: sync_source IN ('OPENSKY_LIVE', 'DEMO_FLIGHTS')
      - openmeteo: sync_source IN ('OPENMETEO_LIVE', 'DEMO_WEATHER')
      - faa: sync_source IN ('FAA_LIVE', 'DEMO_FAA')
    """
    source_definitions = {
        "opensky": ("OPENSKY_LIVE", "DEMO_FLIGHTS"),
        "openmeteo": ("OPENMETEO_LIVE", "DEMO_WEATHER"),
        "faa": ("FAA_LIVE", "DEMO_FAA"),
    }

    sources_status: Dict[str, SourceStatusDetail] = {}
    overall_last_sync: Optional[datetime] = None

    with conn.cursor() as cur:
        for key, matching_sources in source_definitions.items():
            # Query the latest attempt (regardless of status)
            cur.execute(
                """
                SELECT sync_status, created_at, records_extracted, records_inserted, 
                       records_updated, duration_ms, error_message
                FROM operations_sync_log
                WHERE sync_source = ANY(%s)
                ORDER BY created_at DESC, id DESC
                LIMIT 1;
                """,
                (list(matching_sources),),
            )
            latest_attempt = cur.fetchone()

            # Query the latest successful run
            cur.execute(
                """
                SELECT created_at
                FROM operations_sync_log
                WHERE sync_source = ANY(%s) AND sync_status = 'SUCCESS'
                ORDER BY created_at DESC, id DESC
                LIMIT 1;
                """,
                (list(matching_sources),),
            )
            latest_success_row = cur.fetchone()
            last_success = latest_success_row[0] if latest_success_row else None

            if not latest_attempt:
                # Source has never been synced
                sources_status[key] = SourceStatusDetail(
                    status="NEVER_SYNCED",
                    last_attempt=None,
                    last_success=None,
                    records_extracted=0,
                    records_inserted=0,
                    records_updated=0,
                    duration_ms=0.0,
                    error_message=None,
                )
            else:
                att_status = latest_attempt[0]
                att_time = latest_attempt[1]
                rec_ext = latest_attempt[2] or 0
                rec_ins = latest_attempt[3] or 0
                rec_upd = latest_attempt[4] or 0
                dur_ms = float(latest_attempt[5]) if latest_attempt[5] is not None else 0.0
                err_msg = latest_attempt[6]

                if overall_last_sync is None or (att_time and att_time > overall_last_sync):
                    overall_last_sync = att_time

                sources_status[key] = SourceStatusDetail(
                    status=att_status,
                    last_attempt=att_time,
                    last_success=last_success,
                    records_extracted=rec_ext,
                    records_inserted=rec_ins,
                    records_updated=rec_upd,
                    duration_ms=dur_ms,
                    error_message=err_msg,
                )

    # Compute overall status across tracked sources
    statuses = [s.status for s in sources_status.values()]
    if all(st == "NEVER_SYNCED" for st in statuses):
        overall_status = "NEVER_SYNCED"
    elif all(st == "SUCCESS" for st in statuses):
        overall_status = "HEALTHY"
    elif any(st == "SUCCESS" for st in statuses):
        overall_status = "PARTIAL"
    else:
        overall_status = "FAILED"

    return OperationsStatusResponse(
        overall_status=overall_status,
        last_sync=overall_last_sync,
        sources=sources_status,
    )


def trigger_live_sync(
    mode: str = "live",
    airport_icao: str = "KORD",
    dry_run: bool = False,
) -> Tuple[bool, Optional[OperationsSyncResponse]]:
    """
    Safely trigger orchestration run.
    Guarantees concurrency serialization: returns (False, None) if a sync is already running.
    Otherwise runs synchronously and returns (True, OperationsSyncResponse).
    """
    global _SYNC_IN_PROGRESS

    # Attempt to acquire lock without blocking
    acquired = _SYNC_LOCK.acquire(blocking=False)
    if not acquired:
        return False, None

    try:
        _SYNC_IN_PROGRESS = True
        logger.info("Executing on-demand synchronization [mode=%s, airport=%s, dry_run=%s]", mode, airport_icao, dry_run)
        
        orch_res = orchestrate_ingestion(
            mode=mode,
            airport_icao=airport_icao,
            dry_run=dry_run,
        )

        sources_detail: Dict[str, SourceSyncResultDetail] = {}
        for src_key, src_val in orch_res.sources.items():
            sources_detail[src_key] = SourceSyncResultDetail(
                source_name=src_val.source_name,
                status=src_val.status,
                records_extracted=src_val.records_extracted,
                records_transformed=src_val.records_transformed,
                records_inserted=src_val.records_inserted,
                records_updated=src_val.records_updated,
                records_skipped=src_val.records_skipped,
                errors=src_val.errors,
                error_message=src_val.error_message,
                duration_ms=src_val.duration_ms,
                timestamp=src_val.timestamp,
                skip_reasons=getattr(src_val, "skip_reasons", {}),
            )

        resp = OperationsSyncResponse(
            status=orch_res.overall_status,
            overall_status=orch_res.overall_status,
            duration_ms=orch_res.duration_ms,
            timestamp=orch_res.timestamp,
            sources=sources_detail,
        )
        return True, resp

    finally:
        _SYNC_IN_PROGRESS = False
        _SYNC_LOCK.release()
