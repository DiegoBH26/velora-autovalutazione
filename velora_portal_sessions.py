"""Manual-only customer portal sessions for Velora.

This module never reads, types, logs or stores passwords / one-time codes.
A person signs in directly in a visible Chrome window. Separate persistent
profiles keep sessions independent across portals and property analyses.
It does NOT scrape authenticated pages or circumvent access restrictions.
"""
from __future__ import annotations

import asyncio
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright

PORTALS = {
    "expedia": {
        "name": "Ercole", "label": "Expedia", "home": "https://www.expedia.it/",
        "authentication": "Email + codice temporaneo; inserimento manuale.",
        "scraping": "disabled_until_authorized",
    },
    "vrbo": {
        "name": "Atlante", "label": "Vrbo", "home": "https://www.vrbo.com/it-it/",
        "authentication": "Account One Key Expedia + codice temporaneo; inserimento manuale.",
        "scraping": "disabled_until_authorized",
    },
    "holidu": {
        "name": "Mercurio", "label": "Holidu", "home": "https://www.holidu.it/",
        "authentication": "Email + password; inserimento manuale.",
        "scraping": "disabled_until_authorized",
    },
}
SESSION_MAX_SECONDS = 45 * 60

class ManualPortalSessions:
    """One supervised browser per portal, a single active manual login at a time."""
    def __init__(self, state_root: Path):
        self.base = state_root / "portal-sessions"
        self.base.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.state = {
            key: {"state": "idle", "message": "Accesso non ancora preparato."}
            for key in PORTALS
        }
        self.stop_events: dict[str, threading.Event] = {}

    def statuses(self) -> dict:
        with self.lock:
            return {key: dict(value) for key, value in self.state.items()}

    def begin(self, portal: str) -> dict:
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        with self.lock:
            if any(v["state"] in ("queued", "open") for v in self.state.values()):
                raise RuntimeError("Completa o chiudi prima la sessione manuale già aperta.")
            stop = threading.Event()
            self.stop_events[portal] = stop
            self.state[portal] = {
                "state": "queued",
                "message": "Apertura browser manuale in corso.",
                "startedAt": datetime.now(timezone.utc).isoformat(),
            }
        threading.Thread(
            target=self._run, args=(portal, stop),
            daemon=True, name=f"velora-manual-login-{portal}"
        ).start()
        return dict(self.state[portal])

    def finish(self, portal: str) -> dict:
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        with self.lock:
            state = self.state[portal]["state"]
            if state not in ("queued", "open"):
                raise RuntimeError("Nessuna sessione manuale aperta.")
            self.stop_events[portal].set()
            self.state[portal]["message"] = "Chiusura del browser e salvataggio del profilo locale..."
            return dict(self.state[portal])

    def _run(self, portal: str, stop: threading.Event) -> None:
        try:
            asyncio.run(self._browser(portal, stop))
            with self.lock:
                self.state[portal] = {
                    "state": "closed",
                    "message": "Finestra chiusa. Profilo Chrome conservato localmente: accesso non verificato automaticamente.",
                    "closedAt": datetime.now(timezone.utc).isoformat(),
                }
            print(f"[SESSIONE] {PORTALS[portal]['name']} ({PORTALS[portal]['label']}) | CHIUSA | Profilo locale conservato; credenziali non acquisite", flush=True)
        except Exception as exc:
            with self.lock:
                self.state[portal] = {
                    "state": "error",
                    "message": f"Impossibile aprire Chrome: {type(exc).__name__}: {str(exc)[:140]}",
                }
            print(f"[SESSIONE] {PORTALS[portal]['name']} ({PORTALS[portal]['label']}) | ERRORE | {type(exc).__name__}", flush=True)
        finally:
            with self.lock:
                self.stop_events.pop(portal, None)

    async def _browser(self, portal: str, stop: threading.Event) -> None:
        config = PORTALS[portal]
        user_data_dir = self.base / portal / "chrome-profile"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                channel="chrome",
                headless=False,
                locale="it-IT",
                timezone_id="Europe/Rome",
                viewport={"width": 1280, "height": 850},
                args=["--window-position=80,80", "--window-size=1300,900"],
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(config["home"], wait_until="domcontentloaded", timeout=45000)
                with self.lock:
                    self.state[portal] = {
                        "state": "open",
                        "message": "Browser aperto: effettua personalmente l'accesso, poi premi Chiudi sessione in Velora.",
                        "startedAt": self.state[portal].get("startedAt"),
                    }
                print(f"[SESSIONE] {config['name']} ({config['label']}) | APERTA | Login manuale richiesto; nessuna password letta", flush=True)
                await asyncio.to_thread(stop.wait, SESSION_MAX_SECONDS)
            finally:
                await context.close()


__all__ = ["PORTALS", "SESSION_MAX_SECONDS", "ManualPortalSessions"]
