import React, { useState, useEffect } from 'react';
import { RefreshCw, Radio, Database } from 'lucide-react';

export default function Header({
  systemHealth,
  onRefresh,
  loading,
  mode = 'demo',
  onModeChange,
}) {
  const [utcTime, setUtcTime] = useState('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const h = String(now.getUTCHours()).padStart(2, '0');
      const m = String(now.getUTCMinutes()).padStart(2, '0');
      const s = String(now.getUTCSeconds()).padStart(2, '0');
      setUtcTime(`${h}:${m}:${s} UTC`);
    };

    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const isConnected = systemHealth?.status === 'healthy';

  return (
    <header className="fp-header">
      <div className="fp-header-left">
        <div className="fp-brand-badge">FP-OPS</div>
        <div className="fp-brand-titles">
          <div className="fp-brand-name">
            FLIGHTPULSE <span className="fp-brand-version">v2.4</span>
          </div>
          <div className="fp-brand-desc">
            OPERATIONAL FLIGHT DELAY INTELLIGENCE & GROUNDED INVESTIGATION
          </div>
        </div>

        {/* DEMO / LIVE Mode Switcher */}
        <div className="fp-mode-switcher" role="group" aria-label="Operational Mode">
          <button
            type="button"
            className={`fp-mode-btn ${mode === 'demo' ? 'is-active' : ''} mono`}
            onClick={() => onModeChange && onModeChange('demo')}
            aria-pressed={mode === 'demo'}
          >
            DEMO
          </button>
          <button
            type="button"
            className={`fp-mode-btn mode-live ${mode === 'live' ? 'is-active' : ''} mono`}
            onClick={() => onModeChange && onModeChange('live')}
            aria-pressed={mode === 'live'}
          >
            LIVE
          </button>
        </div>
      </div>

      <div className="fp-header-right">
        <div className="fp-telemetry-item">
          <span className="fp-telemetry-label">UTC CLOCK</span>
          <span className="fp-telemetry-val mono">{utcTime || '—'}</span>
        </div>

        <div className="fp-telemetry-separator"></div>

        <div className="fp-telemetry-item">
          <span className="fp-telemetry-label">DATABASE</span>
          <span className="fp-telemetry-val mono">
            <Database size={11} className="inline-icon" /> POSTGRESQL 17
          </span>
        </div>

        <div className="fp-telemetry-separator"></div>

        <div className="fp-telemetry-item">
          <span className="fp-telemetry-label">API SYSTEM</span>
          <span className={`fp-status-indicator ${isConnected ? 'status-live' : 'status-offline'} mono`}>
            <Radio size={11} className="inline-icon" />
            {isConnected ? 'ONLINE :8000' : 'OFFLINE'}
          </span>
        </div>

        <button
          className={`fp-refresh-btn ${loading ? 'is-loading' : ''}`}
          onClick={onRefresh}
          title="Refresh Operations Feed"
          disabled={loading}
        >
          <RefreshCw size={13} className={loading ? 'spin' : ''} />
          <span className="refresh-btn-label">POLL DATA</span>
        </button>
      </div>
    </header>
  );
}
