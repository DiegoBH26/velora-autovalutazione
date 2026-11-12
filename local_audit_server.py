#!/usr/bin/env python3
"""Agente locale Velora per audit browser, pricing pilot e PDF.

Ascolta soltanto su 127.0.0.1. Il frontend online GitHub Pages puo' parlare con
il loopback del PC; Playwright e Chrome restano sulla macchina dell'utente.
Non supera login/CAPTCHA. Il token di sessione cambia a ogni avvio.
"""

from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import importlib
import os
import sys
import re
import secrets
import shutil
import threading
import types
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen

import browser_audit_pilot as browser_pilot
import velora_direct_stays as leonardo_direct_engine
try:
    from velora_portal_sessions import ManualPortalSessions, PORTALS as LOGIN_PORTALS
except ImportError:
    ManualPortalSessions=None
    LOGIN_PORTALS={}
try:
    import velora_agent_network as agent_network
    AGENT_IMPORT_ERROR=""
except ImportError as exc:
    # Mantieni operative le scansioni storiche ma rendi visibile il motivo del 503.
    agent_network=None
    AGENT_IMPORT_ERROR=f"{type(exc).__name__}: {exc}"

def specialist_unavailable_message():
    detail=(" Motivo rilevato: "+AGENT_IMPORT_ERROR) if AGENT_IMPORT_ERROR else ""
    return ("Rete specialisti non disponibile. Esegui AGGIORNA_VELORA_COMPLETO.bat "
            "nella cartella dell'agente e riavvia AVVIA_AGENTE_VELORA.bat."+detail)

CHANNELS=browser_pilot.CHANNELS
run=browser_pilot.run
EXPECTED_PILOT_BUILD="velora-browser-pilot-v125"
PILOT_RAW_URL="https://raw.githubusercontent.com/DiegoBH26/velora-autovalutazione/main/browser_audit_pilot.py"


def ensure_pilot_sync():
    global browser_pilot, CHANNELS, run
    current=getattr(browser_pilot,"PILOT_BUILD","legacy")
    if current == EXPECTED_PILOT_BUILD:
        return current

    target=Path(__file__).resolve().parent/"browser_audit_pilot.py"
    temporary=target.with_suffix(".py.update")
    try:
        req=Request(
            PILOT_RAW_URL,
            headers={
                "User-Agent":"Velora-local-agent",
                "Cache-Control":"no-cache",
                "Pragma":"no-cache",
            },
        )
        with urlopen(req,timeout=20) as response:
            payload=response.read()
        text=payload.decode("utf-8")
        marker=f'PILOT_BUILD = "{EXPECTED_PILOT_BUILD}"'
        if marker not in text:
            raise RuntimeError("la versione scaricata non corrisponde a quella attesa")

        temporary.write_text(text,encoding="utf-8")
        os.replace(temporary,target)

        # Su alcuni PC Windows importlib può continuare a usare bytecode vecchio.
        # Carichiamo quindi direttamente il sorgente appena scaricato, senza
        # dipendere dalla cache Python.
        namespace={
            "__name__":"browser_audit_pilot_live",
            "__file__":str(target),
            "__package__":None,
        }
        exec(compile(text,str(target),"exec"),namespace)
        loaded=str(namespace.get("PILOT_BUILD") or "legacy")
        if loaded != EXPECTED_PILOT_BUILD:
            raise RuntimeError(f"pilot caricato come {loaded}, atteso {EXPECTED_PILOT_BUILD}")

        live=types.SimpleNamespace(**namespace)
        browser_pilot=live
        CHANNELS=namespace["CHANNELS"]
        run=namespace["run"]
        if agent_network is not None:
            agent_network.pilot=live

        # Rimuove anche il vecchio bytecode per il prossimo avvio.
        pycache=target.parent/"__pycache__"
        if pycache.exists():
            for cached in pycache.glob("browser_audit_pilot*.pyc"):
                try:
                    cached.unlink()
                except Exception:
                    pass

        print(
            f"Sincronizzazione automatica pilot completata: {current} -> {loaded}",
            flush=True,
        )
        return loaded
    except Exception as exc:
        try:
            temporary.unlink(missing_ok=True)
        except Exception:
            pass
        print(
            f"ATTENZIONE: sincronizzazione automatica pilot fallita: {type(exc).__name__}: {str(exc)[:180]}",
            flush=True,
        )
        return getattr(browser_pilot,"PILOT_BUILD",current)

from playwright.async_api import async_playwright
from site_audit_builder import build_site_audit, public_url as validate_site_url

ROOT=Path(__file__).resolve().parent
DIST=ROOT/"dist"

# I file runtime NON devono vivere nella cartella del programma quando questa è
# sincronizzata da OneDrive/Dropbox: Windows può bloccare per pochi istanti i
# rename atomici e interrompere un audit lungo. Usa AppData\\Local\\Velora.
_local_appdata=str(os.environ.get("LOCALAPPDATA") or "").strip()
STATE_ROOT=(Path(_local_appdata)/"Velora") if _local_appdata else (ROOT/"tmp"/"velora-local-state")
RUNTIME_PROPERTIES=STATE_ROOT/"runtime-properties"
RUNTIME_AUDITS=STATE_ROOT/"runtime-audits"
PILOT_RESULTS=STATE_ROOT/"pilot-results"
AGENT_RESULTS=STATE_ROOT/"specialist-agents"
AGENT_RUN_LOCK=threading.Lock()
AGENT_WORK_SLOTS=threading.BoundedSemaphore(2)  # evita saturazione Chrome su PC
AGENT_RUNS={}
VRBO_PRESENCE_LOCK=threading.Lock()
VRBO_PRESENCE_RUNS={}
PORTAL_SESSIONS=ManualPortalSessions(STATE_ROOT) if ManualPortalSessions is not None else None
OTA_SOURCE_CACHE=STATE_ROOT/"ota-source-cache.json"
CATALOG_PATHS=(ROOT/"database_strutture.xlsx",ROOT/"database_alberghi_familiari_con_320_integrazioni.xlsx")
for _runtime_dir in (STATE_ROOT,RUNTIME_PROPERTIES,RUNTIME_AUDITS,PILOT_RESULTS,AGENT_RESULTS):
    _runtime_dir.mkdir(parents=True,exist_ok=True)

PROPERTIES={
    "perla-saracena-torre-pali":ROOT/"src"/"perla-saracena-audit.json",
    "casa-albergo-santantonio-alberobello":ROOT/"src"/"santantonio-audit.json",
}
HOST="127.0.0.1"
PORT=8768
ALLOWED_ORIGINS={
    f"http://{HOST}:{PORT}",
    f"http://localhost:{PORT}",
    "https://diegobh26.github.io",
}
PROPERTY_ID_RE=re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")


class PilotState:
    def __init__(self):
        self.lock=threading.Lock()
        self.token=secrets.token_urlsafe(32)
        self.running=False
        self.error=""
        self.property_id=""
        self.property_path=None
        self.intervention={}
        self.intervention_action=""
        self.intervention_event=threading.Event()


class AutoAuditState:
    def __init__(self):
        self.lock=threading.Lock()
        self.running=False
        self.error=""
        self.message=""
        self.property_id=""
        self.result=None


STATE=PilotState()
AUTO_STATE=AutoAuditState()


# CMD dashboard: the completion marker means a job finished, not that Giove validated its data.
AGENT_CONSOLE_LOCK=threading.Lock()

def _enable_agent_console_colors():
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return False
    if os.name!="nt":
        return True
    try:
        import ctypes
        kernel32=ctypes.windll.kernel32
        handle=kernel32.GetStdHandle(-11)
        flags=ctypes.c_ulong()
        if not kernel32.GetConsoleMode(handle,ctypes.byref(flags)):
            return False
        return bool(kernel32.SetConsoleMode(handle,flags.value|0x0004))
    except Exception:
        return False

AGENT_TERMINAL_COLORS=_enable_agent_console_colors()

def _console_color(value, color):
    return ("\033["+color+"m"+value+"\033[0m") if AGENT_TERMINAL_COLORS else value

def _column(value, width):
    text=str(value or "").replace("\r"," ").replace("\n"," ").replace("|","/").strip()
    return text[:width-1]+"…" if len(text)>width else text.ljust(width)

def print_agent_status(agent_id,phase,result,detail=""):
    if agent_network is None:
        return
    actor=agent_network.agent_display(agent_id)
    colored=_console_color(result, "32" if result=="VALIDATO"
                           else "31" if result=="ERRORE" else "33" if result=="IN CODA" else "36")
    with AGENT_CONSOLE_LOCK:
        print("  "+_column(actor,28)+" | "+_column(phase,20)+" | "
              +_column(result,12).replace(result,colored,1)+" | "+str(detail)[:150],flush=True)

def print_giove_report(report):
    with AGENT_CONSOLE_LOCK:
        print("\n"+("="*108),flush=True)
        print("GIOVE (VALIDATORE) - CHECK MANUALE - STRUTTURA: "+str(report.get("propertyId")),flush=True)
        print(_column("AGENTE (OTA)",28)+" | "+_column("CONTROLLO",30)+" | "
              +_column("ESITO",12)+" | DETTAGLIO",flush=True)
        print("-"*108,flush=True)
        for row in report.get("rows") or []:
            state=str(row.get("status") or "ERRORE")
            colored=_console_color(state,"32" if state=="VALIDATO" else "31")
            print(_column(row.get("agentName"),28)+" | "+_column(row.get("check"),30)
                  +" | "+_column(state,12).replace(state,colored,1)
                  +" | "+str(row.get("details") or "")[:100].replace("\n"," "),flush=True)
        print("-"*108,flush=True)
        print("GIOVE: "+str(report.get("passed",0))+"/"+str(report.get("total",0))
              +" controlli VALIDATI. I rimanenti richiedono verifica: nessun falso verde.",flush=True)
        print("="*108+"\n",flush=True)


def agent_workspace(property_id,agent_id):
    return AGENT_RESULTS / property_id / agent_id


def agent_output(property_id,agent_id):
    return agent_workspace(property_id,agent_id) / "result.json"


# Local, bounded agent mailbox. Structured observations only: no prompts,
# executable commands, credentials, browser control or cross-OTA navigation.
# Giove can audit the exchange, which never overrides evidence from the portal.
MAILBOX_LOCK=threading.RLock()
MAILBOX_EVENT_TYPES={"manual_presence","direct_master","booking_reference","pricing_read_failure","pricing_observed","technical_block","help_request","help_reply","review_decision","identity_rejected"}
MAILBOX_LIMIT=120


def agent_mailbox_path(property_id):
    return AGENT_RESULTS / safe_property_id(property_id) / "agent-mailbox.json"


def agent_mailbox_publish(property_id, sender, event_type, details, *, reset=False):
    if sender not in ((set(agent_network.AGENTS) if agent_network else set()) | {"giove"}):
        raise ValueError("Mittente mailbox non riconosciuto")
    if event_type not in MAILBOX_EVENT_TYPES:
        raise ValueError("Evento mailbox non consentito")
    dest=agent_mailbox_path(property_id)
    with MAILBOX_LOCK:
        payload={"propertyId":property_id,"events":[]}
        if not reset and dest.exists():
            try:
                old=json.loads(dest.read_text(encoding="utf-8"))
                if old.get("propertyId")==property_id and isinstance(old.get("events"),list):
                    payload=old
            except (OSError,ValueError,TypeError):
                pass
        safe_details={
            key:value for key,value in (details or {}).items()
            if key in {"propertyName","sourceRun","windows","date","status",
                       "roomCount","priceCount","observedPriceCount","technicalReason","ota","message",
                       "recipient","strategy","decision"}
            and isinstance(value,(str,int,float,bool,list))
        }
        # Only bounded scalar strings and compact date-window dictionaries.
        for key,value in list(safe_details.items()):
            if isinstance(value,str): safe_details[key]=value[:220]
            if isinstance(value,list):
                safe_details[key]=[
                    {k:str(v)[:70] for k,v in item.items()
                     if k in {"requestedCheckin","requestedCheckout","checkin",
                              "checkout","status","nights","adults"}}
                    for item in value[:16] if isinstance(item,dict)
                ]
        event={
            "from":sender,"to":str(safe_details.get("recipient") or (
                "ota_specialists" if event_type=="booking_reference" else "giove"))[:60],
            "type":event_type,"createdAt":datetime.now(timezone.utc).isoformat(),
            "details":safe_details,
        }
        payload["events"]=(payload["events"]+[event])[-MAILBOX_LIMIT:]
        dest.parent.mkdir(parents=True,exist_ok=True)
        temporary=dest.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        temporary.replace(dest)
        return event



MANUAL_OTA_AGENT_NAMES={
    "expedia":("Ercole","Expedia"),
    "vrbo":("Atlante","Vrbo"),
    "holidu":("Mercurio","Holidu"),
    "trip":("Turing","Trip.com"),
    "priceline":("Pitagora","Priceline"),
    "hotels":("Tesla","Hotels.com"),
    "travelocity":("Newton","Travelocity"),
}


def manual_ota_presence_path(property_id):
    return AGENT_RESULTS / safe_property_id(property_id) / "manual-ota-presence.json"


def read_manual_ota_presence(property_id):
    path=manual_ota_presence_path(property_id)
    try:
        payload=json.loads(path.read_text(encoding="utf-8"))
        if payload.get("propertyId")==property_id and isinstance(payload.get("observations"),dict):
            return payload
    except (OSError,ValueError,TypeError,AttributeError):
        pass
    return {"schema":"velora-manual-ota-presence-v1",
            "propertyId":property_id,"propertyName":"","observations":{}}


def record_manual_ota_presence(property_id, property_name, ota_id, action):
    """Persist operator's negative search result, distinct from confirmed absence.

    A manual non-detection never invalidates previously acquired OTA rates,
    invents an empty inventory, or changes the actual specialist agent result.
    """
    property_id=safe_property_id(property_id)
    property_name=str(property_name or "").strip()
    if not 2<=len(property_name)<=180:
        raise ValueError("Nome struttura non valido")
    if ota_id not in MANUAL_OTA_AGENT_NAMES:
        raise ValueError("OTA non supportata")
    if action not in {"not_found","clear"}:
        raise ValueError("Operazione non valida")
    actor,ota_label=MANUAL_OTA_AGENT_NAMES[ota_id]
    with MAILBOX_LOCK:
        payload=read_manual_ota_presence(property_id)
        if payload.get("propertyName") and payload["propertyName"]!=property_name:
            raise ValueError("Segnalazioni manuali associate a un'altra struttura")
        observations=payload["observations"]
        existing=observations.get(ota_id) or {}
        if action=="not_found":
            if existing.get("status")=="not_found_by_operator":
                return existing
            result={
                "otaId":ota_id,"status":"not_found_by_operator",
                "source":"operator_manual_search",
                "reportedAt":datetime.now(timezone.utc).isoformat(),
                "absenceConfirmed":False,
            }
            observations[ota_id]=result
            message=(f"{actor} a Giove: l'operatore ha cercato manualmente "
                     f"{ota_label} per questa struttura e non ha individuato "
                     "una scheda pertinente. Possibile asimmetria di presenza "
                     "da verificare; non equivale ad assenza confermata.")
        else:
            if ota_id not in observations:
                return {"otaId":ota_id,"status":"cleared"}
            observations.pop(ota_id,None)
            result={"otaId":ota_id,"status":"cleared"}
            message=(f"{actor} a Giove: l'operatore ha ritirato la segnalazione "
                     f"di scheda non rilevata su {ota_label}. "
                     "Non utilizzarla più come evidenza di presenza negativa.")
        payload["propertyName"]=property_name
        path=manual_ota_presence_path(property_id)
        path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        temporary.replace(path)
        agent_mailbox_publish(property_id,ota_id,"manual_presence",{
            "propertyName":property_name,"ota":ota_id,
            "recipient":"giove",
            "status":result["status"],
            "strategy":"operator_manual_search",
            "message":message,
        })
        return result


def agent_mailbox_reference(property_id, property_name):
    """Read only the latest Booking handoff for the same structure."""
    try:
        payload=json.loads(agent_mailbox_path(property_id).read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError):
        return None
    if payload.get("propertyId")!=property_id:
        return None
    for event in reversed(payload.get("events") or []):
        if event.get("from")=="booking" and event.get("type")=="booking_reference":
            details=event.get("details") or {}
            if details.get("propertyName")==property_name:
                return details
            return None
    return None


def specialist_peer_consultation(property_id, agent_id, expected_name, stage, stay, facts):
    """Runtime collaboration: actual request, reply and Giove decision before retry.

    Only a small, preapproved same-page reading strategy can be returned.
    No peer supplies rates, URLs, JavaScript, credentials or browser commands.
    """
    if (agent_id,stage) not in {
        ("agoda","pricing_help"),("agoda","recovery_result"),
        ("airbnb","identity_help")
    }:
        return {"approved":False,"reason":"outside_specialist_scope"}
    reference=agent_mailbox_reference(property_id,expected_name)
    requested=(str(stay.get("requestedCheckin") or stay.get("checkin") or ""),
               str(stay.get("requestedCheckout") or stay.get("checkout") or ""))
    actual=(str(stay.get("checkin") or ""),str(stay.get("checkout") or ""))
    matching=bool(reference and any(
        (str(row.get("requestedCheckin") or ""),str(row.get("requestedCheckout") or ""))==requested
        and (str(row.get("checkin") or ""),str(row.get("checkout") or ""))==actual
        for row in reference.get("windows") or []
    ))
    if agent_id=="airbnb":
        observed=str(facts.get("observedTitle") or "")[:160]
        agent_mailbox_publish(property_id,"airbnb","help_request",{
            "recipient":"booking",
            "message":(
                f"Minerva, ho trovato su Airbnb una struttura intitolata «{observed}», "
                f"diversa da «{expected_name}». Confermi che non devo "
                "riutilizzare questa scheda per i soggiorni successivi?"
            ),
        })
        agent_mailbox_publish(property_id,"booking","help_reply",{
            "recipient":"airbnb","strategy":"quarantine_wrong_property",
            "message":(
                f"Apollo, il riferimento è «{expected_name}» e le date restano "
                f"{actual[0]} → {actual[1]}. Non riutilizzare quella URL "
                "e cerca soltanto annunci della struttura richiesta."
            ),
        })
        agent_mailbox_publish(property_id,"giove","review_decision",{
            "recipient":"airbnb","decision":"quarantine_wrong_property",
            "message":(
                "Titolo di struttura diversa già riscontrato: scarta "
                "la candidata, non usarne i prezzi e non visitarla "
                "di nuovo negli altri campioni."
            ),
        })
        return {"approved":True,"strategy":"quarantine_wrong_property"}
    count_prices=max(0,min(int(facts.get("numericEuroPrices") or 0),1000))
    count_rooms=max(0,min(int(facts.get("actualRoomNames") or 0),1000))
    if stage=="recovery_result":
        outcome=str(facts.get("status") or "unverified")[:80]
        agent_mailbox_publish(property_id,"agoda","pricing_observed",{
            "recipient":"giove","ota":"agoda",
            "message":(
                f"Minerva, ho eseguito il controllo autorizzato su Agoda "
                f"per {actual[0]} → {actual[1]}. Esito: {outcome}. "
                f"Offerte validate: {max(0,int(facts.get('verifiedQuotes') or 0))}."
            ),
            "status":outcome,
        })
        return {"approved":False,"reason":"completed"}
    agent_mailbox_publish(property_id,"agoda","help_request",{
        "recipient":"booking","ota":"agoda",
        "message":(
            f"Minerva, sulla scheda Agoda per {actual[0]} → {actual[1]} "
            f"vedo {count_rooms} camere e {count_prices} elementi di prezzo, "
            "ma non riesco ad attribuirli alle offerte. Hai un metodo "
            "di verifica da suggerirmi?"
        ),
        "technicalReason":"unmatched_room_price_evidence",
    })
    if not matching:
        agent_mailbox_publish(property_id,"giove","review_decision",{
            "recipient":"agoda","decision":"blocked_no_exact_booking_lock",
            "message":"Riferimento Booking non coincidente: recupero non autorizzato.",
        })
        return {"approved":False,"reason":"booking_lock_mismatch"}
    strategy=(
        "same_page_offer_mapping" if count_rooms>0 and count_prices>0
        else "same_page_room_grid_recheck"
    )
    next_action=(
        "Hai già rilevato camere e prezzi: controlla la corrispondenza "
        "tra ogni riga offerta, la sua camera e il prezzo corrente a notte."
        if strategy=="same_page_offer_mapping" else
        "Le offerte non risultano renderizzate: raggiungi la griglia camere "
        "e attendi il caricamento prima di cercare i prezzi."
    )
    agent_mailbox_publish(property_id,"booking","help_reply",{
        "recipient":"agoda","strategy":strategy,
        "message":(
            f"Galileo, confermo {actual[0]} → {actual[1]}. "
            +next_action+" Rimani sulla tua OTA: non usare le mie tariffe."
        ),
    })
    agent_mailbox_publish(property_id,"giove","review_decision",{
        "recipient":"agoda","decision":"approved_one_same_page_recheck",
        "message":(
            "Autorizzo un solo ulteriore controllo sulla stessa pagina Agoda "
            "e sulle medesime date. Nessuna navigazione incrociata, "
            "nessun bypass, nessun prezzo inventato."
        ),
    })
    return {"approved":True,"strategy":strategy,"maxAttempts":1}


def agent_mailbox_result(property_id,agent_id):
    """Publish diagnostic facts, not an invented commercial availability verdict."""
    try:
        result=json.loads(agent_output(property_id,agent_id).read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError):
        return
    if agent_id=="official_site":
        lock=(result.get("directCommercialAudit") or {}).get("masterStay") or {}
        if lock.get("status")=="direct_price_observed" and lock.get("checkin") and lock.get("checkout"):
            agent_mailbox_publish(property_id,"official_site","direct_master",{
                "propertyName":result.get("propertyName",""),
                "recipient":"booking",
                "status":"direct_price_observed",
                "windows":[lock],
                "roomCount":int(lock.get("roomCount") or 0),
                "priceCount":int(lock.get("priceCount") or 0),
                "message":"Leonardo: tariffe dirette trovate. Minerva, verifica esattamente queste date e questi ospiti senza spostarle.",
            },reset=True)
        return
    if agent_id=="booking":
        locks=[row for row in result.get("bookingReferenceStays") or []
               if isinstance(row,dict) and row.get("status") in {
                   "initial_dates_available","shifted_to_available_booking_dates","direct_master_checked"}]
        if locks:
            counted=sum(len(row.get("quotes") or [])
                for row in result.get("observations") or []
                if row.get("otaId")=="booking")
            from_direct=any(row.get("status")=="direct_master_checked" for row in locks)
            agent_mailbox_publish(property_id,"booking","booking_reference",{
                "propertyName":result.get("propertyName",""),
                "sourceRun":result.get("createdAt",""),
                "windows":locks,
                "roomCount":counted,
                "status":"direct_master_checked" if from_direct else "booking_dates_confirmed",
                "message":(
                    "Minerva: ho cercato le date fornite da Leonardo senza modificarle. "
                    +str(counted)+" offerte Booking osservate. "
                    +"Le altre OTA devono cercare identiche date e occupazione; "
                    +"l'assenza di prezzo Booking richiede verifica dell'asimmetria."
                    if from_direct else
                    "Minerva: date di riferimento Booking condivise con gli altri specialisti."
                ),
            },reset=False)
        return
    if agent_id not in {"official_site","reviews"}:
        rows=[row for row in result.get("observations") or []
              if row.get("otaId")==agent_id]
        if not rows:
            if agent_id=="airbnb":
                agent_mailbox_publish(property_id,"airbnb","pricing_read_failure",{
                    "propertyName":result.get("propertyName",""),
                    "recipient":"booking","ota":"airbnb",
                    "status":"no_ota_observations",
                    "message":"Apollo a Minerva: ho terminato la ricerca Airbnb, ma non ho una scheda con identità e tariffe verificabili. Non considero questa situazione una prova che l'annuncio sia assente; segnalo il confronto come non verificato.",
                })
                agent_mailbox_publish(property_id,"airbnb","pricing_read_failure",{
                    "propertyName":result.get("propertyName",""),
                    "recipient":"giove","ota":"airbnb",
                    "status":"reviews_unverified",
                    "message":"Apollo a Giove: non ho una scheda Airbnb verificata per questa struttura, quindi non posso confermare numero o valutazione delle recensioni. Registra la copertura reputazionale come non verificata, non come zero recensioni.",
                })
            return
        prices=sum(len([q for q in row.get("quotes") or [] if q.get("verified")])
                   for row in rows)
        weak=[row for row in rows if row.get("status") in {
            "needs_human_review","no_public_rate","dates_unconfirmed",
            "quote_candidates_unverified"}]
        errors=[row for row in rows if row.get("status") in {
            "rate_limited","access_blocked","blocked","http_error","login_required",
            "portal_redirect"}]
        rejected=[row for row in rows if row.get("status") in {
            "wrong_property_listing","identity_mismatch","wrong_property"
        } or row.get("identityQuarantined")]
        room_count=max((int((row.get("rateDiagnostics") or {}).get("actualRoomNames") or 0)
                        for row in rows),default=0)
        seen_prices=max((int((row.get("rateDiagnostics") or {}).get("numericEuroPrices") or 0)
                         for row in rows),default=0)
        explicit_absence=bool(rows) and all(
            row.get("status") in {"listing_not_found","not_listed","no_listing_confirmed",
                                  "listing_absent_confirmed"}
            and row.get("sourceIdentityVerified") is not True
            for row in rows
        )
        event_type=("identity_rejected" if rejected and prices==0 else
                    "technical_block" if errors else
                    "pricing_read_failure" if (weak or explicit_absence or prices==0) else
                    "pricing_observed")
        diagnostic=", ".join(dict.fromkeys(
            str(row.get("status") or "") for row in (rejected or errors or weak)))[:180]
        sender_name={"agoda":"Galileo","airbnb":"Apollo","vrbo":"Atlante",
                     "expedia":"Ercole"}.get(agent_id,agent_id.title())
        message=(
            f"{sender_name} a Minerva: ho scartato un annuncio che appartiene a un'altra struttura. "

            "Nessun prezzo attribuito e nessuna prova di assenza su questa OTA."
            if event_type=="identity_rejected" else
            (f"{sender_name} a Minerva: la ricerca su Airbnb non ha individuato una scheda verificabile della struttura. Segnalo una possibile assenza dell'annuncio, ma senza prova sufficiente non dichiaro che la struttura non sia presente. Verifichiamo la distribuzione e le recensioni."
             if explicit_absence else
             f"{sender_name} a Minerva: ho esaminato la mia OTA e trovato {room_count} intestazioni camera "
             f"e {seen_prices} elementi di prezzo, ma solo {prices} offerte validate. "
             f"Esito: {diagnostic or 'lettura non conclusiva'}. Non deduco indisponibilità dalla sola mancanza di prezzi.")
            if event_type=="pricing_read_failure" else
            f"{sender_name} a Minerva: ricerca conclusa sulle date ricevute. Tariffe validate: {prices}. "
            f"Esito: {diagnostic or 'nessun blocco documentato'}."
        )
        if agent_id=="airbnb":
            # Review figures come exclusively from identity-verified page evidence;
            # do not infer missing reviews from an absent listing.
            profiles=result.get("otaProfiles") or {}
            airbnb_profile=profiles.get("airbnb") or {}
            review_count=airbnb_profile.get("reviewCount")
            rating=airbnb_profile.get("rating")
            if airbnb_profile.get("status")=="sampled" and (rating is not None or review_count is not None):
                for colleague in ("booking","agoda"):
                    try:
                        colleague_result=json.loads(agent_output(property_id,colleague).read_text(encoding="utf-8"))
                        if colleague_result.get("propertyId")!=property_id or colleague_result.get("propertyName")!=result.get("propertyName"):
                            continue
                        other=(colleague_result.get("otaProfiles") or {}).get(colleague) or {}
                        if other.get("status")!="sampled":
                            continue
                        their_count=other.get("reviewCount")
                        their_rating=other.get("rating")
                        if review_count is not None and their_count is not None:
                            agent_mailbox_publish(property_id,"airbnb","review_decision",{
                                "propertyName":result.get("propertyName",""),
                                "recipient":"giove","ota":"airbnb",
                                "status":"review_count_difference_observed",
                                "message":f"Apollo a Giove: Airbnb mostra {review_count} recensioni, {colleague.capitalize()} ne mostra {their_count}. È una differenza di copertura e volume delle recensioni, non necessariamente un errore di distribuzione.",
                            })
                        if rating is not None and their_rating is not None and airbnb_profile.get("ratingScale") and airbnb_profile.get("ratingScale")==other.get("ratingScale"):
                            agent_mailbox_publish(property_id,"airbnb","review_decision",{
                                "propertyName":result.get("propertyName",""),
                                "recipient":"giove","ota":"airbnb",
                                "status":"review_rating_difference_observed",
                                "message":f"Apollo a Giove: sulla stessa scala di valutazione Airbnb mostra {rating}, {colleague.capitalize()} {their_rating}. Verifica la differenza prima di qualificarla come asimmetria reputazionale.",
                            })
                    except (OSError,ValueError,TypeError):
                        continue
                agent_mailbox_publish(property_id,"airbnb","pricing_observed",{
                    "propertyName":result.get("propertyName",""),
                    "recipient":"giove","ota":"airbnb",
                    "status":"review_evidence",
                    "message":f"Apollo a Giove: sulla scheda Airbnb associata alla struttura ho letto valutazione {rating if rating is not None else 'non visibile'} e {review_count if review_count is not None else 'numero non visibile'} recensioni. Confronta questi dati con Booking e Agoda, se disponibili; differenze e assenze richiedono verifica.",
                })
            else:
                agent_mailbox_publish(property_id,"airbnb","pricing_read_failure",{
                    "propertyName":result.get("propertyName",""),
                    "recipient":"giove","ota":"airbnb",
                    "status":"reviews_unverified",
                    "message":"Apollo a Giove: non ho un dato di recensioni Airbnb verificato per questa struttura. Segnalo il confronto reputazionale come incompleto, senza attribuire zero recensioni né inventare differenze.",
                })
        agent_mailbox_publish(property_id,agent_id,event_type,{
            "ota":agent_id,"priceCount":prices,"roomCount":room_count,
            "observedPriceCount":seen_prices,
            "technicalReason":diagnostic,
            "status":"evidence_only_no_cross_ota_navigation",
            "message":message,
        })


def vrbo_presence_path(property_id):
    return AGENT_RESULTS / safe_property_id(property_id) / "vrbo-presence.json"


def classify_stored_vrbo_presence(property_id):
    with VRBO_PRESENCE_LOCK:
        item=dict(VRBO_PRESENCE_RUNS.get(property_id) or {})
    if item:
        return item
    target=vrbo_presence_path(property_id)
    try:
        value=json.loads(target.read_text(encoding="utf-8"))
    except (OSError,ValueError):
        return {"propertyId":property_id,"state":"not_started"}
    if value.get("propertyId")!=property_id:
        return {"propertyId":property_id,"state":"not_started"}
    return {"propertyId":property_id,"state":"completed","result":value}


async def _discover_vrbo_presence(data, property_id):
    profile_dir=AGENT_RESULTS/property_id/"vrbo-presence-public-chrome"
    profile_dir.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as playwright:
        # Separate browser profile; no saved accounts or Vrbo credentials.
        context=await browser_pilot._launch_velora_context(
            playwright,profile_dir,data,"Ricerca presenza pubblica Vrbo",True)
        try:
            discovery=await browser_pilot.discover_vrbo_property_listings(context,data,{})
        finally:
            await context.close()
    if agent_network is None:
        raise RuntimeError(specialist_unavailable_message())
    return agent_network.classify_vrbo_presence(discovery,property_id,data["name"])


def run_vrbo_presence_job(data, property_id):
    try:
        with AGENT_WORK_SLOTS:
            with VRBO_PRESENCE_LOCK:
                VRBO_PRESENCE_RUNS[property_id]={
                    "propertyId":property_id,"state":"running",
                    "message":"Atlante sta cercando schede Vrbo per nome e località."
                }
            result=asyncio.run(_discover_vrbo_presence(data,property_id))
            target=vrbo_presence_path(property_id)
            target.parent.mkdir(parents=True,exist_ok=True)
            tmp=target.with_suffix(".tmp")
            tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
            tmp.replace(target)
            with VRBO_PRESENCE_LOCK:
                VRBO_PRESENCE_RUNS[property_id]={
                    "propertyId":property_id,"state":"completed","result":result
                }
    except Exception as exc:
        with VRBO_PRESENCE_LOCK:
            VRBO_PRESENCE_RUNS[property_id]={
                "propertyId":property_id,"state":"failed",
                "error":("La ricerca pubblica non è riuscita: "+type(exc).__name__)[:240]
            }


def agent_validation_output(property_id):
    return AGENT_RESULTS / property_id / "validation.json"


def specialist_progress(agent_id, run_state, result_path):
    """Live progress based on persisted checkpoints, never elapsed-time guesses.

    This reads the incremental JSON written by the existing pilot and does
    not navigate or alter any OTA parser.
    """
    state=run_state.get("state") or ""
    if state=="completed":
        return {"progress":100,"phase":"Analisi terminata","progressDetail":"Esito archiviato; Giove non ha ancora validato le evidenze."}
    if state=="queued":
        return {"progress":0,"phase":"In coda","progressDetail":"In attesa dello slot browser."}
    if state not in ("running","failed"):
        return {"progress":0,"phase":"Non avviato","progressDetail":""}
    phase="Avvio browser"
    detail="Apertura Chrome e identificazione struttura."
    progress=2
    try:
        snapshot=json.loads(result_path.read_text(encoding="utf-8"))
        if snapshot.get("propertyId") != run_state.get("propertyId", snapshot.get("propertyId")):
            raise ValueError("Risultato di struttura diversa")
        if snapshot.get("identityResolution"):
            progress,phase,detail=12,"Identificazione completata","Ricerca della scheda OTA selezionata."
        discovery=snapshot.get("discoveryProgress") or {}
        if discovery:
            total=max(1,int(discovery.get("total") or 1))
            found=min(total,max(0,int(discovery.get("completed") or 0)))
            progress=max(progress,20+int(25*found/total))
            phase,detail="Ricerca scheda OTA",f"Discovery: {found}/{total} canali selezionati."
        phases=snapshot.get("browserPhases") or []
        if any(item.get("phase")=="discovery" and item.get("status")=="completed" for item in phases):
            progress=max(progress,48)
            phase,detail="Ricerca completata","Preparazione della verifica delle date e tariffe."
        if any(item.get("phase")=="pricing" for item in phases):
            progress=max(progress,54)
            phase,detail="Verifica tariffe","Preparazione e controllo dei preventivi."
        reference_identity=snapshot.get("bookingReferenceIdentity") or {}
        if reference_identity.get("status")=="mismatch_or_unverified":
            progress=max(progress,55)
            phase="Booking non corrisponde"
            detail=(
                "Scheda Booking scartata: "
                + str(reference_identity.get("observedProperty") or "identità non verificata")[:80]
                + ". Nessuna ricerca Booking su questa struttura; prezzi OTA non comparabili."
            )
        plan=snapshot.get("plan") or []
        months=max(1,len(plan))
        locks=min(months,len(snapshot.get("bookingReferenceStays") or []))
        if locks:
            progress=max(progress,54+int(14*locks/months))
            phase,detail="Date Booking di riferimento",f"Finestre di soggiorno determinate: {locks}/{months}."
        observations=snapshot.get("observations") or []
        expected=months*max(1,len(snapshot.get("selectedChannels") or [agent_id]))
        processed=min(expected,len(observations))
        if processed:
            progress=max(progress,68+int(28*processed/expected))
            phase,detail="Rilevazione OTA",f"Controlli tariffari registrati: {processed}/{expected}."
        if any(item.get("phase")=="pricing" and item.get("status")=="completed" for item in phases):
            progress=max(progress,98)
            phase,detail="Controlli conclusi","Salvataggio del risultato."
    except (OSError,ValueError,TypeError,AttributeError):
        pass
    if state=="failed":
        return {"progress":min(progress,99),"phase":"Interrotto con errore","progressDetail":str(run_state.get("error") or detail)[:220]}
    return {"progress":min(progress,99),"phase":phase,"progressDetail":detail}


def run_specialist_job(property_id,agent_id,property_file,months,custom_period,ghost,assisted,account_profile=None):
    key=(property_id,agent_id)
    try:
        print_agent_status(agent_id,"Avvio","IN CODA","Attesa di uno slot Chrome indipendente")
        with AGENT_WORK_SLOTS:
            print_agent_status(agent_id,"Browser / scraping","IN CORSO",property_id)
            with AGENT_RUN_LOCK:
                AGENT_RUNS[key]["state"]="running"
                AGENT_RUNS[key]["runningAt"]=datetime.now(timezone.utc).isoformat()
            data=json.loads(Path(property_file).read_text(encoding="utf-8"))
            if account_profile and agent_id in {"expedia","vrbo","holidu"} and PORTAL_SESSIONS is not None:
                portal_state=PORTAL_SESSIONS.statuses().get(agent_id,{})
                if portal_state.get("state")=="ready":
                    print_agent_status(agent_id,"Login Account","CONFERMATO","Riuso profilo Chrome appena verificato")
                elif PORTAL_SESSIONS.has_credentials(agent_id):
                    raise RuntimeError("Prima effettua «Accedi e verifica» nella scheda dell\'agente e completa la verifica con codice; scansione non avviata.")
                else:
                    print_agent_status(agent_id,"Profilo Chrome","DA VERIFICARE","Profilo locale presente; login non confermato")
            # La finestra con PREZZI realmente osservati da Leonardo prevale
            # su date richieste non verificate. Solo per la stessa struttura.
            if agent_id=="booking":
                # Actual mailbox request precedes reading Leonardo's saved result.
                agent_mailbox_publish(property_id,"booking","help_request",{
                    "propertyName":str(data.get("name") or ""),
                    "recipient":"official_site",
                    "strategy":"reuse_direct_master",
                    "message":"Minerva a Leonardo: inviami le date, le notti e gli ospiti della prima ricerca con tariffe prenotabili. Userò lo stesso periodo su Booking.",
                })
                try:
                    direct=json.loads(agent_output(property_id,"official_site").read_text(encoding="utf-8"))
                    lock=(direct.get("directCommercialAudit") or {}).get("masterStay") or {}
                    if (direct.get("propertyId")==property_id
                        and direct.get("propertyName")==data.get("name")
                        and lock.get("status")=="direct_price_observed"):
                        data["_directMasterStay"]=lock
                        agent_mailbox_publish(property_id,"official_site","help_reply",{
                            "propertyName":str(data.get("name") or ""),
                            "recipient":"booking",
                            "strategy":"direct_master_confirmed",
                            "windows":[lock],
                            "status":"direct_price_observed",
                            "priceCount":int(lock.get("priceCount") or 0),
                            "roomCount":int(lock.get("roomCount") or 0),
                            "message":"Leonardo a Minerva: questi sono i parametri della ricerca con tariffe osservate. Confrontali su Booking senza modificare le date.",
                        })
                        print_agent_status(agent_id,"Leonardo MASTER","RICEVUTA",
                            str(lock.get("checkin"))+" → "+str(lock.get("checkout")))
                except (OSError,ValueError,TypeError):
                    pass
            # Dialogo operativo: richiesta e risposta registrate soltanto
            # dopo che il server ha già validato l'exact-date lock di Minerva.
            # Non è una simulazione di un risultato OTA; la risposta comunica
            # esclusivamente le date della ricerca precedente.
            if agent_id not in {"booking","official_site","reviews"}:
                reference=agent_mailbox_reference(property_id,str(data.get("name") or ""))
                locks=data.get("_specialistBookingLocks") or []
                if reference and locks:
                    first=locks[0]
                    wanted=(str(first.get("checkin") or ""),str(first.get("checkout") or ""))
                    from_mailbox=any(
                        (str(w.get("checkin") or ""),str(w.get("checkout") or ""))==wanted
                        for w in reference.get("windows") or [] if isinstance(w,dict))
                    if from_mailbox:
                        names={"agoda":"Galileo","airbnb":"Airbnb","expedia":"Ercole",
                               "vrbo":"Atlante","holidu":"Holidu"}
                        colleague=names.get(agent_id,agent_id.title())
                        interval=wanted[0]+" → "+wanted[1]
                        guests=int(first.get("adults") or 2)
                        nights=int(first.get("nights") or 0)
                        agent_mailbox_publish(property_id,agent_id,"help_request",{
                            "propertyName":str(data.get("name") or ""),
                            "recipient":"booking","strategy":"exact_date_handoff",
                            "message":f"{colleague} a Minerva: sto per controllare la mia OTA. Mi confermi le date e gli ospiti che hai confrontato con Leonardo?",
                        })
                        agent_mailbox_publish(property_id,"booking","help_reply",{
                            "propertyName":str(data.get("name") or ""),
                            "recipient":agent_id,"strategy":"exact_date_handoff",
                            "windows":locks,"status":"reused_minerva_lock",
                            "message":f"Minerva a {colleague}: confermo {interval}, {nights} notti e {guests} adulti. Leonardo ha identificato il periodo sul sito diretto. Cerca queste stesse date e segnalami eventuali differenze.",
                        })
                        agent_mailbox_publish(property_id,agent_id,"help_reply",{
                            "propertyName":str(data.get("name") or ""),
                            "recipient":"booking","strategy":"exact_date_handoff_ack",
                            "message":f"{colleague} a Minerva: ricevuto. Verificherò {interval} per {guests} adulti su {agent_id.capitalize()}; non cambierò il periodo per trovare prezzi diversi.",
                        })
                        print_agent_status(agent_id,"Mailbox Booking","RICEVUTA",
                            f"{len(locks)} finestre, identità struttura verificata")

            peer_callback=(
                lambda stage,stay,facts: specialist_peer_consultation(
                    property_id,agent_id,str(data.get("name") or ""),
                    stage,stay,facts
                )
            ) if agent_id in {"agoda","airbnb"} else None
            # Beta OTA: a frozen frontend must not occupy a Chrome slot for
            # 15+ minutes with no terminal result. The limit covers the whole
            # public search, keeps prior results from other agents untouched,
            # and reports an explicit timeout rather than invented zero rates.
            slow_public_specialists={"hotels","travelocity","trip","priceline"}
            windows=1 if custom_period else (13 if months==12 else max(1,int(months)))
            budget_seconds=min(900,420+60*max(0,windows-1))
            coroutine=agent_network.execute(
                agent_id,data,Path(property_file),agent_output(property_id,agent_id),
                months=months,custom_period=custom_period,ghost=ghost,
                assisted=False,assist_callback=None,
                authorized_profile_dir=Path(account_profile) if account_profile else None,
                peer_callback=peer_callback,
            )
            try:
                if agent_id in slow_public_specialists:
                    asyncio.run(asyncio.wait_for(coroutine,timeout=budget_seconds))
                else:
                    asyncio.run(coroutine)
            except (asyncio.TimeoutError,TimeoutError) as exc:
                raise TimeoutError(
                    f"{agent_id}: tempo limite di {budget_seconds//60} minuti superato "
                    "durante la ricerca pubblica. Il portale non ha completato la lettura "
                    "e le tariffe non sono considerate validate. Conservati i risultati "
                    "già archiviati dagli altri agenti."
                ) from exc
            agent_mailbox_result(property_id,agent_id)
        print_agent_status(agent_id,"Esecuzione","COMPLETATO","Esito salvato, in attesa del check di Giove")
        with AGENT_RUN_LOCK:
            AGENT_RUNS[key]["state"]="completed"
            AGENT_RUNS[key]["completedAt"]=datetime.now(timezone.utc).isoformat()
    except Exception as exc:
        error=f"{type(exc).__name__}: {str(exc)[:300]}"
        with AGENT_RUN_LOCK:
            AGENT_RUNS[key]["state"]="failed"
            AGENT_RUNS[key]["error"]=error
            AGENT_RUNS[key]["completedAt"]=datetime.now(timezone.utc).isoformat()
        print_agent_status(agent_id,"Esecuzione","ERRORE",error)



def _notify_windows_intervention(intervention: dict) -> None:
    """Show a user-dismissable Windows dialog without unblocking the pilot.

    The actual scraping pause is controlled solely by intervention_event;
    closing this dialog never resumes scraping.
    """
    if os.name != "nt":
        return
    try:
        import ctypes
        name=str(intervention.get("label") or "OTA")[:80]
        reason=str(intervention.get("reason") or "")[:280]
        message=(
            "VELORA E' IN PAUSA - VAI ED AGISCI!\n\n"
            + "Portale: "+name+"\n"+reason+"\n\n"
            + "1. Premi OK e controlla la finestra Chrome gia' aperta.\n"
            + "2. Completa solo eventuali verifiche pubbliche che vedi.\n"
            + "3. Torna su Velora con ALT+TAB.\n"
            + "4. Premi 'Ho completato - riprendi' o 'Salta questa OTA'.\n\n"
            + "La scansione resta ferma fino al tuo comando (max 15 minuti)."
        )
        flags=0x00000000 | 0x00000030 | 0x00040000 | 0x00010000
        ctypes.windll.user32.MessageBoxW(None,message,"VELORA - INTERVENTO UMANO RICHIESTO",flags)
    except Exception as exc:
        print(f"Windows alert non disponibile: {type(exc).__name__}",flush=True)


def wait_for_pilot_intervention(payload: dict) -> str:
    """Espone una richiesta di assistenza all'interfaccia e attende la risposta dell'utente."""
    intervention={
        "id":secrets.token_hex(8),
        "type":str(payload.get("type") or "portal_help"),
        "otaId":str(payload.get("otaId") or ""),
        "label":str(payload.get("label") or payload.get("otaId") or "OTA"),
        "reason":str(payload.get("reason") or "")[:1200],
        "instructions":str(payload.get("instructions") or "")[:1800],
        "propertyName":str(payload.get("propertyName") or "")[:220],
        "city":str(payload.get("city") or "")[:160],
        "url":str(payload.get("url") or "")[:1800],
        "stay":payload.get("stay") if isinstance(payload.get("stay"),dict) else {},
        "requestedAt":str(payload.get("requestedAt") or ""),
    }
    with STATE.lock:
        STATE.intervention=intervention
        STATE.intervention_action=""
        STATE.intervention_event.clear()
    print(
        f"INTERVENTO UTENTE · {intervention['label']} · {intervention['type']} · "
        f"{intervention['reason'][:220]} · ATTESA REALE 900s",
        flush=True,
    )
    # A browser tab may cover the Velora web UI. Make the request visible on
    # Windows itself while leaving the actual wait controlled by the web UI.
    if os.name == "nt":
        threading.Thread(
            target=_notify_windows_intervention,
            args=(dict(intervention),),
            name="velora-manual-assistance-alert",
            daemon=True,
        ).start()
    signaled=STATE.intervention_event.wait(timeout=900)
    with STATE.lock:
        action=STATE.intervention_action if signaled else "timeout"
        STATE.intervention={}
        STATE.intervention_action=""
        STATE.intervention_event.clear()
    if not signaled:
        print(f"INTERVENTO UTENTE scaduto · {intervention['label']}",flush=True)
    else:
        print(f"INTERVENTO UTENTE risposta={action} · {intervention['label']}",flush=True)
    return action or "timeout"



def _norm(value):
    text=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode("ascii").lower()
    return " ".join(re.findall(r"[a-z0-9]+",text))


def _catalog_file():
    for path in CATALOG_PATHS:
        if path.exists():
            return path
    return None


def _xlsx_database_rows(path):
    ns="{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel_ns="{http://schemas.openxmlformats.org/package/2006/relationships}"
    office_rel="{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as z:
        shared=[]
        if "xl/sharedStrings.xml" in z.namelist():
            root=ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(ns+"si"):
                shared.append("".join(t.text or "" for t in si.iter(ns+"t")))
        wb=ET.fromstring(z.read("xl/workbook.xml"))
        rels=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        relmap={node.attrib["Id"]:node.attrib["Target"] for node in rels.findall(rel_ns+"Relationship")}
        target=None
        for sheet in wb.find(ns+"sheets"):
            if sheet.attrib.get("name")=="Database":
                target=relmap.get(sheet.attrib.get(office_rel))
                break
        if not target:
            raise ValueError("Foglio Database non trovato nel file Excel")
        if not target.startswith("xl/"):
            target="xl/"+target.lstrip("/")
        root=ET.fromstring(z.read(target))
        rows=[]
        headers={}
        for row in root.find(ns+"sheetData"):
            rn=int(row.attrib.get("r","0"))
            values={}
            for cell in row.findall(ns+"c"):
                ref=cell.attrib.get("r","")
                col=re.match(r"[A-Z]+",ref)
                if not col:
                    continue
                typ=cell.attrib.get("t")
                v=cell.find(ns+"v")
                inline=cell.find(ns+"is")
                value=""
                if typ=="s" and v is not None:
                    try: value=shared[int(v.text)]
                    except Exception: value=""
                elif typ=="inlineStr" and inline is not None:
                    value="".join(t.text or "" for t in inline.iter(ns+"t"))
                elif v is not None:
                    value=v.text or ""
                values[col.group(0)]=value
            if rn==7:
                headers={col:str(value).strip() for col,value in values.items()}
            elif rn>=8 and values:
                rows.append({headers.get(col,col):value for col,value in values.items() if headers.get(col)})
        return rows


def load_structure_catalog():
    path=_catalog_file()
    if not path:
        return {"loaded":False,"path":"","records":[],"summary":{"count":0,"websites":0,"emails":0}}
    try:
        rows=_xlsx_database_rows(path)
    except Exception as exc:
        return {"loaded":False,"path":str(path),"records":[],"error":f"{type(exc).__name__}: {str(exc)[:240]}","summary":{"count":0,"websites":0,"emails":0}}
    records=[]
    for row in rows:
        name=str(row.get("Nome albergo") or "").strip()
        city=str(row.get("Comune") or "").strip()
        if not name or not city:
            continue
        website=str(row.get("Sito internet") or "").strip()
        if website and not re.match(r"^https?://",website,re.I):
            if re.search(r"\.[a-z]{2,}(?:/|$)",website,re.I) and "@" not in website and " " not in website.lower().replace("no website",""):
                website="https://"+website.lstrip("/")
            else:
                website=""
        record={
            "region":str(row.get("Regione") or "").strip(),
            "province":str(row.get("Provincia") or "").strip(),
            "city":city,
            "name":name,
            "address":str(row.get("Indirizzo") or "").strip(),
            "rooms":str(row.get("N. camere") or "").strip(),
            "email":str(row.get("Email") or "").strip(),
            "website":website,
            "propertyType":str(row.get("Tipologia") or "").strip(),
            "stars":str(row.get("Categoria / stelle") or "").strip(),
            "familyStatus":str(row.get("Conduzione familiare") or "").strip(),
            "code":str(row.get("Codice CIN/CIR/CUSR") or "").strip(),
            "source":str(row.get("Fonte") or "").strip(),
        }
        record["_nameNorm"]=_norm(name)
        record["_cityNorm"]=_norm(city)
        record["_addressNorm"]=_norm(record["address"])
        try:
            record["_host"]=(urlparse(website).hostname or "").lower().removeprefix("www.") if website else ""
        except Exception:
            record["_host"]=""
        records.append(record)
    return {
        "loaded":True,
        "path":str(path),
        "records":records,
        "summary":{
            "count":len(records),
            "websites":sum(1 for r in records if r["website"]),
            "emails":sum(1 for r in records if r["email"]),
        },
    }


CATALOG=load_structure_catalog()


def catalog_public_summary():
    summary=dict(CATALOG.get("summary") or {})
    summary.update({
        "loaded":bool(CATALOG.get("loaded")),
        "fileName":Path(CATALOG.get("path") or "").name,
        "error":CATALOG.get("error",""),
    })
    return summary


def match_catalog(payload):
    if not CATALOG.get("loaded"):
        return None
    name=str(payload.get("name") or "").strip()
    city=str(payload.get("city") or "").strip()
    website=str(payload.get("website") or "").strip()
    host=""
    try:
        host=(urlparse(website).hostname or "").lower().removeprefix("www.")
    except Exception:
        pass
    name_norm=_norm(name)
    city_norm=_norm(city)
    best=None
    for record in CATALOG.get("records",[]):
        if host and record.get("_host") and host==record["_host"]:
            return {**record,"matchScore":1.0,"matchReason":"dominio sito ufficiale coincidente"}
        score=0.0
        reasons=[]
        if name_norm:
            ratio=SequenceMatcher(None,name_norm,record.get("_nameNorm","")).ratio()
            score+=0.72*ratio
            reasons.append(f"nome {ratio:.0%}")
        if city_norm and record.get("_cityNorm"):
            city_score=1.0 if city_norm==record["_cityNorm"] else SequenceMatcher(None,city_norm,record["_cityNorm"]).ratio()
            score+=0.20*city_score
            reasons.append(f"citta {city_score:.0%}")
        if payload.get("province") and str(payload.get("province")).strip().lower()==record.get("province","").lower():
            score+=0.08
            reasons.append("provincia coincidente")
        if best is None or score>best[0]:
            best=(score,record,reasons)
    if best and best[0]>=0.76:
        return {**best[1],"matchScore":round(best[0],3),"matchReason":", ".join(best[2])}
    return None


def enrich_from_catalog(payload):
    enriched=dict(payload or {})
    if not str(enriched.get("website") or "").strip():
        try:
            site_source=(enriched.get("sources") or {}).get("sito") or {}
            if isinstance(site_source,dict) and site_source.get("url"):
                enriched["website"]=str(site_source.get("url") or "").strip()
        except Exception:
            pass
    match=match_catalog(enriched)
    if not match:
        return enriched,None
    for key in ("name","city","province","rooms","propertyType"):
        if not str(enriched.get(key) or "").strip() and match.get(key):
            enriched[key]=match[key]
    enriched["address"]=match.get("address","")
    enriched["email"]=match.get("email","")
    if not str(enriched.get("website") or "").strip() and match.get("website"):
        enriched["website"]=match["website"]
    enriched["catalogMatch"]={
        "score":match.get("matchScore"),
        "reason":match.get("matchReason"),
        "name":match.get("name"),
        "city":match.get("city"),
        "address":match.get("address"),
        "website":match.get("website"),
        "code":match.get("code"),
    }
    return enriched,match


def _site_host(url):
    try:
        return (urlparse(str(url or "")).hostname or "").lower().removeprefix("www.")
    except Exception:
        return ""


def _identity_key(payload):
    sources=payload.get("sources") if isinstance(payload,dict) else {}
    site_url=""
    if isinstance(sources,dict):
        site_url=((sources.get("sito") or {}).get("url") if isinstance(sources.get("sito"),dict) else "") or ""
    site_url=site_url or str((payload or {}).get("website") or "")
    host=_site_host(site_url)
    if host:
        # Il dominio ufficiale è l'identità primaria: il nome può cambiare tra audit e OTA.
        return f"site:{host}"
    name=_norm((payload or {}).get("name") or "")
    city=_norm((payload or {}).get("city") or "")
    return f"name:{name}|city:{city}" if name else ""


def _read_ota_cache():
    try:
        data=json.loads(OTA_SOURCE_CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data,dict) else {}
    except (OSError,json.JSONDecodeError):
        return {}


def _write_ota_cache(data):
    OTA_SOURCE_CACHE.parent.mkdir(parents=True,exist_ok=True)
    tmp=OTA_SOURCE_CACHE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(OTA_SOURCE_CACHE)


def cache_ota_sources(property_data):
    if not isinstance(property_data,dict):
        return
    key=_identity_key(property_data)
    if not key:
        return
    sources=property_data.get("sources") or {}
    ota_sources={}
    for source_id,source in sources.items():
        if source_id=="sito" or not isinstance(source,dict) or not source.get("url"):
            continue
        try:
            url=public_http_url(source.get("url"))
        except Exception:
            continue
        ota_sources[source_id]={
            "label":str(source.get("label") or source_id)[:160],
            "url":url,
        }
    if not ota_sources:
        return
    cache=_read_ota_cache()
    entry=cache.get(key) if isinstance(cache.get(key),dict) else {}
    merged=dict(entry.get("sources") or {})
    merged.update(ota_sources)
    cache[key]={
        "name":str(property_data.get("name") or "")[:180],
        "site":((sources.get("sito") or {}).get("url") if isinstance(sources.get("sito"),dict) else "") or "",
        "sources":merged,
        "updatedAt":datetime.now(timezone.utc).isoformat(),
    }
    _write_ota_cache(cache)


def recover_cached_ota_sources(payload):
    recovered={}
    key=_identity_key(payload)
    cache=_read_ota_cache()
    if key and isinstance(cache.get(key),dict):
        recovered.update(cache[key].get("sources") or {})

    # Migrazione automatica: recupera fonti da vecchi runtime con stessa identità.
    wanted_host=_site_host(((payload.get("sources") or {}).get("sito") or {}).get("url") if isinstance(payload.get("sources"),dict) else payload.get("website"))
    wanted_name=_norm(payload.get("name") or "")
    for path in RUNTIME_PROPERTIES.glob("*.json"):
        try:
            item=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):
            continue
        item_host=_site_host(((item.get("sources") or {}).get("sito") or {}).get("url"))
        if wanted_host:
            if item_host != wanted_host:
                continue
        elif wanted_name and _norm(item.get("name") or "") != wanted_name:
            continue
        for source_id,source in (item.get("sources") or {}).items():
            if source_id=="sito" or not isinstance(source,dict) or not source.get("url"):
                continue
            recovered.setdefault(source_id,source)

    # Seconda migrazione: vecchi risultati pilot che avevano una discovery verificata.
    for path in ROOT.glob("dati_strutture_pilot_*.json"):
        try:
            item=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):
            continue
        if wanted_name and _norm(item.get("propertyName") or "") != wanted_name:
            continue
        discovery=(item.get("discoveredSources") or {}).get("booking")
        if isinstance(discovery,dict) and discovery.get("status") in {"found","existing"} and discovery.get("url"):
            recovered.setdefault("booking",{"label":"Booking.com","url":discovery.get("url")})

    return recovered


def safe_property_id(value):
    value=str(value or "").strip().lower()
    if not PROPERTY_ID_RE.fullmatch(value):
        raise ValueError("ID struttura non valido")
    return value


def public_http_url(value):
    url=str(value or "").strip()
    p=urlparse(url)
    if p.scheme not in {"http","https"} or not p.hostname:
        raise ValueError("URL pubblico non valido")
    host=p.hostname.lower().rstrip(".")
    if host=="localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("URL locale non consentito")
    try:
        addr=ipaddress.ip_address(host)
    except ValueError:
        addr=None
    if addr is not None and not addr.is_global:
        raise ValueError("IP non pubblico non consentito")
    return url


def runtime_property_path(property_id):
    return RUNTIME_PROPERTIES/f"{safe_property_id(property_id)}.json"


def auto_audit_output_path(property_id):
    return RUNTIME_AUDITS/f"{safe_property_id(property_id)}.json"


def result_path(property_id):
    return PILOT_RESULTS/f"dati_strutture_pilot_{safe_property_id(property_id)}.json"


def reset_property_runtime(payload):
    """Rimuove lo stato locale di una struttura per consentire un audit realmente pulito."""
    if not isinstance(payload,dict):
        raise ValueError("Dati reset non validi")
    property_id=safe_property_id(payload.get("propertyId"))
    name=str(payload.get("name") or "").strip()[:180]
    website=str(payload.get("website") or "").strip()

    # Recupera l'identità anche dal runtime prima di cancellarlo, così possiamo
    # eliminare la relativa cache OTA in modo affidabile.
    runtime_path=runtime_property_path(property_id)
    runtime_data={}
    if runtime_path.exists():
        try:
            runtime_data=json.loads(runtime_path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):
            runtime_data={}

    if not name:
        name=str(runtime_data.get("name") or "").strip()[:180]
    if not website:
        sources=runtime_data.get("sources") or {}
        website=str(((sources.get("sito") or {}).get("url") if isinstance(sources.get("sito"),dict) else "") or "")

    # A reset must never race with any specialist writing into its folder.
    # Lock order matches agent start: classic states, then the agent registry.
    with VRBO_PRESENCE_LOCK:
        presence_active=VRBO_PRESENCE_RUNS.get(property_id,{}).get("state") in {"queued","running"}
    if presence_active:
        raise RuntimeError("Attendi la verifica presenza Vrbo prima del reset.")
    with STATE.lock,AUTO_STATE.lock,AGENT_RUN_LOCK:
        active_agents=[
            agent for (pid,agent),status in AGENT_RUNS.items()
            if pid==property_id and status.get("state") in {"running","queued"}
        ]
        if STATE.running or AUTO_STATE.running or active_agents:
            detail=(" Agenti attivi: "+", ".join(active_agents)) if active_agents else ""
            raise RuntimeError(
                "Attendi che tutte le scansioni siano terminate prima del reset."+detail
            )

    removed=[]
    for path in (runtime_path,auto_audit_output_path(property_id),result_path(property_id)):
        try:
            if path.exists():
                path.unlink()
                removed.append(str(path.name))
        except OSError as exc:
            raise RuntimeError(f"Impossibile cancellare {path.name}: {type(exc).__name__}") from exc

    # Remove only the exact cached identity. A similar name or a shared
    # website hostname must never cause another property's records to vanish.
    cache=_read_ota_cache()
    identity_payload=runtime_data if runtime_data else {
        "name":name, "website":website,
        "city":str(payload.get("city") or ""),
    }
    cache_key=_identity_key(identity_payload)
    removed_cache=[]
    shared_cache=False
    if cache_key and cache_key in cache:
        for other_path in RUNTIME_PROPERTIES.glob("*.json"):
            if other_path.name==runtime_path.name:
                continue
            try:
                other=json.loads(other_path.read_text(encoding="utf-8"))
            except (OSError,json.JSONDecodeError):
                continue
            if _identity_key(other)==cache_key:
                shared_cache=True
                break
        if not shared_cache:
            cache.pop(cache_key,None)
            removed_cache.append(cache_key)
            _write_ota_cache(cache)

    # All twelve agents and Giove store their reports under this property's
    # own folder; the manually authorized OTA browser profiles are elsewhere.
    agent_dir=AGENT_RESULTS/property_id
    if agent_dir.exists():
        try:
            shutil.rmtree(agent_dir)
            removed.append("specialist-agents/"+property_id)
        except OSError as exc:
            raise RuntimeError("Impossibile eliminare gli esiti degli agenti: "
                               +type(exc).__name__) from exc
    with AGENT_RUN_LOCK:
        for key in list(AGENT_RUNS):
            if key[0]==property_id:
                AGENT_RUNS.pop(key,None)
    with VRBO_PRESENCE_LOCK:
        VRBO_PRESENCE_RUNS.pop(property_id,None)

    with STATE.lock:
        if STATE.property_id==property_id:
            STATE.error=""
            STATE.property_id=""
            STATE.property_path=None
    with AUTO_STATE.lock:
        if AUTO_STATE.property_id==property_id:
            AUTO_STATE.error=""
            AUTO_STATE.message=""
            AUTO_STATE.property_id=""
            AUTO_STATE.result=None

    print(
        f"reset struttura: {property_id} · file={len(removed)} · cache OTA={len(removed_cache)}",
        flush=True,
    )
    return {
        "ok":True,
        "propertyId":property_id,
        "removedFiles":removed,
        "removedCacheEntries":len(removed_cache),
        "sharedCachePreserved":shared_cache,
        "agentRunsReset":True,
        "portalLoginProfilesPreserved":True,
    }


def prepare_runtime_property(payload):
    if payload is None:
        return None
    if not isinstance(payload,dict):
        raise ValueError("Dati struttura non validi")
    payload,_=enrich_from_catalog(payload)
    property_id=safe_property_id(payload.get("id"))
    name=str(payload.get("name") or "").strip()[:180]
    if not name:
        raise ValueError("Nome struttura mancante")
    sources=payload.get("sources")
    if not isinstance(sources,dict) or not sources:
        raise ValueError("Fonti struttura mancanti")
    cleaned={}
    for source_id,source in list(sources.items())[:40]:
        if not isinstance(source_id,str) or not isinstance(source,dict) or not source.get("url"):
            continue
        try:
            url=public_http_url(source["url"])
        except ValueError:
            continue
        cleaned[source_id[:60]]={"label":str(source.get("label") or source_id)[:160],"url":url}
    if "sito" not in cleaned:
        raise ValueError("La fonte sito con URL pubblico e' obbligatoria")

    # Recupera fonti OTA già verificate anche se l'ID runtime è cambiato.
    recovery_payload={**payload,"sources":cleaned}
    for source_id,source in recover_cached_ota_sources(recovery_payload).items():
        if source_id in cleaned or not isinstance(source,dict) or not source.get("url"):
            continue
        try:
            url=public_http_url(source.get("url"))
        except ValueError:
            continue
        cleaned[source_id[:60]]={
            "label":str(source.get("label") or source_id)[:160],
            "url":url,
        }

    # Mantiene le OTA già scoperte dal pilota quando il frontend reinvia solo il sito ufficiale.
    existing_path=runtime_property_path(property_id)
    if existing_path.exists():
        try:
            existing=json.loads(existing_path.read_text(encoding="utf-8"))
            same_name=_norm(existing.get("name"))==_norm(name)
            existing_site=((existing.get("sources") or {}).get("sito") or {}).get("url","")
            current_site=(cleaned.get("sito") or {}).get("url","")
            same_site=False
            try:
                same_site=(urlparse(existing_site).hostname or "").lower().removeprefix("www.") == (urlparse(current_site).hostname or "").lower().removeprefix("www.")
            except Exception:
                same_site=False
            if same_name and same_site:
                for source_id,source in (existing.get("sources") or {}).items():
                    if source_id in cleaned or not isinstance(source,dict) or not source.get("url"):
                        continue
                    try:
                        url=public_http_url(source.get("url"))
                    except ValueError:
                        continue
                    cleaned[source_id[:60]]={
                        "label":str(source.get("label") or source_id)[:160],
                        "url":url,
                    }
        except (OSError,json.JSONDecodeError):
            pass

    data={
        "id":property_id,
        "name":name,
        "city":str(payload.get("city") or "").strip()[:100],
        "province":str(payload.get("province") or "").strip()[:20],
        "address":str(payload.get("address") or "").strip()[:240],
        "email":str(payload.get("email") or "").strip()[:180],
        "rooms":str(payload.get("rooms") or "").strip()[:20],
        "propertyType":str(payload.get("propertyType") or "").strip()[:100],
        "catalogMatch":payload.get("catalogMatch"),
        "sources":cleaned,
    }
    path=runtime_property_path(property_id)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)
    cache_ota_sources(data)
    return property_id,path


def resolve_property_path(property_id):
    if property_id in PROPERTIES:
        return PROPERTIES[property_id]
    path=runtime_property_path(property_id)
    return path if path.exists() else None


def run_auto_audit(payload):
    try:
        with AUTO_STATE.lock:
            AUTO_STATE.message="Analisi del sito ufficiale in corso..."
        result=asyncio.run(build_site_audit(payload))
        property_id=safe_property_id(result.get("id"))
        out=auto_audit_output_path(property_id)
        tmp=out.with_suffix(".tmp")
        tmp.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        tmp.replace(out)
        with AUTO_STATE.lock:
            AUTO_STATE.result=result
            AUTO_STATE.property_id=property_id
            AUTO_STATE.message="Audit iniziale completato. La scheda puo' essere aperta in Velora."
    except Exception as exc:
        with AUTO_STATE.lock:
            AUTO_STATE.error=f"{type(exc).__name__}: {str(exc)[:300]}"
            AUTO_STATE.message="Analisi interrotta."
    finally:
        with AUTO_STATE.lock:
            AUTO_STATE.running=False


def run_pilot(property_id,property_path,months,channels,ghost=False,assisted=False,pricing_only=True,custom_period=None):
    try:
        args=argparse.Namespace(
            property=str(property_path),
            output=str(result_path(property_id)),
            channels=",".join(channels),
            months=months,
            custom_period=custom_period,
            today=None,
            dry_run=False,
            ghost=bool(ghost),
            assisted=bool(assisted),
            assist_callback=wait_for_pilot_intervention if assisted else None,
            pricing_only=bool(pricing_only),
        )

        # Il pilot v73 recupera Chrome internamente tra discovery e pricing.
        # Questo resta soltanto come fallback estremo se l'errore avviene prima del checkpoint.
        for attempt in range(2):
            try:
                asyncio.run(run(args))
                break
            except Exception as exc:
                message=f"{type(exc).__name__}: {str(exc)}"
                lowered=message.lower()
                browser_closed=(
                    "browser has been closed" in lowered
                    or "context or browser has been closed" in lowered
                    or "target page, context or browser has been closed" in lowered
                    or "targetclosederror" in lowered
                )
                if attempt==0 and browser_closed:
                    print(
                        "WATCHDOG CHROME ESTREMO: errore prima/dopo il recovery interno. "
                        "Ultimo tentativo completo...",
                        flush=True,
                    )
                    continue
                raise

        try:
            latest=json.loads(Path(property_path).read_text(encoding="utf-8"))
            cache_ota_sources(latest)
        except (OSError,json.JSONDecodeError):
            pass
        print(f"Pilot completato: {property_id}",flush=True)
    except Exception as exc:
        error=f"{type(exc).__name__}: {str(exc)[:240]}"
        with STATE.lock:
            STATE.error=error
        print(f"ERRORE PILOT: {error}",flush=True)
    finally:
        with STATE.lock:
            STATE.running=False
            STATE.intervention={}
            STATE.intervention_action=""
            STATE.intervention_event.set()


async def render_pdf(html):
    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome",headless=True)
        try:
            context=await browser.new_context(java_script_enabled=False)
            page=await context.new_page()
            await page.route("**/*",lambda route:route.abort())
            await page.set_content(html,wait_until="domcontentloaded",timeout=15000)
            return await page.pdf(format="A4",print_background=True,prefer_css_page_size=True)
        finally:
            await browser.close()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(DIST),**kwargs)

    def _allowed_origin(self):
        origin=self.headers.get("Origin","")
        return origin if origin in ALLOWED_ORIGINS else ""

    def _cors(self):
        origin=self._allowed_origin()
        if origin:
            self.send_header("Access-Control-Allow-Origin",origin)
            self.send_header("Vary","Origin")
            self.send_header("Access-Control-Allow-Private-Network","true")

    def _json(self,status,body):
        data=json.dumps(body,ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self._cors()
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        if not self._allowed_origin():
            self.send_response(403); self.end_headers(); return
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type, X-Velora-Local-Token")
        self.send_header("Access-Control-Max-Age","600")
        self.end_headers()

    def do_GET(self):
        route=urlparse(self.path).path
        if route=="/api/pilot/config":
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            self._json(200,{
                "token":STATE.token,
                "propertyIds":sorted(PROPERTIES),
                "onlineBridge":True,
                "autoAudit":True,
                "agentVersion":"velora-local-agent-v125",
                "leonardoBuild":getattr(leonardo_direct_engine,"LEONARDO_BUILD","legacy"),
                "catalog":catalog_public_summary(),
                "pilotBuild":getattr(browser_pilot,"PILOT_BUILD","legacy"),
                "pilotSync":getattr(browser_pilot,"PILOT_BUILD","legacy")==EXPECTED_PILOT_BUILD,
                "aiWebSearch":{
                    "configured":False,
                    "model":"free-multi-engine",
                    "mode":"free",
                },
            })
            return
        if route=="/api/pilot/status":
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            with STATE.lock:
                running,error,property_id=STATE.running,STATE.error,STATE.property_id
                intervention=dict(STATE.intervention or {})
            output=result_path(property_id) if property_id else None
            try:
                result=json.loads(output.read_text(encoding="utf-8")) if output and output.exists() else None
            except (OSError,json.JSONDecodeError):
                result=None
            self._json(200,{"running":running,"error":error,"propertyId":property_id,"result":result,"intervention":intervention or None})
            return
        if route=="/api/portal-session/status":
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            if PORTAL_SESSIONS is None:
                self._json(503,{"error":"Aggiorna l'agente locale: manca il modulo di navigazione assistita."}); return
            self._json(200,{
                "portals":{key:{"name":value["name"],"label":value["label"],
                                "authentication":value["authentication"],"scraping":value["scraping"]}
                           for key,value in LOGIN_PORTALS.items()},
                "sessions":PORTAL_SESSIONS.statuses(),"firefoxTest":PORTAL_SESSIONS.firefox_test_status(),"manualOnly":True,
                "automatedLoginSupported":True,
                "message":"Credenziali opzionali conservate solo nel Gestore credenziali Windows. La sessione Chrome viene riusata autonomamente; se richiesto codice email o CAPTCHA serve conferma manuale. Login e tariffe non sono automaticamente certificati."
            })
            return
        if route=="/api/agents/config":
            if agent_network is None:
                self._json(503,{"error":specialist_unavailable_message()}); return
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            self._json(200,{"schema":agent_network.NETWORK_SCHEMA,"agents":agent_network.AGENTS,
                             "plannedAgents":agent_network.FUTURE_AGENTS,
                             "reviewer":{"name":agent_network.REVIEWER_NAME,"trigger":"manual_only"},"version":"v125"})
            return
        if route in {"/api/agents/status","/api/agents/result","/api/agents/validation","/api/agents/chat"}:
            if agent_network is None:
                self._json(503,{"error":specialist_unavailable_message()}); return
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            query=parse_qs(urlparse(self.path).query)
            try:
                property_id=safe_property_id((query.get("propertyId") or [""])[0])
            except ValueError:
                self._json(400,{"error":"Struttura non valida"}); return
            if route=="/api/agents/chat":
                # Read-only Giove viewer: the logged structured exchanges only.
                # No credentials, prompts or hidden browser actions are exposed.
                target=agent_mailbox_path(property_id)
                try:
                    payload=json.loads(target.read_text(encoding="utf-8"))
                    if payload.get("propertyId")!=property_id:
                        raise ValueError("Proprietà della mailbox non coerente")
                    events=payload.get("events") or []
                    if not isinstance(events,list):
                        raise ValueError("Formato mailbox non valido")
                except FileNotFoundError:
                    events=[]
                except (OSError,ValueError,TypeError):
                    self._json(500,{"error":"Mailbox agenti non leggibile"}); return
                self._json(200,{"propertyId":property_id,"events":events[-120:],
                                 "viewer":"Giove","mode":"structured-events-read-only"})
                return
            if route=="/api/agents/status":
                with AGENT_RUN_LOCK:
                    status={agent:dict(AGENT_RUNS.get((property_id,agent),{})) for agent in agent_network.AGENTS}
                for agent in status:
                    target=agent_output(property_id,agent)
                    status[agent]["hasResult"]=target.is_file()
                    snapshot={**status[agent],"propertyId":property_id}
                    status[agent].update(specialist_progress(agent,snapshot,target))
                self._json(200,{"propertyId":property_id,"agents":status,
                                 "validationAvailable":agent_validation_output(property_id).is_file()})
                return
            if route=="/api/agents/validation":
                target=agent_validation_output(property_id)
            else:
                agent=(query.get("agentId") or [""])[0]
                if agent not in agent_network.AGENTS:
                    self._json(400,{"error":"Agente non valido"}); return
                target=agent_output(property_id,agent)
            try:
                value=json.loads(target.read_text(encoding="utf-8"))
            except (OSError,json.JSONDecodeError):
                self._json(404,{"error":"Nessun esito salvato"}); return
            self._json(200,value)
            return
        if route=="/api/ota-presence/manual":
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            query=parse_qs(urlparse(self.path).query)
            try:
                property_id=safe_property_id((query.get("propertyId") or [""])[0])
            except ValueError:
                self._json(400,{"error":"Struttura non valida"}); return
            self._json(200,read_manual_ota_presence(property_id))
            return
        if route=="/api/vrbo-presence/status":
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            query=parse_qs(urlparse(self.path).query)
            try:
                property_id=safe_property_id((query.get("propertyId") or [""])[0])
            except ValueError:
                self._json(400,{"error":"Struttura non valida"}); return
            self._json(200,classify_stored_vrbo_presence(property_id))
            return
        if route=="/api/audit/status":
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            with AUTO_STATE.lock:
                body={
                    "running":AUTO_STATE.running,
                    "error":AUTO_STATE.error,
                    "message":AUTO_STATE.message,
                    "propertyId":AUTO_STATE.property_id,
                    "auditData":AUTO_STATE.result,
                }
            self._json(200,body)
            return
        if route.startswith("/api/"):
            self._json(404,{"error":"Percorso sconosciuto"}); return
        return super().do_GET()

    def do_POST(self):
        route=urlparse(self.path).path
        if route not in {"/api/pilot/start","/api/pilot/reset","/api/scraping/reset","/api/pilot/intervention","/api/audit/start","/api/report/pdf","/api/agents/start","/api/agents/validate","/api/ota-presence/manual","/api/vrbo-presence/start","/api/portal-session/start","/api/portal-session/finish","/api/portal-session/navigate","/api/portal-account/save","/api/portal-account/remove","/api/portal-account/info","/api/portal-auth/resume","/api/portal-auth/start","/api/portal-firefox/start","/api/portal-firefox/finish"}:
            self._json(404,{"error":"Percorso sconosciuto"}); return
        if (not self._allowed_origin()
                or self.headers.get("X-Velora-Local-Token")!=STATE.token
                or self.headers.get_content_type()!="application/json"):
            self._json(403,{"error":"Richiesta Velora non autorizzata"}); return
        try:
            length=int(self.headers.get("Content-Length","0"))
            max_size=5_000_000 if route=="/api/report/pdf" else 100_000
            if not 0<length<=max_size:
                raise ValueError("Dimensione richiesta non valida")
            payload=json.loads(self.rfile.read(length))
            if not isinstance(payload,dict):
                raise ValueError("Richiesta JSON non valida")

            if route=="/api/ota-presence/manual":
                property_id=safe_property_id(payload.get("propertyId"))
                try:
                    result=record_manual_ota_presence(
                        property_id,
                        payload.get("propertyName"),
                        str(payload.get("otaId") or "").lower(),
                        str(payload.get("action") or ""),
                    )
                    self._json(200,{"ok":True,"propertyId":property_id,
                                    "observation":result})
                except ValueError as exc:
                    self._json(400,{"error":str(exc)[:200]})
                return

            if route in {"/api/portal-firefox/start","/api/portal-firefox/finish"}:
                if PORTAL_SESSIONS is None:
                    self._json(503,{"error":"Aggiorna l'agente Windows per il test Firefox."}); return
                if route.endswith("/start"):
                    with AGENT_RUN_LOCK:
                        active=any(row.get("state") in {"running","queued"} for row in AGENT_RUNS.values())
                    with STATE.lock,AUTO_STATE.lock:
                        active=active or STATE.running or AUTO_STATE.running
                    if active:
                        self._json(409,{"error":"Termina le scansioni prima del test Firefox."}); return
                try:
                    state=(PORTAL_SESSIONS.start_firefox_test()
                           if route.endswith("/start")
                           else PORTAL_SESSIONS.close_firefox_test())
                    self._json(202 if route.endswith("/start") else 200,{"ok":True,"firefoxTest":state})
                except RuntimeError as exc:
                    self._json(409,{"error":str(exc)[:240]})
                return

            if route=="/api/portal-auth/start":
                if PORTAL_SESSIONS is None:
                    self._json(503,{"error":"Aggiorna l'agente Windows per verificare l'accesso."}); return
                portal_id=str(payload.get("portalId") or "").strip().lower()
                if portal_id not in LOGIN_PORTALS:
                    self._json(400,{"error":"Portale non supportato"}); return
                with AGENT_RUN_LOCK:
                    active=any(row.get("state") in {"running","queued"} for row in AGENT_RUNS.values())
                with STATE.lock,AUTO_STATE.lock:
                    active=active or STATE.running or AUTO_STATE.running
                if active:
                    self._json(409,{"error":"Prima termina le scansioni in corso, poi verifica il login."}); return
                try:
                    state=PORTAL_SESSIONS.start_account_check(portal_id)
                    self._json(202,{"ok":True,"portalId":portal_id,"session":state})
                except RuntimeError as exc:
                    self._json(409,{"error":str(exc)[:240]})
                return

            if route=="/api/portal-auth/resume":
                if PORTAL_SESSIONS is None:
                    self._json(503,{"error":"Aggiorna l'agente locale per la verifica assistita."}); return
                portal_id=str(payload.get("portalId") or "").strip().lower()
                if portal_id not in LOGIN_PORTALS:
                    self._json(400,{"error":"Portale non supportato"}); return
                try:
                    state=PORTAL_SESSIONS.resume_agent_login(portal_id)
                    self._json(200,{"ok":True,"portalId":portal_id,"session":state})
                except RuntimeError as exc:
                    self._json(409,{"error":str(exc)[:200]})
                return

            if route in {"/api/portal-account/save","/api/portal-account/remove","/api/portal-account/info"}:
                if PORTAL_SESSIONS is None:
                    self._json(503,{"error":"Aggiorna il servizio Windows per memorizzare gli accessi."}); return
                portal_id=str(payload.get("portalId") or "").strip().lower()
                if portal_id not in LOGIN_PORTALS:
                    self._json(400,{"error":"Portale non supportato"}); return
                try:
                    if route.endswith("/save"):
                        status=PORTAL_SESSIONS.save_credentials(portal_id,str(payload.get("email") or ""),str(payload.get("password") or ""))
                    elif route.endswith("/info"):
                        status=PORTAL_SESSIONS.account_info(portal_id)
                    else:
                        status=PORTAL_SESSIONS.remove_credentials(portal_id)
                    self._json(200,{"ok":True,"portalId":portal_id,"status":status})
                except (RuntimeError,OSError,ValueError) as exc:
                    self._json(400,{"error":str(exc)[:200]})
                return

            if route in {"/api/portal-session/start","/api/portal-session/finish","/api/portal-session/navigate"}:
                if PORTAL_SESSIONS is None:
                    self._json(503,{"error":"Modulo di sessione mancante. Scarica l'aggiornamento Windows."}); return
                portal_id=str(payload.get("portalId") or "").strip().lower()
                if portal_id not in LOGIN_PORTALS:
                    self._json(400,{"error":"Portale di login non riconosciuto"}); return
                try:
                    if route=="/api/portal-session/start":
                        with AGENT_RUN_LOCK:
                            busy=any(row.get("state") in {"running","queued"} for row in AGENT_RUNS.values())
                        if busy:
                            self._json(409,{"error":"Completa gli agenti di scraping prima di aprire Chrome per il login."}); return
                        state=PORTAL_SESSIONS.begin(portal_id)
                        self._json(202,{"portalId":portal_id,"session":state,"manualOnly":True})
                    elif route=="/api/portal-session/navigate":
                        state=PORTAL_SESSIONS.navigate(portal_id,str(payload.get("url") or ""))
                        self._json(200,{"portalId":portal_id,"session":state,"manualOnly":True})
                    else:
                        state=PORTAL_SESSIONS.finish(portal_id)
                        self._json(200,{"portalId":portal_id,"session":state,"manualOnly":True})
                except RuntimeError as exc:
                    self._json(409,{"error":str(exc)})
                return

            if route in {"/api/agents/validate","/api/agents/start"} and agent_network is None:
                self._json(503,{"error":specialist_unavailable_message()}); return

            if route=="/api/vrbo-presence/start":
                if agent_network is None:
                    self._json(503,{"error":specialist_unavailable_message()}); return
                property_id=safe_property_id(payload.get("propertyId"))
                data=payload.get("propertyData")
                if not isinstance(data,dict) or data.get("id")!=property_id:
                    raise ValueError("Dati struttura mancanti o non coerenti")
                name=str(data.get("name") or "").strip()[:180]
                city=str(data.get("city") or "").strip()[:100]
                if not name or not city:
                    raise ValueError("Per cercare su Vrbo sono necessari nome e località")
                data={
                    "id":property_id,"name":name,"city":city,
                    "province":str(data.get("province") or "")[:80],
                    "address":str(data.get("address") or "")[:180],
                    "website":str(data.get("website") or "")[:500],
                    "sources":{}
                }
                with VRBO_PRESENCE_LOCK:
                    current=VRBO_PRESENCE_RUNS.get(property_id,{})
                    if current.get("state") in {"queued","running"}:
                        self._json(409,{"error":"Atlante sta già verificando la presenza Vrbo."}); return
                    VRBO_PRESENCE_RUNS[property_id]={
                        "propertyId":property_id,"state":"queued",
                        "message":"Ricerca pubblica Vrbo in coda, senza login."
                    }
                threading.Thread(target=run_vrbo_presence_job,
                    args=(data,property_id),daemon=True).start()
                self._json(202,{"propertyId":property_id,"state":"queued"})
                return

            if route=="/api/agents/validate":
                property_id=safe_property_id(payload.get("propertyId"))
                with AGENT_RUN_LOCK:
                    active=[name for (pid,name),value in AGENT_RUNS.items()
                            if pid==property_id and value.get("state") in {"running","queued"}]
                if active:
                    self._json(409,{"error":"Attendi la conclusione degli agenti prima del check: "+", ".join(active)}); return
                outputs={agent:agent_output(property_id,agent) for agent in agent_network.AGENTS}
                report=agent_network.evaluate(property_id,outputs)
                print_giove_report(report)
                dest=agent_validation_output(property_id)
                dest.parent.mkdir(parents=True,exist_ok=True)
                tmp=dest.with_suffix(".tmp")
                tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
                tmp.replace(dest)
                self._json(200,report)
                return

            if route=="/api/agents/start":
                agent_id=str(payload.get("agentId") or "").strip()
                if agent_id not in agent_network.AGENTS:
                    raise ValueError("Agente non disponibile")
                if payload.get("assisted"):
                    raise ValueError("L'assistenza umana per gli specialisti non è ancora abilitata: usa la scansione classica.")
                if agent_network.AGENTS[agent_id]["kind"]=="ota" and getattr(browser_pilot,"PILOT_BUILD","")!=EXPECTED_PILOT_BUILD:
                    self._json(409,{"error":"Aggiorna e riavvia agente locale e pilot v125 prima di avviare gli specialisti."}); return
                session_mode=str(payload.get("sessionMode") or "public").strip().lower()
                if session_mode not in {"public","account"}:
                    raise ValueError("Modalità agente non riconosciuta")
                # These specialists must never silently revert to anonymous navigation.
                if agent_id in {"expedia", "vrbo", "holidu"} and session_mode != "account":
                    self._json(409, {"error": (
                        "Seleziona Modalità Account per Expedia, Vrbo o Holidu. "
                        "Apri accesso, effettua personalmente il login, chiudi e conserva "
                        "il profilo Chrome e avvia nuovamente questo agente."
                    )})
                    return
                account_profile=None
                if session_mode=="account":
                    if PORTAL_SESSIONS is None or agent_id not in LOGIN_PORTALS:
                        self._json(409,{"error":"La modalità Account è disponibile solo per Expedia, Vrbo e Holidu con profilo Chrome locale."}); return
                    session=PORTAL_SESSIONS.statuses().get(agent_id) or {}
                    if session.get("state") in {"open","queued","awaiting_user","authenticating"}:
                        self._json(409,{"error":"Prima chiudi e conserva la sessione manuale di questo portale. Chrome non può usare lo stesso profilo due volte."}); return
                    if not PORTAL_SESSIONS.has_saved_profile(agent_id) and not PORTAL_SESSIONS.has_credentials(agent_id):
                        self._json(409,{"error":"Nessuna sessione o credenziale disponibile per "+agent_id+". Configura credenziali Windows oppure premi Apri accesso e Chiudi e conserva."}); return
                    if session.get("state")!="ready":
                        self._json(409,{"error":"Accesso non verificato: prima salva l'email in «Configura credenziali», poi premi «Accedi e verifica». Inserisci l'eventuale codice nel Chrome dedicato e conferma «Riprendi». Nessun timer avviato."}); return
                    account_profile=str(PORTAL_SESSIONS.profile_dir(agent_id))
                property_id=safe_property_id(payload.get("propertyId"))
                with STATE.lock,AUTO_STATE.lock:
                    if STATE.running or AUTO_STATE.running:
                        self._json(409,{"error":"La scansione classica è ancora attiva: completala prima di avviare gli specialisti."}); return
                work=agent_workspace(property_id,agent_id)
                work.mkdir(parents=True,exist_ok=True)
                # Snapshot isolato: nessuno specialista modifica il JSON originale.
                supplied=payload.get("propertyData")
                if not isinstance(supplied,dict) or supplied.get("id")!=property_id:
                    raise ValueError("Identità struttura non coerente")
                base_path=resolve_property_path(property_id)
                base_data={}
                if base_path is not None:
                    try: base_data=json.loads(base_path.read_text(encoding="utf-8"))
                    except (OSError,json.JSONDecodeError): base_data={}
                data={**base_data, **supplied}
                base_sources=base_data.get("sources") or {}
                data["sources"]={**base_sources,**(supplied.get("sources") or {})}
                data["id"]=property_id
                if data.get("website") and not data["sources"].get("sito"):
                    data["sources"]["sito"]={"label":"Sito ufficiale","url":data["website"]}
                months=payload.get("months",1)
                if months not in (1,6,12):
                    raise ValueError("Seleziona 1, 6 o 12 mesi")
                custom_period=payload.get("customPeriod")
                if custom_period is not None:
                    if not isinstance(custom_period,dict) or not all(k in custom_period for k in ("start","end","nights","adults","frequency")):
                        raise ValueError("Calendario personalizzato non valido")
                    from datetime import date as _date, timedelta as _timedelta
                    a,b=_date.fromisoformat(str(custom_period["start"])),_date.fromisoformat(str(custom_period["end"]))
                    n=int(custom_period["nights"]); adults=int(custom_period["adults"])
                    frequency=str(custom_period["frequency"])
                    if a<_date.today() or b<a or (b-a).days>366 or n not in (1,2,3,4,5,7,14) or not 1<=adults<=12 or frequency not in ("daily","weekly","biweekly") or a+_timedelta(days=n)>b:
                        raise ValueError("Calendario personalizzato non valido")
                    custom_period={"start":a.isoformat(),"end":b.isoformat(),"nights":n,"adults":adults,"frequency":frequency}
                # Preflight before queueing: every pricing agent must receive the
                # same EXACT confirmed Booking windows for this property and plan.
                # Never use a stale partial snapshot, a similarly named property,
                # or a lock from another requested interval.
                data.pop("_specialistBookingLocks",None)
                # Tutti gli specialisti lavorano sulla finestra di Leonardo
                # che Minerva deve avere verificato, non su tutte le date vuote.
                direct_master=None
                try:
                    direct_result=json.loads(agent_output(property_id,"official_site").read_text(encoding="utf-8"))
                    candidate=(direct_result.get("directCommercialAudit") or {}).get("masterStay") or {}
                    if (direct_result.get("propertyId")==property_id
                        and direct_result.get("propertyName")==data.get("name")
                        and candidate.get("status")=="direct_price_observed"
                        and candidate.get("checkin") and candidate.get("checkout")):
                        direct_master=candidate
                except (OSError,ValueError,TypeError):
                    pass
                if direct_master and agent_id!="official_site":
                    custom_period={
                        "start":direct_master["checkin"],"end":direct_master["checkout"],
                        "nights":int(direct_master["nights"]),
                        "adults":int(direct_master["adults"]),"frequency":"daily"}
                    if agent_id=="booking":
                        data["_directMasterStay"]=direct_master
                if agent_id not in {"booking","official_site","reviews"}:
                    try:
                        booking_result=json.loads(agent_output(property_id,"booking").read_text(encoding="utf-8"))
                        if (booking_result.get("propertyId")!=property_id
                                or booking_result.get("propertyName")!=data.get("name")):
                            raise ValueError("Identità Booking diversa dalla struttura attuale")
                        expected_plan=(browser_pilot.custom_date_plan(datetime.now().date(),custom_period)
                            if custom_period else browser_pilot.monthly_plan(
                                datetime.now().date(),limit=(13 if months==12 else months)))
                        locks=booking_result.get("bookingReferenceStays") or []
                        expected_keys=[
                            (str(stay.get("checkin")),str(stay.get("checkout")),
                             int(stay.get("nights") or 0),int(stay.get("adults") or 2))
                            for stay in expected_plan
                        ]
                        by_key={}
                        for row in locks:
                            if not isinstance(row,dict) or row.get("status") not in {
                                "initial_dates_available","shifted_to_available_booking_dates","direct_master_checked"
                            }:
                                continue
                            key=(str(row.get("requestedCheckin")),str(row.get("requestedCheckout")),
                                 int(row.get("nights") or 0),int(row.get("adults") or 2))
                            if row.get("checkin") and row.get("checkout"):
                                by_key[key]=row
                        if not expected_keys or any(key not in by_key for key in expected_keys):
                            raise ValueError("Finestre Booking incomplete o di un altro periodo")
                        data["_specialistBookingLocks"]=[dict(by_key[key]) for key in expected_keys]
                        print(f"[GIOVE] Date Booking sincronizzate: {len(expected_keys)} finestre",flush=True)
                    except (FileNotFoundError,OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
                        self._json(409,{"error":(
                            "DATE NON SINCRONIZZATE: esegui prima Booking con lo stesso "
                            "periodo e la stessa struttura, poi avvia questa OTA. "
                            "Nessuna scansione disallineata è stata avviata. "
                            +str(exc)[:150]
                        )}); return
                with AGENT_RUN_LOCK:
                    current=AGENT_RUNS.get((property_id,agent_id),{})
                    if current.get("state") in {"running","queued"}:
                        self._json(409,{"error":"Questo agente è già in esecuzione"}); return
                    AGENT_RUNS[(property_id,agent_id)]={
                        "state":"queued","agentId":agent_id,"startedAt":datetime.now(timezone.utc).isoformat(),"error":""
                    }
                input_path=work/"property.json"
                input_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                agent_output(property_id,agent_id).unlink(missing_ok=True)
                agent_validation_output(property_id).unlink(missing_ok=True)
                threading.Thread(target=run_specialist_job,args=(
                    property_id,agent_id,input_path,months,custom_period,
                    bool(payload.get("ghost",False)),bool(payload.get("assisted",False)),
                    account_profile
                ),daemon=True,name="velora-"+agent_id).start()
                self._json(202,{"ok":True,"propertyId":property_id,"agentId":agent_id,"state":"queued","sessionMode":session_mode})
                return

            if route=="/api/pilot/intervention":
                action=str(payload.get("action") or "").strip().lower()
                if action not in {"continue","done","skip"}:
                    raise ValueError("Azione intervento non valida")
                with STATE.lock:
                    if not STATE.running or not STATE.intervention:
                        self._json(409,{"error":"Nessun intervento utente attivo"}); return
                    STATE.intervention_action="continue" if action in {"continue","done"} else "skip"
                    STATE.intervention_event.set()
                self._json(200,{"ok":True,"action":STATE.intervention_action})
                return

            if route in {"/api/pilot/reset","/api/scraping/reset"}:
                try:
                    result=reset_property_runtime(payload)
                except RuntimeError as exc:
                    self._json(409,{"error":str(exc)}); return
                except ValueError as exc:
                    self._json(400,{"error":str(exc)}); return
                self._json(200,result)
                return

            if route=="/api/report/pdf":
                html=payload.get("html")
                if not isinstance(html,str) or not html.lstrip().lower().startswith("<!doctype html"):
                    raise ValueError("Report HTML non valido")
                try:
                    pdf=asyncio.run(render_pdf(html))
                except Exception as exc:
                    self._json(500,{"error":f"Chrome non ha generato il PDF: {type(exc).__name__}"}); return
                filename=re.sub(r"[^a-zA-Z0-9._-]","-",str(payload.get("filename","report-velora.pdf")))[:100]
                if not filename.endswith(".pdf"):
                    filename+=".pdf"
                self.send_response(200)
                self.send_header("Content-Type","application/pdf")
                self.send_header("Content-Disposition",f'attachment; filename="{filename}"')
                self._cors()
                self.send_header("Content-Length",str(len(pdf)))
                self.end_headers()
                self.wfile.write(pdf)
                return

            if route=="/api/pilot/start":
                pilot_build=getattr(browser_pilot,"PILOT_BUILD","legacy")
                if pilot_build != EXPECTED_PILOT_BUILD:
                    self._json(409,{
                        "error":(
                            f"Pilot non sincronizzato: caricato {pilot_build}, atteso {EXPECTED_PILOT_BUILD}. "
                            "Eseguire AGGIORNA_VELORA_COMPLETO.bat e riavviare l'agente."
                        )
                    })
                    return

            if route=="/api/audit/start":
                website=validate_site_url(payload.get("website"))
                raw_audit_payload={
                    "website":website,
                    "name":str(payload.get("name") or "").strip()[:180],
                    "city":str(payload.get("city") or "").strip()[:100],
                    "province":str(payload.get("province") or "").strip()[:10],
                    "rooms":str(payload.get("rooms") or "").strip()[:10],
                    "propertyType":str(payload.get("propertyType") or "").strip()[:100],
                }
                audit_payload,_=enrich_from_catalog(raw_audit_payload)
                with AUTO_STATE.lock,STATE.lock,AGENT_RUN_LOCK:
                    specialists_active=any(v.get("state") in {"running","queued"} for v in AGENT_RUNS.values())
                    if AUTO_STATE.running or STATE.running or specialists_active:
                        self._json(409,{"error":"Un'altra rilevazione Velora e' gia' in corso"}); return
                    AUTO_STATE.running=True
                    AUTO_STATE.error=""
                    AUTO_STATE.message="Avvio analisi sito ufficiale..."
                    AUTO_STATE.property_id=""
                    AUTO_STATE.result=None
                threading.Thread(target=run_auto_audit,args=(audit_payload,),daemon=True).start()
                self._json(202,{"running":True,"message":"Analisi automatica avviata"})
                return

            custom_period=payload.get("customPeriod")
            if custom_period is not None:
                if not isinstance(custom_period,dict):
                    raise ValueError("Periodo personalizzato non valido")
                from datetime import date as _date, timedelta as _timedelta
                try:
                    _start=_date.fromisoformat(str(custom_period["start"]))
                    _end=_date.fromisoformat(str(custom_period["end"]))
                    _nights=int(custom_period["nights"])
                    _adults=int(custom_period["adults"])
                    _frequency=str(custom_period["frequency"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError("Campi calendario personalizzato non validi") from exc
                if (_start<_date.today() or _end<_start or (_end-_start).days>366
                    or _nights not in (1,2,3,4,5,7,14) or not 1<=_adults<=12
                    or _frequency not in ("daily","weekly","biweekly")
                    or _start+_timedelta(days=_nights)>_end):
                    raise ValueError("Calendario non valido: soggiorno completo obbligatorio nel periodo")
                custom_period={"start":_start.isoformat(),"end":_end.isoformat(),
                               "nights":_nights,"adults":_adults,"frequency":_frequency}
            elif payload.get("months") not in (1,6,12):
                raise ValueError("Periodo non supportato: scegli 1, 6 o 12 mesi")
            requested_channels=payload.get("channels")
            if requested_channels is None:
                # La discovery delle fonti viene comunque eseguita su tutto OTA_DISCOVERY_ORDER.
                # Le osservazioni mese-per-mese, invece, partono solo sui canali con adapter date:
                # evita righe ripetute "date_adapter_missing" per metasearch/review portal.
                requested_channels=[
                    channel for channel in CHANNELS
                    if channel in getattr(browser_pilot,"DATE_URL_ADAPTERS",set())
                ]
            if not isinstance(requested_channels,list) or not requested_channels:
                raise ValueError("Canali pilota non validi")
            requested_channels=[str(item).strip() for item in requested_channels if str(item).strip()]
            unknown_channels=set(requested_channels)-set(CHANNELS)
            if unknown_channels:
                raise ValueError("Canali non supportati: "+", ".join(sorted(unknown_channels)))
            runtime=prepare_runtime_property(payload.get("propertyData"))
            if runtime:
                property_id,property_path=runtime
            else:
                property_id=safe_property_id(payload.get("propertyId"))
                property_path=resolve_property_path(property_id)
                if property_path is None:
                    raise ValueError("Struttura non registrata: inviare propertyData")
        except (ValueError,json.JSONDecodeError) as exc:
            self._json(400,{"error":str(exc)}); return

        with STATE.lock,AUTO_STATE.lock,AGENT_RUN_LOCK:
            specialists_active=any(v.get("state") in {"running","queued"} for v in AGENT_RUNS.values())
            if STATE.running or AUTO_STATE.running or specialists_active:
                self._json(409,{"error":"Un'altra rilevazione Velora e' gia' in corso"}); return
            output=result_path(property_id)
            try:
                output.unlink(missing_ok=True)
            except OSError:
                self._json(500,{"error":"Impossibile preparare il file dei risultati locali"}); return
            STATE.running=True
            STATE.error=""
            STATE.property_id=property_id
            STATE.property_path=property_path
            STATE.intervention={}
            STATE.intervention_action=""
            STATE.intervention_event.clear()
        months=int(payload["months"])
        ghost=bool(payload.get("ghost",False))
        assisted=bool(payload.get("assisted",False))
        pricing_only=bool(payload.get("pricingOnly",True))
        threading.Thread(
            target=run_pilot,
            args=(property_id,property_path,months,requested_channels,ghost,assisted,pricing_only,custom_period),
            daemon=True,
        ).start()
        self._json(202,{
            "running":True,"propertyId":property_id,"ghost":ghost,"assisted":assisted,
            "months":months,"customPeriod":custom_period,"channels":requested_channels,"pricingOnly":pricing_only,
        })


if __name__=="__main__":
    if not (DIST/"index.html").exists():
        print("Build locale non presente: va bene se usi Velora online; restano attive le API locali.",flush=True)

    pilot_build=ensure_pilot_sync()

    print("Versione agente: velora-local-agent-v125 · rete agenti e sessioni OTA",flush=True)
    if agent_network is None:
        print("ERRORE RETE AGENTI: "+specialist_unavailable_message(),flush=True)
    else:
        count=len(agent_network.AGENTS)
        print(f"RETE AGENTI: {count}/12 specialisti caricati · revisore {agent_network.REVIEWER_NAME} disponibile",flush=True)
        if count!=12:
            print("ERRORE RETE AGENTI: numero specialisti inatteso. Non avviare i test.",flush=True)
    print(f"Versione pilot: {pilot_build}",flush=True)
    print(f"Cartella runtime locale: {STATE_ROOT}",flush=True)
    if pilot_build != EXPECTED_PILOT_BUILD:
        print("ATTENZIONE: browser_audit_pilot.py non e aggiornato; Prova un mese restera' bloccata.",flush=True)
    print(f"Agente Velora: http://{HOST}:{PORT}/  (Ctrl+C per fermare)",flush=True)
    print("Puoi continuare a usare Velora online: il browser pubblico si colleghera' a questo agente locale.",flush=True)
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
