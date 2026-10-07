"""
Timeline service assembling chronological disruption progression for a flight.
Uses only existing factual records in the PostgreSQL database without fabricating events.
"""

from typing import List, Optional
from psycopg2.extensions import connection

from app.schemas.timeline import FlightTimelineResponse, TimelineEventItem
from app.services.flight_service import get_flight_by_id, get_flight_disruptions, get_flight_weather


def build_flight_timeline(conn: connection, flight_id: int) -> Optional[FlightTimelineResponse]:
    """
    Assemble an ordered, chronological timeline of all events relevant to a flight.
    
    Args:
        conn: Active psycopg2 database connection
        flight_id: Unique flight identifier

    Returns:
        FlightTimelineResponse if flight exists, else None.
    """
    flight = get_flight_by_id(conn, flight_id)
    if not flight:
        return None

    raw_events: List[TimelineEventItem] = []

    # 1. Flight Milestones
    if flight.scheduled_departure:
        raw_events.append(TimelineEventItem(
            time=flight.scheduled_departure,
            event_type="SCHEDULED_DEPARTURE",
            category="FLIGHT",
            title="Scheduled Departure",
            detail=f"Scheduled departure from {flight.origin_iata or 'Origin'} to {flight.destination_iata or 'Destination'}",
            severity="INFO",
            source="FLIGHT_SCHEDULE",
        ))

    if flight.actual_departure:
        dep_delay_str = f"delay: {flight.departure_delay_minutes} min" if flight.departure_delay_minutes is not None else "live transponder observation"
        sev = "HIGH" if (flight.departure_delay_minutes or 0) > 45 else ("MEDIUM" if (flight.departure_delay_minutes or 0) > 15 else "LOW")
        raw_events.append(TimelineEventItem(
            time=flight.actual_departure,
            event_type="ACTUAL_DEPARTURE",
            category="FLIGHT",
            title="Actual Departure",
            detail=f"Aircraft departed {flight.origin_iata or 'Airspace'} ({dep_delay_str})",
            severity=sev,
            source="ACTUAL_OPERATIONS",
        ))

    if flight.scheduled_arrival:
        raw_events.append(TimelineEventItem(
            time=flight.scheduled_arrival,
            event_type="SCHEDULED_ARRIVAL",
            category="FLIGHT",
            title="Scheduled Arrival",
            detail=f"Scheduled arrival at {flight.destination_iata or 'Destination'}",
            severity="INFO",
            source="FLIGHT_SCHEDULE",
        ))

    if flight.actual_arrival:
        raw_events.append(TimelineEventItem(
            time=flight.actual_arrival,
            event_type="ACTUAL_ARRIVAL",
            category="FLIGHT",
            title="Actual Arrival",
            detail=f"Aircraft touched down and docked at {flight.destination_iata or 'Destination'}",
            severity="INFO",
            source="ACTUAL_OPERATIONS",
        ))

    # 2. Flight Lifecycle Events from `flight_events` table
    with conn.cursor() as cur:
        cur.execute(
            "SELECT event_type, event_time, description, metadata FROM flight_events WHERE flight_id = %s ORDER BY event_time ASC;",
            (flight.id,)
        )
        fe_rows = cur.fetchall()

    for r in fe_rows:
        fe_type, fe_time, fe_desc, fe_meta = r
        raw_events.append(TimelineEventItem(
            time=fe_time,
            event_type=f"LIFECYCLE_{fe_type}",
            category="AIRLINE",
            title=fe_desc,
            detail=str(fe_meta) if fe_meta else None,
            severity="MEDIUM" if "DELAY" in fe_type else "INFO",
            source="DISPATCH_LOGS",
        ))

    # 3. FAA Disruption Advisories
    disruptions_data = get_flight_disruptions(conn, flight_id)
    if disruptions_data:
        for d in disruptions_data.disruptions:
            raw_events.append(TimelineEventItem(
                time=d.start_time,
                event_type=f"DISRUPTION_START_{d.event_type}",
                category="ATC",
                title=f"{d.title} (Began)",
                detail=d.summary[:150] if d.summary else None,
                severity=d.severity,
                source=d.source,
            ))
            if d.end_time:
                raw_events.append(TimelineEventItem(
                    time=d.end_time,
                    event_type=f"DISRUPTION_END_{d.event_type}",
                    category="ATC",
                    title=f"{d.title} (Ended)",
                    detail=f"Advisory lifted for {d.affected_airport_code or 'airspace'}",
                    severity="INFO",
                    source=d.source,
                ))

    # 4. Significant Weather Observations near departure window (within +/- 1.5 hours)
    weather_data = get_flight_weather(conn, flight_id)
    if weather_data:
        for wx in weather_data.origin_observations:
            # Highlight non-clear or windy/restricted weather
            if wx.condition_code not in ("CLEAR", "MAINLY_CLEAR") or (wx.wind_speed_knots and wx.wind_speed_knots >= 20.0):
                detail_parts = [f"Condition: {wx.condition_code}"]
                if wx.wind_speed_knots:
                    detail_parts.append(f"Wind: {wx.wind_speed_knots:.1f} kt" + (f" G {wx.wind_gust_knots:.1f} kt" if wx.wind_gust_knots else ""))
                if wx.visibility_miles:
                    detail_parts.append(f"Visibility: {wx.visibility_miles:.2f} mi")

                raw_events.append(TimelineEventItem(
                    time=wx.observation_time,
                    event_type="WEATHER_OBSERVATION",
                    category="WEATHER",
                    title=f"Weather Observation at {wx.airport_code}: {wx.condition_code}",
                    detail=", ".join(detail_parts),
                    severity="HIGH" if "THUNDERSTORM" in wx.condition_code else "MEDIUM",
                    source="METAR_STATION",
                ))

    # Sort strictly chronologically by timestamp
    raw_events.sort(key=lambda e: e.time)

    return FlightTimelineResponse(
        flight_id=flight.id,
        flight_number=flight.flight_number,
        route=f"{flight.origin_iata} -> {flight.destination_iata}",
        total_events=len(raw_events),
        timeline=raw_events,
    )
