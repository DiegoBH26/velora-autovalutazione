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
import threading
import types
import unicodedata
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import browser_audit_pilot as browser_pilot

CHANNELS=browser_pilot.CHANNELS
run=browser_pilot.run
EXPECTED_PILOT_BUILD="velora-browser-pilot-v82"
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
OTA_SOURCE_CACHE=STATE_ROOT/"ota-source-cache.json"
CATALOG_PATHS=(ROOT/"database_strutture.xlsx",ROOT/"database_alberghi_familiari_con_320_integrazioni.xlsx")
for _runtime_dir in (STATE_ROOT,RUNTIME_PROPERTIES,RUNTIME_AUDITS,PILOT_RESULTS):
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
        f"{intervention['reason'][:220]}",
        flush=True,
    )
    signaled=STATE.intervention_event.wait(timeout=300)
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

    with STATE.lock,AUTO_STATE.lock:
        if STATE.running or AUTO_STATE.running:
            raise RuntimeError("Non puoi cancellare i dati locali mentre una scansione è in corso.")

    removed=[]
    for path in (runtime_path,auto_audit_output_path(property_id),result_path(property_id)):
        try:
            if path.exists():
                path.unlink()
                removed.append(str(path.name))
        except OSError as exc:
            raise RuntimeError(f"Impossibile cancellare {path.name}: {type(exc).__name__}") from exc

    cache=_read_ota_cache()
    wanted_host=_site_host(website)
    wanted_name=_norm(name)
    removed_cache=[]
    for key,entry in list(cache.items()):
        if not isinstance(entry,dict):
            continue
        entry_host=_site_host(str(entry.get("site") or ""))
        entry_name=_norm(entry.get("name") or "")
        if (wanted_host and entry_host==wanted_host) or (wanted_name and entry_name==wanted_name):
            removed_cache.append(key)
            cache.pop(key,None)
    if removed_cache:
        _write_ota_cache(cache)

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


def run_pilot(property_id,property_path,months,channels,ghost=False,assisted=True):
    try:
        args=argparse.Namespace(
            property=str(property_path),
            output=str(result_path(property_id)),
            channels=",".join(channels),
            months=months,
            today=None,
            dry_run=False,
            ghost=bool(ghost),
            assisted=bool(assisted),
            assist_callback=wait_for_pilot_intervention if assisted else None,
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
                "agentVersion":"velora-local-agent-v82",
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
        if route not in {"/api/pilot/start","/api/pilot/reset","/api/pilot/intervention","/api/audit/start","/api/report/pdf"}:
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

            if route=="/api/pilot/reset":
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
                with AUTO_STATE.lock,STATE.lock:
                    if AUTO_STATE.running or STATE.running:
                        self._json(409,{"error":"Un'altra rilevazione Velora e' gia' in corso"}); return
                    AUTO_STATE.running=True
                    AUTO_STATE.error=""
                    AUTO_STATE.message="Avvio analisi sito ufficiale..."
                    AUTO_STATE.property_id=""
                    AUTO_STATE.result=None
                threading.Thread(target=run_auto_audit,args=(audit_payload,),daemon=True).start()
                self._json(202,{"running":True,"message":"Analisi automatica avviata"})
                return

            if payload.get("months") not in (1,"all"):
                raise ValueError("Periodo non supportato dal pilota")
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

        with STATE.lock,AUTO_STATE.lock:
            if STATE.running or AUTO_STATE.running:
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
        months=1 if payload["months"]==1 else None
        ghost=bool(payload.get("ghost",False))
        assisted=bool(payload.get("assisted",True))
        threading.Thread(
            target=run_pilot,
            args=(property_id,property_path,months,requested_channels,ghost,assisted),
            daemon=True,
        ).start()
        self._json(202,{"running":True,"propertyId":property_id,"ghost":ghost,"assisted":assisted})


if __name__=="__main__":
    if not (DIST/"index.html").exists():
        print("Build locale non presente: va bene se usi Velora online; restano attive le API locali.",flush=True)

    pilot_build=ensure_pilot_sync()

    print("Versione agente: velora-local-agent-v82 · solo frontend pubblico · mai login/account/member · date + ospiti + cerca + tariffe",flush=True)
    print(f"Versione pilot: {pilot_build}",flush=True)
    print(f"Cartella runtime locale: {STATE_ROOT}",flush=True)
    if pilot_build != EXPECTED_PILOT_BUILD:
        print("ATTENZIONE: browser_audit_pilot.py non e aggiornato; Prova un mese restera' bloccata.",flush=True)
    print(f"Agente Velora: http://{HOST}:{PORT}/  (Ctrl+C per fermare)",flush=True)
    print("Puoi continuare a usare Velora online: il browser pubblico si colleghera' a questo agente locale.",flush=True)
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
