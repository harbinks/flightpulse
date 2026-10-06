import React from 'react';
import { formatTimeUtc } from '../api';

export default function WeatherPanel({ weather, loading }) {
  if (loading) {
    return (
      <div className="fp-panel-state">
        <span className="mono">ACQUIRING METAR TELEMETRY...</span>
      </div>
    );
  }

  const originObs = weather?.origin_observations || [];
  const originStation = weather?.origin_airport || 'ORIGIN';

  return (
    <div className="fp-weather-module">
      <div className="fp-module-header">
        <div className="fp-module-title-wrap">
          <span className="fp-module-kicker mono">METEOROLOGICAL OBSERVATIONS (METAR)</span>
          <h4 className="fp-module-heading">
            STATION {originStation} ATMOSPHERIC TELEMETRY
          </h4>
        </div>
        <div className="fp-module-count mono">
          {originObs.length} METAR RECORDS
        </div>
      </div>

      {originObs.length === 0 ? (
        <div className="fp-panel-state is-empty">
          <span className="mono">NO ABNORMAL METAR OBSERVATIONS RECORDED AT {originStation}</span>
        </div>
      ) : (
        <div className="fp-weather-telemetry-grid">
          {originObs.map((obs) => {
            const isSevere =
              obs.condition_code === 'THUNDERSTORM' ||
              obs.condition_code === 'HEAVY_RAIN' ||
              (obs.wind_gust_knots && obs.wind_gust_knots >= 35);

            return (
              <div
                key={obs.id}
                className={`fp-telemetry-card ${isSevere ? 'is-severe' : ''}`}
              >
                <div className="fp-card-header mono">
                  <span className="station-time">
                    {obs.airport_code} / {formatTimeUtc(obs.observation_time)}
                  </span>
                  <span
                    className={`condition-pill ${
                      isSevere ? 'pill-severe' : 'pill-standard'
                    }`}
                  >
                    {obs.condition_code || 'CLEAR'}
                  </span>
                </div>

                <div className="fp-telemetry-metrics-matrix mono">
                  <div className="metric-cell">
                    <span className="metric-tag">TEMP</span>
                    <span className="metric-num">
                      {obs.temperature_c != null ? `${obs.temperature_c}°C` : '—'}
                    </span>
                  </div>

                  <div className="metric-cell">
                    <span className="metric-tag">WIND</span>
                    <span className="metric-num">
                      {obs.wind_speed_knots != null ? `${obs.wind_speed_knots} KT` : '—'}
                    </span>
                  </div>

                  <div className="metric-cell">
                    <span className="metric-tag">GUST</span>
                    <span className={`metric-num ${obs.wind_gust_knots >= 30 ? 'text-severe' : ''}`}>
                      {obs.wind_gust_knots != null ? `${obs.wind_gust_knots} KT` : 'CALM'}
                    </span>
                  </div>

                  <div className="metric-cell">
                    <span className="metric-tag">VIS</span>
                    <span className={`metric-num ${obs.visibility_miles <= 3 ? 'text-severe' : ''}`}>
                      {obs.visibility_miles != null ? `${obs.visibility_miles} MI` : '—'}
                    </span>
                  </div>

                  <div className="metric-cell">
                    <span className="metric-tag">QNH</span>
                    <span className="metric-num">
                      {obs.altimeter_inhg != null ? `${obs.altimeter_inhg} IN` : '—'}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
