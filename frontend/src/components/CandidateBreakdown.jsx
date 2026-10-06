import React from 'react';
import { CheckCircle2 } from 'lucide-react';

export default function CandidateBreakdown({ intelligence, loading }) {
  if (loading) {
    return (
      <div className="fp-panel-state">
        <span className="mono">COMPUTING DETERMINISTIC CANDIDATE HYPOTHESES...</span>
      </div>
    );
  }

  const candidates = intelligence?.candidates || [];

  return (
    <div className="fp-candidates-module">
      <div className="fp-module-header">
        <div className="fp-module-title-wrap">
          <span className="fp-module-kicker mono">DETERMINISTIC EVALUATION ENGINE</span>
          <h4 className="fp-module-heading">SCORING MATRIX OF CANDIDATE CAUSES</h4>
        </div>
        <div className="fp-module-count mono">
          {candidates.length} EVALUATED HYPOTHESES
        </div>
      </div>

      <div className="fp-candidates-grid">
        {candidates.map((cand, idx) => {
          const scorePercent = Math.round((cand.score || 0) * 100);
          const conf = cand.confidence || 'LOW';

          return (
            <div key={idx} className="fp-candidate-card">
              <div className="fp-candidate-header">
                <div className="fp-candidate-rank mono">#{idx + 1}</div>

                <div className="fp-candidate-meta">
                  <div className="fp-candidate-name mono">{cand.category}</div>
                  <div className="fp-candidate-signal mono">
                    SIGNAL: {cand.primary_signal || 'EMPIRICAL LOGS'}
                  </div>
                </div>

                <div className="fp-candidate-scores mono">
                  <span className={`fp-cand-conf conf-${conf.toLowerCase()}`}>
                    {conf}
                  </span>
                  <span className="fp-cand-pct">{scorePercent}%</span>
                </div>
              </div>

              {/* Progress bar visual */}
              <div className="fp-score-bar-track">
                <div
                  className="fp-score-bar-fill"
                  style={{ width: `${Math.max(scorePercent, 4)}%` }}
                ></div>
              </div>

              {/* Evidence points */}
              <div className="fp-cand-evidence-list">
                {cand.evidence && cand.evidence.length > 0 ? (
                  cand.evidence.map((ev, i) => (
                    <div key={i} className="fp-cand-ev-item mono">
                      <CheckCircle2 size={11} className="cand-ev-icon" />
                      <span>{ev}</span>
                    </div>
                  ))
                ) : (
                  <div className="fp-cand-ev-empty mono">
                    No corroborating evidence detected. Hypothesis rejected.
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
