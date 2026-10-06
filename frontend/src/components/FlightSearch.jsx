import React from 'react';
import { Search, RotateCcw } from 'lucide-react';

export default function FlightSearch({
  flightNumber,
  setFlightNumber,
  origin,
  setOrigin,
  delayStatus,
  setDelayStatus,
  onSubmit,
  onReset,
  totalFlights,
}) {
  return (
    <div className="fp-search-control">
      <div className="fp-control-bar-header">
        <span className="fp-control-title">DISPATCH SEARCH & FILTER</span>
        <span className="fp-control-count mono">
          ACTIVE MATCHES: <strong>{totalFlights}</strong>
        </span>
      </div>

      <form className="fp-search-form" onSubmit={onSubmit}>
        <div className="fp-form-field fp-field-flight">
          <label className="fp-field-label">FLIGHT IDENT</label>
          <div className="fp-input-wrap">
            <Search size={13} className="fp-input-icon" />
            <input
              type="text"
              placeholder="e.g. UA415"
              value={flightNumber}
              onChange={(e) => setFlightNumber(e.target.value)}
              className="fp-input mono"
              spellCheck={false}
            />
          </div>
        </div>

        <div className="fp-form-field fp-field-origin">
          <label className="fp-field-label">ORIGIN IATA</label>
          <input
            type="text"
            placeholder="e.g. ORD"
            value={origin}
            onChange={(e) => setOrigin(e.target.value.toUpperCase())}
            maxLength={4}
            className="fp-input mono text-center"
            spellCheck={false}
          />
        </div>

        <div className="fp-form-field fp-field-status">
          <label className="fp-field-label">DELAY THRESHOLD</label>
          <select
            value={delayStatus}
            onChange={(e) => setDelayStatus(e.target.value)}
            className="fp-select mono"
          >
            <option value="">ALL FLIGHTS</option>
            <option value="DELAYED">DELAYED ONLY (&gt;15m)</option>
            <option value="ON_TIME">ON-TIME / SCHEDULED</option>
          </select>
        </div>

        <div className="fp-form-actions">
          <button type="submit" className="fp-btn-primary">
            FILTER
          </button>
          <button type="button" className="fp-btn-secondary" onClick={onReset} title="Reset Filter Parameters">
            <RotateCcw size={12} />
          </button>
        </div>
      </form>
    </div>
  );
}
