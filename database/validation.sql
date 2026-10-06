-- ============================================================================
-- FlightPulse Database Validation Script
-- Comprehensive verification of schema, integrity constraints, triggers,
-- indexes, analytical views, and reporting queries.
-- ============================================================================

\echo '========================================================'
\echo '1. CORE TABLES EXISTENCE'
\echo '========================================================'
SELECT 
    table_name,
    table_type
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name IN ('airports', 'airlines', 'flights', 'weather_observations', 'news_events', 'flight_events')
ORDER BY table_name;

\echo '========================================================'
\echo '2. TABLE ROW COUNTS'
\echo '========================================================'
SELECT 'airports' AS table_name, COUNT(*) AS row_count FROM airports
UNION ALL
SELECT 'airlines', COUNT(*) FROM airlines
UNION ALL
SELECT 'flights', COUNT(*) FROM flights
UNION ALL
SELECT 'weather_observations', COUNT(*) FROM weather_observations
UNION ALL
SELECT 'news_events', COUNT(*) FROM news_events
UNION ALL
SELECT 'flight_events', COUNT(*) FROM flight_events;

\echo '========================================================'
\echo '3. SEED AIRPORTS VERIFICATION'
\echo '========================================================'
SELECT id, iata_code, icao_code, name, city, country, timezone 
FROM airports 
ORDER BY id;

\echo '========================================================'
\echo '4. SEED AIRLINES VERIFICATION'
\echo '========================================================'
SELECT id, iata_code, icao_code, name, callsign, country, active 
FROM airlines 
ORDER BY id;

\echo '========================================================'
\echo '5. FLIGHTS INSERTION & MAPPING VERIFICATION'
\echo '========================================================'
SELECT 
    f.id,
    f.flight_number,
    al.iata_code AS airline,
    orig.iata_code AS origin,
    dest.iata_code AS destination,
    f.flight_date,
    f.scheduled_departure,
    f.status,
    f.departure_delay_minutes,
    f.delay_category
FROM flights f
JOIN airlines al ON f.airline_id = al.id
JOIN airports orig ON f.origin_airport_id = orig.id
JOIN airports dest ON f.destination_airport_id = dest.id
ORDER BY f.id;

\echo '========================================================'
\echo '6. WEATHER OBSERVATIONS VERIFICATION'
\echo '========================================================'
SELECT 
    w.id,
    a.iata_code AS airport,
    w.observation_time,
    w.temperature_c,
    w.wind_speed_knots,
    w.wind_gust_knots,
    w.visibility_miles,
    w.condition_code
FROM weather_observations w
JOIN airports a ON w.airport_id = a.id
ORDER BY w.observation_time;

\echo '========================================================'
\echo '7. NEWS EVENTS VERIFICATION'
\echo '========================================================'
SELECT 
    n.id,
    n.title,
    n.event_type,
    n.severity,
    a.iata_code AS affected_airport,
    al.iata_code AS affected_airline,
    n.start_time,
    n.end_time
FROM news_events n
LEFT JOIN airports a ON n.airport_id = a.id
LEFT JOIN airlines al ON n.airline_id = al.id
ORDER BY n.id;

\echo '========================================================'
\echo '8. FLIGHT EVENTS & JSONB METADATA VERIFICATION'
\echo '========================================================'
SELECT 
    fe.id,
    f.flight_number,
    fe.event_type,
    fe.event_time,
    fe.description,
    fe.metadata
FROM flight_events fe
JOIN flights f ON fe.flight_id = f.id
ORDER BY fe.event_time;

\echo '========================================================'
\echo '9. CONSTRAINT VERIFICATIONS'
\echo '========================================================'

-- 9a. Test Unique Flight Constraint (Expected: Failure / Duplicate key violation)
\echo 'Testing Unique Flight Constraint (should trigger unique_violation):'
DO $$
BEGIN
    INSERT INTO flights (
        flight_number, airline_id, origin_airport_id, destination_airport_id,
        flight_date, scheduled_departure, scheduled_arrival, status
    ) VALUES (
        'DL1042', 1, 1, 5, '2026-10-04', '2026-10-04 12:00:00+00', '2026-10-04 14:15:00+00', 'SCHEDULED'
    );
    RAISE EXCEPTION 'Constraint check failed: duplicate flight was allowed!';
EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'SUCCESS: Unique flight instance constraint prevented duplicate insertion as expected.';
END $$;

-- 9b. Test Weather Uniqueness Constraint (Expected: Failure / Duplicate key violation)
\echo 'Testing Weather Uniqueness Constraint (should trigger unique_violation):'
DO $$
BEGIN
    INSERT INTO weather_observations (airport_id, observation_time, temperature_c)
    VALUES (2, '2026-10-04 13:51:00+00', 25.0);
    RAISE EXCEPTION 'Constraint check failed: duplicate weather observation was allowed!';
EXCEPTION
    WHEN unique_violation THEN
        RAISE NOTICE 'SUCCESS: Weather uniqueness constraint prevented duplicate station observation.';
END $$;

-- 9c. Test Foreign Key RESTRICT on Airlines (Expected: Cannot delete airline with active flights)
\echo 'Testing Foreign Key RESTRICT on Airlines (should prevent deletion):'
DO $$
BEGIN
    DELETE FROM airlines WHERE id = 1;
    RAISE EXCEPTION 'Constraint check failed: airline with flights was deleted!';
EXCEPTION
    WHEN foreign_key_violation THEN
        RAISE NOTICE 'SUCCESS: ON DELETE RESTRICT prevented deletion of active airline.';
END $$;

-- 9d. Test JSONB Index Existence
\echo 'Checking GIN Index on flight_events.metadata:'
SELECT 
    indexname, 
    indexdef 
FROM pg_indexes 
WHERE tablename = 'flight_events' AND indexname = 'idx_flight_events_metadata';

-- 9e. Test updated_at Trigger
\echo 'Testing updated_at trigger behavior:'
DO $$
DECLARE
    v_old_updated_at TIMESTAMPTZ;
    v_new_updated_at TIMESTAMPTZ;
BEGIN
    SELECT updated_at INTO v_old_updated_at FROM airports WHERE iata_code = 'ATL';
    
    -- Small delay to guarantee timestamp difference
    PERFORM pg_sleep(0.05);
    
    UPDATE airports SET elevation_ft = 1026 WHERE iata_code = 'ATL';
    
    SELECT updated_at INTO v_new_updated_at FROM airports WHERE iata_code = 'ATL';
    
    IF v_new_updated_at > v_old_updated_at THEN
        RAISE NOTICE 'SUCCESS: updated_at trigger automatically updated timestamp (old: %, new: %)', v_old_updated_at, v_new_updated_at;
    ELSE
        RAISE EXCEPTION 'Trigger check failed: updated_at was not advanced!';
    END IF;
END $$;

\echo '========================================================'
\echo '10. ANALYTICAL VIEWS VERIFICATION'
\echo '========================================================'
\echo 'Querying vw_flight_delay_summary:'
SELECT 
    flight_number,
    airline_iata,
    origin_iata,
    destination_iata,
    status,
    departure_delay_minutes,
    departure_delay_bracket
FROM vw_flight_delay_summary
ORDER BY flight_number;

\echo 'Querying vw_flight_weather_context:'
SELECT 
    flight_number,
    origin_iata,
    departure_delay_minutes,
    delay_category,
    weather_time,
    temperature_c,
    wind_speed_knots,
    wind_gust_knots,
    condition_code
FROM vw_flight_weather_context
ORDER BY flight_number;

\echo '========================================================'
\echo '11. ANALYTICAL CHECKS'
\echo '========================================================'

-- a. Total Flights
\echo 'a. Total Flights:'
SELECT COUNT(*) AS total_flights FROM flights;

-- b. Delayed Flights (> 15 minutes departure delay per standard FAA definition)
\echo 'b. Delayed Flights (departure_delay > 15m):'
SELECT 
    COUNT(*) AS delayed_flights_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM flights WHERE status <> 'CANCELLED'), 1) AS delay_percentage
FROM flights 
WHERE departure_delay_minutes > 15;

-- c. Average Departure Delay (for operated flights)
\echo 'c. Average Departure Delay (minutes):'
SELECT 
    ROUND(AVG(departure_delay_minutes), 2) AS avg_departure_delay_min,
    ROUND(AVG(departure_delay_minutes) FILTER (WHERE departure_delay_minutes > 15), 2) AS avg_delay_when_delayed_min
FROM flights
WHERE status IN ('LANDED', 'EN_ROUTE', 'ACTIVE');

-- d. Flights Grouped by Delay Category
\echo 'd. Flights Grouped by Delay Category:'
SELECT 
    COALESCE(delay_category, 'NONE_OR_UNSPECIFIED') AS delay_category,
    COUNT(*) AS flight_count,
    ROUND(AVG(departure_delay_minutes), 1) AS avg_delay_minutes
FROM flights
GROUP BY delay_category
ORDER BY flight_count DESC, avg_delay_minutes DESC;

-- e. Flights Grouped by Airline
\echo 'e. Flights Grouped by Airline:'
SELECT 
    al.name AS airline_name,
    al.iata_code,
    COUNT(f.id) AS total_flights,
    COUNT(f.id) FILTER (WHERE f.departure_delay_minutes > 15) AS delayed_flights,
    ROUND(AVG(f.departure_delay_minutes), 1) AS avg_departure_delay_min
FROM airlines al
LEFT JOIN flights f ON al.id = f.airline_id
GROUP BY al.id, al.name, al.iata_code
ORDER BY total_flights DESC, avg_departure_delay_min DESC;

-- f. Flights Grouped by Origin Airport
\echo 'f. Flights Grouped by Origin Airport:'
SELECT 
    orig.iata_code AS origin_airport,
    orig.name AS airport_name,
    COUNT(f.id) AS departures_count,
    COUNT(f.id) FILTER (WHERE f.departure_delay_minutes > 15) AS delayed_departures,
    ROUND(AVG(f.departure_delay_minutes), 1) AS avg_dep_delay_min
FROM airports orig
LEFT JOIN flights f ON orig.id = f.origin_airport_id
GROUP BY orig.id, orig.iata_code, orig.name
ORDER BY departures_count DESC, avg_dep_delay_min DESC;

-- g. Weather Observations Associated with Flights
\echo 'g. Weather Observations Associated with Flights (within 1h window):'
SELECT 
    f.flight_number,
    al.iata_code AS airline,
    orig.iata_code AS origin,
    f.scheduled_departure,
    f.departure_delay_minutes,
    f.status,
    wo.observation_time AS metar_time,
    wo.condition_code,
    wo.wind_speed_knots,
    wo.wind_gust_knots,
    wo.visibility_miles
FROM flights f
JOIN airlines al ON f.airline_id = al.id
JOIN airports orig ON f.origin_airport_id = orig.id
LEFT JOIN LATERAL (
    SELECT * 
    FROM weather_observations w
    WHERE w.airport_id = f.origin_airport_id
      AND w.observation_time BETWEEN f.scheduled_departure - INTERVAL '1 hour'
                                  AND f.scheduled_departure + INTERVAL '1 hour'
    ORDER BY ABS(EXTRACT(EPOCH FROM (w.observation_time - f.scheduled_departure))) ASC
    LIMIT 1
) wo ON TRUE
ORDER BY f.scheduled_departure;

-- h. News Events Associated with Affected Airports/Airlines
\echo 'h. News Events Associated with Affected Airports/Airlines:'
SELECT 
    ne.title,
    ne.event_type,
    ne.severity,
    COALESCE(a.iata_code, 'ALL') AS affected_airport,
    COALESCE(al.iata_code, 'ALL') AS affected_airline,
    ne.start_time,
    ne.end_time,
    COUNT(f.id) AS impacted_scheduled_flights
FROM news_events ne
LEFT JOIN airports a ON ne.airport_id = a.id
LEFT JOIN airlines al ON ne.airline_id = al.id
LEFT JOIN flights f ON (
    (ne.airport_id IS NOT NULL AND (f.origin_airport_id = ne.airport_id OR f.destination_airport_id = ne.airport_id))
    OR (ne.airline_id IS NOT NULL AND f.airline_id = ne.airline_id)
) AND (f.scheduled_departure BETWEEN ne.start_time - INTERVAL '1 hour' AND COALESCE(ne.end_time, CURRENT_TIMESTAMP) + INTERVAL '1 hour')
GROUP BY ne.id, ne.title, ne.event_type, ne.severity, a.iata_code, al.iata_code, ne.start_time, ne.end_time
ORDER BY ne.start_time;
