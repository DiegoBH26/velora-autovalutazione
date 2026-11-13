import React, {useRef, useState} from "react";
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
  guideEnabled?: boolean;
  onGuideToggle?: () => void;
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


/* Guida contestuale condivisa fra Archivio, Radar, Intervista, Audit e Scraping.
   È soltanto descrittiva: non esegue comandi o altera le rilevazioni. */
const GUIDE_HINTS: Array<[RegExp, string]> = [
  [/reset scraping|azzera scraping/i, "Cancella, dopo conferma esplicita, le rilevazioni della struttura attiva: prezzi, riscontri OTA, sito diretto e recensioni. Non serve ad aggiornare la pagina."],
  [/scheda non rilevata/i, "Registra che l'operatore non ha individuato una scheda pertinente su questa OTA. Non equivale alla prova definitiva che l'annuncio sia assente."],
  [/apri 5 ota|apri tutte e 5 le ota/i, "Apre la dashboard degli agenti Chrome assistiti e richiede al Companion le cinque schede OTA. Cerca struttura, date e ospiti corretti prima dell'acquisizione."],
  [/acquisisci.*chrome|acquisisci (expedia|vrbo|holidu)/i, "Legge su richiesta la pagina OTA già visibile in Chrome. Non registra automaticamente una tariffa validata: verifica prima nome, date, ospiti e prezzi."],
  [/importa .*tariff|verifica e importa prezzi/i, "Registra i prezzi acquisiti per la struttura attiva, mantenendo la fonte, la valuta e lo stato di verifica. Le condizioni delle camere devono essere confrontate prima di calcolare differenze."],
  [/tariffe puntuali|storico tariffe|tariffe acquisite/i, "Consulta prezzi e condizioni osservati, distinti per OTA, date e camera. Le rilevazioni non verificate non producono delta commerciali affidabili."],
  [/riepilogo mensile/i, "Riepiloga i campioni tariffari e la disponibilità per mese e OTA. Apri per consultare: le date campionate non rappresentano automaticamente tutto il mese."],
  [/asimmetrie/i, "Evidenzia differenze osservate tra sito diretto e OTA. Verifica prima che struttura, camera, date, ospiti e condizioni siano comparabili."],
  [/sito diretto|leonardo/i, "Verifica l'esperienza e le tariffe del sito ufficiale: è il MASTER commerciale da confrontare con Booking e gli altri canali."],
  [/booking engine/i, "È il sistema di prenotazione del sito diretto. Qui si controllano ricerca, disponibilità, camere e prezzi realmente visibili."],
  [/booking/i, "Booking è il primo canale OTA di riferimento. Serve per confrontare gli altri portali, rispettando date, ospiti e unità equivalenti."],
  [/verifica presenza|cerca presenza/i, "Avvia una verifica della presenza di un annuncio. Le schede candidate richiedono comunque la conferma dell'identità della struttura."],
  [/giove|chat agenti/i, "Mostra o registra i passaggi condivisi dagli agenti. Le note di Giove non sostituiscono le verifiche delle tariffe sui portali."],
  [/recensioni/i, "Raccoglie e analizza i riscontri degli ospiti, distinguendo il campione letto dalle conclusioni verificate."],
  [/fotograf|immagini/i, "Esamina la presentazione fotografica e la coerenza dei contenuti visibili sul sito diretto e sulle OTA."],
  [/kpi|revpar|adr|occupazione/i, "Indica le principali misure di performance. La lettura dipende da periodo, qualità e completezza dei dati disponibili."],
  [/report|pdf|esporta/i, "Raccoglie risultati e osservazioni in un documento. Prima di esportarlo controlla la struttura, i dati e le eventuali limitazioni di verifica."],
  [/archivio strutture/i, "Apri e gestisci le schede delle strutture già registrate, con i relativi dati e risultati conservati."],
  [/panoramica|radar/i, "Vista sintetica delle aree dell'analisi: da qui accedi ad audit, KPI, report e altre sezioni operative."],
  [/dati struttura|anagrafica/i, "Controlla nome, località e riferimenti della struttura. Questi dati aiutano gli agenti a identificare la scheda corretta."],
  [/intervista completa|analisi rapida|personalizza intervista/i, "Percorso consulenziale per registrare valutazioni e priorità. Puoi scegliere l'intervista completa o una selezione più breve."],
  [/salva/i, "Salva i dati della sezione corrente. Verifica prima che le informazioni siano associate alla struttura giusta."],
  [/elimina/i, "Rimuove il singolo elemento indicato, non tutto l'archivio. Verifica attentamente la voce prima di procedere."],
];

function guideTextFor(target: HTMLElement): string {
  const custom = target.getAttribute("data-guide")?.trim();
  if (custom) return custom;
  const tag = target.tagName.toLowerCase();
  const labelElement = /^(input|select|textarea)$/.test(tag) ? target.closest("label") : null;
  const label = (
    target.getAttribute("aria-label") ||
    labelElement?.textContent ||
    target.textContent ||
    target.getAttribute("title") ||
    ""
  ).replace(/\\s+/g, " ").trim().slice(0, 150);
  if (!label) return "";
  const title = target.getAttribute("title")?.trim();
  for (const [test, description] of GUIDE_HINTS) {
    if (test.test(label)) return description;
  }
  if (title && title.length > 35) return title;
  if (tag === "summary") return "Apri o chiudi il pannello «" + label + "» per consultare i dettagli senza modificare i dati.";
  if (tag === "input" || tag === "select" || tag === "textarea" || tag === "label")
    return "Campo «" + label + "»: inserisci o verifica l'informazione richiesta per la struttura attiva.";
  if (tag === "a") return "Apre il collegamento «" + label + "».";
  if (tag === "button") return "Comando «" + label + "». Utilizzalo per gestire questa funzione della sezione corrente.";
  return "Area «" + label + "»: consulta il contenuto e gli eventuali dettagli disponibili.";
}

export default function VeloraWorkspace({
  title, description, structureName, status, navigation, guideEnabled = false, onGuideToggle, children
}: VeloraWorkspaceProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [guideTip, setGuideTip] = useState<{text:string;x:number;y:number}|null>(null);
  const lastGuideTarget = useRef<HTMLElement|null>(null);
  function showGuide(event: React.SyntheticEvent<HTMLDivElement>) {
    if (!guideEnabled) return;
    const origin = event.target;
    if (!(origin instanceof HTMLElement)) return;
    const target = origin.closest<HTMLElement>('[data-guide],button,summary,label,input,select,textarea,h1,h2,h3,h4,a');
    if (!target || target.closest('[data-velora-guide-ui]')) {
      if (lastGuideTarget.current) {lastGuideTarget.current=null;setGuideTip(null);}
      return;
    }
    if (lastGuideTarget.current === target) return;
    const explanation = guideTextFor(target);
    if (!explanation) return;
    lastGuideTarget.current = target;
    const bounds = target.getBoundingClientRect();
    const nearSidebar = Boolean(target.closest('.velora-workspace__sidebar'));
    const x = Math.max(14, Math.min(nearSidebar ? bounds.right+12 : bounds.left, window.innerWidth-354));
    const y = bounds.bottom+12 < window.innerHeight-170 ? bounds.bottom+10 : Math.max(12,bounds.top-160);
    setGuideTip({text:explanation,x,y});
  }
  function hideGuide() {lastGuideTarget.current=null;setGuideTip(null);}
  return (
    <div className={"velora-workspace" + (collapsed ? " velora-workspace--collapsed" : "") + (guideEnabled ? " velora-workspace--guide-enabled" : "")}
      onPointerOver={showGuide} onPointerLeave={hideGuide} onFocusCapture={showGuide} onBlurCapture={hideGuide}
      onKeyDown={event=>{if(event.key==="Escape")hideGuide();}}>
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
            data-guide={item.label + ": " + (item.description || "Apri la sezione selezionata") + ". Premi per accedere alla relativa area operativa."}
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
            {onGuideToggle && <button type="button" data-velora-guide-ui
              className="velora-workspace__guide-toggle" aria-pressed={guideEnabled}
              title={guideEnabled?"Disattiva la guida contestuale":"Attiva la guida contestuale"}
              onClick={()=>{hideGuide();onGuideToggle();}}>
              <span aria-hidden="true" className="velora-workspace__guide-question">?</span>
              {guideEnabled?"Guida attiva":"Attiva guida"}
            </button>}
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
        {guideEnabled && guideTip && <div data-velora-guide-ui role="tooltip" className="velora-workspace__guide-tooltip"
          style={{left:guideTip.x,top:guideTip.y}}>{guideTip.text}</div>}
      </div>
    </div>
  );
}
