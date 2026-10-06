# FlightPulse Database Architecture

FlightPulse is an end-to-end flight delay intelligence platform. This directory houses the core relational data layer designed in PostgreSQL, supporting high-throughput historical flight storage, normalized reference entities, METAR weather observation tracking, operational news/disruption events, and flight lifecycle audits.

---

## Architecture & Entity-Relationship Overview

```
                      +-------------------+
                      |     AIRLINES      |
                      +-------------------+
                               |
                               | 1:N (ON DELETE RESTRICT)
                               v
+----------------+       +-------------------+       +--------------------+
|    AIRPORTS    |------>|      FLIGHTS      |<------|      AIRPORTS      |
|    (Origin)    | 1:N   +-------------------+  1:N  |   (Destination)    |
+----------------+                 |                 +--------------------+
        |                          | 1:N (ON DELETE CASCADE)
        | 1:N (ON DELETE CASCADE)  v
        v                +-------------------+
+--------------------+   |   FLIGHT_EVENTS   |
|WEATHER_OBSERVATIONS|   +-------------------+
+--------------------+
```

### Reference Relationships
- **`airports` & `airlines`**: Master catalog entities.
- **`flights`**: Core operational records. Each flight belongs to exactly one `airline` and connects two distinct `airports` (`origin_airport_id` and `destination_airport_id`). Both references enforce `ON DELETE RESTRICT` to protect operational integrity.
- **`weather_observations`**: Time-stamped METAR weather observations tied to specific airports (`ON DELETE CASCADE`).
- **`news_events`**: Disruption context (FAA ground stops, ATC strikes, severe weather advisories) optionally associated with affected airports or airlines (`ON DELETE SET NULL`).
- **`flight_events`**: Event-sourced audit log capturing the lifecycle progression of each flight (delays, gate changes, pushbacks, diversions).

---

## Data Dictionary & Schema Design

### 1. `airports`
Master reference table for worldwide airports with geographical coordinates and IANA timezones.
- **`id`** (`SERIAL PRIMARY KEY`): Surrogate key.
- **`iata_code`** (`VARCHAR(3) UNIQUE NOT NULL`): 3-character IATA identifier (e.g. `'JFK'`, `'ORD'`).
- **`icao_code`** (`VARCHAR(4) UNIQUE`): 4-character ICAO identifier (e.g. `'KJFK'`).
- **`name`**, **`city`**, **`state`**, **`country`**: Location descriptors (no default country assumed).
- **`latitude`**, **`longitude`**, **`elevation_ft`**: Geospatial coordinates.
- **`timezone`** (`VARCHAR(50) NOT NULL`): IANA timezone identifier (e.g. `'America/New_York'`) for local time calculations.
- **ETL fields**: `data_source`, `source_record_id`, `ingested_at`.

### 2. `airlines`
Master reference table for commercial air carriers.
- **`id`** (`SERIAL PRIMARY KEY`): Surrogate key.
- **`iata_code`** (`VARCHAR(2) UNIQUE NOT NULL`): 2-character carrier code (e.g. `'DL'`, `'AA'`).
- **`icao_code`** (`VARCHAR(3) UNIQUE`): 3-character ICAO designator (e.g. `'DAL'`).
- **`name`**, **`callsign`**, **`country`**, **`active`**: Carrier details and active operating status.
- **ETL fields**: `data_source`, `source_record_id`, `ingested_at`.

### 3. `flights`
Central fact table recording scheduled and actual flight movements and delay statistics.
- **`id`** (`BIGSERIAL PRIMARY KEY`): Surrogate identifier for high-volume historical data.
- **`flight_number`** (`VARCHAR(10) NOT NULL`): Operational flight identifier (e.g. `'DL1042'`).
- **`airline_id`**, **`origin_airport_id`**, **`destination_airport_id`**: Foreign keys with `ON DELETE RESTRICT`.
- **`flight_date`** (`DATE NOT NULL`): Departure date for partitioning and day-level aggregations.
- **`scheduled_departure`**, **`actual_departure`**, **`scheduled_arrival`**, **`actual_arrival`** (`TIMESTAMPTZ`): Stored in UTC.
- **`status`** (`VARCHAR(20)`): Enforced by check constraint (`'SCHEDULED'`, `'ACTIVE'`, `'EN_ROUTE'`, `'LANDED'`, `'CANCELLED'`, `'DIVERTED'`, `'DELAYED'`).
- **`departure_delay_minutes`**, **`arrival_delay_minutes`** (`INT`): Delay duration in minutes (positive values represent delays; negative values indicate early arrivals).
- **`delay_category`** (`VARCHAR(50)`): Source-reported delay classification from upstream systems/FAA (`'CARRIER'`, `'WEATHER'`, `'NAS'`, `'SECURITY'`, `'LATE_AIRCRAFT'`, `'OTHER'`).
- **`tail_number`**, **`aircraft_type`**, **`distance_miles`**: Equipment and route details.
- **Uniqueness constraint**: `uq_flight_instance (airline_id, flight_number, scheduled_departure)` to ensure idempotent ingestion.
- **ETL fields**: `data_source`, `source_record_id`, `ingested_at`.

### 4. `weather_observations`
Time-series METAR and station observations at airports.
- **`id`** (`BIGSERIAL PRIMARY KEY`)
- **`airport_id`** (`INT NOT NULL REFERENCES airports(id)`): Airport station location.
- **`observation_time`** (`TIMESTAMPTZ NOT NULL`): Observation epoch in UTC.
- **Atmospheric parameters**: `temperature_c`, `dewpoint_c`, `wind_speed_knots`, `wind_gust_knots`, `wind_direction_deg`, `visibility_miles`, `altimeter_inhg`, `condition_code`.
- **`raw_metar`** (`TEXT`): Preserved raw METAR telegram for auditability and parser adjustments.
- **Uniqueness constraint**: `uq_weather_station_time (airport_id, observation_time)`.
- **ETL fields**: `data_source`, `source_record_id`, `ingested_at`.

### 5. `news_events`
External operational disruptions, FAA Air Traffic Control System Command Center (ATCSCC) advisories, and weather alerts.
- **`id`** (`BIGSERIAL PRIMARY KEY`)
- **`title`**, **`summary`**, **`source`**, **`url`**: Disruption narrative and citations.
- **`event_type`**: `'GROUND_STOP'`, `'AIRPORT_OUTAGE'`, `'ATC_STRIKE'`, `'SEVERE_WEATHER_ALERT'`, `'SECURITY_INCIDENT'`, `'GENERAL_DISRUPTION'`.
- **`severity`**: `'LOW'`, `'MEDIUM'`, `'HIGH'`, `'CRITICAL'`.
- **`airport_id`**, **`airline_id`**: Optional foreign keys for targeted events.
- **`start_time`**, **`end_time`** (`TIMESTAMPTZ`): Active disruption time window.
- **ETL fields**: `data_source`, `source_record_id`, `ingested_at`.

### 6. `flight_events`
Audit trail of real-time state changes and delay progressions for each flight.
- **`id`** (`BIGSERIAL PRIMARY KEY`)
- **`flight_id`** (`BIGINT NOT NULL REFERENCES flights(id) ON DELETE CASCADE`)
- **`event_type`**: `'SCHEDULED'`, `'GATE_CHANGE'`, `'DELAY_UPDATE'`, `'TAXI_OUT'`, `'AIRBORNE'`, `'DIVERTED'`, `'LANDED'`, `'CANCELLED'`, `'OTHER'`.
- **`event_time`** (`TIMESTAMPTZ NOT NULL`): Timestamp of the event occurrence.
- **`description`** (`TEXT`): Human-readable notification or log entry.
- **`metadata`** (`JSONB NOT NULL DEFAULT '{}'`): Flexible payload capturing dynamic data (e.g. `{"gate": "C22", "revised_delay_minutes": 105}`).
- **ETL fields**: `data_source`, `source_record_id`, `ingested_at`.

---

## ETL Provenance & Idempotent Ingestion

To facilitate robust batch and streaming ETL pipelines, all core tables feature:
1. `data_source` (`VARCHAR(50)`): Identifies the origin provider (e.g. `'FLIGHTAWARE'`, `'NOAA_METAR'`, `'FAA_SWIM'`).
2. `source_record_id` (`VARCHAR(100)`): Provider's native primary key or message ID.
3. `ingested_at` (`TIMESTAMPTZ`): System timestamp when the row was loaded into PostgreSQL.

### Idempotent Upsert Pattern
With `uq_flight_instance` (`airline_id, flight_number, scheduled_departure`), pipelines can safely ingest updates without creating duplicates:

```sql
INSERT INTO flights (
    flight_number, airline_id, origin_airport_id, destination_airport_id,
    flight_date, scheduled_departure, actual_departure, scheduled_arrival,
    actual_arrival, status, departure_delay_minutes, arrival_delay_minutes,
    delay_category, data_source, source_record_id
)
VALUES (...)
ON CONFLICT (airline_id, flight_number, scheduled_departure)
DO UPDATE SET
    actual_departure = EXCLUDED.actual_departure,
    actual_arrival = EXCLUDED.actual_arrival,
    status = EXCLUDED.status,
    departure_delay_minutes = EXCLUDED.departure_delay_minutes,
    arrival_delay_minutes = EXCLUDED.arrival_delay_minutes,
    delay_category = EXCLUDED.delay_category,
    updated_at = CURRENT_TIMESTAMP;
```

---

## Analytical Views

### 1. `vw_flight_delay_summary`
Aggregates flights with airline names, origin/destination airport details, and classifies delays into standard brackets (`'ON_TIME_OR_EARLY'`, `'SLIGHT_DELAY'`, `'MODERATE_DELAY'`, `'SEVERE_DELAY'`, `'CANCELLED'`).

### 2. `vw_flight_weather_context`
Correlates flight records with the closest METAR weather observation recorded at the origin airport within $\pm 1$ hour of scheduled departure.

---

## Applying the Schema and Seed Data

### Using `psql`:
```bash
# 1. Create target database
createdb flightpulse

# 2. Run schema migration
psql -d flightpulse -f database/schema.sql

# 3. Load seed data
psql -d flightpulse -f database/seed.sql
```

### Using Docker PostgreSQL:
```bash
docker run --name flightpulse-postgres -e POSTGRES_DB=flightpulse -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:16

# Apply files
psql -h localhost -U postgres -d flightpulse -f database/schema.sql
psql -h localhost -U postgres -d flightpulse -f database/seed.sql
```

---

## Example Queries for Delay Analytics

### Average Departure Delay by Airline
```sql
SELECT 
    airline_name,
    COUNT(*) AS total_flights,
    ROUND(AVG(departure_delay_minutes), 1) AS avg_delay_min,
    COUNT(*) FILTER (WHERE departure_delay_minutes > 15) AS delayed_flights,
    ROUND(COUNT(*) FILTER (WHERE departure_delay_minutes > 15) * 100.0 / COUNT(*), 1) AS delay_rate_pct
FROM vw_flight_delay_summary
WHERE status = 'LANDED'
GROUP BY airline_name
ORDER BY avg_delay_min DESC;
```

### Origin Weather Correlation with Delayed Flights
```sql
SELECT 
    origin_iata,
    flight_number,
    departure_delay_minutes,
    condition_code,
    wind_speed_knots,
    wind_gust_knots,
    visibility_miles
FROM vw_flight_weather_context
WHERE departure_delay_minutes > 15
ORDER BY departure_delay_minutes DESC;
```
