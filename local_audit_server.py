#!/usr/bin/env python3
"""Serve Velora sul PC e avvia il pilota OTA senza servizi a pagamento.

Il server ascolta solo su 127.0.0.1, usa una struttura predefinita e non
accetta URL arbitrari. L'autenticazione utenti resta quella di Velora.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import secrets
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from browser_audit_pilot import CHANNELS, run
from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
PROPERTIES = {
    "perla-saracena-torre-pali": ROOT / "src" / "perla-saracena-audit.json",
    "casa-albergo-santantonio-alberobello": ROOT / "src" / "santantonio-audit.json",
}
HOST = "127.0.0.1"
PORT = 8768


class PilotState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.running = False
        self.error = ""
        self.property_id = ""


STATE = PilotState()


def result_path(property_id: str) -> Path:
    return ROOT / f"dati_strutture_pilot_{property_id}.json"


def run_pilot(property_id: str, months: int | None) -> None:
    try:
        args = argparse.Namespace(property=str(PROPERTIES[property_id]), output=str(result_path(property_id)),
                                  channels=",".join(CHANNELS), months=months,
                                  today=None, dry_run=False)
        asyncio.run(run(args))
    except Exception as exc:
        with STATE.lock:
            STATE.error = f"{type(exc).__name__}: {str(exc)[:240]}"
    finally:
        with STATE.lock:
            STATE.running = False


async def render_pdf(html: str) -> bytes:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        try:
            context = await browser.new_context(java_script_enabled=False)
            page = await context.new_page()
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(html, wait_until="domcontentloaded", timeout=15000)
            return await page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            await browser.close()


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, directory=str(DIST), **kwargs)

    def _json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/api/pilot/config":
            self._json(200, {"token": STATE.token, "propertyIds": list(PROPERTIES)})
            return
        if urlparse(self.path).path == "/api/pilot/status":
            with STATE.lock:
                running, error, property_id = STATE.running, STATE.error, STATE.property_id
            output = result_path(property_id) if property_id in PROPERTIES else None
            try:
                result = json.loads(output.read_text(encoding="utf-8")) if output and output.exists() else None
            except (OSError, json.JSONDecodeError):
                result = None
            self._json(200, {"running": running, "error": error, "propertyId": property_id, "result": result})
            return
        if self.path.startswith("/api/"):
            self._json(404, {"error": "Percorso sconosciuto"})
            return
        return super().do_GET()

    def do_POST(self) -> None:
        if self.path not in ("/api/pilot/start", "/api/report/pdf"):
            self._json(404, {"error": "Percorso sconosciuto"})
            return
        origin = self.headers.get("Origin", "")
        expected = f"http://{HOST}:{PORT}"
        if (origin != expected or self.headers.get("X-Velora-Local-Token") != STATE.token
                or self.headers.get_content_type() != "application/json"):
            self._json(403, {"error": "Richiesta locale non autorizzata"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= (512 if self.path == "/api/pilot/start" else 5_000_000):
                raise ValueError("Dimensione richiesta non valida")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Richiesta JSON non valida")
            if self.path == "/api/report/pdf":
                html = payload.get("html")
                if not isinstance(html, str) or not html.lstrip().lower().startswith("<!doctype html"):
                    raise ValueError("Report HTML non valido")
                try:
                    pdf = asyncio.run(render_pdf(html))
                except Exception as exc:
                    self._json(500, {"error": f"Chrome non ha generato il PDF: {type(exc).__name__}"})
                    return
                filename = re.sub(r"[^a-zA-Z0-9._-]", "-", str(payload.get("filename", "report-velora.pdf")))[:100]
                if not filename.endswith(".pdf"):
                    filename += ".pdf"
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(pdf)))
                self.end_headers()
                self.wfile.write(pdf)
                return
            if payload.get("propertyId") not in PROPERTIES or payload.get("months") not in (1, "all"):
                raise ValueError("Struttura o periodo non supportato dal pilota")
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        with STATE.lock:
            if STATE.running:
                self._json(409, {"error": "Rilevazione già in corso"})
                return
            output = result_path(payload["propertyId"])
            try:
                output.unlink(missing_ok=True)
            except OSError:
                self._json(500, {"error": "Impossibile preparare il file dei risultati locali"})
                return
            STATE.running = True
            STATE.error = ""
            STATE.property_id = payload["propertyId"]
        months = 1 if payload["months"] == 1 else None
        threading.Thread(target=run_pilot, args=(payload["propertyId"], months), daemon=True).start()
        self._json(202, {"running": True})


if __name__ == "__main__":
    if not (DIST / "index.html").exists():
        raise SystemExit("Prima crea la versione locale con: npm run build")
    print(f"Velora locale: http://{HOST}:{PORT}/ (Ctrl+C per fermare)", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
