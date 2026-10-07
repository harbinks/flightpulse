"""
Flight service providing query and filtering operations over PostgreSQL flight records.
"""

from typing import Any, Dict, List, Optional
from psycopg2.extensions import connection

from app.schemas.disruptions import DisruptionEventItem, FlightDisruptionsResponse
from app.schemas.flights import FlightDetailResponse, FlightListResponse, FlightSummary
from app.schemas.weather import FlightWeatherResponse, WeatherObservationItem


def search_flights(
    conn: connection,
    airline: Optional[str] = None,
    flight_number: Optional[str] = None,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
    date: Optional[str] = None,
    delay_status: Optional[str] = None,
    mode: str = "demo",
    limit: int = 50,
    offset: int = 0,
) -> FlightListResponse:
    """
    Search and filter flights with optional parameters and DEMO/LIVE mode isolation.
    - mode="demo" (default): data_source IN ('DEMO', 'FIXTURE', 'FIXTURE_REPLAY', 'FLIGHTAWARE')
    - mode="live": data_source = 'OPENSKY_LIVE'
    - mode="all": no data_source restriction
    """
    conditions = []
    params: List[Any] = []

    clean_mode = (mode or "demo").strip().lower()
    if clean_mode == "live":
        conditions.append("f.data_source = 'OPENSKY_LIVE'")
    elif clean_mode == "demo":
        conditions.append("(f.data_source IS NULL OR f.data_source IN ('DEMO', 'FIXTURE', 'FIXTURE_REPLAY', 'FLIGHTAWARE'))")
    # if clean_mode == "all", no data_source condition added

    if airline:
        conditions.append("(al.iata_code = %s OR al.icao_code = %s OR al.name ILIKE %s)")
        clean_al = airline.strip().upper()
        params.extend([clean_al, clean_al, f"%{airline.strip()}%"])

    if flight_number:
        conditions.append("f.flight_number ILIKE %s")
        params.append(f"%{flight_number.strip()}%")

    if origin:
        clean_orig = origin.strip().upper()
        conditions.append("(orig.iata_code = %s OR orig.icao_code = %s)")
        params.extend([clean_orig, clean_orig])

    if destination:
        clean_dest = destination.strip().upper()
        conditions.append("(dest.iata_code = %s OR dest.icao_code = %s)")
        params.extend([clean_dest, clean_dest])

    if date:
        conditions.append("f.flight_date = %s")
        params.append(date.strip())

    if delay_status:
        clean_status = delay_status.strip().upper()
        if clean_status == "DELAYED":
            conditions.append("f.departure_delay_minutes > 15")
        elif clean_status == "ON_TIME":
            conditions.append("f.departure_delay_minutes <= 15 AND f.status <> 'CANCELLED'")
        elif clean_status in ("CANCELLED", "DIVERTED", "LANDED", "SCHEDULED"):
            conditions.append("f.status = %s")
            params.append(clean_status)

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    count_sql = f"""
        SELECT COUNT(*)
        FROM flights f
        LEFT JOIN airlines al ON f.airline_id = al.id
        LEFT JOIN airports orig ON f.origin_airport_id = orig.id
        LEFT JOIN airports dest ON f.destination_airport_id = dest.id
        {where_clause};
    """

    # For DEMO mode, order by flight_date DESC, scheduled_departure DESC
    # For LIVE mode (where scheduled_departure is NULL), order by actual_departure DESC NULLS LAST
    order_clause = (
        "ORDER BY f.actual_departure DESC NULLS LAST, f.flight_date DESC"
        if clean_mode == "live"
        else "ORDER BY f.flight_date DESC, f.scheduled_departure DESC NULLS LAST"
    )

    select_sql = f"""
        SELECT 
            f.id, f.flight_number, al.name AS airline_name, al.iata_code AS airline_iata,
            orig.iata_code AS origin_iata, orig.city AS origin_city,
            dest.iata_code AS destination_iata, dest.city AS destination_city,
            f.flight_date::text, f.scheduled_departure, f.actual_departure,
            f.scheduled_arrival, f.actual_arrival, f.status,
            f.departure_delay_minutes, f.arrival_delay_minutes, f.delay_category,
            f.aircraft_type, f.data_source
        FROM flights f
        LEFT JOIN airlines al ON f.airline_id = al.id
        LEFT JOIN airports orig ON f.origin_airport_id = orig.id
        LEFT JOIN airports dest ON f.destination_airport_id = dest.id
        {where_clause}
        {order_clause}
        LIMIT %s OFFSET %s;
    """

    with conn.cursor() as cur:
        cur.execute(count_sql, tuple(params))
        total = cur.fetchone()[0]

        select_params = list(params) + [limit, offset]
        cur.execute(select_sql, tuple(select_params))
        rows = cur.fetchall()

    summaries = [
        FlightSummary(
            id=r[0],
            flight_number=r[1],
            airline_name=r[2],
            airline_iata=r[3],
            origin_iata=r[4],
            origin_city=r[5],
            destination_iata=r[6],
            destination_city=r[7],
            flight_date=str(r[8]),
            scheduled_departure=r[9],
            actual_departure=r[10],
            scheduled_arrival=r[11],
            actual_arrival=r[12],
            status=r[13],
            departure_delay_minutes=r[14],
            arrival_delay_minutes=r[15],
            delay_category=r[16],
            aircraft_type=r[17],
            data_source=r[18],
        )
        for r in rows
    ]

    return FlightListResponse(total=total, flights=summaries)


def get_flight_by_id(conn: connection, flight_id: int) -> Optional[FlightDetailResponse]:
    """Retrieve full flight record by primary key."""
    sql = """
        SELECT 
            f.id, f.flight_number, f.airline_id, al.name AS airline_name, al.iata_code AS airline_iata,
            f.origin_airport_id, orig.iata_code AS origin_iata, orig.name AS origin_name,
            orig.city AS origin_city, orig.timezone AS origin_timezone,
            f.destination_airport_id, dest.iata_code AS destination_iata, dest.name AS destination_name,
            dest.city AS destination_city, dest.timezone AS destination_timezone,
            f.flight_date::text, f.scheduled_departure, f.actual_departure,
            f.scheduled_arrival, f.actual_arrival, f.status,
            f.departure_delay_minutes, f.arrival_delay_minutes, f.delay_category,
            f.tail_number, f.aircraft_type, f.distance_miles, f.data_source
        FROM flights f
        LEFT JOIN airlines al ON f.airline_id = al.id
        LEFT JOIN airports orig ON f.origin_airport_id = orig.id
        LEFT JOIN airports dest ON f.destination_airport_id = dest.id
        WHERE f.id = %s;
    """
    with conn.cursor() as cur:
        cur.execute(sql, (flight_id,))
        r = cur.fetchone()
        if not r:
            return None

    return FlightDetailResponse(
        id=r[0],
        flight_number=r[1],
        airline_id=r[2],
        airline_name=r[3],
        airline_iata=r[4],
        origin_airport_id=r[5],
        origin_iata=r[6],
        origin_name=r[7],
        origin_city=r[8],
        origin_timezone=r[9],
        destination_airport_id=r[10],
        destination_iata=r[11],
        destination_name=r[12],
        destination_city=r[13],
        destination_timezone=r[14],
        flight_date=str(r[15]),
        scheduled_departure=r[16],
        actual_departure=r[17],
        scheduled_arrival=r[18],
        actual_arrival=r[19],
        status=r[20],
        departure_delay_minutes=r[21],
        arrival_delay_minutes=r[22],
        delay_category=r[23],
        tail_number=r[24],
        aircraft_type=r[25],
        distance_miles=float(r[26]) if r[26] is not None else None,
        data_source=r[27],
    )


def get_flight_weather(conn: connection, flight_id: int) -> Optional[FlightWeatherResponse]:
    """Retrieve weather observations near departure and arrival for a flight."""
    flight = get_flight_by_id(conn, flight_id)
    if not flight:
        return None

    ref_dep = flight.scheduled_departure or flight.actual_departure
    ref_arr = flight.scheduled_arrival or flight.actual_arrival or ref_dep

    if not ref_dep or (flight.origin_airport_id is None and flight.destination_airport_id is None):
        return FlightWeatherResponse(
            flight_id=flight.id,
            flight_number=flight.flight_number,
            origin_airport=flight.origin_iata,
            destination_airport=flight.destination_iata,
            origin_observations=[],
            destination_observations=[],
        )

    sql = """
        SELECT 
            w.id, w.airport_id, a.iata_code, (w.airport_id = %s) AS is_origin,
            w.observation_time, w.temperature_c, w.dewpoint_c,
            w.wind_speed_knots, w.wind_gust_knots, w.wind_direction_deg,
            w.visibility_miles, w.altimeter_inhg, w.condition_code,
            w.raw_metar, w.data_source
        FROM weather_observations w
        JOIN airports a ON w.airport_id = a.id
        WHERE (w.airport_id = %s AND w.observation_time BETWEEN %s - INTERVAL '3 hours' AND %s + INTERVAL '3 hours')
           OR (w.airport_id = %s AND w.observation_time BETWEEN %s - INTERVAL '3 hours' AND %s + INTERVAL '3 hours')
        ORDER BY w.observation_time ASC;
    """

    with conn.cursor() as cur:
        cur.execute(sql, (
            flight.origin_airport_id,
            flight.origin_airport_id, ref_dep, ref_dep,
            flight.destination_airport_id, ref_arr, ref_arr,
        ))
        rows = cur.fetchall()

    origin_items: List[WeatherObservationItem] = []
    dest_items: List[WeatherObservationItem] = []

    for r in rows:
        item = WeatherObservationItem(
            id=r[0],
            airport_id=r[1],
            airport_code=r[2],
            is_origin=bool(r[3]),
            observation_time=r[4],
            temperature_c=float(r[5]) if r[5] is not None else None,
            dewpoint_c=float(r[6]) if r[6] is not None else None,
            wind_speed_knots=float(r[7]) if r[7] is not None else None,
            wind_gust_knots=float(r[8]) if r[8] is not None else None,
            wind_direction_deg=r[9],
            visibility_miles=float(r[10]) if r[10] is not None else None,
            altimeter_inhg=float(r[11]) if r[11] is not None else None,
            condition_code=r[12] or "UNKNOWN",
            raw_metar=r[13],
            data_source=r[14],
        )
        if item.is_origin:
            origin_items.append(item)
        else:
            dest_items.append(item)

    return FlightWeatherResponse(
        flight_id=flight.id,
        flight_number=flight.flight_number,
        origin_airport=flight.origin_iata,
        destination_airport=flight.destination_iata,
        origin_observations=origin_items,
        destination_observations=dest_items,
    )


def get_flight_disruptions(conn: connection, flight_id: int) -> Optional[FlightDisruptionsResponse]:
    """Retrieve operational disruptions and advisories relevant to a flight."""
    flight = get_flight_by_id(conn, flight_id)
    if not flight:
        return None

    ref_time = flight.scheduled_departure or flight.actual_departure
    if not ref_time:
        return FlightDisruptionsResponse(
            flight_id=flight.id,
            flight_number=flight.flight_number,
            total_disruptions=0,
            disruptions=[],
        )

    sql = """
        SELECT 
            n.id, n.title, n.summary, n.source, n.url, n.event_type, n.severity,
            a.iata_code AS affected_airport, al.iata_code AS affected_airline,
            n.start_time, n.end_time, n.data_source
        FROM news_events n
        LEFT JOIN airports a ON n.airport_id = a.id
        LEFT JOIN airlines al ON n.airline_id = al.id
        WHERE (
            (n.airport_id = %s OR n.airport_id = %s OR n.airport_id IS NULL)
            AND (n.airline_id = %s OR n.airline_id IS NULL)
        )
        AND n.start_time <= %s + INTERVAL '4 hours'
        AND (n.end_time IS NULL OR n.end_time >= %s - INTERVAL '4 hours')
        ORDER BY n.start_time ASC;
    """

    with conn.cursor() as cur:
        cur.execute(sql, (
            flight.origin_airport_id, flight.destination_airport_id,
            flight.airline_id,
            ref_time,
            ref_time,
        ))
        rows = cur.fetchall()

    items = [
        DisruptionEventItem(
            id=r[0],
            title=r[1],
            summary=r[2],
            source=r[3],
            url=r[4],
            event_type=r[5],
            severity=r[6],
            affected_airport_code=r[7],
            affected_airline_code=r[8],
            start_time=r[9],
            end_time=r[10],
            data_source=r[11],
        )
        for r in rows
    ]

    return FlightDisruptionsResponse(
        flight_id=flight.id,
        flight_number=flight.flight_number,
        disruptions=items,
    )
