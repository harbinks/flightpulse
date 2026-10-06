import React, { useState, useEffect } from 'react';
import {
  Plane,
  Search,
  AlertTriangle,
  CheckCircle2,
  Clock,
  CloudRain,
  ShieldAlert,
  Wind,
  Thermometer,
  Calendar,
  Activity,
  Layers,
  ChevronRight,
  RefreshCw,
  ExternalLink,
  MapPin,
  FileText
} from 'lucide-react';
import './App.css';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export default function App() {
  const [flights, setFlights] = useState([]);
  const [totalFlights, setTotalFlights] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [systemHealth, setSystemHealth] = useState(null);

  // Filters
  const [flightNumberFilter, setFlightNumberFilter] = useState('');
  const [originFilter, setOriginFilter] = useState('');
  const [delayStatusFilter, setDelayStatusFilter] = useState('');

  // Selected Flight State
  const [selectedFlightId, setSelectedFlightId] = useState(null);
  const [flightDetail, setFlightDetail] = useState(null);
  const [intelligence, setIntelligence] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [weather, setWeather] = useState(null);
  const [disruptions, setDisruptions] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Active View Tab in Details Panel
  const [activeTab, setActiveTab] = useState('intelligence'); // 'intelligence', 'timeline', 'candidates', 'raw_evidence'

  // Fetch system health on mount
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => res.json())
      .then((data) => setSystemHealth(data))
      .catch(() => setSystemHealth({ status: 'unreachable' }));
  }, []);

  // Fetch flights on filter changes
  const fetchFlights = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (flightNumberFilter) params.append('flight_number', flightNumberFilter);
      if (originFilter) params.append('origin', originFilter);
      if (delayStatusFilter) params.append('delay_status', delayStatusFilter);
      params.append('limit', '50');

      const res = await fetch(`${API_BASE}/flights?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP error ${res.status}`);
      const data = await res.json();
      setFlights(data.flights || []);
      setTotalFlights(data.total || 0);

      // Auto-select first delayed flight if available, else first flight
      if (data.flights && data.flights.length > 0) {
        const delayed = data.flights.find((f) => f.departure_delay_minutes > 15);
        const defaultId = delayed ? delayed.id : data.flights[0].id;
        setSelectedFlightId(defaultId);
      } else {
        setSelectedFlightId(null);
      }
    } catch (err) {
      console.error(err);
      setError('Failed to fetch flights from API');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFlights();
  }, [delayStatusFilter]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    fetchFlights();
  };

  // Fetch comprehensive flight intelligence bundle when selected flight changes
  useEffect(() => {
    if (!selectedFlightId) {
      setFlightDetail(null);
      setIntelligence(null);
      setTimeline(null);
      setWeather(null);
      setDisruptions(null);
      return;
    }

    const loadFlightData = async () => {
      setDetailLoading(true);
      try {
        const [detailRes, intelRes, timelineRes, weatherRes, disruptRes] = await Promise.all([
          fetch(`${API_BASE}/flights/${selectedFlightId}`),
          fetch(`${API_BASE}/flights/${selectedFlightId}/intelligence`),
          fetch(`${API_BASE}/flights/${selectedFlightId}/timeline`),
          fetch(`${API_BASE}/flights/${selectedFlightId}/weather`),
          fetch(`${API_BASE}/flights/${selectedFlightId}/disruptions`),
        ]);

        if (detailRes.ok) setFlightDetail(await detailRes.json());
        if (intelRes.ok) setIntelligence(await intelRes.json());
        if (timelineRes.ok) setTimeline(await timelineRes.json());
        if (weatherRes.ok) setWeather(await weatherRes.json());
        if (disruptRes.ok) setDisruptions(await disruptRes.json());
      } catch (err) {
        console.error('Failed loading flight details:', err);
      } finally {
        setDetailLoading(false);
      }
    };

    loadFlightData();
  }, [selectedFlightId]);

  const formatDateTime = (dtStr) => {
    if (!dtStr) return 'N/A';
    try {
      const d = new Date(dtStr);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false }) + ' UTC';
    } catch {
      return dtStr;
    }
  };

  const getConfidenceBadgeClass = (confidence) => {
    switch (confidence) {
      case 'HIGH':
        return 'badge-high';
      case 'MEDIUM':
        return 'badge-medium';
      case 'LOW':
        return 'badge-low';
      default:
        return 'badge-insufficient';
    }
  };

  const getEventBadgeClass = (category) => {
    switch (category) {
      case 'WEATHER':
        return 'badge-weather';
      case 'ATC':
        return 'badge-atc';
      case 'FLIGHT':
        return 'badge-flight';
      case 'AIRLINE':
        return 'badge-airline';
      case 'AIRPORT':
        return 'badge-airport';
      default:
        return 'badge-default';
    }
  };

  return (
    <div className="flightpulse-app">
      {/* Top Header */}
      <header className="header">
        <div className="header-brand">
          <div className="logo-icon">
            <Plane size={24} className="plane-icon" />
          </div>
          <div>
            <h1 className="brand-title">FlightPulse</h1>
            <p className="brand-subtitle">Deterministic Flight Delay Intelligence & Operational Attribution</p>
          </div>
        </div>

        <div className="header-meta">
          <div className={`health-pill ${systemHealth?.status === 'healthy' ? 'healthy' : 'unhealthy'}`}>
            <span className="dot"></span>
            <span>API {systemHealth?.status === 'healthy' ? 'Connected' : 'Offline'}</span>
          </div>
          <button className="refresh-btn" onClick={fetchFlights} title="Refresh Data">
            <RefreshCw size={16} />
          </button>
        </div>
      </header>

      {/* Main Layout */}
      <div className="main-layout">
        {/* Left Sidebar: Flight Search & Flight List */}
        <aside className="sidebar">
          {/* Search Form */}
          <form className="search-form" onSubmit={handleSearchSubmit}>
            <div className="search-input-group">
              <Search size={16} className="search-icon" />
              <input
                type="text"
                placeholder="Flight (e.g. UA415)"
                value={flightNumberFilter}
                onChange={(e) => setFlightNumberFilter(e.target.value)}
                className="input-field"
              />
            </div>

            <div className="filter-row">
              <input
                type="text"
                placeholder="Origin (e.g. ORD)"
                value={originFilter}
                onChange={(e) => setOriginFilter(e.target.value)}
                maxLength={4}
                className="input-field-sm"
              />
              <select
                value={delayStatusFilter}
                onChange={(e) => setDelayStatusFilter(e.target.value)}
                className="select-field"
              >
                <option value="">All Flights</option>
                <option value="DELAYED">Delayed Only</option>
                <option value="ON_TIME">On-Time</option>
              </select>
            </div>

            <button type="submit" className="search-btn">
              Apply Filters
            </button>
          </form>

          {/* Flight List Header */}
          <div className="flight-list-header">
            <span>Available Flights ({totalFlights})</span>
            <span className="source-tag">PostgreSQL Engine</span>
          </div>

          {/* Flights Scroll List */}
          <div className="flight-list">
            {loading ? (
              <div className="state-message">Loading flights...</div>
            ) : error ? (
              <div className="state-message error">{error}</div>
            ) : flights.length === 0 ? (
              <div className="state-message">No flights match the criteria.</div>
            ) : (
              flights.map((f) => {
                const isSelected = f.id === selectedFlightId;
                const isDelayed = f.departure_delay_minutes > 15;
                return (
                  <div
                    key={f.id}
                    className={`flight-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedFlightId(f.id)}
                  >
                    <div className="flight-item-top">
                      <span className="flight-num">{f.flight_number}</span>
                      <span className={`status-badge ${isDelayed ? 'delayed' : 'ontime'}`}>
                        {isDelayed ? `+${f.departure_delay_minutes}m` : 'ON TIME'}
                      </span>
                    </div>

                    <div className="flight-item-route">
                      <span className="airport-code">{f.origin_iata}</span>
                      <span className="route-arrow">→</span>
                      <span className="airport-code">{f.destination_iata}</span>
                      <span className="airline-name">{f.airline_name}</span>
                    </div>

                    <div className="flight-item-bottom">
                      <span className="flight-date">{f.flight_date}</span>
                      <span className="flight-status">{f.status}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </aside>

        {/* Right Content Area: Intelligence & Disruption Analysis */}
        <main className="content-pane">
          {detailLoading ? (
            <div className="center-loader">
              <RefreshCw size={32} className="spin" />
              <p>Analyzing multi-signal evidence for flight...</p>
            </div>
          ) : !flightDetail ? (
            <div className="center-loader">
              <Plane size={48} className="muted-icon" />
              <p>Select a flight from the list to inspect delay intelligence.</p>
            </div>
          ) : (
            <div className="flight-detail-container">
              {/* Flight Summary Header Card */}
              <div className="flight-banner">
                <div className="banner-primary">
                  <div className="route-display">
                    <div className="route-endpoint">
                      <span className="iata">{flightDetail.origin_iata}</span>
                      <span className="city">{flightDetail.origin_city}</span>
                    </div>
                    <div className="route-path">
                      <Plane size={20} className="plane-flying" />
                      <div className="flight-line"></div>
                      <span className="distance">{flightDetail.airline_name} • {flightDetail.flight_number}</span>
                    </div>
                    <div className="route-endpoint">
                      <span className="iata">{flightDetail.destination_iata}</span>
                      <span className="city">{flightDetail.destination_city}</span>
                    </div>
                  </div>

                  <div className="delay-metric-box">
                    <span className="metric-label">DEPARTURE DELAY</span>
                    <span className={`metric-value ${flightDetail.departure_delay_minutes > 15 ? 'delayed' : 'ontime'}`}>
                      {flightDetail.departure_delay_minutes > 0 ? `+${flightDetail.departure_delay_minutes} min` : 'On Time'}
                    </span>
                    <span className="reported-cat">
                      Carrier Reported: <strong>{flightDetail.delay_category || 'NONE'}</strong>
                    </span>
                  </div>
                </div>

                <div className="banner-details-grid">
                  <div className="detail-item">
                    <span className="item-label">Scheduled Departure</span>
                    <span className="item-val">{formatDateTime(flightDetail.scheduled_departure)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="item-label">Actual Departure</span>
                    <span className="item-val">{formatDateTime(flightDetail.actual_departure)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="item-label">Scheduled Arrival</span>
                    <span className="item-val">{formatDateTime(flightDetail.scheduled_arrival)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="item-label">Actual Arrival</span>
                    <span className="item-val">{formatDateTime(flightDetail.actual_arrival)}</span>
                  </div>
                  <div className="detail-item">
                    <span className="item-label">Aircraft / Equipment</span>
                    <span className="item-val">{flightDetail.aircraft_type || 'Commercial Jet'}</span>
                  </div>
                  <div className="detail-item">
                    <span className="item-label">Operational Status</span>
                    <span className="item-val">{flightDetail.status}</span>
                  </div>
                </div>
              </div>

              {/* Navigation Tabs */}
              <div className="nav-tabs">
                <button
                  className={`tab-btn ${activeTab === 'intelligence' ? 'active' : ''}`}
                  onClick={() => setActiveTab('intelligence')}
                >
                  <Activity size={16} />
                  <span>Why Was This Delayed?</span>
                </button>
                <button
                  className={`tab-btn ${activeTab === 'timeline' ? 'active' : ''}`}
                  onClick={() => setActiveTab('timeline')}
                >
                  <Clock size={16} />
                  <span>Disruption Timeline ({timeline?.total_events || 0})</span>
                </button>
                <button
                  className={`tab-btn ${activeTab === 'candidates' ? 'active' : ''}`}
                  onClick={() => setActiveTab('candidates')}
                >
                  <Layers size={16} />
                  <span>Ranked Candidates ({intelligence?.candidates?.length || 0})</span>
                </button>
                <button
                  className={`tab-btn ${activeTab === 'raw_evidence' ? 'active' : ''}`}
                  onClick={() => setActiveTab('raw_evidence')}
                >
                  <FileText size={16} />
                  <span>Raw Signals & METAR</span>
                </button>
              </div>

              {/* TAB 1: Why Was This Flight Delayed? (Primary Intelligence Attribution) */}
              {activeTab === 'intelligence' && (
                <div className="tab-content">
                  {intelligence?.primary_candidate ? (
                    <div className="attribution-card">
                      <div className="attribution-header">
                        <div className="attribution-title-group">
                          <span className="attribution-subtitle">PRIMARY ATTRIBUTED CAUSE</span>
                          <h2 className="attribution-title">{intelligence.primary_candidate.category}</h2>
                        </div>
                        <div className="attribution-badges">
                          <span className={`confidence-badge ${getConfidenceBadgeClass(intelligence.primary_candidate.confidence)}`}>
                            {intelligence.primary_candidate.confidence} CONFIDENCE
                          </span>
                          <span className="score-badge">
                            Score: {Math.round(intelligence.primary_candidate.score * 100)}%
                          </span>
                        </div>
                      </div>

                      <div className="attribution-explanation">
                        <p>{intelligence.explanation_summary}</p>
                      </div>

                      <div className="evidence-section">
                        <h4 className="evidence-header">Deterministic Supporting Evidence:</h4>
                        <ul className="evidence-list">
                          {intelligence.candidates && intelligence.candidates[0]?.evidence?.length > 0 ? (
                            intelligence.candidates[0].evidence.map((item, idx) => (
                              <li key={idx} className="evidence-item">
                                <CheckCircle2 size={16} className="evidence-check" />
                                <span>{item}</span>
                              </li>
                            ))
                          ) : (
                            <li className="evidence-item muted">
                              No corroborating meteorological or air traffic management advisories matched the flight departure window.
                            </li>
                          )}
                        </ul>
                      </div>

                      <div className="attribution-footer">
                        <ShieldAlert size={14} className="shield-icon" />
                        <span>
                          Attribution is deterministically generated by the FlightPulse intelligence engine using multi-signal correlation across weather observations, FAA NAS status, and operational gate logs.
                        </span>
                      </div>
                    </div>
                  ) : (
                    <div className="attribution-card">
                      <p>Flight intelligence attribution currently unavailable.</p>
                    </div>
                  )}

                  {/* Summary Callout Cards */}
                  <div className="signals-summary-row">
                    <div className="summary-box">
                      <div className="summary-box-header">
                        <CloudRain size={18} className="box-icon weather" />
                        <span>Departure Weather Context</span>
                      </div>
                      <p className="summary-text">
                        {weather?.origin_observations?.length > 0
                          ? `${weather.origin_observations.length} METAR observations recorded around scheduled departure (${weather.origin_airport}). Recent condition: ${weather.origin_observations[0].condition_code}, Wind: ${weather.origin_observations[0].wind_speed_knots || 0} kts.`
                          : `No severe atmospheric conditions reported for origin airport ${flightDetail.origin_iata}.`}
                      </p>
                    </div>

                    <div className="summary-box">
                      <div className="summary-box-header">
                        <AlertTriangle size={18} className="box-icon atc" />
                        <span>FAA Ground Stops & NAS Notices</span>
                      </div>
                      <p className="summary-text">
                        {disruptions?.disruptions?.length > 0
                          ? `${disruptions.disruptions.length} FAA air traffic restriction notice(s) active during operations at ${disruptions.disruptions[0].airport_code}: ${disruptions.disruptions[0].title}.`
                          : `Zero active FAA ground stops or NAS delay programs affecting ${flightDetail.origin_iata} or route.`}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: Chronological Disruption Timeline */}
              {activeTab === 'timeline' && (
                <div className="tab-content">
                  <div className="timeline-container">
                    <div className="timeline-header-info">
                      <h3>Factual Chronological Progression</h3>
                      <p>Assembled strictly from database event milestones, METAR records, and FAA disruption notices without fabrication.</p>
                    </div>

                    <div className="timeline-stream">
                      {timeline?.timeline?.map((ev, index) => (
                        <div key={index} className="timeline-item">
                          <div className="timeline-time">
                            <span className="time-val">{formatDateTime(ev.time)}</span>
                            <span className="time-date">{new Date(ev.time).toLocaleDateString([], { month: 'short', day: 'numeric' })}</span>
                          </div>

                          <div className="timeline-node">
                            <span className={`node-dot ${getEventBadgeClass(ev.category)}`}></span>
                            {index < timeline.timeline.length - 1 && <div className="node-line"></div>}
                          </div>

                          <div className="timeline-card">
                            <div className="timeline-card-header">
                              <span className={`category-tag ${getEventBadgeClass(ev.category)}`}>
                                {ev.category}
                              </span>
                              <span className="timeline-title">{ev.title}</span>
                              {ev.severity && <span className="severity-badge">{ev.severity}</span>}
                            </div>
                            {ev.detail && <p className="timeline-detail">{ev.detail}</p>}
                            {ev.source && <span className="timeline-source">Source: {ev.source}</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: Ranked Candidates Breakdown */}
              {activeTab === 'candidates' && (
                <div className="tab-content">
                  <div className="candidates-list">
                    <div className="candidates-header">
                      <h3>All Evaluated Candidate Hypotheses</h3>
                      <p>
                        The intelligence engine scores every candidate category deterministically. Candidates with zero supporting evidence are scored down or marked insufficient.
                      </p>
                    </div>

                    {intelligence?.candidates?.map((candidate, idx) => (
                      <div key={idx} className="candidate-card">
                        <div className="candidate-top">
                          <div className="candidate-rank">#{idx + 1}</div>
                          <div className="candidate-cat">
                            <h4>{candidate.category}</h4>
                            <span className="primary-sig">Signal: {candidate.primary_signal}</span>
                          </div>
                          <div className="candidate-metrics">
                            <span className={`confidence-badge ${getConfidenceBadgeClass(candidate.confidence)}`}>
                              {candidate.confidence}
                            </span>
                            <span className="candidate-score">{(candidate.score * 100).toFixed(0)}%</span>
                          </div>
                        </div>

                        <div className="candidate-evidence">
                          {candidate.evidence?.length > 0 ? (
                            <ul>
                              {candidate.evidence.map((ev, i) => (
                                <li key={i}>{ev}</li>
                              ))}
                            </ul>
                          ) : (
                            <span className="no-evidence">No corroborating evidence detected.</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* TAB 4: Raw Evidence & METAR Records */}
              {activeTab === 'raw_evidence' && (
                <div className="tab-content">
                  {/* Weather Observations Table */}
                  <div className="raw-section">
                    <h3 className="section-title">
                      <CloudRain size={18} /> Origin Airport Weather Observations ({weather?.origin_airport})
                    </h3>
                    {weather?.origin_observations?.length > 0 ? (
                      <div className="table-responsive">
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Time (UTC)</th>
                              <th>Condition</th>
                              <th>Temp (°C)</th>
                              <th>Wind (kts)</th>
                              <th>Gust (kts)</th>
                              <th>Visibility (mi)</th>
                              <th>Altimeter</th>
                            </tr>
                          </thead>
                          <tbody>
                            {weather.origin_observations.map((obs) => (
                              <tr key={obs.id}>
                                <td>{formatDateTime(obs.observation_time)}</td>
                                <td><span className="condition-pill">{obs.condition_code}</span></td>
                                <td>{obs.temperature_c != null ? `${obs.temperature_c}°C` : '-'}</td>
                                <td>{obs.wind_speed_knots != null ? `${obs.wind_speed_knots} kts` : '-'}</td>
                                <td>{obs.wind_gust_knots != null ? `${obs.wind_gust_knots} kts` : '-'}</td>
                                <td>{obs.visibility_miles != null ? `${obs.visibility_miles} mi` : '-'}</td>
                                <td>{obs.altimeter_inhg != null ? `${obs.altimeter_inhg} inHg` : '-'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <p className="empty-notice">No weather observations stored within the temporal query window.</p>
                    )}
                  </div>

                  {/* FAA Disruption Events */}
                  <div className="raw-section">
                    <h3 className="section-title">
                      <AlertTriangle size={18} /> FAA Disruption Events & NAS Advisories
                    </h3>
                    {disruptions?.disruptions?.length > 0 ? (
                      <div className="disruptions-cards">
                        {disruptions.disruptions.map((d) => (
                          <div key={d.id} className="disruption-item-card">
                            <div className="disruption-item-header">
                              <span className="disruption-badge">{d.event_type}</span>
                              <span className="disruption-apt">{d.airport_code}</span>
                              <span className="disruption-severity">{d.severity}</span>
                            </div>
                            <h4 className="disruption-item-title">{d.title}</h4>
                            <p className="disruption-item-desc">{d.description}</p>
                            <div className="disruption-meta">
                              <span>Window: {formatDateTime(d.start_time)} → {formatDateTime(d.end_time)}</span>
                              <span>Source: {d.source || 'FAA NAS'}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="empty-notice">No FAA disruption notices logged for this flight's departure window.</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
