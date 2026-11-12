import React, { useState } from "react";
import "./velora-radar.css";

/**
 * Visual navigation only: callers connect sectors to existing Velora modules.
 * No localStorage, network requests, resets or changes to underlying assessment data.
 */
export type VeloraRadarSector = {
  id: string;
  label: string;
  short: string[];
  description: string;
  color: string;
  metric?: string;
};

export type VeloraRadarMetric = {
  label: string;
  value: string;
  description?: string;
};

type VeloraRadarProps = {
  structureName: string;
  mode?: "main" | "macro";
  title?: string;
  description?: string;
  sectors: VeloraRadarSector[];
  metrics?: VeloraRadarMetric[];
  onSelect: (id: string) => void;
  onBack?: () => void;
};

const RADAR_CX = 360;
const RADAR_CY = 360;
const INNER_RADIUS = 133;
const OUTER_RADIUS = 292;

function polar(r: number, degrees: number) {
  const theta = (degrees * Math.PI) / 180;
  return [RADAR_CX + Math.cos(theta) * r, RADAR_CY + Math.sin(theta) * r];
}

function wedgePath(from: number, to: number) {
  const startOuter = polar(OUTER_RADIUS, from);
  const endOuter = polar(OUTER_RADIUS, to);
  const endInner = polar(INNER_RADIUS, to);
  const startInner = polar(INNER_RADIUS, from);
  const largeArc = to - from > 180 ? 1 : 0;
  return [
    \`M \${startOuter[0]} \${startOuter[1]}\`,
    \`A \${OUTER_RADIUS} \${OUTER_RADIUS} 0 \${largeArc} 1 \${endOuter[0]} \${endOuter[1]}\`,
    \`L \${endInner[0]} \${endInner[1]}\`,
    \`A \${INNER_RADIUS} \${INNER_RADIUS} 0 \${largeArc} 0 \${startInner[0]} \${startInner[1]}\`,
    "Z",
  ].join(" ");
}

export default function VeloraRadar({
  structureName,
  mode = "main",
  title = "Scanner di autovalutazione",
  description = "Seleziona uno spicchio per aprire il modulo. Ogni area conserva funzioni, dati e storico già registrati.",
  sectors,
  metrics = [],
  onSelect,
  onBack,
}: VeloraRadarProps) {
  const [pointedId, setPointedId] = useState<string | null>(null);
  const pointed = sectors.find((sector) => sector.id === pointedId) ?? null;
  const perSector = sectors.length ? 360 / sectors.length : 360;

  return (
    <section className="velora-radar" aria-labelledby="velora-radar-heading">
      <header className="velora-radar__header">
        <div>
          <p className="velora-radar__eyebrow">
            <span className="velora-radar__online-indicator" aria-hidden="true" />
            {mode === "macro" ? "Scanner secondo livello" : "Centro di controllo / Navigazione"}
          </p>
          <h2 id="velora-radar-heading">{title}</h2>
          <p>{description}</p>
        </div>
        {onBack && <button type="button" className="velora-radar__back" onClick={onBack}>
          <span aria-hidden="true">←</span> Torna al radar principale
        </button>}
      </header>

      <div className="velora-radar__workspace">
        <div className="velora-radar__circle-panel">
          <div className="velora-radar__circle-heading">
            <span>VELORA / RADAR</span>
            <span>{sectors.length} AREE ATTIVE</span>
          </div>
          <div className="velora-radar__svg-container">
            <svg viewBox="0 0 720 720" className="velora-radar__svg"
                 role="group" aria-label={mode === "macro" ? "Radar macroaree osservabili" : "Radar moduli Velora"}>
              <defs>
                <radialGradient id="velora-radar-background">
                  <stop offset="0%" stopColor="#152c43" />
                  <stop offset="66%" stopColor="#0e1e32" />
                  <stop offset="100%" stopColor="#0a1729" />
                </radialGradient>
                <filter id="velora-radar-glow" x="-60%" y="-60%" width="220%" height="220%">
                  <feGaussianBlur stdDeviation="5" />
                </filter>
              </defs>
              <circle cx={RADAR_CX} cy={RADAR_CY} r="337" fill="url(#velora-radar-background)" stroke="#283e59" strokeWidth="1.5" />
              {[317, 295, 260, 215, 166, 132, 103].map((r) =>
                <circle key={r} cx={RADAR_CX} cy={RADAR_CY} r={r} className="velora-radar__range" />
              )}
              <line x1="360" x2="360" y1="18" y2="702" className="velora-radar__axis" />
              <line x1="18" x2="702" y1="360" y2="360" className="velora-radar__axis" />
              <g className="velora-radar__sweep" aria-hidden="true">
                <path d="M360 360 L360 31 A329 329 0 0 1 523 74 Z" fill="#36ddbd" opacity=".035" />
                <line x1="360" y1="360" x2="360" y2="31" stroke="#46e9c3" strokeWidth="2" opacity=".42" />
              </g>
              {sectors.map((sector, index) => {
                const begin = -90 + index * perSector + 1.6;
                const end = -90 + (index + 1) * perSector - 1.6;
                const midpoint = (begin + end) / 2;
                const [tx, ty] = polar(214, midpoint);
                const active = pointedId === sector.id;
                return (
                  <g
                    key={sector.id}
                    role="button"
                    tabIndex={0}
                    aria-label={\`Apri \${sector.label}\`}
                    className={\`velora-radar__slice\${active ? " is-previewed" : ""}\`}
                    style={{ "--radar-sector": sector.color } as React.CSSProperties}
                    onMouseEnter={() => setPointedId(sector.id)}
                    onMouseLeave={() => setPointedId(null)}
                    onFocus={() => setPointedId(sector.id)}
                    onBlur={() => setPointedId(null)}
                    onClick={() => onSelect(sector.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        onSelect(sector.id);
                      }
                    }}
                  >
                    <title>{sector.label}: {sector.description}</title>
                    <path d={wedgePath(begin, end)} className="velora-radar__slice-fill" />
                    <path d={wedgePath(begin, end)} className="velora-radar__slice-stroke" />
                    <circle cx={...polar(277, midpoint).slice(0,1)} cy={polar(277,midpoint)[1]} r="3.1" fill={sector.color} />
                    <text x={tx} y={ty - ((sector.short.length - 1) * 8)} className="velora-radar__slice-label" textAnchor="middle">
                      {sector.short.map((line, li) => <tspan key={li} x={tx} dy={li === 0 ? 0 : 16}>{line}</tspan>)}
                      {sector.metric && <tspan x={tx} dy="17" className="velora-radar__slice-metric">{sector.metric}</tspan>}
                    </text>
                  </g>
                );
              })}
              <circle cx={RADAR_CX} cy={RADAR_CY} r="127" fill="#0c192c" stroke="#3d607b" strokeWidth="2" />
              <circle cx={RADAR_CX} cy={RADAR_CY} r="117" fill="none" stroke="#4de5c4" strokeWidth="1" strokeDasharray="3 9" opacity=".5" />
              <text x="360" y="312" textAnchor="middle" className="velora-radar__center-kicker">
                {mode === "macro" ? "MACROAREE" : "STRUTTURA ATTIVA"}
              </text>
              <text x="360" y="344" textAnchor="middle" className="velora-radar__center-title">
                {mode === "macro" ? "AUDIT WEB" : "VELORA"}
              </text>
              <text x="360" y="367" textAnchor="middle" className="velora-radar__center-info">
                {mode === "macro" ? \`\${sectors.length} aree osservabili\` : "AUTOVALUTAZIONE"}
              </text>
              <path d="M310 390h100" stroke="#2a6371" />
              <text x="360" y="410" textAnchor="middle" className="velora-radar__center-property">
                {structureName.length > 24 ? structureName.slice(0, 23) + "…" : structureName}
              </text>
            </svg>
          </div>
          <p className="velora-radar__circle-note">
            <span className="velora-radar__online-indicator" aria-hidden="true" />
            Ogni settore apre contenuti reali · Nessun dato viene azzerato o sostituito
          </p>
        </div>

        <aside className="velora-radar__guide" aria-label="Indice dei settori cliccabili">
          <div className="velora-radar__guide-heading">
            <div>
              <span>INDICE OPERATIVO</span>
              <h3>{mode === "macro" ? "Macroaree frontend" : "Aree di autovalutazione"}</h3>
            </div>
            <span className="velora-radar__guide-count">{sectors.length}</span>
          </div>
          <div className="velora-radar__sector-grid">
            {sectors.map((sector, index) =>
              <button
                key={sector.id}
                type="button"
                className={\`velora-radar__sector-button\${pointedId === sector.id ? " is-previewed" : ""}\`}
                style={{ "--radar-sector": sector.color } as React.CSSProperties}
                onMouseEnter={() => setPointedId(sector.id)}
                onMouseLeave={() => setPointedId(null)}
                onFocus={() => setPointedId(sector.id)}
                onBlur={() => setPointedId(null)}
                onClick={() => onSelect(sector.id)}
              >
                <span className="velora-radar__sector-number">{String(index + 1).padStart(2,"0")}</span>
                <span className="velora-radar__sector-copy">
                  <strong>{sector.label}</strong>
                  <small>{sector.description}</small>
                </span>
                <span className="velora-radar__sector-arrow" aria-hidden="true">↗</span>
              </button>
            )}
          </div>
          <div className="velora-radar__focus">
            <p>SETTORE SELEZIONATO</p>
            <h4>{pointed ? pointed.label : "Passa su uno spicchio"}</h4>
            <span>{pointed ? pointed.description : "Puoi cliccare direttamente sulla ruota oppure sui pulsanti dell’indice."}</span>
            {pointed && <button type="button" onClick={() => onSelect(pointed.id)}>Apri questa area →</button>}
          </div>
        </aside>
      </div>

      {metrics.length > 0 && <div className="velora-radar__metrics" aria-label="Riepilogo dati effettivi">
        {metrics.map((metric) => <div className="velora-radar__metric" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
          {metric.description && <small>{metric.description}</small>}
        </div>)}
      </div>}
    </section>
  );
}
