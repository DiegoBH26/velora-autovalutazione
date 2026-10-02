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
import re
import secrets
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from browser_audit_pilot import CHANNELS, run
from playwright.async_api import async_playwright
from site_audit_builder import build_site_audit, public_url as validate_site_url

ROOT=Path(__file__).resolve().parent
DIST=ROOT/"dist"
RUNTIME_PROPERTIES=ROOT/"tmp"/"runtime-properties"
RUNTIME_AUDITS=ROOT/"tmp"/"runtime-audits"
RUNTIME_PROPERTIES.mkdir(parents=True,exist_ok=True)
RUNTIME_AUDITS.mkdir(parents=True,exist_ok=True)

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
    return ROOT/f"dati_strutture_pilot_{safe_property_id(property_id)}.json"


def prepare_runtime_property(payload):
    if payload is None:
        return None
    if not isinstance(payload,dict):
        raise ValueError("Dati struttura non validi")
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
    data={"id":property_id,"name":name,"sources":cleaned}
    path=runtime_property_path(property_id)
    tmp=path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)
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


def run_pilot(property_id,property_path,months):
    try:
        args=argparse.Namespace(
            property=str(property_path),
            output=str(result_path(property_id)),
            channels=",".join(CHANNELS),
            months=months,
            today=None,
            dry_run=False,
        )
        asyncio.run(run(args))
    except Exception as exc:
        with STATE.lock:
            STATE.error=f"{type(exc).__name__}: {str(exc)[:240]}"
    finally:
        with STATE.lock:
            STATE.running=False


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
                "agentVersion":"velora-local-agent-v3",
            })
            return
        if route=="/api/pilot/status":
            if self.headers.get("Origin") and not self._allowed_origin():
                self._json(403,{"error":"Origine non autorizzata"}); return
            with STATE.lock:
                running,error,property_id=STATE.running,STATE.error,STATE.property_id
            output=result_path(property_id) if property_id else None
            try:
                result=json.loads(output.read_text(encoding="utf-8")) if output and output.exists() else None
            except (OSError,json.JSONDecodeError):
                result=None
            self._json(200,{"running":running,"error":error,"propertyId":property_id,"result":result})
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
        if route not in {"/api/pilot/start","/api/audit/start","/api/report/pdf"}:
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

            if route=="/api/audit/start":
                website=validate_site_url(payload.get("website"))
                audit_payload={
                    "website":website,
                    "name":str(payload.get("name") or "").strip()[:180],
                    "city":str(payload.get("city") or "").strip()[:100],
                    "province":str(payload.get("province") or "").strip()[:10],
                    "rooms":str(payload.get("rooms") or "").strip()[:10],
                    "propertyType":str(payload.get("propertyType") or "").strip()[:100],
                }
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
        months=1 if payload["months"]==1 else None
        threading.Thread(target=run_pilot,args=(property_id,property_path,months),daemon=True).start()
        self._json(202,{"running":True,"propertyId":property_id})


if __name__=="__main__":
    if not (DIST/"index.html").exists():
        print("Build locale non presente: va bene se usi Velora online; restano attive le API locali.",flush=True)
    print(f"Agente Velora: http://{HOST}:{PORT}/  (Ctrl+C per fermare)",flush=True)
    print("Puoi continuare a usare Velora online: il browser pubblico si colleghera' a questo agente locale.",flush=True)
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
