import React from 'react';
import { formatTimeUtc } from '../api';
import { ShieldAlert } from 'lucide-react';

export default function DisruptionPanel({ disruptions, loading }) {
  if (loading) {
    return (
      <div className="fp-panel-state">
        <span className="mono">SCANNING FAA NAS DISRUPTIONS...</span>
      </div>
    );
  }

  const items = disruptions?.disruptions || [];

  return (
    <div className="fp-disruptions-module">
      <div className="fp-module-header">
        <div className="fp-module-title-wrap">
          <span className="fp-module-kicker mono">FAA NATIONAL AIRSPACE SYSTEM (NAS)</span>
          <h4 className="fp-module-heading">ACTIVE AIR TRAFFIC MANAGEMENT RESTRICTIONS</h4>
        </div>
        <div className="fp-module-count mono">
          {items.length} ACTIVE ADVISORIES
        </div>
      </div>

      {items.length === 0 ? (
        <div className="fp-panel-state is-empty">
          <span className="mono">ZERO ACTIVE FAA GROUND STOPS OR FLOW RESTRICTIONS IN DEPARTURE WINDOW</span>
        </div>
      ) : (
        <div className="fp-disruptions-grid">
          {items.map((item) => {
            const sev = (item.severity || 'HIGH').toUpperCase();
            const isCritical = sev === 'CRITICAL' || sev === 'HIGH';

            return (
              <div
                key={item.id}
                className={`fp-disruption-notice ${isCritical ? 'notice-critical' : ''}`}
              >
                <div className="fp-notice-header mono">
                  <div className="fp-notice-type-tag">
                    <ShieldAlert size={12} className="inline-icon" />
                    <span>FAA / {item.event_type}</span>
                  </div>

                  <span className="fp-notice-apt">
                    STATION: {item.airport_code || 'EN-ROUTE'}
                  </span>

                  <span className={`fp-notice-severity sev-${sev.toLowerCase()}`}>
                    {sev}
                  </span>
                </div>

                <div className="fp-notice-title-row">
                  <h5 className="fp-notice-title">{item.title}</h5>
                </div>

                {item.description && (
                  <p className="fp-notice-desc mono">{item.description}</p>
                )}

                <div className="fp-notice-footer mono">
                  <span className="notice-window">
                    WINDOW: {formatTimeUtc(item.start_time)} ➔ {formatTimeUtc(item.end_time)}
                  </span>
                  <span className="notice-source">SOURCE: {item.source || 'FAA OIS'}</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
