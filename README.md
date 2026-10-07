# FlightPulse

### Understanding why flights get delayed — with data, evidence, and grounded AI.

I built FlightPulse because flight delays are usually explained with a single label — weather, carrier, late aircraft, etc. — even though the real operational picture is often more complicated. 

When your flight sits on the tarmac for two hours, the airline app might simply say "Late Inbound Aircraft." But why was that inbound aircraft late? Did convective thunderstorms at Chicago O'Hare trigger an FAA Ground Delay Program? Did crosswinds exceed runway operating limits? Or was there an ATC staffing ground stop?

FlightPulse is an aviation intelligence platform that ingests live and historical flight telemetry, high-resolution airport weather observations, and National Airspace System (NAS) disruption notices. It feeds them through a deterministic intelligence engine to deduce candidate causes, evaluate supporting evidence, calculate confidence tiers, and then uses a local, grounded AI analyst to explain the operational chain of events — without hallucinating facts.

---

## Architecture Overview

FlightPulse is structured around strict data provenance and causal attribution:

```
                      +-----------------------------------------+
                      |               External Feeds            |
                      |  - OpenSky Network (ADS-B Telemetry)    |
                      |  - Open-Meteo (METAR / Atmospheric)     |
                      |  - FAA NAS Status (Ground Stops / GDP)  |
                      +--------------------+--------------------+
                                           |
                                           v
                      +-----------------------------------------+
                      |         Python ETL Orchestrator         |
                      |   (Fault-isolated concurrent branches)  |
                      +--------------------+--------------------+
                                           |
                                           v
                      +-----------------------------------------+
                      |           PostgreSQL Database           |
                      | (Relational store with DEMO/LIVE split) |
                      +--------------------+--------------------+
                                           |
                                           v
                      +-----------------------------------------+
                      | Deterministic Delay Intelligence Engine |
                      |    (Scoring, Candidates & Attribution)  |
                      +--------------------+--------------------+
                                           |
                                           v
                      +-----------------------------------------+
                      |            FastAPI API Layer            |
                      |    (REST Endpoints, Operations Audit)   |
                      +--------------------+--------------------+
                                           |
                                           v
                      +-----------------------------------------+
                      |         React / Vite Dashboard          |
                      |   (Dual-mode: DEMO vs LIVE telemetry)   |
                      +--------------------+--------------------+
                                           |
                                           v
                      +-----------------------------------------+
                      |      Ollama Local AI Analyst (LLM)      |
                      | (Strictly grounded on structured facts) |
                      +-----------------------------------------+
```

---

## Why This Project Matters

FlightPulse is an end-to-end engineering demonstration of:
- **Resilient Data Pipelines**: Multi-source Python ETL with fault isolation, bounded exponential backoff, rate-limit awareness, and idempotent upserts.
- **Data Provenance & Integrity**: Strict separation between curated benchmark scenarios (`DEMO`, `FLIGHTAWARE`, `FIXTURE_REPLAY`) and raw observations (`OPENSKY_LIVE`).
- **Telemetry Semantics**: Never fabricating commercial flight schedules or delay minutes when only raw transponder pings exist.
- **Deterministic-First AI**: A rule-based scoring and candidate generation engine acts as the authoritative source of truth. The LLM explains the evidence rather than inventing it.
- **Production-Grade Full Stack**: High-throughput PostgreSQL data models, performant FastAPI asynchronous endpoints, and a responsive editorial-style React operations dashboard.

---

## Core System Capabilities

### 1. Multi-Source Ingestion & Fault Isolation
- **OpenSky Network REST API**: ADS-B transponder telemetry for airport departures.
- **Open-Meteo API**: Coordinate-based surface weather observations including temperature, dew point, wind speed, gust velocities, visibility, surface pressure, and WMO weather codes.
- **FAA ATCSCC Feed**: Real-time National Airspace System advisories, ground stops, ground delay programs (GDP), and airport arrival acceptance rates.
- **Fault-Isolated Orchestration**: The orchestrator runs these pipelines concurrently. If one external service fails or is rate-limited, the other sources continue and complete normally.

### 2. Deterministic Flight Delay Intelligence Engine
Instead of asking an AI model to guess why a flight was delayed, the deterministic engine runs verifiable heuristics:
- **Correlated Weather Assessment**: Checks wind speed against operational crosswind thresholds (>25 kts), visibility limitations (<3 miles), and convective thunderstorms.
- **NAS Disruption Cross-Referencing**: Correlates active ground stops and ground delay programs overlapping departure/arrival time windows.
- **Carrier & Turnaround Signals**: Evaluates turnaround buffers and aircraft arrival delays.
- **Attribution Tiers**: Assigns primary candidate causes (e.g., `ATC / WEATHER INTERACTION`, `SEVERE_WEATHER`, `CARRIER_LOGISTICS`) with explicit confidence ratings (`HIGH`, `MEDIUM`, `LOW`).

### 3. Grounded Local AI Analyst
- Integrates with local **Ollama (`llama3:latest`)**.
- Uses structured prompts containing only the verified evidence bundle (flight details, METAR readings, FAA events, candidate breakdown).
- Guided by strict system constraints: no invented weather, no hallucinated airline reasons, and honest explanations when evidence is insufficient.

### 4. DEMO Mode vs. LIVE Operations Mode
- **DEMO Mode**: Runs against a curated benchmark dataset (including benchmark scenario `UA415` departing KORD during severe convective weather and ground stops). Ensures repeatable, reliable demonstrations and automated test verification.
- **LIVE Operations Mode**: Switched via the top navigation bar. Pulls real ADS-B telemetry, live METAR weather, and active FAA advisories with dedicated operational freshness indicators in the live ribbon.

---

## Live Data Status & Upstream Rate Limiting

FlightPulse is built to handle real-world aviation APIs honestly:
- The live pipeline accepts real OpenSky ADS-B observations.
- Unknown regional airlines or unseeded destination airports are stored with `airline_id = NULL` or `destination_airport_id = NULL` rather than fabricating dummy entities.
- Commercial schedules, delay minutes, and delay categories are left `NULL` for telemetry-only observations.
- **Upstream Rate Limit Note**: During project validation, the unauthenticated anonymous OpenSky API tier returned `HTTP 429: Too Many Requests` (`X-Rate-Limit-Retry-After-Seconds: ~80603s`, indicating ~22.4 hours remaining on the shared anonymous IP quota).
- Rather than manufacturing fake live data, FlightPulse handles this transparently:
  - The orchestrator traps `OpenSkyRateLimitError` and logs `RATE_LIMITED`.
  - Operations sync status reports `PARTIAL` (weather and FAA feeds succeeded).
  - The live UI displays `OPENSKY ● RATE LIMITED` and `OPERATIONAL STATUS: PARTIAL`.
- Supplying authenticated OpenSky credentials (`OPENSKY_USERNAME`, `OPENSKY_PASSWORD`) or running after quota reset immediately enables full live ingestion.

---

## Tech Stack

| Domain | Technologies |
| :--- | :--- |
| **Backend & API** | Python 3.11, FastAPI, Pydantic v2, Uvicorn |
| **Database** | PostgreSQL (relational schema, partial unique indexes, foreign key lookups) |
| **ETL & Data** | Python (`requests`, `psycopg2-binary`), OpenSky REST API, Open-Meteo, FAA ATCSCC |
| **Intelligence** | Deterministic causal heuristics, weighted scoring, multi-candidate ranking |
| **AI Layer** | Ollama local inference (`llama3:latest`), structured grounding prompts |
| **Frontend** | React 19, Vite, Lucide React, Space Mono & Inter typography |
| **Testing & Quality** | Pytest, oxlint, Vite production build |

---

## Validated Engineering Metrics

- **103 Automated Tests Passed** (`pytest tests/`, 0 failures, 100% passing across ETL, intelligence, API, and orchestrator).
- **Frontend Code Quality**: `0 warnings and 0 errors` via `oxlint`.
- **Production Build**: Built cleanly with Vite in under 1 second.
- **13 Controlled Demo Records**: Retained in PostgreSQL with absolute DEMO/LIVE logical isolation.
- **0 Fabricated Telemetry Records**: Zero synthetic records generated during upstream rate limits.
- **UA415 Benchmark Integrity**: Validated with `105 min` weather delay and `ATC / WEATHER INTERACTION (HIGH)` deterministic attribution.

---

## Directory Structure

```
flightpulse/
├── app/                           # FastAPI Backend
│   ├── routes/                    # API endpoints (flights, intelligence, weather, disruptions, operations)
│   ├── schemas/                   # Pydantic validation schemas
│   ├── services/                  # Business logic & Ollama analyst client
│   ├── database.py                # Connection pool provider
│   └── main.py                    # Application entrypoint & static mount
├── database/                      # PostgreSQL DDL & Seed Scripts
│   ├── schema.sql                 # Complete relational schema & indexes
│   └── seed.sql                   # Curated airports, airlines, and demo flights
├── frontend/                      # React / Vite Operations Dashboard
│   ├── src/
│   │   ├── components/            # Header, FlightList, FlightHeader, OperationsRibbon, etc.
│   │   ├── api.js                 # API client wrapper
│   │   ├── App.jsx                # Main application view & workspace
│   │   └── App.css                # Aviation operations editorial styling
│   ├── package.json
│   └── vite.config.js
├── pipeline/                      # Ingestion & Intelligence Pipelines
│   ├── extract/                   # API clients (OpenSky, Open-Meteo, FAA)
│   ├── transform/                 # Data cleaners, normalizers & dual-branch parser
│   ├── load/                      # Idempotent PostgreSQL upsert operations
│   ├── intelligence/              # Deterministic delay scoring & candidate generator
│   ├── fixtures/                  # Local JSON fixtures for offline testing
│   ├── config.py                  # Environment configuration
│   └── orchestrator.py            # Concurrent multi-source coordinator
├── tests/                         # Comprehensive Pytest Suite (103 tests)
├── .env.example                   # Template environment configuration
├── .gitignore                     # Environment & credential protection
└── requirements.txt               # Python package dependencies
```

---

## Quickstart & Local Setup

### 1. Prerequisites
- **Python**: 3.10+
- **Node.js**: 18+ and `npm`
- **PostgreSQL**: 14+ running locally
- **Ollama** (optional, for local AI analyst): [ollama.ai](https://ollama.ai)

### 2. Clone Repository
```bash
git clone https://github.com/harbinks/flightpulse.git
cd flightpulse
```

### 3. Backend Setup
```bash
# Create and activate virtual environment
python -m venv .venv
# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
# source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your local PostgreSQL credentials
```

### 4. Database Setup
```bash
# Create database and apply schema and seed data
createdb flightpulse
psql -d flightpulse -f database/schema.sql
psql -d flightpulse -f database/seed.sql
```

### 5. Frontend Setup
```bash
cd frontend
npm install
cd ..
```

### 6. Run the Application
In terminal 1 (FastAPI backend):
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

In terminal 2 (React frontend):
```bash
cd frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

*(Optional) Start Ollama for local grounded analysis:*
```bash
ollama run llama3:latest
```

---

## Deployment Architecture

FlightPulse is architected for cloud-native zero-downtime deployment:

```
                      +-----------------------------+
                      |       Vercel Hosting        |
                      |    (React / Vite SPA Frontend)
                      +--------------+--------------+
                                     |
                                     | HTTPS / JSON
                                     v
                      +-----------------------------+
                      |        Render Hosting       |
                      |   (FastAPI / Python Web App)|
                      +--------------+--------------+
                                     |
                                     | PostgreSQL TCP
                                     v
                      +-----------------------------+
                      |     Managed PostgreSQL      |
                      |  (Render / Supabase / Neon) |
                      +-----------------------------+
```

### 1. Database Provisioning
Run `python init_db.py` with your remote database's connection string:
```bash
DATABASE_URL="postgres://user:password@hostname:5432/dbname" python init_db.py
```
This automatically applies `database/schema.sql` and loads the baseline benchmark flights from `database/seed.sql` while preserving DEMO/LIVE provenance isolation.

### 2. Render Backend Web Service
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `DATABASE_URL`: Managed PostgreSQL connection string.
  - `CORS_ORIGINS`: Your Vercel frontend URL (e.g. `https://flightpulse.vercel.app`).
  - `PORT`: Automatically assigned by Render.

### 3. Vercel Frontend Deployment
- **Framework Preset**: Vite
- **Root Directory**: `frontend`
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Environment Variables**:
  - `VITE_API_BASE_URL`: Your Render backend service URL (e.g. `https://flightpulse.onrender.com`).
- **SPA Rewrites**: Pre-configured in [`frontend/vercel.json`](frontend/vercel.json).

### 4. Local AI Analyst in Production
- Ollama is designed for local and self-hosted environments.
- In production, when Ollama is not deployed to the cloud container, FlightPulse gracefully activates its deterministic intelligence fallback.
- The UI transparently notes that the local AI model is offline while delivering 100% of the deterministic flight delay attribution, candidate breakdown, and correlated weather facts without error.

---

## Key API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Application and PostgreSQL health status |
| `GET` | `/flights?mode=demo` | Retrieve curated benchmark flights |
| `GET` | `/flights?mode=live` | Retrieve live ADS-B flights |
| `GET` | `/flights/{id}` | Flight details, aircraft type, and route info |
| `GET` | `/flights/{id}/intelligence` | Deterministic delay attribution & candidate scores |
| `GET` | `/flights/{id}/weather` | Correlated surface METAR observations |
| `GET` | `/flights/{id}/disruptions` | Correlated FAA ground stops and NAS programs |
| `GET` | `/flights/{id}/ai-analysis` | Grounded Ollama LLM investigation report |
| `GET` | `/operations/status` | Ingestion health, sync audit, and rate-limit status |
| `POST` | `/operations/sync?mode=live` | Trigger on-demand multi-feed synchronization |

---

## Running Verification Tests

```bash
# Run complete Python test suite
python -m pytest tests/

# Run frontend linting
cd frontend
npm run lint

# Run frontend production build
npm run build
```

---

## What I Learned Building FlightPulse

1. **ADS-B Telemetry is Not a Commercial Schedule**: An ADS-B observation gives you a transponder ping and a departure timestamp. It does not give you scheduled gate departure, commercial flight number, or delay reason. Conflating the two creates false data; keeping them separate keeps your system honest.
2. **Grounding LLMs Requires Deterministic Boundaries**: Letting an LLM deduce flight delay causes directly from raw numbers leads to subtle hallucinations. Generating deterministic scores first and forcing the model to synthesize only confirmed facts produces dependable, production-ready analysis.
3. **External API Quotas Must Be First-Class Citizens**: Rather than treating an HTTP 429 as a catastrophic failure, modeling rate-limited states explicitly in the database, API, and UI keeps operators informed without breaking system integrity.
