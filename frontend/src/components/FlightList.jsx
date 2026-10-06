import React from 'react';
import { formatTimeUtc } from '../api';

export default function FlightList({
  flights,
  selectedFlightId,
  onSelectFlight,
  loading,
  error,
}) {
  if (loading) {
    return (
      <div className="fp-list-state">
        <div className="fp-state-pulse"></div>
        <span>POLLING FLIGHT ROSTER...</span>
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
    return (
      <div className="fp-list-state is-empty">
        <span>ZERO MATCHING OPERATIONS</span>
      </div>
    );
  }

  return (
    <div className="fp-flight-list" role="list">
      {flights.map((flight) => {
        const isSelected = flight.id === selectedFlightId;
        const delayMins = flight.departure_delay_minutes || 0;
        const isDelayed = delayMins > 15;
        const isMinorDelay = delayMins > 0 && delayMins <= 15;

        return (
          <div
            key={flight.id}
            role="listitem"
            className={`fp-flight-strip ${isSelected ? 'is-selected' : ''}`}
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
            <div className={`fp-strip-indicator ${isDelayed ? 'ind-delayed' : 'ind-ontime'}`}></div>

            <div className="fp-strip-main">
              <div className="fp-strip-row-1">
                <span className="fp-strip-ident mono">{flight.flight_number}</span>
                <span className="fp-strip-airline">{flight.airline_name || 'Commercial'}</span>

                <span
                  className={`fp-strip-delay-badge mono ${
                    isDelayed ? 'badge-delayed' : isMinorDelay ? 'badge-minor' : 'badge-ontime'
                  }`}
                >
                  {isDelayed ? `+${delayMins} MIN` : isMinorDelay ? `+${delayMins}m` : 'ON-TIME'}
                </span>
              </div>

              <div className="fp-strip-row-2">
                <div className="fp-strip-route">
                  <span className="fp-strip-station mono">{flight.origin_iata}</span>
                  <span className="fp-strip-arrow">➔</span>
                  <span className="fp-strip-station mono">{flight.destination_iata}</span>
                </div>

                <div className="fp-strip-times mono">
                  <span>{formatTimeUtc(flight.scheduled_departure)}</span>
                  {flight.actual_departure && (
                    <>
                      <span className="fp-times-sep">/</span>
                      <span className={isDelayed ? 'text-delayed' : ''}>
                        {formatTimeUtc(flight.actual_departure)}
                      </span>
                    </>
                  )}
                </div>
              </div>

              <div className="fp-strip-row-3">
                <span className="fp-strip-date mono">{flight.flight_date}</span>
                <span className="fp-strip-reported">
                  {flight.delay_category ? `REP: ${flight.delay_category}` : `STATUS: ${flight.status}`}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
