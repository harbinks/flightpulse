-- ============================================================================
-- FlightPulse Database Schema
-- Production-style flight delay intelligence platform schema
-- ============================================================================

-- Ensure standard extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 1. Helper Functions & Triggers
-- ============================================================================

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 2. Core Tables
-- ============================================================================

-- ----------------------------------------------------------------------------
-- AIRPORTS
-- Reference table for worldwide airport metadata, locations, and timezones
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS airports (
    id SERIAL PRIMARY KEY,
    iata_code VARCHAR(3) NOT NULL UNIQUE,
    icao_code VARCHAR(4) UNIQUE,
    name VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(100),
    country VARCHAR(100) NOT NULL,
    latitude NUMERIC(9,6) NOT NULL,
    longitude NUMERIC(9,6) NOT NULL,
    elevation_ft INT,
    timezone VARCHAR(50) NOT NULL, -- IANA timezone (e.g. 'America/New_York')
    
    -- ETL Provenance
    data_source VARCHAR(50),
    source_record_id VARCHAR(100),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_airports_iata_format CHECK (iata_code ~ '^[A-Z0-9]{3}$'),
    CONSTRAINT chk_airports_lat_range CHECK (latitude BETWEEN -90.0 AND 90.0),
    CONSTRAINT chk_airports_lon_range CHECK (longitude BETWEEN -180.0 AND 180.0)
);

CREATE TRIGGER trg_airports_updated_at
    BEFORE UPDATE ON airports
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

-- ----------------------------------------------------------------------------
-- AIRLINES
-- Reference table for commercial air carrier operators
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS airlines (
    id SERIAL PRIMARY KEY,
    iata_code VARCHAR(2) NOT NULL UNIQUE,
    icao_code VARCHAR(3) UNIQUE,
    name VARCHAR(255) NOT NULL,
    callsign VARCHAR(100),
    country VARCHAR(100),
    active BOOLEAN NOT NULL DEFAULT TRUE,

    -- ETL Provenance
    data_source VARCHAR(50),
    source_record_id VARCHAR(100),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_airlines_iata_format CHECK (iata_code ~ '^[A-Z0-9]{2}$')
);

CREATE TRIGGER trg_airlines_updated_at
    BEFORE UPDATE ON airlines
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

-- ----------------------------------------------------------------------------
-- FLIGHTS
-- Core flight schedules, actual operations, and delay metrics
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flights (
    id BIGSERIAL PRIMARY KEY,
    flight_number VARCHAR(10) NOT NULL,
    airline_id INT NOT NULL REFERENCES airlines(id) ON DELETE RESTRICT,
    origin_airport_id INT NOT NULL REFERENCES airports(id) ON DELETE RESTRICT,
    destination_airport_id INT NOT NULL REFERENCES airports(id) ON DELETE RESTRICT,
    
    flight_date DATE NOT NULL,
    scheduled_departure TIMESTAMPTZ, -- Nullable for live ADS-B telemetry observations lacking published timetables
    actual_departure TIMESTAMPTZ,
    scheduled_arrival TIMESTAMPTZ,   -- Nullable for live ADS-B telemetry observations
    actual_arrival TIMESTAMPTZ,

    status VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED',
    departure_delay_minutes INT DEFAULT 0,
    arrival_delay_minutes INT DEFAULT 0,
    
    -- Source-reported delay category (FAA/DOT classifications: CARRIER, WEATHER, NAS, SECURITY, LATE_AIRCRAFT)
    delay_category VARCHAR(50),
    
    tail_number VARCHAR(20),
    aircraft_type VARCHAR(20),
    distance_miles NUMERIC(8,2),

    -- ETL Provenance
    data_source VARCHAR(50),
    source_record_id VARCHAR(100),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_flight_instance UNIQUE (airline_id, flight_number, scheduled_departure),
    CONSTRAINT chk_flights_airports_distinct CHECK (origin_airport_id <> destination_airport_id),
    CONSTRAINT chk_flights_status CHECK (
        status IN ('SCHEDULED', 'ACTIVE', 'EN_ROUTE', 'LANDED', 'CANCELLED', 'DIVERTED', 'DELAYED')
    ),
    CONSTRAINT chk_flights_delay_category CHECK (
        delay_category IS NULL OR delay_category IN ('CARRIER', 'WEATHER', 'NAS', 'SECURITY', 'LATE_AIRCRAFT', 'OTHER')
    )
);

CREATE TRIGGER trg_flights_updated_at
    BEFORE UPDATE ON flights
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

-- ----------------------------------------------------------------------------
-- WEATHER_OBSERVATIONS
-- High-frequency weather observations (METARs) tied to airports
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_observations (
    id BIGSERIAL PRIMARY KEY,
    airport_id INT NOT NULL REFERENCES airports(id) ON DELETE CASCADE,
    observation_time TIMESTAMPTZ NOT NULL,
    
    temperature_c NUMERIC(4,1),
    dewpoint_c NUMERIC(4,1),
    wind_speed_knots NUMERIC(5,1),
    wind_gust_knots NUMERIC(5,1),
    wind_direction_deg INT,
    visibility_miles NUMERIC(5,2),
    altimeter_inhg NUMERIC(5,2),
    condition_code VARCHAR(50),
    raw_metar TEXT,

    -- ETL Provenance
    data_source VARCHAR(50),
    source_record_id VARCHAR(100),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT uq_weather_station_time UNIQUE (airport_id, observation_time),
    CONSTRAINT chk_weather_wind_deg CHECK (wind_direction_deg IS NULL OR wind_direction_deg BETWEEN 0 AND 360)
);

-- ----------------------------------------------------------------------------
-- NEWS_EVENTS
-- Disruptions, NOTAMs, weather alerts, strikes, and FAA ground stops
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_events (
    id BIGSERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    source VARCHAR(100),
    url TEXT,
    event_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'MEDIUM',
    
    airport_id INT REFERENCES airports(id) ON DELETE SET NULL,
    airline_id INT REFERENCES airlines(id) ON DELETE SET NULL,
    
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,

    -- ETL Provenance
    data_source VARCHAR(50),
    source_record_id VARCHAR(100),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    CONSTRAINT chk_news_severity CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    CONSTRAINT chk_news_event_type CHECK (
        event_type IN ('GROUND_STOP', 'AIRPORT_OUTAGE', 'ATC_STRIKE', 'SEVERE_WEATHER_ALERT', 'SECURITY_INCIDENT', 'GENERAL_DISRUPTION')
    ),
    CONSTRAINT chk_news_time_window CHECK (end_time IS NULL OR end_time >= start_time)
);

CREATE TRIGGER trg_news_events_updated_at
    BEFORE UPDATE ON news_events
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

-- ----------------------------------------------------------------------------
-- FLIGHT_EVENTS
-- Lifecycle progression, gate changes, and delay updates over time
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS flight_events (
    id BIGSERIAL PRIMARY KEY,
    flight_id BIGINT NOT NULL REFERENCES flights(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    description TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- ETL Provenance
    data_source VARCHAR(50),
    source_record_id VARCHAR(100),
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_flight_event_type CHECK (
        event_type IN ('SCHEDULED', 'GATE_CHANGE', 'DELAY_UPDATE', 'TAXI_OUT', 'AIRBORNE', 'DIVERTED', 'LANDED', 'CANCELLED', 'OTHER')
    )
);

-- ============================================================================
-- 3. Indexes for Query Performance & Analytical Filtering
-- ============================================================================

-- Airports & Airlines Indexes
CREATE INDEX IF NOT EXISTS idx_airports_iata ON airports (iata_code);
CREATE INDEX IF NOT EXISTS idx_airports_city ON airports (city);
CREATE INDEX IF NOT EXISTS idx_airlines_iata ON airlines (iata_code);

-- Flights Indexes
CREATE INDEX IF NOT EXISTS idx_flights_origin_sched_dep 
    ON flights (origin_airport_id, scheduled_departure);

CREATE INDEX IF NOT EXISTS idx_flights_dest_sched_arr 
    ON flights (destination_airport_id, scheduled_arrival);

CREATE INDEX IF NOT EXISTS idx_flights_airline_date 
    ON flights (airline_id, flight_date);

CREATE INDEX IF NOT EXISTS idx_flights_status 
    ON flights (status);

CREATE INDEX IF NOT EXISTS idx_flights_flight_number_date
    ON flights (flight_number, flight_date);

-- Partial index for delayed flight analytics (>15 min FAA threshold)
CREATE INDEX IF NOT EXISTS idx_flights_delayed_dep 
    ON flights (departure_delay_minutes) 
    WHERE departure_delay_minutes > 15;

-- ETL lookup index for deduplication and idempotent upserts
CREATE INDEX IF NOT EXISTS idx_flights_source_rec 
    ON flights (data_source, source_record_id);

-- Live transponder deduplication index (OPENSKY_LIVE only)
CREATE UNIQUE INDEX IF NOT EXISTS uq_live_flight_tail_dep
    ON flights (tail_number, actual_departure)
    WHERE data_source = 'OPENSKY_LIVE' AND tail_number IS NOT NULL AND actual_departure IS NOT NULL;

-- Weather Observations Indexes
CREATE INDEX IF NOT EXISTS idx_weather_airport_time 
    ON weather_observations (airport_id, observation_time DESC);

CREATE INDEX IF NOT EXISTS idx_weather_condition 
    ON weather_observations (condition_code);

-- News Events Indexes
CREATE INDEX IF NOT EXISTS idx_news_airport_time 
    ON news_events (airport_id, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_news_airline_time 
    ON news_events (airline_id, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_news_timerange 
    ON news_events (start_time, end_time);

CREATE INDEX IF NOT EXISTS idx_news_type_severity 
    ON news_events (event_type, severity);

-- Flight Events Indexes
CREATE INDEX IF NOT EXISTS idx_flight_events_flight_time 
    ON flight_events (flight_id, event_time DESC);

CREATE INDEX IF NOT EXISTS idx_flight_events_type 
    ON flight_events (event_type);

-- GIN index for JSONB metadata querying
CREATE INDEX IF NOT EXISTS idx_flight_events_metadata 
    ON flight_events USING gin (metadata);

-- ============================================================================
-- 4. Analytical Views for Reporting & AI Context Retrieval
-- ============================================================================

-- Comprehensive flight performance summary with delay classifications
CREATE OR REPLACE VIEW vw_flight_delay_summary AS
SELECT 
    f.id AS flight_id,
    f.flight_number,
    f.flight_date,
    al.name AS airline_name,
    al.iata_code AS airline_iata,
    orig.iata_code AS origin_iata,
    orig.name AS origin_airport_name,
    orig.city AS origin_city,
    dest.iata_code AS destination_iata,
    dest.name AS destination_airport_name,
    dest.city AS destination_city,
    f.scheduled_departure,
    f.actual_departure,
    f.scheduled_arrival,
    f.actual_arrival,
    f.status,
    f.departure_delay_minutes,
    f.arrival_delay_minutes,
    f.delay_category,
    CASE 
        WHEN f.status = 'CANCELLED' THEN 'CANCELLED'
        WHEN f.status = 'DIVERTED' THEN 'DIVERTED'
        WHEN f.departure_delay_minutes <= 0 THEN 'ON_TIME_OR_EARLY'
        WHEN f.departure_delay_minutes <= 15 THEN 'SLIGHT_DELAY'
        WHEN f.departure_delay_minutes <= 45 THEN 'MODERATE_DELAY'
        ELSE 'SEVERE_DELAY'
    END AS departure_delay_bracket,
    f.distance_miles,
    f.aircraft_type,
    f.tail_number
FROM flights f
JOIN airlines al ON f.airline_id = al.id
JOIN airports orig ON f.origin_airport_id = orig.id
JOIN airports dest ON f.destination_airport_id = dest.id;

-- View correlating flights with closest origin weather observation within +/- 1 hour
CREATE OR REPLACE VIEW vw_flight_weather_context AS
SELECT 
    f.id AS flight_id,
    f.flight_number,
    f.flight_date,
    f.departure_delay_minutes,
    f.delay_category,
    orig.iata_code AS origin_iata,
    w.observation_time AS weather_time,
    w.temperature_c,
    w.wind_speed_knots,
    w.wind_gust_knots,
    w.visibility_miles,
    w.condition_code,
    w.raw_metar
FROM flights f
JOIN airports orig ON f.origin_airport_id = orig.id
LEFT JOIN LATERAL (
    SELECT *
    FROM weather_observations wo
    WHERE wo.airport_id = f.origin_airport_id
      AND wo.observation_time BETWEEN f.scheduled_departure - INTERVAL '1 hour' 
                                  AND f.scheduled_departure + INTERVAL '1 hour'
    ORDER BY ABS(EXTRACT(EPOCH FROM (wo.observation_time - f.scheduled_departure))) ASC
    LIMIT 1
) w ON TRUE;

-- ============================================================================
-- 5. Operations Sync Audit Table
-- ============================================================================
CREATE TABLE IF NOT EXISTS operations_sync_log (
    id SERIAL PRIMARY KEY,
    sync_source VARCHAR(50) NOT NULL,
    sync_status VARCHAR(20) NOT NULL,
    records_extracted INT DEFAULT 0,
    records_inserted INT DEFAULT 0,
    records_updated INT DEFAULT 0,
    error_message TEXT,
    duration_ms NUMERIC(9,2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
