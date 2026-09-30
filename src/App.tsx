import React, { useEffect, useMemo, useState } from "react";
import santantonioAudit from "./santantonio-audit.json";
import santantonioReportUrl from "./santantonio-report.pdf?url";

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
};

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
  nights: 1, roomType: "Matrimoniale", guests: 2, board: "Colazione inclusa",
  refund: "Rimborsabile", audience: "Pubblico senza login", taxes: "IVA inclusa, tassa di soggiorno esclusa",
  promotion: "", promotionKind: "Non verificata", originalTotal: 0, eventTag: "", sourceUrl: "",
};

function todayLocalIso(date = new Date()): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function rateCohortKey(quote: RateQuote): string {
  return [quote.roomType.trim().toLowerCase(), quote.guests, quote.nights, quote.board, quote.refund, quote.audience, quote.taxes].join("|");
}

function rateCohortLabel(quote: RateQuote): string {
  return `${quote.roomType} · ${quote.guests} ospiti · ${quote.nights} notte/i · ${quote.board} · ${quote.refund} · ${quote.audience} · ${quote.taxes}`;
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

function monthlyCoverageSummary(quotes: RateQuote[], probes: AvailabilityProbe[], month: string, otaId: string): string {
  const priceCount = monthlyRateCell(quotes, month, otaId).count;
  const probeSummary = monthlyAvailabilitySummary(probes, month, otaId);
  return [priceCount && `Prezzo visibile: ${priceCount} data/e`, probeSummary !== "Non verificato" && probeSummary].filter(Boolean).join("; ") || "Non verificato";
}

function promotionSummary(quote: RateQuote): string {
  const type = quote.promotionKind || (quote.promotion ? "Tipo non classificato" : "Non verificata");
  const discount = Number(quote.originalTotal) > quote.total
    ? ` · -${((1 - quote.total / Number(quote.originalTotal)) * 100).toFixed(1)}% rispetto al prezzo barrato`
    : "";
  return `${type}${quote.promotion ? ` · ${quote.promotion}` : ""}${discount}`;
}

function monthlyRateCell(quotes: RateQuote[], month: string, otaId: string): { average: number | null; count: number; deltaPct: number | null; matched: number } {
  const own = quotes.filter((quote) => quote.otaId === otaId && quote.stayDate.startsWith(month));
  if (!own.length) return { average: null, count: 0, deltaPct: null, matched: 0 };
  const average = own.reduce((sum, quote) => sum + quote.total / quote.nights, 0) / own.length;
  const pairs = otaId === "booking" ? [] : own.flatMap((quote) => {
    const base = quotes.find((other) => other.otaId === "booking" && other.stayDate === quote.stayDate && other.observedAt.slice(0, 10) === quote.observedAt.slice(0, 10));
    return base ? [{ own: quote.total / quote.nights, base: base.total / base.nights }] : [];
  });
  const deltaPct = pairs.length ? pairs.reduce((sum, pair) => sum + 100 * (pair.own - pair.base) / pair.base, 0) / pairs.length : null;
  return { average, count: own.length, deltaPct, matched: pairs.length };
}

function santantonioStructure(): AnalyzedStructure {
  const answers: Record<string, Answer> = {};
  for (const check of santantonioAudit.checks) {
    const status = check.status as AuditStatus;
    const sourceLinks = check.sources
      .map((sourceId) => santantonioAudit.sources[sourceId as keyof typeof santantonioAudit.sources]?.url)
      .filter(Boolean);
    answers[check.id] = {
      importance: status === "unverified" ? 0 : 3,
      current: status === "present" ? 3 : status === "partial" ? 1.5 : 0,
      fit: status === "unverified" ? 0 : 3,
      auditStatus: status,
      note: `${check.evidence}\nFonti: ${sourceLinks.join(" · ")}`,
    };
  }
  for (const channel of santantonioAudit.otaPresence) {
    const source = santantonioAudit.sources[channel.source as keyof typeof santantonioAudit.sources];
    answers[`audit-ota-${channel.id}`] = {
      ...emptyAnswer(),
      auditStatus: channel.status as AuditStatus,
      note: `${channel.finding}\nFonte: ${source?.url ?? "verifica manuale"}`,
    };
  }
  for (const policy of santantonioAudit.pricingAudit.policies) {
    const source = santantonioAudit.sources[policy.source as keyof typeof santantonioAudit.sources];
    answers[`audit-policy-${policy.otaId}`] = {
      ...emptyAnswer(),
      note: `Piani: ${policy.plans}\nPromozioni/sconti: ${policy.promotions}\nAffidabilità: ${policy.confidence}. Fonte: ${source?.url ?? "verifica manuale"}`,
    };
  }
  answers["audit-policy-direct"] = { ...emptyAnswer(), note: santantonioAudit.pricingAudit.direct };
  answers["audit-google-strengths"] = { ...emptyAnswer(), note: santantonioAudit.reviewInsights.strengths.map((entry) => `${entry.theme}: ${entry.finding}`).join("\n") };
  answers["audit-google-weaknesses"] = { ...emptyAnswer(), note: santantonioAudit.reviewInsights.weaknesses.map((entry) => `${entry.theme}: ${entry.finding}`).join("\n") };
  answers["audit-google-actions"] = { ...emptyAnswer(), note: santantonioAudit.reviewInsights.weaknesses.map((entry) => `${entry.theme}: ${entry.action}`).join("\n") };
  answers["audit-photo-score"] = { ...emptyAnswer(), current: santantonioAudit.photoAssessment.score, note: `${santantonioAudit.photoAssessment.gaps}\nAzione: ${santantonioAudit.photoAssessment.actions}` };
  return {
    id: santantonioAudit.id,
    name: santantonioAudit.name,
    city: santantonioAudit.city,
    province: santantonioAudit.province,
    rooms: String(santantonioAudit.rooms),
    website: santantonioAudit.website,
    reportPath: santantonioAudit.reportPath,
    auditedAt: santantonioAudit.auditedAt,
    ownerInfo: {
      ...EMPTY_OWNER_INFO,
      propertyName: santantonioAudit.name,
      location: santantonioAudit.city,
      city: santantonioAudit.city,
      province: santantonioAudit.province,
      propertyType: santantonioAudit.propertyType,
      rooms: String(santantonioAudit.rooms),
      channels: "Sito ufficiale, Booking.com, Google Hotels, Hotels.com",
      objective: "Audit pubblico di visibilità, prenotazione diretta e reputazione",
    },
    answers,
    rateQuotes: [],
    availabilityProbes: [],
    assessmentMode: "web-audit",
    updatedAt: santantonioAudit.auditedAt,
  };
}

function loadAnalyzedStructures(): AnalyzedStructure[] {
  const seed = santantonioStructure();
  try {
    const saved = JSON.parse(window.localStorage.getItem(STRUCTURES_KEY) || "[]");
    if (!Array.isArray(saved)) return [seed];
    const existing = saved.filter((item): item is AnalyzedStructure =>
      Boolean(item && typeof item.id === "string" && item.ownerInfo && item.answers)
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
      return { ...item, answers, rateQuotes: Array.isArray(item.rateQuotes) ? item.rateQuotes : [], availabilityProbes: Array.isArray(item.availabilityProbes) ? item.availabilityProbes : [] };
    });
    return migrated.some((item) => item.id === seed.id) ? migrated : [seed, ...migrated];
  } catch {
    return [seed];
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

export default function App() {
  const [structures, setStructures] = useState<AnalyzedStructure[]>(loadAnalyzedStructures);
  const [activeStructureId, setActiveStructureId] = useState<string | null>(null);
  const [showStructures, setShowStructures] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [ownerInfo, setOwnerInfo] = useState<OwnerInfo>(EMPTY_OWNER_INFO);

  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [rateQuotes, setRateQuotes] = useState<RateQuote[]>([]);
  const [rateDraft, setRateDraft] = useState<RateQuote>(EMPTY_RATE_DRAFT);
  const [availabilityProbes, setAvailabilityProbes] = useState<AvailabilityProbe[]>([]);
  const [availabilityDraft, setAvailabilityDraft] = useState<AvailabilityProbe>(EMPTY_AVAILABILITY_DRAFT);
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
  const [activeMacroId, setActiveMacroId] = useState(ASSESSMENT_DATA[0]?.id ?? "");
  const [showOnlyPriority, setShowOnlyPriority] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [auditSourceFilter, setAuditSourceFilter] = useState("Tutte le fonti");

  const isQuickHotelBb = assessmentMode === "quick-hotel-bb";
  const isWebAudit = assessmentMode === "web-audit";
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

  function openStoredReport(structure: AnalyzedStructure) {
    if (!structure.reportPath) return;
    const url = structure.id === santantonioAudit.id
      ? santantonioReportUrl
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
    const quote = { ...rateDraft, id: globalThis.crypto?.randomUUID?.() ?? `rate-${Date.now()}`, observedAt: new Date().toISOString(), roomType: rateDraft.roomType.trim(), sourceUrl: rateDraft.sourceUrl.trim() };
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
    const reportChannels = santantonioAudit.otaPresence;
    const monthlyTable = (channels: typeof reportChannels) => `<table><thead><tr><th>Mese</th>${channels.map((channel) => `<th>${safe(channel.platform)}</th>`).join("")}</tr></thead><tbody>${reportMonths.map((month) => `<tr><td><b>${safe(new Date(`${month}-01T12:00:00Z`).toLocaleDateString("it-IT", { month: "short", year: "numeric", timeZone: "UTC" }))}</b></td>${channels.map((channel) => { const cell = monthlyRateCell(reportQuotes, month, channel.id); return `<td>${cell.average === null ? "n.d." : `<b>€ ${cell.average.toFixed(2)}</b><small>${cell.count} data/e${cell.deltaPct === null ? " · Δ n.d." : ` · Δ ${cell.deltaPct > 0 ? "+" : ""}${cell.deltaPct.toFixed(1)}% (${cell.matched})`}</small>`}</td>`; }).join("")}</tr>`).join("")}</tbody></table>`;
    const commercialReportHtml = isWebAudit ? `<section class="page-break"><h2>Politiche commerciali e tariffarie per OTA</h2><p>Rilevazione pubblica: i piani e gli sconti sono validi soltanto per date, camera e pubblico consultati. Una scheda presente non dimostra inventario vendibile su tutto il calendario. ${activeStructureId === santantonioAudit.id ? safe(santantonioAudit.pricingAudit.method) : "Annotare fonte e data per ogni riscontro."}</p><table><thead><tr><th style="width:17%">Canale</th><th>Tariffe, promozioni e limiti del riscontro</th></tr></thead><tbody><tr><td><b>Sito diretto</b></td><td>${safe(answers["audit-policy-direct"]?.note || "Non verificato")}</td></tr>${reportChannels.map((channel) => `<tr><td><b>${safe(channel.platform)}</b></td><td>${safe(answers[`audit-policy-${channel.id}`]?.note || "Non verificato")}</td></tr>`).join("")}</tbody></table><h2>Prezzo medio osservato per mese e canale</h2><p><b>Non è ADR realizzato.</b> È la media dei preventivi per notte nel campione inserito. ${reportCohort ? `Condizioni confrontate: ${safe(reportCohorts.find(([key]) => key === reportCohort)?.[1] || "")}.` : "Nessuna quotazione omogenea inserita: celle n.d. e nessun delta calcolabile."} Il delta confronta soltanto le stesse date di soggiorno, rilevate nello stesso giorno e nelle stesse condizioni.</p>${monthlyTable(reportChannels.slice(0, 5))}${monthlyTable(reportChannels.slice(5))}<p>Δ = differenza percentuale media rispetto a Booking; il numero tra parentesi indica le date abbinate. Una o poche date non rappresentano tutto il mese. Controllare in particolare Pasqua, ponti, giugno, Ferragosto e Natale/Capodanno. I prezzi possono variare dopo la rilevazione.</p></section>` : "";

    const coverageTable = (channels: typeof reportChannels) => '<table><thead><tr><th>Mese futuro</th>' + channels.map((channel) => '<th>' + safe(channel.platform) + '</th>').join('') + '</tr></thead><tbody>' + reportMonths.map((month) => '<tr><td><b>' + safe(new Date(month + '-01T12:00:00Z').toLocaleDateString('it-IT', { month: 'short', year: 'numeric', timeZone: 'UTC' })) + '</b></td>' + channels.map((channel) => {
      const status = monthlyCoverageSummary(reportQuotes, availabilityProbes, month, channel.id);
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
            {santantonioAudit.otaPresence.map((channel) => {
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
          <h3 className="mt-6 text-lg font-black text-[#23124A]">Piani tariffari, promozioni e sconti per canale</h3>
          <p className="mt-1 text-xs leading-5 text-[#50627F]">Registra soltanto ciò che compare sulla specifica scheda, con data e URL. Una dicitura “potresti avere uno sconto” non dimostra una promozione attiva; tariffe per iscritti o app vanno distinte da quelle pubbliche.</p>
          <label className="mt-3 block text-[11px] font-black text-[#23124A]">Sito diretto e listino
            <textarea value={answers["audit-policy-direct"]?.note ?? ""} onChange={(event) => updateAnswer("audit-policy-direct", { note: event.target.value })} placeholder="Periodi, prezzi, condizioni, fonte e data" className="mt-1.5 min-h-[65px] w-full resize-y rounded-xl border border-[#E0D7EC] bg-[#FBF9FF] px-3 py-2 text-xs font-medium leading-5 text-[#23124A]" />
          </label>
          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
            {santantonioAudit.otaPresence.map((channel) => <label key={`policy-${channel.id}`} className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3 text-[11px] font-black text-[#23124A]">
              {channel.platform} <span className="font-medium text-[#50627F]">· {channel.group}</span>
              <textarea value={answers[`audit-policy-${channel.id}`]?.note ?? ""} onChange={(event) => updateAnswer(`audit-policy-${channel.id}`, { note: event.target.value })} placeholder="Rimborsabile/parziale/non rimborsabile; Genius, mobile, member, pacchetti; URL e data. Se non verificato, dichiararlo." className="mt-2 min-h-[94px] w-full resize-y rounded-lg border border-[#E0D7EC] bg-white px-2.5 py-2 text-[11px] font-medium leading-5 text-[#23124A] placeholder:text-slate-400" />
            </label>)}
          </div>

          <h3 className="mt-7 text-lg font-black text-[#23124A]">Prezzi osservati per mese e delta tra OTA</h3>
          <p className="mt-1 text-xs leading-5 text-[#50627F]">Questa è la <b>media dei prezzi richiesti per notte nel campione</b>, non l'ADR reale (ricavi camere / camere vendute). Inserisci preventivi della stessa camera, ospiti, durata, colazione, cancellazione, pubblico, valuta e trattamento fiscale. I delta rispetto a Booking sono calcolati solo su date di soggiorno identiche, rilevate nello stesso giorno. “—” = nessun dato, non prezzo zero.</p>
          <div className="mt-4 grid grid-cols-2 gap-2 rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] p-4 md:grid-cols-4">
            <label className="text-[11px] font-black text-[#23124A]">OTA<select value={rateDraft.otaId} onChange={(event) => setRateDraft((previous) => ({ ...previous, otaId: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs">{santantonioAudit.otaPresence.map((channel) => <option key={channel.id} value={channel.id}>{channel.platform}</option>)}</select></label>
            <label className="text-[11px] font-black text-[#23124A]">Data soggiorno<input type="date" value={rateDraft.stayDate} onChange={(event) => setRateDraft((previous) => ({ ...previous, stayDate: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Totale camera in EUR<input type="number" min="0.01" step="0.01" value={rateDraft.total || ""} onChange={(event) => setRateDraft((previous) => ({ ...previous, total: Number(event.target.value) }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Notti<input type="number" min="1" value={rateDraft.nights} onChange={(event) => setRateDraft((previous) => ({ ...previous, nights: Math.max(1, Number(event.target.value)) }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
            <label className="text-[11px] font-black text-[#23124A]">Tipologia camera<input value={rateDraft.roomType} onChange={(event) => setRateDraft((previous) => ({ ...previous, roomType: event.target.value }))} className="mt-1 w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs" /></label>
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
          <button type="button" onClick={addRateQuote} className="mt-3 rounded-xl bg-[#23124A] px-4 py-2 text-xs font-black text-white">Salva prezzo e promozione osservati con data e ora della verifica</button>
          <label className="mt-4 block text-[11px] font-black text-[#23124A]">Confronta condizioni omogenee
            <select value={activeCohort} onChange={(event) => setSelectedRateCohort(event.target.value)} className="mt-1 block w-full rounded-xl border border-[#E0D7EC] bg-white p-2.5 text-xs font-medium"><option value="">Nessuna rilevazione ancora inserita</option>{cohortOptions.map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
          </label>
          <div className="mt-3 overflow-x-auto rounded-xl border border-[#E5DDF1]"><table className="min-w-[1240px] w-full border-collapse text-[11px]"><thead className="bg-[#23124A] text-white"><tr><th className="p-2 text-left">Mese soggiorno</th>{santantonioAudit.otaPresence.map((channel) => <th key={channel.id} className="p-2 text-left">{channel.platform}</th>)}</tr></thead><tbody>{rateMonths.map((month) => <tr key={month} className="border-t border-[#E5DDF1] odd:bg-[#FBF9FF]"><th className="p-2 text-left text-[#23124A]">{new Date(`${month}-01T12:00:00Z`).toLocaleDateString("it-IT", { month: "long", year: "numeric", timeZone: "UTC" })}</th>{santantonioAudit.otaPresence.map((channel) => { const cell = monthlyRateCell(comparableQuotes, month, channel.id); return <td key={channel.id} className="p-2 text-[#23124A]">{cell.average === null ? "—" : <><b>€{cell.average.toFixed(2)}</b><span className="block text-[10px] text-[#50627F]">{cell.count} data/e{cell.deltaPct === null ? " · Δ n.d." : ` · Δ ${cell.deltaPct > 0 ? "+" : ""}${cell.deltaPct.toFixed(1)}% (${cell.matched})`}</span></>}</td>; })}</tr>)}</tbody></table></div>
          <p className="mt-2 text-[10px] text-[#50627F]">Δ = scostamento medio percentuale rispetto a Booking su date coincidenti e rilevate nello stesso giorno; (n) = confronti abbinati. Una sola data non rappresenta l'intero mese. Nessun dato è stimato da listini stagionali o prezzi di altre strutture. Focus: Pasqua, ponti, 2 giugno, Ferragosto, Natale/Capodanno e principali eventi locali solo se confermati.</p>
          <div className="mt-3 space-y-1">{[...rateQuotes].reverse().slice(0, 20).map((quote) => <div key={quote.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#E5DDF1] px-3 py-2 text-[11px] text-[#23124A]"><span><b>{santantonioAudit.otaPresence.find((channel) => channel.id === quote.otaId)?.platform ?? quote.otaId}</b> · {quote.stayDate} · €{(quote.total / quote.nights).toFixed(2)}/notte · {quote.refund} · {quote.promotion || "senza promo annotata"}{quote.eventTag ? ` · ${quote.eventTag}` : ""} · rilevato {new Date(quote.observedAt).toLocaleString("it-IT")}</span><button type="button" onClick={() => removeRateQuote(quote.id)} className="rounded-md border border-rose-200 px-2 py-1 font-black text-rose-700">Elimina</button></div>)}</div>
          <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
            <b>Promozioni verificate su una tariffa futura:</b> {rateQuotes.filter((quote) => quote.stayDate >= todayLocalIso() && quote.promotionKind && !["Non verificata", "Nessuna visibile"].includes(quote.promotionKind)).length || "nessuna"}.
            {rateQuotes.filter((quote) => quote.stayDate >= todayLocalIso() && quote.promotionKind && !["Non verificata", "Nessuna visibile"].includes(quote.promotionKind)).slice(-6).map((quote) => <p key={`promo-${quote.id}`} className="mt-1">{santantonioAudit.otaPresence.find((channel) => channel.id === quote.otaId)?.platform ?? quote.otaId} · {quote.stayDate} · {promotionSummary(quote)}</p>)}
          </div>
          <h3 className="mt-7 text-lg font-black text-[#23124A]">Visibilità del calendario futuro per OTA</h3>
          <p className="mt-1 text-xs leading-5 text-[#50627F]">Controlla date future su ogni canale. Registra separatamente prezzo non mostrato, data non selezionabile e verifica impedita. Una data senza prezzo può dipendere da camere esaurite, soggiorno minimo, chiusura delle vendite, finestra di prenotazione o errore tecnico: da sola non prova che la stagione sia chiusa.</p>
          <div className="mt-3 grid grid-cols-2 gap-2 rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] p-4 md:grid-cols-4">
            <label className="text-[11px] font-black text-[#23124A]">OTA<select value={availabilityDraft.otaId} onChange={(event) => setAvailabilityDraft((previous) => ({ ...previous, otaId: event.target.value }))} className="mt-1 block w-full rounded-lg border border-[#E0D7EC] bg-white p-2 text-xs">{santantonioAudit.otaPresence.map((channel) => <option key={`probe-${channel.id}`} value={channel.id}>{channel.platform}</option>)}</select></label>
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
              <thead className="bg-[#23124A] text-white"><tr><th className="p-2 text-left">Mese futuro</th>{santantonioAudit.otaPresence.map((channel) => <th key={`coverage-head-${channel.id}`} className="p-2 text-left">{channel.platform}</th>)}</tr></thead>
              <tbody>{rateMonths.map((month) => <tr key={`coverage-${month}`} className="border-t border-[#E5DDF1] odd:bg-[#FBF9FF]">
                <th className="p-2 text-left text-[#23124A]">{new Date(`${month}-01T12:00:00Z`).toLocaleDateString("it-IT", { month: "long", year: "numeric", timeZone: "UTC" })}</th>
                {santantonioAudit.otaPresence.map((channel) => <td key={`coverage-${month}-${channel.id}`} className="p-2 text-[#23124A]">{monthlyCoverageSummary(comparableQuotes, availabilityProbes, month, channel.id)}</td>)}
              </tr>)}</tbody>
            </table>
          </div>
          <p className="mt-2 text-[10px] leading-4 text-[#50627F]">“Non verificato” significa che non è stata registrata una prova per quel mese, non che il canale sia inattivo. “Prezzo non mostrato” riguarda solo le date provate. Se il calendario futuro non è aperto su più canali e date, verificare in extranet finestra di vendita, tariffe 2027, restrizioni e sincronizzazione: possibile intervento commerciale prioritario.</p>
          <div className="mt-3 space-y-1">{[...availabilityProbes].reverse().slice(0, 12).map((probe) => <div key={probe.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[#E5DDF1] px-3 py-2 text-[11px] text-[#23124A]"><span><b>{santantonioAudit.otaPresence.find((channel) => channel.id === probe.otaId)?.platform ?? probe.otaId}</b> · {probe.stayDate} · {AVAILABILITY_LABELS[probe.status]} · {probe.roomType}, {probe.guests} ospiti · rilevato {new Date(probe.observedAt).toLocaleString("it-IT")}{probe.note ? ` · ${probe.note}` : ""}</span><button type="button" onClick={() => removeAvailabilityProbe(probe.id)} className="rounded-md border border-rose-200 px-2 py-1 font-black text-rose-700">Elimina</button></div>)}</div>
          <h3 className="mt-6 text-lg font-black text-[#23124A]">Recensioni Google e qualità fotografica</h3>
          <p className="mt-1 text-xs leading-5 text-[#50627F]">Annota esempi specifici, non soltanto il voto medio. Un campione pubblico non equivale all'analisi di tutte le recensioni. Valuta le foto da 1 a 10 rispetto a uno shooting alberghiero professionale.</p>
          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
            {([
              ["audit-google-strengths", "Punti di forza percepiti"],
              ["audit-google-weaknesses", "Criticità percepite"],
              ["audit-google-actions", "Azioni operative dalle recensioni"],
            ] as const).map(([id, label]) => <label key={id} className="block text-[11px] font-black text-[#23124A]">{label}
              <textarea value={answers[id]?.note ?? ""} onChange={(event) => updateAnswer(id, { note: event.target.value })} placeholder="Tema, esempio concreto, fonte e data" className="mt-1.5 min-h-[90px] w-full resize-y rounded-xl border border-[#E0D7EC] bg-[#FBF9FF] px-3 py-2 text-xs font-medium leading-5 text-[#23124A] placeholder:text-slate-400" />
            </label>)}
            <div className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] p-3">
              <label className="text-[11px] font-black text-[#23124A]">Qualità delle foto / 10
                <input type="number" min="1" max="10" step="0.5" value={answers["audit-photo-score"]?.current || ""} onChange={(event) => updateAnswer("audit-photo-score", { current: Number(event.target.value) })} className="mt-1.5 block w-24 rounded-lg border border-[#E0D7EC] bg-white px-2.5 py-2 text-sm font-black text-[#23124A]" />
              </label>
              <textarea value={answers["audit-photo-score"]?.note ?? ""} onChange={(event) => updateAnswer("audit-photo-score", { note: event.target.value })} placeholder="Luce, composizione, copertura delle tipologie e intervento consigliato" className="mt-2 min-h-[65px] w-full resize-y rounded-xl border border-[#E0D7EC] bg-white px-3 py-2 text-xs font-medium leading-5 text-[#23124A] placeholder:text-slate-400" />
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
                  Apri la scheda compilata per consultare o aggiornare i riscontri. Il PDF disponibile è il report alla data indicata.
                </p>
              </div>
              <button type="button" onClick={() => setShowStructures(false)} className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] px-5 py-3 text-sm font-black hover:bg-[#F3EEF9]">
                Torna al questionario
              </button>
            </div>
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
                  </div>
                </div>
              </article>
            ))}
          </div>
          <p className="mt-5 text-xs leading-5 text-[#50627F]">Le modifiche alle schede restano salvate in questo browser. Le strutture del prossimo elenco saranno aggiunte al catalogo quando riceverò il file con città, provincia e numero di camere.</p>
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
            <button type="button" onClick={() => setShowStructures(true)} className="rounded-xl bg-[#23124A] px-5 py-3 text-sm font-black text-white hover:bg-[#372368]">
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
