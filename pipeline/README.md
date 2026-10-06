# FlightPulse: Ingestion Pipelines (Phase 2, Phase 3, Phase 4)

This directory contains production-style Python ETL pipelines for ingesting flight operations, airport weather observations, and aviation disruption events into the FlightPulse PostgreSQL database.

---

## 1. Data Sources

### A. Flight Data: The OpenSky Network API
- **Source**: The OpenSky Network REST API (`https://opensky-network.org/api`).
- **Endpoints**: `/flights/departure` (and `/states/all`).
- **Characteristics**: Public aviation research network providing live and recent transponder-based flight tracking.
- **Access Policies**: Unauthenticated anonymous access allows querying the most recent 2 hours (up to 7,200-second window). Registered accounts (`OPENSKY_USERNAME`, `OPENSKY_PASSWORD`) permit extended historical queries up to 30 days and up to 4,000 requests/day.

### B. Weather Data: Open-Meteo API
- **Source**: Open-Meteo Weather Forecast & Historical API (`https://api.open-meteo.com/v1/forecast`).
- **Characteristics**: Open-access weather API providing global coordinate-based atmospheric data.
- **Access Policies**: Free for non-commercial and development use without requiring API keys (up to 10,000 requests/day).
- **Parameters**: Native UTC timestamps, temperature (`temperature_2m`), dewpoint (`dew_point_2m`), wind speed & gusts (`wind_speed_10m`, `wind_gusts_10m` in knots), barometric pressure (`surface_pressure`), and WMO weather condition codes.

### C. News & Disruption Events: FAA ATCSCC NAS Status Feed
- **Source**: Federal Aviation Administration (FAA) Air Traffic Control System Command Center (`https://nasstatus.faa.gov/api/airport-status-information`).
- **Characteristics**: Official US government operational feed reporting real-time ground stops, ground delay programs (GDP), airport closures, severe convective weather advisories, and runway maintenance.
- **Access Policies**: Public, open access without authentication or API keys.
- **Parameters**: Structured operational advisories, delay types, reason codes, affected airport identifiers, and start/end time windows.

---

## 2. Directory Structure

```
pipeline/
├── config.py                      # Environment-driven configuration dataclasses
├── database.py                    # PostgreSQL connection pooling & lookup caches (airports/airlines/coords)
├── extract/
│   ├── flights.py                 # OpenSky REST API client (retries, backoff, 429) & fixture loader
│   ├── news.py                    # FAA ATCSCC XML feed client & fixture loader
│   └── weather.py                 # Open-Meteo coordinate API client & fixture loader
├── fixtures/
│   ├── raw_flights_sample.json    # Sample flight payloads (on-time, delayed, cancelled, malformed, duplicates)
│   ├── raw_news_sample.json       # Sample disruption payloads (ground stops, closures, strikes, security, duplicates)
│   └── raw_weather_sample.json    # Sample weather payloads (standard, thunderstorms, conversions, duplicates)
├── load/
│   ├── flights.py                 # Parameterized PostgreSQL upserts for `flights`
│   ├── news.py                    # Parameterized PostgreSQL idempotent upserts for `news_events`
│   └── weather.py                 # Parameterized PostgreSQL upserts for `weather_observations`
├── transform/
│   ├── flights.py                 # Flight normalization, delay math, in-batch deduplication, error logging
│   ├── news.py                    # Disruption normalization, event type/severity mapping, foreign key resolution
│   └── weather.py                 # Weather normalization, unit conversions (F->C, mph/kmh->knots), WMO mapping
├── run_flight_pipeline.py         # Flight ingestion pipeline runner (CLI)
├── run_news_pipeline.py           # News & disruption ingestion pipeline runner (CLI)
├── run_weather_pipeline.py        # Weather ingestion pipeline runner (CLI)
└── README.md                      # Pipeline architecture and operational documentation
```

---

## 3. ETL Architecture & Stages

Each pipeline adheres to an **Extract $\rightarrow$ Validate $\rightarrow$ Transform $\rightarrow$ Load** lifecycle:

1. **Extract**:
   - Fetches live data from remote REST endpoints with exponential backoff and rate-limit handling (`HTTP 429`), or reads local test fixtures.
   - Raw source payloads and attribution metadata are preserved without modification.
2. **Validate & Transform**:
   - Resolves foreign keys against cached `airports` and `airlines` tables (supports airport-only, airline-only, and unmapped location events without fabricating relationships).
   - Normalizes all timestamps to timezone-aware UTC `datetime`.
   - Maps operational events to allowed database types (`'GROUND_STOP'`, `'AIRPORT_OUTAGE'`, `'ATC_STRIKE'`, `'SEVERE_WEATHER_ALERT'`, `'SECURITY_INCIDENT'`, `'GENERAL_DISRUPTION'`) and severities (`'LOW'`, `'MEDIUM'`, `'HIGH'`, `'CRITICAL'`).
   - Deduplicates records within each batch before hitting PostgreSQL.
   - Rejects malformed records with structured audit reasons.
3. **Load**:
   - Uses PostgreSQL parameterized queries (`%s`).
   - Implements idempotent persistence without duplicate creation.
   - Supports `--dry-run` to simulate processing without modifying the database.

---

## 4. How to Run the Pipelines

### Running All Unit Tests
```bash
python -m pytest -v tests/
```

### Running the Flight Pipeline
```bash
# Fixture Replay
python -m pipeline.run_flight_pipeline --source fixture

# Fixture Dry-Run
python -m pipeline.run_flight_pipeline --source fixture --dry-run

# Live OpenSky Ingestion
python -m pipeline.run_flight_pipeline --source opensky --airport KORD --hours 1
```

### Running the Weather Pipeline
```bash
# Fixture Replay
python -m pipeline.run_weather_pipeline --source fixture

# Fixture Dry-Run
python -m pipeline.run_weather_pipeline --source fixture --dry-run

# Live Open-Meteo Ingestion
python -m pipeline.run_weather_pipeline --source openmeteo --airports KORD,KATL,KDEN,KJFK
```

### Running the News & Disruption Pipeline
```bash
# Fixture Replay
python -m pipeline.run_news_pipeline --source fixture

# Fixture Dry-Run
python -m pipeline.run_news_pipeline --source fixture --dry-run

# Live FAA NAS Status Ingestion
python -m pipeline.run_news_pipeline --source faa
```

---

## 5. Flight Delay Intelligence Engine (Phase 5)

The deterministic intelligence layer analyzes flight delays against environmental weather observations, FAA operational notices, and flight lifecycle events to produce evidence-backed causal attributions.

### Core Concepts Separated
1. **Reported Delay Category**: Upstream carrier/DOT reported code (`CARRIER`, `WEATHER`, `NAS`, `LATE_AIRCRAFT`).
2. **Candidate Causes**: Inferred categories (`WEATHER`, `ATC`, `AIRPORT_DISRUPTION`, `SECURITY`, `AIRLINE_OPERATIONAL`, `UNKNOWN / INSUFFICIENT_EVIDENCE`).
3. **Supporting Evidence**: Concrete facts (e.g. observation timestamps, condition codes, wind gust magnitudes, FAA advisory durations).
4. **Confidence**: Deterministic composite score mapped to `HIGH` ($\ge 0.75$), `MEDIUM` ($0.50 - 0.74$), `LOW` ($0.25 - 0.49$), and `INSUFFICIENT` ($< 0.25$).

### Running the Intelligence Engine
```bash
# Analyze a specific flight by flight number
python -m pipeline.run_intelligence --flight UA415

# Output structured JSON
python -m pipeline.run_intelligence --flight UA415 --json

# Analyze all flights in database
python -m pipeline.run_intelligence --all

# Analyze only delayed flights (>15m)
python -m pipeline.run_intelligence --all --delayed-only
```

