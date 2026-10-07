import React, { useState, useEffect, useRef } from 'react';
import Header from './components/Header';
import FlightSearch from './components/FlightSearch';
import FlightList from './components/FlightList';
import FlightHeader from './components/FlightHeader';
import AnalystBrief from './components/AnalystBrief';
import FlightTimeline from './components/FlightTimeline';
import WeatherPanel from './components/WeatherPanel';
import DisruptionPanel from './components/DisruptionPanel';
import CandidateBreakdown from './components/CandidateBreakdown';
import OperationsRibbon from './components/OperationsRibbon';
import {
  fetchHealth,
  fetchFlights,
  fetchOperationsStatus,
  syncLiveFeeds,
  fetchFlightDetail,
  fetchFlightIntelligence,
  fetchFlightTimeline,
  fetchFlightWeather,
  fetchFlightDisruptions,
  fetchFlightAiAnalysis,
} from './api';
import './App.css';
import { Activity, Clock, Cloud, Layers } from 'lucide-react';

export default function App() {
  // Operational Mode State: 'demo' (default) or 'live'
  const [mode, setMode] = useState('demo');

  // System Health
  const [systemHealth, setSystemHealth] = useState(null);

  // Operations Status & Synchronization State
  const [operationsStatus, setOperationsStatus] = useState(null);
  const [operationsLoading, setOperationsLoading] = useState(false);
  const [operationsError, setOperationsError] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState(null); // { type: 'success' | 'partial' | 'failed' | 'conflict', message: '...' }

  // Flight Directory State
  const [flights, setFlights] = useState([]);
  const [totalFlights, setTotalFlights] = useState(0);
  const [flightsLoading, setFlightsLoading] = useState(true);
  const [flightsError, setFlightsError] = useState(null);

  // Search & Filter State
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

  // Grounded AI Analyst State
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState(null);
  const [aiCache, setAiCache] = useState({});
  const aiAbortControllerRef = useRef(null);

  // View Navigation inside Workspace
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState('dossier'); // 'dossier' | 'timeline' | 'weather_atc' | 'candidates'

  // 1. Initial Health Check
  const loadHealth = async () => {
    const health = await fetchHealth();
    setSystemHealth(health);
  };

  useEffect(() => {
    loadHealth();
    const interval = setInterval(loadHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  // 2. Operations Status Polling (Active ONLY in LIVE mode)
  const loadOperationsStatus = async () => {
    setOperationsLoading(true);
    try {
      setOperationsError(null);
      const data = await fetchOperationsStatus();
      setOperationsStatus(data);
    } catch (err) {
      console.warn('Failed loading operations status:', err);
      setOperationsError(err.message || 'Status unavailable');
    } finally {
      setOperationsLoading(false);
    }
  };

  useEffect(() => {
    if (mode === 'live') {
      loadOperationsStatus();
      const interval = setInterval(loadOperationsStatus, 30000);
      return () => clearInterval(interval);
    }
  }, [mode]);

  // 3. Fetch Flights Directory
  const loadFlights = async (selectedIdToPreserve = null, overrideMode = null) => {
    const activeMode = overrideMode || mode;
    setFlightsLoading(true);
    setFlightsError(null);
    try {
      const data = await fetchFlights({
        flightNumber: flightNumberFilter,
        origin: originFilter,
        delayStatus: delayStatusFilter,
        mode: activeMode,
        limit: 50,
      });

      const list = data.flights || [];
      setFlights(list);
      setTotalFlights(data.total || 0);

      // Preserve selection or auto-select delayed flight
      if (list.length > 0) {
        if (selectedIdToPreserve && list.some((f) => f.id === selectedIdToPreserve)) {
          setSelectedFlightId(selectedIdToPreserve);
        } else if (!selectedFlightId || !list.some((f) => f.id === selectedFlightId)) {
          const delayed = list.find((f) => f.departure_delay_minutes > 15);
          setSelectedFlightId(delayed ? delayed.id : list[0].id);
        }
      } else {
        setSelectedFlightId(null);
      }
    } catch (err) {
      console.error('Failed to load flights:', err);
      setFlightsError(err.message || 'Error fetching flights');
    } finally {
      setFlightsLoading(false);
    }
  };

  // Reload flights when mode or delayStatusFilter changes
  useEffect(() => {
    loadFlights(null, mode);
  }, [mode, delayStatusFilter]);

  // Handle Mode Switch (DEMO <-> LIVE)
  const handleModeChange = (newMode) => {
    if (newMode === mode) return;
    setMode(newMode);
    setSelectedFlightId(null);
    setFlightDetail(null);
    setIntelligence(null);
    setTimeline(null);
    setWeather(null);
    setDisruptions(null);
    setAiAnalysis(null);
    setSyncResult(null);
  };

  // Handle On-Demand Live Synchronization
  const handleSyncFeeds = async () => {
    if (syncing) return;
    setSyncing(true);
    setSyncResult(null);
    try {
      const res = await syncLiveFeeds();
      const st = res.overall_status || res.status;
      const openskyStatus = res.sources?.flights?.status || res.sources?.opensky?.status;

      if (st === 'SUCCESS') {
        setSyncResult({ type: 'success', message: 'LIVE FEEDS UPDATED' });
      } else if (openskyStatus === 'RATE_LIMITED') {
        setSyncResult({ type: 'rate-limited', message: 'OPENSKY RATE LIMITED — TRY LATER' });
      } else if (st === 'PARTIAL') {
        setSyncResult({ type: 'partial', message: 'LIVE SYNC PARTIAL' });
      } else {
        setSyncResult({ type: 'failed', message: 'LIVE SYNC FAILED' });
      }

      // Refresh operations status and flights list
      await Promise.all([
        loadOperationsStatus(),
        loadFlights(selectedFlightId, 'live'),
      ]);
    } catch (err) {
      console.warn('Sync live feeds error:', err);
      if (err.message && err.message.includes('409')) {
        setSyncResult({ type: 'conflict', message: 'SYNC ALREADY IN PROGRESS' });
      } else {
        setSyncResult({ type: 'failed', message: 'LIVE SYNC FAILED' });
      }
    } finally {
      setSyncing(false);
    }
  };

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    loadFlights();
  };

  const handleResetFilters = () => {
    setFlightNumberFilter('');
    setOriginFilter('');
    setDelayStatusFilter('');
  };

  // 3. Load Flight Details, Deterministic Intelligence, Timeline, Weather, and Disruptions
  useEffect(() => {
    if (!selectedFlightId) {
      setFlightDetail(null);
      setIntelligence(null);
      setTimeline(null);
      setWeather(null);
      setDisruptions(null);
      setAiAnalysis(null);
      return;
    }

    let isMounted = true;
    setDetailLoading(true);
    if (!aiCache[selectedFlightId]) {
      setAiAnalysis(null);
    }
    setAiError(null);

    // Cancel any existing in-flight AI requests
    if (aiAbortControllerRef.current) {
      aiAbortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    aiAbortControllerRef.current = abortController;

    const loadFlightData = async () => {
      try {
        const [detailData, intelData, timelineData, weatherData, disruptData] = await Promise.all([
          fetchFlightDetail(selectedFlightId),
          fetchFlightIntelligence(selectedFlightId),
          fetchFlightTimeline(selectedFlightId),
          fetchFlightWeather(selectedFlightId),
          fetchFlightDisruptions(selectedFlightId),
        ]);

        if (isMounted) {
          setFlightDetail(detailData);
          setIntelligence(intelData);
          setTimeline(timelineData);
          setWeather(weatherData);
          setDisruptions(disruptData);
          setDetailLoading(false);
        }

        // 4. Check client-side AI cache or fetch Grounded AI Analysis asynchronously
        if (isMounted) {
          if (aiCache[selectedFlightId]) {
            setAiAnalysis(aiCache[selectedFlightId]);
            setAiLoading(false);
          } else {
            setAiLoading(true);
            setAiError(null);
            try {
              const aiData = await fetchFlightAiAnalysis(selectedFlightId, abortController.signal);
              if (isMounted) {
                setAiAnalysis(aiData);
                if (aiData && aiData.status === 'success') {
                  setAiCache((prev) => ({ ...prev, [selectedFlightId]: aiData }));
                }
              }
            } catch (aiErr) {
              if (aiErr.name !== 'AbortError' && isMounted) {
                console.warn('AI analysis load failed; using fallback:', aiErr);
                setAiError(aiErr.message);
                // Construct seamless client fallback
                setAiAnalysis({
                  status: 'unavailable',
                  flight_id: selectedFlightId,
                  analysis: {
                    summary: intelData?.explanation_summary || 'Deterministic FlightPulse analysis active.',
                    primary_cause: intelData?.primary_candidate?.category || 'UNKNOWN',
                    confidence: intelData?.primary_candidate?.confidence || 'INSUFFICIENT',
                    explanation: intelData?.explanation_summary || '',
                    evidence_used: intelData?.candidates?.[0]?.evidence || [],
                    limitations: ['Local AI analyst service offline; displaying deterministic engine findings.'],
                  },
                  model_used: null,
                  execution_time_ms: 0,
                });
              }
            } finally {
              if (isMounted) {
                setAiLoading(false);
              }
            }
          }
        }
      } catch (err) {
        if (isMounted) {
          console.error('Failed loading flight details:', err);
          setDetailLoading(false);
        }
      }
    };

    loadFlightData();

    return () => {
      isMounted = false;
      abortController.abort();
    };
  }, [selectedFlightId]);

  return (
    <div className="flightpulse-root">
      {/* Top Application Header */}
      <Header
        systemHealth={systemHealth}
        onRefresh={() => loadFlights(selectedFlightId)}
        loading={flightsLoading}
        mode={mode}
        onModeChange={handleModeChange}
      />

      {/* Live Operations Ribbon (rendered only when LIVE mode is active) */}
      {mode === 'live' && (
        <OperationsRibbon
          operationsStatus={operationsStatus}
          loading={operationsLoading}
          error={operationsError}
          syncing={syncing}
          syncResult={syncResult}
          onSync={handleSyncFeeds}
          onRetryStatus={loadOperationsStatus}
        />
      )}

      {/* Main Operations Split View */}
      <div className="fp-operations-layout">
        {/* Left Column: Dispatch Flight Directory */}
        <aside className="fp-dispatch-sidebar">
          <FlightSearch
            flightNumber={flightNumberFilter}
            setFlightNumber={setFlightNumberFilter}
            origin={originFilter}
            setOrigin={setOriginFilter}
            delayStatus={delayStatusFilter}
            setDelayStatus={setDelayStatusFilter}
            onSubmit={handleSearchSubmit}
            onReset={handleResetFilters}
            totalFlights={totalFlights}
          />

          <div className="fp-roster-header mono">
            <span>{mode === 'live' ? 'LIVE ADS-B ROSTER' : 'OPERATIONAL FLIGHT DIRECTORY'}</span>
            <span>{flights.length} LOADED</span>
          </div>

          <FlightList
            flights={flights}
            selectedFlightId={selectedFlightId}
            onSelectFlight={(id) => setSelectedFlightId(id)}
            loading={flightsLoading}
            error={flightsError}
            mode={mode}
            onSync={handleSyncFeeds}
            operationsStatus={operationsStatus}
          />
        </aside>

        {/* Right Main Column: Investigation Workspace */}
        <main className="fp-workspace-main">
          {!selectedFlightId || !flightDetail ? (
            <div className="fp-empty-workspace">
              <div className="fp-empty-banner mono">
                <span className="empty-kicker">OPERATIONAL STATUS: READY</span>
                <h2>SELECT A FLIGHT IDENTIFIER TO COMMENCE DELAY INVESTIGATION</h2>
                <p>
                  FlightPulse correlates airport METAR observations, FAA National Airspace System advisories, and gate timestamps through deterministic logic and local Ollama synthesis.
                </p>
              </div>
            </div>
          ) : (
            <div className="fp-investigation-workspace">
              {/* Primary Flight Header & Carrier vs FlightPulse Attribution */}
              <FlightHeader
                flight={flightDetail}
                intelligence={intelligence}
              />

              {/* Core Grounded AI Analyst Panel */}
              <AnalystBrief
                aiAnalysis={aiAnalysis}
                loading={aiLoading}
                error={aiError}
                deterministicIntelligence={intelligence}
                onRetry={() => {
                  if (selectedFlightId) {
                    setAiLoading(true);
                    setAiError(null);
                    setAiCache((prev) => {
                      const copy = { ...prev };
                      delete copy[selectedFlightId];
                      return copy;
                    });
                    fetchFlightAiAnalysis(selectedFlightId)
                      .then((d) => {
                        setAiAnalysis(d);
                        if (d && d.status === 'success') {
                          setAiCache((prev) => ({ ...prev, [selectedFlightId]: d }));
                        }
                      })
                      .catch((err) => setAiError(err.message))
                      .finally(() => setAiLoading(false));
                  }
                }}
              />

              {/* Workspace Navigation Sub-Bar */}
              <div className="fp-workspace-nav">
                <button
                  className={`fp-nav-tab ${activeWorkspaceTab === 'dossier' ? 'is-active' : ''} mono`}
                  onClick={() => setActiveWorkspaceTab('dossier')}
                >
                  <Activity size={13} className="inline-icon" />
                  <span>INVESTIGATION DOSSIER</span>
                </button>
                <button
                  className={`fp-nav-tab ${activeWorkspaceTab === 'timeline' ? 'is-active' : ''} mono`}
                  onClick={() => setActiveWorkspaceTab('timeline')}
                >
                  <Clock size={13} className="inline-icon" />
                  <span>CHRONOLOGICAL TIMELINE ({timeline?.total_events || 0})</span>
                </button>
                <button
                  className={`fp-nav-tab ${activeWorkspaceTab === 'weather_atc' ? 'is-active' : ''} mono`}
                  onClick={() => setActiveWorkspaceTab('weather_atc')}
                >
                  <Cloud size={13} className="inline-icon" />
                  <span>METAR & FAA ADVISORIES</span>
                </button>
                <button
                  className={`fp-nav-tab ${activeWorkspaceTab === 'candidates' ? 'is-active' : ''} mono`}
                  onClick={() => setActiveWorkspaceTab('candidates')}
                >
                  <Layers size={13} className="inline-icon" />
                  <span>CANDIDATE RANKING ({intelligence?.candidates?.length || 0})</span>
                </button>
              </div>

              {/* Workspace Content Display */}
              <div className="fp-workspace-content">
                {activeWorkspaceTab === 'dossier' && (
                  <div className="fp-editorial-dossier-grid">
                    {/* Left Column: Timeline progression */}
                    <div className="fp-dossier-col-timeline">
                      <FlightTimeline timeline={timeline} loading={detailLoading} />
                    </div>

                    {/* Right Column: Telemetry & Notices */}
                    <div className="fp-dossier-col-telemetry">
                      <WeatherPanel weather={weather} loading={detailLoading} />
                      <DisruptionPanel disruptions={disruptions} loading={detailLoading} />
                      <CandidateBreakdown intelligence={intelligence} loading={detailLoading} />
                    </div>
                  </div>
                )}

                {activeWorkspaceTab === 'timeline' && (
                  <div className="fp-single-view">
                    <FlightTimeline timeline={timeline} loading={detailLoading} />
                  </div>
                )}

                {activeWorkspaceTab === 'weather_atc' && (
                  <div className="fp-telemetry-dual-view">
                    <WeatherPanel weather={weather} loading={detailLoading} />
                    <DisruptionPanel disruptions={disruptions} loading={detailLoading} />
                  </div>
                )}

                {activeWorkspaceTab === 'candidates' && (
                  <div className="fp-single-view">
                    <CandidateBreakdown intelligence={intelligence} loading={detailLoading} />
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
