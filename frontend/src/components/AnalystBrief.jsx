import React from 'react';
import { Terminal, Shield, CheckCircle, AlertTriangle, Cpu } from 'lucide-react';

export default function AnalystBrief({
  aiAnalysis,
  loading,
  error,
  deterministicIntelligence,
  onRetry,
}) {
  // Loading State
  if (loading) {
    return (
      <div className="fp-analyst-panel is-loading">
        <div className="fp-analyst-header">
          <div className="fp-analyst-title-wrap">
            <span className="fp-analyst-kicker mono">LOCAL LLM SYNTHESIS</span>
            <h3 className="fp-analyst-heading">FLIGHTPULSE ANALYST</h3>
          </div>
          <div className="fp-analyst-status-badge mono loading-badge">
            <span className="pulse-dot"></span> ANALYZING EVIDENCE
          </div>
        </div>

        <div className="fp-analyst-loading-body">
          <div className="fp-loading-bar-track">
            <div className="fp-loading-bar-fill"></div>
          </div>
          <div className="fp-loading-text mono">
            SYNTHESIZING OPERATIONAL EVIDENCE & ATM TELEMETRY...
          </div>
          <div className="fp-loading-subtext">
            Compiling METAR records, FAA NAS advisories, and carrier claims into grounded dossier.
          </div>
        </div>
      </div>
    );
  }

  // Determine if Ollama succeeded or fell back
  const isAvailable = aiAnalysis && aiAnalysis.status === 'success';
  const isOffline = aiAnalysis && aiAnalysis.status === 'unavailable';
  const isError = aiAnalysis && aiAnalysis.status === 'error';

  // Analysis data from AI or deterministic fallback
  const analysis = aiAnalysis?.analysis || null;
  const primaryCause = analysis?.primary_cause || deterministicIntelligence?.primary_candidate?.category || 'UNKNOWN';
  const confidence = analysis?.confidence || deterministicIntelligence?.primary_candidate?.confidence || 'INSUFFICIENT';
  const summary = analysis?.summary || deterministicIntelligence?.explanation_summary || 'Analysis currently unavailable.';
  const explanation = analysis?.explanation || deterministicIntelligence?.explanation_summary || '';
  const evidenceList = analysis?.evidence_used || (deterministicIntelligence?.candidates?.[0]?.evidence || []);
  const limitations = analysis?.limitations || [];

  const modelUsed = aiAnalysis?.model_used || 'DETERMINISTIC ENGINE';
  const latencyMs = aiAnalysis?.execution_time_ms ? `${aiAnalysis.execution_time_ms.toFixed(0)} ms` : null;

  return (
    <div className="fp-analyst-panel">
      {/* Header Bar */}
      <div className="fp-analyst-header">
        <div className="fp-analyst-title-wrap">
          <div className="fp-analyst-kicker-row">
            <span className="fp-analyst-kicker mono">GROUNDED OPERATIONAL DOSSIER</span>
            <span className="fp-grounding-tag mono">
              <Shield size={11} className="inline-icon" /> 100% GROUNDED
            </span>
          </div>
          <h3 className="fp-analyst-heading">FLIGHTPULSE ANALYST</h3>
        </div>

        {/* Telemetry Badge / Status */}
        <div className="fp-analyst-telemetry mono">
          {isAvailable ? (
            <div className="fp-model-telemetry">
              <span className="fp-telemetry-chip model-chip">
                <Cpu size={11} className="inline-icon" /> {modelUsed}
              </span>
              {latencyMs && (
                <span className="fp-telemetry-chip latency-chip">{latencyMs}</span>
              )}
            </div>
          ) : (
            <div className="fp-fallback-telemetry">
              <span className="fp-telemetry-chip offline-chip">
                ANALYST OFFLINE / DETERMINISTIC FALLBACK
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Offline / Fallback Advisory Banner (Shown when Ollama is offline or times out) */}
      {(isOffline || isError) && (
        <div className="fp-analyst-offline-banner">
          <div className="fp-banner-icon-cell">
            <AlertTriangle size={15} />
          </div>
          <div className="fp-banner-content">
            <div className="fp-offline-title mono">
              {isError ? 'ANALYST SERVICE ERROR — DETERMINISTIC ENGINE ACTIVE' : 'ANALYST DAEMON OFFLINE — DETERMINISTIC ENGINE ACTIVE'}
            </div>
            <div className="fp-offline-desc">
              {error ? `Detail: ${error}. ` : ''}
              Local Ollama service was unavailable or timed out. FlightPulse deterministic multi-signal intelligence remains authoritative and fully rendered below.
            </div>
          </div>
          {onRetry && (
            <button type="button" className="fp-refresh-btn mono" onClick={onRetry} style={{ marginLeft: 'auto' }}>
              RETRY LLM
            </button>
          )}
        </div>
      )}

      {/* Main Analytical Content */}
      <div className="fp-analyst-body">
        {/* Executive Summary Callout */}
        <div className="fp-executive-summary">
          <div className="fp-summary-label mono">EXECUTIVE OPERATIONAL BRIEFING</div>
          <div className="fp-summary-text">{summary}</div>
        </div>

        {/* Attribution Anchor Grid */}
        <div className="fp-analyst-anchor-grid">
          <div className="fp-anchor-cell">
            <span className="fp-anchor-label mono">PRIMARY ATTRIBUTED CAUSE</span>
            <span className="fp-anchor-val cause-val mono">{primaryCause}</span>
          </div>
          <div className="fp-anchor-cell">
            <span className="fp-anchor-label mono">CORRELATION CONFIDENCE</span>
            <span className={`fp-anchor-val conf-val conf-${confidence.toLowerCase()} mono`}>
              {confidence}
            </span>
          </div>
        </div>

        {/* Detailed Narrative Explanation */}
        {explanation && (
          <div className="fp-analyst-narrative-block">
            <span className="fp-narrative-label mono">INVESTIGATIVE BREAKDOWN</span>
            <p className="fp-narrative-text">{explanation}</p>
          </div>
        )}

        {/* Operational Evidence Records (Rendered as factual telemetry references) */}
        <div className="fp-evidence-dossier">
          <div className="fp-evidence-dossier-header">
            <span className="fp-evidence-label mono">
              SUPPORTING OPERATIONAL EVIDENCE ({evidenceList.length})
            </span>
            <span className="fp-evidence-sub mono">STRICT FACTUAL CITATIONS</span>
          </div>

          {evidenceList && evidenceList.length > 0 ? (
            <div className="fp-evidence-records-grid">
              {evidenceList.map((item, idx) => (
                <div key={idx} className="fp-evidence-record">
                  <div className="fp-record-bullet">
                    <CheckCircle size={13} className="bullet-check" />
                  </div>
                  <div className="fp-record-text mono">{item}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="fp-evidence-empty mono">
              No corroborating atmospheric or air traffic advisories logged in database.
            </div>
          )}
        </div>

        {/* Known Operational Limitations & Uncertainties */}
        {limitations && limitations.length > 0 && (
          <div className="fp-limitations-block">
            <div className="fp-limitations-header mono">
              OPERATIONAL UNCERTAINTIES & BOUNDING LIMITATIONS
            </div>
            <ul className="fp-limitations-list">
              {limitations.map((lim, idx) => (
                <li key={idx} className="fp-limitation-item">
                  {lim}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Footer Audit Protocol */}
      <div className="fp-analyst-footer">
        <span className="fp-audit-line mono">
          <Terminal size={12} className="inline-icon" /> AUDIT PROVENANCE: Strictly bounded by deterministic facts. Causality anchored to engine evaluation.
        </span>
      </div>
    </div>
  );
}
