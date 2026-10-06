import React from 'react';
import { formatTimeUtc, formatDateTimeUtc } from '../api';
import { Clock, ShieldAlert, Cloud, Plane } from 'lucide-react';

export default function FlightTimeline({ timeline, loading }) {
  if (loading) {
    return (
      <div className="fp-panel-state">
        <span className="mono">RECONSTRUCTING CHRONOLOGICAL PROGRESSION...</span>
      </div>
    );
  }

  const events = timeline?.timeline || [];

  if (events.length === 0) {
    return (
      <div className="fp-panel-state is-empty">
        <span className="mono">ZERO LOGGED TIMELINE MILESTONES IN RECONSTRUCTION WINDOW</span>
      </div>
    );
  }

  const getCategoryIcon = (category) => {
    switch (category) {
      case 'WEATHER':
        return <Cloud size={13} />;
      case 'ATC':
      case 'DISRUPTION':
        return <ShieldAlert size={13} />;
      case 'FLIGHT':
        return <Plane size={13} />;
      default:
        return <Clock size={13} />;
    }
  };

  return (
    <div className="fp-timeline-module">
      <div className="fp-module-header">
        <div className="fp-module-title-wrap">
          <span className="fp-module-kicker mono">TEMPORAL AUDIT TRAIL</span>
          <h4 className="fp-module-heading">FACTUAL CHRONOLOGICAL PROGRESSION</h4>
        </div>
        <div className="fp-module-count mono">
          {events.length} RECORDED MILESTONES
        </div>
      </div>

      <div className="fp-timeline-container">
        <div className="fp-timeline-spine"></div>

        <div className="fp-timeline-stream">
          {events.map((ev, idx) => {
            const cat = ev.category || 'EVENT';
            const catClass = `cat-${cat.toLowerCase()}`;
            const severity = ev.severity;

            return (
              <div key={idx} className={`fp-timeline-entry ${catClass}`}>
                {/* Time Stamp Cell */}
                <div className="fp-entry-time mono">
                  <span className="time-primary">{formatTimeUtc(ev.time)}</span>
                  <span className="time-secondary">{formatDateTimeUtc(ev.time).split(',')[0]}</span>
                </div>

                {/* Node Marker on Spine */}
                <div className="fp-entry-node">
                  <div className={`node-marker ${catClass}`}>
                    {getCategoryIcon(cat)}
                  </div>
                </div>

                {/* Content Strip */}
                <div className="fp-entry-card">
                  <div className="fp-entry-header">
                    <span className={`fp-entry-category mono ${catClass}`}>
                      {cat}
                    </span>
                    <span className="fp-entry-title">{ev.title}</span>
                    {severity && (
                      <span className={`fp-entry-severity mono sev-${severity.toLowerCase()}`}>
                        {severity}
                      </span>
                    )}
                  </div>

                  {ev.detail && (
                    <div className="fp-entry-detail mono">
                      {ev.detail}
                    </div>
                  )}

                  {ev.source && (
                    <div className="fp-entry-meta mono">
                      SOURCE: {ev.source}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
