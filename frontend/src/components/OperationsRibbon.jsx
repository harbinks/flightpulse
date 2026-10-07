import React from 'react';
import { formatTimeUtc, formatRelativeTime } from '../api';
import { RefreshCw, Radio, AlertTriangle } from 'lucide-react';

export default function OperationsRibbon({
  operationsStatus,
  loading,
  error,
  syncing,
  syncResult,
  onSync,
  onRetryStatus,
}) {
  const sources = operationsStatus?.sources || {};
  const opensky = sources.opensky || {};
  const weather = sources.openmeteo || {};
  const faa = sources.faa || {};

  const renderSourcePill = (name, src) => {
    const rawStatus = (src.status || 'NEVER_SYNCED').toUpperCase();
    let displayStatus = 'NEVER SYNCED';
    let statusClass = 'status-neutral';

    if (rawStatus === 'SUCCESS') {
      displayStatus = 'OK';
      statusClass = 'status-ok';
    } else if (rawStatus === 'FAILED') {
      displayStatus = 'FAILED';
      statusClass = 'status-failed';
    } else if (rawStatus === 'PARTIAL') {
      displayStatus = 'PARTIAL';
      statusClass = 'status-partial';
    }

    const freshness = formatRelativeTime(src.last_attempt);

    return (
      <div className="fp-ribbon-source-item mono">
        <span className="fp-source-name">{name}</span>
        <span className={`fp-source-dot ${statusClass}`}>●</span>
        <span className={`fp-source-status ${statusClass}`}>{displayStatus}</span>
        <span className="fp-source-freshness">{freshness}</span>
      </div>
    );
  };

  const lastSyncFormatted = formatTimeUtc(operationsStatus?.last_sync);

  return (
    <div className="fp-operations-ribbon" role="region" aria-label="Live Operations Telemetry">
      <div className="fp-ribbon-left">
        <div className="fp-ribbon-title mono">
          <Radio size={12} className="inline-icon status-live-pulse" />
          <span>LIVE OPERATIONS</span>
        </div>

        <div className="fp-ribbon-divider"></div>

        {error ? (
          <div className="fp-ribbon-error mono">
            <AlertTriangle size={12} className="inline-icon" />
            <span>OPERATIONS STATUS UNAVAILABLE</span>
            {onRetryStatus && (
              <button type="button" className="fp-ribbon-retry-btn" onClick={onRetryStatus}>
                RETRY
              </button>
            )}
          </div>
        ) : (
          <div className="fp-ribbon-sources">
            {renderSourcePill('OPENSKY', opensky)}
            <div className="fp-ribbon-source-sep">/</div>
            {renderSourcePill('WEATHER', weather)}
            <div className="fp-ribbon-source-sep">/</div>
            {renderSourcePill('FAA NAS', faa)}
          </div>
        )}
      </div>

      <div className="fp-ribbon-right">
        {syncResult && (
          <div className={`fp-sync-result-badge mono result-${syncResult.type}`}>
            {syncResult.message}
          </div>
        )}

        <div className="fp-ribbon-last-sync mono">
          <span className="last-sync-label">LAST SYNC:</span>
          <span className="last-sync-time">{lastSyncFormatted}</span>
        </div>

        <button
          type="button"
          className={`fp-sync-feeds-btn mono ${syncing ? 'is-syncing' : ''}`}
          onClick={onSync}
          disabled={syncing || loading}
          title="Trigger live OpenSky, Open-Meteo, and FAA feed ingestion"
        >
          <RefreshCw size={12} className={syncing ? 'spin' : ''} />
          <span>{syncing ? 'SYNCING LIVE FEEDS…' : 'SYNC LIVE FEEDS'}</span>
        </button>
      </div>
    </div>
  );
}
