# FlightPulse Application & API Layer

This directory contains the production-style FastAPI backend and application layer for FlightPulse, exposing deterministic flight delay intelligence, weather observations, FAA disruption notices, and chronological timelines.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   React / Vite Dashboard    |
                      |   (frontend/ on :5173 or    |
                      |    FastAPI /dashboard)      |
                      +--------------+--------------+
                                     |
                                     | HTTP / JSON
                                     v
                      +-----------------------------+
                      |   FastAPI Application Layer |
                      |         (app/main.py)       |
                      +--------------+--------------+
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v                           v                           v
+-----------------+        +--------------------+       +-------------------+
| Flight Service  |        |Intelligence Service|       | Timeline Service  |
| (search/filter/ |        | (evaluates signals |       | (assembles factual|
|  weather/FAA)   |        |  via pipeline)     |       |  event progression|
+--------+--------+        +---------+----------+       +---------+---------+
         |                           |                            |
         +---------------------------+----------------------------+
                                     |
                                     v
                      +-----------------------------+
                      |   PostgreSQL 17 Database    |
                      |        `flightpulse`        |
                      +-----------------------------+
```

---

## Directory Structure

```
app/
├── database.py              # psycopg2 connection pool and dependency injection
├── main.py                  # FastAPI application entrypoint and static mount
├── README.md                # Application documentation
├── routes/
│   ├── health.py            # GET /health
│   ├── flights.py           # GET /flights, GET /flights/{flight_id}
│   ├── weather.py           # GET /flights/{flight_id}/weather
│   ├── disruptions.py       # GET /flights/{flight_id}/disruptions
│   ├── intelligence.py      # GET /flights/{flight_id}/intelligence
│   ├── timeline.py          # GET /flights/{flight_id}/timeline
│   └── ai.py                # GET /flights/{flight_id}/ai-analysis
├── schemas/
│   ├── flights.py           # Pydantic schemas for flight search and detail
│   ├── weather.py           # Schemas for atmospheric METAR observations
│   ├── disruptions.py       # Schemas for FAA advisories and ground stops
│   ├── intelligence.py      # Schemas for deterministic causal attribution
│   ├── timeline.py          # Schemas for chronological event milestones
│   └── ai.py                # Schemas for Grounded AI Analyst & fallback responses
└── services/
    ├── flight_service.py       # SQL queries for flights, weather, and notices
    ├── intelligence_service.py # Bridges API to deterministic scoring engine
    ├── timeline_service.py     # Assembles strict chronological timeline
    ├── ollama_service.py       # Local Ollama HTTP client with timeout & error handling
    └── ai_analyst.py           # Context assembly, grounded prompting & safe fallback
```

---

## REST Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check verifying database connectivity |
| `GET` | `/flights` | Search flights (filters: `airline`, `flight_number`, `origin`, `delay_status`, `date`) |
| `GET` | `/flights/{id}` | Full details for a single flight |
| `GET` | `/flights/{id}/weather` | Weather observations near departure and arrival |
| `GET` | `/flights/{id}/disruptions` | Relevant FAA advisories and ground stops |
| `GET` | `/flights/{id}/intelligence` | Deterministic delay attribution, ranked candidates, and evidence |
| `GET` | `/flights/{id}/timeline` | Factual chronological progression of events ($t_i \le t_{i+1}$) |
| `GET` | `/flights/{id}/ai-analysis` | Grounded Local AI Analyst synthesis with deterministic fallback |
| `GET` | `/docs` | Interactive OpenAPI / Swagger UI |
| `GET` | `/dashboard` | Mounted production build of the React/Vite dashboard |

---

## Grounded Local AI Analyst (Ollama)

The AI Analyst synthesizes operational findings into an executive narrative. Crucially, the **Deterministic Intelligence Engine remains the single source of truth**:

1. **Strict Prompt Grounding**:
   - The LLM is fed a factual Operational Dossier containing already-computed deterministic candidate scores, confidence levels, METAR weather, and FAA advisories.
   - System instructions prohibit hallucinating external weather phenomena, inventing causal claims, or overriding the deterministic engine's causal attribution.
2. **Graceful Degradation (No HTTP 500)**:
   - If Ollama is offline, unreachable, or times out, the endpoint returns HTTP 200 with `status: "unavailable"` and full deterministic intelligence preserved.
   - If the LLM generates invalid JSON, the endpoint falls back gracefully with `status: "error"`.
3. **Configuration**:
   - `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
   - `OLLAMA_MODEL` (default: `llama3:latest`, compatible with `tinyllama:latest` or custom models)
   - `OLLAMA_TIMEOUT_SEC` (default: `120.0`)

---

## Running the Application Locally

### 1. Start Backend API
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
API runs on `http://localhost:8000`.
Swagger docs: `http://localhost:8000/docs`.
Built dashboard: `http://localhost:8000/dashboard/`.

### 2. Start Frontend Dev Server (Optional, with HMR)
```bash
cd frontend
npm run dev
```
Development dashboard runs on `http://localhost:5173`.

### 3. Run Test Suite
```bash
python -m pytest -v tests/
```
All 63 unit and integration tests run in under 10 seconds.
