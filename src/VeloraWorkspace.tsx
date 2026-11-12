import React, {useState} from "react";
import "./workspace-dark.css";

/**
 * Velora visual shell only.
 * The interview, agents, reports and their existing storage remain in App.tsx.
 */
export type WorkspaceNavigationItem = {
  id: string;
  label: string;
  description?: string;
  onClick: () => void;
  active?: boolean;
};

type VeloraWorkspaceProps = {
  title: string;
  description: string;
  structureName?: string;
  status?: string;
  navigation: WorkspaceNavigationItem[];
  children: React.ReactNode;
};

const paths: Record<string, string> = {
  archivio: "M4 7h16v13H4z M4 11h16 M9 3h6l1 4H8z",
  nuova: "M12 5v14 M5 12h14",
  panoramica: "M3 3h8v8H3z M13 3h8v5h-8z M13 10h8v11h-8z M3 13h8v8H3z",
  struttura: "M3 21h18 M5 21V7l7-4 7 4v14 M9 21v-7h6v7 M8 9h.01 M16 9h.01",
  intervista: "M8 4H5v17h14V4h-3 M9 3h6v4H9z M8 12h8 M8 16h6",
  personalizza: "M4 7h16 M4 17h16 M9 4v6 M15 14v6",
  rapida: "m13 2-9 12h7l-1 8 10-12h-7z",
  audit: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z M2 12h20 M12 2c-3 3-4.5 7-4.5 10s1.5 7 4.5 10 M12 2c3 3 4.5 7 4.5 10s-1.5 7-4.5 10",
  scraping: "M4 5h16v4H4z M4 11h16v4H4z M4 17h16v3H4z",
  report: "M6 2h8l4 4v16H6z M14 2v5h5 M9 12h6 M9 16h6",
  torna: "M14 6 8 12l6 6 M8 12h13"
};

function WorkspaceGlyph({name}: {name: string}) {
  return <svg className="velora-workspace__glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d={paths[name] || paths.panoramica} />
  </svg>;
}

export default function VeloraWorkspace({
  title, description, structureName, status, navigation, children
}: VeloraWorkspaceProps) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <div className={"velora-workspace" + (collapsed ? " velora-workspace--collapsed" : "")}>
      <a href="#velora-workspace-content" className="velora-workspace__skip">Vai ai contenuti</a>
      <aside className="velora-workspace__sidebar" aria-label="Menu Velora Autovalutazione">
        <div className="velora-workspace__brand">
          <div className="velora-workspace__logo" aria-hidden="true">V</div>
          <div className="velora-workspace__brand-copy">
            <strong>VELORA</strong>
            <span>AUTOVALUTAZIONE</span>
            <span className="velora-workspace__ui-version">RADAR · R6</span>
          </div>
          <button type="button" className="velora-workspace__collapse" onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "Espandi menu" : "Comprimi menu"} title={collapsed ? "Espandi menu" : "Comprimi menu"}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
              <path d={collapsed ? "M8 5l7 7-7 7" : "M16 5l-7 7 7 7"} />
            </svg>
          </button>
        </div>
        <p className="velora-workspace__nav-heading">PERCORSO DI VALUTAZIONE</p>
        <nav className="velora-workspace__nav" aria-label="Sezioni operative">
          {navigation.map(item => <button key={item.id} type="button"
            className={"velora-workspace__nav-button" + (item.active ? " is-active" : "")}
            onClick={item.onClick}
            aria-current={item.active ? "page" : undefined}
            title={item.label}>
            <WorkspaceGlyph name={item.id} />
            <span className="velora-workspace__nav-copy"><strong>{item.label}</strong>
              {item.description && <small>{item.description}</small>}
            </span>
            {item.active && <span className="velora-workspace__nav-rail" />}
          </button>)}
        </nav>
        <div className="velora-workspace__sidebar-footer">
          <div className="velora-workspace__safemark">✓</div>
          <div className="velora-workspace__sidebar-footer-copy"><strong>Ambiente di lavoro</strong>
            <span>Interviste, scraping e archivio nello stesso sistema.</span>
          </div>
        </div>
      </aside>

      <div className="velora-workspace__stage">
        <header className="velora-workspace__topbar">
          <div className="velora-workspace__topbar-main">
            <div className="velora-workspace__breadcrumbs"><span>Velora</span><span>/</span><span>Autovalutazione</span></div>
            <h1>{title}</h1>
            <p>{description}</p>
          </div>
          <div className="velora-workspace__context">
            {structureName && <div className="velora-workspace__property-chip">
              <span className="velora-workspace__property-dot" />
              <span className="velora-workspace__property-label"><small>Struttura attiva</small><strong>{structureName}</strong></span>
            </div>}
            {status && <div className="velora-workspace__status"><i aria-hidden="true"/>{status}</div>}
          </div>
        </header>
        <div className="velora-workspace__content" id="velora-workspace-content">
          {children}
        </div>
      </div>
    </div>
  );
}
