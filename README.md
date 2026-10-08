# FlightPulse

FlightPulse is an aviation operations and delay intelligence system that reconstructs why flights get delayed using multi-source operational data, weather observations, and National Airspace System (NAS) disruption feeds.

---

## Live Demo

- **Web Dashboard**: [https://flightpulse-psi.vercel.app/](https://flightpulse-psi.vercel.app/)
- **API Documentation**: [https://flightpulse-51i5.onrender.com/docs](https://flightpulse-51i5.onrender.com/docs)
- **Source Code**: [https://github.com/harbinks/flightpulse](https://github.com/harbinks/flightpulse)

> **Note on Deployed Behavior**: The public web deployment runs the deterministic intelligence engine in full. The optional LLM analyst uses Ollama (`llama3:latest`) and is designed to run locally; when Ollama is offline (such as on cloud container hosting), the interface presents the complete deterministic attribution and clearly reports that the local AI analyst is unavailable.

---

## What FlightPulse Does

Most flight trackers and airline apps only report a surface label: *"Delayed — 105 min"* or *"Late Inbound Aircraft."* They tell you that a delay happened, but rarely explain the operational chain of events behind it.

FlightPulse investigates the delay by cross-referencing multiple independent data sources:
- **Carrier-Reported Reason**: What the airline or dispatch system filed (e.g., `WEATHER`, `NAS`, `CARRIER`).
- **Deterministic FlightPulse Attribution**: What the evidence actually supports based on correlated weather readings, ground stops, and timing windows.
- **Supporting Evidence**: Concrete observations (wind gusts, cloud ceilings, ground stop issuance times, gate pushback records).
- **Confidence Rating**: An evidence-based rating (`HIGH`, `MEDIUM`, `LOW`, or `INSUFFICIENT`) reflecting data density and alignment.

---

## Example Investigation

Consider the benchmark scenario for **United Airlines flight UA415** from Chicago O'Hare (`ORD`) to Denver (`DEN`):

- **Scheduled Departure**: 14:30 UTC
- **Actual Departure**: 16:15 UTC
- **Departure Delay**: +105 minutes
- **Carrier-Reported Reason**: `WEATHER`

### Operational Timeline Reconstruction

```
14:00 UTC ── FAA ATCSCC issues Ground Delay Program for Chicago Center (ZAU) airspace
14:15 UTC ── FAA issues full Ground Stop for ORD departures (convective storms)
14:20 UTC ── Airline dispatch posts initial 60-minute delay citing FAA Ground Stop
14:30 UTC ── Scheduled departure time passes with aircraft holding at gate C22
14:51 UTC ── METAR KORD reports +TSRA (Thunderstorm), peak gust 42 kts, visibility 2.5 SM
15:15 UTC ── Ground stop extended; delay revised to 105 minutes
16:00 UTC ── FAA Ground Stop lifted
16:15 UTC ── UA415 pushes back from gate C22 and commences taxi (+105 min delay)
```

### Deterministic Engine Output

- **Primary Attribution**: `ATC / WEATHER INTERACTION`
- **Confidence**: `HIGH` (Score: `1.00`)
- **Ranked Candidates**:
  1. `ATC / WEATHER INTERACTION` (Score: 1.00, Confidence: HIGH)
  2. `ATC` (Score: 0.90, Confidence: HIGH)
  3. `WEATHER` (Score: 0.85, Confidence: HIGH)
- **Explanation**: Flight delay of 105 minutes strongly correlates with an Air Traffic Control restriction (Ground Stop / GDP) compounded by severe convective weather conditions at the origin airport.

*Note: FlightPulse provides evidence-based deterministic attribution and correlation, not absolute statistical proof of causality.*

---

## How It Works

```
  +--------------------------------------------------------------+
  |                        External Data                         |
  |   OpenSky (ADS-B)  ·  Open-Meteo (METAR)  ·  FAA NAS Status  |
  +-------------------------------+------------------------------+
                                  |
                                  v
  +--------------------------------------------------------------+
  |                   Python ETL Orchestrator                    |
  |     Concurrent extraction, cleaning, and foreign-key joins   |
  +-------------------------------+------------------------------+
                                  |
                                  v
  +--------------------------------------------------------------+
  |                     Supabase PostgreSQL                      |
  |   Relational tables, schema constraints, DEMO/LIVE split     |
  +-------------------------------+------------------------------+
                                  |
                                  v
  +--------------------------------------------------------------+
  |            Deterministic Intelligence Engine                 |
  |   Window proximity, threshold scoring, candidate ranking    |
  +-------------------------------+------------------------------+
                                  |
                                  v
  +--------------------------------------------------------------+
  |                      FastAPI Backend                         |
  |   REST endpoints, operations status, DEMO/LIVE isolation     |
  +-------------------------------+------------------------------+
                                  |
                                  v
  +--------------------------------------------------------------+
  |                    React / Vite Dashboard                    |
  |   Editorial aviation UI, live ribbon, interactive timeline  |
  +-------------------------------+------------------------------+
                                  |
                                  v
  +--------------------------------------------------------------+
  |                Optional Ollama Local Analyst                 |
  |   Grounded Llama 3 report (strictly uses verified facts)     |
  +--------------------------------------------------------------+
```

1. **Extraction**: Python pipeline extracts flight telemetry, airport weather, and FAA advisories.
2. **Persistence**: Validated records are stored in PostgreSQL with strict logical separation between curated demo benchmarks and live observations.
3. **Deterministic Intelligence**: Evaluates temporal windows, weather thresholds, and FAA event overlaps to produce ranked candidate causes.
4. **API Service**: FastAPI serves flight summaries, deep investigation records, weather context, and chronological timelines.
5. **Dashboard**: React interface provides operations filtering, dual DEMO/LIVE mode, and deep-dive delay analysis.
6. **Local AI Analyst**: When running locally, Ollama generates an investigative narrative grounded entirely on the deterministic evidence bundle.

---

## Data Sources

| Source | Role | Current Behavior & Practical Constraints |
| :--- | :--- | :--- |
| **OpenSky Network** | ADS-B flight transponder observations | Provides departure transponder pings. Anonymous public requests are subject to upstream IP rate limits; telemetry pings do not provide commercial timetables or delay figures, so FlightPulse never fabricates schedules when only transponder data is present. |
| **Open-Meteo** | Surface weather & METAR data | Provides temperature, dew point, wind velocity, peak gusts, cloud cover, and visibility for airport coordinates. |
| **FAA NAS Status** | Air traffic management advisories | Ingests Ground Stops, Ground Delay Programs (GDP), and severe weather alerts from the FAA Air Traffic Control System Command Center (ATCSCC). Covers US airspace. |
| **PostgreSQL Benchmark Data** | Curated historical scenarios | Controlled operational records (such as UA415) providing consistent test validation and offline demonstration capability. |

---

## Intelligence Engine

The deterministic intelligence engine is the authoritative core of FlightPulse:
- **Evidence Gathering**: Assembles all METAR weather observations and FAA NAS events occurring within relevant operational time windows before and during the flight.
- **Weather Analysis**: Checks wind velocities against operational crosswind thresholds (>25 kts), reduced visibility (<3 statute miles), and convective phenomena (thunderstorms, squalls).
- **Air Traffic Analysis**: Checks whether departure or arrival airports were subject to active FAA Ground Stops or Ground Delay Programs during the flight window.
- **Candidate Ranking**: Evaluates multiple potential explanations (`ATC / WEATHER INTERACTION`, `ATC`, `WEATHER`, `AIRLINE_OPERATIONAL`, `UNKNOWN / INSUFFICIENT_EVIDENCE`) and scores each candidate.
- **Provenance Preservation**: Preserves the carrier's reported delay reason alongside FlightPulse's attribution.

> **Key Design Rule**: The LLM is not the source of truth for causal attribution. All causal ranking and confidence scoring are performed deterministically in Python before any LLM prompt is constructed.

---

## Local AI Analyst

When running locally with Ollama:
- **Model**: `llama3:latest` running locally via Ollama.
- **Strict Grounding**: The model is prompted with structured JSON containing only verified facts (flight parameters, METAR observations, active FAA advisories, deterministic scores).
- **System Directives**: The model is strictly instructed never to invent weather conditions, fabricate delays, or contradict deterministic scores.
- **Offline Fallback**: When Ollama is not running, the application gracefully presents all deterministic intelligence, candidate breakdowns, and weather facts, clearly indicating that the local AI analyst is offline.

---

## Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 19, Vite, Lucide React, Vanilla CSS |
| **Backend** | Python 3.11, FastAPI, Pydantic v2, Uvicorn |
| **Database** | PostgreSQL 17 (Supabase) |
| **ETL & Data** | Python (`requests`, `psycopg2-binary`) |
| **Intelligence** | Deterministic rule-based scoring engine |
| **Local AI** | Ollama, Llama 3 (`llama3:latest`) |
| **Deployment** | Vercel (Frontend), Render (Backend), Supabase (Database) |

---

## Project Structure

```
flightpulse/
├── app/                           # FastAPI backend
│   ├── routes/                    # API endpoints (flights, intelligence, weather, operations)
│   ├── schemas/                   # Pydantic request/response models
│   ├── services/                  # Business logic, flight queries, Ollama analyst client
│   ├── database.py                # Database connection utilities
│   └── main.py                    # Application entrypoint & CORS configuration
├── database/                      # Relational database definitions
│   ├── schema.sql                 # PostgreSQL DDL, constraints, triggers & views
│   └── seed.sql                   # Curated benchmark datasets (airports, airlines, flights)
├── frontend/                      # React / Vite web dashboard
│   ├── src/
│   │   ├── components/            # Header, FlightList, DelayIntelligence, OperationsRibbon
│   │   ├── api.js                 # API client wrapper
│   │   ├── App.jsx                # Main layout & state management
│   │   └── App.css                # Aviation operations editorial styling
│   ├── package.json
│   └── vite.config.js
├── pipeline/                      # Data ingestion & intelligence pipelines
│   ├── extract/                   # API clients (OpenSky, Open-Meteo, FAA)
│   ├── transform/                 # Data normalizers & schema mappers
│   ├── load/                      # Idempotent PostgreSQL persistence
│   ├── intelligence/              # Deterministic delay scoring & candidate generation
│   ├── fixtures/                  # Local JSON sample data for offline testing
│   ├── config.py                  # Environment variable configuration
│   └── orchestrator.py            # Multi-source concurrent sync coordinator
├── tests/                         # Pytest test suite (103 tests)
├── init_db.py                     # Database initialization & verification script
├── requirements.txt               # Python package dependencies
└── README.md
```

---

## Running Locally

### 1. Prerequisites
- **Python**: 3.10+
- **Node.js**: 18+ and `npm`
- **PostgreSQL**: 14+ (local instance or cloud database URL)
- **Ollama** *(optional, for local LLM analyst)*: [ollama.ai](https://ollama.ai)

### 2. Clone the Repository
```bash
git clone https://github.com/harbinks/flightpulse.git
cd flightpulse
```

### 3. Backend Setup
```bash
# Create and activate a virtual environment
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On macOS/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create environment configuration
cp .env.example .env
```

Configure your database connection in `.env`:
```env
DATABASE_URL=postgresql://postgres:password@localhost:5432/flightpulse
```

### 4. Initialize Database
Run the idempotent database setup script to apply the schema and seed benchmark records:
```bash
python init_db.py
```

### 5. Frontend Setup
```bash
cd frontend
npm install
cd ..
```

### 6. Start Development Servers

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

*(Optional) Start Ollama for local LLM analyst narratives:*
```bash
ollama run llama3:latest
```

---

## Testing

The codebase has an automated test suite verifying data transformation, intelligence scoring, API endpoints, and orchestrator fault isolation:

```bash
# Run backend test suite (103 tests)
python -m pytest tests/

# Run frontend linting
cd frontend
npm run lint

# Verify frontend production build
npm run build
```

**Validated Test Status**:
- **103 / 103 Python backend tests passing** across all pipeline, intelligence, API, and orchestration modules.
- **Frontend linter clean** (`oxlint` reported 0 errors and 0 warnings).
- **Production bundle verified** via Vite.

---

## Deployment

The public architecture is deployed across three services:

- **Frontend**: [Vercel](https://flightpulse-psi.vercel.app/) — React/Vite single-page application.
- **Backend**: [Render](https://flightpulse-51i5.onrender.com) — FastAPI application running in Python web service.
- **Database**: [Supabase](https://supabase.com) — Managed PostgreSQL database.

*Note: Render's free tier spins down web services after periods of inactivity. Initial requests after dormancy may take 30–60 seconds while the backend instance spins up.*

---

## Current Limitations

1. **Local-Only LLM**: Ollama and Llama 3 run locally; the public Render deployment relies on the deterministic engine and transparently displays an offline indicator for the AI narrative.
2. **OpenSky Rate Limiting**: Anonymous public calls to OpenSky are subject to upstream IP quotas. The pipeline reports `RATE_LIMITED` gracefully rather than breaking.
3. **Telemetry vs. Schedule Semantics**: Live ADS-B observations record aircraft presence, not commercial timetables. FlightPulse does not fabricate scheduled times or delay minutes for telemetry-only observations.
4. **Geographic Coverage**: FAA ATCSCC disruption advisories are US-centric.
5. **Inference vs. Absolute Causality**: Deterministic attributions are evidence-based correlations, not absolute physical or operational proof.
6. **Free-Tier Cold Starts**: Render hosting may take up to a minute to awaken on first load.

---

## Roadmap

- [ ] Authenticated live flight data feeds with higher request allowances.
- [ ] Broader global coverage for international air traffic management advisories.
- [ ] Persistent time-series telemetry storage for multi-week historical delay trending.
- [ ] Tail-number rotation analysis to trace inbound aircraft turnaround cascades.
- [ ] Optional cloud-hosted LLM endpoint for production analyst generation.
- [ ] Refined causal score calibration against historical DOT/BTS delay data.
- [ ] Automated monitoring and alert notifications for critical ground stops.
