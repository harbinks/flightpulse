import React from 'react';
import { formatDateTimeUtc } from '../api';
import { Plane, AlertOctagon, ShieldCheck } from 'lucide-react';

export default function FlightHeader({ flight, intelligence }) {
  if (!flight) return null;

  const isTelemetry = flight.data_source === 'OPENSKY_LIVE';
  const delayMins = flight.departure_delay_minutes;
  const hasDelay = delayMins != null;
  const isDelayed = hasDelay && delayMins > 15;
  const primaryCandidate = intelligence?.primary_candidate;

  const reportedCategory = isTelemetry
    ? 'NONE (LIVE ADS-B TELEMETRY)'
    : (flight.delay_category || 'NOT REPORTED / NONE');

  const assessedCategory = isTelemetry
    ? 'INSUFFICIENT EVIDENCE (LIVE TELEMETRY)'
    : (primaryCandidate?.category || 'EVALUATING...');

  const assessedConfidence = isTelemetry
    ? 'INSUFFICIENT'
    : (primaryCandidate?.confidence || 'PENDING');

  const assessedScore = (!isTelemetry && primaryCandidate?.score != null)
    ? Math.round(primaryCandidate.score * 100)
    : null;

  return (
    <div className={`fp-investigation-banner ${isTelemetry ? 'is-telemetry-banner' : ''}`}>
      {/* Top Bar: Callsign, Carrier & Aircraft */}
      <div className="fp-banner-meta-bar">
        <div className="fp-banner-ident">
          <span className="fp-ident-code mono">{flight.flight_number}</span>
          <span className="fp-ident-carrier">
            {isTelemetry ? (flight.airline_name || 'ADS-B Track') : (flight.airline_name || 'Commercial Operator')}
          </span>
          <span className="fp-ident-aircraft mono">
            {isTelemetry ? (flight.tail_number ? `ICAO24: ${flight.tail_number}` : 'ADS-B') : (flight.aircraft_type || 'A320 / B737')}
          </span>
        </div>
        <div className="fp-banner-date mono">
          <span className={`fp-provenance-badge ${isTelemetry ? 'badge-live' : 'badge-demo'}`}>
            {isTelemetry ? 'OBSERVED FLIGHT • LIVE ADS-B TELEMETRY' : 'DEMO BENCHMARK DATASET'}
          </span>
          {' • '}
          STATUS: {flight.status?.toUpperCase()}
        </div>
      </div>

      {/* Main Route and Metrics Row */}
      <div className="fp-banner-hero-row">
        {/* Route Block */}
        <div className="fp-route-block">
          <div className="fp-station-cell origin">
            <span className="fp-station-code mono">{flight.origin_iata || '---'}</span>
            <span className="fp-station-city">{flight.origin_city || flight.origin_iata || 'Airspace Origin'}</span>
          </div>

          <div className="fp-route-trajectory">
            <div className="fp-trajectory-line">
              <Plane size={16} className="fp-plane-icon" />
            </div>
            <span className="fp-trajectory-label mono">
              {isTelemetry ? 'ADS-B TELEMETRY TRACK' : 'NON-STOP PASSENGER SECTOR'}
            </span>
          </div>

          <div className="fp-station-cell destination">
            <span className="fp-station-code mono">{flight.destination_iata || '---'}</span>
            <span className="fp-station-city">
              {flight.destination_city || flight.destination_iata || (isTelemetry ? 'In-Flight Track' : 'Destination')}
            </span>
          </div>
        </div>

        {/* Departure Delay Magnitude Callout */}
        <div
          className={`fp-delay-metric-callout ${
            isTelemetry ? 'is-telemetry' : isDelayed ? 'is-delayed' : 'is-ontime'
          }`}
        >
          <div className="fp-delay-metric-label">
            {isTelemetry ? 'COMMERCIAL DELAY' : 'DEPARTURE TIMING'}
          </div>
          <div className="fp-delay-metric-val mono">
            {isTelemetry
              ? 'NOT AVAILABLE'
              : isDelayed
              ? `+${delayMins} MIN`
              : hasDelay && delayMins > 0
              ? `+${delayMins}m`
              : 'ON SCHEDULE'}
          </div>
          <div className="fp-delay-metric-sub mono">
            {isTelemetry
              ? 'NO PUBLISHED SCHEDULE RECORD'
              : isDelayed
              ? 'SUBSTANTIAL OPERATION DELAY'
              : 'NORMAL SCHEDULE TOLERANCE'}
          </div>
        </div>
      </div>

      {/* Schedule vs Actual Matrix */}
      <div className="fp-schedule-matrix">
        <div className="fp-matrix-cell">
          <span className="fp-cell-label">SCHEDULED DEPARTURE</span>
          <span className="fp-cell-val mono">
            {flight.scheduled_departure ? formatDateTimeUtc(flight.scheduled_departure) : 'NOT AVAILABLE'}
          </span>
        </div>
        <div className="fp-matrix-cell">
          <span className="fp-cell-label">
            {isTelemetry ? 'OBSERVED DEPARTURE (FIRST SEEN)' : 'ACTUAL DEPARTURE'}
          </span>
          <span className={`fp-cell-val mono ${isDelayed ? 'text-delayed' : ''}`}>
            {formatDateTimeUtc(flight.actual_departure)}
          </span>
        </div>
        <div className="fp-matrix-cell">
          <span className="fp-cell-label">SCHEDULED ARRIVAL</span>
          <span className="fp-cell-val mono">
            {flight.scheduled_arrival ? formatDateTimeUtc(flight.scheduled_arrival) : 'NOT AVAILABLE'}
          </span>
        </div>
        <div className="fp-matrix-cell">
          <span className="fp-cell-label">
            {isTelemetry ? 'OBSERVED ARRIVAL (LAST SEEN)' : 'ACTUAL ARRIVAL'}
          </span>
          <span className="fp-cell-val mono">{formatDateTimeUtc(flight.actual_arrival)}</span>
        </div>
      </div>

      {/* CRITICAL COMPARISON: Carrier Claim vs FlightPulse Grounded Attribution */}
      <div className="fp-attribution-comparison-grid">
        {/* Box A: Carrier Claim */}
        <div className="fp-comparison-box carrier-box">
          <div className="fp-box-header">
            <AlertOctagon size={13} className="box-header-icon" />
            <span className="fp-box-title">CARRIER-REPORTED REASON</span>
          </div>
          <div className="fp-box-body">
            <div className="fp-claim-badge mono">{reportedCategory}</div>
            <p className="fp-box-note">
              {isTelemetry
                ? 'No airline dispatch reason exists for raw ADS-B transponder observations. Transponder data captures physical flight movement only.'
                : 'Self-reported by airline dispatch for regulatory billing & delay categorization. Often uncorroborated by independent atmospheric data.'}
            </p>
          </div>
        </div>

        {/* Box B: FlightPulse Intelligence Assessment */}
        <div className="fp-comparison-box fp-intelligence-box">
          <div className="fp-box-header">
            <ShieldCheck size={13} className="box-header-icon" />
            <span className="fp-box-title">FLIGHTPULSE ENGINE ATTRIBUTION</span>
          </div>
          <div className="fp-box-body">
            <div className="fp-attribution-result">
              <span className="fp-assessed-cause mono">{assessedCategory}</span>
              <div className="fp-confidence-pill-wrap">
                <span className={`fp-confidence-pill conf-${assessedConfidence.toLowerCase()} mono`}>
                  {assessedConfidence} CONFIDENCE
                </span>
                {assessedScore != null && (
                  <span className="fp-score-tag mono">{assessedScore}% CORRELATION</span>
                )}
              </div>
            </div>
            <p className="fp-box-note">
              {isTelemetry
                ? 'Deterministic causal attribution requires a published scheduled departure time to calculate delay delta. Live ADS-B records operate in telemetry-only observation mode.'
                : 'Inferred through multi-signal correlation across airport METAR telemetry, FAA Ground Stop advisories, and gate time delta.'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
