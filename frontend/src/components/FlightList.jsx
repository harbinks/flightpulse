import React from 'react';
import { formatTimeUtc } from '../api';

export default function FlightList({
  flights,
  selectedFlightId,
  onSelectFlight,
  loading,
  error,
  mode = 'demo',
  onSync,
}) {
  if (loading) {
    return (
      <div className="fp-list-state">
        <div className="fp-state-pulse"></div>
        <span>{mode === 'live' ? 'POLLING LIVE ADS-B TELEMETRY...' : 'POLLING FLIGHT ROSTER...'}</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="fp-list-state is-error">
        <span>ERROR: {error}</span>
      </div>
    );
  }

  if (!flights || flights.length === 0) {
    if (mode === 'live') {
      return (
        <div className="fp-list-state fp-live-empty-state">
          <span className="empty-title mono">NO LIVE TELEMETRY AVAILABLE</span>
          <p className="empty-desc">OpenSky currently returned no usable live flight records for the configured airspace.</p>
          {onSync && (
            <button type="button" className="fp-empty-sync-btn mono" onClick={onSync}>
              SYNC LIVE FEEDS
            </button>
          )}
        </div>
      );
    }

    return (
      <div className="fp-list-state is-empty">
        <span>ZERO MATCHING OPERATIONS</span>
      </div>
    );
  }

  const isLiveMode = mode === 'live';

  return (
    <div className="fp-flight-list" role="list">
      {flights.map((flight) => {
        const isSelected = flight.id === selectedFlightId;
        const isTelemetry = flight.data_source === 'OPENSKY_LIVE' || isLiveMode;
        const delayMins = flight.departure_delay_minutes;
        const hasDelay = delayMins != null;
        const isDelayed = hasDelay && delayMins > 15;
        const isMinorDelay = hasDelay && delayMins > 0 && delayMins <= 15;

        return (
          <div
            key={flight.id}
            role="listitem"
            className={`fp-flight-strip ${isSelected ? 'is-selected' : ''} ${isTelemetry ? 'is-telemetry' : ''}`}
            onClick={() => onSelectFlight(flight.id)}
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onSelectFlight(flight.id);
              }
            }}
          >
            {/* Left strip status line indicator */}
            <div
              className={`fp-strip-indicator ${
                isTelemetry ? 'ind-telemetry' : isDelayed ? 'ind-delayed' : 'ind-ontime'
              }`}
            ></div>

            <div className="fp-strip-main">
              <div className="fp-strip-row-1">
                <span className="fp-strip-ident mono">{flight.flight_number}</span>
                <span className="fp-strip-airline">
                  {isTelemetry ? (flight.airline_name || 'ADS-B Track') : (flight.airline_name || 'Commercial')}
                </span>

                {isTelemetry ? (
                  <span className="fp-strip-delay-badge badge-telemetry mono">
                    LIVE ADS-B
                  </span>
                ) : (
                  <span
                    className={`fp-strip-delay-badge mono ${
                      isDelayed ? 'badge-delayed' : isMinorDelay ? 'badge-minor' : 'badge-ontime'
                    }`}
                  >
                    {isDelayed ? `+${delayMins} MIN` : isMinorDelay ? `+${delayMins}m` : 'ON-TIME'}
                  </span>
                )}
              </div>

              <div className="fp-strip-row-2">
                <div className="fp-strip-route">
                  <span className="fp-strip-station mono">{flight.origin_iata}</span>
                  <span className="fp-strip-arrow">➔</span>
                  <span className="fp-strip-station mono">{flight.destination_iata}</span>
                </div>

                <div className="fp-strip-times mono">
                  {isTelemetry ? (
                    <span>OBS: {formatTimeUtc(flight.actual_departure)}</span>
                  ) : (
                    <>
                      <span>{formatTimeUtc(flight.scheduled_departure)}</span>
                      {flight.actual_departure && (
                        <>
                          <span className="fp-times-sep">/</span>
                          <span className={isDelayed ? 'text-delayed' : ''}>
                            {formatTimeUtc(flight.actual_departure)}
                          </span>
                        </>
                      )}
                    </>
                  )}
                </div>
              </div>

              <div className="fp-strip-row-3">
                <span className="fp-strip-date mono">{flight.flight_date}</span>
                <span className="fp-strip-provenance mono">
                  {isTelemetry ? (
                    `TAIL: ${flight.aircraft_type || flight.flight_number || 'UNKNOWN'}`
                  ) : (
                    flight.delay_category ? `REP: ${flight.delay_category}` : `STATUS: ${flight.status}`
                  )}
                </span>
                <span className={`fp-provenance-tag mono ${isTelemetry ? 'tag-live' : 'tag-demo'}`}>
                  {isTelemetry ? 'LIVE ADS-B' : 'DEMO BENCHMARK'}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
