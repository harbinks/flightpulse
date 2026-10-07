"""
Evidence collection module for FlightPulse Intelligence Engine.
Queries PostgreSQL for all available facts (flight schedules, actuals, weather observations,
operational disruption events, and flight lifecycle events) relating to a specific flight.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
from psycopg2.extensions import connection


@dataclass
class FlightDetail:
    """Core flight details extracted from the database."""
    flight_id: int
    flight_number: str
    airline_id: Optional[int]
    airline_name: Optional[str]
    airline_iata: Optional[str]
    origin_airport_id: Optional[int]
    origin_iata: Optional[str]
    origin_name: Optional[str]
    destination_airport_id: Optional[int]
    destination_iata: Optional[str]
    destination_name: Optional[str]
    flight_date: str
    scheduled_departure: Optional[datetime]
    actual_departure: Optional[datetime]
    scheduled_arrival: Optional[datetime]
    actual_arrival: Optional[datetime]
    status: str
    departure_delay_minutes: Optional[int]
    arrival_delay_minutes: Optional[int]
    delay_category: Optional[str]
    tail_number: Optional[str]
    aircraft_type: Optional[str]


@dataclass
class WeatherEvidence:
    """Weather observation evidence associated with an airport."""
    airport_id: int
    airport_code: str
    observation_time: datetime
    temperature_c: Optional[float]
    wind_speed_knots: Optional[float]
    wind_gust_knots: Optional[float]
    wind_direction_deg: Optional[int]
    visibility_miles: Optional[float]
    altimeter_inhg: Optional[float]
    condition_code: str
    raw_metar: Optional[str]
    is_origin: bool


@dataclass
class DisruptionEvidence:
    """Operational news or disruption event from FAA / external feeds."""
    event_id: int
    title: str
    summary: str
    source: str
    url: Optional[str]
    event_type: str
    severity: str
    affected_airport_id: Optional[int]
    affected_airport_code: Optional[str]
    affected_airline_id: Optional[int]
    affected_airline_code: Optional[str]
    start_time: datetime
    end_time: Optional[datetime]


@dataclass
class FlightEventEvidence:
    """Lifecycle progression or dispatch event for a flight."""
    event_id: int
    event_type: str
    event_time: datetime
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlightEvidenceBundle:
    """Aggregated bundle of all factual evidence pertaining to a flight."""
    flight: FlightDetail
    weather_observations: List[WeatherEvidence] = field(default_factory=list)
    disruptions: List[DisruptionEvidence] = field(default_factory=list)
    flight_events: List[FlightEventEvidence] = field(default_factory=list)


def collect_flight_evidence(conn: connection, flight_ref: Union[int, str]) -> Optional[FlightEvidenceBundle]:
    """
    Query PostgreSQL to assemble a complete factual evidence bundle for a flight.
    
    Args:
        conn: Active psycopg2 database connection
        flight_ref: Flight ID (int) or Flight Number (str, e.g. 'UA415')

    Returns:
        FlightEvidenceBundle if flight found, else None.
    """
    with conn.cursor() as cur:
        # 1. Fetch Flight Details
        if isinstance(flight_ref, int) or (isinstance(flight_ref, str) and flight_ref.isdigit()):
            flight_sql = """
                SELECT 
                    f.id, f.flight_number, f.airline_id, al.name AS airline_name, al.iata_code AS airline_iata,
                    f.origin_airport_id, orig.iata_code AS origin_iata, orig.name AS origin_name,
                    f.destination_airport_id, dest.iata_code AS destination_iata, dest.name AS destination_name,
                    f.flight_date::text, f.scheduled_departure, f.actual_departure,
                    f.scheduled_arrival, f.actual_arrival, f.status,
                    f.departure_delay_minutes, f.arrival_delay_minutes, f.delay_category,
                    f.tail_number, f.aircraft_type
                FROM flights f
                LEFT JOIN airlines al ON f.airline_id = al.id
                LEFT JOIN airports orig ON f.origin_airport_id = orig.id
                LEFT JOIN airports dest ON f.destination_airport_id = dest.id
                WHERE f.id = %s
                LIMIT 1;
            """
            cur.execute(flight_sql, (int(flight_ref),))
        else:
            flight_sql = """
                SELECT 
                    f.id, f.flight_number, f.airline_id, al.name AS airline_name, al.iata_code AS airline_iata,
                    f.origin_airport_id, orig.iata_code AS origin_iata, orig.name AS origin_name,
                    f.destination_airport_id, dest.iata_code AS destination_iata, dest.name AS destination_name,
                    f.flight_date::text, f.scheduled_departure, f.actual_departure,
                    f.scheduled_arrival, f.actual_arrival, f.status,
                    f.departure_delay_minutes, f.arrival_delay_minutes, f.delay_category,
                    f.tail_number, f.aircraft_type
                FROM flights f
                LEFT JOIN airlines al ON f.airline_id = al.id
                LEFT JOIN airports orig ON f.origin_airport_id = orig.id
                LEFT JOIN airports dest ON f.destination_airport_id = dest.id
                WHERE f.flight_number = %s
                ORDER BY f.scheduled_departure DESC NULLS LAST, f.actual_departure DESC NULLS LAST
                LIMIT 1;
            """
            cur.execute(flight_sql, (flight_ref.strip().upper(),))

        flight_row = cur.fetchone()
        if not flight_row:
            return None

        flight = FlightDetail(
            flight_id=flight_row[0],
            flight_number=flight_row[1],
            airline_id=flight_row[2],
            airline_name=flight_row[3],
            airline_iata=flight_row[4],
            origin_airport_id=flight_row[5],
            origin_iata=flight_row[6],
            origin_name=flight_row[7],
            destination_airport_id=flight_row[8],
            destination_iata=flight_row[9],
            destination_name=flight_row[10],
            flight_date=str(flight_row[11]),
            scheduled_departure=flight_row[12],
            actual_departure=flight_row[13],
            scheduled_arrival=flight_row[14],
            actual_arrival=flight_row[15],
            status=flight_row[16],
            departure_delay_minutes=flight_row[17],
            arrival_delay_minutes=flight_row[18],
            delay_category=flight_row[19],
            tail_number=flight_row[20],
            aircraft_type=flight_row[21],
        )

        ref_dep = flight.scheduled_departure or flight.actual_departure
        ref_arr = flight.scheduled_arrival or flight.actual_arrival or ref_dep

        # 2. Fetch Relevant Weather Observations (Within +/- 3 hours of departure / arrival)
        weather_list = []
        if ref_dep and (flight.origin_airport_id is not None or flight.destination_airport_id is not None):
            weather_sql = """
                SELECT 
                    w.airport_id, a.iata_code, w.observation_time, w.temperature_c,
                    w.wind_speed_knots, w.wind_gust_knots, w.wind_direction_deg,
                    w.visibility_miles, w.altimeter_inhg, w.condition_code, w.raw_metar,
                    (w.airport_id = %s) AS is_origin
                FROM weather_observations w
                JOIN airports a ON w.airport_id = a.id
                WHERE (w.airport_id = %s AND w.observation_time BETWEEN %s AND %s)
                   OR (w.airport_id = %s AND w.observation_time BETWEEN %s AND %s)
                ORDER BY w.observation_time ASC;
            """
            cur.execute(weather_sql, (
                flight.origin_airport_id,
                flight.origin_airport_id, ref_dep - timedelta(hours=3), ref_dep + timedelta(hours=3),
                flight.destination_airport_id, ref_arr - timedelta(hours=3), ref_arr + timedelta(hours=3),
            ))
            weather_rows = cur.fetchall()

            weather_list = [
                WeatherEvidence(
                    airport_id=row[0],
                    airport_code=row[1],
                    observation_time=row[2],
                    temperature_c=float(row[3]) if row[3] is not None else None,
                    wind_speed_knots=float(row[4]) if row[4] is not None else None,
                    wind_gust_knots=float(row[5]) if row[5] is not None else None,
                    wind_direction_deg=row[6],
                    visibility_miles=float(row[7]) if row[7] is not None else None,
                    altimeter_inhg=float(row[8]) if row[8] is not None else None,
                    condition_code=row[9] or "UNKNOWN",
                    raw_metar=row[10],
                    is_origin=bool(row[11]),
                )
                for row in weather_rows
            ]

        # 3. Fetch Relevant Disruptions & News Events
        disruption_list = []
        if ref_dep:
            disruption_sql = """
                SELECT 
                    n.id, n.title, n.summary, n.source, n.url, n.event_type, n.severity,
                    n.airport_id, a.iata_code, n.airline_id, al.iata_code,
                    n.start_time, n.end_time
                FROM news_events n
                LEFT JOIN airports a ON n.airport_id = a.id
                LEFT JOIN airlines al ON n.airline_id = al.id
                WHERE (
                    (n.airport_id = %s OR n.airport_id = %s OR n.airport_id IS NULL)
                    AND (n.airline_id = %s OR n.airline_id IS NULL)
                )
                AND n.start_time <= %s
                AND (n.end_time IS NULL OR n.end_time >= %s)
                ORDER BY n.start_time ASC;
            """
            cur.execute(disruption_sql, (
                flight.origin_airport_id, flight.destination_airport_id,
                flight.airline_id,
                ref_dep + timedelta(hours=4),
                ref_dep - timedelta(hours=4),
            ))
            disruption_rows = cur.fetchall()

        disruption_list = [
            DisruptionEvidence(
                event_id=row[0],
                title=row[1],
                summary=row[2] or "",
                source=row[3] or "",
                url=row[4],
                event_type=row[5],
                severity=row[6],
                affected_airport_id=row[7],
                affected_airport_code=row[8],
                affected_airline_id=row[9],
                affected_airline_code=row[10],
                start_time=row[11],
                end_time=row[12],
            )
            for row in disruption_rows
        ]

        # 4. Fetch Flight Lifecycle Events
        events_sql = """
            SELECT id, event_type, event_time, description, metadata
            FROM flight_events
            WHERE flight_id = %s
            ORDER BY event_time ASC;
        """
        cur.execute(events_sql, (flight.flight_id,))
        event_rows = cur.fetchall()

        event_list = [
            FlightEventEvidence(
                event_id=row[0],
                event_type=row[1],
                event_time=row[2],
                description=row[3] or "",
                metadata=row[4] or {},
            )
            for row in event_rows
        ]

        return FlightEvidenceBundle(
            flight=flight,
            weather_observations=weather_list,
            disruptions=disruption_list,
            flight_events=event_list,
        )
