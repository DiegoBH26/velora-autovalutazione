import React, { useEffect, useMemo, useState } from "react";

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

type AssessmentMode = "full" | "quick-hotel-bb";

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
};

type OwnerInfo = {
  propertyName: string;
  ownerName: string;
  location: string;
  propertyType: string;
  rooms: string;
  channels: string;
  objective: string;
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

const QUICK_HOTEL_BB_CORE_ITEM_SET = new Set<string>(QUICK_HOTEL_BB_CORE_ITEM_IDS);
const QUICK_HOTEL_BB_DEEP_DIVE_ITEM_SET = new Set<string>(
  QUICK_HOTEL_BB_DEEP_DIVE_ITEM_IDS
);
const QUICK_HOTEL_BB_ALL_ITEM_SET = new Set<string>([
  ...QUICK_HOTEL_BB_CORE_ITEM_IDS,
  ...QUICK_HOTEL_BB_DEEP_DIVE_ITEM_IDS,
]);

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
  return { importance: 0, current: 0, fit: 0, note: "" };
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

export default function App() {
  const [ownerInfo, setOwnerInfo] = useState<OwnerInfo>({
    propertyName: "",
    ownerName: "",
    location: "",
    propertyType: "",
    rooms: "",
    channels: "",
    objective: "",
  });

  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [assessmentMode, setAssessmentMode] = useState<AssessmentMode>("full");
  const [showQuickDeepDive, setShowQuickDeepDive] = useState(false);
  const [activeMacroId, setActiveMacroId] = useState(ASSESSMENT_DATA[0]?.id ?? "");
  const [showOnlyPriority, setShowOnlyPriority] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");

  const isQuickHotelBb = assessmentMode === "quick-hotel-bb";
  const assessmentData = isQuickHotelBb
    ? showQuickDeepDive
      ? QUICK_HOTEL_BB_ALL_DATA
      : QUICK_HOTEL_BB_CORE_DATA
    : ASSESSMENT_DATA;

  const allRows = useMemo(() => flattenItems(assessmentData), [assessmentData]);

  const answeredCount = useMemo(
    () =>
      allRows.filter(({ item }) => {
        const answer = answers[item.id];
        return answer && (answer.importance || answer.current || answer.fit || answer.note);
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
          return answer && (answer.importance || answer.current || answer.fit || answer.note);
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
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;

    try {
      const parsed = JSON.parse(raw);
      if (parsed.ownerInfo) setOwnerInfo(parsed.ownerInfo);
      if (parsed.answers) setAnswers(parsed.answers);
      if (parsed.assessmentMode === "full" || parsed.assessmentMode === "quick-hotel-bb") {
        setAssessmentMode(parsed.assessmentMode);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ ownerInfo, answers, assessmentMode })
    );
  }, [ownerInfo, answers, assessmentMode]);

  const activeMacro =
    assessmentData.find((macro) => macro.id === activeMacroId) ?? assessmentData[0];

  const activeMacroScore = macroScores.find((macro) => macro.id === activeMacro?.id);
  const globalLabel = getScoreLabel(globalScore);
  const progressPct = allRows.length ? Math.round((answeredCount / allRows.length) * 100) : 0;

  function updateOwnerInfo<K extends keyof OwnerInfo>(key: K, value: OwnerInfo[K]) {
    setOwnerInfo((prev) => ({ ...prev, [key]: value }));
  }

  function updateAnswer(itemId: string, patch: Partial<Answer>) {
    setAnswers((prev) => ({
      ...prev,
      [itemId]: { ...(prev[itemId] ?? emptyAnswer()), ...patch },
    }));
  }

  function switchAssessmentMode(mode: AssessmentMode) {
    const nextData = mode === "quick-hotel-bb" ? QUICK_HOTEL_BB_CORE_DATA : ASSESSMENT_DATA;
    setAssessmentMode(mode);
    setShowQuickDeepDive(false);
    setActiveMacroId(nextData[0]?.id ?? "");
    setShowOnlyPriority(false);
    setSearchTerm("");
  }


  function saveDiagnosis(showMessage = true) {
    const payload = {
      ownerInfo,
      answers,
      assessmentMode,
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
    window.localStorage.removeItem(STORAGE_KEY);
  }

  function exportJson() {
    const payload = {
      generatedAt: new Date().toISOString(),
      assessmentMode,
      assessmentFormat: isQuickHotelBb ? "Analisi rapida Hotel / B&B" : "Analisi completa",
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

    const rows = [
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
    a.download = "velora-modello-analisi-rapida-hotel-bb.csv";
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

    const sectionsHtml = [
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
          <title>Modello Analisi rapida Hotel e B&amp;B</title>
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
            <h1>Analisi rapida Hotel / B&amp;B</h1>
            <p class="subtitle">30 domande principali e 20 opzionali per una diagnosi di posizionamento, vendita, revenue, gestione delegata e qualità del servizio.</p>
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

          <footer>Modello generato da Velora RMS · Analisi rapida Hotel / B&amp;B · 30 domande principali + 20 di approfondimento.</footer>
        </body>
      </html>
    `;

    const date = new Date().toISOString().slice(0, 10);
    await savePdfHtml(
      html,
      `velora-modello-analisi-rapida-hotel-bb-${date}.pdf`,
      "Modello rapido PDF salvato correttamente.",
      "velora-quick-template-frame"
    );
  }

  async function generatePrintableReport() {
    const generatedAt = new Date().toLocaleString("it-IT");

    const safe = (value: unknown) =>
      String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

    const optionLabel = (
      options: { value: number; label: string }[],
      value: number
    ) => options.find((option) => option.value === value)?.label ?? String(value);

    const highPriorities = topOpportunities.filter((row) => row.score >= 70);
    const mediumPriorities = topOpportunities.filter(
      (row) => row.score >= 40 && row.score < 70
    );

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

    const macroRowsHtml = macroScores
      .map((macro) => {
        const label = getScoreLabel(macro.score);
        return `
          <tr>
            <td>${safe(macro.title)}</td>
            <td class="center">${macro.answeredItems}/${macro.totalItems}</td>
            <td class="center"><strong>${macro.score}</strong>/100</td>
            <td><span class="badge">${safe(label.label)}</span></td>
          </tr>
        `;
      })
      .join("");

    const topOpportunitiesHtml = topOpportunities.length
      ? topOpportunities
          .map((row, index) => {
            const answer = row.answer ?? emptyAnswer();
            const label = getScoreLabel(row.score);

            return `
              <tr>
                <td class="center">${index + 1}</td>
                <td>
                  <strong>${safe(row.item.text)}</strong><br />
                  <span>${safe(row.macro.title)} · ${safe(row.category.title)}</span>
                </td>
                <td class="center"><strong>${row.score}</strong>/100</td>
                <td>${safe(label.label)}</td>
                <td>${safe(answer.note || "—")}</td>
              </tr>
            `;
          })
          .join("")
      : `
        <tr>
          <td colspan="5" class="empty">
            Nessuna opportunità rilevante ancora individuata.
          </td>
        </tr>
      `;

    const detailedRowsHtml = completedRows.length
      ? completedRows
          .map((row) => {
            const answer = answers[row.item.id] ?? emptyAnswer();
            const score = getItemScore(answer);
            const label = getScoreLabel(score);

            return `
              <tr>
                <td>
                  <strong>${safe(row.item.text)}</strong><br />
                  <span>${safe(row.macro.title)} · ${safe(row.category.title)}</span>
                </td>
                <td>${safe(optionLabel(scoreOptions, answer.importance))}</td>
                <td>${safe(optionLabel(currentOptions, answer.current))}</td>
                <td>${safe(optionLabel(scoreOptions, answer.fit))}</td>
                <td class="center"><strong>${score}</strong>/100<br />${safe(label.label)}</td>
                <td>${safe(answer.note || "—")}</td>
              </tr>
            `;
          })
          .join("")
      : `
        <tr>
          <td colspan="6" class="empty">
            Nessuna voce compilata.
          </td>
        </tr>
      `;

    const html = `
      <!doctype html>
      <html lang="it">
        <head>
          <meta charset="utf-8" />
          <title>${isQuickHotelBb ? "Report Analisi rapida Hotel e B&B" : "Report Autovalutazione Velora"}</title>
          <style>
            @page {
              size: A4;
              margin: 18mm;
            }

            * {
              box-sizing: border-box;
            }

            body {
              margin: 0;
              background: #ffffff;
              color: #1f2937;
              font-family: Arial, Helvetica, sans-serif;
              font-size: 12px;
              line-height: 1.45;
            }

            .cover {
              border-bottom: 4px solid #C8A96B;
              padding-bottom: 24px;
              margin-bottom: 24px;
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
              font-size: 30px;
              line-height: 1.1;
              margin: 0 0 12px;
            }

            h2 {
              color: #23124A;
              font-size: 19px;
              margin: 28px 0 12px;
              padding-bottom: 8px;
              border-bottom: 1px solid #e5e7eb;
            }

            .subtitle {
              color: #475569;
              font-size: 13px;
              max-width: 760px;
            }

            .grid {
              display: grid;
              grid-template-columns: repeat(4, 1fr);
              gap: 10px;
              margin: 18px 0;
            }

            .card {
              border: 1px solid #e5e7eb;
              border-radius: 14px;
              padding: 12px;
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
              font-size: 20px;
              font-weight: 800;
              margin-top: 4px;
            }

            .info {
              display: grid;
              grid-template-columns: repeat(2, 1fr);
              gap: 8px 18px;
              margin-top: 16px;
            }

            .info div {
              border-bottom: 1px solid #e5e7eb;
              padding-bottom: 6px;
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
              font-size: 13px;
              margin-top: 2px;
            }

            table {
              width: 100%;
              border-collapse: collapse;
              margin-top: 10px;
              page-break-inside: auto;
            }

            th {
              background: #23124A;
              color: #ffffff;
              text-align: left;
              font-size: 10px;
              text-transform: uppercase;
              letter-spacing: 0.08em;
              padding: 8px;
            }

            td {
              border: 1px solid #e5e7eb;
              padding: 8px;
              vertical-align: top;
            }

            tr {
              page-break-inside: avoid;
            }

            td span {
              color: #64748b;
              font-size: 10px;
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

            .empty {
              text-align: center;
              color: #64748b;
              padding: 18px;
            }

            .page-break {
              page-break-before: always;
            }

            .footer {
              margin-top: 30px;
              padding-top: 12px;
              border-top: 1px solid #e5e7eb;
              color: #64748b;
              font-size: 10px;
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
            <div class="eyebrow">Velora RMS · ${isQuickHotelBb ? "Analisi rapida Hotel / B&B" : "Autovalutazione consulenziale"}</div>
            <h1>${isQuickHotelBb ? "Report analisi rapida Hotel / B&B" : "Report di autovalutazione struttura ricettiva"}</h1>
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
              <div>
                <span>Obiettivo principale</span>
                <strong>${safe(ownerInfo.objective || "Non indicato")}</strong>
              </div>
              <div>
                <span>Data generazione</span>
                <strong>${safe(generatedAt)}</strong>
              </div>
            </div>
          </section>

          <section>
            <h2>Sintesi executive</h2>

            <div class="grid">
              <div class="card">
                <div class="card-label">Indice opportunità</div>
                <div class="card-value">${globalScore}/100</div>
              </div>
              <div class="card">
                <div class="card-label">Voci compilate</div>
                <div class="card-value">${answeredCount}/${allRows.length}</div>
              </div>
              <div class="card">
                <div class="card-label">Priorità alte</div>
                <div class="card-value">${highPriorities.length}</div>
              </div>
              <div class="card">
                <div class="card-label">Priorità medie</div>
                <div class="card-value">${mediumPriorities.length}</div>
              </div>
            </div>

            <div class="summary-box">
              <strong>Interpretazione del punteggio:</strong><br />
              il valore cresce quando una voce è importante, oggi poco presidiata
              e coerente con il possibile intervento Velora. Un punteggio alto non indica
              un errore della struttura, ma una maggiore opportunità consulenziale.
            </div>
          </section>

          <section>
            <h2>Risultato per macro-area</h2>
            <table>
              <thead>
                <tr>
                  <th>Macro-area</th>
                  <th>Compilazione</th>
                  <th>Punteggio</th>
                  <th>Lettura</th>
                </tr>
              </thead>
              <tbody>
                ${macroRowsHtml}
              </tbody>
            </table>
          </section>

          <section class="page-break">
            <h2>Prime opportunità consulenziali</h2>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Voce</th>
                  <th>Punteggio</th>
                  <th>Priorità</th>
                  <th>Note / evidenze</th>
                </tr>
              </thead>
              <tbody>
                ${topOpportunitiesHtml}
              </tbody>
            </table>
          </section>

          <section class="page-break">
            <h2>Dettaglio voci compilate</h2>
            <table>
              <thead>
                <tr>
                  <th>Voce</th>
                  <th>Importanza</th>
                  <th>Stato attuale</th>
                  <th>Fit Velora</th>
                  <th>Punteggio</th>
                  <th>Note / criticità / evidenze</th>
                </tr>
              </thead>
              <tbody>
                ${detailedRowsHtml}
              </tbody>
            </table>
          </section>

          <div class="footer">
            Report generato da Velora RMS · ${isQuickHotelBb ? `Analisi rapida Hotel / B&B · ${showQuickDeepDive ? "30 domande principali + 20 di approfondimento" : "30 domande principali"}.` : "Modulo Autovalutazione struttura ricettiva."}
          </div>

        </body>
      </html>
    `;

    if (window.veloraDesktop?.savePdf) {
      try {
        const reportKind = isQuickHotelBb ? "analisi-rapida-hotel-bb" : "autovalutazione";
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
    isDeepDive = false
  ) {
    const answer = answers[item.id] ?? emptyAnswer();
    const score = getItemScore(answer);
    const label = getScoreLabel(score);

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
            <h4 className="mt-1 text-base font-black leading-6 text-[#23124A]">
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
                renderQuestionCard(item, numberById.get(item.id), isDeepDive)
              )}
            </div>
          </div>
        ))}
      </section>
    ));
  }


  return (
    <main className="min-h-screen bg-[#F7F4FB] px-6 py-6 text-[#23124A]">
      <div className="mx-auto flex max-w-[1500px] flex-col gap-6">
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
            </div>

            <div className="grid w-full grid-cols-1 gap-3 md:grid-cols-2 xl:w-auto xl:min-w-[660px]">
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
                    30 + 20
                  </span>
                </span>
                <span className="mt-1 block text-xs font-semibold text-[#50627F]">
                  30 principali, più 20 approfondimenti opzionali
                </span>
              </button>
            </div>
          </div>

          {isQuickHotelBb && (
            <div className="mt-4 flex flex-col gap-3 rounded-2xl border border-[#E8D8B3] bg-[#FFFBF2] p-4 md:flex-row md:items-center md:justify-between">
              <p className="text-sm font-semibold text-[#50627F]">
                Esporta il modello completo: 30 domande principali e 20 approfondimenti opzionali.
              </p>
              <div className="flex flex-col gap-2 sm:flex-row">
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
                  {isQuickHotelBb
                    ? "Analisi rapida Hotel / B&B"
                    : "Autovalutazione struttura ricettiva"}
                </h1>
                <p className="mt-3 max-w-3xl text-sm leading-7 text-[#50627F]">
                  {isQuickHotelBb
                    ? `Percorso guidato con 30 domande principali${showQuickDeepDive ? " e 20 approfondimenti aperti" : ""}, focalizzato su posizionamento, revenue, vendita, gestione delegata e qualità del servizio.`
                    : "Questionario diagnostico per capire i bisogni reali della struttura, le aree scoperte e dove Velora può generare valore concreto prima di proporre un intervento consulenziale o operativo."}
                </p>
              </div>

              <div
                className={`min-w-[260px] rounded-[1.5rem] border px-5 py-4 shadow-sm ${globalLabel.className}`}
              >
                <p className="text-[11px] font-black uppercase tracking-[0.18em]">
                  Indice opportunità
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
                {answeredCount} su {allRows.length} voci operative
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
                {isQuickHotelBb ? "settori essenziali selezionati" : "mappa completa dei bisogni"}
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
                prime aree da valutare
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
              ["location", "Località", "Città / zona"],
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

        {isQuickHotelBb ? (
          <section className="flex flex-col gap-6">
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
                              <h4 className="mt-1 text-base font-black leading-6 text-[#23124A]">
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
                Prime opportunità consulenziali
              </h2>
              <p className="mt-2 text-sm leading-6 text-[#50627F]">
                Le voci con punteggio più alto indicano dove Velora può generare più valore
                o dove serve una valutazione più approfondita.
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
                      Compila almeno alcune voci per generare le priorità.
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
