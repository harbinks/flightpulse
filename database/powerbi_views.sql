-- ============================================================================
-- FlightPulse Power BI Analytical Views
-- Dedicated semantic layer views for Star-Schema modeling in Power BI
-- ============================================================================

-- 1. DimAirline: Carrier dimension
CREATE OR REPLACE VIEW vw_powerbi_dim_airlines AS
SELECT 
    id AS airline_id,
    iata_code,
    icao_code,
    name AS airline_name,
    callsign,
    country,
    active
FROM airlines;

-- 2. DimAirport: Worldwide airport dimension
CREATE OR REPLACE VIEW vw_powerbi_dim_airports AS
SELECT 
    id AS airport_id,
    iata_code,
    icao_code,
    name AS airport_name,
    city,
    state,
    country,
    latitude,
    longitude,
    elevation_ft,
    timezone,
    city || ', ' || COALESCE(state || ', ', '') || country AS location_display
FROM airports;

-- 3. DimDate: Calendar dimension for time intelligence
CREATE OR REPLACE VIEW vw_powerbi_dim_date AS
SELECT 
    datum AS date_key,
    EXTRACT(YEAR FROM datum)::INT AS year,
    'Q' || EXTRACT(QUARTER FROM datum)::TEXT AS quarter,
    EXTRACT(MONTH FROM datum)::INT AS month_num,
    TO_CHAR(datum, 'Mon') AS month_name,
    TO_CHAR(datum, 'YYYY-MM') AS year_month,
    EXTRACT(DAY FROM datum)::INT AS day_of_month,
    TO_CHAR(datum, 'Dy') AS day_of_week_short,
    EXTRACT(ISODOW FROM datum)::INT AS day_of_week_num,
    CASE WHEN EXTRACT(ISODOW FROM datum) IN (6, 7) THEN TRUE ELSE FALSE END AS is_weekend
FROM GENERATE_SERIES('2024-01-01'::DATE, '2027-12-31'::DATE, '1 day'::INTERVAL) AS datum;

-- 4. FactFlights: Core flight operations and delays
CREATE OR REPLACE VIEW vw_powerbi_fact_flights AS
SELECT 
    f.id AS flight_id,
    f.flight_number,
    f.airline_id,
    f.origin_airport_id,
    f.destination_airport_id,
    f.flight_date,
    f.scheduled_departure,
    f.actual_departure,
    f.scheduled_arrival,
    f.actual_arrival,
    f.status,
    f.departure_delay_minutes,
    f.arrival_delay_minutes,
    f.delay_category AS reported_delay_category,
    CASE 
        WHEN f.status = 'CANCELLED' THEN 'CANCELLED'
        WHEN f.departure_delay_minutes <= 0 THEN 'ON_TIME_OR_EARLY'
        WHEN f.departure_delay_minutes <= 15 THEN 'SLIGHT_DELAY (1-15m)'
        WHEN f.departure_delay_minutes <= 60 THEN 'MODERATE_DELAY (16-60m)'
        ELSE 'SEVERE_DELAY (>60m)'
    END AS departure_delay_bracket,
    CASE WHEN f.status <> 'CANCELLED' THEN 1 ELSE 0 END AS is_operated,
    CASE WHEN f.status = 'CANCELLED' THEN 1 ELSE 0 END AS is_cancelled,
    CASE WHEN f.departure_delay_minutes > 15 AND f.status <> 'CANCELLED' THEN 1 ELSE 0 END AS is_delayed_15,
    CASE WHEN f.departure_delay_minutes > 60 AND f.status <> 'CANCELLED' THEN 1 ELSE 0 END AS is_delayed_60,
    f.distance_miles,
    f.aircraft_type,
    f.tail_number,
    -- Pre-joined deterministic intelligence results if available
    fdi.primary_candidate_cause,
    fdi.confidence_level,
    fdi.confidence_score,
    fdi.primary_signal,
    fdi.explanation_summary,
    fdi.supporting_evidence_count,
    fdi.all_evidence_summary
FROM flights f
LEFT JOIN flight_delay_intelligence fdi ON f.id = fdi.flight_id;

-- 5. FactFlightIntelligence: Dedicated intelligence analysis facts
CREATE OR REPLACE VIEW vw_powerbi_fact_intelligence AS
SELECT 
    fdi.flight_id,
    fdi.flight_number,
    fdi.primary_candidate_cause,
    fdi.confidence_level,
    fdi.confidence_score,
    fdi.primary_signal,
    fdi.reported_delay_category,
    fdi.is_on_time,
    fdi.explanation_summary,
    fdi.supporting_evidence_count,
    fdi.weather_evidence,
    fdi.disruption_evidence,
    fdi.flight_event_evidence,
    fdi.all_evidence_summary,
    fdi.evaluated_at
FROM flight_delay_intelligence fdi;

-- 6. FactWeather: Meteorological observation facts
CREATE OR REPLACE VIEW vw_powerbi_fact_weather AS
SELECT 
    wo.id AS observation_id,
    wo.airport_id,
    wo.observation_time,
    wo.observation_time::DATE AS observation_date,
    wo.temperature_c,
    wo.dewpoint_c,
    wo.wind_speed_knots,
    wo.wind_gust_knots,
    wo.wind_direction_deg,
    wo.visibility_miles,
    wo.altimeter_inhg,
    wo.condition_code,
    wo.raw_metar,
    CASE WHEN wo.condition_code ILIKE '%THUNDERSTORM%' OR wo.condition_code ILIKE '%TS%' THEN 1 ELSE 0 END AS is_thunderstorm,
    CASE WHEN wo.condition_code ILIKE '%FOG%' OR wo.visibility_miles <= 1.0 THEN 1 ELSE 0 END AS is_fog,
    CASE WHEN wo.wind_speed_knots >= 25 OR wo.wind_gust_knots >= 35 THEN 1 ELSE 0 END AS is_high_wind,
    CASE WHEN wo.visibility_miles <= 3.0 THEN 1 ELSE 0 END AS is_low_visibility
FROM weather_observations wo;

-- 7. FactDisruptions: FAA advisories, ground stops, and airspace notices
CREATE OR REPLACE VIEW vw_powerbi_fact_disruptions AS
SELECT 
    ne.id AS disruption_id,
    ne.event_type,
    ne.severity,
    ne.title,
    ne.summary AS description,
    ne.airport_id,
    ne.airline_id,
    ne.start_time,
    ne.end_time,
    ne.start_time::DATE AS disruption_date,
    ROUND(EXTRACT(EPOCH FROM (ne.end_time - ne.start_time)) / 60.0, 1) AS duration_minutes,
    ne.source AS data_source
FROM news_events ne;

-- 8. FactFlightEvents: In-flight operational progression
CREATE OR REPLACE VIEW vw_powerbi_fact_flight_events AS
SELECT 
    fe.id AS event_id,
    fe.flight_id,
    fe.event_type,
    fe.event_time,
    fe.event_time::DATE AS event_date,
    fe.description,
    fe.metadata->>'gate' AS gate,
    fe.metadata->>'delay_minutes' AS delay_minutes_update,
    fe.data_source
FROM flight_events fe;

-- 9. FactTimelineUnified: Complete factual progression of events per flight
CREATE OR REPLACE VIEW vw_powerbi_fact_timeline_unified AS
SELECT 
    f.id AS flight_id,
    f.flight_number,
    f.scheduled_departure AS event_time,
    'FLIGHT' AS category,
    'SCHEDULED' AS event_type,
    'Scheduled Departure' AS title,
    'Scheduled departure from ' || orig.iata_code || ' to ' || dest.iata_code AS detail,
    'INFO' AS severity,
    'Airline Schedule' AS source
FROM flights f
JOIN airports orig ON f.origin_airport_id = orig.id
JOIN airports dest ON f.destination_airport_id = dest.id

UNION ALL

SELECT 
    fe.flight_id,
    f.flight_number,
    fe.event_time,
    'AIRLINE' AS category,
    fe.event_type,
    fe.description AS title,
    'Gate/Turnaround Update: ' || COALESCE(fe.metadata->>'gate', 'Operational') AS detail,
    'INFO' AS severity,
    fe.data_source AS source
FROM flight_events fe
JOIN flights f ON fe.flight_id = f.id

UNION ALL

SELECT 
    f.id AS flight_id,
    f.flight_number,
    wo.observation_time AS event_time,
    'WEATHER' AS category,
    wo.condition_code AS event_type,
    'METAR: ' || wo.condition_code || ' at ' || orig.iata_code AS title,
    'Temp: ' || COALESCE(wo.temperature_c::text, 'N/A') || 'C, Wind: ' || COALESCE(wo.wind_speed_knots::text, '0') || 'kts (Gust: ' || COALESCE(wo.wind_gust_knots::text, '0') || 'kts), Vis: ' || COALESCE(wo.visibility_miles::text, 'N/A') || 'mi' AS detail,
    CASE WHEN wo.condition_code ILIKE '%THUNDERSTORM%' THEN 'CRITICAL' WHEN wo.condition_code ILIKE '%RAIN%' THEN 'MEDIUM' ELSE 'LOW' END AS severity,
    'Open-Meteo METAR' AS source
FROM flights f
JOIN airports orig ON f.origin_airport_id = orig.id
JOIN weather_observations wo ON wo.airport_id = f.origin_airport_id
WHERE wo.observation_time BETWEEN f.scheduled_departure - INTERVAL '3 hours' 
                             AND COALESCE(f.actual_departure, f.scheduled_departure) + INTERVAL '1 hour'

UNION ALL

SELECT 
    f.id AS flight_id,
    f.flight_number,
    ne.start_time AS event_time,
    'ATC' AS category,
    ne.event_type,
    'FAA Notice: ' || ne.title AS title,
    ne.summary AS detail,
    ne.severity,
    ne.source AS source
FROM flights f
JOIN news_events ne ON (ne.airport_id = f.origin_airport_id OR ne.airline_id = f.airline_id)
WHERE (ne.start_time, COALESCE(ne.end_time, ne.start_time + INTERVAL '4 hours')) 
      OVERLAPS (f.scheduled_departure - INTERVAL '2 hours', COALESCE(f.actual_departure, f.scheduled_departure) + INTERVAL '2 hours')

UNION ALL

SELECT 
    f.id AS flight_id,
    f.flight_number,
    f.actual_departure AS event_time,
    'FLIGHT' AS category,
    'DEPARTED' AS event_type,
    'Actual Departure' AS title,
    'Flight departed with ' || f.departure_delay_minutes || ' minutes delay' AS detail,
    CASE WHEN f.departure_delay_minutes > 60 THEN 'CRITICAL' WHEN f.departure_delay_minutes > 15 THEN 'HIGH' ELSE 'LOW' END AS severity,
    'ATC/ACARS' AS source
FROM flights f
WHERE f.actual_departure IS NOT NULL

UNION ALL

SELECT 
    f.id AS flight_id,
    f.flight_number,
    f.actual_arrival AS event_time,
    'FLIGHT' AS category,
    'ARRIVED' AS event_type,
    'Actual Arrival' AS title,
    'Flight arrived at destination (' || dest.iata_code || ')' AS detail,
    'LOW' AS severity,
    'ATC/ACARS' AS source
FROM flights f
JOIN airports dest ON f.destination_airport_id = dest.id
WHERE f.actual_arrival IS NOT NULL;
