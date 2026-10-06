/**
 * FlightPulse Frontend API Client.
 * Connects to the FastAPI backend layer and provides typed, structured methods
 * for querying flight directory records, deterministic delay attribution,
 * chronological timelines, weather telemetry, and the grounded Ollama AI analyst.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Handle HTTP response and parse JSON.
 */
async function handleResponse(response, context) {
  if (!response.ok) {
    const errorText = await response.text().catch(() => '');
    throw new Error(`${context} failed (HTTP ${response.status}): ${errorText || response.statusText}`);
  }
  return response.json();
}

export async function fetchHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return await handleResponse(res, 'Health check');
  } catch (err) {
    return { status: 'unreachable', database: 'disconnected', error: err.message };
  }
}

export async function fetchFlights({ flightNumber = '', origin = '', delayStatus = '', limit = 50 } = {}) {
  const params = new URLSearchParams();
  if (flightNumber) params.append('flight_number', flightNumber.trim());
  if (origin) params.append('origin', origin.trim().toUpperCase());
  if (delayStatus) params.append('delay_status', delayStatus);
  params.append('limit', String(limit));

  const res = await fetch(`${API_BASE}/flights?${params.toString()}`);
  return handleResponse(res, 'Fetch flights');
}

export async function fetchFlightDetail(id) {
  const res = await fetch(`${API_BASE}/flights/${id}`);
  return handleResponse(res, `Fetch flight ${id}`);
}

export async function fetchFlightIntelligence(id) {
  const res = await fetch(`${API_BASE}/flights/${id}/intelligence`);
  return handleResponse(res, `Fetch intelligence for flight ${id}`);
}

export async function fetchFlightTimeline(id) {
  const res = await fetch(`${API_BASE}/flights/${id}/timeline`);
  return handleResponse(res, `Fetch timeline for flight ${id}`);
}

export async function fetchFlightWeather(id) {
  const res = await fetch(`${API_BASE}/flights/${id}/weather`);
  return handleResponse(res, `Fetch weather for flight ${id}`);
}

export async function fetchFlightDisruptions(id) {
  const res = await fetch(`${API_BASE}/flights/${id}/disruptions`);
  return handleResponse(res, `Fetch disruptions for flight ${id}`);
}

export async function fetchFlightAiAnalysis(id, signal) {
  const res = await fetch(`${API_BASE}/flights/${id}/ai-analysis`, { signal });
  return handleResponse(res, `Fetch AI analysis for flight ${id}`);
}

/**
 * Format ISO datetime into clean 24-hr UTC time string (e.g., "20:21 UTC").
 */
export function formatTimeUtc(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const hours = String(d.getUTCHours()).padStart(2, '0');
    const minutes = String(d.getUTCMinutes()).padStart(2, '0');
    return `${hours}:${minutes} UTC`;
  } catch {
    return isoStr;
  }
}

/**
 * Format ISO datetime into full date + UTC time (e.g., "Mar 29, 20:21 UTC").
 */
export function formatDateTimeUtc(isoStr) {
  if (!isoStr) return '—';
  try {
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return isoStr;
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = months[d.getUTCMonth()];
    const day = d.getUTCDate();
    const hours = String(d.getUTCHours()).padStart(2, '0');
    const minutes = String(d.getUTCMinutes()).padStart(2, '0');
    return `${month} ${day}, ${hours}:${minutes} UTC`;
  } catch {
    return isoStr;
  }
}
