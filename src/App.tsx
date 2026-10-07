import React, { useEffect, useMemo, useState } from "react";
import santantonioAudit from "./santantonio-audit.json";
import santantonioReportUrl from "./santantonio-report.pdf?url";
import perlaAudit from "./perla-saracena-audit.json";
import perlaReportUrl from "./perla-saracena-report.pdf?url";
import braAudit from "./bra-hotel-audit.json";
import braReportUrl from "./bra-hotel-report.pdf?url";
import { buildRateComparisonRows } from "./rate-comparison";

declare global {
  interface Window {
    veloraDesktop?: {
      savePdf: (
        html: string,
        suggestedName?: string
      ) => Promise<{ ok: boolean; filePath?: string; canceled?: boolean; error?: string }>;
    };
  }
}

type AssessmentMode = "full" | "quick-hotel-bb" | "web-audit";
type AuditData = typeof santantonioAudit | typeof perlaAudit | typeof braAudit;

const LOCAL_AGENT_BASE = "http://127.0.0.1:8768";
function localAgentUrl(path: string): string {
  return window.location.hostname === "127.0.0.1" && window.location.port === "8768" ? path : LOCAL_AGENT_BASE + path;
}

type AuditStatus = "" | "present" | "partial" | "missing" | "unverified" | "not-applicable";

type AssessmentItem = {
  id: string;
  text: string;
};

type AssessmentCategory = {
  id: string;
  title: string;
  items: AssessmentItem[];
};

type AssessmentMacro = {
  id: string;
  title: string;
  categories: AssessmentCategory[];
};

type Answer = {
  importance: number;
  current: number;
  fit: number;
  note: string;
  auditStatus?: AuditStatus;
};

type OwnerInfo = {
  propertyName: string;
  ownerName: string;
  consultantName: string;
  location: string;
  city: string;
  province: string;
  propertyType: string;
  rooms: string;
  channels: string;
  objective: string;
};

const EMPTY_OWNER_INFO: OwnerInfo = {
  propertyName: "",
  ownerName: "",
  consultantName: "",
  location: "",
  city: "",
  province: "",
  propertyType: "",
  rooms: "",
  channels: "",
  objective: "",
};

const ASSESSMENT_DATA: AssessmentMacro[] = [
  {
    "id": "m4",
    "title": "MARKETING & POSIZIONAMENTO STRUTTURA",
    "categories": [
      {
        "id": "c5",
        "title": "Branding struttura ricettiva",
        "items": [
          {
            "id": "q6",
            "text": "Posizionamento"
          },
          {
            "id": "q7",
            "text": "Target ospite"
          },
          {
            "id": "q8",
            "text": "Promessa di soggiorno"
          },
          {
            "id": "q9",
            "text": "Identità territoriale"
          },
          {
            "id": "q10",
            "text": "Strategia Ocean Blue (associato a raggiungimento USP)"
          }
        ]
      },
      {
        "id": "c11",
        "title": "Sito ufficiale direct booking",
        "items": [
          {
            "id": "q12",
            "text": "UX mobile"
          },
          {
            "id": "q13",
            "text": "Booking engine"
          },
          {
            "id": "q14",
            "text": "Camere/tariffe"
          },
          {
            "id": "q15",
            "text": "Trust elements"
          },
          {
            "id": "q16",
            "text": "Conversione prenotazioni dirette"
          }
        ]
      },
      {
        "id": "c17",
        "title": "Infrastruttura digitale",
        "items": [
          {
            "id": "q18",
            "text": "Hosting"
          },
          {
            "id": "q19",
            "text": "Dominio"
          },
          {
            "id": "q20",
            "text": "SSL"
          },
          {
            "id": "q21",
            "text": "Cookie/GDPR"
          },
          {
            "id": "q22",
            "text": "Privacy"
          },
          {
            "id": "q23",
            "text": "Licenze software"
          },
          {
            "id": "q24",
            "text": "Tracciamenti marketing"
          }
        ]
      }
    ]
  },
  {
    "id": "m25",
    "title": "PMS / STACK OPERATIVO RICETTIVO",
    "categories": [
      {
        "id": "c26",
        "title": "Calendario unificato disponibilità camere/unità",
        "items": [
          {
            "id": "q27",
            "text": "Calendario unificato disponibilità camere/unità"
          },
          {
            "id": "q28",
            "text": "Allotment"
          },
          {
            "id": "q29",
            "text": "Stop-sale"
          },
          {
            "id": "q30",
            "text": "Minimum stay"
          },
          {
            "id": "q31",
            "text": "Blocchi operativi"
          }
        ]
      },
      {
        "id": "c32",
        "title": "Gestione prenotazioni",
        "items": [
          {
            "id": "q33",
            "text": "Conferme"
          },
          {
            "id": "q34",
            "text": "Modifiche"
          },
          {
            "id": "q35",
            "text": "Cancellazioni"
          },
          {
            "id": "q36",
            "text": "No-show"
          },
          {
            "id": "q37",
            "text": "Policy tariffarie"
          },
          {
            "id": "q38",
            "text": "Note operative"
          }
        ]
      },
      {
        "id": "c39",
        "title": "Channel Manager integrato",
        "items": [
          {
            "id": "q40",
            "text": "Sincronizzazione OTA"
          },
          {
            "id": "q41",
            "text": "Sito diretto"
          },
          {
            "id": "q42",
            "text": "Metasearch"
          },
          {
            "id": "q43",
            "text": "Allotment"
          },
          {
            "id": "q44",
            "text": "Restrizioni tariffarie"
          }
        ]
      },
      {
        "id": "c45",
        "title": "Pricing e revenue management",
        "items": [
          {
            "id": "q46",
            "text": "Listini"
          },
          {
            "id": "q47",
            "text": "BAR"
          },
          {
            "id": "q48",
            "text": "Piani tariffari"
          },
          {
            "id": "q49",
            "text": "Supplementi"
          },
          {
            "id": "q50",
            "text": "Occupancy"
          },
          {
            "id": "q51",
            "text": "Compressione domanda"
          }
        ]
      },
      {
        "id": "c52",
        "title": "Anagrafiche camere/unità",
        "items": [
          {
            "id": "q53",
            "text": "Tipologie"
          },
          {
            "id": "q54",
            "text": "Dotazioni"
          },
          {
            "id": "q55",
            "text": "Capienza"
          },
          {
            "id": "q56",
            "text": "Servizi"
          },
          {
            "id": "q57",
            "text": "Foto"
          },
          {
            "id": "q58",
            "text": "Amenities"
          },
          {
            "id": "q59",
            "text": "Standard vendita"
          }
        ]
      },
      {
        "id": "c60",
        "title": "Contabilità e fatturazione ospiti",
        "items": [
          {
            "id": "q61",
            "text": "Acconti"
          },
          {
            "id": "q62",
            "text": "Saldo"
          },
          {
            "id": "q63",
            "text": "Ricevute"
          },
          {
            "id": "q64",
            "text": "Fatture"
          },
          {
            "id": "q65",
            "text": "Split payment"
          },
          {
            "id": "q66",
            "text": "Note credito"
          },
          {
            "id": "q67",
            "text": "Riconciliazioni"
          }
        ]
      },
      {
        "id": "c68",
        "title": "Gestione proprietà/direzione",
        "items": [
          {
            "id": "q69",
            "text": "Marginalità"
          },
          {
            "id": "q70",
            "text": "Report economici"
          },
          {
            "id": "q71",
            "text": "Budget"
          },
          {
            "id": "q72",
            "text": "Forecast"
          },
          {
            "id": "q73",
            "text": "Decisioni commerciali"
          }
        ]
      },
      {
        "id": "c74",
        "title": "Gestione ospiti",
        "items": [
          {
            "id": "q75",
            "text": "Guest journey"
          },
          {
            "id": "q76",
            "text": "Documenti"
          },
          {
            "id": "q77",
            "text": "Preferenze"
          },
          {
            "id": "q78",
            "text": "Consensi"
          },
          {
            "id": "q79",
            "text": "Comunicazioni"
          },
          {
            "id": "q80",
            "text": "Storico soggiorni"
          }
        ]
      },
      {
        "id": "c81",
        "title": "Operations e housekeeping",
        "items": [
          {
            "id": "q82",
            "text": "Planning pulizie"
          },
          {
            "id": "q83",
            "text": "Cambio biancheria"
          },
          {
            "id": "q84",
            "text": "Camere pronte"
          },
          {
            "id": "q85",
            "text": "Extra"
          },
          {
            "id": "q86",
            "text": "Priorità arrivi"
          }
        ]
      },
      {
        "id": "c87",
        "title": "Reportistica direzionale",
        "items": [
          {
            "id": "q88",
            "text": "ADR"
          },
          {
            "id": "q89",
            "text": "RevPAR"
          },
          {
            "id": "q90",
            "text": "TrevPAR"
          },
          {
            "id": "q91",
            "text": "GopPAR"
          },
          {
            "id": "q92",
            "text": "Occupancy"
          },
          {
            "id": "q93",
            "text": "Pickup"
          },
          {
            "id": "q94",
            "text": "Cancellazioni"
          },
          {
            "id": "q95",
            "text": "Produzione per canale"
          },
          {
            "id": "q96",
            "text": "Marginalità"
          }
        ]
      },
      {
        "id": "c97",
        "title": "Integrazioni istituzionali",
        "items": [
          {
            "id": "q98",
            "text": "Alloggiati Web"
          },
          {
            "id": "q99",
            "text": "ISTAT"
          },
          {
            "id": "q100",
            "text": "Tassa di soggiorno"
          },
          {
            "id": "q101",
            "text": "Portali comunali"
          },
          {
            "id": "q102",
            "text": "Flussi obbligatori"
          }
        ]
      },
      {
        "id": "c103",
        "title": "Modulo contratti e documentale",
        "items": [
          {
            "id": "q104",
            "text": "Condizioni di soggiorno"
          },
          {
            "id": "q105",
            "text": "Liberatorie"
          },
          {
            "id": "q106",
            "text": "Informative"
          },
          {
            "id": "q107",
            "text": "Policy"
          },
          {
            "id": "q108",
            "text": "Archiviazione digitale"
          }
        ]
      },
      {
        "id": "c109",
        "title": "Sicurezza e permessi",
        "items": [
          {
            "id": "q110",
            "text": "Ruoli staff"
          },
          {
            "id": "q111",
            "text": "Accessi PMS"
          },
          {
            "id": "q112",
            "text": "Log operativi"
          },
          {
            "id": "q113",
            "text": "Protezione dati ospiti"
          },
          {
            "id": "q114",
            "text": "Procedure interne"
          }
        ]
      }
    ]
  },
  {
    "id": "m115",
    "title": "MODULISTICA & CONSULENZA PER STRUTTURE",
    "categories": [
      {
        "id": "c116",
        "title": "Contrattualistica ospite",
        "items": [
          {
            "id": "q117",
            "text": "Condizioni prenotazione"
          },
          {
            "id": "q118",
            "text": "Penali"
          },
          {
            "id": "q119",
            "text": "Cauzioni"
          },
          {
            "id": "q120",
            "text": "House rules"
          },
          {
            "id": "q121",
            "text": "Privacy"
          },
          {
            "id": "q122",
            "text": "Consenso marketing"
          }
        ]
      },
      {
        "id": "c123",
        "title": "Contratti fornitori",
        "items": [
          {
            "id": "q124",
            "text": "Lavanderia"
          },
          {
            "id": "q125",
            "text": "Pulizie"
          },
          {
            "id": "q126",
            "text": "Manutentori"
          },
          {
            "id": "q127",
            "text": "Transfer"
          },
          {
            "id": "q128",
            "text": "Tour"
          },
          {
            "id": "q129",
            "text": "Ristorazione"
          },
          {
            "id": "q130",
            "text": "SLA"
          },
          {
            "id": "q131",
            "text": "Livelli di servizio"
          }
        ]
      },
      {
        "id": "c132",
        "title": "Partnership B2B per vendita camere/esperienze",
        "items": [
          {
            "id": "q133",
            "text": "Agenzie viaggio"
          },
          {
            "id": "q134",
            "text": "DMC"
          },
          {
            "id": "q135",
            "text": "Aziende"
          },
          {
            "id": "q136",
            "text": "Wedding planner"
          },
          {
            "id": "q137",
            "text": "Tour operator"
          }
        ]
      },
      {
        "id": "c138",
        "title": "Assistenza legale, fiscale e normativa",
        "items": [
          {
            "id": "q139",
            "text": "Classificazione struttura"
          },
          {
            "id": "q140",
            "text": "SCIA"
          },
          {
            "id": "q141",
            "text": "CIR/CIN"
          },
          {
            "id": "q142",
            "text": "Imposta soggiorno"
          },
          {
            "id": "q143",
            "text": "Adempimenti locali"
          }
        ]
      }
    ]
  },
  {
    "id": "m144",
    "title": "ACQUISIZIONE / SVILUPPO OFFERTA RICETTIVA",
    "categories": [
      {
        "id": "c145",
        "title": "Analisi prodotto ricettivo",
        "items": [
          {
            "id": "q146",
            "text": "Camere/unità"
          },
          {
            "id": "q147",
            "text": "Location"
          },
          {
            "id": "q148",
            "text": "Servizi"
          },
          {
            "id": "q149",
            "text": "Target ospite"
          },
          {
            "id": "q150",
            "text": "Stagionalità"
          },
          {
            "id": "q151",
            "text": "Competitività territoriale"
          }
        ]
      },
      {
        "id": "c152",
        "title": "Analisi potenziale economico",
        "items": [
          {
            "id": "q153",
            "text": "ADR atteso"
          },
          {
            "id": "q154",
            "text": "Occupancy"
          },
          {
            "id": "q155",
            "text": "RevPAR"
          },
          {
            "id": "q156",
            "text": "Costi operativi"
          },
          {
            "id": "q157",
            "text": "Margine"
          },
          {
            "id": "q158",
            "text": "Break-even"
          }
        ]
      },
      {
        "id": "c159",
        "title": "Business plan per proprietà/direzione",
        "items": [
          {
            "id": "q160",
            "text": "Scenari tariffari"
          },
          {
            "id": "q161",
            "text": "Budget annuale"
          },
          {
            "id": "q162",
            "text": "Forecast"
          },
          {
            "id": "q163",
            "text": "Piano di rientro investimenti"
          }
        ]
      },
      {
        "id": "c164",
        "title": "Formalizzazione accordi commerciali",
        "items": [
          {
            "id": "q165",
            "text": "Gestione"
          },
          {
            "id": "q166",
            "text": "Revenue"
          },
          {
            "id": "q167",
            "text": "Marketing"
          },
          {
            "id": "q168",
            "text": "Commissioni"
          },
          {
            "id": "q169",
            "text": "Fee"
          },
          {
            "id": "q170",
            "text": "Responsabilità operative"
          }
        ]
      },
      {
        "id": "c171",
        "title": "Raccolta documentale",
        "items": [
          {
            "id": "q172",
            "text": "Planimetrie"
          },
          {
            "id": "q173",
            "text": "Autorizzazioni"
          },
          {
            "id": "q174",
            "text": "Visure"
          },
          {
            "id": "q175",
            "text": "Documenti titolare"
          },
          {
            "id": "q176",
            "text": "Certificazioni impianti"
          },
          {
            "id": "q177",
            "text": "Polizze"
          }
        ]
      },
      {
        "id": "c178",
        "title": "Prescrizioni sicurezza struttura",
        "items": [
          {
            "id": "q179",
            "text": "Antincendio"
          },
          {
            "id": "q180",
            "text": "Estintori"
          },
          {
            "id": "q181",
            "text": "Segnaletica"
          },
          {
            "id": "q182",
            "text": "Cassette primo soccorso"
          },
          {
            "id": "q183",
            "text": "Accessi"
          },
          {
            "id": "q184",
            "text": "Procedure emergenza"
          }
        ]
      },
      {
        "id": "c185",
        "title": "Onboarding iniziale in PMS",
        "items": [
          {
            "id": "q186",
            "text": "Creazione struttura"
          },
          {
            "id": "q187",
            "text": "Camere/unità"
          },
          {
            "id": "q188",
            "text": "Tariffe base"
          },
          {
            "id": "q189",
            "text": "Policy"
          },
          {
            "id": "q190",
            "text": "Tasse"
          },
          {
            "id": "q191",
            "text": "Canali"
          }
        ]
      }
    ]
  },
  {
    "id": "m192",
    "title": "GESTIONE PROPRIETÀ / DIREZIONE STRUTTURA",
    "categories": [
      {
        "id": "c193",
        "title": "Customer service alla proprietà/direzione",
        "items": [
          {
            "id": "q194",
            "text": "Aggiornamenti operativi"
          },
          {
            "id": "q195",
            "text": "Criticità"
          },
          {
            "id": "q196",
            "text": "Reclami"
          },
          {
            "id": "q197",
            "text": "Manutenzioni"
          },
          {
            "id": "q198",
            "text": "Performance"
          }
        ]
      },
      {
        "id": "c199",
        "title": "Relazioni commerciali con proprietà e stakeholder",
        "items": [
          {
            "id": "q200",
            "text": "Obiettivi"
          },
          {
            "id": "q201",
            "text": "Marginalità"
          },
          {
            "id": "q202",
            "text": "Investimenti"
          },
          {
            "id": "q203",
            "text": "Standard"
          },
          {
            "id": "q204",
            "text": "Piani di crescita"
          }
        ]
      },
      {
        "id": "c205",
        "title": "Rendicontazione economica",
        "items": [
          {
            "id": "q206",
            "text": "Produzione"
          },
          {
            "id": "q207",
            "text": "Commissioni OTA"
          },
          {
            "id": "q208",
            "text": "Costi variabili"
          },
          {
            "id": "q209",
            "text": "Fee gestione"
          },
          {
            "id": "q210",
            "text": "Incassi"
          },
          {
            "id": "q211",
            "text": "Pagamenti"
          }
        ]
      }
    ]
  },
  {
    "id": "m212",
    "title": "LICENZE, AUTORIZZAZIONI E ADEMPIMENTI",
    "categories": [
      {
        "id": "c213",
        "title": "SCIA e pratiche autorizzative",
        "items": [
          {
            "id": "q214",
            "text": "Apertura"
          },
          {
            "id": "q215",
            "text": "Subentro"
          },
          {
            "id": "q216",
            "text": "Variazioni camere/posti letto"
          },
          {
            "id": "q217",
            "text": "Insegna"
          },
          {
            "id": "q218",
            "text": "Requisiti locali"
          }
        ]
      },
      {
        "id": "c219",
        "title": "CIN/CIR e codici identificativi",
        "items": [
          {
            "id": "q220",
            "text": "Ottenimento"
          },
          {
            "id": "q221",
            "text": "Esposizione"
          },
          {
            "id": "q222",
            "text": "Coerenza sui portali"
          },
          {
            "id": "q223",
            "text": "Aggiornamento dati struttura"
          }
        ]
      },
      {
        "id": "c224",
        "title": "Alloggiati Web",
        "items": [
          {
            "id": "q225",
            "text": "Abilitazione questura"
          },
          {
            "id": "q226",
            "text": "Invio schedine"
          },
          {
            "id": "q227",
            "text": "Gestione documenti ospiti"
          },
          {
            "id": "q228",
            "text": "Controlli di pubblica sicurezza"
          }
        ]
      },
      {
        "id": "c229",
        "title": "Comune e tassa di soggiorno",
        "items": [
          {
            "id": "q230",
            "text": "Configurazione tariffe"
          },
          {
            "id": "q231",
            "text": "Esenzioni"
          },
          {
            "id": "q232",
            "text": "Dichiarazioni"
          },
          {
            "id": "q233",
            "text": "Riversamenti"
          },
          {
            "id": "q234",
            "text": "Riconciliazione incassi"
          }
        ]
      }
    ]
  },
  {
    "id": "m235",
    "title": "ASSICURAZIONI E COPERTURE RISCHI",
    "categories": [
      {
        "id": "c236",
        "title": "RC fabbricato/struttura",
        "items": [
          {
            "id": "q237",
            "text": "Copertura danni a ospiti"
          },
          {
            "id": "q238",
            "text": "Aree comuni"
          },
          {
            "id": "q239",
            "text": "Impianti"
          },
          {
            "id": "q240",
            "text": "Incendio"
          },
          {
            "id": "q241",
            "text": "Eventi atmosferici"
          },
          {
            "id": "q242",
            "text": "Responsabilità civile"
          }
        ]
      },
      {
        "id": "c243",
        "title": "RC attività ricettiva/locazione turistica",
        "items": [
          {
            "id": "q244",
            "text": "Responsabilità verso ospiti"
          },
          {
            "id": "q245",
            "text": "Gestione"
          },
          {
            "id": "q246",
            "text": "Collaboratori"
          },
          {
            "id": "q247",
            "text": "Terzi"
          }
        ]
      },
      {
        "id": "c248",
        "title": "Coperture danni causati dall’ospite",
        "items": [
          {
            "id": "q249",
            "text": "Cauzione"
          },
          {
            "id": "q250",
            "text": "Pre-autorizzazione"
          },
          {
            "id": "q251",
            "text": "Franchigie"
          },
          {
            "id": "q252",
            "text": "Sinistri"
          },
          {
            "id": "q253",
            "text": "Procedura addebito danni"
          }
        ]
      },
      {
        "id": "c254",
        "title": "Coperture ospite",
        "items": [
          {
            "id": "q255",
            "text": "Annullamento"
          },
          {
            "id": "q256",
            "text": "Interruzione soggiorno"
          },
          {
            "id": "q257",
            "text": "Assistenza viaggio"
          },
          {
            "id": "q258",
            "text": "Policy assicurative opzionali"
          }
        ]
      }
    ]
  },
  {
    "id": "m259",
    "title": "ONBOARDING SCHEDA PRODOTTO RICETTIVA",
    "categories": [
      {
        "id": "c260",
        "title": "Servizio fotografico professionale",
        "items": [
          {
            "id": "q261",
            "text": "Camere"
          },
          {
            "id": "q262",
            "text": "Bagni"
          },
          {
            "id": "q263",
            "text": "Aree comuni"
          },
          {
            "id": "q264",
            "text": "Esterni"
          },
          {
            "id": "q265",
            "text": "Breakfast"
          },
          {
            "id": "q266",
            "text": "Dettagli esperienziali"
          },
          {
            "id": "q267",
            "text": "Shooting stagionale"
          }
        ]
      },
      {
        "id": "c268",
        "title": "Scheda tecnica struttura",
        "items": [
          {
            "id": "q269",
            "text": "Camere"
          },
          {
            "id": "q270",
            "text": "Letti"
          },
          {
            "id": "q271",
            "text": "Bagni"
          },
          {
            "id": "q272",
            "text": "Amenities"
          },
          {
            "id": "q273",
            "text": "Accessibilità"
          },
          {
            "id": "q274",
            "text": "Parcheggio"
          },
          {
            "id": "q275",
            "text": "Colazione"
          },
          {
            "id": "q276",
            "text": "Servizi"
          },
          {
            "id": "q277",
            "text": "Regole casa"
          }
        ]
      },
      {
        "id": "c278",
        "title": "Copywriting vendita",
        "items": [
          {
            "id": "q279",
            "text": "Descrizioni camere"
          },
          {
            "id": "q280",
            "text": "USP"
          },
          {
            "id": "q281",
            "text": "Territorio"
          },
          {
            "id": "q282",
            "text": "Esperienze"
          },
          {
            "id": "q283",
            "text": "Servizi inclusi"
          },
          {
            "id": "q284",
            "text": "Policy"
          },
          {
            "id": "q285",
            "text": "Tono di voce hospitality"
          }
        ]
      },
      {
        "id": "c286",
        "title": "Traduzioni multilingua",
        "items": [
          {
            "id": "q287",
            "text": "Inglese"
          },
          {
            "id": "q288",
            "text": "Lingue target in base a provenienza ospiti"
          },
          {
            "id": "q289",
            "text": "OTA"
          },
          {
            "id": "q290",
            "text": "Mercati di riferimento"
          }
        ]
      },
      {
        "id": "c291",
        "title": "Caricamento in PMS/booking engine/OTA",
        "items": [
          {
            "id": "q292",
            "text": "Contenuti"
          },
          {
            "id": "q293",
            "text": "Tariffe"
          },
          {
            "id": "q294",
            "text": "Policy"
          },
          {
            "id": "q295",
            "text": "Foto"
          },
          {
            "id": "q296",
            "text": "Servizi"
          },
          {
            "id": "q297",
            "text": "Tasse"
          },
          {
            "id": "q298",
            "text": "Condizioni di prenotazione"
          }
        ]
      },
      {
        "id": "c299",
        "title": "Sincronizzazione prenotazioni",
        "items": [
          {
            "id": "q300",
            "text": "Sincronizzazione prenotazioni"
          },
          {
            "id": "q301",
            "text": "Blocchi"
          },
          {
            "id": "q302",
            "text": "Restrizioni"
          },
          {
            "id": "q303",
            "text": "Minimum stay"
          },
          {
            "id": "q304",
            "text": "CTA/CTD"
          },
          {
            "id": "q305",
            "text": "Disponibilità reale per canale"
          }
        ]
      },
      {
        "id": "c306",
        "title": "Pubblicazione online e controllo qualità schede",
        "items": [
          {
            "id": "q307",
            "text": "Sito"
          },
          {
            "id": "q308",
            "text": "OTA"
          },
          {
            "id": "q309",
            "text": "Metasearch"
          },
          {
            "id": "q310",
            "text": "Google Business Profile"
          },
          {
            "id": "q311",
            "text": "Coerenza contenuti"
          }
        ]
      }
    ]
  },
  {
    "id": "m312",
    "title": "GESTIONE OTA E CANALI DI VENDITA",
    "categories": [
      {
        "id": "c313",
        "title": "Pubblicazione schede su OTA",
        "items": [
          {
            "id": "q314",
            "text": "Booking.com"
          },
          {
            "id": "q315",
            "text": "Airbnb"
          },
          {
            "id": "q316",
            "text": "Expedia"
          },
          {
            "id": "q317",
            "text": "Vrbo"
          },
          {
            "id": "q318",
            "text": "Google Hotel"
          },
          {
            "id": "q319",
            "text": "Canali verticali di destinazione"
          }
        ]
      },
      {
        "id": "c320",
        "title": "Sincronizzazione prezzi/disponibilità con PMS e channel manager",
        "items": [
          {
            "id": "q321",
            "text": "Piani tariffari"
          },
          {
            "id": "q322",
            "text": "Allotment"
          },
          {
            "id": "q323",
            "text": "Restrizioni"
          },
          {
            "id": "q324",
            "text": "Stop-sale"
          }
        ]
      },
      {
        "id": "c325",
        "title": "Aggiornamento contenuti OTA",
        "items": [
          {
            "id": "q326",
            "text": "Foto"
          },
          {
            "id": "q327",
            "text": "Descrizioni"
          },
          {
            "id": "q328",
            "text": "Servizi"
          },
          {
            "id": "q329",
            "text": "Policy"
          },
          {
            "id": "q330",
            "text": "Promozioni"
          },
          {
            "id": "q331",
            "text": "Ranking factors"
          },
          {
            "id": "q332",
            "text": "Contenuti stagionali"
          }
        ]
      },
      {
        "id": "c333",
        "title": "Messaggistica ospiti OTA",
        "items": [
          {
            "id": "q334",
            "text": "Tempi risposta"
          },
          {
            "id": "q335",
            "text": "Template"
          },
          {
            "id": "q336",
            "text": "Richieste speciali"
          },
          {
            "id": "q337",
            "text": "Upsell"
          },
          {
            "id": "q338",
            "text": "Problemi arrivo"
          },
          {
            "id": "q339",
            "text": "Gestione aspettative"
          }
        ]
      },
      {
        "id": "c340",
        "title": "Gestione recensioni e reputation",
        "items": [
          {
            "id": "q341",
            "text": "Richiesta recensioni"
          },
          {
            "id": "q342",
            "text": "Risposte pubbliche"
          },
          {
            "id": "q343",
            "text": "Analisi sentiment"
          },
          {
            "id": "q344",
            "text": "Azioni correttive"
          }
        ]
      },
      {
        "id": "c345",
        "title": "Gestione incassi OTA",
        "items": [
          {
            "id": "q346",
            "text": "Virtual card"
          },
          {
            "id": "q347",
            "text": "Bonifici"
          },
          {
            "id": "q348",
            "text": "Commissioni"
          },
          {
            "id": "q349",
            "text": "Riconciliazioni"
          },
          {
            "id": "q350",
            "text": "Rimborsi"
          },
          {
            "id": "q351",
            "text": "Fatturazione"
          }
        ]
      },
      {
        "id": "c352",
        "title": "Fatture e adempimenti OTA",
        "items": [
          {
            "id": "q353",
            "text": "Commissioni"
          },
          {
            "id": "q354",
            "text": "Reverse charge/intrastat"
          },
          {
            "id": "q355",
            "text": "Documentazione fiscale"
          },
          {
            "id": "q356",
            "text": "Verifica estratti conto"
          }
        ]
      },
      {
        "id": "c357",
        "title": "Reclami, contestazioni e rimborsi",
        "items": [
          {
            "id": "q358",
            "text": "Casi no-show"
          },
          {
            "id": "q359",
            "text": "Overbooking"
          },
          {
            "id": "q360",
            "text": "Danni"
          },
          {
            "id": "q361",
            "text": "Disservizi"
          },
          {
            "id": "q362",
            "text": "Chargeback"
          },
          {
            "id": "q363",
            "text": "Mediazione OTA"
          }
        ]
      }
    ]
  },
  {
    "id": "m364",
    "title": "REVENUE MANAGEMENT",
    "categories": [
      {
        "id": "c365",
        "title": "Analisi competitiva comp set",
        "items": [
          {
            "id": "q366",
            "text": "Strutture simili"
          },
          {
            "id": "q367",
            "text": "Posizione"
          },
          {
            "id": "q368",
            "text": "Servizi"
          },
          {
            "id": "q369",
            "text": "Recensioni"
          },
          {
            "id": "q370",
            "text": "Pricing"
          },
          {
            "id": "q371",
            "text": "Restrizioni"
          },
          {
            "id": "q372",
            "text": "Value perception"
          }
        ]
      },
      {
        "id": "c373",
        "title": "Analisi stagionalità e lead time",
        "items": [
          {
            "id": "q374",
            "text": "Pickup"
          },
          {
            "id": "q375",
            "text": "Booking window"
          },
          {
            "id": "q376",
            "text": "Eventi locali"
          },
          {
            "id": "q377",
            "text": "Ponti"
          },
          {
            "id": "q378",
            "text": "Festività"
          },
          {
            "id": "q379",
            "text": "Domanda per segmento"
          }
        ]
      },
      {
        "id": "c380",
        "title": "Ottimizzazione prezzi manuale/AI",
        "items": [
          {
            "id": "q381",
            "text": "BAR"
          },
          {
            "id": "q382",
            "text": "Dynamic pricing"
          },
          {
            "id": "q383",
            "text": "Rate shopper"
          },
          {
            "id": "q384",
            "text": "Regole tariffarie"
          },
          {
            "id": "q385",
            "text": "Controllo parità tariffaria"
          }
        ]
      },
      {
        "id": "c386",
        "title": "Scontistiche e promozioni",
        "items": [
          {
            "id": "q387",
            "text": "Last minute"
          },
          {
            "id": "q388",
            "text": "Early booking"
          },
          {
            "id": "q389",
            "text": "Long stay"
          },
          {
            "id": "q390",
            "text": "Non rimborsabile"
          },
          {
            "id": "q391",
            "text": "Mobile rate"
          },
          {
            "id": "q392",
            "text": "Offerte OTA mirate"
          }
        ]
      },
      {
        "id": "c393",
        "title": "Strategie OTA specifiche",
        "items": [
          {
            "id": "q394",
            "text": "Genius"
          },
          {
            "id": "q395",
            "text": "Preferred"
          },
          {
            "id": "q396",
            "text": "Visibility booster"
          },
          {
            "id": "q397",
            "text": "Expedia Accelerator"
          },
          {
            "id": "q398",
            "text": "Promozioni chiuse"
          },
          {
            "id": "q399",
            "text": "Canali wholesale"
          }
        ]
      },
      {
        "id": "c400",
        "title": "Report performance",
        "items": [
          {
            "id": "q401",
            "text": "RevPAR"
          },
          {
            "id": "q402",
            "text": "ADR"
          },
          {
            "id": "q403",
            "text": "Occupancy"
          },
          {
            "id": "q404",
            "text": "GOPPAR"
          },
          {
            "id": "q405",
            "text": "Pickup"
          },
          {
            "id": "q406",
            "text": "Cancellation rate"
          },
          {
            "id": "q407",
            "text": "Channel mix"
          },
          {
            "id": "q408",
            "text": "Costo acquisizione"
          }
        ]
      },
      {
        "id": "c409",
        "title": "Forecasting ricavi e occupazione",
        "items": [
          {
            "id": "q410",
            "text": "Budget mensile"
          },
          {
            "id": "q411",
            "text": "Previsione domanda"
          },
          {
            "id": "q412",
            "text": "Scenari prezzo"
          },
          {
            "id": "q413",
            "text": "Azioni correttive"
          }
        ]
      }
    ]
  },
  {
    "id": "m414",
    "title": "CENTRO PRENOTAZIONI / SALES OFFICE",
    "categories": [
      {
        "id": "c415",
        "title": "Prenotazioni dirette struttura",
        "items": [
          {
            "id": "q416",
            "text": "Telefono"
          },
          {
            "id": "q417",
            "text": "Email"
          },
          {
            "id": "q418",
            "text": "WhatsApp"
          },
          {
            "id": "q419",
            "text": "Sito"
          },
          {
            "id": "q420",
            "text": "Booking engine"
          },
          {
            "id": "q421",
            "text": "Preventivi"
          },
          {
            "id": "q422",
            "text": "Follow-up commerciale"
          }
        ]
      },
      {
        "id": "c423",
        "title": "Prenotazioni da circuito/network proprietario",
        "items": [
          {
            "id": "q424",
            "text": "Database clienti"
          },
          {
            "id": "q425",
            "text": "Referral"
          },
          {
            "id": "q426",
            "text": "Convenzioni"
          },
          {
            "id": "q427",
            "text": "Repeat guest"
          },
          {
            "id": "q428",
            "text": "Campagne CRM"
          }
        ]
      },
      {
        "id": "c429",
        "title": "Prenotazioni indirette da OTA",
        "items": [
          {
            "id": "q430",
            "text": "Gestione richieste"
          },
          {
            "id": "q431",
            "text": "Modifiche"
          },
          {
            "id": "q432",
            "text": "Upsell"
          },
          {
            "id": "q433",
            "text": "Policy"
          },
          {
            "id": "q434",
            "text": "Protezione marginalità"
          }
        ]
      },
      {
        "id": "c435",
        "title": "Prenotazioni da agenzie viaggi e B2B",
        "items": [
          {
            "id": "q436",
            "text": "Tariffe nette"
          },
          {
            "id": "q437",
            "text": "Voucher"
          },
          {
            "id": "q438",
            "text": "Allotment"
          },
          {
            "id": "q439",
            "text": "Fatturazione"
          },
          {
            "id": "q440",
            "text": "Gruppi"
          },
          {
            "id": "q441",
            "text": "Corporate"
          }
        ]
      },
      {
        "id": "c442",
        "title": "Infrastruttura centralino/CRM",
        "items": [
          {
            "id": "q443",
            "text": "VoIP cloud"
          },
          {
            "id": "q444",
            "text": "Registrazione chiamate"
          },
          {
            "id": "q445",
            "text": "Tracciamento lead"
          },
          {
            "id": "q446",
            "text": "SLA risposta"
          },
          {
            "id": "q447",
            "text": "Report conversione"
          }
        ]
      }
    ]
  },
  {
    "id": "m448",
    "title": "CUSTOMER EXPERIENCE / GUEST JOURNEY",
    "categories": [
      {
        "id": "c449",
        "title": "Comunicazioni pre-stay",
        "items": [
          {
            "id": "q450",
            "text": "Conferma"
          },
          {
            "id": "q451",
            "text": "Istruzioni arrivo"
          },
          {
            "id": "q452",
            "text": "Upsell"
          },
          {
            "id": "q453",
            "text": "Richiesta documenti"
          },
          {
            "id": "q454",
            "text": "Orari"
          },
          {
            "id": "q455",
            "text": "Parcheggio"
          },
          {
            "id": "q456",
            "text": "Policy"
          }
        ]
      },
      {
        "id": "c457",
        "title": "Web check-in documentale e riconoscimento",
        "items": [
          {
            "id": "q458",
            "text": "Raccolta dati ospiti"
          },
          {
            "id": "q459",
            "text": "Documenti"
          },
          {
            "id": "q460",
            "text": "Firme digitali"
          },
          {
            "id": "q461",
            "text": "Invio Alloggiati Web"
          }
        ]
      },
      {
        "id": "c462",
        "title": "Contratti/condizioni soggiorno con firma OTP",
        "items": [
          {
            "id": "q463",
            "text": "Regole struttura"
          },
          {
            "id": "q464",
            "text": "Cauzione"
          },
          {
            "id": "q465",
            "text": "Privacy"
          },
          {
            "id": "q466",
            "text": "Responsabilità"
          },
          {
            "id": "q467",
            "text": "Autorizzazioni"
          }
        ]
      },
      {
        "id": "c468",
        "title": "Assistenza ospite multilivello",
        "items": [
          {
            "id": "q469",
            "text": "Prima risposta"
          },
          {
            "id": "q470",
            "text": "Escalation manutenzione"
          },
          {
            "id": "q471",
            "text": "Emergenze"
          },
          {
            "id": "q472",
            "text": "Concierge"
          },
          {
            "id": "q473",
            "text": "Gestione reclami"
          }
        ]
      },
      {
        "id": "c474",
        "title": "Upselling",
        "items": [
          {
            "id": "q475",
            "text": "Transfer"
          },
          {
            "id": "q476",
            "text": "Colazione"
          },
          {
            "id": "q477",
            "text": "Late check-out"
          },
          {
            "id": "q478",
            "text": "Esperienze"
          },
          {
            "id": "q479",
            "text": "Noleggi"
          },
          {
            "id": "q480",
            "text": "Spa"
          },
          {
            "id": "q481",
            "text": "Ristorazione"
          },
          {
            "id": "q482",
            "text": "Tour"
          },
          {
            "id": "q483",
            "text": "Servizi in camera"
          }
        ]
      },
      {
        "id": "c484",
        "title": "Coinvolgimento post-stay",
        "items": [
          {
            "id": "q485",
            "text": "Ringraziamento"
          },
          {
            "id": "q486",
            "text": "Richiesta recensione"
          },
          {
            "id": "q487",
            "text": "Recupero criticità"
          },
          {
            "id": "q488",
            "text": "Offerte ritorno"
          },
          {
            "id": "q489",
            "text": "Referral"
          }
        ]
      },
      {
        "id": "c490",
        "title": "Survey soddisfazione",
        "items": [
          {
            "id": "q491",
            "text": "NPS"
          },
          {
            "id": "q492",
            "text": "Pulizia"
          },
          {
            "id": "q493",
            "text": "Accoglienza"
          },
          {
            "id": "q494",
            "text": "Comfort"
          },
          {
            "id": "q495",
            "text": "Rapporto qualità/prezzo"
          },
          {
            "id": "q496",
            "text": "Aree di miglioramento"
          }
        ]
      }
    ]
  },
  {
    "id": "m497",
    "title": "GESTIONE OPERATIONS",
    "categories": [
      {
        "id": "c498",
        "title": "Coordinamento pulizie camere/unità",
        "items": [
          {
            "id": "q499",
            "text": "Planning arrivi/partenze"
          },
          {
            "id": "q500",
            "text": "Camere in fermata"
          },
          {
            "id": "q501",
            "text": "Standard rifacimento"
          },
          {
            "id": "q502",
            "text": "Controlli"
          }
        ]
      },
      {
        "id": "c503",
        "title": "Coordinamento biancheria",
        "items": [
          {
            "id": "q504",
            "text": "Par stock"
          },
          {
            "id": "q505",
            "text": "Consegne"
          },
          {
            "id": "q506",
            "text": "Ritiri"
          },
          {
            "id": "q507",
            "text": "Lavanderia"
          },
          {
            "id": "q508",
            "text": "Extra letto"
          },
          {
            "id": "q509",
            "text": "Teli"
          },
          {
            "id": "q510",
            "text": "Rotture"
          },
          {
            "id": "q511",
            "text": "Consumi"
          }
        ]
      },
      {
        "id": "c512",
        "title": "Coordinamento self check-in/out",
        "items": [
          {
            "id": "q513",
            "text": "Serrature smart"
          },
          {
            "id": "q514",
            "text": "Keybox"
          },
          {
            "id": "q515",
            "text": "Codici accesso"
          },
          {
            "id": "q516",
            "text": "Verifiche identità"
          },
          {
            "id": "q517",
            "text": "Assistenza remota"
          }
        ]
      },
      {
        "id": "c518",
        "title": "Gestione check-in in presenza",
        "items": [
          {
            "id": "q519",
            "text": "Turni staff"
          },
          {
            "id": "q520",
            "text": "Accoglienza"
          },
          {
            "id": "q521",
            "text": "Spiegazione servizi"
          },
          {
            "id": "q522",
            "text": "Incasso extra"
          },
          {
            "id": "q523",
            "text": "Gestione arrivi tardivi"
          }
        ]
      }
    ]
  },
  {
    "id": "m524",
    "title": "DEPOSITO CAUZIONALE / PRE-AUTORIZZAZIONI",
    "categories": [
      {
        "id": "c525",
        "title": "Incasso/pre-autorizzazione cauzione",
        "items": [
          {
            "id": "q526",
            "text": "Carta"
          },
          {
            "id": "q527",
            "text": "POS online"
          },
          {
            "id": "q528",
            "text": "Link pagamento"
          },
          {
            "id": "q529",
            "text": "Importi per tipologia"
          },
          {
            "id": "q530",
            "text": "Policy danni"
          }
        ]
      },
      {
        "id": "c531",
        "title": "Custodia e monitoraggio cauzione",
        "items": [
          {
            "id": "q532",
            "text": "Scadenze"
          },
          {
            "id": "q533",
            "text": "Blocchi"
          },
          {
            "id": "q534",
            "text": "Segnalazioni housekeeping"
          },
          {
            "id": "q535",
            "text": "Danni rilevati"
          },
          {
            "id": "q536",
            "text": "Documentazione fotografica"
          }
        ]
      },
      {
        "id": "c537",
        "title": "Restituzione/sblocco cauzione",
        "items": [
          {
            "id": "q538",
            "text": "Tempi"
          },
          {
            "id": "q539",
            "text": "Verifiche finali"
          },
          {
            "id": "q540",
            "text": "Addebiti"
          },
          {
            "id": "q541",
            "text": "Contestazioni"
          },
          {
            "id": "q542",
            "text": "Comunicazione all’ospite"
          }
        ]
      }
    ]
  },
  {
    "id": "m543",
    "title": "GESTIONE INCASSI OSPITI",
    "categories": [
      {
        "id": "c544",
        "title": "POS online e payment link",
        "items": [
          {
            "id": "q545",
            "text": "Acconti"
          },
          {
            "id": "q546",
            "text": "Saldi"
          },
          {
            "id": "q547",
            "text": "Extra"
          },
          {
            "id": "q548",
            "text": "Cauzioni"
          },
          {
            "id": "q549",
            "text": "Carte virtuali"
          },
          {
            "id": "q550",
            "text": "Pagamenti contactless"
          }
        ]
      },
      {
        "id": "c551",
        "title": "Bonifici",
        "items": [
          {
            "id": "q552",
            "text": "Riconciliazione prenotazioni"
          },
          {
            "id": "q553",
            "text": "Scadenze pagamento"
          },
          {
            "id": "q554",
            "text": "Solleciti"
          },
          {
            "id": "q555",
            "text": "Causali"
          },
          {
            "id": "q556",
            "text": "Controllo accrediti"
          }
        ]
      },
      {
        "id": "c557",
        "title": "Contanti",
        "items": [
          {
            "id": "q558",
            "text": "Gestione nei limiti normativi"
          },
          {
            "id": "q559",
            "text": "Ricevute"
          },
          {
            "id": "q560",
            "text": "Cassa"
          },
          {
            "id": "q561",
            "text": "Quadratura giornaliera"
          },
          {
            "id": "q562",
            "text": "Procedure antifrode"
          }
        ]
      }
    ]
  },
  {
    "id": "m563",
    "title": "GESTIONE PAGAMENTI E USCITE",
    "categories": [
      {
        "id": "c564",
        "title": "Pagamenti clienti/ospiti",
        "items": [
          {
            "id": "q565",
            "text": "Rimborsi"
          },
          {
            "id": "q566",
            "text": "Storni"
          },
          {
            "id": "q567",
            "text": "Chargeback"
          },
          {
            "id": "q568",
            "text": "Note credito"
          },
          {
            "id": "q569",
            "text": "Gestione contestazioni"
          }
        ]
      },
      {
        "id": "c570",
        "title": "Pagamenti proprietà/direzione",
        "items": [
          {
            "id": "q571",
            "text": "Rendiconti"
          },
          {
            "id": "q572",
            "text": "Canoni"
          },
          {
            "id": "q573",
            "text": "Fee"
          },
          {
            "id": "q574",
            "text": "Revenue share"
          },
          {
            "id": "q575",
            "text": "Minimi garantiti"
          },
          {
            "id": "q576",
            "text": "Scadenze contrattuali"
          }
        ]
      },
      {
        "id": "c577",
        "title": "Pagamenti fornitori",
        "items": [
          {
            "id": "q578",
            "text": "Pulizie"
          },
          {
            "id": "q579",
            "text": "Lavanderia"
          },
          {
            "id": "q580",
            "text": "Manutenzioni"
          },
          {
            "id": "q581",
            "text": "Servizi esterni"
          },
          {
            "id": "q582",
            "text": "Provvigioni"
          },
          {
            "id": "q583",
            "text": "Controllo SLA"
          }
        ]
      },
      {
        "id": "c584",
        "title": "Pagamenti tassa di soggiorno ai comuni",
        "items": [
          {
            "id": "q585",
            "text": "Riversamenti"
          },
          {
            "id": "q586",
            "text": "Dichiarazioni periodiche"
          },
          {
            "id": "q587",
            "text": "Esenzioni"
          },
          {
            "id": "q588",
            "text": "Riconciliazione ospiti"
          }
        ]
      },
      {
        "id": "c589",
        "title": "Ritenute, imposte e adempimenti fiscali",
        "items": [
          {
            "id": "q590",
            "text": "Ritenute"
          },
          {
            "id": "q591",
            "text": "Certificazioni"
          },
          {
            "id": "q592",
            "text": "Scadenze fiscali"
          },
          {
            "id": "q593",
            "text": "Coordinamento consulente"
          }
        ]
      }
    ]
  },
  {
    "id": "m594",
    "title": "AMMINISTRAZIONE",
    "categories": [
      {
        "id": "c595",
        "title": "Emissione fatture/ricevute",
        "items": [
          {
            "id": "q596",
            "text": "Ospiti"
          },
          {
            "id": "q597",
            "text": "Aziende"
          },
          {
            "id": "q598",
            "text": "Agenzie"
          },
          {
            "id": "q599",
            "text": "Fornitori"
          },
          {
            "id": "q600",
            "text": "Proprietà"
          },
          {
            "id": "q601",
            "text": "Note di variazione"
          }
        ]
      },
      {
        "id": "c602",
        "title": "Trasmissione fatture elettroniche",
        "items": [
          {
            "id": "q603",
            "text": "SDI"
          },
          {
            "id": "q604",
            "text": "Codici destinatario"
          },
          {
            "id": "q605",
            "text": "PEC"
          },
          {
            "id": "q606",
            "text": "Controlli scarti"
          },
          {
            "id": "q607",
            "text": "Conservazione sostitutiva"
          }
        ]
      },
      {
        "id": "c608",
        "title": "Registrazioni contabili",
        "items": [
          {
            "id": "q609",
            "text": "Incassi"
          },
          {
            "id": "q610",
            "text": "Costi operativi"
          },
          {
            "id": "q611",
            "text": "Commissioni OTA"
          },
          {
            "id": "q612",
            "text": "Cauzioni"
          },
          {
            "id": "q613",
            "text": "Riconciliazioni bancarie"
          },
          {
            "id": "q614",
            "text": "Cassa"
          }
        ]
      },
      {
        "id": "c615",
        "title": "Rapporti con amministrazioni pubbliche",
        "items": [
          {
            "id": "q616",
            "text": "Comune"
          },
          {
            "id": "q617",
            "text": "Regione"
          },
          {
            "id": "q618",
            "text": "Questura"
          },
          {
            "id": "q619",
            "text": "Agenzia Entrate"
          },
          {
            "id": "q620",
            "text": "SUAP"
          },
          {
            "id": "q621",
            "text": "Uffici turismo"
          }
        ]
      },
      {
        "id": "c622",
        "title": "Comunicazioni ISTAT",
        "items": [
          {
            "id": "q623",
            "text": "Flussi turistici"
          },
          {
            "id": "q624",
            "text": "Arrivi/presenze"
          },
          {
            "id": "q625",
            "text": "Nazionalità ospiti"
          },
          {
            "id": "q626",
            "text": "Scadenze"
          },
          {
            "id": "q627",
            "text": "Controlli errori"
          }
        ]
      },
      {
        "id": "c628",
        "title": "Comunicazioni pubblica sicurezza",
        "items": [
          {
            "id": "q629",
            "text": "Schedine alloggiati"
          },
          {
            "id": "q630",
            "text": "Invii giornalieri"
          },
          {
            "id": "q631",
            "text": "Deleghe"
          },
          {
            "id": "q632",
            "text": "Conservazione dati"
          },
          {
            "id": "q633",
            "text": "Procedure"
          }
        ]
      },
      {
        "id": "c634",
        "title": "Adempimenti imposta soggiorno",
        "items": [
          {
            "id": "q635",
            "text": "Calcolo"
          },
          {
            "id": "q636",
            "text": "Esenzioni"
          },
          {
            "id": "q637",
            "text": "Incasso"
          },
          {
            "id": "q638",
            "text": "Dichiarazione"
          },
          {
            "id": "q639",
            "text": "Riversamento"
          },
          {
            "id": "q640",
            "text": "Report ospiti"
          }
        ]
      },
      {
        "id": "c641",
        "title": "Archiviazione documentale e informatica",
        "items": [
          {
            "id": "q642",
            "text": "Contratti"
          },
          {
            "id": "q643",
            "text": "Documenti ospiti"
          },
          {
            "id": "q644",
            "text": "Fatture"
          },
          {
            "id": "q645",
            "text": "Autorizzazioni"
          },
          {
            "id": "q646",
            "text": "Privacy"
          },
          {
            "id": "q647",
            "text": "Backup"
          }
        ]
      }
    ]
  },
  {
    "id": "m648",
    "title": "LEGALE / PRIVACY / RECLAMI",
    "categories": [
      {
        "id": "c649",
        "title": "Modulistica contrattuale",
        "items": [
          {
            "id": "q650",
            "text": "Condizioni generali"
          },
          {
            "id": "q651",
            "text": "Policy cancellazione"
          },
          {
            "id": "q652",
            "text": "Cauzioni"
          },
          {
            "id": "q653",
            "text": "House rules"
          },
          {
            "id": "q654",
            "text": "Liberatorie"
          },
          {
            "id": "q655",
            "text": "Clausole ospite"
          }
        ]
      },
      {
        "id": "c656",
        "title": "Verifica privacy GDPR",
        "items": [
          {
            "id": "q657",
            "text": "Informative"
          },
          {
            "id": "q658",
            "text": "Consensi marketing"
          },
          {
            "id": "q659",
            "text": "Data retention"
          },
          {
            "id": "q660",
            "text": "Nomine responsabili"
          },
          {
            "id": "q661",
            "text": "Gestione data breach"
          }
        ]
      },
      {
        "id": "c662",
        "title": "Consulenza specialistica",
        "items": [
          {
            "id": "q663",
            "text": "Autorizzazioni"
          },
          {
            "id": "q664",
            "text": "Contenziosi"
          },
          {
            "id": "q665",
            "text": "Fiscalità turistica"
          },
          {
            "id": "q666",
            "text": "Classificazione struttura"
          },
          {
            "id": "q667",
            "text": "Contratti B2B"
          }
        ]
      },
      {
        "id": "c668",
        "title": "Gestione reclami operativi",
        "items": [
          {
            "id": "q669",
            "text": "Pulizia"
          },
          {
            "id": "q670",
            "text": "Manutenzione"
          },
          {
            "id": "q671",
            "text": "Rumore"
          },
          {
            "id": "q672",
            "text": "Overbooking"
          },
          {
            "id": "q673",
            "text": "Disservizi"
          },
          {
            "id": "q674",
            "text": "Compensazioni commerciali"
          }
        ]
      },
      {
        "id": "c675",
        "title": "Gestione reclami legali",
        "items": [
          {
            "id": "q676",
            "text": "Diffide"
          },
          {
            "id": "q677",
            "text": "Chargeback"
          },
          {
            "id": "q678",
            "text": "Contestazioni danni"
          },
          {
            "id": "q679",
            "text": "Responsabilità civile"
          },
          {
            "id": "q680",
            "text": "Rapporti con legali/assicurazioni"
          }
        ]
      }
    ]
  },
  {
    "id": "m681",
    "title": "MANUTENZIONE STRUTTURA",
    "categories": [
      {
        "id": "c682",
        "title": "Manutenzione ordinaria",
        "items": [
          {
            "id": "q683",
            "text": "Impianti"
          },
          {
            "id": "q684",
            "text": "Climatizzazione"
          },
          {
            "id": "q685",
            "text": "Serrature"
          },
          {
            "id": "q686",
            "text": "Arredi"
          },
          {
            "id": "q687",
            "text": "Elettrodomestici"
          },
          {
            "id": "q688",
            "text": "Wi-Fi"
          },
          {
            "id": "q689",
            "text": "Controlli programmati"
          }
        ]
      },
      {
        "id": "c690",
        "title": "Emergenze e problem solving",
        "items": [
          {
            "id": "q691",
            "text": "Guasti durante soggiorno"
          },
          {
            "id": "q692",
            "text": "Reperibilità"
          },
          {
            "id": "q693",
            "text": "Tempi intervento"
          },
          {
            "id": "q694",
            "text": "Escalation"
          },
          {
            "id": "q695",
            "text": "Comunicazione ospite"
          }
        ]
      },
      {
        "id": "c696",
        "title": "Gestione fornitori tecnici",
        "items": [
          {
            "id": "q697",
            "text": "Idraulico"
          },
          {
            "id": "q698",
            "text": "Elettricista"
          },
          {
            "id": "q699",
            "text": "Fabbro"
          },
          {
            "id": "q700",
            "text": "Condizionatori"
          },
          {
            "id": "q701",
            "text": "Piscina"
          },
          {
            "id": "q702",
            "text": "Giardino"
          },
          {
            "id": "q703",
            "text": "Controllo qualità interventi"
          }
        ]
      },
      {
        "id": "c704",
        "title": "Preventivi e follow-up lavori",
        "items": [
          {
            "id": "q705",
            "text": "Sopralluoghi"
          },
          {
            "id": "q706",
            "text": "Approvazioni"
          },
          {
            "id": "q707",
            "text": "Comparazione fornitori"
          },
          {
            "id": "q708",
            "text": "Consuntivi"
          },
          {
            "id": "q709",
            "text": "Impatto su disponibilità"
          }
        ]
      },
      {
        "id": "c710",
        "title": "Verifiche periodiche impianti",
        "items": [
          {
            "id": "q711",
            "text": "Caldaie"
          },
          {
            "id": "q712",
            "text": "Climatizzatori"
          },
          {
            "id": "q713",
            "text": "Estintori"
          },
          {
            "id": "q714",
            "text": "Ascensori"
          },
          {
            "id": "q715",
            "text": "Piscina"
          },
          {
            "id": "q716",
            "text": "Antincendio"
          },
          {
            "id": "q717",
            "text": "Certificazioni"
          }
        ]
      }
    ]
  },
  {
    "id": "m718",
    "title": "CONTROLLI DI QUALITÀ",
    "categories": [
      {
        "id": "c719",
        "title": "Controlli qualità struttura",
        "items": [
          {
            "id": "q720",
            "text": "Stato camere"
          },
          {
            "id": "q721",
            "text": "Aree comuni"
          },
          {
            "id": "q722",
            "text": "Odori"
          },
          {
            "id": "q723",
            "text": "Usura"
          },
          {
            "id": "q724",
            "text": "Manutenzioni visibili"
          },
          {
            "id": "q725",
            "text": "Coerenza standard brand"
          }
        ]
      },
      {
        "id": "c726",
        "title": "Verifica standard pulizie",
        "items": [
          {
            "id": "q727",
            "text": "Checklist camera/bagno/cucina"
          },
          {
            "id": "q728",
            "text": "Linen"
          },
          {
            "id": "q729",
            "text": "Superfici"
          },
          {
            "id": "q730",
            "text": "Dettagli"
          },
          {
            "id": "q731",
            "text": "Ispezione prima arrivo"
          }
        ]
      },
      {
        "id": "c732",
        "title": "Verifica dotazioni minime e premium",
        "items": [
          {
            "id": "q733",
            "text": "Amenities"
          },
          {
            "id": "q734",
            "text": "Wi-Fi"
          },
          {
            "id": "q735",
            "text": "Minibar"
          },
          {
            "id": "q736",
            "text": "Courtesy set"
          },
          {
            "id": "q737",
            "text": "Cucina"
          },
          {
            "id": "q738",
            "text": "Safety kit"
          },
          {
            "id": "q739",
            "text": "Materiali informativi"
          }
        ]
      },
      {
        "id": "c740",
        "title": "Audit periodici foto vs realtà",
        "items": [
          {
            "id": "q741",
            "text": "Aggiornamento immagini"
          },
          {
            "id": "q742",
            "text": "Arredi cambiati"
          },
          {
            "id": "q743",
            "text": "Servizi non più disponibili"
          },
          {
            "id": "q744",
            "text": "Aspettative ospite"
          }
        ]
      },
      {
        "id": "c745",
        "title": "Mystery guest test",
        "items": [
          {
            "id": "q746",
            "text": "Prenotazione"
          },
          {
            "id": "q747",
            "text": "Check-in"
          },
          {
            "id": "q748",
            "text": "Assistenza"
          },
          {
            "id": "q749",
            "text": "Pulizia"
          },
          {
            "id": "q750",
            "text": "Upsell"
          },
          {
            "id": "q751",
            "text": "Check-out"
          },
          {
            "id": "q752",
            "text": "Valutazione esperienza reale"
          }
        ]
      }
    ]
  },
  {
    "id": "m753",
    "title": "SERVIZI A VALORE AGGIUNTO",
    "categories": [
      {
        "id": "c754",
        "title": "Inserimento nel sito/portale diretto della struttura",
        "items": [
          {
            "id": "q755",
            "text": "Booking engine"
          },
          {
            "id": "q756",
            "text": "Offerte"
          },
          {
            "id": "q757",
            "text": "Pacchetti"
          },
          {
            "id": "q758",
            "text": "Contenuti territoriali"
          }
        ]
      },
      {
        "id": "c759",
        "title": "Inserimento su portali e network di vendita selezionati",
        "items": [
          {
            "id": "q760",
            "text": "OTA"
          },
          {
            "id": "q761",
            "text": "Metasearch"
          },
          {
            "id": "q762",
            "text": "Consorzi"
          },
          {
            "id": "q763",
            "text": "DMC"
          },
          {
            "id": "q764",
            "text": "Marketplace verticali"
          }
        ]
      },
      {
        "id": "c765",
        "title": "Abilitazione alla vendita cross-selling",
        "items": [
          {
            "id": "q766",
            "text": "Camere"
          },
          {
            "id": "q767",
            "text": "Appartamenti"
          },
          {
            "id": "q768",
            "text": "Esperienze"
          },
          {
            "id": "q769",
            "text": "Servizi ancillari"
          },
          {
            "id": "q770",
            "text": "Portfolio collegato"
          }
        ]
      },
      {
        "id": "c771",
        "title": "Anticipo finanziario/minimo garantito o revenue guarantee",
        "items": [
          {
            "id": "q772",
            "text": "Condizioni"
          },
          {
            "id": "q773",
            "text": "Rischio"
          },
          {
            "id": "q774",
            "text": "Cash flow"
          },
          {
            "id": "q775",
            "text": "Sostenibilità economica"
          }
        ]
      },
      {
        "id": "c776",
        "title": "Google Workspace e strumenti professionali",
        "items": [
          {
            "id": "q777",
            "text": "Email dominio"
          },
          {
            "id": "q778",
            "text": "Drive"
          },
          {
            "id": "q779",
            "text": "Calendar staff"
          },
          {
            "id": "q780",
            "text": "Documentale"
          },
          {
            "id": "q781",
            "text": "Firme"
          },
          {
            "id": "q782",
            "text": "Collaborazione interna"
          }
        ]
      }
    ]
  }
];

const STORAGE_KEY = "velora-owner-assessment-v2";
const STRUCTURES_KEY = "velora-analyzed-structures-v1";
const ACTIVE_STRUCTURE_KEY = "velora-active-structure-v1";
const DELETED_STRUCTURES_KEY = "velora-deleted-structures-v1";
const UI_STATE_KEY = "velora-ui-state-v1";

function loadDeletedStructureIds(): Set<string> {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(DELETED_STRUCTURES_KEY) || "[]");
    return new Set(Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : []);
  } catch {
    return new Set();
  }
}

function isStructureDeleted(id: string): boolean {
  return loadDeletedStructureIds().has(id);
}

function markStructureDeleted(id: string) {
  const deleted = loadDeletedStructureIds();
  deleted.add(id);
  window.localStorage.setItem(DELETED_STRUCTURES_KEY, JSON.stringify([...deleted]));
}

function unmarkStructureDeleted(id: string) {
  const deleted = loadDeletedStructureIds();
  if (!deleted.delete(id)) return;
  window.localStorage.setItem(DELETED_STRUCTURES_KEY, JSON.stringify([...deleted]));
}

type PersistedUiState = {
  showStructures?: boolean;
  activeMacroId?: string;
  searchTerm?: string;
  auditSourceFilter?: string;
  scrollY?: number;
  autoAuditDraft?: { name: string; website: string; city: string; province: string; rooms: string };
};

function loadUiState(): PersistedUiState {
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(UI_STATE_KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed as PersistedUiState : {};
  } catch {
    return {};
  }
}

// Aggiorna soltanto i riscontri pubblicati nel primo audit, senza toccare le note modificate dall'utente.
const SANTANTONIO_PREVIOUS_EVIDENCE: Record<string, string> = {
  q14: "Scheda camere e listino 2026 presenti, senza prezzo e disponibilità per data.",
  q385: "Confronto omogeneo impossibile: il sito non espone una tariffa diretta prenotabile per data.",
  q15: "Recensioni presenti senza data; widget con 5 Excellent non rappresentativo dei rating pubblici.",
  q141: "Codici rilevati sui portali, non sulle pagine principali del sito ufficiale.",
  q222: "CIN IT072003A100027082 coerente su Booking e Tripadvisor.",
  q261: "Galleria dedicata alle camere con circa dieci immagini.",
  q266: "Fotografie principalmente descrittive; limitati dettagli di esperienza ospite.",
  q308: "Schede su Booking, Hotels.com/Expedia, Trip.com e altri distributori.",
  q342: "Nel campione recente di Tripadvisor non sono state rilevate risposte della direzione.",
  q369: "Booking discreto; Google 3,6/5 e Tripadvisor 3,1/5 evidenziano un gap di percezione.",
  q372: "Posizione e pulizia apprezzate; camere e comfort generano riserve.",
  q669: "Booking circa 8,3/10 e Tripadvisor 4,1/5 per pulizia.",
  q670: "Recensioni ripetute su camere datate, arredi, rumore e assenza di climatizzazione.",
  q720: "Camere ampie e pulite, ma spesso descritte come semplici o datate.",
  q724: "Recensioni segnalano aggiornamenti necessari; impossibile ispezionare fisicamente.",
  q744: "Promessa di comfort da chiarire: solo 3 camere Superior su 24 hanno aria condizionata.",
};

type AnalyzedStructure = {
  id: string;
  name: string;
  city: string;
  province: string;
  rooms: string;
  website?: string;
  reportPath?: string;
  auditedAt?: string;
  ownerInfo: OwnerInfo;
  answers: Record<string, Answer>;
  rateQuotes?: RateQuote[];
  availabilityProbes?: AvailabilityProbe[];
  auditData?: AuditData;
  assessmentMode: AssessmentMode;
  updatedAt: string;
};

type RateQuote = {
  id: string;
  otaId: string;
  stayDate: string;
  observedAt: string;
  total: number;
  nights: number;
  roomType: string;
  unitId?: string;
  referenceRoomKey?: string;
  bookingReferenceRoom?: string;
  roomMatchStatus?: string;
  roomMatchScore?: number;
  comparisonWarning?: string;
  guests: number;
  board: string;
  refund: string;
  audience: string;
  taxes: string;
  promotion: string;
  promotionKind?: string;
  originalTotal?: number;
  eventTag: string;
  sourceUrl: string;
  ratePlan?: string;
  origin?: "manual" | "pilot";
  pilotKey?: string;
  pilotVerified?: boolean;
};

type BrowserPilotQuoteCandidate = {
  roomType: string;
  ratePlan?: string;
  total: number;
  nightlyRate?: number;
  displayedAmount?: number;
  displayedBasis?: "nightly" | "stay-total" | "unknown";
  priceDerivation?: string;
  comparisonSelected?: boolean;
  bookingReferenceRoom?: string;
  referenceRoomKey?: string;
  roomMatchStatus?: "booking-reference" | "same-room" | "different-room-fallback" | "not-selected" | string;
  roomMatchScore?: number;
  comparisonWarning?: string;
  currency: string;
  nights: number;
  guests: number;
  board: string;
  refund: string;
  audience: string;
  taxes: string;
  verified?: boolean;
  evidence?: string;
};

type BrowserPilotReviewTheme = {
  theme: string;
  count: number;
  weight?: string;
  sentiment?: string;
  phrases?: string[];
  examples?: string[];
  action?: string;
};

type BrowserPilotReputation = {
  status: string;
  source?: string;
  url?: string;
  name?: string;
  rating?: number | null;
  reviewCount?: number | null;
  sampleSize?: number;
  sampleAverage?: number | null;
  responseCount?: number;
  responseRate?: number;
  strengths?: BrowserPilotReviewTheme[];
  weaknesses?: BrowserPilotReviewTheme[];
  isolatedSignals?: BrowserPilotReviewTheme[];
  recurringThemes?: BrowserPilotReviewTheme[];
  keywords?: { word: string; count: number }[];
  evidence?: string;
};

type BrowserPilotPhotoAudit = {
  status: string;
  source?: string;
  url?: string;
  score?: number;
  imageCount?: number;
  highResolutionCount?: number;
  altTextCount?: number;
  categoryCounts?: Record<string, number>;
  components?: Record<string, number>;
  strengths?: string[];
  gaps?: string[];
  actions?: string[];
  evidence?: string;
};

type BrowserPilotObservation = {
  otaId: string;
  month: string;
  checkin: string;
  checkout: string;
  status: string;
  evidence?: string;
  requestedUrl?: string;
  finalUrl?: string;
  title?: string;
  quotes?: BrowserPilotQuoteCandidate[];
};

type BrowserPilotOtaProfile = {
  status: string;
  url?: string;
  title?: string;
  rating?: number | null;
  ratingScale?: number | null;
  reviewCount?: number | null;
  recommendationRate?: number | null;
  visiblePrices?: { amount: number; currency: string; text?: string }[];
  outboundHosts?: string[];
  commercialHosts?: string[];
  commercialLinks?: { host: string; url: string; text?: string; otaId?: string }[];
  visibleExcerpt?: string;
  evidence?: string;
};

type DiscoveredPilotSource = {
  status: string;
  url?: string;
  candidateUrl?: string;
  title?: string;
  score?: number;
  evidence?: string;
  searchUrl?: string;
  identityVerified?: boolean;
  presenceDetected?: boolean;
  verification?: string;
};

type BrowserPilotResult = {
  schema: "velora-browser-audit-pilot-v1";
  propertyId: string;
  createdAt: string;
  bookingEngine?: { status: string; provider: string; url: string; mode: string; evidence: string };
  discoveredSources?: Record<string, DiscoveredPilotSource>;
  otaProfiles?: Record<string, BrowserPilotOtaProfile>;
  reputation?: BrowserPilotReputation;
  photoAudit?: BrowserPilotPhotoAudit;
  discoveryProgress?: {
    stage?: string;
    completed?: number;
    total?: number;
    otaId?: string;
    label?: string;
    updatedAt?: string;
  };
  plan?: { month?: string; checkin?: string; checkout?: string; nights?: number; adults?: number }[];
  roomReferences?: {
    checkin: string;
    checkout: string;
    roomType: string;
    referenceRoomKey: string;
    matchedOtas?: number;
    evidence?: string;
  }[];
  observations: BrowserPilotObservation[];
};

function mergeBrowserPilotResults(previous: BrowserPilotResult | null | undefined, next: BrowserPilotResult): BrowserPilotResult {
  if (!previous || previous.propertyId !== next.propertyId) return next;
  const observations = new Map<string, BrowserPilotObservation>();
  for (const item of previous.observations || []) {
    observations.set([item.otaId,item.month,item.checkin,item.checkout].join("|"), item);
  }
  for (const item of next.observations || []) {
    observations.set([item.otaId,item.month,item.checkin,item.checkout].join("|"), item);
  }
  return {
    ...previous,
    ...next,
    createdAt: next.createdAt || previous.createdAt,
    bookingEngine: next.bookingEngine?.status && next.bookingEngine.status !== "unverified" ? next.bookingEngine : previous.bookingEngine,
    discoveredSources: { ...(previous.discoveredSources || {}), ...(next.discoveredSources || {}) },
    otaProfiles: { ...(previous.otaProfiles || {}), ...(next.otaProfiles || {}) },
    reputation: next.reputation?.status ? next.reputation : previous.reputation,
    photoAudit: next.photoAudit?.status ? next.photoAudit : previous.photoAudit,
    roomReferences: next.roomReferences?.length ? next.roomReferences : previous.roomReferences,
    observations: [...observations.values()].sort((a,b) => (a.month + a.otaId).localeCompare(b.month + b.otaId)),
  };
}

type AvailabilityStatus = "no-rate" | "calendar-closed" | "blocked";

type AvailabilityProbe = {
  id: string;
  otaId: string;
  stayDate: string;
  observedAt: string;
  status: AvailabilityStatus;
  roomType: string;
  guests: number;
  sourceUrl: string;
  note: string;
};

const EMPTY_AVAILABILITY_DRAFT: AvailabilityProbe = {
  id: "", otaId: "booking", stayDate: "", observedAt: "", status: "no-rate",
  roomType: "Matrimoniale", guests: 2, sourceUrl: "", note: "",
};

const AVAILABILITY_LABELS: Record<AvailabilityStatus, string> = {
  "no-rate": "Nessun prezzo mostrato per questa ricerca",
  "calendar-closed": "Data non selezionabile / calendario non aperto",
  blocked: "Verifica impedita dal portale",
};

const EMPTY_RATE_DRAFT: RateQuote = {
  id: "", otaId: "booking", stayDate: "", observedAt: "", total: 0,
  nights: 1, roomType: "Matrimoniale", unitId: "", guests: 2, board: "Colazione inclusa",
  refund: "Rimborsabile", audience: "Pubblico senza login", taxes: "IVA inclusa, tassa di soggiorno esclusa",
  promotion: "", promotionKind: "Non verificata", originalTotal: 0, eventTag: "", sourceUrl: "",
};

function providerFromBookingUrl(value: string): { provider: string; mode: string; status: AuditStatus } | null {
  try {
    const url = new URL(value.trim());
    if (!['https:', 'http:'].includes(url.protocol)) return null;
    const host = url.hostname.toLowerCase().replace(/^www\./, '');
    if (host.endsWith('.kross.travel') || host === 'book.krossbooking.com') {
      return { provider: 'Kross Booking', mode: 'Fornitore indicato dal dominio del percorso di prenotazione', status: 'present' };
    }
    if (host === 'book.ermeshotels.com' || host.endsWith('.book.ermeshotels.com')) {
      return { provider: 'ErmesHotels', mode: 'Fornitore indicato dal dominio del percorso di prenotazione', status: 'present' };
    }
    if (['booking.com', 'airbnb.com', 'expedia.com', 'expedia.it', 'vrbo.com', 'hotels.com', 'agoda.com', 'trip.com'].some((domain) => host === domain || host.endsWith(`.${domain}`))) {
      return null;
    }
    return { provider: '', mode: `Fornitore non identificato dal dominio ${host}`, status: 'partial' };
  } catch {
    return null;
  }
}

function formatPilotElapsed(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function todayLocalIso(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function rateCohortKey(quote: RateQuote): string {
  const physicalUnit = quote.referenceRoomKey?.trim().toLowerCase()
    || quote.unitId?.trim().toLowerCase()
    || `non-verificata:${quote.otaId}:${quote.roomType.trim().toLowerCase()}`;
  return [physicalUnit, quote.guests, quote.nights, quote.board, quote.refund, quote.audience, quote.taxes].join("|");
}

function rateCohortLabel(quote: RateQuote): string {
  const room = quote.referenceRoomKey
    ? `Reference Booking: ${quote.bookingReferenceRoom || quote.roomType}`
    : quote.unitId?.trim()
      ? `Unità ${quote.unitId.trim()}`
      : `${quote.roomType} (camera non comparabile)`;
  return `${room} · ${quote.guests} ospiti · ${quote.nights} notte/i · ${quote.board} · ${quote.refund} · ${quote.audience} · ${quote.taxes}`;
}

function monthKeys(from: string, count = 12): string[] {
  const [year, month] = from.split("-").map(Number);
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(Date.UTC(year, month - 1 + index, 1));
    return date.toISOString().slice(0, 7);
  });
}

function futureMonthKeys(date = new Date()): string[] {
  return monthKeys(todayLocalIso(date).slice(0, 7), 24 - date.getMonth());
}

function latestRateQuotes(quotes: RateQuote[], cohort: string): RateQuote[] {
  const latest = new Map<string, RateQuote>();
  const today = todayLocalIso();
  for (const quote of quotes.filter((item) => rateCohortKey(item) === cohort && Number.isFinite(item.total) && item.total > 0 && Number.isFinite(item.nights) && item.nights > 0 && /^\d{4}-\d{2}-\d{2}$/.test(item.stayDate) && item.stayDate >= today)) {
    const key = `${quote.otaId}|${quote.stayDate}`;
    const old = latest.get(key);
    if (!old || old.observedAt < quote.observedAt) latest.set(key, quote);
  }
  return [...latest.values()];
}

function monthlyAvailabilitySummary(probes: AvailabilityProbe[], month: string, otaId: string): string {
  const latest = new Map<string, AvailabilityProbe>();
  for (const probe of probes.filter((item) => item.otaId === otaId && item.stayDate.startsWith(month) && item.stayDate >= todayLocalIso())) {
    const key = `${probe.stayDate}|${probe.roomType}|${probe.guests}`;
    const old = latest.get(key);
    if (!old || old.observedAt < probe.observedAt) latest.set(key, probe);
  }
  const values = [...latest.values()];
  if (!values.length) return "Non verificato";
  const counts = { "no-rate": 0, "calendar-closed": 0, blocked: 0 };
  values.forEach((item) => { counts[item.status] += 1; });
  return [counts["no-rate"] && `Prezzo non mostrato: ${counts["no-rate"]} data/e`, counts["calendar-closed"] && `Calendario non aperto: ${counts["calendar-closed"]} data/e`, counts.blocked && `Verifica impedita: ${counts.blocked} data/e`].filter(Boolean).join("; ");
}

function pilotCoverageSummary(result: BrowserPilotResult | null | undefined, month: string, otaId: string): string {
  const entries = (result?.observations || []).filter((item) => item.month === month && item.otaId === otaId);
  if (!entries.length) return "";
  const item = entries[entries.length - 1];
  const quotes = Array.isArray(item.quotes) ? item.quotes : [];
  const quoteCount = quotes.length;
  const verifiedCount = quotes.filter((quote) => quote.verified).length;

  if (item.status === "quote_candidates") {
    if (!quoteCount) return "Tariffe rilevate";
    if (otaId === "booking") {
      if (verifiedCount === quoteCount) return `Tariffe rilevate: ${quoteCount} · camera e prezzo validati`;
      if (verifiedCount > 0) return `Tariffe rilevate: ${quoteCount} · ${verifiedCount} validate · confronto OTA da completare`;
      return `Tariffe rilevate: ${quoteCount} · condizioni da completare`;
    }
    return verifiedCount
      ? `Tariffe rilevate: ${quoteCount} · ${verifiedCount} validate`
      : `Prezzi rilevati: ${quoteCount} · attribuzione camera/piano da verificare`;
  }

  if (item.status === "quote_candidates_unverified") {
    if (!quoteCount) return "Prezzi rilevati · attribuzione da verificare";
    return otaId === "booking"
      ? `Tariffe rilevate: ${quoteCount} · associazione camera/piano non ancora validata`
      : `Prezzi rilevati: ${quoteCount} · attribuzione camera/piano da verificare`;
  }

  const discovery = result?.discoveredSources?.[otaId];
  if (item.status === "source_missing" && (discovery?.presenceDetected || discovery?.candidateUrl)) {
    return "Pagina OTA rilevata · identità/prezzo da verificare";
  }
  const labels: Record<string, string> = {
    no_public_rate: "Nessuna tariffa pubblica rilevata sulle date testate",
    needs_human_review: "Pagina letta · prezzo non attribuibile con certezza",
    dates_unconfirmed: "Date non confermate dal portale",
    date_adapter_missing: "Date non applicate automaticamente",
    source_not_retested: "Scheda non ritestata nel test rapido",
    source_missing: "Scheda non individuata automaticamente in questo passaggio",
    rate_limited: "Portale limita temporaneamente la verifica",
    blocked: "Verifica impedita dal portale",
    http_error: "Errore HTTP durante la verifica",
    navigation_error: "Errore di navigazione durante la verifica",
    empty_page: "Pagina senza contenuto tariffario leggibile",
    dated_search_inconclusive: "Ricerca datata non conclusiva",
    login_required: "Login richiesto dal portale · nessun prezzo usato",
  };
  return labels[item.status] || item.status || "";
}

function pilotProfileMetricFallback(profile: BrowserPilotOtaProfile): string {
  const labels: Record<string,string> = {
    source_missing: "Non individuato in questa scansione",
    http_error: "Non leggibile (HTTP)",
    rate_limited: "Temporaneamente limitato",
    blocked: "Bloccato dal portale",
    robots_denied: "Accesso automatico non consentito",
    robots_unavailable: "Verifica non conclusiva",
    navigation_error: "Verifica non conclusiva",
    sampled: "Dato non esposto",
  };
  return labels[profile.status] || "Dato non disponibile";
}

function pilotProfileMetric(value: number | null | undefined, profile: BrowserPilotOtaProfile, suffix = ""): string {
  return Number.isFinite(value) ? `${Number(value).toFixed(suffix === "%" ? 1 : 0)}${suffix}` : pilotProfileMetricFallback(profile);
}

function monthlyCoverageSummary(quotes: RateQuote[], probes: AvailabilityProbe[], month: string, otaId: string, pilotResult?: BrowserPilotResult | null): string {
  const priceCount = monthlyRateCell(quotes, month, otaId).count;
  const probeSummary = monthlyAvailabilitySummary(probes, month, otaId);
  const manualSummary = [priceCount && `Prezzo visibile: ${priceCount} data/e`, probeSummary !== "Non verificato" && probeSummary].filter(Boolean).join("; ");
  return manualSummary || pilotCoverageSummary(pilotResult, month, otaId) || "Non verificato";
}

function promotionSummary(quote: RateQuote): string {
  const type = quote.promotionKind || (quote.promotion ? "Tipo non classificato" : "Non verificata");
  const discount = Number(quote.originalTotal) > quote.total
    ? ` · -${((1 - quote.total / Number(quote.originalTotal)) * 100).toFixed(1)}% rispetto al prezzo barrato`
    : "";
  return `${type}${quote.promotion ? ` · ${quote.promotion}` : ""}${discount}`;
}

function monthlyRateCell(quotes: RateQuote[], month: string, otaId: string): { average: number | null; count: number; verified: number; deltaPct: number | null; matched: number } {
  const own = quotes.filter((quote) => quote.otaId === otaId && quote.stayDate.startsWith(month));
  if (!own.length) return { average: null, count: 0, verified: 0, deltaPct: null, matched: 0 };
  const average = own.reduce((sum, quote) => sum + quote.total / quote.nights, 0) / own.length;
  const verified = own.filter((quote) => quote.origin !== "pilot" || quote.pilotVerified !== false).length;
  const pairs = otaId === "booking" ? [] : own.flatMap((quote) => {
    if (quote.origin === "pilot" && quote.pilotVerified === false) return [];
    const comparisonUnit = quote.referenceRoomKey?.trim().toLowerCase() || quote.unitId?.trim().toLowerCase();
    if (!comparisonUnit) return [];
    const base = quotes.find((other) => other.otaId === "booking" &&
      !(other.origin === "pilot" && other.pilotVerified === false) &&
      (other.referenceRoomKey?.trim().toLowerCase() || other.unitId?.trim().toLowerCase()) === comparisonUnit &&
      other.stayDate === quote.stayDate && other.observedAt.slice(0, 10) === quote.observedAt.slice(0, 10));
    return base ? [{ own: quote.total / quote.nights, base: base.total / base.nights }] : [];
  });
  const deltaPct = pairs.length ? pairs.reduce((sum, pair) => sum + 100 * (pair.own - pair.base) / pair.base, 0) / pairs.length : null;
  return { average, count: own.length, verified, deltaPct, matched: pairs.length };
}
function normalizedRateToken(value: string | undefined): string {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

const PILOT_TARIFF_OTA_IDS = ["booking","agoda","airbnb","vrbo","holidu","expedia","hotels","travelocity","trip","priceline"] as const;
const PILOT_OTA_LABELS: Record<string,string> = {
  booking:"Booking.com", airbnb:"Airbnb", expedia:"Expedia", hotels:"Hotels.com", vrbo:"Vrbo",
  holidu:"Holidu", agoda:"Agoda", trip:"Trip.com", priceline:"Priceline", travelocity:"Travelocity",
  tripadvisor:"Tripadvisor", trivago:"Trivago", googlehotels:"Google Hotels", holidaycheck:"HolidayCheck",
};

type OtaDistributionAsymmetry = {
  checkin: string; checkout: string; otaId: string; otaLabel: string;
  unitCount: number; maxUnitCount: number; referenceChannels: string[]; units: string[]; finding: string;
};

function pilotDistributionAsymmetries(result: BrowserPilotResult | null | undefined): OtaDistributionAsymmetry[] {
  if (!result) return [];
  const stayMap = new Map<string, Map<string, { units:Set<string>; labels:Map<string,string>; explicitNoRate:boolean }>>();
  for (const observation of result.observations || []) {
    if (!PILOT_TARIFF_OTA_IDS.includes(observation.otaId as typeof PILOT_TARIFF_OTA_IDS[number])) continue;
    const key=[observation.checkin,observation.checkout].join("|");
    if (!stayMap.has(key)) stayMap.set(key,new Map());
    const byOta=stayMap.get(key)!;
    if (!byOta.has(observation.otaId)) byOta.set(observation.otaId,{units:new Set(),labels:new Map(),explicitNoRate:false});
    const slot=byOta.get(observation.otaId)!;
    if (observation.status==="no_public_rate") slot.explicitNoRate=true;
    for (const quote of observation.quotes || []) {
      if (!quote.verified) continue;
      const room=String(quote.roomType || "").trim();
      if (!room || /tipologia camera da verificare/i.test(room)) continue;
      const normalized=normalizedRateToken(room);
      slot.units.add(normalized);
      if (!slot.labels.has(normalized)) slot.labels.set(normalized,room);
    }
  }
  const out: OtaDistributionAsymmetry[]=[];
  for (const [stayKey,byOta] of stayMap) {
    const [checkin,checkout]=stayKey.split("|");
    const positive=[...byOta.entries()].filter(([,slot])=>slot.units.size>0);
    if (positive.length<2) continue;
    const maxUnitCount=Math.max(...positive.map(([,slot])=>slot.units.size));
    if (maxUnitCount<2) continue;
    const referenceChannels=positive.filter(([,slot])=>slot.units.size===maxUnitCount).map(([otaId])=>PILOT_OTA_LABELS[otaId]||otaId);
    for (const [otaId,slot] of byOta) {
      const count=slot.units.size;
      if (count>0 && count<maxUnitCount) {
        const units=[...slot.labels.values()];
        out.push({
          checkin,checkout,otaId,otaLabel:PILOT_OTA_LABELS[otaId]||otaId,unitCount:count,maxUnitCount,referenceChannels,units,
          finding:(PILOT_OTA_LABELS[otaId]||otaId)+" espone "+count+" tipologia/e vendibile/i, mentre "+referenceChannels.join(", ")+" ne espone/espongono "+maxUnitCount+" sulle stesse date. Asimmetria distributiva verificata da frontend. Possibili cause da approfondire: mapping inventario incompleto, disponibilità/restrizioni diverse, configurazione parziale del canale o sincronizzazione channel manager non omogenea.",
        });
      } else if (count===0 && slot.explicitNoRate && maxUnitCount>0) {
        out.push({
          checkin,checkout,otaId,otaLabel:PILOT_OTA_LABELS[otaId]||otaId,unitCount:0,maxUnitCount,referenceChannels,units:[],
          finding:(PILOT_OTA_LABELS[otaId]||otaId)+" non espone tipologie prenotabili sulle date testate, mentre "+referenceChannels.join(", ")+" ne espone/espongono "+maxUnitCount+". Asimmetria di disponibilità verificata da frontend; non prova da sola un errore del channel manager e richiede verifica di allotment, stop-sale, minimum stay e mapping.",
        });
      }
    }
  }
  return out.slice(0,40);
}
function pilotDetectedRateQuotes(result: BrowserPilotResult): RateQuote[] {
  const rows: RateQuote[] = [];
  for (const observation of result.observations || []) {
    if (!PILOT_TARIFF_OTA_IDS.includes(observation.otaId as typeof PILOT_TARIFF_OTA_IDS[number])) continue;
    const sourceUrl = observation.finalUrl || observation.requestedUrl || "";
    for (const quote of observation.quotes || []) {
      if (quote.comparisonSelected === false) continue;
      if (!Number.isFinite(quote.total) || quote.total <= 0 || quote.nights < 1) continue;
      const roomType = String(quote.roomType || "").trim();
      if (!roomType) continue;
      const ratePlan = String(quote.ratePlan || "").trim();
      const pilotKey = [
        observation.otaId,
        observation.checkin,
        observation.checkout,
        normalizedRateToken(roomType),
        normalizedRateToken(ratePlan || quote.refund),
        normalizedRateToken(quote.board),
        quote.guests,
      ].join("|");
      rows.push({
        id: "pilot-" + pilotKey.replace(/[^a-z0-9|_-]+/gi, "-"),
        otaId: observation.otaId,
        stayDate: observation.checkin,
        observedAt: result.createdAt || new Date().toISOString(),
        total: Number(quote.total),
        nights: Number(quote.nights),
        roomType,
        referenceRoomKey: quote.verified ? (quote.referenceRoomKey || undefined) : undefined,
        bookingReferenceRoom: quote.bookingReferenceRoom || undefined,
        roomMatchStatus: quote.verified ? (quote.roomMatchStatus || undefined) : "not-selected",
        roomMatchScore: quote.verified && Number.isFinite(quote.roomMatchScore) ? Number(quote.roomMatchScore) : undefined,
        comparisonWarning: quote.comparisonWarning || (quote.verified ? undefined : "Prezzo rilevato automaticamente ma non ancora validato: mostrato, escluso dal delta OTA."),
        guests: Number(quote.guests || 2),
        board: quote.board || "Trattamento da verificare",
        refund: quote.refund || "Cancellazione da verificare",
        audience: quote.audience || "Pubblico senza login",
        taxes: quote.taxes || "Da verificare nel dettaglio del preventivo",
        promotion: "",
        promotionKind: "Non verificata",
        originalTotal: 0,
        eventTag: "",
        sourceUrl,
        ratePlan,
        origin: "pilot",
        pilotKey,
        pilotVerified: Boolean(quote.verified),
      });
    }
  }
  const latest = new Map<string, RateQuote>();
  rows.forEach((row) => latest.set(row.pilotKey || row.id, row));
  return [...latest.values()];
}

function mergePilotRateQuotes(existing: RateQuote[], incoming: RateQuote[]): RateQuote[] {
  if (!incoming.length) return existing;
  const incomingKeys = new Set(incoming.map((item) => item.pilotKey).filter(Boolean));
  const kept = existing.filter((item) => !(item.origin === "pilot" && item.pilotKey && incomingKeys.has(item.pilotKey)));
  return [...kept, ...incoming];
}

function auditSeedStructure(data: AuditData): AnalyzedStructure {
  const sources = data.sources as Record<string, { label: string; url: string }>;
  const answers: Record<string, Answer> = {};
  for (const check of data.checks) {
    const status = check.status as AuditStatus;
    const sourceLinks = check.sources
      .map((sourceId) => sources[sourceId]?.url)
      .filter(Boolean);
    answers[check.id] = {
      importance: status === "unverified" ? 0 : 3,
      current: status === "present" ? 3 : status === "partial" ? 1.5 : 0,
      fit: status === "unverified" ? 0 : 3,
      auditStatus: status,
      note: `${check.evidence}\nFonti: ${sourceLinks.join(" · ")}`,
    };
  }
  for (const channel of data.otaPresence) {
    const source = sources[channel.source];
    answers[`audit-ota-${channel.id}`] = {
      ...emptyAnswer(),
      auditStatus: channel.status as AuditStatus,
      note: `${channel.finding}\nFonte: ${source?.url ?? "verifica manuale"}`,
    };
  }
  for (const policy of data.pricingAudit.policies) {
    const source = sources[policy.source];
    answers[`audit-policy-${policy.otaId}`] = {
      ...emptyAnswer(),
      note: `Piani: ${policy.plans}\nPromozioni/sconti: ${policy.promotions}\nAffidabilità: ${policy.confidence}. Fonte: ${source?.url ?? "verifica manuale"}`,
    };
  }
  answers["audit-policy-direct"] = { ...emptyAnswer(), note: data.pricingAudit.direct };
  answers["audit-booking-engine"] = { ...emptyAnswer(), auditStatus: data.bookingEngine.status === "provider_identified" ? "present" : data.bookingEngine.status === "provider_unknown" ? "partial" : "unverified" };
  answers["audit-booking-engine-provider"] = { ...emptyAnswer(), note: data.bookingEngine.provider };
  answers["audit-booking-engine-url"] = { ...emptyAnswer(), note: data.bookingEngine.url };
  answers["audit-booking-engine-mode"] = { ...emptyAnswer(), note: data.bookingEngine.mode };
  answers["audit-booking-engine-evidence"] = { ...emptyAnswer(), note: data.bookingEngine.evidence };
  answers["audit-google-strengths"] = { ...emptyAnswer(), note: data.reviewInsights.strengths.map((entry) => `${entry.theme}: ${entry.finding}`).join("\n") };
  answers["audit-google-weaknesses"] = { ...emptyAnswer(), note: data.reviewInsights.weaknesses.map((entry) => `${entry.theme}: ${entry.finding}`).join("\n") };
  answers["audit-google-actions"] = { ...emptyAnswer(), note: data.reviewInsights.weaknesses.map((entry) => `${entry.theme}: ${entry.action}`).join("\n") };
  answers["audit-photo-score"] = { ...emptyAnswer(), current: data.photoAssessment.score, note: `${data.photoAssessment.gaps}\nAzione: ${data.photoAssessment.actions}` };
  return {
    id: data.id,
    name: data.name,
    city: data.city,
    province: data.province,
    rooms: data.rooms ? String(data.rooms) : "n.d.",
    website: data.website,
    reportPath: data.reportPath,
    auditedAt: data.auditedAt,
    ownerInfo: {
      ...EMPTY_OWNER_INFO,
      propertyName: data.name,
      location: data.city,
      city: data.city,
      province: data.province,
      propertyType: data.propertyType,
      rooms: data.rooms ? String(data.rooms) : "n.d.",
      channels: "Sito ufficiale, Booking.com, Google Hotels, Airbnb, Vrbo, Trip.com",
      objective: "Audit pubblico di visibilità, prenotazione diretta e reputazione",
    },
    answers,
    rateQuotes: [],
    availabilityProbes: [],
    auditData: data,
    assessmentMode: "web-audit",
    updatedAt: data.auditedAt,
  };
}

function santantonioStructure(): AnalyzedStructure {
  return auditSeedStructure(santantonioAudit);
}

function knownAuditData(id: string | null | undefined): AuditData | null {
  if (id === santantonioAudit.id) return santantonioAudit;
  if (id === perlaAudit.id) return perlaAudit;
  if (id === braAudit.id) return braAudit;
  return null;
}

function blankAuditDataForStructure(structure: Pick<AnalyzedStructure, "id" | "name" | "city" | "province" | "rooms" | "website">): AuditData {
  const template = JSON.parse(JSON.stringify(santantonioAudit)) as any;
  template.id = structure.id;
  template.name = structure.name || "Nuova struttura";
  template.city = structure.city || "";
  template.province = structure.province || "";
  template.rooms = Number.parseInt(structure.rooms || "", 10) || 0;
  template.propertyType = "Struttura ricettiva";
  template.website = structure.website || "";
  template.auditedAt = todayLocalIso();
  template.reportPath = "";
  template.sources = { sito: { label: "Sito ufficiale", url: structure.website || "" } };
  template.bookingEngine = { status: "unverified", provider: "", url: "", mode: "", evidence: "Da verificare." };
  template.otaPresence = template.otaPresence.map((channel: any) => ({
    ...channel, status: "unverified", finding: "Da verificare su fonte pubblica.", source: "sito",
  }));
  template.pricingAudit = {
    capturedAt: todayLocalIso(),
    method: "Campionamento da eseguire: nessun prezzo viene stimato senza preventivo verificato.",
    direct: "Non verificato.",
    policies: template.otaPresence.map((channel: any) => ({ otaId: channel.id, plans: "Non verificato", promotions: "Non verificato", confidence: "Da verificare", source: "sito" })),
    priceCalendar: { from: todayLocalIso(), through: "", status: "Non verificato", reason: "Da campionare.", metric: "Preventivo datato / notti", focus: "2 adulti; date campione omogenee." },
  };
  template.reviewInsights = { googleRating: "Non verificato", method: "Da verificare.", strengths: [], weaknesses: [] };
  template.photoAssessment = { score: 0, method: "Da verificare.", strengths: "", gaps: "Non verificato.", actions: "Verificare gallery sito e OTA." };
  delete template.reportNarrative;
  template.checks = template.checks.map((check: any) => ({
    ...check, status: "unverified", evidence: "Non ancora verificato.", sources: ["sito"],
  }));
  return template as AuditData;
}

function isAuditData(value: unknown): value is AuditData {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return typeof data.id === "string"
    && typeof data.name === "string"
    && typeof data.website === "string"
    && Array.isArray(data.checks)
    && Array.isArray(data.otaPresence)
    && Boolean(data.pricingAudit && typeof data.pricingAudit === "object")
    && Boolean(data.bookingEngine && typeof data.bookingEngine === "object")
    && Boolean(data.sources && typeof data.sources === "object")
    && Boolean(data.reviewInsights && typeof data.reviewInsights === "object")
    && Boolean(data.photoAssessment && typeof data.photoAssessment === "object");
}

function loadAnalyzedStructures(): AnalyzedStructure[] {
  const seed = santantonioStructure();
  const perlaSeed = auditSeedStructure(perlaAudit);
  const braSeed = auditSeedStructure(braAudit);
  const deleted = loadDeletedStructureIds();
  try {
    const saved = JSON.parse(window.localStorage.getItem(STRUCTURES_KEY) || "[]");
    if (!Array.isArray(saved)) return [seed, perlaSeed, braSeed].filter((item) => !deleted.has(item.id));
    const existing = saved.filter((item): item is AnalyzedStructure =>
      Boolean(item && typeof item.id === "string" && item.ownerInfo && item.answers && !deleted.has(item.id))
    );
    const migrated = existing.map((item) => {
      if (item.id !== seed.id) return item;
      const answers = { ...item.answers };
      for (const [id, answer] of Object.entries(seed.answers)) {
        if (id.startsWith("audit-") && !answers[id]) answers[id] = answer;
        const oldEvidence = SANTANTONIO_PREVIOUS_EVIDENCE[id];
        const noteLines = answers[id]?.note?.split("\n") ?? [];
        if (oldEvidence && noteLines.length === 2 && noteLines[0] === oldEvidence && noteLines[1].startsWith("Fonti: ")) {
          answers[id] = answer;
        }
      }
      return { ...item, answers, auditData: item.auditData ?? knownAuditData(item.id) ?? undefined, rateQuotes: Array.isArray(item.rateQuotes) ? item.rateQuotes : [], availabilityProbes: Array.isArray(item.availabilityProbes) ? item.availabilityProbes : [] };
    });
    const withSantAntonio = deleted.has(seed.id) || migrated.some((item) => item.id === seed.id)
      ? migrated
      : [seed, ...migrated];
    const withPerla = deleted.has(perlaSeed.id) || withSantAntonio.some((item) => item.id === perlaSeed.id)
      ? withSantAntonio
      : [...withSantAntonio, perlaSeed];
    return deleted.has(braSeed.id) || withPerla.some((item) => item.id === braSeed.id)
      ? withPerla
      : [...withPerla, braSeed];
  } catch {
    return [seed, perlaSeed, braSeed].filter((item) => !deleted.has(item.id));
  }
}

const QUICK_HOTEL_BB_CORE_ITEM_IDS = [
  "q6",   // Posizionamento
  "q7",   // Target ospite
  "q8",   // Promessa di soggiorno
  "q13",  // Booking engine
  "q16",  // Conversione prenotazioni dirette
  "q27",  // Calendario unificato
  "q33",  // Conferme prenotazioni
  "q35",  // Cancellazioni
  "q40",  // Sincronizzazione OTA
  "q44",  // Restrizioni tariffarie
  "q47",  // BAR
  "q69",  // Marginalità
  "q70",  // Report economici
  "q89",  // RevPAR
  "q93",  // Pickup
  "q156", // Costi operativi
  "q158", // Break-even
  "q168", // Commissioni
  "q170", // Responsabilità operative
  "q194", // Aggiornamenti operativi alla proprietà
  "q198", // Performance alla proprietà
  "q220", // Ottenimento CIN/CIR - unica verifica burocratica
  "q261", // Servizio fotografico: camere
  "q314", // Pubblicazione Booking.com
  "q366", // Comp set: strutture simili
  "q375", // Booking window
  "q382", // Dynamic pricing
  "q445", // Tracciamento lead CRM
  "q727", // Checklist qualità pulizie
  "q769", // Servizi ancillari
] as const;

const QUICK_HOTEL_BB_DEEP_DIVE_ITEM_IDS = [
  "q9",   // Identità territoriale
  "q15",  // Trust elements
  "q30",  // Minimum stay
  "q34",  // Modifiche prenotazioni
  "q48",  // Piani tariffari
  "q51",  // Compressione domanda
  "q72",  // Forecast
  "q95",  // Produzione per canale
  "q153", // ADR atteso
  "q157", // Margine potenziale
  "q167", // Marketing negli accordi commerciali
  "q195", // Gestione criticità verso la proprietà
  "q266", // Dettagli fotografici esperienziali
  "q370", // Pricing del comp set
  "q376", // Eventi locali
  "q383", // Rate shopper
  "q446", // SLA di risposta
  "q725", // Coerenza con lo standard del brand
  "q731", // Ispezione prima dell'arrivo
  "q756", // Offerte sul canale diretto
] as const;

const EXTERNAL_AUDIT_SOURCE_GROUPS = [
  {
    label: "Sito ufficiale",
    itemIds: [
      "q6", "q7", "q8", "q9", "q12", "q13", "q14", "q15", "q19", "q20", "q21", "q22", "q24",
      "q37", "q41", "q46", "q47", "q48", "q49", "q53", "q54", "q55", "q56", "q57", "q58", "q59",
      "q104", "q105", "q106", "q107", "q139", "q141", "q142", "q146", "q147", "q148", "q149", "q150",
      "q261", "q262", "q263", "q264", "q265", "q266", "q267", "q269", "q270", "q271", "q272", "q273",
      "q274", "q275", "q276", "q277", "q279", "q280", "q281", "q282", "q283", "q284", "q285", "q287",
      "q288", "q292", "q293", "q294", "q295", "q296", "q297", "q298", "q307", "q310", "q311",
      "q416", "q417", "q418", "q419", "q420", "q433", "q454", "q455", "q456", "q475", "q476",
      "q477", "q478", "q479", "q480", "q481", "q482", "q483", "q526", "q527", "q528", "q529",
      "q530", "q545", "q546", "q547", "q548", "q550", "q650", "q651", "q652", "q653", "q654",
      "q655", "q657", "q658", "q755", "q756", "q757", "q758", "q766", "q767", "q768", "q769", "q777",
    ],
  },
  {
    label: "Booking engine",
    itemIds: [
      "q13", "q14", "q15", "q30", "q37", "q41", "q44", "q46", "q47", "q48", "q49", "q104",
      "q117", "q118", "q119", "q120", "q121", "q292", "q293", "q294", "q295", "q296", "q297",
      "q298", "q303", "q305", "q321", "q323", "q381", "q382", "q384", "q385", "q387", "q388",
      "q389", "q390", "q391", "q392", "q419", "q420", "q421", "q450", "q451", "q452", "q453",
      "q454", "q455", "q456", "q463", "q464", "q465", "q466", "q467", "q526", "q527", "q528",
      "q529", "q530", "q545", "q546", "q547", "q548", "q549", "q550", "q650", "q651", "q652",
      "q653", "q654", "q655", "q755", "q756", "q757",
    ],
  },
  {
    label: "OTA e metasearch",
    itemIds: [
      "q14", "q30", "q37", "q42", "q44", "q53", "q54", "q55", "q56", "q57", "q58", "q59",
      "q141", "q146", "q147", "q148", "q149", "q150", "q151", "q220", "q221", "q222", "q223",
      "q261", "q262", "q263", "q264", "q265", "q266", "q267", "q269", "q270", "q271", "q272",
      "q273", "q274", "q275", "q276", "q277", "q279", "q280", "q281", "q282", "q283", "q284",
      "q285", "q287", "q288", "q289", "q290", "q292", "q293", "q294", "q295", "q296", "q297",
      "q298", "q305", "q308", "q309", "q311", "q314", "q315", "q316", "q317", "q318", "q319",
      "q321", "q323", "q326", "q327", "q328", "q329", "q330", "q331", "q332", "q342", "q343",
      "q366", "q367", "q368", "q369", "q370", "q371", "q372", "q381", "q382", "q384", "q385",
      "q387", "q388", "q389", "q390", "q391", "q392", "q394", "q395", "q396", "q397", "q398",
      "q399", "q430", "q431", "q432", "q433", "q760", "q761", "q762", "q763", "q764",
    ],
  },
  {
    label: "Google e Maps",
    itemIds: [
      "q6", "q7", "q8", "q9", "q19", "q139", "q141", "q142", "q147", "q148", "q149", "q150",
      "q151", "q220", "q221", "q222", "q223", "q261", "q263", "q264", "q265", "q266", "q269",
      "q270", "q271", "q272", "q273", "q274", "q275", "q276", "q277", "q279", "q280", "q281",
      "q282", "q283", "q287", "q288", "q307", "q309", "q310", "q311", "q318", "q319", "q326",
      "q327", "q328", "q329", "q330", "q331", "q332", "q342", "q343", "q366", "q367", "q368",
      "q369", "q370", "q371", "q372", "q376", "q377", "q378", "q379", "q760", "q761", "q762",
      "q763", "q764",
    ],
  },
  {
    label: "Recensioni ospiti",
    itemIds: [
      "q6", "q7", "q8", "q9", "q148", "q261", "q262", "q263", "q264", "q265", "q266", "q269",
      "q270", "q271", "q272", "q273", "q274", "q275", "q276", "q277", "q280", "q281", "q282",
      "q283", "q311", "q326", "q327", "q328", "q329", "q342", "q343", "q366", "q367", "q368",
      "q369", "q370", "q371", "q372", "q669", "q670", "q671", "q672", "q673", "q720", "q721",
      "q722", "q723", "q724", "q725", "q733", "q734", "q735", "q736", "q737", "q738", "q739",
      "q741", "q742", "q743", "q744",
    ],
  },
  {
    label: "Social e contenuti",
    itemIds: [
      "q6", "q7", "q8", "q9", "q147", "q148", "q149", "q150", "q151", "q261", "q262", "q263",
      "q264", "q265", "q266", "q267", "q279", "q280", "q281", "q282", "q283", "q284", "q285",
      "q287", "q288", "q307", "q310", "q311", "q326", "q327", "q332", "q376", "q755", "q756",
      "q757", "q758", "q768", "q769",
    ],
  },
  {
    label: "Ricerca web e mercato",
    itemIds: [
      "q6", "q7", "q9", "q139", "q141", "q142", "q146", "q147", "q148", "q149", "q150", "q151",
      "q220", "q221", "q222", "q223", "q366", "q367", "q368", "q369", "q370", "q371", "q372",
      "q376", "q377", "q378", "q379", "q760", "q761", "q762", "q763", "q764",
    ],
  },
  {
    label: "Test di contatto",
    itemIds: [
      "q334", "q335", "q336", "q337", "q339", "q416", "q417", "q418", "q419", "q420", "q421",
      "q422", "q430", "q431", "q432", "q433", "q446", "q450", "q451", "q452", "q453", "q454",
      "q455", "q456", "q463", "q464", "q465", "q466", "q467", "q469", "q472", "q475", "q476",
      "q477", "q478", "q479", "q480", "q481", "q482", "q483",
    ],
  },
] as const;

const FUNDAMENTAL_EXTERNAL_AUDIT_ITEM_IDS = [
  // Brand e proposta di valore
  "q6", "q7", "q8", "q9",
  // Sito, conversione e maturità tecnologica
  "q12", "q13", "q14", "q15", "q20", "q21", "q22", "q24",
  // Conformità pubblicamente verificabile
  "q141", "q221", "q222",
  // Qualità della presentazione del prodotto
  "q261", "q263", "q264", "q266", "q269", "q272", "q279", "q280",
  // Presenza, distribuzione e reputazione online
  "q307", "q308", "q309", "q310", "q311", "q314", "q318", "q342",
  // Competitività e revenue osservabile
  "q366", "q369", "q370", "q372", "q382", "q385",
  // Contatto e conversione commerciale
  "q416", "q417", "q418", "q420", "q446",
  // Qualità percepita e coerenza tra promessa e realtà
  "q669", "q670", "q720", "q724", "q734", "q744",
  // Opportunità commerciali visibili
  "q756", "q769",
] as const;

const EXTERNAL_WEB_AUDIT_ITEM_SET = new Set<string>(
  FUNDAMENTAL_EXTERNAL_AUDIT_ITEM_IDS
);

function getExternalAuditSources(itemId: string) {
  return EXTERNAL_AUDIT_SOURCE_GROUPS
    .filter((group) => (group.itemIds as readonly string[]).includes(itemId))
    .map((group) => group.label);
}

const QUICK_HOTEL_BB_CORE_ITEM_SET = new Set<string>(QUICK_HOTEL_BB_CORE_ITEM_IDS);
const QUICK_HOTEL_BB_DEEP_DIVE_ITEM_SET = new Set<string>(
  QUICK_HOTEL_BB_DEEP_DIVE_ITEM_IDS
);
const QUICK_HOTEL_BB_ALL_ITEM_SET = new Set<string>([
  ...QUICK_HOTEL_BB_CORE_ITEM_IDS,
  ...QUICK_HOTEL_BB_DEEP_DIVE_ITEM_IDS,
]);
const DEFAULT_CUSTOM_QUICK_ITEM_IDS = [
  ...QUICK_HOTEL_BB_CORE_ITEM_IDS,
  ...QUICK_HOTEL_BB_DEEP_DIVE_ITEM_IDS,
] as string[];

function selectAssessmentItems(itemIds: Set<string>): AssessmentMacro[] {
  return ASSESSMENT_DATA.map((macro) => ({
    ...macro,
    categories: macro.categories
      .map((category) => ({
        ...category,
        items: category.items.filter((item) => itemIds.has(item.id)),
      }))
      .filter((category) => category.items.length > 0),
  })).filter((macro) => macro.categories.length > 0);
}

const QUICK_HOTEL_BB_CORE_DATA = selectAssessmentItems(QUICK_HOTEL_BB_CORE_ITEM_SET);
const QUICK_HOTEL_BB_DEEP_DIVE_DATA = selectAssessmentItems(
  QUICK_HOTEL_BB_DEEP_DIVE_ITEM_SET
);
const QUICK_HOTEL_BB_ALL_DATA = selectAssessmentItems(QUICK_HOTEL_BB_ALL_ITEM_SET);
const EXTERNAL_WEB_AUDIT_DATA = selectAssessmentItems(EXTERNAL_WEB_AUDIT_ITEM_SET);

const AUDIT_STATUS_OPTIONS: Array<{
  value: Exclude<AuditStatus, "">;
  label: string;
  shortLabel: string;
  className: string;
  current: number;
}> = [
  {
    value: "present",
    label: "Presente e coerente",
    shortLabel: "Presente",
    className: "border-emerald-300 bg-emerald-50 text-emerald-800",
    current: 3,
  },
  {
    value: "partial",
    label: "Presente ma parziale",
    shortLabel: "Parziale",
    className: "border-amber-300 bg-amber-50 text-amber-800",
    current: 1.5,
  },
  {
    value: "missing",
    label: "Non trovato / incoerente",
    shortLabel: "Non trovato",
    className: "border-red-300 bg-red-50 text-red-800",
    current: 0,
  },
  {
    value: "unverified",
    label: "Non verificato",
    shortLabel: "Da verificare",
    className: "border-slate-300 bg-slate-50 text-slate-600",
    current: 0,
  },
  {
    value: "not-applicable",
    label: "Non applicabile",
    shortLabel: "N/A",
    className: "border-slate-300 bg-slate-50 text-slate-600",
    current: 3,
  },
];

function getAuditStatusLabel(status?: AuditStatus) {
  return AUDIT_STATUS_OPTIONS.find((option) => option.value === status)?.label ?? "Da verificare";
}

const scoreOptions = [
  { value: 0, label: "0 - Non rilevante / assente" },
  { value: 1, label: "1 - Basso" },
  { value: 2, label: "2 - Medio" },
  { value: 3, label: "3 - Alto / critico" },
];

const currentOptions = [
  { value: 0, label: "0 - Non gestito" },
  { value: 1, label: "1 - Gestito male/parzialmente" },
  { value: 2, label: "2 - Gestito ma migliorabile" },
  { value: 3, label: "3 - Già ben presidiato" },
];

function emptyAnswer(): Answer {
  return { importance: 0, current: 0, fit: 0, note: "", auditStatus: "" };
}

function getItemScore(answer?: Answer) {
  if (!answer) return 0;
  const gap = Math.max(0, 3 - answer.current);
  const opportunity = (answer.importance + answer.fit) * gap;
  return Math.round((opportunity / 18) * 100);
}

function getScoreLabel(score: number) {
  if (score >= 70) {
    return {
      label: "Alta priorità",
      shortLabel: "Alta",
      className: "border-red-200 bg-red-50 text-red-700",
      pillClassName: "bg-red-100 text-red-800 ring-red-200",
    };
  }

  if (score >= 40) {
    return {
      label: "Priorità media",
      shortLabel: "Media",
      className: "border-amber-200 bg-amber-50 text-amber-700",
      pillClassName: "bg-amber-100 text-amber-800 ring-amber-200",
    };
  }

  return {
    label: "Bassa priorità",
    shortLabel: "Bassa",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    pillClassName: "bg-emerald-100 text-emerald-800 ring-emerald-200",
  };
}

function flattenItems(data: AssessmentMacro[] = ASSESSMENT_DATA) {
  return data.flatMap((macro) =>
    macro.categories.flatMap((category) =>
      category.items.map((item) => ({ macro, category, item }))
    )
  );
}

function scoreAverage(scores: number[]) {
  if (!scores.length) return 0;
  return Math.round(scores.reduce((sum, value) => sum + value, 0) / scores.length);
}

function sanitizeFilename(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9àèéìòù]+/gi, "-")
    .replace(/^-+|-+$/g, "") || "struttura";
}

function FieldLabel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`text-[11px] font-black uppercase tracking-[0.18em] text-slate-500 ${className}`}
    >
      {children}
    </span>
  );
}

const MACRO_GUIDE_PURPOSES: Record<string, string> = {
  m4: "posizionamento, brand e vendite dirette",
  m25: "efficienza e integrazione dei sistemi operativi",
  m115: "solidità dei documenti e degli accordi",
  m144: "fattibilità e potenziale della nuova offerta",
  m192: "controllo e trasparenza verso la proprietà",
  m212: "conformità autorizzativa della struttura",
  m235: "protezione dai principali rischi operativi",
  m259: "qualità e completezza della scheda di vendita",
  m312: "visibilità, distribuzione e rendimento delle OTA",
  m364: "prezzi, domanda e redditività",
  m414: "conversione delle richieste in prenotazioni",
  m448: "qualità dell’esperienza dell’ospite",
  m497: "continuità e precisione delle operations",
  m524: "gestione sicura di cauzioni e danni",
  m543: "incassi corretti e facilmente riconciliabili",
  m563: "controllo di pagamenti, costi e scadenze",
  m594: "correttezza amministrativa e contabile",
  m648: "riduzione dei rischi legali e dei reclami",
  m681: "affidabilità tecnica e tempi di intervento",
  m718: "coerenza degli standard e qualità reale",
  m753: "ricavi aggiuntivi e valore percepito",
};

const GUIDE_ITEM_HINTS: Array<[RegExp, string]> = [
  [/^target ospite$/i, "Identifica il pubblico con maggiore valore potenziale."],
  [/posizionamento/i, "Chiarisce come la struttura si distingue sul mercato."],
  [/booking engine/i, "Verifica se il sito converte visite in prenotazioni."],
  [/booking window|lead time/i, "Misura quanto prima gli ospiti prenotano."],
  [/\badr\b/i, "Misura il prezzo medio realmente venduto."],
  [/revpar/i, "Misura il ricavo prodotto da ogni camera disponibile."],
  [/occupancy|occupazione/i, "Misura quanta disponibilità viene realmente venduta."],
  [/pickup/i, "Mostra la velocità con cui crescono le prenotazioni."],
  [/forecast|previsione domanda/i, "Stima domanda, occupazione e ricavi futuri."],
  [/marginalità|margine|goppar/i, "Misura il guadagno dopo i costi operativi."],
  [/allotment/i, "Controlla le camere riservate a ciascun canale."],
  [/stop.?sale/i, "Verifica la chiusura tempestiva delle vendite."],
  [/minimum stay/i, "Valuta l’uso del soggiorno minimo per proteggere ricavi."],
  [/sincronizzazione/i, "Controlla l’allineamento automatico tra sistemi e canali."],
  [/foto|immagini|shooting/i, "Verifica se le immagini rappresentano e vendono bene la struttura."],
  [/recension|sentiment/i, "Misura reputazione, fiducia e criticità percepite."],
  [/conversion/i, "Misura quante opportunità diventano prenotazioni."],
  [/pricing|prezz|tariff|\bbar\b/i, "Valuta la coerenza dei prezzi con domanda e obiettivi."],
  [/cauzion|pre-autorizzazione/i, "Verifica tutela economica, regole e tempi di sblocco."],
  [/upsell|cross-selling/i, "Misura la capacità di generare ricavi aggiuntivi."],
  [/sla|tempi risposta|tempi intervento/i, "Misura rapidità e livello del servizio garantito."],
  [/check-in/i, "Valuta fluidità, sicurezza e qualità dell’arrivo."],
  [/check-out/i, "Valuta fluidità e controllo della partenza."],
  [/privacy|consens|gdpr/i, "Verifica raccolta, uso e protezione corretta dei dati."],
  [/cin|cir|codici identificativi/i, "Verifica presenza, validità ed esposizione dei codici."],
  [/istat|flussi turistici|arrivi\/presenze/i, "Controlla correttezza e puntualità degli invii statistici."],
  [/alloggiati|questura|pubblica sicurezza/i, "Controlla invio e conformità dei dati degli ospiti."],
  [/tassa di soggiorno|imposta soggiorno/i, "Verifica calcolo, dichiarazione e riversamento dell’imposta."],
  [/housekeeping|pulizi|biancheria/i, "Misura standard, coordinamento e controllo del servizio."],
  [/manutenz|guasti|impianti/i, "Valuta prevenzione, risposta e continuità della struttura."],
  [/rimbors|chargeback|storni/i, "Verifica gestione economica e documentale delle contestazioni."],
  [/report|rendicont/i, "Verifica se i dati supportano decisioni chiare e tempestive."],
  [/budget|business plan/i, "Confronta obiettivi economici, risorse e risultati attesi."],
  [/sito|direct booking|prenotazioni dirette/i, "Misura autonomia commerciale e vendite senza intermediari."],
];

function getGuideText(
  macro: AssessmentMacro,
  category: AssessmentCategory,
  item: AssessmentItem
) {
  const purpose = MACRO_GUIDE_PURPOSES[macro.id] ?? category.title.toLowerCase();

  if (/^target ospite$/i.test(item.text)) {
    if (macro.id === "m4") {
      return "Individua il pubblico ideale per brand e comunicazione.";
    }
    if (macro.id === "m144") {
      return "Stima i segmenti più redditizi per la nuova offerta.";
    }
  }

  const specificHint = GUIDE_ITEM_HINTS.find(([pattern]) => pattern.test(item.text));
  if (specificHint) return `${specificHint[1]} Utile per ${purpose}.`;

  return `Valuta “${item.text}” per ${category.title.toLowerCase()} e ${purpose}.`;
}

function GuideToggle({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={enabled}
      onClick={onToggle}
      title={enabled ? "Disattiva le spiegazioni al passaggio del mouse" : "Attiva le spiegazioni al passaggio del mouse"}
      className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-black transition ${
        enabled
          ? "border-emerald-500 bg-emerald-50 text-emerald-700 shadow-sm"
          : "border-[#E5DDF1] bg-white text-[#50627F] hover:border-emerald-300 hover:bg-emerald-50/50"
      }`}
    >
      <span
        className={`flex h-6 w-6 items-center justify-center rounded-full text-sm font-black ${
          enabled ? "bg-emerald-500 text-white" : "bg-[#F3EEF9] text-[#23124A]"
        }`}
      >
        ?
      </span>
      {enabled ? "Guida attiva" : "Attiva guida"}
    </button>
  );
}

const LOCAL_PILOT_OTA_OPTIONS = [
  { id: "booking", label: "Booking.com", active: "border-emerald-500 bg-emerald-100 text-emerald-950 shadow-sm", idle: "border-emerald-300 bg-white text-emerald-900 hover:bg-emerald-50" },
  { id: "agoda", label: "Agoda", active: "border-sky-500 bg-sky-100 text-sky-950 shadow-sm", idle: "border-sky-300 bg-white text-sky-900 hover:bg-sky-50" },
  { id: "airbnb", label: "Airbnb", active: "border-rose-500 bg-rose-100 text-rose-950 shadow-sm", idle: "border-rose-300 bg-white text-rose-900 hover:bg-rose-50" },
  { id: "vrbo", label: "Vrbo", active: "border-blue-500 bg-blue-100 text-blue-950 shadow-sm", idle: "border-blue-300 bg-white text-blue-900 hover:bg-blue-50" },
  { id: "expedia", label: "Expedia", active: "border-yellow-500 bg-yellow-100 text-yellow-950 shadow-sm", idle: "border-yellow-300 bg-white text-yellow-900 hover:bg-yellow-50" },
  { id: "holidu", label: "Holidu", active: "border-teal-500 bg-teal-100 text-teal-950 shadow-sm", idle: "border-teal-300 bg-white text-teal-900 hover:bg-teal-50" },
  { id: "hotels", label: "Hotels.com", active: "border-orange-500 bg-orange-100 text-orange-950 shadow-sm", idle: "border-orange-300 bg-white text-orange-900 hover:bg-orange-50" },
  { id: "travelocity", label: "Travelocity", active: "border-cyan-500 bg-cyan-100 text-cyan-950 shadow-sm", idle: "border-cyan-300 bg-white text-cyan-900 hover:bg-cyan-50" },
  { id: "trip", label: "Trip.com", active: "border-violet-500 bg-violet-100 text-violet-950 shadow-sm", idle: "border-violet-300 bg-white text-violet-900 hover:bg-violet-50" },
  { id: "priceline", label: "Priceline", active: "border-indigo-500 bg-indigo-100 text-indigo-950 shadow-sm", idle: "border-indigo-300 bg-white text-indigo-900 hover:bg-indigo-50" },
] as const;

type LocalPilotPeriod = 1 | 6 | 12;

export default function App() {
  const initialUiState = useMemo(() => loadUiState(), []);
  const [structures, setStructures] = useState<AnalyzedStructure[]>(loadAnalyzedStructures);
  const [activeStructureId, setActiveStructureId] = useState<string | null>(null);
  const [showStructures, setShowStructures] = useState(true);
  const [hydrated, setHydrated] = useState(false);
  const [ownerInfo, setOwnerInfo] = useState<OwnerInfo>(EMPTY_OWNER_INFO);

  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [rateQuotes, setRateQuotes] = useState<RateQuote[]>([]);
  const [rateDraft, setRateDraft] = useState<RateQuote>(EMPTY_RATE_DRAFT);
  const [availabilityProbes, setAvailabilityProbes] = useState<AvailabilityProbe[]>([]);
  const [availabilityDraft, setAvailabilityDraft] = useState<AvailabilityProbe>(EMPTY_AVAILABILITY_DRAFT);
  const [browserPilotResult, setBrowserPilotResult] = useState<BrowserPilotResult | null>(null);
  const [localPilotToken, setLocalPilotToken] = useState("");
  const [localPilotRunning, setLocalPilotRunning] = useState(false);
  const [localPilotMessage, setLocalPilotMessage] = useState("");
  const [localPilotGhost, setLocalPilotGhost] = useState(() => window.localStorage.getItem("velora-pilot-ghost") === "1");
  const [localPilotAssisted, setLocalPilotAssisted] = useState(() => window.localStorage.getItem("velora-pilot-assisted") === "1");
  const [localPilotPeriod, setLocalPilotPeriod] = useState<LocalPilotPeriod>(() => {
    const stored = Number(window.localStorage.getItem("velora-pilot-period") || "1");
    return stored === 6 || stored === 12 ? stored : 1;
  });
  const [localPilotSelectedChannels, setLocalPilotSelectedChannels] = useState<string[]>(() => {
    try {
      const parsed = JSON.parse(window.localStorage.getItem("velora-pilot-selected-channels") || "[]");
      return Array.isArray(parsed)
        ? LOCAL_PILOT_OTA_OPTIONS.map((item) => item.id).filter((id) => parsed.includes(id))
        : [];
    } catch {
      return [];
    }
  });
  const [localPilotIntervention, setLocalPilotIntervention] = useState<null | {
    id?: string; type?: string; otaId?: string; label?: string; reason?: string; instructions?: string;
    propertyName?: string; city?: string; url?: string; stay?: { checkin?: string; checkout?: string; adults?: number };
  }>(null);
  const [localPilotProgress, setLocalPilotProgress] = useState(0);
  const [localPilotPhase, setLocalPilotPhase] = useState("");
  const [autoAuditDraft, setAutoAuditDraft] = useState(
    initialUiState.autoAuditDraft ?? { name: "", website: "", city: "", province: "", rooms: "" }
  );
  const [autoAuditRunning, setAutoAuditRunning] = useState(false);
  const [autoAuditMessage, setAutoAuditMessage] = useState("");
  const [selectedRateCohort, setSelectedRateCohort] = useState("");
  const [assessmentMode, setAssessmentMode] = useState<AssessmentMode>("full");
  const [showQuickDeepDive, setShowQuickDeepDive] = useState(false);
  const [useCustomQuickSelection, setUseCustomQuickSelection] = useState(false);
  const [customQuickItemIds, setCustomQuickItemIds] = useState<string[]>(
    DEFAULT_CUSTOM_QUICK_ITEM_IDS
  );
  const [customQuickDraftIds, setCustomQuickDraftIds] = useState<string[]>(
    DEFAULT_CUSTOM_QUICK_ITEM_IDS
  );
  const [isCustomizingInterview, setIsCustomizingInterview] = useState(false);
  const [customizerSearch, setCustomizerSearch] = useState("");
  const [guideEnabled, setGuideEnabled] = useState(false);
  const [activeMacroId, setActiveMacroId] = useState(initialUiState.activeMacroId || ASSESSMENT_DATA[0]?.id || "");
  const [showOnlyPriority, setShowOnlyPriority] = useState(false);
  const [searchTerm, setSearchTerm] = useState(initialUiState.searchTerm || "");
  const [auditSourceFilter, setAuditSourceFilter] = useState(initialUiState.auditSourceFilter || "Tutte le fonti");

  const isQuickHotelBb = assessmentMode === "quick-hotel-bb";
  const isWebAudit = assessmentMode === "web-audit";
  const activeStructure = structures.find((item) => item.id === activeStructureId);
  const activeAuditDataBase: AuditData = activeStructure?.auditData
    ?? knownAuditData(activeStructureId)
    ?? blankAuditDataForStructure({
      id: activeStructureId || "bozza-corrente",
      name: ownerInfo.propertyName || "Nuova struttura",
      city: ownerInfo.city,
      province: ownerInfo.province,
      rooms: ownerInfo.rooms,
      website: activeStructure?.website,
    });
  const activeAuditData = useMemo(() => {
    const data=JSON.parse(JSON.stringify(activeAuditDataBase)) as any;
    if (!Array.isArray(data.otaPresence)) data.otaPresence=[];
    if (!data.otaPresence.some((item:any)=>item?.id==="holidu")) {
      data.otaPresence.push({
        id:"holidu", platform:"Holidu", group:"Holidu",
        status:"unverified", finding:"Da verificare su fonte pubblica.", source:"sito",
      });
    }
    if (data.pricingAudit && Array.isArray(data.pricingAudit.policies) && !data.pricingAudit.policies.some((item:any)=>item?.otaId==="holidu")) {
      data.pricingAudit.policies.push({
        otaId:"holidu", plans:"Non verificato", promotions:"Non verificato",
        confidence:"Da verificare", source:"sito",
      });
    }
    return data as AuditData;
  }, [activeAuditDataBase]);

  async function connectLocalAgent(silent = false): Promise<string> {
    try {
      const response = await fetch(localAgentUrl("/api/pilot/config"), { cache: "no-store", mode: "cors" });
      if (!response.ok) throw new Error("Agente locale non disponibile");
      const config = await response.json() as {
        token?: string;
        agentVersion?: string;
        autoAudit?: boolean;
        catalog?: { loaded?: boolean; count?: number; websites?: number; emails?: number; fileName?: string; error?: string };
      };
      if (!config.token) throw new Error("Token locale mancante");
      setLocalPilotToken(config.token);
      const catalogLabel = config.catalog?.loaded
        ? ` · Database locale: ${config.catalog.count || 0} strutture`
        : config.catalog?.error
          ? " · Database locale non leggibile"
          : " · Database locale non caricato";
      setLocalPilotMessage("Agente locale connesso" + (config.agentVersion ? " · " + config.agentVersion : "") + catalogLabel + ".");
      return config.token;
    } catch {
      setLocalPilotToken("");
      if (!silent) setLocalPilotMessage("Avvia l'agente Velora sul PC e consenti al browser l'accesso alla rete locale/loopback, poi riprova.");
      return "";
    }
  }

  useEffect(() => {
    void connectLocalAgent(true);
  }, []);

  useEffect(() => {
    const saveUiState = () => {
      const payload: PersistedUiState = {
        activeMacroId,
        searchTerm,
        auditSourceFilter,
        autoAuditDraft,
      };
      window.sessionStorage.setItem(UI_STATE_KEY, JSON.stringify(payload));
    };

    saveUiState();
    window.addEventListener("pagehide", saveUiState);
    window.addEventListener("beforeunload", saveUiState);
    return () => {
      saveUiState();
      window.removeEventListener("pagehide", saveUiState);
      window.removeEventListener("beforeunload", saveUiState);
    };
  }, [activeMacroId, searchTerm, auditSourceFilter, autoAuditDraft]);

  useEffect(() => {
    if (!hydrated || !showStructures) return;
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  }, [hydrated, showStructures]);

  useEffect(() => {
    if (!localPilotToken) return;
    let cancelled = false;

    async function recoverAutomaticAudit() {
      try {
        const response = await fetch(localAgentUrl("/api/audit/status"), { cache: "no-store", mode: "cors" });
        if (!response.ok || cancelled) return;
        let status = await response.json() as { running?: boolean; error?: string; message?: string; auditData?: unknown };

        if (status.running) {
          setAutoAuditRunning(true);
          setAutoAuditMessage(status.message || "Audit automatico in corso sul PC...");
          for (let attempt = 0; attempt < 300 && !cancelled; attempt += 1) {
            await new Promise((resolve) => window.setTimeout(resolve, 2000));
            const nextResponse = await fetch(localAgentUrl("/api/audit/status"), { cache: "no-store", mode: "cors" });
            if (!nextResponse.ok || cancelled) return;
            status = await nextResponse.json() as { running?: boolean; error?: string; message?: string; auditData?: unknown };
            if (cancelled) return;
            setAutoAuditMessage(status.message || (status.running ? "Analisi in corso..." : "Elaborazione completata."));
            if (!status.running) break;
          }
        }

        if (cancelled) return;
        setAutoAuditRunning(Boolean(status.running));
        if (status.error) {
          setAutoAuditMessage(status.error);
          return;
        }
        if (!status.running && isAuditData(status.auditData)) {
          const auditId = status.auditData.id;
          if (!isStructureDeleted(auditId) && !structures.some((item) => item.id === auditId)) {
            installAuditData(status.auditData);
            setAutoAuditMessage("Audit completato mentre eri fuori da Velora: risultato recuperato automaticamente.");
          }
        }
      } catch {
        // Se l'agente è spento, mantieni comunque pagina e dati correnti.
      }
    }

    void recoverAutomaticAudit();
    return () => {
      cancelled = true;
    };
  }, [localPilotToken]);

  useEffect(() => {
    if (!activeStructureId) {
      setBrowserPilotResult(null);
      return;
    }
    try {
      const saved = window.localStorage.getItem(`velora-browser-pilot:${activeStructureId}`);
      const parsed = saved ? JSON.parse(saved) as BrowserPilotResult : null;
      setBrowserPilotResult(parsed?.schema === "velora-browser-audit-pilot-v1" && parsed.propertyId === activeStructureId ? parsed : null);
    } catch {
      setBrowserPilotResult(null);
    }
  }, [activeStructureId]);

  function installAuditData(parsed: AuditData) {
    unmarkStructureDeleted(parsed.id);
    const seeded = auditSeedStructure(parsed);
    setStructures((previous) => {
      const index = previous.findIndex((item) => item.id === seeded.id);
      if (index < 0) return [...previous, seeded];
      const next = [...previous];
      next[index] = seeded;
      return next;
    });
    setActiveStructureId(seeded.id);
    window.localStorage.setItem(ACTIVE_STRUCTURE_KEY, seeded.id);
    setOwnerInfo(seeded.ownerInfo);
    setAnswers(seeded.answers);
    setRateQuotes([]);
    setAvailabilityProbes([]);
    setSelectedRateCohort("");
    setAssessmentMode("web-audit");
    setActiveMacroId(EXTERNAL_WEB_AUDIT_DATA[0]?.id ?? "");
    setSearchTerm("");
    setAuditSourceFilter("Tutte le fonti");
    setShowStructures(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
    return seeded;
  }

  async function startAutomaticAudit() {
    if (autoAuditRunning) return;
    const website = autoAuditDraft.website.trim();
    if (!website) {
      window.alert("Inserisci il sito ufficiale della struttura.");
      return;
    }
    const token = await connectLocalAgent(false);
    if (!token) {
      setAutoAuditMessage("L'agente locale non e' attivo. Avvialo sul PC e premi di nuovo Analizza struttura.");
      return;
    }
    setAutoAuditRunning(true);
    setAutoAuditMessage("Avvio audit: sto leggendo il sito ufficiale e preparando la scheda Velora...");
    try {
      const response = await fetch(localAgentUrl("/api/audit/start"), {
        method: "POST",
        mode: "cors",
        headers: { "Content-Type": "application/json", "X-Velora-Local-Token": token },
        body: JSON.stringify(autoAuditDraft),
      });
      if (!response.ok) {
        const body = await response.json() as { error?: string };
        throw new Error(body.error || "Avvio audit non riuscito");
      }
      for (let attempt = 0; attempt < 300; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 2000));
        const statusResponse = await fetch(localAgentUrl("/api/audit/status"), { cache: "no-store", mode: "cors" });
        if (!statusResponse.ok) throw new Error("Impossibile leggere lo stato dell'audit automatico.");
        const status = await statusResponse.json() as { running?: boolean; error?: string; message?: string; auditData?: unknown };
        setAutoAuditMessage(status.message || (status.running ? "Analisi in corso..." : "Elaborazione completata."));
        if (!status.running) {
          if (status.error) throw new Error(status.error);
          if (!isAuditData(status.auditData)) throw new Error("L'agente non ha restituito un audit Velora valido.");
          const seeded = installAuditData(status.auditData);
          setAutoAuditDraft({ name: "", website: "", city: "", province: "", rooms: "" });
          setAutoAuditMessage("Audit iniziale creato per " + seeded.name + ". Completa OTA, recensioni e prezzi futuri prima del report definitivo.");
          return;
        }
      }
      throw new Error("Tempo massimo dell'audit automatico superato.");
    } catch (error) {
      setAutoAuditMessage(error instanceof Error ? error.message : "Errore durante l'audit automatico.");
    } finally {
      setAutoAuditRunning(false);
    }
  }

  async function importAuditDataset(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 10_000_000) {
      window.alert("Il file audit e' troppo grande (massimo 10 MB).");
      return;
    }
    try {
      const parsed = JSON.parse(await file.text()) as unknown;
      if (!isAuditData(parsed)) throw new Error("JSON audit Velora non valido.");
      const seeded = installAuditData(parsed);
      window.alert("Audit importato: " + seeded.name + ". La struttura e' ora disponibile nell'archivio di questo browser.");
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Impossibile importare il JSON audit.");
    }
  }

  async function importBrowserPilotResult(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 5_000_000) {
      window.alert("Il file del pilota è troppo grande (massimo 5 MB).");
      return;
    }
    try {
      const parsed = JSON.parse(await file.text()) as BrowserPilotResult;
      if (parsed.schema !== "velora-browser-audit-pilot-v1" || parsed.propertyId !== activeAuditData.id || !Array.isArray(parsed.observations)) {
        throw new Error("File non valido o appartenente a un'altra struttura.");
      }
      const cleaned: BrowserPilotResult = {
        schema: parsed.schema, propertyId: parsed.propertyId, createdAt: String(parsed.createdAt || ""),
        bookingEngine: parsed.bookingEngine && typeof parsed.bookingEngine === "object" ? {
          status: String(parsed.bookingEngine.status || "unverified"), provider: String(parsed.bookingEngine.provider || ""),
          url: String(parsed.bookingEngine.url || ""), mode: String(parsed.bookingEngine.mode || ""),
          evidence: String(parsed.bookingEngine.evidence || ""),
        } : undefined,
        discoveredSources: parsed.discoveredSources && typeof parsed.discoveredSources === "object"
          ? parsed.discoveredSources
          : undefined,
        otaProfiles: parsed.otaProfiles && typeof parsed.otaProfiles === "object"
          ? parsed.otaProfiles
          : undefined,
        reputation: parsed.reputation && typeof parsed.reputation === "object" ? parsed.reputation : undefined,
        photoAudit: parsed.photoAudit && typeof parsed.photoAudit === "object" ? parsed.photoAudit : undefined,
        roomReferences: Array.isArray(parsed.roomReferences) ? parsed.roomReferences.slice(0, 60) : undefined,
        observations: parsed.observations
          .filter((item) => item && typeof item.otaId === "string" && typeof item.month === "string" && typeof item.status === "string")
          .slice(0, 500)
          .map((item) => ({
            ...item,
            quotes: Array.isArray(item.quotes)
              ? item.quotes.filter((quote) => quote && typeof quote.roomType === "string" && Number.isFinite(Number(quote.total))).slice(0, 20)
              : [],
          })),
      };
      const merged = mergeBrowserPilotResults(browserPilotResult, cleaned);
      setBrowserPilotResult(merged);
      window.localStorage.setItem(`velora-browser-pilot:${cleaned.propertyId}`, JSON.stringify(merged));
      applyPilotEvidence(cleaned);
      const detectedPilotRates = pilotDetectedRateQuotes(cleaned);
      const verifiedPilotRates = detectedPilotRates.filter((quote) => quote.pilotVerified !== false).length;
      window.alert(`${cleaned.observations.length} verifiche importate · ${detectedPilotRates.length} prezzi/tariffe rilevati · ${verifiedPilotRates} validati.`);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Impossibile leggere il file del pilota.");
    }
  }

  function applyPilotEvidence(result: BrowserPilotResult) {
    const automaticPilotQuotes = pilotDetectedRateQuotes(result);
    if (automaticPilotQuotes.length) {
      setRateQuotes((previous) => mergePilotRateQuotes(previous, automaticPilotQuotes));
      setSelectedRateCohort((current) => current || rateCohortKey(automaticPilotQuotes[0]));
    }
    const automaticBookingCount = automaticPilotQuotes.filter((quote) => quote.otaId === "booking").length;
    const automaticCounts = Object.fromEntries(PILOT_TARIFF_OTA_IDS.filter((otaId)=>otaId!=="booking").map((otaId) => [otaId, automaticPilotQuotes.filter((quote) => quote.otaId === otaId).length]));

    const otaLabels: Record<string,string> = PILOT_OTA_LABELS;

    Object.entries(result.discoveredSources || {}).forEach(([otaId, discovery]) => {
      if (!otaLabels[otaId] || !discovery) return;
      const answerId = `audit-ota-${otaId}`;
      if ((discovery.presenceDetected || discovery.candidateUrl || discovery.status === "existing_unverified") && !(discovery.status === "found" && discovery.url)) {
        updateAnswer(answerId, {
          auditStatus: "partial",
          note:
            "Esito: PAGINA OTA RILEVATA · identità da confermare\n" +
            "Riscontro osservato: Velora ha trovato una pagina/scheda " + otaLabels[otaId] + " e ne conserva l'URL.\n" +
            "La presenza non viene più trasformata in assenza solo perché il portale limita la verifica automatica.\n" +
            "Fonte candidata: " + (discovery.candidateUrl || discovery.url || "URL non disponibile") + "\n" +
            "Limite: gli eventuali prezzi letti restano visibili come da verificare e non entrano nel delta.\n" +
            "Dettaglio tecnico: " + (discovery.evidence || discovery.status),
        });
        return;
      }
      if (discovery.status === "found" && discovery.url) {
        updateAnswer(answerId, {
          auditStatus: "present",
          note:
            "Esito: Presente\n" +
            `Riscontro osservato: Velora ha individuato una scheda ${otaLabels[otaId]} attribuibile alla struttura.\n` +
            "Motivo dell'esito: la ricerca master e/o la ricerca mirata hanno prodotto un candidato verificato sulla pagina reale.\n" +
            "Scheda rilevata: " + (discovery.title || "titolo non disponibile") + "\n" +
            "Fonte: " + discovery.url + "\n" +
            "Dettaglio tecnico: " + (discovery.evidence || "nessun dettaglio aggiuntivo"),
        });
      } else if (discovery.status !== "existing") {
        updateAnswer(answerId, {
          auditStatus: "unverified",
          note:
            "Esito: Da verificare\n" +
            `Riscontro osservato: la ricerca automatica ${otaLabels[otaId]} non ha prodotto una scheda attribuibile con sufficiente certezza.\n` +
            "Motivo dell'esito: " + (discovery.evidence || discovery.status) + "\n" +
            `Questo non prova che la struttura sia assente da ${otaLabels[otaId]}.`,
        });
      }
    });

    Object.entries(result.otaProfiles || {}).forEach(([otaId, profile]) => {
      if (!otaLabels[otaId] || !profile || profile.status !== "sampled") return;
      const rating = Number.isFinite(profile.rating) && Number.isFinite(profile.ratingScale)
        ? `${Number(profile.rating).toFixed(1)}/${Number(profile.ratingScale).toFixed(0)}`
        : "n.d.";
      const reviewCount = profile.reviewCount ? String(profile.reviewCount) : "n.d.";
      const recommendation = Number.isFinite(profile.recommendationRate)
        ? `${Number(profile.recommendationRate).toFixed(1)}%`
        : "n.d.";
      const priceText = (profile.visiblePrices || []).length
        ? (profile.visiblePrices || []).slice(0, 4).map((item) => `€${Number(item.amount).toFixed(2)}`).join(", ")
        : "nessun prezzo EUR leggibile con certezza";
      const commercialHosts = (profile.commercialHosts || []).length
        ? (profile.commercialHosts || []).slice(0, 8).join(", ")
        : "nessun partner commerciale riconosciuto nel campione";
      updateAnswer(`audit-ota-${otaId}`, {
        auditStatus: "present",
        note:
          "Esito: Presente\n" +
          `Profilo pubblico ${otaLabels[otaId]} letto direttamente da Velora.\n` +
          "Scheda: " + (profile.title || "titolo non disponibile") + "\n" +
          "Rating: " + rating + " · recensioni: " + reviewCount + " · raccomandazione: " + recommendation + "\n" +
          "Prezzi visibili non attribuiti a camera/piano: " + priceText + "\n" +
          "Link commerciali rilevati: " + commercialHosts + "\n" +
          "Fonte: " + (profile.url || "n.d.") + "\n" +
          "Dettaglio tecnico: " + (profile.evidence || "nessun dettaglio aggiuntivo") +
          "\nLimite: questi dati descrivono la scheda/metasearch e non entrano nel delta tariffario finché camera, date e condizioni non sono comparabili.",
      });
    });

    const bookingObs = result.observations.filter((item) => item.otaId === "booking");
    if (bookingObs.length) {
      const withQuotes = bookingObs.filter((item) => Array.isArray(item.quotes) && item.quotes.length);
      const verifiedCandidates = withQuotes.flatMap((item) => (item.quotes || []).filter((quote) => quote.verified));
      const noRate = bookingObs.filter((item) => item.status === "no_public_rate").length;
      const evidence =
        "Campionamento futuro Booking.com: " + bookingObs.length + " date/mese controllati. " +
        "Righe camera/prezzo rilevate in " + withQuotes.length + " controlli; candidati con riferimento esplicito a totale/soggiorno: " +
        verifiedCandidates.length + "; date con nessuna tariffa pubblica esplicitamente rilevata: " + noRate + ".";
      updateAnswer("audit-policy-booking", {
        note:
          evidence +
          "\nTariffe Booking validate importate automaticamente nella tabella economica: " + automaticBookingCount + ". " +
          "Il delta con altre OTA resta separato finché tasse, condizioni e identità della stessa unità fisica non sono confermate.",
      });
    }

    for (const otaId of ["agoda", "airbnb", "vrbo", "expedia", "hotels", "travelocity", "trip", "priceline"] as const) {
      const observations = result.observations.filter((item) => item.otaId === otaId);
      if (!observations.length) continue;
      const withQuotes = observations.filter((item) => Array.isArray(item.quotes) && item.quotes.length);
      const verifiedCandidates = withQuotes.flatMap((item) => (item.quotes || []).filter((quote) => quote.verified));
      const selectedCandidates = withQuotes.flatMap((item) => (item.quotes || []).filter((quote) => quote.comparisonSelected !== false));
      const diagnostics = observations.slice(-6).map((item) => {
        const quotes = item.quotes || [];
        const selected = quotes.filter((quote) => quote.comparisonSelected !== false);
        const sameRoom = selected.filter((quote) => quote.roomMatchStatus === "same-room").length;
        const differentRoom = selected.filter((quote) => quote.roomMatchStatus === "different-room-fallback").length;
        const roomNote = sameRoom
          ? ` · stessa camera Booking: ${sameRoom} riga/e`
          : differentRoom
            ? " · ATTENZIONE: solo camera diversa dalla reference Booking"
            : "";
        return [
          `${item.checkin} → ${item.checkout}: ${pilotCoverageSummary(result, item.month, otaId) || item.status}${roomNote}`,
          item.evidence ? `Motivo: ${item.evidence}` : "",
          item.finalUrl ? `Pagina finale visitata: ${item.finalUrl}` : "",
        ].filter(Boolean).join("\n");
      }).join("\n\n");
      updateAnswer(`audit-policy-${otaId}`, {
        note:
          "Campionamento futuro " + otaLabels[otaId] + ": " + observations.length + " data/e controllate. " +
          "Controlli con almeno un prezzo letto: " + withQuotes.length + "; righe prezzo validate: " +
          verifiedCandidates.length + "; righe selezionate rispetto alla camera reference Booking: " + selectedCandidates.length + ".\n" +
          "Tariffe " + otaLabels[otaId] + " importate nella tabella economica: " + (automaticCounts[otaId] || 0) + ".\n\n" +
          diagnostics +
          "\n\nRegola confronto: Velora usa la stessa camera reference Booking quando disponibile. Una camera diversa viene riportata solo come alternativa segnalata e non produce delta.",
      });
    }

    const reputation = result.reputation;
    if (reputation?.status === "sampled") {
      const formatTheme = (entry: BrowserPilotReviewTheme, kind: "forza" | "criticita") => {
        const phrases = (entry.phrases || []).slice(0, 4).map((value) => "“" + value + "”").join(" · ");
        const examples = (entry.examples || []).slice(0, 2).map((value) => "“" + value + "”").join(" · ");
        const lead = entry.theme + " — " + entry.count + " recensioni" + (entry.weight ? " · ricorrenza " + entry.weight : "");
        return [
          lead,
          phrases ? "Espressioni rilevate: " + phrases : "",
          examples ? "Esempi dal campione: " + examples : "",
          kind === "criticita" && entry.action ? "Azione: " + entry.action : "",
        ].filter(Boolean).join("\n");
      };

      const strengths = (reputation.strengths || []).map((entry) => formatTheme(entry, "forza")).join("\n\n");
      const weaknesses = (reputation.weaknesses || []).map((entry) => formatTheme(entry, "criticita")).join("\n\n");

      const isolated = (reputation.isolatedSignals || []).map((entry) => {
        const phrases = (entry.phrases || []).slice(0, 3).map((value) => "“" + value + "”").join(" · ");
        const examples = (entry.examples || []).slice(0, 1).map((value) => "“" + value + "”").join(" · ");
        return [
          entry.theme + " — 1 segnalazione isolata",
          phrases ? "Espressione: " + phrases : "",
          examples ? "Esempio: " + examples : "",
        ].filter(Boolean).join("\n");
      }).join("\n\n");

      const actions = (reputation.weaknesses || []).map((entry) =>
        entry.theme + ": " + (entry.action || "Approfondire il tema e definire un intervento misurabile.")
      ).join("\n");

      const recurringThemes = (reputation.recurringThemes || []).map((entry) => {
        const phrases = (entry.phrases || []).slice(0, 4).map((value) => "“" + value + "”").join(" · ");
        return [
          entry.theme + " — " + (entry.sentiment === "negativo" ? "NEGATIVO" : "POSITIVO") + " · " + entry.count + " recensioni",
          phrases ? "Espressioni: " + phrases : "",
        ].filter(Boolean).join("\n");
      }).join("\n\n");

      updateAnswer("audit-google-strengths", { note: strengths || "Nessun punto di forza ricorrente classificato nel campione disponibile." });
      updateAnswer("audit-google-weaknesses", { note: weaknesses || "Nessuna criticità ricorrente classificata nel campione disponibile." });
      updateAnswer("audit-google-isolated", { note: isolated || "Nessuna segnalazione isolata significativa nel campione disponibile." });
      updateAnswer("audit-google-keywords", { note: recurringThemes || "Nessun tema ripetuto in almeno due recensioni del campione." });
      updateAnswer("audit-google-actions", { note: actions || "Nessuna azione prioritaria derivata da criticità ricorrenti nel campione." });
    }

    const photo = result.photoAudit;
    if (photo?.status === "sampled") {
      const categories = Object.entries(photo.categoryCounts || {})
        .map(([name, count]) => name + ": " + count).join(" · ");
      const note = [
        photo.evidence || "",
        (photo.strengths || []).length ? "Punti di forza: " + (photo.strengths || []).join(" ") : "",
        (photo.gaps || []).length ? "Gap: " + (photo.gaps || []).join(" ") : "",
        categories ? "Copertura categorie: " + categories + "." : "",
        (photo.actions || []).length ? "Azioni: " + (photo.actions || []).join(" ") : "",
      ].filter(Boolean).join("\n");
      updateAnswer("audit-photo-score", {
        current: Number(photo.score || 0),
        note,
      });
    }
  }

  async function startLocalPilot(months: LocalPilotPeriod, channelIds: string[]) {
    if (localPilotRunning) return;
    if (!channelIds.length) {
      setLocalPilotMessage("Seleziona almeno una OTA prima di avviare l'analisi.");
      return;
    }
    const token = await connectLocalAgent(false);
    if (!token) {
      setLocalPilotMessage("L'agente locale non e' attivo. Avvialo sul PC e riprova.");
      return;
    }
    setLocalPilotRunning(true);
    setLocalPilotProgress(1);
    setLocalPilotPhase("Avvio scraping");
    const pilotStartedAt = Date.now();
    setLocalPilotMessage("Rilevazione in corso · 00:00 trascorsi. Lascia aperto il servizio locale; il JSON viene salvato progressivamente.");
    try {
      const started = await fetch(localAgentUrl("/api/pilot/start"), {
        method: "POST",
        mode: "cors",
        headers: { "Content-Type": "application/json", "X-Velora-Local-Token": token },
        body: JSON.stringify({
          propertyId: activeAuditData.id,
          months,
          channels: channelIds,
          ghost: localPilotGhost,
          assisted: localPilotAssisted,
          pricingOnly: true,
          propertyData: {
            id: activeAuditData.id,
            name: activeAuditData.name,
            city: activeAuditData.city,
            province: activeAuditData.province,
            sources: activeAuditData.sources,
          },
        }),
      });
      if (!started.ok) {
        const body = await started.json() as { error?: string };
        throw new Error(body.error || "Avvio non riuscito");
      }
      for (;;) {
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
        const response = await fetch(localAgentUrl("/api/pilot/status"), { cache: "no-store", mode: "cors" });
        if (!response.ok) throw new Error("Impossibile leggere lo stato del servizio locale.");
        const status = await response.json() as {
          running: boolean; error?: string; result?: BrowserPilotResult;
          intervention?: null | {
            id?: string; type?: string; otaId?: string; label?: string; reason?: string; instructions?: string;
            propertyName?: string; city?: string; url?: string; stay?: { checkin?: string; checkout?: string; adults?: number };
          };
        };
        setLocalPilotIntervention(status.intervention || null);
        const count = status.result?.observations?.length || 0;
        const observedRows = status.result?.observations?.reduce((sum, item) => sum + (item.quotes?.length || 0), 0) || 0;
        const verifiedPilotRates = status.result ? pilotDetectedRateQuotes(status.result).length : 0;
        const discovery = status.result?.discoveryProgress;
        const discoveryActive = status.running && discovery && Number(discovery.total || 0) > 0 && Number(discovery.completed || 0) < Number(discovery.total || 0);
        const elapsed = formatPilotElapsed(Date.now() - pilotStartedAt);
        const progressUpdatedAt = discovery?.updatedAt ? Date.parse(discovery.updatedAt) : NaN;
        const progressAgeSeconds = Number.isFinite(progressUpdatedAt) ? Math.max(0, Math.round((Date.now() - progressUpdatedAt) / 1000)) : 0;
        const discoveryText = discoveryActive
          ? `Discovery OTA ${Number(discovery.completed || 0)}/${Number(discovery.total || 0)}${discovery.label ? ` · ${discovery.label}` : ""} · ${elapsed} trascorsi${progressAgeSeconds > 45 ? ` · watchdog: ultimo avanzamento ${progressAgeSeconds}s fa` : ""}. `
          : status.running
            ? `Elaborazione tariffe · ${elapsed} trascorsi. `
            : "";
        const expectedChannels = Math.max(1, channelIds.length);
        const expectedMonths = Math.max(1, status.result?.plan?.length || (months === 12 ? 13 : months));
        const expectedChecks = expectedChannels * expectedMonths;
        if (status.intervention) {
          setLocalPilotProgress(Math.max(40, localPilotProgress));
          setLocalPilotPhase(`Intervento richiesto · ${status.intervention.label || status.intervention.otaId || "OTA"}`);
        } else if (discoveryActive) {
          const fraction = Math.min(1, Number(discovery.completed || 0) / Math.max(1, Number(discovery.total || 1)));
          setLocalPilotProgress(Math.max(2, Math.round(5 + fraction * 35)));
          setLocalPilotPhase(`Discovery OTA ${Number(discovery.completed || 0)}/${Number(discovery.total || 0)}`);
        } else if (status.running) {
          const fraction = Math.min(1, count / expectedChecks);
          setLocalPilotProgress(Math.max(40, Math.round(40 + fraction * 55)));
          setLocalPilotPhase(`Verifica prezzi OTA · ${count}/${expectedChecks}`);
        } else {
          setLocalPilotProgress(status.error ? Math.min(99, localPilotProgress) : 100);
          setLocalPilotPhase(status.error ? "Scraping interrotto" : "Scraping completato");
        }
        setLocalPilotMessage(
          status.running
            ? status.intervention
              ? `Scraping in pausa su ${status.intervention.label || status.intervention.otaId || "OTA"}: completa l\'azione richiesta nella finestra Chrome e poi premi «Ho completato · riprendi».`
              : `${discoveryText}${count} controlli tariffari completati · ${observedRows} righe prezzo osservate · ${verifiedPilotRates} validate.`
            : status.error
              ? `Interrotto dopo ${elapsed} · ${count} controlli tariffari · ${observedRows} righe prezzo osservate. Errore: ${status.error}`
              : `Completato in ${elapsed} · ${count} controlli tariffari · ${observedRows} righe prezzo osservate · ${verifiedPilotRates} validate e importate. Esiti pronti per il PDF.`
        );
        if (!status.running) {
          if (status.result?.schema === "velora-browser-audit-pilot-v1" && status.result.propertyId === activeAuditData.id) {
            const mergedResult = mergeBrowserPilotResults(browserPilotResult, status.result);
            setBrowserPilotResult(mergedResult);
            window.localStorage.setItem(`velora-browser-pilot:${activeAuditData.id}`, JSON.stringify(mergedResult));
            applyPilotEvidence(status.result);
          }
          setLocalPilotIntervention(null);
          break;
        }
      }
    } catch (error) {
      const elapsed = formatPilotElapsed(Date.now() - pilotStartedAt);
      setLocalPilotMessage(`Interrotto dopo ${elapsed} · ${error instanceof Error ? error.message : "Errore della rilevazione locale."}`);
    } finally {
      setLocalPilotRunning(false);
      setLocalPilotIntervention(null);
    }
  }

  async function respondLocalPilotIntervention(action: "continue" | "skip") {
    if (!localPilotToken || !localPilotIntervention) return;
    try {
      const response = await fetch(localAgentUrl("/api/pilot/intervention"), {
        method: "POST",
        mode: "cors",
        headers: { "Content-Type": "application/json", "X-Velora-Local-Token": localPilotToken },
        body: JSON.stringify({ action }),
      });
      if (!response.ok) {
        const body = await response.json() as { error?: string };
        throw new Error(body.error || "Impossibile inviare la risposta all\'agente.");
      }
      setLocalPilotMessage(action === "continue" ? "Intervento confermato. Velora riprende lo scraping..." : "OTA saltata su richiesta. Velora prosegue con il canale successivo...");
      setLocalPilotIntervention(null);
    } catch (error) {
      setLocalPilotMessage(error instanceof Error ? error.message : "Errore durante la ripresa dello scraping.");
    }
  }
  const customQuickData = useMemo(
    () => selectAssessmentItems(new Set(customQuickItemIds)),
    [customQuickItemIds]
  );
  const quickTemplateData = useCustomQuickSelection
    ? customQuickData
    : QUICK_HOTEL_BB_ALL_DATA;
  const assessmentData = isWebAudit
    ? EXTERNAL_WEB_AUDIT_DATA
    : isQuickHotelBb
      ? useCustomQuickSelection
        ? customQuickData
        : showQuickDeepDive
          ? QUICK_HOTEL_BB_ALL_DATA
          : QUICK_HOTEL_BB_CORE_DATA
      : ASSESSMENT_DATA;

  const allRows = useMemo(() => flattenItems(assessmentData), [assessmentData]);

  const answeredCount = useMemo(
    () =>
      allRows.filter(({ item }) => {
        const answer = answers[item.id];
        return answer && (
          answer.importance ||
          answer.current ||
          answer.fit ||
          answer.note ||
          answer.auditStatus
        );
      }).length,
    [allRows, answers]
  );

  const globalScore = useMemo(() => {
    const scores = allRows.map((row) => getItemScore(answers[row.item.id]));
    return scoreAverage(scores);
  }, [allRows, answers]);

  const macroScores = useMemo(() => {
    return assessmentData.map((macro) => {
      const macroItems = macro.categories.flatMap((category) => category.items);
      const scores = macroItems.map((item) => getItemScore(answers[item.id]));
      return {
        id: macro.id,
        title: macro.title,
        score: scoreAverage(scores),
        totalItems: macroItems.length,
        answeredItems: macroItems.filter((item) => {
          const answer = answers[item.id];
          return answer && (
            answer.importance ||
            answer.current ||
            answer.fit ||
            answer.note ||
            answer.auditStatus
          );
        }).length,
      };
    });
  }, [answers, assessmentData]);

  const topOpportunities = useMemo(() => {
    return allRows
      .map((row) => ({
        ...row,
        score: getItemScore(answers[row.item.id]),
        answer: answers[row.item.id],
      }))
      .filter((row) => row.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 12);
  }, [allRows, answers]);

  useEffect(() => {
    const selectedId = window.localStorage.getItem(ACTIVE_STRUCTURE_KEY);
    const selected = structures.find((item) => item.id === selectedId);
    if (selected) {
      setActiveStructureId(selected.id);
      setOwnerInfo({ ...EMPTY_OWNER_INFO, ...selected.ownerInfo });
      setAnswers(selected.answers);
      setRateQuotes(Array.isArray(selected.rateQuotes) ? selected.rateQuotes : []);
      setAvailabilityProbes(Array.isArray(selected.availabilityProbes) ? selected.availabilityProbes : []);
      setAssessmentMode(selected.assessmentMode);
      setActiveMacroId(EXTERNAL_WEB_AUDIT_DATA[0]?.id ?? "");
      setHydrated(true);
      return;
    }
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      setHydrated(true);
      return;
    }

    try {
      const parsed = JSON.parse(raw);
      if (parsed.ownerInfo) setOwnerInfo({ ...EMPTY_OWNER_INFO, ...parsed.ownerInfo });
      if (parsed.answers) setAnswers(parsed.answers);
      if (Array.isArray(parsed.rateQuotes)) setRateQuotes(parsed.rateQuotes);
      if (Array.isArray(parsed.availabilityProbes)) setAvailabilityProbes(parsed.availabilityProbes);
      if (
        parsed.assessmentMode === "full" ||
        parsed.assessmentMode === "quick-hotel-bb" ||
        parsed.assessmentMode === "web-audit"
      ) {
        setAssessmentMode(parsed.assessmentMode);
      }
      if (Array.isArray(parsed.customQuickItemIds) && parsed.customQuickItemIds.length) {
        setCustomQuickItemIds(parsed.customQuickItemIds);
        setCustomQuickDraftIds(parsed.customQuickItemIds);
      }
      if (typeof parsed.useCustomQuickSelection === "boolean") {
        setUseCustomQuickSelection(parsed.useCustomQuickSelection);
      }
      if (typeof parsed.guideEnabled === "boolean") {
        setGuideEnabled(parsed.guideEnabled);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        ownerInfo,
        answers,
        rateQuotes,
        availabilityProbes,
        assessmentMode,
        customQuickItemIds,
        useCustomQuickSelection,
        guideEnabled,
      })
    );
  }, [hydrated, ownerInfo, answers, rateQuotes, availabilityProbes, assessmentMode, customQuickItemIds, useCustomQuickSelection, guideEnabled]);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(STRUCTURES_KEY, JSON.stringify(structures));
  }, [hydrated, structures]);

  useEffect(() => {
    if (!hydrated || !activeStructureId) return;
    setStructures((previous) => previous.map((item) => item.id === activeStructureId ? {
      ...item,
      name: ownerInfo.propertyName || item.name,
      city: ownerInfo.city || item.city,
      province: ownerInfo.province || item.province,
      rooms: ownerInfo.rooms || item.rooms,
      ownerInfo,
      answers,
      rateQuotes,
      availabilityProbes,
      assessmentMode,
      updatedAt: new Date().toISOString(),
    } : item));
  }, [hydrated, activeStructureId, ownerInfo, answers, rateQuotes, availabilityProbes, assessmentMode]);

  const activeMacro =
    assessmentData.find((macro) => macro.id === activeMacroId) ?? assessmentData[0];

  const activeMacroScore = macroScores.find((macro) => macro.id === activeMacro?.id);
  const globalLabel = getScoreLabel(globalScore);
  const progressPct = allRows.length ? Math.round((answeredCount / allRows.length) * 100) : 0;

  function updateOwnerInfo<K extends keyof OwnerInfo>(key: K, value: OwnerInfo[K]) {
    setOwnerInfo((prev) => ({ ...prev, [key]: value }));
  }

  function openStructuresHome() {
    setIsCustomizingInterview(false);
    setShowStructures(true);
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: "auto" }));
  }

  function openStructure(structure: AnalyzedStructure) {
    if (!activeStructureId && (ownerInfo.propertyName || Object.keys(answers).length || rateQuotes.length || availabilityProbes.length)) {
      const draftId = `bozza-${Date.now()}`;
      setStructures((previous) => [...previous, {
        id: draftId,
        name: ownerInfo.propertyName || "Bozza precedente",
        city: ownerInfo.city,
        province: ownerInfo.province,
        rooms: ownerInfo.rooms,
        ownerInfo,
        answers,
        rateQuotes,
        availabilityProbes,
        assessmentMode,
        updatedAt: new Date().toISOString(),
      }]);
    }
    setActiveStructureId(structure.id);
    window.localStorage.setItem(ACTIVE_STRUCTURE_KEY, structure.id);
    setOwnerInfo({ ...EMPTY_OWNER_INFO, ...structure.ownerInfo });
    setAnswers(structure.answers);
    setRateQuotes(Array.isArray(structure.rateQuotes) ? structure.rateQuotes : []);
    setAvailabilityProbes(Array.isArray(structure.availabilityProbes) ? structure.availabilityProbes : []);
    setSelectedRateCohort("");
    setAssessmentMode(structure.assessmentMode);
    setActiveMacroId(
      (structure.assessmentMode === "web-audit" ? EXTERNAL_WEB_AUDIT_DATA : ASSESSMENT_DATA)[0]?.id ?? ""
    );
    setSearchTerm("");
    setAuditSourceFilter("Tutte le fonti");
    setShowStructures(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function deleteStructure(structure: AnalyzedStructure) {
    const confirmed = window.confirm(
      `Eliminare “${structure.name}” da Strutture analizzate?\n\nVerranno rimossi anche scraping, risultati pilota e cache OTA locali, così una nuova analisi ripartirà davvero da zero.`
    );
    if (!confirmed) return;

    // Prova prima la pulizia dell'agente locale. Se l'agente è spento,
    // non fingiamo che il reset sia completo: l'utente può riaccenderlo e riprovare.
    let token = localPilotToken;
    if (!token) token = await connectLocalAgent(true);
    if (!token) {
      window.alert("Per una cancellazione completa avvia prima l'agente Velora locale, poi riprova.");
      return;
    }

    try {
      const response = await fetch(localAgentUrl("/api/pilot/reset"), {
        method: "POST",
        mode: "cors",
        headers: {
          "Content-Type": "application/json",
          "X-Velora-Local-Token": token,
        },
        body: JSON.stringify({
          propertyId: structure.id,
          name: structure.name,
          website: structure.website || structure.auditData?.website || "",
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({})) as { error?: string };
        throw new Error(body.error || "Reset locale non riuscito.");
      }
    } catch (error) {
      window.alert(
        "Non ho cancellato la scheda perché il reset locale non è riuscito. " +
        (error instanceof Error ? error.message : "Riprova con l'agente Velora acceso.")
      );
      return;
    }

    markStructureDeleted(structure.id);
    setStructures((previous) => previous.filter((item) => item.id !== structure.id));
    window.localStorage.removeItem(`velora-browser-pilot:${structure.id}`);

    if (activeStructureId === structure.id) {
      setActiveStructureId(null);
      window.localStorage.removeItem(ACTIVE_STRUCTURE_KEY);
      setOwnerInfo(EMPTY_OWNER_INFO);
      setAnswers({});
      setRateQuotes([]);
      setAvailabilityProbes([]);
      setBrowserPilotResult(null);
      setAssessmentMode("full");
    }
  }

  function openStoredReport(structure: AnalyzedStructure) {
    if (!structure.reportPath) return;
    const url = structure.id === santantonioAudit.id
      ? santantonioReportUrl
      : structure.id === perlaAudit.id
        ? perlaReportUrl
      : structure.id === braAudit.id
        ? braReportUrl
      : `${import.meta.env.BASE_URL}${structure.reportPath}`;
    window.open(url, "_blank", "noopener,noreferrer");
  }

  function restoreOriginalAudit() {
    if (!window.confirm("Ripristinare i 50 riscontri originali del Sant'Antonio? Le modifiche locali a questa scheda saranno sostituite.")) return;
    const original = santantonioStructure();
    setStructures((previous) => previous.map((item) => item.id === original.id ? original : item));
    if (activeStructureId === original.id) {
      setOwnerInfo(original.ownerInfo);
      setAnswers(original.answers);
      setRateQuotes([]);
      setAvailabilityProbes([]);
      setAssessmentMode(original.assessmentMode);
    }
  }

  function updateAnswer(itemId: string, patch: Partial<Answer>) {
    setAnswers((prev) => ({
      ...prev,
      [itemId]: { ...(prev[itemId] ?? emptyAnswer()), ...patch },
    }));
  }

  function addRateQuote() {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(rateDraft.stayDate) || rateDraft.stayDate < todayLocalIso() || !Number.isFinite(rateDraft.total) || rateDraft.total <= 0 || rateDraft.nights < 1 || rateDraft.guests < 1 || !rateDraft.roomType.trim() || !/^https?:\/\//i.test(rateDraft.sourceUrl.trim()) || (Number(rateDraft.originalTotal) > 0 && Number(rateDraft.originalTotal) <= rateDraft.total)) {
      window.alert("Inserisci una data futura, prezzo positivo, camera, ospiti e URL. Se indichi un prezzo barrato, deve superare quello finale.");
      return;
    }
    const quote: RateQuote = { ...rateDraft, id: globalThis.crypto?.randomUUID?.() ?? `rate-${Date.now()}`, observedAt: new Date().toISOString(), roomType: rateDraft.roomType.trim(), sourceUrl: rateDraft.sourceUrl.trim(), origin: "manual" };
    setRateQuotes((previous) => [...previous, quote]);
    setSelectedRateCohort(rateCohortKey(quote));
    setRateDraft((previous) => ({ ...previous, stayDate: "", total: 0, originalTotal: 0, promotion: "", eventTag: "", sourceUrl: "" }));
  }

  function addAvailabilityProbe() {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(availabilityDraft.stayDate) || availabilityDraft.stayDate < todayLocalIso() || !availabilityDraft.roomType.trim() || availabilityDraft.guests < 1 || !/^https?:\/\//i.test(availabilityDraft.sourceUrl.trim())) {
      window.alert("Per registrare la verifica servono una data futura, camera, ospiti e URL della ricerca.");
      return;
    }
    const probe = { ...availabilityDraft, id: globalThis.crypto?.randomUUID?.() ?? `availability-${Date.now()}`, observedAt: new Date().toISOString(), roomType: availabilityDraft.roomType.trim(), sourceUrl: availabilityDraft.sourceUrl.trim() };
    setAvailabilityProbes((previous) => [...previous, probe]);
    setAvailabilityDraft((previous) => ({ ...previous, stayDate: "", sourceUrl: "", note: "" }));
  }

  function removeAvailabilityProbe(id: string) {
    if (!window.confirm("Eliminare questa verifica dal browser?")) return;
    setAvailabilityProbes((previous) => previous.filter((probe) => probe.id !== id));
  }

  function removeRateQuote(id: string) {
    if (!window.confirm("Eliminare questa rilevazione tariffaria dalla scheda locale?")) return;
    setRateQuotes((previous) => previous.filter((quote) => quote.id !== id));
  }

  function updateAuditStatus(itemId: string, status: Exclude<AuditStatus, "">) {
    const currentAnswer = answers[itemId] ?? emptyAnswer();

    if (currentAnswer.auditStatus === status) {
      updateAnswer(itemId, {
        auditStatus: "",
        importance: 0,
        current: 0,
        fit: 0,
      });
      return;
    }

    const option = AUDIT_STATUS_OPTIONS.find((entry) => entry.value === status);
    const isNotApplicable = status === "not-applicable" || status === "unverified";

    updateAnswer(itemId, {
      auditStatus: status,
      importance: isNotApplicable ? 0 : 3,
      current: option?.current ?? 0,
      fit: isNotApplicable ? 0 : 3,
    });
  }

  function switchAssessmentMode(mode: AssessmentMode) {
    const nextData =
      mode === "web-audit"
        ? EXTERNAL_WEB_AUDIT_DATA
        : mode === "quick-hotel-bb"
        ? useCustomQuickSelection
          ? customQuickData
          : QUICK_HOTEL_BB_CORE_DATA
        : ASSESSMENT_DATA;
    setAssessmentMode(mode);
    setShowQuickDeepDive(false);
    setActiveMacroId(nextData[0]?.id ?? "");
    setShowOnlyPriority(false);
    setSearchTerm("");
    setAuditSourceFilter("Tutte le fonti");
  }

  function openInterviewCustomizer() {
    setCustomQuickDraftIds(
      useCustomQuickSelection ? customQuickItemIds : DEFAULT_CUSTOM_QUICK_ITEM_IDS
    );
    setCustomizerSearch("");
    setIsCustomizingInterview(true);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function toggleCustomQuestion(itemId: string) {
    setCustomQuickDraftIds((current) =>
      current.includes(itemId)
        ? current.filter((id) => id !== itemId)
        : [...current, itemId]
    );
  }

  function toggleCustomMacro(macro: AssessmentMacro) {
    const macroIds = flattenItems([macro]).map((row) => row.item.id);
    const allSelected = macroIds.every((id) => customQuickDraftIds.includes(id));

    setCustomQuickDraftIds((current) => {
      if (allSelected) {
        return current.filter((id) => !macroIds.includes(id));
      }

      return Array.from(new Set([...current, ...macroIds]));
    });
  }

  function confirmCustomInterview() {
    if (!customQuickDraftIds.length) {
      window.alert("Seleziona almeno una voce per creare l’intervista consulenziale.");
      return;
    }

    const selectedData = selectAssessmentItems(new Set(customQuickDraftIds));
    setCustomQuickItemIds(customQuickDraftIds);
    setUseCustomQuickSelection(true);
    setAssessmentMode("quick-hotel-bb");
    setShowQuickDeepDive(false);
    setActiveMacroId(selectedData[0]?.id ?? "");
    setShowOnlyPriority(false);
    setSearchTerm("");
    setIsCustomizingInterview(false);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function restorePresetQuickInterview() {
    setUseCustomQuickSelection(false);
    setAssessmentMode("quick-hotel-bb");
    setShowQuickDeepDive(false);
    setActiveMacroId(QUICK_HOTEL_BB_CORE_DATA[0]?.id ?? "");
    setShowOnlyPriority(false);
    setSearchTerm("");
  }


  function saveDiagnosis(showMessage = true) {
    const payload = {
      ownerInfo,
      answers,
      rateQuotes,
      availabilityProbes,
      assessmentMode,
      customQuickItemIds,
      useCustomQuickSelection,
      savedAt: new Date().toISOString(),
      globalScore,
      progressPct,
      answeredCount,
    };

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));

    if (showMessage) {
      window.alert("Diagnosi autovalutazione salvata correttamente.");
    }
  }

  function goToPath(path: string) {
    saveDiagnosis(false);
    window.alert(`Versione standalone: dati salvati localmente. In Velora Cloud questa azione aprirebbe: ${path}`);
  }

  function saveAndGoToSetup() {
    saveDiagnosis(false);
    goToPath("/setup");
  }

  function saveAndGoToPricing() {
    saveDiagnosis(false);
    goToPath("/pricing");
  }

  function resetAssessment() {
    const confirmed = window.confirm("Vuoi azzerare l’autovalutazione corrente?");
    if (!confirmed) return;

    setAnswers({});
    setRateQuotes([]);
    setAvailabilityProbes([]);
    window.localStorage.removeItem(STORAGE_KEY);
  }

  function exportJson() {
    const payload = {
      generatedAt: new Date().toISOString(),
      assessmentMode,
      assessmentFormat: isWebAudit
        ? "Audit Web & Frontend"
        : isQuickHotelBb
        ? useCustomQuickSelection
          ? "Intervista consulenziale personalizzata"
          : "Analisi rapida Hotel / B&B"
        : "Analisi completa",
      customQuickItemIds: useCustomQuickSelection ? customQuickItemIds : [],
      ownerInfo,
      globalScore,
      macroScores,
      topOpportunities: topOpportunities.map((row) => ({
        macro: row.macro.title,
        category: row.category.title,
        item: row.item.text,
        score: row.score,
        answer: row.answer,
      })),
      answers,
      rateQuotes,
      availabilityProbes,
    };

    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `velora-autovalutazione-${sanitizeFilename(ownerInfo.propertyName)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportCsv() {
    if (isWebAudit) {
      const header = [
        "Macro-area",
        "Categoria",
        "Voce verificabile",
        "Dove verificare",
        "Esito",
        "Indice criticità",
        "Evidenza / URL / nota",
      ];

      const rows = allRows.map((row) => {
        const answer = answers[row.item.id] ?? emptyAnswer();

        return [
          row.macro.title,
          row.category.title,
          row.item.text,
          getExternalAuditSources(row.item.id).join(", "),
          getAuditStatusLabel(answer.auditStatus),
          String(getItemScore(answer)),
          answer.note,
        ];
      });

      const csv = [header, ...rows]
        .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(";"))
        .join("\n");
      const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `velora-audit-web-${sanitizeFilename(ownerInfo.propertyName)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      return;
    }

    const header = [
      "Macro-area",
      "Categoria",
      "Voce",
      "Importanza",
      "Stato attuale",
      "Fit Velora",
      "Punteggio",
      "Note",
    ];

    const rows = allRows.map((row) => {
      const answer = answers[row.item.id] ?? emptyAnswer();

      return [
        row.macro.title,
        row.category.title,
        row.item.text,
        String(answer.importance),
        String(answer.current),
        String(answer.fit),
        String(getItemScore(answer)),
        answer.note,
      ];
    });

    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(";"))
      .join("\n");

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `velora-autovalutazione-${sanitizeFilename(ownerInfo.propertyName)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function exportQuickTemplateCsv() {
    const header = [
      "Livello",
      "Macro-area",
      "Categoria",
      "Domanda",
      "Importanza (0-3)",
      "Stato attuale (0-3)",
      "Fit Velora (0-3)",
      "Note / evidenze",
    ];

    const buildRows = (data: AssessmentMacro[], level: string) =>
      flattenItems(data).map((row) => [
        level,
        row.macro.title,
        row.category.title,
        row.item.text,
        "",
        "",
        "",
        "",
      ]);

    const rows = useCustomQuickSelection
      ? buildRows(
          quickTemplateData,
          `Intervista personalizzata - ${flattenItems(quickTemplateData).length} domande`
        )
      : [
          ...buildRows(QUICK_HOTEL_BB_CORE_DATA, "Principale - 30 domande"),
          ...buildRows(QUICK_HOTEL_BB_DEEP_DIVE_DATA, "Approfondimento - 20 domande"),
        ];

    const csv = [header, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(";"))
      .join("\n");

    const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = useCustomQuickSelection
      ? "velora-intervista-consulenziale-personalizzata.csv"
      : "velora-modello-analisi-rapida-hotel-bb.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function savePdfHtml(
    html: string,
    suggestedName: string,
    successMessage: string,
    frameId: string
  ) {
    if (window.veloraDesktop?.savePdf) {
      try {
        const result = await window.veloraDesktop.savePdf(html, suggestedName);

        if (result.canceled) return;

        if (!result.ok) {
          window.alert(result.error || "Errore durante la generazione del PDF.");
          return;
        }

        window.alert(successMessage);
      } catch (error) {
        console.error(error);
        window.alert("Errore durante la generazione del PDF nel programma desktop.");
      }

      return;
    }

    const existingFrame = document.getElementById(frameId);
    if (existingFrame) existingFrame.remove();

    const frame = document.createElement("iframe");
    frame.id = frameId;
    frame.title = "Documento PDF Velora";
    frame.style.position = "fixed";
    frame.style.right = "0";
    frame.style.bottom = "0";
    frame.style.width = "1px";
    frame.style.height = "1px";
    frame.style.border = "0";
    frame.style.opacity = "0";
    frame.setAttribute("aria-hidden", "true");

    document.body.appendChild(frame);

    const frameDocument = frame.contentDocument || frame.contentWindow?.document;

    if (!frameDocument || !frame.contentWindow) {
      window.alert("Impossibile generare il documento. Riprova dopo aver riaperto il modulo.");
      frame.remove();
      return;
    }

    frameDocument.open();
    frameDocument.write(html);
    frameDocument.close();

    setTimeout(() => {
      try {
        frame.contentWindow?.focus();
        frame.contentWindow?.print();
      } catch (error) {
        console.error(error);
        window.alert("Errore durante l'apertura della finestra di stampa PDF.");
      } finally {
        setTimeout(() => frame.remove(), 1500);
      }
    }, 500);
  }

  async function generateQuickTemplatePdf() {
    const safe = (value: unknown) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

    const buildSectionsHtml = (
      data: AssessmentMacro[],
      levelTitle: string,
      startingNumber: number
    ) => {
      let questionNumber = startingNumber;
      const content = data
        .map((macro) => {
          const categoriesHtml = macro.categories
            .map((category) => {
              const rowsHtml = category.items
                .map((item) => {
                  questionNumber += 1;
                  return `
                    <tr>
                      <td class="number">${questionNumber}</td>
                      <td><strong>${safe(item.text)}</strong></td>
                      <td class="answer"></td>
                      <td class="answer"></td>
                      <td class="answer"></td>
                      <td class="notes"></td>
                    </tr>
                  `;
                })
                .join("");

              return `
                <h3>${safe(category.title)}</h3>
                <table>
                  <thead>
                    <tr>
                      <th class="number">#</th>
                      <th>Domanda / elemento da valutare</th>
                      <th>Importanza<br />0-3</th>
                      <th>Stato<br />0-3</th>
                      <th>Fit Velora<br />0-3</th>
                      <th>Note / evidenze</th>
                    </tr>
                  </thead>
                  <tbody>${rowsHtml}</tbody>
                </table>
              `;
            })
            .join("");

          return `
            <section>
              <h2>${safe(macro.title)}</h2>
              ${categoriesHtml}
            </section>
          `;
        })
        .join("");

      return `<div class="level-heading">${safe(levelTitle)}</div>${content}`;
    };

    const selectedQuestionCount = flattenItems(quickTemplateData).length;
    const sectionsHtml = useCustomQuickSelection
      ? buildSectionsHtml(
          quickTemplateData,
          `Intervista personalizzata · ${selectedQuestionCount} domande selezionate`,
          0
        )
      : [
          buildSectionsHtml(QUICK_HOTEL_BB_CORE_DATA, "Parte 1 · 30 domande principali", 0),
          buildSectionsHtml(
            QUICK_HOTEL_BB_DEEP_DIVE_DATA,
            "Parte 2 · 20 domande di approfondimento",
            30
          ),
        ].join("");

    const html = `
      <!doctype html>
      <html lang="it">
        <head>
          <meta charset="utf-8" />
          <title>${useCustomQuickSelection ? "Intervista consulenziale personalizzata" : "Modello Analisi rapida Hotel e B&amp;B"}</title>
          <style>
            @page { size: A4; margin: 13mm; }
            * { box-sizing: border-box; }
            body { margin: 0; color: #1f2937; font-family: Arial, Helvetica, sans-serif; font-size: 10px; line-height: 1.35; }
            header { border-bottom: 4px solid #C8A96B; padding-bottom: 14px; margin-bottom: 16px; }
            .eyebrow { color: #C8A96B; font-size: 10px; font-weight: 800; letter-spacing: .2em; text-transform: uppercase; }
            h1 { color: #23124A; font-size: 25px; margin: 6px 0; }
            .subtitle { color: #475569; font-size: 11px; margin: 0; }
            .identity { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 10px; margin: 14px 0; }
            .identity div { border-bottom: 1px solid #94a3b8; min-height: 28px; padding-top: 12px; color: #64748b; }
            .instructions { border-left: 4px solid #C8A96B; background: #f8fafc; border-radius: 8px; padding: 10px 12px; margin-bottom: 16px; }
            .level-heading { color: #23124A; background: #fbf7ed; border: 1px solid #C8A96B; border-radius: 10px; padding: 10px 12px; margin: 18px 0 10px; font-size: 13px; font-weight: 800; break-after: avoid; }
            section { break-inside: auto; }
            h2 { color: #23124A; font-size: 15px; margin: 18px 0 7px; border-bottom: 1px solid #ded7e8; padding-bottom: 5px; }
            h3 { color: #475569; font-size: 11px; margin: 10px 0 4px; }
            table { width: 100%; border-collapse: collapse; table-layout: fixed; margin-bottom: 8px; }
            thead { display: table-header-group; }
            tr { break-inside: avoid; }
            th { background: #23124A; color: white; padding: 5px; font-size: 8px; text-transform: uppercase; }
            td { border: 1px solid #cbd5e1; padding: 6px; height: 31px; vertical-align: top; }
            .number { width: 6%; text-align: center; }
            .answer { width: 10%; text-align: center; }
            .notes { width: 25%; }
            footer { margin-top: 18px; border-top: 1px solid #e2e8f0; padding-top: 8px; color: #64748b; font-size: 8px; }
          </style>
        </head>
        <body>
          <header>
            <div class="eyebrow">Velora Consulting · Modello compilabile</div>
            <h1>${useCustomQuickSelection ? "Intervista consulenziale personalizzata" : "Analisi rapida Hotel / B&amp;B"}</h1>
            <p class="subtitle">${useCustomQuickSelection ? `${selectedQuestionCount} domande scelte dal consulente per questa specifica struttura.` : "30 domande principali e 20 opzionali per una diagnosi di posizionamento, vendita, revenue, gestione delegata e qualità del servizio."}</p>
          </header>

          <div class="identity">
            <div>Struttura</div>
            <div>Referente</div>
            <div>Data</div>
          </div>

          <div class="instructions">
            <strong>Scala di compilazione:</strong>
            Importanza 0-3 (da non rilevante a critica) · Stato attuale 0-3 (da non gestito a ben presidiato) · Fit Velora 0-3 (da non rilevante ad alto).
          </div>

          ${sectionsHtml}

          <footer>Modello generato da Velora RMS · ${useCustomQuickSelection ? `Intervista consulenziale personalizzata · ${selectedQuestionCount} domande.` : "Analisi rapida Hotel / B&amp;B · 30 domande principali + 20 di approfondimento."}</footer>
        </body>
      </html>
    `;

    const date = new Date().toISOString().slice(0, 10);
    await savePdfHtml(
      html,
      useCustomQuickSelection
        ? `velora-intervista-consulenziale-personalizzata-${date}.pdf`
        : `velora-modello-analisi-rapida-hotel-bb-${date}.pdf`,
      useCustomQuickSelection
        ? "Intervista personalizzata PDF salvata correttamente."
        : "Modello rapido PDF salvato correttamente.",
      "velora-quick-template-frame"
    );
  }

  async function generatePrintableReport() {
    const generatedAt = new Date();
    const generatedDate = generatedAt.toLocaleDateString("it-IT");
    const generatedTime = generatedAt.toLocaleTimeString("it-IT", {
      hour: "2-digit",
      minute: "2-digit",
    });

    const safe = (value: unknown) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

    const completedRows = allRows.filter((row) => {
      const answer = answers[row.item.id];
      return (
        answer &&
        (answer.importance > 0 ||
          answer.current > 0 ||
          answer.fit > 0 ||
          answer.note.trim())
      );
    });

    const scoredRows = completedRows.map((row) => {
      const answer = answers[row.item.id] ?? emptyAnswer();
      return { ...row, answer, score: getItemScore(answer) };
    });
    const reportScore = scoreAverage(scoredRows.map((row) => row.score));

    const sortedOpportunities = [...scoredRows]
      .filter((row) => row.score > 0)
      .sort((a, b) => b.score - a.score);
    const priorityRows = sortedOpportunities.slice(0, 5);

    const distribution = scoredRows.reduce(
      (counts, row) => {
        if (row.score >= 70) counts.critical += 1;
        else if (row.score >= 40) counts.attention += 1;
        else counts.controlled += 1;
        return counts;
      },
      { critical: 0, attention: 0, controlled: 0 }
    );

    const distributionTotal = scoredRows.length;
    const percentage = (value: number) =>
      distributionTotal ? Math.round((value / distributionTotal) * 100) : 0;
    const criticalPct = percentage(distribution.critical);
    const attentionPct = percentage(distribution.attention);
    const controlledPct = Math.max(0, 100 - criticalPct - attentionPct);
    const criticalEnd = criticalPct;
    const attentionEnd = criticalPct + attentionPct;

    const topAreas = macroScores
      .filter((macro) => macro.answeredItems > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 3);
    const topAreaText = topAreas.length
      ? topAreas.map((macro) => `${macro.title} (${macro.score}/100)`).join(", ")
      : "nessuna macro-area ancora sufficientemente compilata";

    const coverageText = progressPct >= 80
      ? "La copertura delle risposte è ampia e consente una lettura attendibile del quadro complessivo."
      : progressPct >= 50
        ? "La copertura è sufficiente per una prima diagnosi, ma le conclusioni andranno consolidate completando le voci mancanti."
        : "La compilazione è ancora parziale: le evidenze sono utili per orientare il confronto, non ancora per una diagnosi definitiva.";

    const collaborationText = reportScore >= 70
      ? "L’indice evidenzia un potenziale di collaborazione ampio: è opportuno costruire un piano coordinato, con responsabilità, KPI e verifiche periodiche."
      : reportScore >= 40
        ? "Il potenziale di collaborazione è selettivo: conviene concentrare l’intervento sulle aree ad alto impatto, evitando un progetto troppo esteso nella prima fase."
        : sortedOpportunities.length
          ? "L’indice complessivo è contenuto, ma non equivale a assenza di utilità. Le criticità puntuali emerse giustificano una collaborazione mirata, circoscritta ai presidi con maggiore gap e migliore coerenza d’intervento."
          : "L’indice complessivo è contenuto e non emergono ancora gap quantificabili. Prima di escludere una collaborazione è consigliabile completare le valutazioni e verificare le aree più sensibili con evidenze operative.";

    function recommendedAction(row: (typeof scoredRows)[number]) {
      const context = `${row.macro.title} ${row.category.title} ${row.item.text}`.toLowerCase();
      if (/revenue|pricing|tariff|adr|revpar|forecast|pickup|stagional/.test(context)) {
        return "Impostare una regola di pricing misurabile, un calendario di revisione e KPI revenue condivisi.";
      }
      if (/brand|posizion|sito|direct|conversion|marketing|target|promessa/.test(context)) {
        return "Chiarire posizionamento e proposta di valore, quindi tradurli in contenuti e percorso di prenotazione diretta.";
      }
      if (/prenot|channel|ota|booking|calendario|disponibil/.test(context)) {
        return "Mappare il flusso prenotativo, eliminare i passaggi manuali critici e definire controlli su disponibilità e canali.";
      }
      if (/propriet|direzione|report|accord|commercial|responsabil|customer service/.test(context)) {
        return "Formalizzare responsabilità, SLA, frequenza dei report e criteri di escalation verso proprietà e direzione.";
      }
      if (/foto|qualità|qualita|pulizi|ispezion|standard|servizi/.test(context)) {
        return "Definire standard verificabili, checklist, responsabilità e una cadenza di controllo della qualità erogata.";
      }
      if (/crm|centralino|lead|risposta/.test(context)) {
        return "Centralizzare contatti e richieste, assegnare tempi di risposta e monitorare conversione e richieste perse.";
      }
      return "Definire uno standard minimo, un responsabile, una scadenza e un indicatore con cui verificare il miglioramento.";
    }

    const averageMetric = (metric: keyof Answer) => {
      if (!scoredRows.length) return "0,0";
      const total = scoredRows.reduce((sum, row) => {
        const value = row.answer[metric];
        return sum + (typeof value === "number" ? value : 0);
      }, 0);
      return (total / scoredRows.length).toLocaleString("it-IT", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      });
    };

    const strengths = scoredRows
      .filter((row) => row.answer.current >= 2 && row.answer.importance >= 2)
      .sort((a, b) => b.answer.current - a.answer.current || b.answer.importance - a.answer.importance)
      .slice(0, 5);
    const highFitGaps = scoredRows
      .filter((row) => row.answer.fit >= 2 && row.answer.current <= 1)
      .sort((a, b) => b.score - a.score)
      .slice(0, 5);

    const rowsForContext = (pattern: RegExp) => sortedOpportunities
      .filter((row) => pattern.test(`${row.macro.title} ${row.category.title} ${row.item.text}`.toLowerCase()))
      .slice(0, 4);
    const commercialGaps = rowsForContext(/marketing|brand|posizion|sito|direct|ota|revenue|pricing|tariff|adr|revpar|forecast|pickup/);
    const governanceGaps = rowsForContext(/propriet|direzione|report|accord|responsabil|qualità|qualita|standard|customer service/);

    const namesOf = (rows: typeof scoredRows, fallback: string) =>
      rows.length ? rows.map((row) => row.item.text).join(", ") : fallback;

    const strengthText = strengths.length
      ? `I presidi relativamente più solidi sono ${namesOf(strengths, "")}. Vanno mantenuti e trasformati in standard documentati, così da non dipendere da singole persone.`
      : "Non emergono ancora presidi sufficientemente consolidati. La prima attività dovrebbe essere la definizione di standard minimi e responsabilità chiare.";
    const gapText = highFitGaps.length
      ? `Le aree dove il supporto esterno può produrre il miglior rapporto tra sforzo e risultato sono ${namesOf(highFitGaps, "")}. Qui il gap operativo è alto e la coerenza con un intervento Velora è concreta.`
      : "Non emergono gap ad alta coerenza sufficientemente netti; conviene validare i dati con un breve approfondimento operativo.";
    const commercialText = commercialGaps.length
      ? `Sul piano economico-commerciale richiedono attenzione ${namesOf(commercialGaps, "")}. Il rischio è perdere margine, domanda diretta o capacità di reagire alla stagionalità.`
      : "Il perimetro economico-commerciale appare relativamente presidiato oppure non ancora valutato in modo sufficiente.";
    const governanceText = governanceGaps.length
      ? `Sul piano di governance e qualità emergono ${namesOf(governanceGaps, "")}. È consigliabile collegare ogni attività a un responsabile, una frequenza di controllo e un KPI.`
      : "Non emergono criticità marcate di governance e qualità; resta utile formalizzare responsabilità e indicatori per proteggere la continuità del servizio.";

    const planStages = [
      {
        horizon: "0-30 giorni",
        title: "Priorità e responsabilità",
        rows: priorityRows.slice(0, 2),
        fallback: "Completare le valutazioni mancanti e validare i dati con proprietà e direzione.",
      },
      {
        horizon: "31-60 giorni",
        title: "Implementazione dei presidi",
        rows: priorityRows.slice(2, 4),
        fallback: "Formalizzare procedure, SLA e strumenti di controllo sulle aree selezionate.",
      },
      {
        horizon: "61-90 giorni",
        title: "Misurazione e consolidamento",
        rows: priorityRows.slice(4, 5),
        fallback: "Misurare risultati, correggere le deviazioni e consolidare gli standard efficaci.",
      },
    ];

    const planHtml = planStages.map((stage) => `
      <article class="plan-card">
        <div class="plan-horizon">${stage.horizon}</div>
        <h3>${stage.title}</h3>
        ${stage.rows.length
          ? `<ul>${stage.rows.map((row) => `<li><b>${safe(row.item.text)}:</b> ${safe(recommendedAction(row))}</li>`).join("")}</ul>`
          : `<p>${stage.fallback}</p>`}
      </article>
    `).join("");

    const valueRowsHtml = scoredRows.length
      ? scoredRows
          .map((row) => {
            const label = getScoreLabel(row.score);
            return `
              <tr>
                <td>
                  <strong>${safe(row.item.text)}</strong>
                  <small>${safe(row.macro.title)} · ${safe(row.category.title)}</small>
                </td>
                <td class="center compact-values">${row.answer.importance}</td>
                <td class="center compact-values">${row.answer.current}</td>
                <td class="center compact-values">${row.answer.fit}</td>
                <td class="center score-cell">${row.score}</td>
                <td><span class="status status-${row.score >= 70 ? "critical" : row.score >= 40 ? "attention" : "controlled"}">${safe(label.shortLabel)}</span></td>
                <td>${safe(row.answer.note || "-")}</td>
              </tr>
            `;
          })
          .join("") + `
            <tr class="total-row">
              <td>Media complessiva</td>
              <td class="center">${averageMetric("importance")}</td>
              <td class="center">${averageMetric("current")}</td>
              <td class="center">${averageMetric("fit")}</td>
              <td class="center">${reportScore}</td>
              <td colspan="2">${distribution.critical} critiche · ${distribution.attention} medie · ${distribution.controlled} basse</td>
            </tr>
          `
      : `<tr><td colspan="7" class="empty">Nessuna voce compilata.</td></tr>`;

    const priorityHtml = priorityRows.length
      ? priorityRows
          .map((row, index) => `
            <article class="priority-card">
              <div class="priority-number">${index + 1}</div>
              <div>
                <div class="priority-heading">
                  <strong>${safe(row.item.text)}</strong>
                  <span>${row.score}/100</span>
                </div>
                <small>${safe(row.macro.title)} · ${safe(row.category.title)}</small>
                <p><b>Perché intervenire:</b> importanza ${row.answer.importance}/3, presidio attuale ${row.answer.current}/3, coerenza Velora ${row.answer.fit}/3.${row.answer.note ? ` Evidenza rilevata: ${safe(row.answer.note)}.` : ""}</p>
                <p><b>Prima azione:</b> ${safe(recommendedAction(row))}</p>
              </div>
            </article>
          `)
          .join("")
      : `<div class="empty-box">Non sono ancora disponibili priorità operative. Completare almeno le voci principali per ottenere una lettura consulenziale.</div>`;

    const reportCohorts = [...new Map(rateQuotes.map((quote) => [rateCohortKey(quote), rateCohortLabel(quote)])).entries()];
    const reportCohort = selectedRateCohort && reportCohorts.some(([key]) => key === selectedRateCohort) ? selectedRateCohort : reportCohorts[0]?.[0] ?? "";
    const reportQuotes = reportCohort ? latestRateQuotes(rateQuotes, reportCohort) : [];
    const reportToday = new Date();
    const reportMonths = futureMonthKeys(reportToday);
    const reportChannels = activeAuditData.otaPresence;
    const monthlyTable = (channels: typeof reportChannels) => `<table><thead><tr><th>Mese</th>${channels.map((channel) => `<th>${safe(channel.platform)}</th>`).join("")}</tr></thead><tbody>${reportMonths.map((month) => `<tr><td><b>${safe(new Date(`${month}-01T12:00:00Z`).toLocaleDateString("it-IT", { month: "short", year: "numeric", timeZone: "UTC" }))}</b></td>${channels.map((channel) => { const cell = monthlyRateCell(rateQuotes, month, channel.id); return `<td>${cell.average === null ? "n.d." : `<b>€ ${cell.average.toFixed(2)}</b><small>${cell.count} rilevazione/i · ${cell.verified} validate${cell.deltaPct === null ? " · Δ n.d." : ` · Δ ${cell.deltaPct > 0 ? "+" : ""}${cell.deltaPct.toFixed(1)}% (${cell.matched})`}</small>`}</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;
    const seededSamples = "monthlySamples" in activeAuditData.pricingAudit
      ? activeAuditData.pricingAudit.monthlySamples : [];
    const seededComparisons = "comparisonSamples" in activeAuditData.pricingAudit
      ? activeAuditData.pricingAudit.comparisonSamples : [];
    const manualComparisons = buildRateComparisonRows(rateQuotes, todayLocalIso());
    const otaDistributionAsymmetries = pilotDistributionAsymmetries(browserPilotResult);
    const otaDistributionHtml = otaDistributionAsymmetries.length ?
      "<h2>Asimmetrie distributive tra OTA</h2>" +
      "<p>Confronto effettuato sulle stesse date e soltanto su tipologie/unità con tariffa frontend validata. Le differenze sono fatti osservati; le possibili cause tecniche vanno verificate prima di attribuirle a channel manager o PMS.</p>" +
      "<table><thead><tr><th>Date</th><th>OTA</th><th>Tipologie visibili</th><th>Riferimento massimo</th><th>Riscontro / opportunità</th></tr></thead><tbody>" +
      otaDistributionAsymmetries.map((item)=>
        "<tr><td>"+safe(item.checkin)+" → "+safe(item.checkout)+"</td><td><b>"+safe(item.otaLabel)+"</b></td><td>"+String(item.unitCount)+
        (item.units.length ? "<small>"+safe(item.units.join(" · "))+"</small>" : "")+"</td><td>"+String(item.maxUnitCount)+
        "<small>"+safe(item.referenceChannels.join(", "))+"</small></td><td>"+safe(item.finding)+"</td></tr>"
      ).join("") + "</tbody></table>" : "";
    const numericPricingRows = [
      ...seededComparisons.map((sample) => `<tr><td>${safe(sample.stay)}</td><td><b>${safe(reportChannels.find((channel) => channel.id === sample.otaId)?.platform || (sample.otaId === "sito" ? "Sito diretto" : sample.otaId))}</b></td><td>${safe(sample.roomType)}</td><td class="center"><b>€ ${sample.nightly.toFixed(2)}</b></td><td class="center">—</td><td class="center">${safe(sample.delta)}</td><td>${safe(sample.conditions)}</td></tr>`),
      ...manualComparisons.map(({ quote, nightly, bookingNightly, deltaPct }) => `<tr><td>${safe(quote.stayDate)}</td><td><b>${safe(reportChannels.find((channel) => channel.id === quote.otaId)?.platform || quote.otaId)}</b></td><td>${safe(quote.roomType)}${quote.unitId ? `<small>Unità verificata: ${safe(quote.unitId)}</small>` : "<small>Unità non verificata</small>"}</td><td class="center"><b>€ ${nightly.toFixed(2)}</b></td><td class="center">${bookingNightly === null ? "—" : `€ ${bookingNightly.toFixed(2)}`}</td><td class="center">${deltaPct === null ? "n.d." : quote.otaId === "booking" ? "Base" : `${deltaPct > 0 ? "+" : ""}${deltaPct.toFixed(1)}%`}</td><td>${safe(`${quote.ratePlan ? quote.ratePlan + "; " : ""}${quote.refund}; ${quote.board}; ${quote.audience}; ${quote.taxes}`)}</td></tr>`),
    ];
    const numericPricingHtml = otaDistributionHtml + `<h2>Tariffe puntuali e delta tra OTA</h2><p>Prezzi finali osservati per notte (totale / notti), non ADR realizzato. Δ = (altra OTA / Booking − 1) × 100. Il confronto richiede stessa unità fisica verificata, date, durata, ospiti, trattamento, cancellazione, pubblico, imposte e giorno di rilevazione. “n.d.” significa non confrontabile, non prezzo zero.</p><table><thead><tr><th>Data</th><th>Canale</th><th>Tipologia</th><th>€/notte</th><th>Booking base</th><th>Δ</th><th>Condizioni / limite</th></tr></thead><tbody>${numericPricingRows.join("") || `<tr><td colspan="7">Nessun preventivo datato registrato. La tabella descrittiva sotto resta disponibile.</td></tr>`}</tbody></table>`;
    const seededCell = (sample: { low?: number; high?: number; scope?: string; status?: string }) =>
      sample.low === undefined || sample.high === undefined ? safe(sample.status || "Non campionato")
        : `<b>€${sample.low.toFixed(2)}${sample.low === sample.high ? "" : `–€${sample.high.toFixed(2)}`}/notte</b><small>${safe(sample.scope || "")}</small>`;
    const seededPricingHtml = seededSamples.length ? `<h2>Range osservato per tipologia e mese</h2><p>Campioni pubblici con date e durata indicati in tabella. Gli estremi riguardano soltanto le tipologie e i piani effettivamente quotati; non sono ADR realizzato né media mensile. Una tariffa di calendario priva di preventivo confermato è soltanto indicativa.</p><table><thead><tr><th>Mese / date</th><th>Diretto</th><th>Booking</th><th>Altre OTA</th><th>Delta</th></tr></thead><tbody>${seededSamples.map((sample) => `<tr><td><b>${safe(sample.month)}</b><small>${safe(sample.stay)}</small></td><td>${seededCell(sample.direct)}</td><td>${seededCell(sample.booking)}</td><td>${safe(sample.other)}</td><td>${safe(sample.delta)}</td></tr>`).join("")}</tbody></table><p>Nessun delta numerico senza conferma della stessa unità fisica, date, cancellazione, trattamento, imposte e pubblico. L'assenza di un prezzo nel campione non prova la chiusura stagionale.</p>` : "";
    const manualPricingHtml = rateQuotes.length ? `<h2>Rilevazioni tariffarie registrate</h2><p><b>Non è ADR realizzato.</b> Comprende rilevazioni automatiche del browser pilot (validate oppure marcate da verificare) e inserimenti manuali; la tabella mostra la media dei preventivi per notte nel campione omogeneo. ${reportCohort ? `Condizioni confrontate: ${safe(reportCohorts.find(([key]) => key === reportCohort)?.[1] || "")}.` : "Nessuna quotazione omogenea inserita."} Il delta richiede anche un ID di unità fisica verificato e coincidente.</p>${monthlyTable(reportChannels.slice(0, 5))}${monthlyTable(reportChannels.slice(5))}<p>Una o poche date non rappresentano tutto il mese. I prezzi possono variare dopo la rilevazione.</p>` : "";
    const commercialReportHtml = isWebAudit ? `<section class="page-break"><h2>Politiche commerciali e tariffarie per OTA</h2><p>Rilevazione pubblica: i piani e gli sconti sono validi soltanto per date, camera e pubblico consultati. Una scheda presente non dimostra inventario vendibile su tutto il calendario. ${safe(activeAuditData.pricingAudit.method)}</p><table><thead><tr><th style="width:17%">Canale</th><th>Tariffe, promozioni e limiti del riscontro</th></tr></thead><tbody><tr><td><b>Sito diretto</b></td><td>${safe(answers["audit-policy-direct"]?.note || "Non verificato")}</td></tr>${reportChannels.map((channel) => `<tr><td><b>${safe(channel.platform)}</b></td><td>${safe(answers[`audit-policy-${channel.id}`]?.note || "Non verificato")}</td></tr>`).join("")}</tbody></table>${numericPricingHtml}${seededPricingHtml}${manualPricingHtml}</section>` : "";
    const reputation = browserPilotResult?.propertyId === activeAuditData.id ? browserPilotResult.reputation : undefined;
    const photoAudit = browserPilotResult?.propertyId === activeAuditData.id ? browserPilotResult.photoAudit : undefined;
    const reputationStrengthRows = (reputation?.strengths || []).map((entry) =>
      `<tr><td><b>${safe(entry.theme)}</b></td><td>${entry.count}</td><td>${safe((entry.phrases || []).slice(0, 3).join(" · ") || "—")}</td><td>${safe((entry.examples || []).slice(0, 2).join(" · ") || "Nessun esempio disponibile")}</td></tr>`
    ).join("");
    const reputationWeakRows = (reputation?.weaknesses || []).map((entry) =>
      `<tr><td><b>${safe(entry.theme)}</b></td><td>${entry.count}</td><td>${safe((entry.phrases || []).slice(0, 3).join(" · ") || "—")}</td><td>${safe((entry.examples || []).slice(0, 2).join(" · ") || "Nessun esempio disponibile")}</td><td>${safe(entry.action || "Approfondire il tema")}</td></tr>`
    ).join("");
    const reputationRecurringThemes = (reputation?.recurringThemes || []).map((entry) => {
      const phrases = (entry.phrases || []).slice(0, 3).join(" · ");
      return `${entry.theme} — ${entry.sentiment === "negativo" ? "negativo" : "positivo"} · ${entry.count} recensioni${phrases ? " · " + phrases : ""}`;
    }).join(" | ");
    const isolatedSignals = (reputation?.isolatedSignals || []).map((entry) => entry.theme + (entry.examples?.length ? ": " + entry.examples[0] : "")).join(" · ");
    const reputationReportHtml = isWebAudit ? `<section class="page-break"><h2>Reputazione online e qualità fotografica</h2>
      <p><b>Google:</b> ${reputation?.rating ? safe(String(reputation.rating) + "/5") : "rating non rilevato"}${reputation?.reviewCount ? " · " + safe(String(reputation.reviewCount)) + " recensioni visibili" : ""}. Campione qualitativo: ${safe(String(reputation?.sampleSize || 0))} recensioni. Le ricorrenze descrivono il campione pubblico analizzato, non l\'intero corpus.</p>
      ${reputationRecurringThemes ? `<p><b>Temi e aspetti ricorrenti:</b> ${safe(reputationRecurringThemes)}</p>` : ""}
      <h3>Punti di forza ricorrenti</h3>
      ${reputationStrengthRows ? `<table><thead><tr><th>Tema</th><th>Ricorrenze</th><th>Espressioni ricorrenti</th><th>Esempi dal campione</th></tr></thead><tbody>${reputationStrengthRows}</tbody></table>` : "<p>Nessun tema positivo ricorrente classificato automaticamente.</p>"}
      <h3>Criticità ricorrenti</h3>
      ${reputationWeakRows ? `<table><thead><tr><th>Tema</th><th>Ricorrenze</th><th>Espressioni ricorrenti</th><th>Esempi dal campione</th><th>Azione operativa</th></tr></thead><tbody>${reputationWeakRows}</tbody></table>` : "<p>Nessuna criticità ricorrente classificata automaticamente.</p>"}
      <h3>Segnalazioni isolate da monitorare</h3>
      <p>${safe(isolatedSignals || "Nessuna segnalazione isolata significativa nel campione.")}</p>
      <h3>Audit fotografico frontend</h3>
      <p><b>Indice tecnico/editoriale:</b> ${photoAudit?.score ? safe(String(photoAudit.score) + "/10") : "non rilevato"}${photoAudit?.imageCount !== undefined ? " · " + safe(String(photoAudit.imageCount)) + " immagini rilevanti" : ""}${photoAudit?.highResolutionCount !== undefined ? " · " + safe(String(photoAudit.highResolutionCount)) + " ad alta risoluzione" : ""}.</p>
      <p>${safe(photoAudit?.evidence || answers["audit-photo-score"]?.note || "Audit fotografico non ancora disponibile.")}</p>
      ${(photoAudit?.strengths || []).length ? `<p><b>Punti di forza fotografici:</b> ${safe((photoAudit?.strengths || []).join(" "))}</p>` : ""}
      ${(photoAudit?.gaps || []).length ? `<p><b>Gap fotografici:</b> ${safe((photoAudit?.gaps || []).join(" "))}</p>` : ""}
      ${(photoAudit?.actions || []).length ? `<p><b>Azioni consigliate:</b> ${safe((photoAudit?.actions || []).join(" "))}</p>` : ""}
    </section>` : "";
    const bookingStatus = answers["audit-booking-engine"]?.auditStatus || "unverified";
    const bookingProvider = answers["audit-booking-engine-provider"]?.note || browserPilotResult?.bookingEngine?.provider || "Fornitore non identificato";
    const bookingUrl = answers["audit-booking-engine-url"]?.note || browserPilotResult?.bookingEngine?.url || "URL non disponibile";
    const bookingMode = answers["audit-booking-engine-mode"]?.note || browserPilotResult?.bookingEngine?.mode || "Non verificato";
    const bookingEvidence = answers["audit-booking-engine-evidence"]?.note || browserPilotResult?.bookingEngine?.evidence || "Nessun riscontro registrato";
    const bookingStatusLabel = bookingStatus === "present" ? bookingProvider === "Fornitore non identificato" ? "Percorso di prenotazione rilevato; fornitore non confermato" : "Fornitore identificato" : bookingStatus === "partial" ? "Percorso di prenotazione rilevato; fornitore non confermato" : bookingStatus === "missing" ? "Percorso di prenotazione non rilevato nel campione" : "Non verificato";
    const bookingEngineReportHtml = isWebAudit ? `<section><h2>Booking engine e fornitore del canale diretto</h2><table><tbody><tr><th style="width:25%">Esito</th><td>${safe(bookingStatusLabel)}</td></tr><tr><th>Fornitore</th><td><b>${safe(bookingProvider)}</b></td></tr><tr><th>Percorso</th><td>${safe(bookingMode)}</td></tr><tr><th>URL di prova</th><td>${safe(bookingUrl)}</td></tr><tr><th>Riscontro</th><td>${safe(bookingEvidence)}</td></tr></tbody></table><p>Un dominio riconosciuto identifica il fornitore del percorso pubblico, ma non prova che disponibilità, pagamento e checkout funzionino. Un sito ospitato direttamente dal fornitore va registrato anche se non esiste un dominio ufficiale separato.</p></section>` : "";
    const pilotObservations = browserPilotResult?.propertyId === activeAuditData.id ? browserPilotResult.observations : [];
    const pilotStatusLabels: Record<string, string> = { source_missing: "Scheda non individuata", source_not_retested: "Scheda non ritestata nel test rapido", date_adapter_missing: "Date non applicabili automaticamente", robots_denied: "Accesso automatico non consentito", robots_unavailable: "Regole di accesso non verificabili", blocked: "Blocco o verifica del portale", rate_limited: "Portale temporaneamente limitato", empty_page: "Pagina non leggibile", dates_unconfirmed: "Date non confermate", dated_search_inconclusive: "Ricerca datata non conclusiva", no_public_rate: "Nessuna tariffa pubblica rilevata", needs_human_review: "Preventivo da verificare", not_verified_present: "Pagina OTA rilevata · identità da confermare", existing_unverified: "Pagina OTA nota · identità da riconfermare", quote_candidates: "Tariffe rilevate e strutturate", quote_candidates_unverified: "Prezzi rilevati, attribuzione da completare", http_error: "Errore HTTP", navigation_error: "Errore di navigazione", login_required: "Login richiesto · nessun prezzo usato" };
    const pilotChannelIds = [...new Set(pilotObservations.map((item) => item.otaId))];
    const pilotRows = pilotChannelIds.map((otaId) => {
      const entries = pilotObservations.filter((item) => item.otaId === otaId);
      const counts = [...new Set<string>(entries.map((item) => item.status))].map((status) => `${pilotStatusLabels[status] || status}: ${entries.filter((item) => item.status === status).length}`).join("; ");
      const example = entries.find((item) => item.evidence)?.evidence || "Nessuna prova specifica disponibile.";
      const platform = reportChannels.find((channel) => channel.id === otaId)?.platform || (otaId === "sito" ? "Sito diretto" : otaId);
      return `<tr><td><b>${safe(platform)}</b></td><td class="center">${entries.length}</td><td>${safe(counts)}</td><td>${safe(example)}</td></tr>`;
    });
    const pilotProfileEntries = browserPilotResult?.propertyId === activeAuditData.id
      ? Object.entries(browserPilotResult.otaProfiles || {})
      : [];
    const pilotProfileTableHtml = pilotProfileEntries.length
      ? `<h3>Profili OTA e metasearch</h3><p>Per i portali che non espongono una tariffa camera direttamente comparabile, Velora conserva comunque la scheda pubblica, le metriche reputazionali e gli eventuali link commerciali. I prezzi generici visibili non entrano nel delta.</p><table><thead><tr><th>Canale</th><th>Stato</th><th>Rating</th><th>Recensioni</th><th>Raccomandazione</th><th>Link commerciali / prova</th></tr></thead><tbody>${pilotProfileEntries.map(([otaId, profile]) => {
          const platform = reportChannels.find((channel) => channel.id === otaId)?.platform || otaId;
          const rating = Number.isFinite(profile.rating) && Number.isFinite(profile.ratingScale)
            ? Number(profile.rating).toFixed(1) + "/" + Number(profile.ratingScale).toFixed(0)
            : "n.d.";
          const recommendation = Number.isFinite(profile.recommendationRate)
            ? Number(profile.recommendationRate).toFixed(1) + "%"
            : "n.d.";
          const commercial = (profile.commercialHosts || []).slice(0, 8).join(", ");
          const visiblePrices = (profile.visiblePrices || []).slice(0, 8).map((item) => "€" + Number(item.amount).toFixed(2)).join(" · ");
          const profileProof = [profile.evidence || "", visiblePrices ? "Prezzi EUR visibili: " + visiblePrices + " (non attribuiti a camera/date)" : "", commercial ? "Link commerciali: " + commercial : ""].filter(Boolean).join(" · ");
          return `<tr><td><b>${safe(platform)}</b></td><td>${safe(profile.status)}</td><td>${safe(rating)}</td><td>${safe(profile.reviewCount ? String(profile.reviewCount) : "n.d.")}</td><td>${safe(recommendation)}</td><td>${safe(profileProof || "Nessun dettaglio aggiuntivo")}</td></tr>`;
        }).join("")}</tbody></table>`
      : "";
    const pilotQuoteRows = pilotObservations.flatMap((observation) =>
      (observation.quotes || [])
        .filter((quote) => quote.comparisonSelected !== false)
        .map((quote) => ({ observation, quote }))
    );
    const pilotQuoteTableHtml = pilotQuoteRows.length
      ? `<h3>Tariffe rilevate automaticamente</h3><p>Per ogni OTA Velora normalizza il dato in €/notte e totale soggiorno senza cambiare la durata richiesta. Il report distingue il valore realmente mostrato dal portale da quello calcolato matematicamente; questo evita errori con minimum stay e portali che mostrano solo il totale.</p><table><thead><tr><th>Canale</th><th>Date</th><th>Camera / piano</th><th>€/notte</th><th>Totale soggiorno</th><th>Condizioni</th><th>Stato</th></tr></thead><tbody>${pilotQuoteRows.slice(0,120).map(({ observation, quote }) => {
          const platform = reportChannels.find((channel) => channel.id === observation.otaId)?.platform || observation.otaId;
          const roomStatus = quote.roomMatchStatus === "booking-reference"
            ? "REFERENCE BOOKING"
            : quote.roomMatchStatus === "same-room"
              ? "STESSA CAMERA DELLA REFERENCE BOOKING"
              : quote.roomMatchStatus === "different-room-fallback"
                ? "ATTENZIONE: CAMERA DIVERSA DALLA REFERENCE BOOKING"
                : "";
          const conditions = [quote.ratePlan, quote.board, quote.refund, quote.taxes, quote.priceDerivation, quote.comparisonWarning].filter(Boolean).join(" · ");
          const roomAndPlan = [quote.roomType || "Da verificare", quote.ratePlan, roomStatus].filter(Boolean).join(" · ");
          const nightly = Number(quote.nightlyRate ?? (quote.total / Math.max(1, quote.nights)));
          const nightlyLabel = quote.displayedBasis === "nightly" ? "mostrato" : quote.displayedBasis === "stay-total" ? "calcolato dal totale" : "normalizzato";
          const totalLabel = quote.displayedBasis === "stay-total" ? "mostrato" : quote.displayedBasis === "nightly" ? "calcolato" : "registrato";
          return `<tr><td><b>${safe(platform)}</b></td><td>${safe(observation.checkin)} → ${safe(observation.checkout)}</td><td>${safe(roomAndPlan)}</td><td><b>€${nightly.toFixed(2)}</b><small>${safe(nightlyLabel)}</small></td><td><b>€${Number(quote.total).toFixed(2)}</b><small>${safe(totalLabel)} · ${quote.nights} notti</small></td><td>${safe(conditions)}</td><td>${quote.verified ? "Camera e prezzo validati dal parser" : "Prezzo rilevato · attribuzione da completare"}</td></tr>`;
        }).join("")}</tbody></table>`
      : "";
    const pilotReportHtml = isWebAudit && (pilotObservations.length || pilotProfileEntries.length) ? `<section class="page-break"><h2>Verifiche automatiche locali: esiti e limiti</h2><p>Prova eseguita il ${safe(browserPilotResult?.createdAt || "data non disponibile")}. ${pilotObservations.length} controlli su date future; ${new Set(pilotObservations.map((item) => item.month)).size} mesi campionati; ${pilotProfileEntries.length} profili OTA/metasearch analizzati. I prezzi rilevati automaticamente vengono conservati con data, canale e condizioni osservate; i delta restano esclusi finché le unità non sono comparabili con certezza.</p>${pilotObservations.length ? `<table><thead><tr><th>Canale</th><th>Mesi</th><th>Esiti</th><th>Motivo principale</th></tr></thead><tbody>${pilotRows.join("")}</tbody></table>` : ""}${pilotProfileTableHtml}${pilotQuoteTableHtml}<p>Il file JSON locale conserva date, URL, profili pubblici ed eventuali righe tariffarie di ogni controllo.</p></section>` : "";

    const coverageTable = (channels: typeof reportChannels) => '<table><thead><tr><th>Mese futuro</th>' + channels.map((channel) => '<th>' + safe(channel.platform) + '</th>').join('') + '</tr></thead><tbody>' + reportMonths.map((month) => '<tr><td><b>' + safe(new Date(month + '-01T12:00:00Z').toLocaleDateString('it-IT', { month: 'short', year: 'numeric', timeZone: 'UTC' })) + '</b></td>' + channels.map((channel) => {
      const status = monthlyCoverageSummary(reportQuotes, availabilityProbes, month, channel.id, browserPilotResult);
      return '<td>' + safe(status) + '</td>';
    }).join('') + '</tr>').join('') + '</tbody></table>';
    const futurePromotions = rateQuotes.filter((quote) => quote.stayDate >= todayLocalIso() && quote.promotionKind && !['Non verificata', 'Nessuna visibile'].includes(quote.promotionKind));
    const futureGaps = availabilityProbes.filter((probe) => probe.stayDate >= todayLocalIso() && probe.status !== 'blocked');
    const coverageReportHtml = isWebAudit ? '<section class="page-break"><h2>Copertura delle vendite future per OTA</h2><p>Periodo dalla data del report alla fine dell’anno successivo. Le celle non verificate NON significano vendite chiuse. Una data senza prezzo non prova da sola una chiusura: verificare camere esaurite, minimum stay, booking window, restrizioni e problemi del portale.</p>' + coverageTable(reportChannels.slice(0, 5)) + coverageTable(reportChannels.slice(5)) + '<p><b>Indicatore commerciale:</b> ' + (futureGaps.length ? 'Sono state registrate ' + futureGaps.length + ' date future con prezzo non mostrato o calendario non aperto. Controllare in extranet l’apertura delle vendite e la sincronizzazione prima di definire il periodo non commercializzato.' : 'Non sono ancora state documentate date future con prezzo assente o calendario non aperto. Servono prove per canale e data per valutare l’anticipo di vendita.') + '</p><h2>Promozioni osservate su tariffe future</h2><p>' + (futurePromotions.length ? futurePromotions.map((quote) => safe((reportChannels.find((channel) => channel.id === quote.otaId)?.platform || quote.otaId) + ' · ' + quote.stayDate + ' · ' + promotionSummary(quote))).join('<br/>') : 'Nessuno sconto specifico della struttura confermato su una tariffa futura nel campione registrato. Last minute, Genius, mobile e member restano da verificare per data e pubblico.') + '</p><p>Fonte, data, camera e condizioni di ogni prova sono conservate nella scheda locale ed esportabili in JSON. Una campagna generica del portale non equivale a sconto applicato a questa struttura.</p></section>' : '';

    const html = `
      <!doctype html>
      <html lang="it">
        <head>
          <meta charset="utf-8" />
          <title>${isWebAudit ? "Report Audit Web e Frontend" : isQuickHotelBb ? "Report Analisi rapida Hotel e B&B" : "Report Autovalutazione Velora"}</title>
          <style>
            @page {
              size: A4;
              margin: 12mm;
            }

            * {
              box-sizing: border-box;
            }

            body {
              margin: 0;
              background: #ffffff;
              color: #1f2937;
              font-family: Arial, Helvetica, sans-serif;
              font-size: 9.5px;
              line-height: 1.35;
            }

            .cover {
              border-bottom: 4px solid #C8A96B;
              padding-bottom: 14px;
              margin-bottom: 14px;
            }

            .eyebrow {
              color: #C8A96B;
              font-size: 11px;
              font-weight: 800;
              letter-spacing: 0.22em;
              text-transform: uppercase;
              margin-bottom: 10px;
            }

            h1 {
              color: #23124A;
              font-size: 25px;
              line-height: 1.1;
              margin: 0 0 12px;
            }

            h2 {
              color: #23124A;
              font-size: 16px;
              margin: 18px 0 8px;
              padding-bottom: 5px;
              border-bottom: 1px solid #e5e7eb;
              break-after: avoid;
              page-break-after: avoid;
            }

            .subtitle {
              color: #475569;
              font-size: 10.5px;
              max-width: 760px;
            }

            .grid {
              display: grid;
              grid-template-columns: repeat(4, 1fr);
              gap: 7px;
              margin: 12px 0;
            }

            .card {
              border: 1px solid #e5e7eb;
              border-radius: 10px;
              padding: 9px;
              background: #f8fafc;
            }

            .card-label {
              color: #64748b;
              font-size: 10px;
              text-transform: uppercase;
              letter-spacing: 0.12em;
              font-weight: 700;
            }

            .card-value {
              color: #23124A;
              font-size: 17px;
              font-weight: 800;
              margin-top: 4px;
            }

            .info {
              display: grid;
              grid-template-columns: repeat(3, 1fr);
              gap: 6px 14px;
              margin-top: 12px;
            }

            .info div {
              border-bottom: 1px solid #e5e7eb;
              padding-bottom: 4px;
            }

            .info span {
              display: block;
              color: #64748b;
              font-size: 10px;
              text-transform: uppercase;
              letter-spacing: 0.12em;
              font-weight: 700;
            }

            .info strong {
              display: block;
              color: #111827;
              font-size: 10.5px;
              margin-top: 2px;
            }

            table {
              width: 100%;
              border-collapse: collapse;
              margin-top: 7px;
              page-break-inside: auto;
            }

            thead {
              display: table-header-group;
            }

            th {
              background: #1F4E78;
              color: #ffffff;
              text-align: left;
              font-size: 7.2px;
              text-transform: uppercase;
              letter-spacing: 0.04em;
              padding: 5px 4px;
              border: 1px solid #d5d9dd;
            }

            td {
              border: 1px solid #d5d9dd;
              padding: 3.5px 4px;
              vertical-align: middle;
            }

            tr {
              page-break-inside: avoid;
            }

            tbody tr:nth-child(even):not(.total-row) td {
              background: #f1f3f5;
            }

            td:first-child strong {
              color: #172033;
              font-size: 9.2px;
            }

            td span {
              color: #64748b;
              font-size: 7.5px;
            }

            td small, .priority-card small {
              display: block;
              color: #64748b;
              font-size: 7.5px;
              margin-top: 2px;
            }

            .center {
              text-align: center;
            }

            .badge {
              display: inline-block;
              border: 1px solid #C8A96B;
              border-radius: 999px;
              color: #23124A;
              background: #fbf7ed;
              padding: 3px 8px;
              font-size: 10px;
              font-weight: 700;
            }

            .summary-box {
              border-left: 5px solid #C8A96B;
              background: #f8fafc;
              padding: 14px 16px;
              border-radius: 12px;
              margin-top: 14px;
            }

            .analysis-grid {
              display: grid;
              grid-template-columns: 1.45fr .75fr;
              gap: 14px;
              align-items: start;
              break-inside: avoid;
              page-break-inside: avoid;
            }

            .analysis-copy p {
              margin: 0 0 8px;
            }

            .analysis-copy .focus {
              border-left: 4px solid #C8A96B;
              background: #fbf7ed;
              border-radius: 8px;
              padding: 10px 12px;
            }

            .pie-panel {
              border: 1px solid #e5e7eb;
              border-radius: 14px;
              padding: 12px;
              text-align: center;
              page-break-inside: avoid;
            }

            .pie {
              width: 118px;
              height: 118px;
              margin: 2px auto 10px;
              border-radius: 50%;
              background: ${distributionTotal ? `conic-gradient(#B42318 0 ${criticalEnd}%, #D69E2E ${criticalEnd}% ${attentionEnd}%, #15803D ${attentionEnd}% 100%)` : "#e5e7eb"};
              position: relative;
            }

            .pie::after {
              content: "${distributionTotal}";
              position: absolute;
              inset: 27px;
              display: grid;
              place-items: center;
              border-radius: 50%;
              background: white;
              color: #23124A;
              font-size: 20px;
              font-weight: 800;
            }

            .legend {
              display: grid;
              gap: 5px;
              text-align: left;
            }

            .legend-row {
              display: grid;
              grid-template-columns: 8px 1fr auto;
              gap: 6px;
              align-items: center;
            }

            .dot { width: 8px; height: 8px; border-radius: 50%; }
            .critical { background: #B42318; }
            .attention { background: #D69E2E; }
            .controlled { background: #15803D; }

            .compact-values, .score-cell {
              white-space: nowrap;
              font-weight: 800;
              color: #23124A;
            }

            .score-cell {
              font-size: 11px;
            }

            .status {
              display: inline-block;
              min-width: 42px;
              border-radius: 999px;
              padding: 2px 5px;
              text-align: center;
              font-size: 7px;
              font-weight: 800;
            }

            .status-critical { color: #9f1239; background: #ffe4e6; }
            .status-attention { color: #92400e; background: #fef3c7; }
            .status-controlled { color: #166534; background: #dcfce7; }

            .total-row td {
              background: #dce8f2;
              color: #172033;
              font-weight: 800;
              border-top: 2px solid #1F4E78;
            }

            .insight-grid {
              display: grid;
              grid-template-columns: 1fr 1fr;
              gap: 8px;
              margin-top: 10px;
            }

            .insight-card {
              border: 1px solid #d5d9dd;
              border-top: 4px solid #1F4E78;
              border-radius: 8px;
              padding: 9px 10px;
              background: #f8fafc;
              page-break-inside: avoid;
            }

            .insight-card h3,
            .plan-card h3 {
              color: #23124A;
              font-size: 10.5px;
              margin: 0 0 5px;
            }

            .insight-card p {
              margin: 0;
            }

            .insight-card.positive { border-top-color: #15803D; }
            .insight-card.risk { border-top-color: #B42318; }
            .insight-card.commercial { border-top-color: #D69E2E; }

            .plan-grid {
              display: grid;
              grid-template-columns: repeat(3, 1fr);
              gap: 8px;
              margin-top: 10px;
            }

            .plan-card {
              border: 1px solid #d5d9dd;
              border-radius: 9px;
              padding: 9px;
              page-break-inside: avoid;
            }

            .plan-horizon {
              color: #1F4E78;
              font-size: 7.5px;
              font-weight: 800;
              letter-spacing: .1em;
              text-transform: uppercase;
              margin-bottom: 4px;
            }

            .plan-card ul {
              margin: 5px 0 0;
              padding-left: 14px;
            }

            .plan-card li {
              margin-bottom: 5px;
            }

            .consultant-conclusion {
              border: 1px solid #c9d8e6;
              border-left: 5px solid #1F4E78;
              background: #eef5fa;
              border-radius: 9px;
              padding: 11px 13px;
              margin-top: 10px;
              page-break-inside: avoid;
            }

            .priority-list {
              display: grid;
              grid-template-columns: 1fr 1fr;
              gap: 8px;
            }

            .priority-card {
              display: grid;
              grid-template-columns: 25px 1fr;
              gap: 8px;
              border: 1px solid #e5e7eb;
              border-radius: 11px;
              padding: 9px;
              page-break-inside: avoid;
            }

            .priority-number {
              display: grid;
              place-items: center;
              width: 25px;
              height: 25px;
              border-radius: 50%;
              background: #23124A;
              color: white;
              font-weight: 800;
            }

            .priority-heading {
              display: flex;
              justify-content: space-between;
              gap: 8px;
              color: #23124A;
              font-size: 10.5px;
            }

            .priority-heading span {
              color: #B42318;
              white-space: nowrap;
              font-weight: 800;
            }

            .priority-card p {
              margin: 5px 0 0;
            }

            .empty-box {
              border: 1px dashed #cbd5e1;
              border-radius: 10px;
              color: #64748b;
              padding: 14px;
            }

            .wide {
              grid-column: span 2;
            }

            .empty {
              text-align: center;
              color: #64748b;
              padding: 18px;
            }

            .page-break {
              page-break-before: always;
            }

            .footer {
              margin-top: 18px;
              padding-top: 8px;
              border-top: 1px solid #e5e7eb;
              color: #64748b;
              font-size: 8px;
            }

            @media print {
              button {
                display: none;
              }
            }
          </style>
        </head>

        <body>
          <section class="cover">
            <div class="eyebrow">Velora RMS · ${isWebAudit ? "Audit Web & Frontend" : isQuickHotelBb ? useCustomQuickSelection ? "Intervista consulenziale personalizzata" : "Analisi rapida Hotel / B&B" : "Autovalutazione consulenziale"}</div>
            <h1>${isWebAudit ? "Report audit esterno della struttura ricettiva" : isQuickHotelBb ? useCustomQuickSelection ? "Report intervista consulenziale personalizzata" : "Report analisi rapida Hotel / B&B" : "Report di autovalutazione struttura ricettiva"}</h1>
            <p class="subtitle">
              Diagnosi preliminare dei bisogni operativi, commerciali, revenue,
              amministrativi e gestionali della struttura. Il report evidenzia le aree
              in cui Velora e l’attività consulenziale possono generare maggiore valore.
            </p>

            <div class="info">
              <div>
                <span>Struttura</span>
                <strong>${safe(ownerInfo.propertyName || "Non indicata")}</strong>
              </div>
              <div>
                <span>Proprietario / referente</span>
                <strong>${safe(ownerInfo.ownerName || "Non indicato")}</strong>
              </div>
              <div>
                <span>Consulente</span>
                <strong>${safe(ownerInfo.consultantName || "Non indicato")}</strong>
              </div>
              <div>
                <span>Località</span>
                <strong>${safe(ownerInfo.location || "Non indicata")}</strong>
              </div>
              <div>
                <span>Tipologia</span>
                <strong>${safe(ownerInfo.propertyType || "Non indicata")}</strong>
              </div>
              <div>
                <span>Camere / unità</span>
                <strong>${safe(ownerInfo.rooms || "Non indicate")}</strong>
              </div>
              <div>
                <span>Canali attivi</span>
                <strong>${safe(ownerInfo.channels || "Non indicati")}</strong>
              </div>
              <div class="wide">
                <span>Obiettivo principale</span>
                <strong>${safe(ownerInfo.objective || "Non indicato")}</strong>
              </div>
              <div>
                <span>Data</span>
                <strong>${safe(generatedDate)}</strong>
              </div>
              <div>
                <span>Ora</span>
                <strong>${safe(generatedTime)}</strong>
              </div>
            </div>
          </section>

          <section>
            <h2>Sintesi executive</h2>

            <div class="grid">
              <div class="card">
                <div class="card-label">Indice opportunità</div>
                <div class="card-value">${reportScore}/100</div>
              </div>
              <div class="card">
                <div class="card-label">Voci compilate</div>
                <div class="card-value">${completedRows.length}/${allRows.length}</div>
              </div>
              <div class="card">
                <div class="card-label">Voci critiche</div>
                <div class="card-value">${distribution.critical}</div>
              </div>
              <div class="card">
                <div class="card-label">Da attenzionare</div>
                <div class="card-value">${distribution.attention}</div>
              </div>
            </div>

            <div class="summary-box">
              <strong>Chiave di lettura:</strong> il punteggio misura l’opportunità d’intervento,
              non la qualità assoluta della struttura. Cresce quando una voce è importante,
              poco presidiata e coerente con il contributo che Velora può offrire.
            </div>
          </section>

          ${commercialReportHtml}
          ${bookingEngineReportHtml}
          ${reputationReportHtml}
          ${pilotReportHtml}
          ${coverageReportHtml}

          <section>
            <h2>Tabella completa delle valutazioni</h2>
            <p>
              Quadro sintetico di tutte le voci compilate. Importanza, Presidio attuale
              e Fit Velora sono espressi su scala 0-3; il voto finale è su scala 0-100.
            </p>
            <table>
              <thead>
                <tr>
                  <th style="width: 32%">Voce e ambito</th>
                  <th style="width: 8%">Import.</th>
                  <th style="width: 8%">Presidio</th>
                  <th style="width: 7%">Fit</th>
                  <th style="width: 8%">Voto</th>
                  <th style="width: 10%">Fascia</th>
                  <th>Nota / evidenza</th>
                </tr>
              </thead>
              <tbody>
                ${valueRowsHtml}
              </tbody>
            </table>
          </section>

          <section>
            <h2>Lettura consulenziale dei dati</h2>
            <div class="analysis-grid">
              <div class="analysis-copy">
                <p><strong>Quadro complessivo.</strong> ${safe(coverageText)}</p>
                <p><strong>Concentrazione delle opportunità.</strong> Le macro-aree con il maggiore indice di intervento sono: ${safe(topAreaText)}.</p>
                <p class="focus"><strong>Valutazione della collaborazione.</strong> ${safe(collaborationText)}</p>
                <p>
                  La priorità non va definita soltanto dal voto totale: hanno precedenza le voci
                  che combinano impatto elevato, presidio insufficiente e possibilità concreta
                  di essere migliorate con responsabilità e risultati misurabili.
                </p>
              </div>
              <aside class="pie-panel">
                <div class="pie" aria-label="Distribuzione percentuale delle valutazioni"></div>
                <strong>Distribuzione delle voci</strong>
                <div class="legend">
                  <div class="legend-row"><span class="dot critical"></span><span>Critiche</span><b>${criticalPct}%</b></div>
                  <div class="legend-row"><span class="dot attention"></span><span>Medie</span><b>${attentionPct}%</b></div>
                  <div class="legend-row"><span class="dot controlled"></span><span>Basse / presidiate</span><b>${controlledPct}%</b></div>
                </div>
              </aside>
            </div>

            <div class="insight-grid">
              <article class="insight-card positive">
                <h3>Punti relativamente più presidiati</h3>
                <p>${safe(strengthText)}</p>
              </article>
              <article class="insight-card risk">
                <h3>Gap ad alto potenziale d’intervento</h3>
                <p>${safe(gapText)}</p>
              </article>
              <article class="insight-card commercial">
                <h3>Impatto economico e commerciale</h3>
                <p>${safe(commercialText)}</p>
              </article>
              <article class="insight-card">
                <h3>Governance, controllo e qualità</h3>
                <p>${safe(governanceText)}</p>
              </article>
            </div>
          </section>

          <section>
            <h2>Priorità operative: da dove iniziare</h2>
            <p>
              I primi interventi consigliati sono ordinati per impatto potenziale. Anche con
              un indice complessivo contenuto, queste aree possono giustificare un incarico
              circoscritto, con obiettivi e verifiche chiare.
            </p>
            <div class="priority-list">
              ${priorityHtml}
            </div>
          </section>

          <section>
            <h2>Piano di lavoro consigliato</h2>
            <div class="plan-grid">
              ${planHtml}
            </div>
            <div class="consultant-conclusion">
              <strong>Conclusione consulenziale.</strong> ${safe(collaborationText)}
              L’eventuale collaborazione dovrebbe partire da un perimetro definito,
              con indicatori iniziali, responsabilità assegnate e una verifica dei risultati
              entro 90 giorni. In questo modo anche criticità circoscritte possono produrre
              benefici concreti senza trasformarsi in un progetto sovradimensionato.
            </div>
          </section>

          <div class="footer">
            Report generato da Velora RMS · ${isWebAudit ? `Audit Web & Frontend · ${allRows.length} punti verificabili.` : isQuickHotelBb ? useCustomQuickSelection ? `Intervista consulenziale personalizzata · ${customQuickItemIds.length} domande selezionate.` : `Analisi rapida Hotel / B&B · ${showQuickDeepDive ? "30 domande principali + 20 di approfondimento" : "30 domande principali"}.` : "Modulo Autovalutazione struttura ricettiva."}
          </div>

        </body>
      </html>
    `;

    if (window.veloraDesktop?.savePdf) {
      try {
        const reportKind = isWebAudit
          ? "audit-web-frontend"
          : isQuickHotelBb
          ? useCustomQuickSelection
            ? "intervista-consulenziale-personalizzata"
            : "analisi-rapida-hotel-bb"
          : "autovalutazione";
        const propertySlug = sanitizeFilename(ownerInfo.propertyName);
        const result = await window.veloraDesktop.savePdf(
          html,
          `velora-${reportKind}-${propertySlug}.pdf`
        );

        if (result.canceled) {
          return;
        }

        if (!result.ok) {
          window.alert(result.error || "Errore durante la generazione del PDF.");
          return;
        }

        window.alert("Report PDF salvato correttamente.");
      } catch (error) {
        console.error(error);
        window.alert("Errore durante la generazione del PDF nel programma desktop.");
      }

      return;
    }

    if (localPilotToken) {
      try {
        const token = await connectLocalAgent(true);
        if (!token) throw new Error("Agente locale non disponibile.");
        const reportKind = isWebAudit ? "audit-web-frontend" : isQuickHotelBb ? "analisi-rapida-hotel-bb" : "autovalutazione";
        const filename = `velora-${reportKind}-${sanitizeFilename(ownerInfo.propertyName)}.pdf`;
        const response = await fetch(localAgentUrl("/api/report/pdf"), {
          method: "POST",
          mode: "cors",
          headers: { "Content-Type": "application/json", "X-Velora-Local-Token": token },
          body: JSON.stringify({ html, filename }),
        });
        if (!response.ok) {
          const problem = await response.json() as { error?: string };
          throw new Error(problem.error || "Generazione PDF non riuscita.");
        }
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
        return;
      } catch (error) {
        window.alert(error instanceof Error ? error.message : "Errore durante la generazione del PDF locale.");
        return;
      }
    }

    const existingFrame = document.getElementById("velora-print-frame");
    if (existingFrame) {
      existingFrame.remove();
    }

    const frame = document.createElement("iframe");
    frame.id = "velora-print-frame";
    frame.title = "Report PDF Velora";
    frame.style.position = "fixed";
    frame.style.right = "0";
    frame.style.bottom = "0";
    frame.style.width = "1px";
    frame.style.height = "1px";
    frame.style.border = "0";
    frame.style.opacity = "0";
    frame.setAttribute("aria-hidden", "true");

    document.body.appendChild(frame);

    const frameDocument = frame.contentDocument || frame.contentWindow?.document;

    if (!frameDocument || !frame.contentWindow) {
      window.alert("Impossibile generare il report PDF. Riprova dopo aver riaperto il modulo.");
      frame.remove();
      return;
    }

    frameDocument.open();
    frameDocument.write(html);
    frameDocument.close();

    setTimeout(() => {
      try {
        frame.contentWindow?.focus();
        frame.contentWindow?.print();
      } catch (error) {
        console.error(error);
        window.alert("Errore durante l'apertura della finestra di stampa PDF.");
      } finally {
        setTimeout(() => frame.remove(), 1500);
      }
    }, 500);
  }

  function renderQuestionCard(
    item: AssessmentItem,
    questionNumber?: number,
    isDeepDive = false,
    macro?: AssessmentMacro,
    category?: AssessmentCategory
  ) {
    const answer = answers[item.id] ?? emptyAnswer();
    const score = getItemScore(answer);
    const label = getScoreLabel(score);
    const guideText = macro && category ? getGuideText(macro, category, item) : "";

    return (
      <article
        key={item.id}
        className={`rounded-[1.5rem] border bg-white p-5 transition hover:shadow-[0_14px_34px_rgba(35,18,74,0.06)] ${
          isDeepDive
            ? "border-[#D8C8A5] hover:border-[#C8A96B]"
            : "border-[#E5DDF1] hover:border-[#D4C7E6]"
        }`}
      >
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] font-black uppercase tracking-[0.18em] text-[#C8A96B]">
              {questionNumber
                ? `${isDeepDive ? "Approfondimento" : "Domanda"} ${questionNumber}`
                : "Voce consulenziale"}
            </p>
            <h4
              title={guideEnabled ? guideText : undefined}
              className={`mt-1 text-base font-black leading-6 text-[#23124A] ${
                guideEnabled
                  ? "cursor-help underline decoration-emerald-500/70 decoration-dotted underline-offset-4"
                  : ""
              }`}
            >
              {item.text}
            </h4>
          </div>

          <div
            className={`flex w-fit shrink-0 items-center gap-3 rounded-2xl border px-4 py-3 ${label.className}`}
          >
            <span className="text-2xl font-black leading-none">{score}</span>
            <span className="text-xs font-black uppercase tracking-[0.12em]">
              {label.shortLabel}
            </span>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <label className="flex min-w-0 flex-col gap-2">
            <FieldLabel>Importanza</FieldLabel>
            <select
              value={answer.importance}
              onChange={(event) =>
                updateAnswer(item.id, { importance: Number(event.target.value) })
              }
              className="h-12 w-full rounded-2xl border border-[#E0D7EC] bg-[#FBF9FF] px-4 text-sm font-bold text-[#23124A] outline-none transition focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
            >
              {scoreOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex min-w-0 flex-col gap-2">
            <FieldLabel>Stato attuale</FieldLabel>
            <select
              value={answer.current}
              onChange={(event) =>
                updateAnswer(item.id, { current: Number(event.target.value) })
              }
              className="h-12 w-full rounded-2xl border border-[#E0D7EC] bg-[#FBF9FF] px-4 text-sm font-bold text-[#23124A] outline-none transition focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
            >
              {currentOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex min-w-0 flex-col gap-2">
            <FieldLabel>Fit Velora</FieldLabel>
            <select
              value={answer.fit}
              onChange={(event) =>
                updateAnswer(item.id, { fit: Number(event.target.value) })
              }
              className="h-12 w-full rounded-2xl border border-[#E0D7EC] bg-[#FBF9FF] px-4 text-sm font-bold text-[#23124A] outline-none transition focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
            >
              {scoreOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="mt-4 flex flex-col gap-2">
          <FieldLabel>Note, criticità, evidenze</FieldLabel>
          <textarea
            value={answer.note}
            onChange={(event) => updateAnswer(item.id, { note: event.target.value })}
            placeholder="Scrivi qui ciò che emerge: risultati, criticità, responsabilità del gestore, rischi o margini di miglioramento..."
            className="min-h-[96px] w-full resize-y rounded-2xl border border-[#E0D7EC] bg-white px-4 py-3 text-sm font-medium leading-6 text-[#23124A] outline-none transition placeholder:text-slate-400 focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
          />
        </label>
      </article>
    );
  }

  function renderExternalWebAudit() {
    const normalizedSearch = searchTerm.trim().toLowerCase();
    const publishedMonthlySamples = "monthlySamples" in activeAuditData.pricingAudit
      ? activeAuditData.pricingAudit.monthlySamples : [];
    const publishedComparisonSamples = "comparisonSamples" in activeAuditData.pricingAudit
      ? activeAuditData.pricingAudit.comparisonSamples : [];
    const rateDetailRows = buildRateComparisonRows(rateQuotes, todayLocalIso());
    const publishedRange = (sample: { low?: number; high?: number; scope?: string; status?: string }) =>
      sample.low === undefined || sample.high === undefined
        ? sample.status || "Non campionato"
        : `€${sample.low.toFixed(2)}${sample.low === sample.high ? "" : `–€${sample.high.toFixed(2)}`}/notte · ${sample.scope || "copertura da verificare"}`;
    const cohortOptions = [...new Map(rateQuotes.map((quote) => [rateCohortKey(quote), rateCohortLabel(quote)])).entries()];
    const activeCohort = selectedRateCohort && cohortOptions.some(([key]) => key === selectedRateCohort)
      ? selectedRateCohort : cohortOptions[0]?.[0] ?? "";
    const comparableQuotes = activeCohort ? latestRateQuotes(rateQuotes, activeCohort) : [];
    const today = new Date();
    const rateMonths = futureMonthKeys(today);
    const statusCounts = AUDIT_STATUS_OPTIONS.map((option) => ({
      ...option,
      count: allRows.filter(({ item }) => answers[item.id]?.auditStatus === option.value).length,
    }));

    const visibleData = EXTERNAL_WEB_AUDIT_DATA.map((macro) => ({
      ...macro,
      categories: macro.categories
        .map((category) => ({
          ...category,
          items: category.items.filter((item) => {
            const sources = getExternalAuditSources(item.id);
            const matchesSource =
              auditSourceFilter === "Tutte le fonti" || sources.some((source) => source === auditSourceFilter);
            const matchesSearch =
              !normalizedSearch ||
              `${macro.title} ${category.title} ${item.text} ${sources.join(" ")}`
                .toLowerCase()
                .includes(normalizedSearch);
            return matchesSource && matchesSearch;
          }),
        }))
        .filter((category) => category.items.length > 0),
    })).filter((macro) => macro.categories.length > 0);

    return (
      <section className="flex flex-col gap-5">
        <div className="rounded-[2rem] border border-emerald-200 bg-gradient-to-br from-emerald-50 to-white p-6 shadow-[0_18px_50px_rgba(35,18,74,0.05)]">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
            <div className="max-w-4xl">
              <p className="text-[11px] font-black uppercase tracking-[0.24em] text-emerald-700">
                Verifica autonoma senza intervista
              </p>
              <h2 className="mt-2 text-2xl font-black text-[#23124A]">
                Checklist Audit Web &amp; Frontend
              </h2>
              <p className="mt-2 text-sm leading-7 text-[#50627F]">
                Controlla solo elementi dimostrabili dall’esterno. Per ogni voce indica il riscontro
                trovato e annota URL, pagina, screenshot o risultato del test. Un elemento non visibile
                non prova che il processo interno non esista: segnala soltanto che non è verificabile dal cliente.
              </p>
            </div>
            <div className="rounded-2xl border border-emerald-200 bg-white px-5 py-4 text-center">
              <p className="text-[10px] font-black uppercase tracking-[0.18em] text-emerald-700">
                Punti verificabili
              </p>
              <p className="mt-1 text-4xl font-black text-[#23124A]">{allRows.length}</p>
              <p className="mt-1 text-xs font-semibold text-[#50627F]">estratti dalle 643 voci</p>
            </div>
          </div>

          <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_260px]">
            <label className="flex flex-col gap-2">
              <FieldLabel>Cerca nella checklist</FieldLabel>
              <input
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Es. foto, CIN, prezzi, recensioni, mobile..."
                className="h-11 rounded-2xl border border-emerald-200 bg-white px-4 text-sm font-semibold text-[#23124A] outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
              />
            </label>
            <label className="flex flex-col gap-2">
              <FieldLabel>Dove stai verificando</FieldLabel>
              <select
                value={auditSourceFilter}
                onChange={(event) => setAuditSourceFilter(event.target.value)}
                className="h-11 rounded-2xl border border-emerald-200 bg-white px-4 text-sm font-bold text-[#23124A] outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
              >
                <option>Tutte le fonti</option>
                {EXTERNAL_AUDIT_SOURCE_GROUPS.map((group) => (
                  <option key={group.label}>{group.label}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            {statusCounts.map((status) => (
              <div key={status.value} className={`rounded-2xl border px-4 py-3 ${status.className}`}>
                <p className="text-[10px] font-black uppercase tracking-[0.14em]">{status.shortLabel}</p>
                <p className="mt-1 text-2xl font-black">{status.count}</p>
              </div>
            ))}
          </div>
        </div>

        <section className="rounded-[2rem] border border-[#E5DDF1] bg-white p-5 shadow-[0_14px_40px_rgba(35,18,74,0.05)] md:p-6">
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[#C8A96B]">Approfondimento non incluso nell'indice dei 50 controlli</p>
          <h3 className="mt-1 text-xl font-black text-[#23124A]">Mappa delle singole OTA e dei gruppi</h3>
          <p className="mt-2 text-xs leading-5 text-[#50627F]">Segna una scheda come presente solo con un URL univoco. “Non trovato” significa soltanto che non è emersa nella ricerca pubblica; non prova l'assenza di un contratto. Google Hotels è un metasearch, HolidayCheck può mostrare offerte senza distribuzione diretta.</p>
          <div className="mt-4 grid grid-cols-1 gap-2 lg:grid-cols-2">
            {activeAuditData.otaPresence.map((channel) => {
              const id = `audit-ota-${channel.id}`;
              const answer = answers[id] ?? emptyAnswer();
              return <div key={id} className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div><p className="text-xs font-black text-[#23124A]">{channel.platform}</p><p className="text-[10px] font-semibold text-[#50627F]">{channel.group}</p></div>
                  <select aria-label={`Esito ${channel.platform}`} value={answer.auditStatus ?? ""} onChange={(event) => updateAnswer(id, { auditStatus: event.target.value as AuditStatus })} className="rounded-lg border border-[#DCCFEA] bg-white px-2 py-1.5 text-[11px] font-bold text-[#23124A]">
                    <option value="">Da esaminare</option><option value="present">Scheda trovata</option><option value="missing">Non trovata</option><option value="unverified">Non confermata</option><option value="not-applicable">Non adatta</option>
                  </select>
                </div>
                <input value={answer.note} onChange={(event) => updateAnswer(id, { note: event.target.value })} placeholder="URL o prova concreta della scheda" className="mt-2 w-full rounded-lg border border-[#E0D7EC] bg-white px-2.5 py-2 text-[11px] text-[#23124A] placeholder:text-slate-400" />
              </div>;
            })}
          </div>
          <section className="mt-5 rounded-2xl border border-[#C8A96B] bg-[#FFF9EC] p-4">
            <h3 className="text-lg font-black text-[#23124A]">Booking engine e fornitore del canale diretto</h3>
            <p className="mt-1 text-[11px] leading-5 text-[#50627F]">Registra anche il caso in cui la struttura usa soltanto un minisito ospitato dal fornitore. Un URL può identificare Kross Booking o ErmesHotels; con un dominio personalizzato il fornitore può restare non riconoscibile. Il collegamento non dimostra che il checkout funzioni.</p>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              <label className="text-[11px] font-black text-[#23124A]">Esito della verifica
                <select value={answers["audit-booking-engine"]?.auditStatus || "unverified"} onChange={(event) => updateAnswer("audit-booking-engine", { auditStatus: event.target.value as AuditStatus })} className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs">
                  <option value="unverified">Non verificato</option><option value="present">Motore e fornitore identificati</option><option value="partial">Percorso rilevato; fornitore incerto</option><option value="missing">Percorso non rilevato nel campione</option>
                </select>
              </label>
              <label className="text-[11px] font-black text-[#23124A]">Fornitore identificato
                <input value={answers["audit-booking-engine-provider"]?.note || ""} onChange={(event) => updateAnswer("audit-booking-engine-provider", { note: event.target.value })} placeholder="Es. Kross Booking, ErmesHotels; lascia vuoto se non certo" className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" />
              </label>
              <label className="text-[11px] font-black text-[#23124A]">URL del percorso di prenotazione
                <input type="url" value={answers["audit-booking-engine-url"]?.note || ""} onChange={(event) => updateAnswer("audit-booking-engine-url", { note: event.target.value })} placeholder="https://..." className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" />
              </label>
              <label className="text-[11px] font-black text-[#23124A]">Tipo di collegamento
                <input value={answers["audit-booking-engine-mode"]?.note || ""} onChange={(event) => updateAnswer("audit-booking-engine-mode", { note: event.target.value })} placeholder="Sito ospitato, link esterno, widget integrato..." className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" />
              </label>
            </div>
            <button type="button" onClick={() => {
              const url = answers["audit-booking-engine-url"]?.note || "";
              const match = providerFromBookingUrl(url);
              if (!match) { window.alert("Inserisci l'URL pubblico del percorso diretto: una scheda OTA non identifica il booking engine."); return; }
              updateAnswer("audit-booking-engine-provider", { note: match.provider });
              updateAnswer("audit-booking-engine-mode", { note: match.mode });
              updateAnswer("audit-booking-engine", { auditStatus: match.status });
              updateAnswer("audit-booking-engine-evidence", { note: `Dominio del percorso di prenotazione: ${new URL(url).hostname}. Verificare manualmente disponibilità e checkout.` });
            }} className="mt-3 rounded-xl border border-[#C8A96B] bg-white px-4 py-2 text-xs font-black text-[#23124A]">Riconosci il fornitore dall’URL</button>
            <label className="mt-3 block text-[11px] font-black text-[#23124A]">Evidenza e limiti della verifica
              <textarea value={answers["audit-booking-engine-evidence"]?.note || ""} onChange={(event) => updateAnswer("audit-booking-engine-evidence", { note: event.target.value })} placeholder="Dove porta Prenota, cosa compare, data della prova, cosa non è stato verificato" className="mt-1 block min-h-[70px] w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" />
            </label>
            {browserPilotResult?.propertyId === activeAuditData.id && browserPilotResult.bookingEngine && <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-[11px] text-[#135443]">
              <b>Riscontro della prova locale:</b> {browserPilotResult.bookingEngine.provider || "Fornitore non identificato"} · {browserPilotResult.bookingEngine.evidence}
              <button type="button" onClick={() => {
                const found = browserPilotResult.bookingEngine!;
                updateAnswer("audit-booking-engine", { auditStatus: found.status === "provider_identified" ? "present" : found.status === "provider_unknown" || found.status === "request_only" ? "partial" : "unverified" });
                updateAnswer("audit-booking-engine-provider", { note: found.provider });
                updateAnswer("audit-booking-engine-url", { note: found.url });
                updateAnswer("audit-booking-engine-mode", { note: found.mode });
                updateAnswer("audit-booking-engine-evidence", { note: found.evidence });
              }} className="ml-2 font-black underline">Usa questo riscontro</button>
            </div>}
          </section>
          <h3 className="mt-6 text-lg font-black text-[#23124A]">Piani tariffari, promozioni e sconti per canale</h3>
          <p className="mt-1 text-xs leading-5 text-[#50627F]">Registra soltanto ciò che compare sulla specifica scheda, con data e URL. Una dicitura “potresti avere uno sconto” non dimostra una promozione attiva; tariffe per iscritti o app vanno distinte da quelle pubbliche.</p>
          <label className="mt-3 block text-[11px] font-black text-[#23124A]">Sito diretto e listino
            <textarea value={answers["audit-policy-direct"]?.note ?? ""} onChange={(event) => updateAnswer("audit-policy-direct", { note: event.target.value })} placeholder="Periodi, prezzi, condizioni, fonte e data" className="mt-1.5 min-h-[65px] w-full resize-y rounded-xl border border-[#E0D7EC] bg-[#FBF9FF] px-3 py-2 text-xs font-medium leading-5 text-[#23124A]" />
          </label>
          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
            {activeAuditData.otaPresence.map((channel) => <label key={`policy-${channel.id}`} className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3 text-[11px] font-black text-[#23124A]">
              {channel.platform} <span className="font-medium text-[#50627F]">· {channel.group}</span>
              <textarea value={answers[`audit-policy-${channel.id}`]?.note ?? ""} onChange={(event) => updateAnswer(`audit-policy-${channel.id}`, { note: event.target.value })} placeholder="Rimborsabile/parziale/non rimborsabile; Genius, mobile, member, pacchetti; URL e data. Se non verificato, dichiararlo." className="mt-2 min-h-[94px] w-full resize-y rounded-lg border border-[#E0D7EC] bg-white px-2.5 py-2 text-[11px] font-medium leading-5 text-[#23124A] placeholder:text-slate-400" />
            </label>)}
          </div>

          <h3 className="mt-7 text-lg font-black text-[#23124A]">Prezzi osservati per mese e delta tra OTA</h3>
          <p className="mt-1 text-xs leading-5 text-[#50627F]">Il <b>range</b> va dalla tipologia meno cara alla più cara effettivamente quotata per quelle date, usando il piano meno caro di ciascuna tipologia. Non è ADR reale (ricavi camere / camere vendute), né una media di tutto il mese. Un delta è ammesso soltanto quando è confermata la <b>stessa unità fisica</b>, oltre a date, ospiti, durata, colazione, cancellazione, pubblico, valuta e imposte uguali. “—” non significa prezzo zero.</p>
          {pilotDistributionAsymmetries(browserPilotResult).length > 0 && <div className="mt-4 rounded-2xl border border-amber-300 bg-amber-50 p-4">
            <h4 className="text-sm font-black text-[#23124A]">Asimmetrie distributive OTA rilevate</h4>
            <p className="mt-1 text-[11px] leading-5 text-[#50627F]">Confronto eseguito solo sulle stesse date e usando tipologie/unità con prezzo frontend validato. La differenza è un fatto osservato; la causa tecnica (channel manager, mapping, allotment, restrizioni o stop-sale) resta da verificare.</p>
            <div className="mt-3 space-y-2">
              {pilotDistributionAsymmetries(browserPilotResult).map((item,index)=><div key={"ota-asym-"+index} className="rounded-xl border border-amber-200 bg-white p-3">
                <p className="text-xs font-black text-[#7C4A00]">{item.otaLabel} · {item.checkin} → {item.checkout} · {item.unitCount}/{item.maxUnitCount} tipologie</p>
                <p className="mt-1 text-[11px] leading-5 text-[#50627F]">{item.finding}</p>
                {item.units.length>0 && <p className="mt-1 text-[10px] font-semibold text-[#23124A]">Tipologie rilevate: {item.units.join(" · ")}</p>}
              </div>)}
            </div>
          </div>}
          <div className="mt-4 rounded-2xl border border-[#C8A96B] bg-[#FFF9EC] p-4">
            <h4 className="text-sm font-black text-[#23124A]">Rilevazione locale gratuita</h4>
            <p className="mt-1 text-[11px] leading-5 text-[#50627F]">Configura un test mirato scegliendo <b>periodo</b> e <b>OTA</b>. Velora analizza soltanto i canali selezionati e, nei test successivi, riusa le schede già verificate: quando aggiungi una nuova OTA la discovery si concentra sul nuovo canale. Il percorso tariffario resta sempre pubblico: <b>scheda struttura → date → 2 adulti → Cerca/Verifica disponibilità → tariffe visibili</b>. Nessun login, registrazione, account, tariffa member o app. Un HTTP 429/403 senza frontend utilizzabile viene registrato e il test passa automaticamente al canale successivo.</p>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <label className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-black ${localPilotGhost ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-[#E5DDF1] bg-white text-[#50627F]"}`}>
                <input
                  type="checkbox"
                  checked={localPilotGhost}
                  disabled={localPilotRunning}
                  onChange={(event) => {
                    const enabled = event.target.checked;
                    setLocalPilotGhost(enabled);
                    window.localStorage.setItem("velora-pilot-ghost", enabled ? "1" : "0");
                  }}
                />
                Modalità Ghost · browser minimizzato
              </label>
              <label className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-black ${localPilotAssisted ? "border-amber-300 bg-amber-50 text-amber-900" : "border-[#E5DDF1] bg-white text-[#50627F]"}`}>
                <input
                  type="checkbox"
                  checked={localPilotAssisted}
                  disabled={localPilotRunning}
                  onChange={(event) => {
                    const enabled = event.target.checked;
                    setLocalPilotAssisted(enabled);
                    window.localStorage.setItem("velora-pilot-assisted", enabled ? "1" : "0");
                  }}
                />
                Assistenza manuale su verifica visibile (opzionale)
              </label>
              {localPilotRunning && <span className="inline-flex items-center gap-2 text-xs font-black text-emerald-800">
                <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-500" />
                Scraping in corso
              </span>}
            </div>
            {localPilotRunning && <div className="mt-3 rounded-xl border border-emerald-200 bg-white p-3">
              <div className="mb-1 flex items-center justify-between gap-3 text-[10px] font-black text-[#23124A]">
                <span>{localPilotPhase || "Velora sta lavorando"}</span>
                <span>{Math.max(1, Math.min(99, localPilotProgress))}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[#EEE8F4]">
                <div className="h-full rounded-full bg-emerald-500 transition-all duration-500" style={{ width: `${Math.max(1, Math.min(99, localPilotProgress))}%` }} />
              </div>
            </div>}
            {localPilotRunning && localPilotIntervention && <div className="mt-3 rounded-xl border-2 border-amber-400 bg-amber-50 p-4 text-[#23124A] shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-black">Azione richiesta · {localPilotIntervention.label || localPilotIntervention.otaId || "OTA"}</p>
                <span className="rounded-full bg-amber-200 px-2 py-1 text-[9px] font-black uppercase tracking-wide">Chrome portato in primo piano</span>
              </div>
              {localPilotIntervention.reason && <p className="mt-2 text-[11px] font-semibold text-amber-950">{localPilotIntervention.reason}</p>}
              <p className="mt-2 text-xs font-semibold leading-5">{localPilotIntervention.instructions || "Completa nella finestra Chrome l\'azione richiesta dal portale, poi riprendi."}</p>
              {localPilotIntervention.stay?.checkin && <p className="mt-2 text-[10px] font-black text-[#50627F]">Date da mantenere: {localPilotIntervention.stay.checkin} → {localPilotIntervention.stay.checkout} · {localPilotIntervention.stay.adults || 2} adulti</p>}
              <p className="mt-2 text-[10px] font-semibold text-[#50627F]"><b>Regola fissa:</b> Velora non effettua mai login, registrazione o accesso account e non usa tariffe member/app. L\'intervento serve solo per una scheda pubblica, cookie/consenso o una verifica visibile; poi riprende sul frontend pubblico.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" onClick={() => void respondLocalPilotIntervention("continue")} className="rounded-xl bg-[#23124A] px-4 py-2 text-xs font-black text-white">Ho completato · riprendi</button>
                <button type="button" onClick={() => void respondLocalPilotIntervention("skip")} className="rounded-xl border border-amber-400 bg-white px-4 py-2 text-xs font-black text-amber-950">Salta questa OTA</button>
              </div>
            </div>}
            {!localPilotToken ? <div className="mt-4 flex flex-wrap items-center gap-2">
              <button type="button" onClick={() => void connectLocalAgent(false)} className="rounded-xl border border-[#C8A96B] bg-white px-4 py-2 text-xs font-black text-[#23124A]">Collega agente locale</button>
              <span className="text-[10px] font-semibold text-[#50627F]">Puoi restare su Velora online: l'agente esegue Chrome/Playwright sul tuo PC.</span>
            </div> : <div className="mt-4 rounded-2xl border border-[#E5DDF1] bg-white p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-wide text-[#23124A]">Configura test OTA</p>
                  <p className="mt-1 text-[10px] leading-4 text-[#50627F]">Scegli periodo e canali. Bianco = escluso; colorato = selezionato. Velora analizzerà soltanto le OTA che scegli.</p>
                </div>
                <div className="rounded-xl bg-[#F6F2FA] px-3 py-2 text-[10px] font-black text-[#23124A]">
                  {localPilotSelectedChannels.length}/10 OTA · {localPilotPeriod === 12 ? "12 mesi avanti" : `${localPilotPeriod} ${localPilotPeriod === 1 ? "mese" : "mesi"}`}
                </div>
              </div>

              <div className="mt-4">
                <p className="mb-2 text-[10px] font-black uppercase tracking-wide text-[#50627F]">Periodo</p>
                <div className="flex flex-wrap gap-2">
                  {([
                    { value: 1 as LocalPilotPeriod, label: "1 mese", detail: "mese corrente" },
                    { value: 6 as LocalPilotPeriod, label: "6 mesi", detail: "mese corrente + 5" },
                    { value: 12 as LocalPilotPeriod, label: "12 mesi", detail: "fino allo stesso mese dell’anno prossimo" },
                  ]).map((option) => {
                    const selected = localPilotPeriod === option.value;
                    return <button
                      key={option.value}
                      type="button"
                      disabled={localPilotRunning}
                      aria-pressed={selected}
                      onClick={() => {
                        setLocalPilotPeriod(option.value);
                        window.localStorage.setItem("velora-pilot-period", String(option.value));
                      }}
                      className={`rounded-xl border px-4 py-2 text-left text-xs font-black transition disabled:opacity-50 ${selected ? "border-[#23124A] bg-[#23124A] text-white shadow-sm" : "border-[#D8CEE7] bg-white text-[#50627F] hover:border-[#8F79AE] hover:bg-[#F8F5FB]"}`}
                    >
                      <span className="block">{option.label}</span>
                      <span className={`block text-[9px] font-semibold ${selected ? "text-white/75" : "text-[#7A6A91]"}`}>{option.detail}</span>
                    </button>;
                  })}
                </div>
              </div>

              <div className="mt-4">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[10px] font-black uppercase tracking-wide text-[#50627F]">OTA da analizzare</p>
                  <div className="flex gap-3">
                    <button
                      type="button"
                      disabled={localPilotRunning}
                      onClick={() => {
                        const all = LOCAL_PILOT_OTA_OPTIONS.map((item) => item.id);
                        setLocalPilotSelectedChannels([...all]);
                        window.localStorage.setItem("velora-pilot-selected-channels", JSON.stringify(all));
                      }}
                      className="text-[10px] font-black text-[#23124A] underline decoration-[#C8A96B] underline-offset-2 disabled:opacity-50"
                    >Seleziona tutte</button>
                    <button
                      type="button"
                      disabled={localPilotRunning}
                      onClick={() => {
                        setLocalPilotSelectedChannels([]);
                        window.localStorage.setItem("velora-pilot-selected-channels", "[]");
                      }}
                      className="text-[10px] font-black text-[#50627F] underline decoration-[#D8CEE7] underline-offset-2 disabled:opacity-50"
                    >Deseleziona tutte</button>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {LOCAL_PILOT_OTA_OPTIONS.map((ota) => {
                    const selected = localPilotSelectedChannels.includes(ota.id);
                    return <button
                      key={ota.id}
                      type="button"
                      disabled={localPilotRunning}
                      aria-pressed={selected}
                      onClick={() => {
                        const next = selected
                          ? localPilotSelectedChannels.filter((id) => id !== ota.id)
                          : [...localPilotSelectedChannels, ota.id];
                        const ordered = LOCAL_PILOT_OTA_OPTIONS.map((item) => item.id).filter((id) => next.includes(id));
                        setLocalPilotSelectedChannels(ordered);
                        window.localStorage.setItem("velora-pilot-selected-channels", JSON.stringify(ordered));
                      }}
                      className={`rounded-xl border px-4 py-2 text-xs font-black transition disabled:opacity-50 ${selected ? ota.active : ota.idle}`}
                    >
                      <span className="inline-flex items-center gap-2">
                        <span className={`flex h-4 w-4 items-center justify-center rounded-full border text-[9px] ${selected ? "border-current bg-white/70" : "border-current/40 bg-white"}`}>{selected ? "✓" : ""}</span>
                        {ota.label}
                      </span>
                    </button>;
                  })}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#EEE8F4] pt-4">
                <div className="text-[10px] leading-4 text-[#50627F]">
                  <b className="text-[#23124A]">Selezione:</b> {localPilotSelectedChannels.length
                    ? LOCAL_PILOT_OTA_OPTIONS.filter((ota) => localPilotSelectedChannels.includes(ota.id)).map((ota) => ota.label).join(" · ")
                    : "nessuna OTA selezionata"}
                </div>
                <button
                  type="button"
                  disabled={localPilotRunning || localPilotSelectedChannels.length === 0}
                  onClick={() => void startLocalPilot(localPilotPeriod, localPilotSelectedChannels)}
                  className="rounded-xl bg-[#23124A] px-5 py-2.5 text-xs font-black text-white shadow-sm transition hover:bg-[#33205B] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {localPilotRunning ? "Analisi in corso…" : "Avvia analisi selezionata"}
                </button>
              </div>
            </div>}
            {localPilotMessage && <p className="mt-2 text-[11px] font-semibold text-[#23124A]" role="status">{localPilotMessage}</p>}
            <label className="mt-3 inline-flex cursor-pointer items-center gap-2 rounded-xl bg-[#23124A] px-4 py-2 text-xs font-black text-white">Importa esiti della prova locale<input type="file" accept=".json,application/json" onChange={importBrowserPilotResult} className="sr-only" /></label>
            {browserPilotResult?.propertyId === activeAuditData.id && <>
              <p className="mt-2 text-[11px] font-semibold text-[#23124A]">
                {browserPilotResult.observations.length} controlli tariffari importati · {browserPilotResult.observations.reduce((sum, item) => sum + (item.quotes?.length || 0), 0)} righe prezzo osservate · {pilotDetectedRateQuotes(browserPilotResult).length} validate · {Object.keys(browserPilotResult.otaProfiles || {}).length} profili/metasearch · esiti inclusi nel prossimo report PDF.
              </p>
              <p className="mt-1 text-[10px] leading-4 text-[#50627F]"><b>Lettura canali:</b> 14 fonti complessive = 10 canali tariffari + 4 profili/metasearch. Una riga prezzo osservata può essere reale ma ancora non attribuita con certezza a camera/piano; in quel caso viene mostrata ma non usata nel delta.</p>
              {(browserPilotResult.roomReferences || []).length > 0 && <div className="mt-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-[10px] leading-4 text-emerald-950">
                <b>Camera reference Booking</b>
                {(browserPilotResult.roomReferences || []).map((reference, index) => <span key={`room-ref-${index}`} className="block mt-1">
                  {reference.checkin} → {reference.checkout}: <b>{reference.roomType}</b>{Number.isFinite(reference.matchedOtas) ? ` · stessa tipologia riconosciuta su ${reference.matchedOtas} OTA` : ""}
                </span>)}
                <span className="block mt-1">Le altre camere vengono escluse dal confronto quando la stessa tipologia è disponibile. Se non esiste, Velora mostra una sola alternativa con avviso e senza delta.</span>
              </div>}
              {Object.keys(browserPilotResult.otaProfiles || {}).length > 0 && <div className="mt-2 overflow-x-auto rounded-xl border border-[#E5DDF1] bg-white">
                <table className="min-w-[860px] w-full border-collapse text-[10px]">
                  <thead className="bg-[#F4F0F8] text-[#23124A]"><tr><th className="p-2 text-left">Profilo</th><th className="p-2 text-left">Rating</th><th className="p-2 text-left">Recensioni</th><th className="p-2 text-left">Raccomandazione</th><th className="p-2 text-left">Riscontro</th></tr></thead>
                  <tbody>{Object.entries(browserPilotResult.otaProfiles || {}).map(([otaId, profile]) => <tr key={`profile-${otaId}`} className="border-t border-[#EEE8F4] align-top">
                    <td className="p-2 font-black">{activeAuditData.otaPresence.find((channel) => channel.id === otaId)?.platform || otaId}<span className="block text-[9px] font-medium text-[#50627F]">{profile.status}</span></td>
                    <td className="p-2">{Number.isFinite(profile.rating) && Number.isFinite(profile.ratingScale) ? `${Number(profile.rating).toFixed(1)}/${Number(profile.ratingScale).toFixed(0)}` : pilotProfileMetricFallback(profile)}</td>
                    <td className="p-2">{Number.isFinite(profile.reviewCount) ? Number(profile.reviewCount).toLocaleString("it-IT") : pilotProfileMetricFallback(profile)}</td>
                    <td className="p-2">{pilotProfileMetric(profile.recommendationRate, profile, "%")}</td>
                    <td className="p-2">
                      {profile.evidence || "Profilo letto senza metriche strutturate"}
                      {(profile.visiblePrices || []).length > 0 && <span className="block mt-1 font-black text-[#23124A]">Prezzi EUR visibili sul profilo: {(profile.visiblePrices || []).slice(0, 8).map((item) => `€${Number(item.amount).toFixed(2)}`).join(" · ")} <span className="font-medium text-[#50627F]">(non attribuiti a camera/date, quindi esclusi dal delta)</span></span>}
                      {(profile.commercialHosts || []).length > 0 && <span className="block mt-1 text-[9px] text-[#50627F]">Link commerciali: {(profile.commercialHosts || []).slice(0, 6).join(", ")}</span>}
                    </td>
                  </tr>)}</tbody>
                </table>
              </div>}
              {browserPilotResult.observations.length > 0 && <div className="mt-2 max-h-72 overflow-auto rounded-xl border border-[#E5DDF1] bg-white">
                <table className="min-w-[980px] w-full border-collapse text-[10px]">
                  <thead className="sticky top-0 bg-[#23124A] text-white"><tr><th className="p-2 text-left">OTA</th><th className="p-2 text-left">Date testate</th><th className="p-2 text-left">Esito tecnico</th><th className="p-2 text-left">Motivo / cosa manca</th></tr></thead>
                  <tbody>{browserPilotResult.observations.map((observation, index) => {
                    const quotes = observation.quotes || [];
                    const verified = quotes.filter((quote) => quote.verified).length;
                    const label = pilotCoverageSummary(browserPilotResult, observation.month, observation.otaId) || observation.status;
                    const quoteDetail = quotes.length ? ` · ${quotes.length} righe prezzo · ${verified} validate` : "";
                    return <tr key={`pilot-diagnostic-${index}`} className="border-t border-[#EEE8F4] align-top odd:bg-[#FBF9FF]">
                      <td className="p-2 font-black">{activeAuditData.otaPresence.find((channel) => channel.id === observation.otaId)?.platform || observation.otaId}</td>
                      <td className="p-2">{observation.checkin} → {observation.checkout}</td>
                      <td className="p-2 font-semibold">{label}{quoteDetail}</td>
                      <td className="p-2">{observation.evidence || "Nessun dettaglio tecnico disponibile"}{observation.finalUrl && <span className="block mt-1 break-all text-[9px] text-[#50627F]">Pagina finale: {observation.finalUrl}</span>}</td>
                    </tr>;
                  })}</tbody>
                </table>
              </div>}
              {browserPilotResult.observations.some((item) => item.quotes?.length) && <div className="mt-2 max-h-64 overflow-auto rounded-xl border border-[#E5DDF1] bg-white">
                <table className="w-full border-collapse text-[10px]">
                  <thead className="sticky top-0 bg-[#F4F0F8] text-[#23124A]"><tr><th className="p-2 text-left">OTA</th><th className="p-2 text-left">Date</th><th className="p-2 text-left">Camera / piano</th><th className="p-2 text-right">€/notte</th><th className="p-2 text-right">Totale soggiorno</th><th className="p-2 text-left">Condizioni</th></tr></thead>
                  <tbody>
                    {browserPilotResult.observations.flatMap((observation, obsIndex) => (observation.quotes || []).filter((quote) => quote.comparisonSelected !== false).map((quote, quoteIndex) =>
                      <tr key={`pilot-quote-${obsIndex}-${quoteIndex}`} className={`border-t border-[#EEE8F4] align-top ${quote.roomMatchStatus === "different-room-fallback" ? "bg-amber-50" : ""}`}>
                        <td className="p-2 font-black">{activeAuditData.otaPresence.find((channel) => channel.id === observation.otaId)?.platform || observation.otaId}</td>
                        <td className="p-2">{observation.checkin} → {observation.checkout}</td>
                        <td className="p-2">{quote.roomType}{quote.ratePlan && <span className="block text-[9px] font-semibold text-[#7A5B96]">{quote.ratePlan}</span>}<span className="block text-[9px] text-[#50627F]">{quote.verified ? "parser verificato" : "da verificare"}</span>{quote.roomMatchStatus === "booking-reference" && <span className="mt-1 block font-black text-emerald-700">REFERENCE BOOKING</span>}{quote.roomMatchStatus === "same-room" && <span className="mt-1 block font-black text-emerald-700">STESSA CAMERA DELLA REFERENCE BOOKING</span>}{quote.roomMatchStatus === "different-room-fallback" && <span className="mt-1 block font-black text-amber-700">ATTENZIONE · CAMERA DIVERSA DALLA REFERENCE BOOKING</span>}</td>
                        <td className="p-2 text-right font-black">€{Number(quote.nightlyRate ?? (quote.total / Math.max(1, quote.nights))).toFixed(2)}<span className="block text-[9px] font-normal text-[#50627F]">{quote.displayedBasis === "nightly" ? "mostrato dal portale" : quote.displayedBasis === "stay-total" ? "calcolato dal totale" : "normalizzato"}</span></td>
                        <td className="p-2 text-right font-black">€{Number(quote.total).toFixed(2)}<span className="block text-[9px] font-normal text-[#50627F]">{quote.displayedBasis === "stay-total" ? "mostrato dal portale" : quote.displayedBasis === "nightly" ? `calcolato × ${quote.nights} notti` : `${quote.nights} notti`}</span></td>
                        <td className="p-2">{[quote.ratePlan, quote.board, quote.refund].filter(Boolean).join(" · ")}{quote.priceDerivation && <span className="block mt-1 text-[9px] text-[#50627F]">{quote.priceDerivation}</span>}{quote.comparisonWarning && <span className="block mt-1 font-black text-amber-700">{quote.comparisonWarning}</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>}
            </>}
          </div>
          <h4 className="mt-4 text-sm font-black text-[#23124A]">Tariffe puntuali per OTA e scostamento da Booking</h4>
          <p className="mt-1 text-[10px] leading-4 text-[#50627F]">Ogni cifra è un preventivo datato diviso per le notti. Δ = (prezzo OTA / prezzo Booking − 1) × 100. Un numero nella colonna Δ compare solo con unità fisica e condizioni identiche, rilevate lo stesso giorno; altrimenti n.d. La tabella descrittiva delle politiche commerciali resta invariata.</p>
          <div className="mt-2 overflow-x-auto rounded-xl border border-[#E5DDF1]"><table className="min-w-[1050px] w-full border-collapse text-[11px]"><thead className="bg-[#23124A] text-white"><tr><th className="p-2 text-left">Date</th><th className="p-2 text-left">OTA</th><th className="p-2 text-left">Camera/unità</th><th className="p-2 text-right">€/notte</th><th className="p-2 text-right">Booking base</th><th className="p-2 text-right">Δ</th><th className="p-2 text-left">Condizioni / limite</th></tr></thead><tbody>
            {publishedComparisonSamples.map((sample, index) => <tr key={`published-${index}`} className="border-t border-[#E5DDF1] align-top odd:bg-[#FBF9FF]"><td className="p-2">{sample.stay}</td><td className="p-2 font-black">{activeAuditData.otaPresence.find((channel) => channel.id === sample.otaId)?.platform || (sample.otaId === "sito" ? "Sito diretto" : sample.otaId)}</td><td className="p-2">{sample.roomType}</td><td className="p-2 text-right font-black">€{sample.nightly.toFixed(2)}</td><td className="p-2 text-right">—</td><td className="p-2 text-right">{sample.delta}</td><td className="p-2">{sample.conditions}</td></tr>)}
            {rateDetailRows.map(({ quote, nightly, bookingNightly, deltaPct }) => <tr key={`rate-${quote.id}`} className="border-t border-[#E5DDF1] align-top odd:bg-[#FBF9FF]"><td className="p-2">{quote.stayDate}</td><td className="p-2 font-black">{activeAuditData.otaPresence.find((channel) => channel.id === quote.otaId)?.platform || quote.otaId}</td><td className="p-2">{quote.roomType}<span className="block text-[10px] text-[#50627F]">{quote.referenceRoomKey ? `Reference Booking: ${quote.bookingReferenceRoom || quote.roomType}` : quote.unitId ? `Unità verificata: ${quote.unitId}` : "Camera non comparabile con Booking"}</span>{quote.roomMatchStatus === "different-room-fallback" && <span className="block mt-1 text-[10px] font-black text-amber-700">ATTENZIONE · CAMERA DIVERSA</span>}</td><td className="p-2 text-right font-black">€{nightly.toFixed(2)}</td><td className="p-2 text-right">{bookingNightly === null ? "—" : `€${bookingNightly.toFixed(2)}`}</td><td className="p-2 text-right font-black">{deltaPct === null ? "n.d." : quote.otaId === "booking" ? "Base" : `${deltaPct > 0 ? "+" : ""}${deltaPct.toFixed(1)}%`}</td><td className="p-2">{quote.refund} · {quote.board} · {quote.audience} · {quote.taxes}{quote.comparisonWarning && <span className="block mt-1 font-black text-amber-700">{quote.comparisonWarning}</span>}</td></tr>)}
            {!publishedComparisonSamples.length && !rateDetailRows.length && <tr><td colSpan={7} className="p-3 text-[#50627F]">Nessun preventivo datato registrato. Aggiungine uno qui sotto per popolare la tabella.</td></tr>}
          </tbody></table></div>
          {publishedMonthlySamples.length > 0 && <div className="mt-4 overflow-x-auto rounded-xl border border-[#E5DDF1]">
            <table className="min-w-[1000px] w-full border-collapse text-[11px]"><thead className="bg-[#23124A] text-white"><tr><th className="p-2 text-left">Mese / date campione</th><th className="p-2 text-left">Sito diretto · range tipologie</th><th className="p-2 text-left">Booking · range tipologie</th><th className="p-2 text-left">Altri portali · copertura parziale</th><th className="p-2 text-left">Delta omogeneo</th></tr></thead><tbody>{publishedMonthlySamples.map((sample) => <tr key={sample.month} className="border-t border-[#E5DDF1] align-top odd:bg-[#FBF9FF]"><th className="p-2 text-left text-[#23124A]">{sample.month}<span className="block font-medium text-[#50627F]">{sample.stay} · {sample.nights} notti</span></th><td className="p-2">{publishedRange(sample.direct)}</td><td className="p-2">{publishedRange(sample.booking)}</td><td className="p-2">{sample.other}</td><td className="p-2">{sample.delta}</td></tr>)}</tbody></table>
          </div>}
          {publishedMonthlySamples.length > 0 && <p className="mt-2 text-[10px] leading-4 text-[#50627F]">{activeAuditData.pricingAudit.method} I mesi senza prezzo verificato non provano chiusura stagionale; i delta richiedono preventivi omogenei.</p>}
          <div className="mt-4 grid grid-cols-2 gap-2 rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] p-4 md:grid-cols-4">
            <label className="text-[11px] font-black text-[#23124A]">OTA<select value={rateDraft.otaId} onChange={(event) => setRateDraft((previous) => ({ ...previous, otaId: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs">{activeAuditData.otaPresence.map((channel) => <option key={channel.id} value={channel.id}>{channel.platform}</option>)}</select></label>
            <label className="text-[11px] font-black text-[#23124A]">Data soggiorno<input type="date" value={rateDraft.stayDate} onChange={(event) => setRateDraft((previous) => ({ ...previous, stayDate: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Totale camera in EUR<input type="number" min="0.01" step="0.01" value={rateDraft.total || ""} onChange={(event) => setRateDraft((previous) => ({ ...previous, total: Number(event.target.value) }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Notti<input type="number" min="1" value={rateDraft.nights} onChange={(event) => setRateDraft((previous) => ({ ...previous, nights: Math.max(1, Number(event.target.value)) }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Tipologia camera<input value={rateDraft.roomType} onChange={(event) => setRateDraft((previous) => ({ ...previous, roomType: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">ID unità fisica verificata<input value={rateDraft.unitId || ""} onChange={(event) => setRateDraft((previous) => ({ ...previous, unitId: event.target.value }))} placeholder="Stesso ID solo se la camera è davvero identica" className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Ospiti<input type="number" min="1" value={rateDraft.guests} onChange={(event) => setRateDraft((previous) => ({ ...previous, guests: Math.max(1, Number(event.target.value)) }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Trattamento<select value={rateDraft.board} onChange={(event) => setRateDraft((previous) => ({ ...previous, board: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs"><option>Colazione inclusa</option><option>Solo camera</option><option>Altro / non chiaro</option></select></label>
            <label className="text-[11px] font-black text-[#23124A]">Cancellazione<select value={rateDraft.refund} onChange={(event) => setRateDraft((previous) => ({ ...previous, refund: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs"><option>Rimborsabile</option><option>Parzialmente rimborsabile</option><option>Non rimborsabile</option><option>Non chiaro</option></select></label>
            <label className="text-[11px] font-black text-[#23124A]">Pubblico<select value={rateDraft.audience} onChange={(event) => setRateDraft((previous) => ({ ...previous, audience: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs"><option>Pubblico senza login</option><option>Iscritto / loyalty</option><option>Solo app / mobile</option><option>Altro</option></select></label>
            <label className="text-[11px] font-black text-[#23124A]">Tasse<select value={rateDraft.taxes} onChange={(event) => setRateDraft((previous) => ({ ...previous, taxes: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs"><option>IVA inclusa, tassa di soggiorno esclusa</option><option>Tutte le imposte incluse</option><option>Imposte escluse</option><option>Non chiaro</option></select></label>
            <label className="text-[11px] font-black text-[#23124A]">Sconto / promo visibile<input value={rateDraft.promotion} onChange={(event) => setRateDraft((previous) => ({ ...previous, promotion: event.target.value }))} placeholder="Nessuno, Genius, mobile..." className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Evento / festività (se pertinente)<input value={rateDraft.eventTag} onChange={(event) => setRateDraft((previous) => ({ ...previous, eventTag: event.target.value }))} placeholder="Ferragosto, Pasqua, ponte..." className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">URL del preventivo<input type="url" value={rateDraft.sourceUrl} onChange={(event) => setRateDraft((previous) => ({ ...previous, sourceUrl: event.target.value }))} placeholder="https://..." className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
          </div>
          <div className="mt-2 grid grid-cols-1 gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 md:grid-cols-2">
            <label className="text-[11px] font-black text-[#23124A]">Tipo di sconto sulla tariffa osservata
              <select value={rateDraft.promotionKind ?? "Non verificata"} onChange={(event) => setRateDraft((previous) => ({ ...previous, promotionKind: event.target.value }))} className="mt-1 block w-full rounded-lg border border-amber-200 bg-white p-2 text-xs">
                <option>Non verificata</option><option>Nessuna visibile</option><option>Last minute</option><option>Early booking</option><option>Genius</option><option>Member / loyalty</option><option>Mobile / app</option><option>Coupon</option><option>Pacchetto</option><option>Altra promozione</option>
              </select>
            </label>
            <label className="text-[11px] font-black text-[#23124A]">Prezzo barrato originale in EUR (solo se visibile)
              <input type="number" min="0" step="0.01" value={rateDraft.originalTotal || ""} onChange={(event) => setRateDraft((previous) => ({ ...previous, originalTotal: Number(event.target.value) }))} className="mt-1 block w-full rounded-lg border border-amber-200 bg-white p-2 text-xs" />
            </label>
            <p className="text-[10px] leading-4 text-amber-900 md:col-span-2">Il portale deve attribuire lo sconto a questa struttura e a queste date. Non confondere campagne generiche del portale con una promozione dell'hotel; se il prezzo barrato non compare, lascia vuoto.</p>
          </div>
          <button type="button" onClick={addRateQuote} className="mt-3 rounded-xl bg-[#23124A] px-4 py-2 text-xs font-black text-white">Aggiungi manualmente prezzo e promozione osservati</button>
          <label className="mt-4 block text-[11px] font-black text-[#23124A]">Confronta condizioni omogenee
            <select value={activeCohort} onChange={(event) => setSelectedRateCohort(event.target.value)} className="mt-1 block w-full rounded-xl border border-[#E0D7EC] bg-white p-2.5 text-xs font-medium"><option value="">Seleziona camera e piano tariffario</option>{cohortOptions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          </label>
          {rateQuotes.some((quote) => quote.origin === "pilot" && ["booking", "agoda", "airbnb", "vrbo", "expedia", "hotels", "travelocity", "trip", "priceline"].includes(quote.otaId)) && <p className="mt-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[10px] font-semibold text-emerald-900"><b>{rateQuotes.filter((quote) => quote.origin === "pilot" && ["booking", "agoda", "airbnb", "vrbo", "expedia", "hotels", "travelocity", "trip", "priceline"].includes(quote.otaId)).length} righe tariffarie automatiche rilevate su {new Set(rateQuotes.filter((quote) => quote.origin === "pilot" && ["booking", "agoda", "airbnb", "vrbo", "expedia", "hotels", "travelocity", "trip", "priceline"].includes(quote.otaId)).map((quote) => quote.otaId)).size} canale/i</b>. I valori non validati restano visibili ma non alimentano il delta. I campioni restano separati per canale; il delta compare soltanto quando è confermata la stessa unità fisica con condizioni omogenee.</p>}
          <div className="mt-3 overflow-x-auto rounded-xl border border-[#E5DDF1]"><table className="min-w-[1240px] w-full border-collapse text-[11px]"><thead className="bg-[#23124A] text-white"><tr><th className="p-2 text-left">Mese soggiorno</th>{activeAuditData.otaPresence.map((channel) => <th key={channel.id} className="p-2 text-left">{channel.platform}</th>)}</tr></thead><tbody>{rateMonths.map((month) => <tr key={month} className="border-t border-[#E5DDF1] odd:bg-[#FBF9FF]"><th className="p-2 text-left text-[#23124A]">{new Date(`${month}-01T12:00:00Z`).toLocaleDateString("it-IT", { month: "long", year: "numeric", timeZone: "UTC" })}</th>{activeAuditData.otaPresence.map((channel) => { const cell = monthlyRateCell(rateQuotes, month, channel.id); return <td key={channel.id} className="p-2 text-[#23124A]">{cell.average === null ? <span className="text-[10px] leading-4 text-[#50627F]">{pilotCoverageSummary(browserPilotResult, month, channel.id) || "—"}</span> : <><b>€{cell.average.toFixed(2)}</b><span className="block text-[10px] text-[#50627F]">{cell.count} rilevazione/i · {cell.verified} validate{cell.deltaPct === null ? " · Δ n.d." : ` · Δ ${cell.deltaPct > 0 ? "+" : ""}${cell.deltaPct.toFixed(1)}% (${cell.matched})`}</span></>}</td>; })}</tr>)}</tbody></table></div>
          <p className="mt-2 text-[10px] text-[#50627F]">Δ = scostamento medio percentuale rispetto a Booking su date coincidenti e rilevate nello stesso giorno; (n) = confronti abbinati. Una sola data non rappresenta l'intero mese. Nessun dato è stimato da listini stagionali o prezzi di altre strutture. Focus: Pasqua, ponti, 2 giugno, Ferragosto, Natale/Capodanno e principali eventi locali solo se confermati.</p>
          <div className="mt-3 space-y-1">{[...rateQuotes].reverse().slice(0, 20).map((quote) => <div key={quote.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#E5DDF1] px-3 py-2 text-[11px] text-[#23124A]"><span><b>{activeAuditData.otaPresence.find((channel) => channel.id === quote.otaId)?.platform ?? quote.otaId}</b> · {quote.stayDate} · €{(quote.total / quote.nights).toFixed(2)}/notte · {quote.ratePlan || quote.refund} · {quote.origin === "pilot" ? (quote.pilotVerified === false ? "rilevazione automatica · da verificare" : "rilevazione automatica validata") : (quote.promotion || "inserimento manuale")}{quote.eventTag ? ` · ${quote.eventTag}` : ""} · rilevato {new Date(quote.observedAt).toLocaleString("it-IT")}</span><button type="button" onClick={() => removeRateQuote(quote.id)} className="rounded-md border border-rose-200 px-2 py-1 font-black text-rose-700">Elimina</button></div>)}</div>
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
            <b>Promozioni verificate su una tariffa futura:</b> {rateQuotes.filter((quote) => quote.stayDate >= todayLocalIso() && quote.promotionKind && !["Non verificata", "Nessuna visibile"].includes(quote.promotionKind)).length || "nessuna"}.
            {rateQuotes.filter((quote) => quote.stayDate >= todayLocalIso() && quote.promotionKind && !["Non verificata", "Nessuna visibile"].includes(quote.promotionKind)).slice(-6).map((quote) => <p key={`promo-${quote.id}`} className="mt-1">{activeAuditData.otaPresence.find((channel) => channel.id === quote.otaId)?.platform ?? quote.otaId} · {quote.stayDate} · {promotionSummary(quote)}</p>)}
          </div>
          <h3 className="mt-7 text-lg font-black text-[#23124A]">Visibilità del calendario futuro per OTA</h3>
          <p className="mt-1 text-xs leading-5 text-[#50627F]">Controlla date future su ogni canale. Registra separatamente prezzo non mostrato, data non selezionabile e verifica impedita. Una data senza prezzo può dipendere da camere esaurite, soggiorno minimo, chiusura delle vendite, finestra di prenotazione o errore tecnico: da sola non prova che la stagione sia chiusa.</p>
          <div className="mt-3 grid grid-cols-2 gap-2 rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] p-4 md:grid-cols-4">
            <label className="text-[11px] font-black text-[#23124A]">OTA<select value={availabilityDraft.otaId} onChange={(event) => setAvailabilityDraft((previous) => ({ ...previous, otaId: event.target.value }))} className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs">{activeAuditData.otaPresence.map((channel) => <option key={`probe-${channel.id}`} value={channel.id}>{channel.platform}</option>)}</select></label>
            <label className="text-[11px] font-black text-[#23124A]">Data soggiorno<input type="date" min={todayLocalIso()} value={availabilityDraft.stayDate} onChange={(event) => setAvailabilityDraft((previous) => ({ ...previous, stayDate: event.target.value }))} className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Esito<select value={availabilityDraft.status} onChange={(event) => setAvailabilityDraft((previous) => ({ ...previous, status: event.target.value as AvailabilityStatus }))} className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs">{Object.entries(AVAILABILITY_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
            <label className="text-[11px] font-black text-[#23124A]">Camera<input value={availabilityDraft.roomType} onChange={(event) => setAvailabilityDraft((previous) => ({ ...previous, roomType: event.target.value }))} className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Ospiti<input type="number" min="1" value={availabilityDraft.guests} onChange={(event) => setAvailabilityDraft((previous) => ({ ...previous, guests: Math.max(1, Number(event.target.value)) }))} className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">URL della ricerca<input type="url" value={availabilityDraft.sourceUrl} onChange={(event) => setAvailabilityDraft((previous) => ({ ...previous, sourceUrl: event.target.value }))} placeholder="https://..." className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="col-span-2 text-[11px] font-black text-[#23124A]">Nota sul messaggio mostrato<input value={availabilityDraft.note} onChange={(event) => setAvailabilityDraft((previous) => ({ ...previous, note: event.target.value }))} placeholder="Es. data non selezionabile fino al..." className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <button type="button" onClick={addAvailabilityProbe} className="col-span-2 rounded-xl bg-[#23124A] px-4 py-2 text-xs font-black text-white md:col-span-4">Registra verifica del calendario</button>
          </div>
          <div className="mt-3 overflow-x-auto rounded-xl border border-[#E5DDF1]">
            <table className="min-w-[1240px] w-full border-collapse text-[10px]">
              <thead className="bg-[#23124A] text-white"><tr><th className="p-2 text-left">Mese futuro</th>{activeAuditData.otaPresence.map((channel) => <th key={`coverage-head-${channel.id}`} className="p-2 text-left">{channel.platform}</th>)}</tr></thead>
              <tbody>{rateMonths.map((month) => <tr key={`coverage-${month}`} className="border-t border-[#E5DDF1] odd:bg-[#FBF9FF]">
                <th className="p-2 text-left text-[#23124A]">{new Date(`${month}-01T12:00:00Z`).toLocaleDateString("it-IT", { month: "long", year: "numeric", timeZone: "UTC" })}</th>
                {activeAuditData.otaPresence.map((channel) => <td key={`coverage-${month}-${channel.id}`} className="p-2 text-[#23124A]">{monthlyCoverageSummary(comparableQuotes, availabilityProbes, month, channel.id, browserPilotResult)}</td>)}
              </tr>)}</tbody>
            </table>
          </div>
          <p className="mt-2 text-[10px] leading-4 text-[#50627F]"><b>Come leggere la tabella:</b> “Tariffe rilevate” significa che Velora ha letto importi reali sulla scheda OTA per le date testate. “Camera e prezzo validati” significa che il parser ha associato l’importo alla relativa camera; il confronto tra OTA richiede ancora condizioni omogenee, tasse e stessa unità. “Prezzi rilevati · attribuzione da verificare” significa che gli importi sono presenti, ma non sono ancora collegati con sufficiente certezza a camera e piano tariffario. “Non verificato” compare solo quando quel mese/canale non è stato ancora controllato.</p>
          <div className="mt-3 space-y-1">{[...availabilityProbes].reverse().slice(0, 12).map((probe) => <div key={probe.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#E5DDF1] px-3 py-2 text-[11px] text-[#23124A]"><span><b>{activeAuditData.otaPresence.find((channel) => channel.id === probe.otaId)?.platform ?? probe.otaId}</b> · {probe.stayDate} · {AVAILABILITY_LABELS[probe.status]} · {probe.roomType}, {probe.guests} ospiti · rilevato {new Date(probe.observedAt).toLocaleString("it-IT")}{probe.note ? ` · ${probe.note}` : ""}</span><button type="button" onClick={() => removeAvailabilityProbe(probe.id)} className="rounded-md border border-rose-200 px-2 py-1 font-black text-rose-700">Elimina</button></div>)}</div>
          <h3 className="mt-6 text-lg font-black text-[#23124A]">Recensioni Google e qualità fotografica</h3>
          <p className="mt-1 text-xs leading-5 text-[#50627F]">Velora distingue temi ricorrenti positivi e negativi, segnalazioni isolate ed esempi concreti del campione pubblico. Il punteggio fotografico automatico usa soltanto segnali frontend osservabili; luce, styling e composizione restano esplicitamente separati finché non vengono valutati visivamente.</p>

          {browserPilotResult?.propertyId === activeAuditData.id && browserPilotResult.reputation?.status === "sampled" && <>
            <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-5">
              <div className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3"><div className="text-[9px] font-black uppercase tracking-wider text-[#8064A2]">Google</div><div className="mt-1 text-lg font-black text-[#23124A]">{browserPilotResult.reputation.rating ?? "n.d."}/5</div></div>
              <div className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3"><div className="text-[9px] font-black uppercase tracking-wider text-[#8064A2]">Recensioni visibili</div><div className="mt-1 text-lg font-black text-[#23124A]">{browserPilotResult.reputation.reviewCount ?? "n.d."}</div></div>
              <div className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3"><div className="text-[9px] font-black uppercase tracking-wider text-[#8064A2]">Campione testuale</div><div className="mt-1 text-lg font-black text-[#23124A]">{browserPilotResult.reputation.sampleSize ?? 0}</div></div>
              <div className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3"><div className="text-[9px] font-black uppercase tracking-wider text-[#8064A2]">Forze ricorrenti</div><div className="mt-1 text-lg font-black text-[#23124A]">{browserPilotResult.reputation.strengths?.length ?? 0}</div></div>
              <div className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3"><div className="text-[9px] font-black uppercase tracking-wider text-[#8064A2]">Criticità ricorrenti</div><div className="mt-1 text-lg font-black text-[#23124A]">{browserPilotResult.reputation.weaknesses?.length ?? 0}</div></div>
            </div>
            <div className="mt-2 rounded-xl border border-[#E5DDF1] bg-white px-3 py-2 text-[10px] leading-5 text-[#50627F]">
              <b className="text-[#23124A]">Copertura del campione:</b>{" "}
              {browserPilotResult.reputation.sampleSize ?? 0} recensioni testuali analizzate su {browserPilotResult.reputation.reviewCount ?? "n.d."} recensioni pubbliche
              {browserPilotResult.reputation.reviewCount && browserPilotResult.reputation.sampleSize !== undefined
                ? ` · ${Math.round(((browserPilotResult.reputation.sampleSize || 0) / browserPilotResult.reputation.reviewCount) * 100)}%`
                : ""}.
              {" "}Forze e criticità descrivono esclusivamente il campione effettivamente letto.
            </div>
          </>}

          <div className="mt-4 grid grid-cols-1 gap-x-4 gap-y-4 lg:grid-cols-2">
            {([
              ["audit-google-strengths", "Punti di forza ricorrenti"],
              ["audit-google-weaknesses", "Criticità ricorrenti"],
              ["audit-google-isolated", "Segnalazioni isolate da monitorare"],
              ["audit-google-actions", "Azioni operative dalle recensioni"],
            ] as const).map(([id, label]) => (
              <label key={id} className="flex min-w-0 flex-col text-[11px] font-black text-[#23124A]">
                <span className="mb-1.5 block min-h-[16px]">{label}</span>
                <textarea
                  value={answers[id]?.note ?? ""}
                  onChange={(event) => updateAnswer(id, { note: event.target.value })}
                  placeholder="Tema, ricorrenza, esempi concreti e fonte"
                  className="min-h-[138px] w-full resize-y rounded-xl border border-[#E0D7EC] bg-[#FBF9FF] px-3 py-2.5 text-xs font-medium leading-5 text-[#23124A] placeholder:text-slate-400"
                />
              </label>
            ))}

            <label className="flex min-w-0 flex-col text-[11px] font-black text-[#23124A]">
              <span className="mb-1.5 block min-h-[16px]">Temi e aspetti ricorrenti</span>
              <textarea
                value={answers["audit-google-keywords"]?.note ?? ""}
                onChange={(event) => updateAnswer("audit-google-keywords", { note: event.target.value })}
                placeholder="Temi positivi e negativi ricorrenti, ricorrenza ed espressioni rilevate"
                className="min-h-[190px] w-full resize-y rounded-xl border border-[#E0D7EC] bg-[#FBF9FF] px-3 py-2.5 text-xs font-medium leading-5 text-[#23124A] placeholder:text-slate-400"
              />
            </label>

            <div className="flex min-w-0 flex-col">
              <div className="mb-1.5 min-h-[16px] text-[11px] font-black text-[#23124A]">Indice fotografico frontend / 10</div>
              <div className="min-h-[190px] rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3">
                <div className="flex flex-wrap items-start gap-3">
                  <input
                    aria-label="Indice fotografico frontend su 10"
                    type="number"
                    min="0"
                    max="10"
                    step="0.1"
                    value={answers["audit-photo-score"]?.current || ""}
                    onChange={(event) => updateAnswer("audit-photo-score", { current: Number(event.target.value) })}
                    className="w-24 rounded-lg border border-[#E0D7EC] bg-white px-2.5 py-2 text-sm font-black text-[#23124A]"
                  />
                  {browserPilotResult?.photoAudit?.status === "sampled" && <div className="grid min-w-[280px] flex-1 grid-cols-3 gap-2 text-center text-[10px]">
                    <div className="rounded-lg bg-white p-2"><b className="block text-sm text-[#23124A]">{browserPilotResult.photoAudit.imageCount ?? 0}</b>immagini</div>
                    <div className="rounded-lg bg-white p-2"><b className="block text-sm text-[#23124A]">{browserPilotResult.photoAudit.highResolutionCount ?? 0}</b>alta ris.</div>
                    <div className="rounded-lg bg-white p-2"><b className="block text-sm text-[#23124A]">{browserPilotResult.photoAudit.altTextCount ?? 0}</b>alt utili</div>
                  </div>}
                </div>
                <textarea
                  value={answers["audit-photo-score"]?.note ?? ""}
                  onChange={(event) => updateAnswer("audit-photo-score", { note: event.target.value })}
                  placeholder="Copertura, risoluzione, metadati, gap e interventi consigliati"
                  className="mt-2.5 min-h-[118px] w-full resize-y rounded-xl border border-[#E0D7EC] bg-white px-3 py-2.5 text-xs font-medium leading-5 text-[#23124A] placeholder:text-slate-400"
                />
              </div>
            </div>
          </div>
          <p className="mt-3 text-[10px] text-[#50627F]">Il PDF salvato nella scheda Sant'Antonio fotografa l'analisi pubblicata; modifiche locali a queste note non lo rigenerano automaticamente.</p>
        </section>

        {visibleData.map((macro) => (
          <section
            key={`audit-${macro.id}`}
            className="overflow-hidden rounded-[2rem] border border-[#E5DDF1] bg-white shadow-[0_14px_40px_rgba(35,18,74,0.05)]"
          >
            <div className="border-b border-[#EFE9F7] bg-[#FBF9FF] px-5 py-4">
              <p className="text-[9px] font-black uppercase tracking-[0.2em] text-[#C8A96B]">
                Macro-area osservabile
              </p>
              <h3 className="mt-1 text-lg font-black text-[#23124A]">{macro.title}</h3>
            </div>

            <div className="space-y-5 p-4 md:p-5">
              {macro.categories.map((category) => (
                <div key={`audit-${category.id}`}>
                  <div className="mb-3 flex items-center gap-3">
                    <h4 className="text-xs font-black uppercase tracking-[0.12em] text-[#50627F]">
                      {category.title}
                    </h4>
                    <span className="h-px flex-1 bg-[#EFE9F7]" />
                    <span className="text-[10px] font-black text-[#50627F]">
                      {category.items.length} controlli
                    </span>
                  </div>

                  <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                    {category.items.map((item) => {
                      const answer = answers[item.id] ?? emptyAnswer();
                      const sources = getExternalAuditSources(item.id);
                      const activeStatus = AUDIT_STATUS_OPTIONS.find(
                        (option) => option.value === answer.auditStatus
                      );

                      return (
                        <article
                          key={`audit-${item.id}`}
                          className="rounded-2xl border border-[#E5DDF1] bg-white p-4 transition hover:border-emerald-300 hover:shadow-sm"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="text-[9px] font-black uppercase tracking-[0.16em] text-[#C8A96B]">
                                Riscontro esterno
                              </p>
                              <h5 className="mt-1 text-sm font-black leading-5 text-[#23124A]">
                                {item.text}
                              </h5>
                            </div>
                            <span
                              className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-black ${
                                activeStatus?.className ?? "border-slate-200 bg-slate-50 text-slate-500"
                              }`}
                            >
                              {activeStatus?.shortLabel ?? "Da verificare"}
                            </span>
                          </div>

                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {sources.map((source) => (
                              <span
                                key={`${item.id}-${source}`}
                                className="rounded-full bg-[#F3EEF9] px-2.5 py-1 text-[9px] font-black text-[#50627F]"
                              >
                                {source}
                              </span>
                            ))}
                          </div>

                          <div className="mt-3 grid grid-cols-2 gap-2">
                            {AUDIT_STATUS_OPTIONS.map((status) => {
                              const active = answer.auditStatus === status.value;
                              return (
                                <button
                                  key={`${item.id}-${status.value}`}
                                  type="button"
                                  aria-pressed={active}
                                  onClick={() => updateAuditStatus(item.id, status.value)}
                                  className={`rounded-xl border px-2.5 py-2 text-[10px] font-black transition ${
                                    active
                                      ? status.className
                                      : "border-[#E5DDF1] bg-white text-[#50627F] hover:bg-[#FBF9FF]"
                                  }`}
                                >
                                  {status.shortLabel}
                                </button>
                              );
                            })}
                          </div>

                          <label className="mt-3 block">
                            <span className="text-[9px] font-black uppercase tracking-[0.14em] text-slate-500">
                              Prova concreta: URL, pagina o nota
                            </span>
                            <textarea
                              value={answer.note}
                              onChange={(event) => updateAnswer(item.id, { note: event.target.value })}
                              placeholder="Es. pagina camere, URL Booking, screenshot, esito del test..."
                              className="mt-1.5 min-h-[64px] w-full resize-y rounded-xl border border-[#E0D7EC] bg-[#FBF9FF] px-3 py-2 text-xs font-medium leading-5 text-[#23124A] outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10"
                            />
                          </label>
                        </article>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}

        {!visibleData.length && (
          <div className="rounded-[2rem] border border-dashed border-[#CFC1DF] bg-white p-8 text-center text-sm font-semibold text-[#50627F]">
            Nessuna voce corrisponde ai filtri selezionati.
          </div>
        )}
      </section>
    );
  }

  function renderQuickSections(
    data: AssessmentMacro[],
    startingNumber: number,
    isDeepDive = false
  ) {
    const numberById = new Map(
      flattenItems(data).map((row, index) => [row.item.id, startingNumber + index + 1])
    );

    return data.map((macro) => (
      <section key={`${isDeepDive ? "deep" : "core"}-${macro.id}`} className="flex flex-col gap-4">
        <div className={`rounded-[1.5rem] border px-5 py-4 ${isDeepDive ? "border-[#D8C8A5] bg-[#FFFBF2]" : "border-[#E5DDF1] bg-[#FBF9FF]"}`}>
          <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[#C8A96B]">
            {isDeepDive ? "Area di approfondimento" : "Area principale"}
          </p>
          <h3 className="mt-1 text-lg font-black text-[#23124A]">{macro.title}</h3>
        </div>

        {macro.categories.map((category) => (
          <div
            key={`${isDeepDive ? "deep" : "core"}-${category.id}`}
            className="overflow-hidden rounded-[2rem] border border-[#E5DDF1] bg-white shadow-[0_18px_50px_rgba(35,18,74,0.05)]"
          >
            <div className="border-b border-[#EFE9F7] bg-[#FBF9FF] px-6 py-5">
              <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[#C8A96B]">
                    Reparto selezionato
                  </p>
                  <h4 className="mt-1 text-xl font-black text-[#23124A]">
                    {category.title}
                  </h4>
                </div>
                <span className="w-fit rounded-full bg-white px-3 py-1 text-xs font-black text-[#50627F] ring-1 ring-[#E5DDF1]">
                  {category.items.length} {category.items.length === 1 ? "domanda" : "domande"}
                </span>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 p-4">
              {category.items.map((item) =>
                renderQuestionCard(
                  item,
                  numberById.get(item.id),
                  isDeepDive,
                  macro,
                  category
                )
              )}
            </div>
          </div>
        ))}
      </section>
    ));
  }

  if (showStructures) {
    return (
      <main className="min-h-screen bg-[#F7F4FB] px-4 py-8 text-[#23124A] md:px-6">
        <div className="mx-auto max-w-[1300px]">
          <section className="rounded-[2rem] border border-[#E5DDF1] bg-white p-6 shadow-[0_18px_50px_rgba(35,18,74,0.06)] md:p-8">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[#C8A96B]">Archivio consulenziale</p>
                <h1 className="mt-2 text-3xl font-black">Strutture analizzate</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[#50627F]">
                  Questa è la home dell'audit: da qui apri volontariamente una struttura, avvii una nuova analisi o consulti i report. Rientrando in Velora tornerai sempre a questo elenco.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <label className="inline-flex cursor-pointer items-center rounded-xl bg-[#23124A] px-5 py-3 text-sm font-black text-white hover:bg-[#372368]">
                  Importa audit JSON
                  <input type="file" accept=".json,application/json" onChange={importAuditDataset} className="sr-only" />
                </label>
                {activeStructureId && <button type="button" onClick={() => { setShowStructures(false); window.scrollTo({ top: 0, behavior: "auto" }); }} className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] px-5 py-3 text-sm font-black hover:bg-[#F3EEF9]">
                  Torna alla scheda aperta
                </button>}
              </div>
            </div>
          </section>
          <section className="mt-5 rounded-[2rem] border border-[#C8A96B]/50 bg-[#FFFDF7] p-6 shadow-sm md:p-7">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="max-w-3xl">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[#C8A96B]">Nuovo audit automatico</p>
                <h2 className="mt-1 text-2xl font-black text-[#23124A]">Parti dal sito ufficiale</h2>
                <p className="mt-2 text-sm leading-6 text-[#50627F]">
                  Velora online invia il sito all'agente gratuito sul tuo PC. Il database Excel, quando contiene la struttura, accelera il riconoscimento ma non e' obbligatorio: per strutture esterne al database Velora ricostruisce l'identita' dal sito ufficiale e usa quei segnali per cercare e verificare le schede OTA. OTA, recensioni e prezzi futuri restano separati finche' non vengono verificati.
                </p>
              </div>
              <div className={"rounded-full px-3 py-1.5 text-xs font-black " + (localPilotToken ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-800")}>
                {localPilotToken ? "Agente locale collegato" : "Agente locale da collegare"}
              </div>
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-6">
              <label className="lg:col-span-2">
                <span className="text-[11px] font-black text-[#23124A]">Nome struttura <span className="font-semibold text-[#718096]">(opzionale)</span></span>
                <input value={autoAuditDraft.name} onChange={(event) => setAutoAuditDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Es. Hotel Aurora" className="mt-1.5 h-11 w-full rounded-xl border border-[#E0D7EC] bg-white px-3 text-sm font-semibold outline-none focus:border-[#23124A]" />
              </label>
              <label className="lg:col-span-4">
                <span className="text-[11px] font-black text-[#23124A]">Sito ufficiale *</span>
                <input value={autoAuditDraft.website} onChange={(event) => setAutoAuditDraft((current) => ({ ...current, website: event.target.value }))} placeholder="https://www.struttura.it" className="mt-1.5 h-11 w-full rounded-xl border border-[#E0D7EC] bg-white px-3 text-sm font-semibold outline-none focus:border-[#23124A]" />
              </label>
              <label className="lg:col-span-2">
                <span className="text-[11px] font-black text-[#23124A]">Citta' <span className="font-semibold text-[#718096]">(opzionale)</span></span>
                <input value={autoAuditDraft.city} onChange={(event) => setAutoAuditDraft((current) => ({ ...current, city: event.target.value }))} className="mt-1.5 h-11 w-full rounded-xl border border-[#E0D7EC] bg-white px-3 text-sm font-semibold outline-none focus:border-[#23124A]" />
              </label>
              <label>
                <span className="text-[11px] font-black text-[#23124A]">Provincia</span>
                <input value={autoAuditDraft.province} maxLength={2} onChange={(event) => setAutoAuditDraft((current) => ({ ...current, province: event.target.value.toUpperCase() }))} placeholder="LE" className="mt-1.5 h-11 w-full rounded-xl border border-[#E0D7EC] bg-white px-3 text-sm font-semibold uppercase outline-none focus:border-[#23124A]" />
              </label>
              <label>
                <span className="text-[11px] font-black text-[#23124A]">Camere / unita'</span>
                <input value={autoAuditDraft.rooms} inputMode="numeric" onChange={(event) => setAutoAuditDraft((current) => ({ ...current, rooms: event.target.value.replace(/\D/g, "").slice(0, 4) }))} placeholder="Es. 12" className="mt-1.5 h-11 w-full rounded-xl border border-[#E0D7EC] bg-white px-3 text-sm font-semibold outline-none focus:border-[#23124A]" />
              </label>
              <div className="flex items-end gap-2 lg:col-span-2">
                {!localPilotToken && <button type="button" onClick={() => void connectLocalAgent(false)} className="h-11 rounded-xl border border-[#C8A96B] bg-white px-4 text-xs font-black text-[#23124A] hover:bg-[#FFF8E8]">Collega agente</button>}
                <button type="button" disabled={autoAuditRunning || !autoAuditDraft.website.trim()} onClick={() => void startAutomaticAudit()} className="h-11 flex-1 rounded-xl bg-[#23124A] px-5 text-sm font-black text-white hover:bg-[#372368] disabled:cursor-not-allowed disabled:opacity-50">
                  {autoAuditRunning ? "Analisi in corso..." : "Analizza struttura"}
                </button>
              </div>
            </div>
            {(autoAuditMessage || localPilotMessage) && <p className="mt-3 rounded-xl bg-white px-4 py-3 text-xs font-semibold leading-5 text-[#50627F] ring-1 ring-[#E5DDF1]" role="status">{autoAuditMessage || localPilotMessage}</p>}
          </section>

          <div className="mt-5 grid gap-4">
            {structures.map((structure) => (
              <article key={structure.id} className="rounded-[1.7rem] border border-[#E5DDF1] bg-white p-5 shadow-sm md:p-6">
                <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
                  <div className="min-w-0">
                    <p className="text-[10px] font-black uppercase tracking-[0.18em] text-[#C8A96B]">
                      {structure.assessmentMode === "web-audit" ? "Audit Web & Frontend" : "Analisi Velora"}
                    </p>
                    <h2 className="mt-1 text-xl font-black">{structure.name}</h2>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs font-bold text-[#50627F]">
                      <span className="rounded-full bg-[#F3EEF9] px-3 py-1.5">{structure.city || "Città da inserire"} {structure.province ? `(${structure.province})` : ""}</span>
                      <span className="rounded-full bg-[#F3EEF9] px-3 py-1.5">{structure.rooms || "—"} camere / unità</span>
                      <span className="rounded-full bg-[#F3EEF9] px-3 py-1.5">{Object.keys(structure.answers).length} voci compilate</span>
                      {structure.auditedAt && <span className="rounded-full bg-[#F3EEF9] px-3 py-1.5">Report {new Date(`${structure.auditedAt}T12:00:00`).toLocaleDateString("it-IT")}</span>}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" onClick={() => openStructure(structure)} className="rounded-xl bg-[#23124A] px-5 py-3 text-sm font-black text-white hover:bg-[#372368]">
                      Apri analisi
                    </button>
                    {structure.reportPath && <button type="button" onClick={() => openStoredReport(structure)} className="rounded-xl border border-[#C8A96B] bg-[#FFF8E8] px-5 py-3 text-sm font-black hover:bg-[#FFF1CF]">
                      Apri report PDF
                    </button>}
                    {structure.id === santantonioAudit.id && <button type="button" onClick={restoreOriginalAudit} className="rounded-xl border border-[#E5DDF1] px-5 py-3 text-sm font-black hover:bg-[#FBF9FF]">
                      Ripristina audit originale
                    </button>}
                    {structure.website && <a href={structure.website} target="_blank" rel="noreferrer" className="rounded-xl border border-[#E5DDF1] px-5 py-3 text-sm font-black hover:bg-[#FBF9FF]">Sito web</a>}
                    <button
                      type="button"
                      onClick={() => deleteStructure(structure)}
                      title={`Elimina ${structure.name}`}
                      aria-label={`Elimina ${structure.name}`}
                      className="inline-flex h-11 w-11 items-center justify-center rounded-xl border border-red-200 bg-red-50 text-red-700 transition hover:bg-red-100"
                    >
                      <svg viewBox="0 0 24 24" aria-hidden="true" className="h-5 w-5 fill-none stroke-current" strokeWidth="1.8">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5" />
                      </svg>
                    </button>
                  </div>
                </div>
              </article>
            ))}
          </div>
          <p className="mt-5 text-xs leading-5 text-[#50627F]">Le modifiche e le nuove strutture restano salvate in questo browser. Per l&apos;audit automatico il software online usa l&apos;agente gratuito sullo stesso PC; i dati non verificabili restano marcati come tali.</p>
        </div>
      </main>
    );
  }

  if (isCustomizingInterview) {
    const normalizedCustomizerSearch = customizerSearch.trim().toLowerCase();
    const selectedDraftSet = new Set(customQuickDraftIds);

    return (
      <main className="min-h-screen bg-[#F7F4FB] px-4 py-5 text-[#23124A] md:px-6">
        <div className="mx-auto flex max-w-[1600px] flex-col gap-5">
          <section className="rounded-[2rem] border border-[#E5DDF1] bg-white p-5 shadow-[0_18px_50px_rgba(35,18,74,0.07)] md:p-6">
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="max-w-4xl">
                <p className="text-[11px] font-black uppercase tracking-[0.24em] text-[#C8A96B]">
                  Configuratore consulenziale
                </p>
                <h1 className="mt-2 text-3xl font-black tracking-tight text-[#23124A] md:text-4xl">
                  Personalizza intervista consulenziale
                </h1>
                <p className="mt-3 max-w-3xl text-sm leading-6 text-[#50627F]">
                  Seleziona soltanto le voci utili per la struttura che visiterai. Ogni macro-area
                  è organizzata in un box compatto per consentire una consultazione e una scelta rapide.
                </p>
                <div className="mt-4">
                  <GuideToggle
                    enabled={guideEnabled}
                    onToggle={() => setGuideEnabled((current) => !current)}
                  />
                </div>
              </div>

              <div className="grid min-w-[280px] grid-cols-2 gap-3">
                <div className="rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.18em] text-[#C8A96B]">
                    Selezionate
                  </p>
                  <p className="mt-1 text-3xl font-black text-[#23124A]">
                    {customQuickDraftIds.length}
                  </p>
                </div>
                <div className="rounded-2xl border border-[#E5DDF1] bg-white p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.18em] text-[#C8A96B]">
                    Disponibili
                  </p>
                  <p className="mt-1 text-3xl font-black text-[#23124A]">
                    {flattenItems(ASSESSMENT_DATA).length}
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_auto_auto]">
              <label className="flex flex-col gap-2">
                <FieldLabel>Cerca voce o reparto</FieldLabel>
                <input
                  value={customizerSearch}
                  onChange={(event) => setCustomizerSearch(event.target.value)}
                  placeholder="Es. pricing, Booking, foto, qualità..."
                  className="h-11 rounded-2xl border border-[#E0D7EC] bg-[#FBF9FF] px-4 text-sm font-semibold text-[#23124A] outline-none transition placeholder:text-slate-400 focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
                />
              </label>

              <button
                type="button"
                onClick={() => setCustomQuickDraftIds(DEFAULT_CUSTOM_QUICK_ITEM_IDS)}
                className="self-end rounded-2xl border border-[#C8A96B] bg-[#FFF8E8] px-4 py-3 text-xs font-black text-[#23124A] transition hover:bg-[#F9EAC8]"
              >
                Ripristina modello 30 + 20
              </button>
              <button
                type="button"
                onClick={() => setCustomQuickDraftIds([])}
                className="self-end rounded-2xl border border-[#E5DDF1] bg-white px-4 py-3 text-xs font-black text-[#50627F] transition hover:bg-[#FBF9FF]"
              >
                Deseleziona tutto
              </button>
            </div>
          </section>

          <div className="flex flex-col gap-3">
            {ASSESSMENT_DATA.map((macro) => {
              const macroItemIds = flattenItems([macro]).map((row) => row.item.id);
              const selectedInMacro = macroItemIds.filter((id) => selectedDraftSet.has(id)).length;
              const allMacroSelected =
                macroItemIds.length > 0 && selectedInMacro === macroItemIds.length;
              const visibleCategories = macro.categories
                .map((category) => ({
                  ...category,
                  items: category.items.filter((item) => {
                    if (!normalizedCustomizerSearch) return true;
                    return `${macro.title} ${category.title} ${item.text}`
                      .toLowerCase()
                      .includes(normalizedCustomizerSearch);
                  }),
                }))
                .filter((category) => category.items.length > 0);

              if (!visibleCategories.length) return null;

              return (
                <section
                  key={`customizer-${macro.id}`}
                  className="overflow-hidden rounded-[1.75rem] border border-[#E5DDF1] bg-white shadow-[0_12px_34px_rgba(35,18,74,0.045)]"
                >
                  <div className="flex flex-col gap-2 border-b border-[#EFE9F7] bg-[#FBF9FF] px-4 py-3 md:flex-row md:items-center md:justify-between">
                    <div>
                      <p className="text-[9px] font-black uppercase tracking-[0.2em] text-[#C8A96B]">
                        Macro-area
                      </p>
                      <h2 className="mt-0.5 text-sm font-black text-[#23124A] md:text-base">
                        {macro.title}
                      </h2>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="rounded-full bg-white px-3 py-1.5 text-[11px] font-black text-[#50627F] ring-1 ring-[#E5DDF1]">
                        {selectedInMacro}/{macroItemIds.length} selezionate
                      </span>
                      <button
                        type="button"
                        onClick={() => toggleCustomMacro(macro)}
                        className="rounded-xl border border-[#C8A96B]/60 bg-white px-3 py-1.5 text-[10px] font-black text-[#23124A] transition hover:bg-[#FFF8E8]"
                      >
                        {allMacroSelected ? "Deseleziona area" : "Seleziona area"}
                      </button>
                    </div>
                  </div>

                  <div className="space-y-3 p-3 md:p-4">
                    {visibleCategories.map((category) => (
                      <div key={`customizer-${category.id}`}>
                        <div className="mb-1.5 flex items-center gap-3">
                          <h3 className="text-[10px] font-black uppercase tracking-[0.1em] text-[#50627F]">
                            {category.title}
                          </h3>
                          <span className="h-px flex-1 bg-[#EFE9F7]" />
                        </div>
                        <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-6">
                          {category.items.map((item) => {
                            const selected = selectedDraftSet.has(item.id);
                            return (
                              <label
                                key={`customizer-${item.id}`}
                                title={guideEnabled ? getGuideText(macro, category, item) : undefined}
                                className={`flex min-h-[42px] items-start gap-2 rounded-lg border px-2.5 py-2 transition ${
                                  guideEnabled ? "cursor-help" : "cursor-pointer"
                                } ${
                                  selected
                                    ? "border-[#C8A96B] bg-[#FFF8E8] shadow-sm"
                                    : "border-[#E8E2F0] bg-white hover:border-[#CFC1DF] hover:bg-[#FBF9FF]"
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  checked={selected}
                                  onChange={() => toggleCustomQuestion(item.id)}
                                  className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border-[#CFC1DF] accent-[#23124A]"
                                />
                                <span
                                  className={`text-[11px] font-semibold leading-[1.25] text-[#23124A] ${
                                    guideEnabled
                                      ? "underline decoration-emerald-500/70 decoration-dotted underline-offset-2"
                                      : ""
                                  }`}
                                >
                                  {item.text}
                                </span>
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              );
            })}
          </div>

          <section className="sticky bottom-4 z-20 rounded-[1.5rem] border border-[#D8C8A5] bg-white/95 p-4 shadow-[0_18px_55px_rgba(35,18,74,0.16)] backdrop-blur md:px-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <p className="text-sm font-black text-[#23124A]">
                  {customQuickDraftIds.length} domande formeranno la nuova Analisi rapida
                </p>
                <p className="mt-1 text-xs font-semibold text-[#50627F]">
                  La conferma sostituisce il modello rapido corrente, senza cancellare le risposte già inserite.
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  onClick={() => setIsCustomizingInterview(false)}
                  className="rounded-xl border border-[#E5DDF1] bg-white px-5 py-3 text-sm font-black text-[#50627F] transition hover:bg-[#FBF9FF]"
                >
                  Annulla
                </button>
                <button
                  type="button"
                  onClick={confirmCustomInterview}
                  className="rounded-xl bg-[#23124A] px-6 py-3 text-sm font-black text-white shadow-sm transition hover:bg-[#2F1A63]"
                >
                  Conferma e apri Analisi rapida
                </button>
              </div>
            </div>
          </section>
        </div>
      </main>
    );
  }


  return (
    <main className="min-h-screen bg-[#F7F4FB] px-6 py-6 text-[#23124A]">
      <div className="mx-auto flex max-w-[1500px] flex-col gap-6">
        <section className="flex flex-col gap-3 rounded-[1.5rem] border border-[#E5DDF1] bg-white px-5 py-4 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[#C8A96B]">Archivio consulenziale</p>
            <p className="mt-1 text-sm font-bold text-[#23124A]">
              {activeStructureId ? `Scheda aperta: ${ownerInfo.propertyName || "struttura senza nome"}` : `${structures.length} strutture in archivio`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {activeStructureId && structures.find((item) => item.id === activeStructureId)?.reportPath && (
              <button type="button" onClick={() => openStoredReport(structures.find((item) => item.id === activeStructureId)!)} className="rounded-xl border border-[#C8A96B] bg-[#FFF8E8] px-5 py-3 text-sm font-black hover:bg-[#FFF1CF]">
                Apri report PDF originale
              </button>
            )}
            <button type="button" onClick={openStructuresHome} className="rounded-xl bg-[#23124A] px-5 py-3 text-sm font-black text-white hover:bg-[#372368]">
              Strutture analizzate
            </button>
          </div>
        </section>
        <section className="rounded-[2rem] border border-[#E5DDF1] bg-white p-5 shadow-[0_18px_50px_rgba(35,18,74,0.06)]">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
            <div>
              <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[#C8A96B]">
                Formato di analisi
              </p>
              <h2 className="mt-1 text-xl font-black text-[#23124A]">
                Scegli il livello di approfondimento
              </h2>
              <p className="mt-1 text-sm text-[#50627F]">
                Le risposte restano collegate: puoi passare da un formato all’altro senza perdere dati.
              </p>
              <div className="mt-3">
                <GuideToggle
                  enabled={guideEnabled}
                  onToggle={() => setGuideEnabled((current) => !current)}
                />
              </div>
            </div>

            <div className="grid w-full grid-cols-1 gap-3 md:grid-cols-2 xl:w-auto xl:min-w-[1180px] xl:grid-cols-4">
              <button
                type="button"
                aria-pressed={assessmentMode === "full"}
                onClick={() => switchAssessmentMode("full")}
                className={`rounded-2xl border px-5 py-4 text-left transition ${
                  assessmentMode === "full"
                    ? "border-[#23124A] bg-[#23124A] text-white shadow-sm"
                    : "border-[#E5DDF1] bg-[#FBF9FF] text-[#23124A] hover:bg-[#F3EEF9]"
                }`}
              >
                <span className="block text-sm font-black">Analisi completa</span>
                <span className={`mt-1 block text-xs font-semibold ${assessmentMode === "full" ? "text-white/75" : "text-[#50627F]"}`}>
                  Tutte le {flattenItems(ASSESSMENT_DATA).length} voci disponibili
                </span>
              </button>

              <button
                type="button"
                aria-pressed={assessmentMode === "web-audit"}
                onClick={() => switchAssessmentMode("web-audit")}
                className={`rounded-2xl border px-5 py-4 text-left transition ${
                  assessmentMode === "web-audit"
                    ? "border-emerald-500 bg-emerald-50 text-[#23124A] shadow-sm ring-2 ring-emerald-500/20"
                    : "border-emerald-200 bg-white text-[#23124A] hover:bg-emerald-50"
                }`}
              >
                <span className="flex items-center justify-between gap-3 text-sm font-black">
                  Audit Web &amp; Frontend
                  <span className="rounded-full bg-emerald-500 px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-white">
                    {flattenItems(EXTERNAL_WEB_AUDIT_DATA).length}
                  </span>
                </span>
                <span className="mt-1 block text-xs font-semibold text-[#50627F]">
                  Checklist autonoma su prove pubbliche
                </span>
              </button>

              <button
                type="button"
                aria-pressed={assessmentMode === "quick-hotel-bb"}
                onClick={() => switchAssessmentMode("quick-hotel-bb")}
                className={`rounded-2xl border px-5 py-4 text-left transition ${
                  assessmentMode === "quick-hotel-bb"
                    ? "border-[#C8A96B] bg-[#FFF8E8] text-[#23124A] shadow-sm ring-2 ring-[#C8A96B]/20"
                    : "border-[#C8A96B]/40 bg-white text-[#23124A] hover:bg-[#FFF8E8]"
                }`}
              >
                <span className="flex items-center justify-between gap-3 text-sm font-black">
                  Analisi rapida Hotel / B&amp;B
                  <span className="rounded-full bg-[#C8A96B] px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-[#23124A]">
                    {useCustomQuickSelection ? customQuickItemIds.length : "30 + 20"}
                  </span>
                </span>
                <span className="mt-1 block text-xs font-semibold text-[#50627F]">
                  {useCustomQuickSelection
                    ? `${customQuickItemIds.length} domande scelte dal consulente`
                    : "30 principali, più 20 approfondimenti opzionali"}
                </span>
              </button>

              <button
                type="button"
                onClick={openInterviewCustomizer}
                className={`rounded-2xl border px-5 py-4 text-left transition ${
                  useCustomQuickSelection
                    ? "border-[#23124A] bg-[#F3EEF9] text-[#23124A] shadow-sm ring-2 ring-[#23124A]/10"
                    : "border-[#E5DDF1] bg-white text-[#23124A] hover:bg-[#FBF9FF]"
                }`}
              >
                <span className="flex items-center justify-between gap-3 text-sm font-black">
                  Personalizza intervista
                  <span className="rounded-full bg-[#23124A] px-2.5 py-1 text-[10px] uppercase tracking-[0.12em] text-white">
                    Configura
                  </span>
                </span>
                <span className="mt-1 block text-xs font-semibold text-[#50627F]">
                  Scegli le voci adatte alla singola consulenza
                </span>
              </button>
            </div>
          </div>

          {isQuickHotelBb && (
            <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-[#E8D8B3] bg-[#FFFBF2] p-4 md:flex-row md:items-center md:justify-between">
              <p className="text-sm font-semibold text-[#50627F]">
                {useCustomQuickSelection
                  ? `Modello personalizzato attivo: ${customQuickItemIds.length} domande selezionate.`
                  : "Esporta il modello completo: 30 domande principali e 20 approfondimenti opzionali."}
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
                {useCustomQuickSelection && (
                  <button
                    type="button"
                    onClick={restorePresetQuickInterview}
                    className="rounded-xl border border-[#C8A96B]/60 bg-white px-4 py-2.5 text-xs font-black text-[#23124A] transition hover:bg-[#FFF8E8]"
                  >
                    Torna al modello 30 + 20
                  </button>
                )}
                <button
                  type="button"
                  onClick={generateQuickTemplatePdf}
                  className="rounded-xl bg-[#23124A] px-4 py-2.5 text-xs font-black text-white transition hover:bg-[#2F1A63]"
                >
                  Esporta modello PDF
                </button>
                <button
                  type="button"
                  onClick={exportQuickTemplateCsv}
                  className="rounded-xl border border-[#C8A96B]/60 bg-white px-4 py-2.5 text-xs font-black text-[#23124A] transition hover:bg-[#FFF8E8]"
                >
                  Esporta modello CSV
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="overflow-hidden rounded-[2rem] border border-[#E5DDF1] bg-white shadow-[0_18px_50px_rgba(35,18,74,0.08)]">
          <div className="border-b border-[#EFE9F7] bg-gradient-to-r from-white via-[#FBF8FF] to-[#F3EEF9] px-6 py-6">
            <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
              <div className="max-w-4xl">
                <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                  Velora Consulting
                </p>
                <h1 className="mt-3 text-4xl font-black tracking-tight text-[#23124A]">
                  {isWebAudit
                    ? "Audit Web & Frontend struttura ricettiva"
                    : isQuickHotelBb
                    ? useCustomQuickSelection
                      ? "Analisi rapida personalizzata"
                      : "Analisi rapida Hotel / B&B"
                    : "Autovalutazione struttura ricettiva"}
                </h1>
                <p className="mt-3 max-w-3xl text-sm leading-7 text-[#50627F]">
                  {isWebAudit
                    ? "Checklist di elementi verificabili autonomamente su sito, booking engine, OTA, Google, recensioni, social e test di contatto. Ogni valutazione deve essere accompagnata da un riscontro concreto."
                    : isQuickHotelBb
                    ? useCustomQuickSelection
                      ? `Percorso consulenziale dinamico con ${customQuickItemIds.length} domande selezionate per questa specifica intervista.`
                      : `Percorso guidato con 30 domande principali${showQuickDeepDive ? " e 20 approfondimenti aperti" : ""}, focalizzato su posizionamento, revenue, vendita, gestione delegata e qualità del servizio.`
                    : "Questionario diagnostico per capire i bisogni reali della struttura, le aree scoperte e dove Velora può generare valore concreto prima di proporre un intervento consulenziale o operativo."}
                </p>
              </div>

              <div
                className={`min-w-[260px] rounded-[1.5rem] border px-5 py-4 shadow-sm ${globalLabel.className}`}
              >
                <p className="text-[11px] font-black uppercase tracking-[0.18em]">
                  {isWebAudit ? "Indice criticità esterna" : "Indice opportunità"}
                </p>
                <div className="mt-2 flex items-end gap-2">
                  <span className="text-5xl font-black leading-none">{globalScore}</span>
                  <span className="pb-1 text-sm font-black">/100</span>
                </div>
                <p className="mt-2 text-sm font-bold">{globalLabel.label}</p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 p-6 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-[1.5rem] border border-[#E5DDF1] bg-[#FBF9FF] p-5">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[#C8A96B]">
                Compilazione
              </p>
              <p className="mt-2 text-3xl font-black text-[#23124A]">{progressPct}%</p>
              <div className="mt-3 h-2 overflow-hidden rounded-full bg-[#E8E0F2]">
                <div
                  className="h-full rounded-full bg-[#23124A]"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <p className="mt-2 text-xs font-semibold text-[#50627F]">
                {answeredCount} su {allRows.length} {isWebAudit ? "riscontri verificati" : "voci operative"}
              </p>
            </div>

            <div className="rounded-[1.5rem] border border-[#E5DDF1] bg-white p-5">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[#C8A96B]">
                Macro-aree
              </p>
              <p className="mt-2 text-3xl font-black text-[#23124A]">
                {assessmentData.length}
              </p>
              <p className="mt-2 text-xs font-semibold text-[#50627F]">
                {isWebAudit
                  ? "aree con evidenze osservabili"
                  : isQuickHotelBb
                    ? "settori essenziali selezionati"
                    : "mappa completa dei bisogni"}
              </p>
            </div>

            <div className="rounded-[1.5rem] border border-[#E5DDF1] bg-white p-5">
              <p className="text-xs font-black uppercase tracking-[0.18em] text-[#C8A96B]">
                Priorità alte
              </p>
              <p className="mt-2 text-3xl font-black text-[#23124A]">
                {topOpportunities.filter((row) => row.score >= 70).length}
              </p>
              <p className="mt-2 text-xs font-semibold text-[#50627F]">
                {isWebAudit ? "criticità pubbliche rilevate" : "prime aree da valutare"}
              </p>
            </div>

            <div className="flex flex-col justify-center gap-2 rounded-[1.5rem] border border-[#E5DDF1] bg-white p-5">
              <button
                type="button"
                onClick={generatePrintableReport}
                className="rounded-2xl bg-[#23124A] px-4 py-3 text-sm font-black text-white shadow-sm transition hover:bg-[#2F1A63]"
              >
                Genera report PDF
              </button>

              <button
                type="button"
                onClick={exportJson}
                className="rounded-2xl border border-[#23124A]/20 bg-white px-4 py-3 text-sm font-black text-[#23124A] transition hover:bg-slate-50"
              >
                Esporta JSON
              </button>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={exportCsv}
                  className="rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] px-4 py-3 text-sm font-black text-[#23124A] transition hover:bg-[#F3EEF9]"
                >
                  CSV
                </button>
                <button
                  type="button"
                  onClick={resetAssessment}
                  className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-black text-red-700 transition hover:bg-red-100"
                >
                  Azzera
                </button>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-[2rem] border border-[#E5DDF1] bg-white p-6 shadow-[0_18px_50px_rgba(35,18,74,0.06)]">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                Profilo preliminare
              </p>
              <h2 className="mt-2 text-2xl font-black text-[#23124A]">
                Dati struttura e referente
              </h2>
            </div>
            <p className="max-w-xl text-sm leading-6 text-[#50627F]">
              Questi dati servono a contestualizzare la diagnosi e saranno utili per report,
              sintesi consulenziale e futuro collegamento con Floppy.
            </p>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {[
              ["propertyName", "Nome struttura", "Es. Hotel Riviera"],
              ["ownerName", "Proprietario / referente", "Nome e cognome"],
              ["consultantName", "Consulente", "Nome e cognome del consulente"],
              ["location", "Località", "Città / zona"],
              ["city", "Città", "Es. Alberobello"],
              ["province", "Provincia", "Es. BA"],
              ["propertyType", "Tipologia", "Hotel, B&B, appartamenti..."],
              ["rooms", "Camere / unità", "Es. 18 camere"],
              ["channels", "Canali attivi", "Booking, Airbnb, sito..."],
              ["objective", "Obiettivo principale", "Es. più margine, più direct..."],
            ].map(([key, label, placeholder]) => (
              <label key={key} className="flex flex-col gap-2">
                <FieldLabel>{label}</FieldLabel>
                <input
                  value={ownerInfo[key as keyof OwnerInfo]}
                  onChange={(event) =>
                    updateOwnerInfo(key as keyof OwnerInfo, event.target.value)
                  }
                  placeholder={placeholder}
                  className="h-12 rounded-2xl border border-[#E0D7EC] bg-white px-4 text-sm font-semibold text-[#23124A] outline-none transition placeholder:text-slate-400 focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
                />
              </label>
            ))}
          </div>
        </section>

        {isWebAudit ? (
          renderExternalWebAudit()
        ) : isQuickHotelBb ? (
          <section className="flex flex-col gap-6">
            {useCustomQuickSelection ? (
              <>
                <div className="rounded-[2rem] border border-[#D8C8A5] bg-[#FFFBF2] p-6 shadow-[0_18px_50px_rgba(35,18,74,0.06)]">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="max-w-4xl">
                      <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                        Percorso consulenziale personalizzato
                      </p>
                      <h2 className="mt-2 text-2xl font-black text-[#23124A]">
                        {customQuickItemIds.length} domande selezionate per questa intervista
                      </h2>
                      <p className="mt-2 text-sm leading-7 text-[#50627F]">
                        Le domande sono ordinate per macro-area e reparto. Puoi modificare la
                        selezione in qualsiasi momento senza perdere le risposte già compilate.
                      </p>
                    </div>
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <button
                        type="button"
                        onClick={openInterviewCustomizer}
                        className="rounded-2xl bg-[#23124A] px-5 py-3 text-sm font-black text-white shadow-sm transition hover:bg-[#2F1A63]"
                      >
                        Modifica selezione
                      </button>
                      <span className="flex items-center justify-center rounded-full bg-[#C8A96B] px-4 py-2 text-xs font-black uppercase tracking-[0.14em] text-[#23124A]">
                        {assessmentData.length} macro-aree
                      </span>
                    </div>
                  </div>
                </div>

                {renderQuickSections(customQuickData, 0)}
              </>
            ) : (
              <>
            <div className="rounded-[2rem] border border-[#E5DDF1] bg-white p-6 shadow-[0_18px_50px_rgba(35,18,74,0.06)]">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-4xl">
                  <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                    Percorso guidato senza sidebar
                  </p>
                  <h2 className="mt-2 text-2xl font-black text-[#23124A]">
                    30 domande principali già selezionate
                  </h2>
                  <p className="mt-2 text-sm leading-7 text-[#50627F]">
                    Tutte le domande sono mostrate qui in sequenza. La selezione privilegia
                    posizionamento, vendita diretta, distribuzione, revenue, controllo del
                    gestore e qualità del servizio; la burocrazia è limitata alla verifica CIN/CIR.
                  </p>
                </div>
                <span className="w-fit rounded-full bg-[#23124A] px-4 py-2 text-xs font-black uppercase tracking-[0.14em] text-white">
                  Parte 1 · 30 domande
                </span>
              </div>
            </div>

            {renderQuickSections(QUICK_HOTEL_BB_CORE_DATA, 0)}

            <div className="rounded-[2rem] border border-[#D8C8A5] bg-[#FFFBF2] p-6 shadow-[0_18px_50px_rgba(35,18,74,0.05)]">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="max-w-3xl">
                  <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[#C8A96B]">
                    Secondo livello opzionale
                  </p>
                  <h2 className="mt-1 text-xl font-black text-[#23124A]">
                    Vuoi approfondire la diagnosi?
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-[#50627F]">
                    Apri altre 20 domande mirate su forecast, margini, pricing competitivo,
                    standard del brand, SLA del gestore e opportunità commerciali.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowQuickDeepDive((current) => !current)}
                  className="rounded-2xl bg-[#C8A96B] px-5 py-4 text-sm font-black text-[#23124A] shadow-sm transition hover:bg-[#D5B97F]"
                >
                  {showQuickDeepDive
                    ? "Nascondi le 20 domande di approfondimento"
                    : "Apri altre 20 domande di approfondimento"}
                </button>
              </div>
            </div>

            {showQuickDeepDive && (
              <div className="flex flex-col gap-6">
                <div className="rounded-[2rem] border border-[#D8C8A5] bg-white p-6">
                  <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                    Parte 2
                  </p>
                  <h2 className="mt-2 text-2xl font-black text-[#23124A]">
                    20 domande di approfondimento
                  </h2>
                  <p className="mt-2 text-sm leading-7 text-[#50627F]">
                    Questo secondo livello completa l’analisi senza modificare le risposte già date.
                  </p>
                </div>
                {renderQuickSections(QUICK_HOTEL_BB_DEEP_DIVE_DATA, 30, true)}
              </div>
            )}
              </>
            )}
          </section>
        ) : (
        <section className="grid grid-cols-1 gap-6 xl:grid-cols-[360px_1fr]">
          <aside className="h-fit rounded-[2rem] border border-[#E5DDF1] bg-white p-5 shadow-[0_18px_50px_rgba(35,18,74,0.06)] xl:sticky xl:top-6">
            <div>
              <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                Navigazione
              </p>
              <h2 className="mt-2 text-xl font-black text-[#23124A]">Macro-aree</h2>
            </div>

            <div className="mt-4 flex flex-col gap-3">
              <label className="flex flex-col gap-2">
                <FieldLabel>Cerca voce</FieldLabel>
                <input
                  value={searchTerm}
                  onChange={(event) => setSearchTerm(event.target.value)}
                  placeholder="Es. pricing, OTA, pulizie..."
                  className="h-11 rounded-2xl border border-[#E0D7EC] bg-[#FBF9FF] px-4 text-sm font-semibold text-[#23124A] outline-none transition placeholder:text-slate-400 focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
                />
              </label>

              <label className="flex items-center gap-3 rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] px-4 py-3 text-sm font-bold text-[#50627F]">
                <input
                  type="checkbox"
                  checked={showOnlyPriority}
                  onChange={(event) => setShowOnlyPriority(event.target.checked)}
                  className="h-4 w-4 rounded border-[#E0D7EC]"
                />
                Mostra solo priorità medie/alte
              </label>
            </div>

            <div className="mt-5 flex max-h-[62vh] flex-col gap-2 overflow-y-auto pr-1">
              {macroScores.map((macro) => {
                const label = getScoreLabel(macro.score);
                const active = macro.id === activeMacroId;

                return (
                  <button
                    key={macro.id}
                    type="button"
                    onClick={() => setActiveMacroId(macro.id)}
                    className={`rounded-2xl border p-4 text-left transition ${
                      active
                        ? "border-[#23124A] bg-[#23124A] text-white shadow-sm"
                        : "border-[#E5DDF1] bg-white text-[#23124A] hover:bg-[#FBF9FF]"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-sm font-black leading-5">{macro.title}</span>
                      <span
                        className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-black ring-1 ${
                          active
                            ? "bg-white/15 text-white ring-white/20"
                            : label.pillClassName
                        }`}
                      >
                        {macro.score}
                      </span>
                    </div>
                    <p
                      className={`mt-2 text-xs font-semibold ${
                        active ? "text-white/75" : "text-[#50627F]"
                      }`}
                    >
                      {macro.answeredItems}/{macro.totalItems} compilate
                    </p>
                  </button>
                );
              })}
            </div>
          </aside>

          <section className="flex min-w-0 flex-col gap-5">
            <div className="rounded-[2rem] border border-[#E5DDF1] bg-white p-6 shadow-[0_18px_50px_rgba(35,18,74,0.06)]">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                    Area attiva
                  </p>
                  <h2 className="mt-2 text-2xl font-black text-[#23124A]">
                    {activeMacro?.title}
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-7 text-[#50627F]">
                    Valuta ogni voce su tre dimensioni: importanza per la struttura,
                    livello attuale di presidio e fit Velora. Il punteggio cresce quando
                    una voce è importante, poco presidiata e adatta al nostro intervento.
                  </p>
                </div>

                <div className="rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] px-5 py-4">
                  <p className="text-[11px] font-black uppercase tracking-[0.18em] text-[#C8A96B]">
                    Score area
                  </p>
                  <p className="mt-1 text-3xl font-black text-[#23124A]">
                    {activeMacroScore?.score ?? 0}
                  </p>
                </div>
              </div>
            </div>

            {activeMacro?.categories.map((category) => {
              const normalizedSearch = searchTerm.trim().toLowerCase();

              const visibleItems = category.items.filter((item) => {
                const score = getItemScore(answers[item.id]);
                const matchesPriority = !showOnlyPriority || score >= 40;
                const matchesSearch =
                  !normalizedSearch ||
                  item.text.toLowerCase().includes(normalizedSearch) ||
                  category.title.toLowerCase().includes(normalizedSearch) ||
                  activeMacro.title.toLowerCase().includes(normalizedSearch);

                return matchesPriority && matchesSearch;
              });

              if (!visibleItems.length) return null;

              return (
                <div
                  key={category.id}
                  className="overflow-hidden rounded-[2rem] border border-[#E5DDF1] bg-white shadow-[0_18px_50px_rgba(35,18,74,0.05)]"
                >
                  <div className="border-b border-[#EFE9F7] bg-[#FBF9FF] px-6 py-5">
                    <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                      <div>
                        <p className="text-[11px] font-black uppercase tracking-[0.22em] text-[#C8A96B]">
                          Sottosezione
                        </p>
                        <h3 className="mt-1 text-xl font-black text-[#23124A]">
                          {category.title}
                        </h3>
                      </div>
                      <span className="w-fit rounded-full bg-white px-3 py-1 text-xs font-black text-[#50627F] ring-1 ring-[#E5DDF1]">
                        {visibleItems.length} voci
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-4 p-4">
                    {visibleItems.map((item) => {
                      const answer = answers[item.id] ?? emptyAnswer();
                      const score = getItemScore(answer);
                      const label = getScoreLabel(score);

                      return (
                        <article
                          key={item.id}
                          className="rounded-[1.5rem] border border-[#E5DDF1] bg-white p-5 transition hover:border-[#D4C7E6] hover:shadow-[0_14px_34px_rgba(35,18,74,0.06)]"
                        >
                          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                            <div className="min-w-0">
                              <p className="text-[11px] font-black uppercase tracking-[0.18em] text-[#C8A96B]">
                                Voce consulenziale
                              </p>
                              <h4
                                title={guideEnabled ? getGuideText(activeMacro, category, item) : undefined}
                                className={`mt-1 text-base font-black leading-6 text-[#23124A] ${
                                  guideEnabled
                                    ? "cursor-help underline decoration-emerald-500/70 decoration-dotted underline-offset-4"
                                    : ""
                                }`}
                              >
                                {item.text}
                              </h4>
                            </div>

                            <div
                              className={`flex w-fit shrink-0 items-center gap-3 rounded-2xl border px-4 py-3 ${label.className}`}
                            >
                              <span className="text-2xl font-black leading-none">{score}</span>
                              <span className="text-xs font-black uppercase tracking-[0.12em]">
                                {label.shortLabel}
                              </span>
                            </div>
                          </div>

                          <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
                            <label className="flex min-w-0 flex-col gap-2">
                              <FieldLabel>Importanza</FieldLabel>
                              <select
                                value={answer.importance}
                                onChange={(event) =>
                                  updateAnswer(item.id, {
                                    importance: Number(event.target.value),
                                  })
                                }
                                className="h-12 w-full rounded-2xl border border-[#E0D7EC] bg-[#FBF9FF] px-4 text-sm font-bold text-[#23124A] outline-none transition focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
                              >
                                {scoreOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </label>

                            <label className="flex min-w-0 flex-col gap-2">
                              <FieldLabel>Stato attuale</FieldLabel>
                              <select
                                value={answer.current}
                                onChange={(event) =>
                                  updateAnswer(item.id, { current: Number(event.target.value) })
                                }
                                className="h-12 w-full rounded-2xl border border-[#E0D7EC] bg-[#FBF9FF] px-4 text-sm font-bold text-[#23124A] outline-none transition focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
                              >
                                {currentOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </label>

                            <label className="flex min-w-0 flex-col gap-2">
                              <FieldLabel>Fit Velora</FieldLabel>
                              <select
                                value={answer.fit}
                                onChange={(event) =>
                                  updateAnswer(item.id, { fit: Number(event.target.value) })
                                }
                                className="h-12 w-full rounded-2xl border border-[#E0D7EC] bg-[#FBF9FF] px-4 text-sm font-bold text-[#23124A] outline-none transition focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
                              >
                                {scoreOptions.map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </label>
                          </div>

                          <label className="mt-4 flex flex-col gap-2">
                            <FieldLabel>Note, criticità, evidenze</FieldLabel>
                            <textarea
                              value={answer.note}
                              onChange={(event) =>
                                updateAnswer(item.id, { note: event.target.value })
                              }
                              placeholder="Scrivi qui ciò che emerge dal colloquio: problemi reali, evidenze, rischi, margini di miglioramento o motivi per cui Velora può/non può portare valore..."
                              className="min-h-[96px] w-full resize-y rounded-2xl border border-[#E0D7EC] bg-white px-4 py-3 text-sm font-medium leading-6 text-[#23124A] outline-none transition placeholder:text-slate-400 focus:border-[#23124A] focus:ring-4 focus:ring-[#23124A]/10"
                            />
                          </label>
                        </article>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </section>
        </section>
        )}

        <section className="rounded-[2rem] border border-[#E5DDF1] bg-white p-6 shadow-[0_18px_50px_rgba(35,18,74,0.06)]">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                Output consulenziale
              </p>
              <h2 className="mt-2 text-2xl font-black text-[#23124A]">
                {isWebAudit ? "Criticità visibili dall’esterno" : "Prime opportunità consulenziali"}
              </h2>
              <p className="mt-2 text-sm leading-6 text-[#50627F]">
                {isWebAudit
                  ? "Le voci non trovate o solo parzialmente riscontrate indicano i primi punti da approfondire con la struttura o correggere sui canali pubblici."
                  : "Le voci con punteggio più alto indicano dove Velora può generare più valore o dove serve una valutazione più approfondita."}
              </p>
            </div>

            <span className="w-fit rounded-full bg-[#FBF9FF] px-4 py-2 text-xs font-black uppercase tracking-[0.14em] text-[#50627F] ring-1 ring-[#E5DDF1]">
              Top 12
            </span>
          </div>

          <div className="mt-6 overflow-hidden rounded-3xl border border-[#E5DDF1]">
            <table className="w-full border-collapse text-left text-sm">
              <thead className="bg-[#FBF9FF] text-[11px] uppercase tracking-[0.16em] text-[#50627F]">
                <tr>
                  <th className="px-4 py-4 font-black">Area</th>
                  <th className="px-4 py-4 font-black">Categoria</th>
                  <th className="px-4 py-4 font-black">Voce</th>
                  <th className="px-4 py-4 text-right font-black">Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EFE9F7] bg-white">
                {topOpportunities.length ? (
                  topOpportunities.map((row) => {
                    const label = getScoreLabel(row.score);

                    return (
                      <tr key={row.item.id} className="align-top">
                        <td className="px-4 py-4 font-black text-[#23124A]">
                          {row.macro.title}
                        </td>
                        <td className="px-4 py-4 font-semibold text-[#50627F]">
                          {row.category.title}
                        </td>
                        <td className="px-4 py-4 font-semibold text-[#50627F]">
                          {row.item.text}
                        </td>
                        <td className="px-4 py-4 text-right">
                          <span
                            className={`inline-flex min-w-12 justify-center rounded-full px-3 py-1 text-sm font-black ring-1 ${label.pillClassName}`}
                          >
                            {row.score}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                ) : (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-4 py-8 text-center text-sm font-semibold text-[#50627F]"
                    >
                      {isWebAudit
                        ? "Verifica almeno alcune voci per evidenziare le criticità esterne."
                        : "Compila almeno alcune voci per generare le priorità."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-[2rem] border border-[#E5DDF1] bg-white p-6 shadow-[0_18px_50px_rgba(35,18,74,0.06)]">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
            <div className="max-w-3xl">
              <p className="text-[12px] font-black uppercase tracking-[0.28em] text-[#C8A96B]">
                Azioni finali standalone
              </p>
              <h2 className="mt-2 text-2xl font-black text-[#23124A]">
                Esporta, salva o azzera l’autovalutazione
              </h2>
              <p className="mt-2 text-sm leading-6 text-[#50627F]">
                Questa versione è indipendente dal gestionale Velora: puoi generare il report
                PDF, esportare i dati in CSV per Excel, salvare il file JSON tecnico oppure
                azzerare la compilazione e iniziare una nuova diagnosi.
              </p>
            </div>

            <div className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2 xl:w-auto xl:min-w-[560px]">
              <button
                type="button"
                onClick={generatePrintableReport}
                className="rounded-2xl bg-[#23124A] px-5 py-4 text-sm font-black text-white shadow-sm transition hover:bg-[#2F1A63]"
              >
                Genera report PDF
              </button>

              <button
                type="button"
                onClick={exportCsv}
                className="rounded-2xl border border-[#23124A]/20 bg-[#FBF9FF] px-5 py-4 text-sm font-black text-[#23124A] transition hover:bg-[#F3EEF9]"
              >
                Esporta CSV
              </button>

              <button
                type="button"
                onClick={exportJson}
                className="rounded-2xl border border-[#C8A96B]/50 bg-[#FFF8E8] px-5 py-4 text-sm font-black text-[#23124A] transition hover:bg-[#F7EBC9]"
              >
                Esporta JSON
              </button>

              <button
                type="button"
                onClick={resetAssessment}
                className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm font-black text-red-700 transition hover:bg-red-100"
              >
                Azzera modulo
              </button>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
