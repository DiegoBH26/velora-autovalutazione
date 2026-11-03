"""Authorized portal profiles and optional local Windows credential-assisted login.

Only the Windows user controls the local account; passwords stay in Windows
Credential Manager and are never written to source, results or logs. CAPTCHA,
OTP, identity checks and account restrictions require direct human action.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import threading
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

from playwright.async_api import async_playwright
from velora_portal_credentials import WindowsPortalVault

PORTALS = {
    "expedia": {
        "name": "Ercole", "label": "Expedia", "home": "https://www.expedia.it/",
        "authentication": "Email + codice temporaneo; inserimento manuale.",
        "scraping": "account_profile_opt_in_test",
    },
    "vrbo": {
        "name": "Atlante", "label": "Vrbo", "home": "https://www.vrbo.com/it-it/",
        "authentication": "Account One Key Expedia + codice temporaneo; inserimento manuale.",
        "scraping": "account_profile_opt_in_test",
    },
    "holidu": {
        "name": "Mercurio", "label": "Holidu", "home": "https://www.holidu.it/",
        "authentication": "Email + password; inserimento manuale.",
        "scraping": "account_profile_opt_in_test",
    },
}
SESSION_MAX_SECONDS = 45 * 60
HUMAN_LOGIN_MAX_SECONDS = 15 * 60

class ManualPortalSessions:
    """One supervised browser per portal, a single active manual login at a time."""
    def __init__(self, state_root: Path):
        self.base = state_root / "portal-sessions"
        self.base.mkdir(parents=True, exist_ok=True)
        self.vault = WindowsPortalVault() if os.name == "nt" else None
        self.lock = threading.Lock()
        self.state = {
            key: {"state": "idle", "message": "Accesso non ancora preparato."}
            for key in PORTALS
        }
        self.stop_events: dict[str, threading.Event] = {}
        self.auth_resume_events: dict[str, threading.Event] = {}
        self.pending_urls: dict[str, str] = {}
        self.account_workers: dict[str, threading.Thread] = {}
        self.firefox_test = {"state": "idle", "result": "", "message": "Test Firefox non ancora avviato."}
        self.firefox_stop = threading.Event()
        self.firefox_thread: threading.Thread | None = None

    def profile_dir(self, portal: str) -> Path:
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        return self.base / portal / "chrome-profile"

    def has_saved_profile(self, portal: str) -> bool:
        # This detects a Chrome profile, not whether its authentication is valid.
        profile=self.profile_dir(portal)
        return (profile / "Local State").is_file() or (profile / "Default" / "Preferences").is_file()

    def statuses(self) -> dict:
        with self.lock:
            entries={key: dict(value) for key,value in self.state.items()}
        for portal,state in entries.items():
            state["profileSaved"]=self.has_saved_profile(portal)
            state["credentialSaved"]=self.has_credentials(portal)
        return entries


    def has_credentials(self, portal: str) -> bool:
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        return bool(self.vault and self.vault.exists(portal))


    def firefox_test_status(self) -> dict:
        """Diagnostic-only Firefox state; never reused as Chrome auth readiness."""
        with self.lock:
            return dict(self.firefox_test)

    def start_firefox_test(self) -> dict:
        """One explicit Expedia compatibility check, not a CAPTCHA bypass."""
        with self.lock:
            if self.firefox_thread and self.firefox_thread.is_alive():
                raise RuntimeError("Un test Firefox è già aperto. Chiudilo prima di riprovare.")
            if any(row.get("state") in {"queued", "open", "awaiting_user", "authenticating"}
                   for row in self.state.values()):
                raise RuntimeError("Completa prima l'accesso Chrome già aperto.")
            self.firefox_stop = threading.Event()
            self.firefox_test = {
                "state": "starting", "result": "",
                "message": "Preparo Firefox Playwright separato da Chrome. Nessuna scansione o login eseguito.",
                "startedAt": datetime.now(timezone.utc).isoformat(),
            }
            self.firefox_thread = threading.Thread(
                target=self._firefox_test_worker, daemon=True,
                name="velora-firefox-expedia-test",
            )
            self.firefox_thread.start()
            return dict(self.firefox_test)

    def close_firefox_test(self) -> dict:
        with self.lock:
            if not self.firefox_thread or not self.firefox_thread.is_alive():
                raise RuntimeError("Non c'è un test Firefox attivo.")
            self.firefox_stop.set()
            self.firefox_test["message"] = (
                "Chiusura richiesta: conserverò il risultato diagnostico e il profilo Firefox separato."
            )
            return dict(self.firefox_test)

    def _set_firefox_test(self, state: str, message: str, result: str | None = None) -> None:
        with self.lock:
            self.firefox_test["state"] = state
            self.firefox_test["message"] = message
            if result is not None:
                self.firefox_test["result"] = result
        print(f"[FIREFOX TEST] Expedia | {state.upper()} | {message[:240]}", flush=True)

    def _firefox_test_worker(self) -> None:
        try:
            asyncio.run(self._run_firefox_test())
        except Exception as exc:
            self._set_firefox_test(
                "error",
                f"Firefox non utilizzabile: {type(exc).__name__}: {str(exc)[:230]}. "
                "Chrome e i risultati esistenti non sono stati modificati.",
                "error",
            )
        finally:
            with self.lock:
                self.firefox_thread = None

    async def _run_firefox_test(self) -> None:
        async with async_playwright() as playwright:
            firefox_path = Path(playwright.firefox.executable_path)
            if not firefox_path.is_file():
                self._set_firefox_test(
                    "installing", "Installo Firefox di Playwright sul PC (solo al primo test)."
                )
                result = await asyncio.to_thread(
                    subprocess.run,
                    [sys.executable, "-m", "playwright", "install", "firefox"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=240,
                    check=False,
                )
                if result.returncode != 0 or not firefox_path.is_file():
                    raise RuntimeError(
                        "Installazione Firefox Playwright non riuscita. "
                        "Controlla connessione internet e permessi del PC."
                    )
            if self.firefox_stop.is_set():
                self._set_firefox_test("closed", "Test annullato prima dell'apertura.")
                return
            self._set_firefox_test(
                "navigating",
                "Avvio Firefox dedicato e apro Expedia una sola volta, senza aggirare controlli.",
            )
            profile = self.base / "expedia" / "firefox-test-profile"
            profile.mkdir(parents=True, exist_ok=True)
            context = await playwright.firefox.launch_persistent_context(
                user_data_dir=str(profile), headless=False,
                locale="it-IT", timezone_id="Europe/Rome",
                viewport={"width": 1280, "height": 850},
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(
                    PORTALS["expedia"]["home"],
                    wait_until="domcontentloaded", timeout=45000,
                )
                await page.wait_for_timeout(1200)
                reason = await self._access_restricted_reason(page)
                if reason:
                    self._set_firefox_test(
                        "blocked",
                        "Expedia limita anche Firefox automatizzato. Nessun altro tentativo "
                        "e nessun login eseguito: puoi chiudere il test.",
                        "blocked",
                    )
                else:
                    email = page.locator(
                        'input[type="email"],input[autocomplete="username"]'
                    )
                    if not await self._has_visible(email):
                        signin = await self._signin_button(page)
                        if signin is not None:
                            self._set_firefox_test(
                                "opening_login",
                                "Pagina Expedia aperta; provo una sola volta il pulsante Accedi.",
                            )
                            try:
                                await signin.click(timeout=10000)
                                await page.wait_for_timeout(1200)
                            except Exception:
                                self._set_firefox_test(
                                    "manual_check",
                                    "Expedia si apre con Firefox, ma il pulsante Accedi "
                                    "non è cliccabile automaticamente. Controlla "
                                    "cookie o avvisi nella finestra Firefox.",
                                    "manual_check",
                                )
                        else:
                            self._set_firefox_test(
                                "manual_check",
                                "Expedia si apre con Firefox ma non riconosco Accedi. "
                                "Verifica eventuale popup privacy nella finestra.",
                                "manual_check",
                            )
                    reason = await self._access_restricted_reason(page)
                    if reason:
                        self._set_firefox_test(
                            "blocked",
                            "Expedia ha limitato Firefox dopo l'apertura di Accedi. "
                            "Non verranno effettuati altri tentativi.",
                            "blocked",
                        )
                    elif await self._has_visible(
                        page.locator('input[type="email"],input[autocomplete="username"]')
                    ):
                        self._set_firefox_test(
                            "login_reached",
                            "RISULTATO POSITIVO: Firefox Playwright è arrivato "
                            "alla schermata email di Expedia. Non significa che "
                            "la sessione sia autenticata o che lo scraping funzioni.",
                            "login_reached",
                        )
                    elif self.firefox_test_status()["state"] not in {
                        "manual_check", "blocked"
                    }:
                        self._set_firefox_test(
                            "manual_check",
                            "Expedia è aperto su Firefox ma il campo email "
                            "non è comparso: verifica la finestra e segnala "
                            "che cosa mostra.",
                            "manual_check",
                        )
                # Leave the actual test browser visible so the user can inspect
                # or screenshot it. The browser/profile is isolated from Ercole.
                await asyncio.to_thread(self.firefox_stop.wait, 300)
                previous = self.firefox_test_status()
                self._set_firefox_test(
                    "closed",
                    previous["message"] + " Browser Firefox di prova chiuso.",
                    previous.get("result") or "inconclusive",
                )
            finally:
                await context.close()

    def account_info(self, portal: str) -> dict:
        """Exact saved email, only for the local token-protected account route."""
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        if self.vault is None:
            raise RuntimeError("Il Gestore credenziali Windows non è disponibile.")
        email=self.vault.saved_email(portal)
        return {"credentialSaved":email is not None, "savedEmail":email or ""}

    def save_credentials(self, portal: str, email: str, password: str) -> dict:
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        if self.vault is None:
            raise RuntimeError("Le credenziali protette sono disponibili soltanto sul PC Windows.")
        email=str(email or "").strip()
        # When re-saving the same account with an empty password field,
        # preserve a previously stored password instead of silently wiping it.
        existing=self.vault.load(portal)
        if existing and existing[0].casefold()==email.casefold() and not password:
            password=existing[1]
        self.vault.save(portal, email, password)
        # The write must be read back successfully from Windows before the
        # user can see a "saved" confirmation. Never return the password.
        actual=self.vault.saved_email(portal)
        if actual!=email:
            raise RuntimeError(
                "Salvataggio non confermato: Windows non restituisce l'email attesa."
            )
        return {**self.account_info(portal), "profileSaved":self.has_saved_profile(portal)}

    def remove_credentials(self, portal: str) -> dict:
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        if self.vault is None:
            raise RuntimeError("Il Gestore credenziali Windows non è disponibile.")
        self.vault.remove(portal)
        return {**self.account_info(portal), "profileSaved":self.has_saved_profile(portal)}


    def start_account_check(self, portal: str) -> dict:
        """Start a separate visible login check without starting any OTA scan."""
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        if not self.has_credentials(portal):
            raise RuntimeError(
                "Prima salva l'email dell'account esistente in «Configura credenziali» "
                "(password vuota se Expedia/Vrbo usa un codice)."
            )
        with self.lock:
            if any(value.get("state") in {"queued", "open", "awaiting_user", "authenticating"}
                   for value in self.state.values()):
                raise RuntimeError(
                    "Completa prima il login già aperto su Expedia, Vrbo o Holidu."
                )
            self.state[portal] = {
                "state": "authenticating",
                "message": "Apertura Chrome: verifica accesso prima della scansione.",
                "startedAt": datetime.now(timezone.utc).isoformat(),
            }
        thread = threading.Thread(
            target=self._account_check_worker,
            args=(portal,), daemon=True,
            name=f"velora-account-check-{portal}",
        )
        with self.lock:
            self.account_workers[portal] = thread
        thread.start()
        return dict(self.state[portal])

    def _account_check_worker(self, portal: str) -> None:
        try:
            note = asyncio.run(
                self.prepare_account_session(portal, require_confirmation=True)
            )
            verified = "verifica completata manualmente" in note
            with self.lock:
                self.state[portal] = {
                    "state": "ready" if verified else "unverified",
                    "message": (
                        "Accesso confermato su Chrome e profilo conservato: "
                        "puoi avviare l'agente Account."
                        if verified else
                        "Accesso non confermato: " + note
                    ),
                    "checkedAt": datetime.now(timezone.utc).isoformat(),
                }
            print(
                f"[ACCOUNT] {PORTALS[portal]['name']} | "
                f"{'CONFERMATO' if verified else 'DA VERIFICARE'} | "
                "Chrome chiuso, profilo locale conservato",
                flush=True,
            )
        except Exception as exc:
            is_portal_block="ACCESSO LIMITATO DAL PORTALE" in str(exc)
            with self.lock:
                self.state[portal] = {
                    "state": "access_limited" if is_portal_block else "error",
                    "message": (
                        str(exc)[:440] if is_portal_block else
                        f"Login non completato ({type(exc).__name__}): "
                        f"{str(exc)[:210]}"
                    ),
                }
            print(
                f"[ACCOUNT] {PORTALS[portal]['name']} | "
                f"{'ACCESSO LIMITATO DAL PORTALE' if is_portal_block else 'ERRORE'} | "
                f"{type(exc).__name__}",
                flush=True,
            )
        finally:
            with self.lock:
                self.account_workers.pop(portal, None)

    def resume_agent_login(self, portal: str) -> dict:
        """The signed-in user confirms that they personally completed the code step."""
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        with self.lock:
            if self.state[portal].get("state") != "awaiting_user":
                raise RuntimeError("Nessun codice di accesso in attesa per questo portale.")
            event = self.auth_resume_events.get(portal)
            if event is None:
                raise RuntimeError("La sessione di verifica è scaduta o non è più attiva.")
            event.set()
            self.state[portal]["message"] = "Conferma ricevuta. Verifica la pagina e riprende la scansione."
            return dict(self.state[portal])

    async def _wait_for_human_login(self, portal: str, page, explanation: str) -> str:
        """Keep the SAME authenticated Chrome window open while the user enters OTP."""
        await self._require_access_not_blocked(page)
        event = threading.Event()
        with self.lock:
            if self.state[portal].get("state") in {"open", "queued", "awaiting_user"}:
                raise RuntimeError("È già aperta una sessione di accesso per questo portale.")
            self.auth_resume_events[portal] = event
            self.state[portal] = {
                "state": "awaiting_user",
                "message": explanation,
                "startedAt": datetime.now(timezone.utc).isoformat(),
            }
        print(f"[ASSISTENZA LOGIN] {PORTALS[portal]['name']} | IN ATTESA | Codice o verifica richiesti nella finestra Chrome", flush=True)
        success = False
        try:
            confirmed = await asyncio.to_thread(event.wait, HUMAN_LOGIN_MAX_SECONDS)
            if not confirmed:
                raise RuntimeError(
                    "VERIFICA SCADUTA: non è arrivata la conferma entro 15 minuti. "
                    "Ripeti ▶ Account per un nuovo tentativo."
                )
            await page.wait_for_timeout(1800)
            await self._require_access_not_blocked(page)
            if await self._needs_human_challenge(page):
                raise RuntimeError(
                    "ACCESSO NON COMPLETATO: il codice o la verifica di sicurezza sono "
                    "ancora visibili nella finestra Chrome. Completa l'accesso e riprova."
                )
            login_fields = page.locator(
                'input[type="email"],input[type="password"],'
                'input[autocomplete="username"],input[autocomplete="one-time-code"]'
            )
            if await self._has_visible(login_fields):
                raise RuntimeError(
                    "ACCESSO NON COMPLETATO: la pagina mostra ancora i campi di login. "
                    "Completa la verifica prima di riprendere."
                )
            login_path = urlparse(page.url).path.lower()
            if any(term in login_path for term in ("/login", "/signin", "/sign-in", "/authentication")):
                raise RuntimeError(
                    "ACCESSO NON COMPLETATO: sei ancora nella schermata di autenticazione."
                )
            is_closed = getattr(page, "is_closed", None)
            if callable(is_closed) and is_closed():
                raise RuntimeError("ACCESSO NON COMPLETATO: hai chiuso Chrome prima della conferma.")
            if await self._looks_signed_out(page):
                raise RuntimeError(
                    "ACCESSO NON COMPLETATO: il portale mostra ancora «Accedi». "
                    "Completa la verifica nel Chrome dedicato prima di riprendere."
                )
            success = True
            return "verifica completata manualmente; sessione riutilizzata su conferma dell'utente"
        finally:
            with self.lock:
                self.auth_resume_events.pop(portal, None)
                self.state[portal] = {
                    "state": "closed" if success else "error",
                    "message": (
                        "Accesso completato; profilo Chrome conservato."
                        if success else
                        "Accesso non verificato o scaduto; segui l'errore dell'agente."
                    ),
                }

    @staticmethod
    async def _request_one_time_code(page) -> bool:
        """Click a visible 'send code' action once; never read/submit the OTP."""
        pattern = re.compile(
            r"\b(invia|inviami|manda|send|get|receive|ricevi|richiedi|request)\b.{0,35}"
            r"\b(codice|code|otp|verification)\b",
            re.IGNORECASE
        )
        # The first Continue button often sends a code already. Never click
        # "resend" and invalidate the OTP that the user just received.
        if await ManualPortalSessions._has_visible(page.locator(
            'input[autocomplete="one-time-code"],input[name*="otp" i],'
            'input[id*="otp" i],input[name*="verificationCode" i]'
        )):
            return False
        try:
            body = (await page.locator("body").inner_text(timeout=3000))[:3500].lower()
            if any(x in body for x in (
                "codice inviato", "codice è stato inviato", "abbiamo inviato un codice",
                "code sent", "code was sent", "we sent a code", "we've sent a code",
            )):
                return False
        except Exception:
            pass
        for role in ("button", "link"):
            candidate = page.get_by_role(role, name=pattern)
            if await ManualPortalSessions._has_visible(candidate):
                await candidate.first.click(timeout=9000)
                await page.wait_for_timeout(700)
                return True
        return False

    async def prepare_account_session(self, portal: str, require_confirmation: bool = False) -> str:
        """Try one authorized login without bypassing portal security challenges.

        An existing persistent profile is reused. If the service has logged the
        account out, attempt one password login. OTP, CAPTCHA or an unrecognized
        screen PAUSE the scan; user enters OTP in Chrome, then explicitly resumes.
        """
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        saved = self.vault.load(portal) if self.vault is not None else None
        if saved is None:
            return "profilo Chrome esistente; credenziali non memorizzate"
        email, password = saved
        profile = self.profile_dir(portal)
        profile.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile), channel="chrome", headless=False,
                chromium_sandbox=True, locale="it-IT", timezone_id="Europe/Rome",
                viewport={"width": 1280, "height": 850},
                args=["--window-position=80,80", "--window-size=1300,900"],
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(PORTALS[portal]["home"], wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(1200)
                await self._require_access_not_blocked(page)
                if await self._needs_human_challenge(page):
                    return await self._wait_for_human_login(
                        portal, page,
                        "Completa il codice temporaneo o la verifica di sicurezza nel Chrome dedicato, "
                        "poi premi «Ho completato l'accesso · Riprendi» in Velora."
                    )
                email_field = page.locator('input[type="email"],input[autocomplete="username"]')
                if not await self._has_visible(email_field):
                    signin = await self._signin_button(page)
                    if signin is None:
                        # An invisible sign-in control is not proof that this account
                        # is logged in. For a standalone login check ask the user to
                        # inspect the opened Chrome before marking it prepared.
                        if require_confirmation:
                            return await self._wait_for_human_login(
                                portal, page,
                                "Verifica sul sito Expedia/Vrbo che compaia il tuo account. "
                                "Se compare Accedi, completa il login e inserisci il codice. "
                                "Poi premi «Ho completato l\'accesso · Riprendi»."
                            )
                        return "sessione Chrome riutilizzata, accesso effettivo da verificare"
                    try:
                        await signin.click(timeout=6000)
                        await page.wait_for_timeout(1250)
                        await self._require_access_not_blocked(page)
                    except RuntimeError:
                        # Preserve explicit Expedia/Vrbo restriction errors.
                        raise
                    except Exception:
                        return await self._wait_for_human_login(
                            portal, page,
                            "Apertura del login non riconosciuta: completa l'accesso nel Chrome "
                            "dedicato e premi «Ho completato l'accesso · Riprendi»."
                        )
                if await self._needs_human_challenge(page):
                    return await self._wait_for_human_login(
                        portal, page,
                        "Il portale richiede una verifica: completala nel Chrome dedicato "
                        "e premi «Ho completato l'accesso · Riprendi»."
                    )
                email_field = page.locator('input[type="email"],input[autocomplete="username"]')
                if not await self._has_visible(email_field):
                    # A previously valid session may redirect directly into the account.
                    if await self._looks_signed_out(page):
                        return await self._wait_for_human_login(
                            portal, page,
                            "Login non riconosciuto: accedi nella finestra Chrome "
                            "e poi premi «Ho completato l'accesso · Riprendi»."
                        )
                    if require_confirmation:
                        return await self._wait_for_human_login(
                            portal, page,
                            "Controlla nella finestra Chrome che Expedia/Vrbo mostri il tuo account. "
                            "Se serve il codice, completalo lì. Poi premi «Ho completato l\'accesso · Riprendi»."
                        )
                    return "sessione Chrome riutilizzata, accesso effettivo da verificare"
                self._ensure_login_host(portal, page.url)
                await email_field.first.fill(email, timeout=9000)
                continue_button = await self._submit_button(page)
                if continue_button is None:
                    return await self._wait_for_human_login(
                        portal, page,
                        "Non trovo il pulsante per inviare il codice: premilo direttamente "
                        "nel Chrome aperto, inserisci il codice e poi premi Riprendi."
                    )
                await continue_button.click(timeout=9000)
                await page.wait_for_timeout(1400)
                await self._require_access_not_blocked(page)
                # If Continue already triggered an OTP, don't send another one.
                # Otherwise click "Invia codice" once, when safely recognizable.
                if not await self._needs_human_challenge(page):
                    await self._request_one_time_code(page)
                    await self._require_access_not_blocked(page)
                if await self._needs_human_challenge(page):
                    return await self._wait_for_human_login(
                        portal, page,
                        "Codice inviato o verifica richiesta. Inseriscilo sul portale "
                        "nella finestra Chrome; quando sei dentro premi «Ho completato l'accesso · Riprendi»."
                    )
                password_field = page.locator('input[type="password"]')
                if not await self._has_visible(password_field):
                    # Expedia/One Key often uses an emailed code instead of a
                    # password. We cannot infer success from submitting an email.
                    return await self._wait_for_human_login(
                        portal, page,
                        "Expedia/Vrbo usa il codice ricevuto sul telefono o via email. "
                        "Inseriscilo direttamente nel Chrome aperto, senza comunicarlo a Velora. "
                        "Quando compare il tuo account, premi «Ho completato l'accesso · Riprendi»."
                    )
                if await self._has_visible(password_field):
                    if not password:
                        return await self._wait_for_human_login(
                            portal, page,
                            "Questo portale richiede una password. Inseriscila nel Chrome dedicato "
                            "e premi «Ho completato l'accesso · Riprendi»."
                        )
                    self._ensure_login_host(portal, page.url)
                    await password_field.first.fill(password, timeout=9000)
                    submit = await self._submit_button(page)
                    if submit is None:
                        raise RuntimeError("LOGIN DA VERIFICARE: conferma password non riconosciuta.")
                    await submit.click(timeout=9000)
                    await page.wait_for_timeout(1600)
                if await self._needs_human_challenge(page):
                    return await self._wait_for_human_login(
                        portal, page,
                        "Codice temporaneo o CAPTCHA richiesto: risolvi la verifica manualmente "
                        "nel Chrome dedicato e premi «Ho completato l'accesso · Riprendi»."
                    )
                if await self._has_visible(page.locator('input[type="email"],input[type="password"]')):
                    raise RuntimeError(
                        "LOGIN NON CONFERMATO: il form di accesso è ancora visibile. "
                        "Controlla credenziali e messaggi del portale nel Chrome dedicato."
                    )
                login_path = urlparse(page.url).path.lower()
                if any(segment in login_path for segment in ("/login","/signin","/sign-in","/authentication")):
                    raise RuntimeError(
                        "LOGIN NON CONFERMATO: la pagina di autenticazione è ancora aperta. "
                        "Verifica il portale tramite Apri accesso e Chiudi e conserva."
                    )
                return "tentativo di login automatico completato; autenticazione da verificare sul sito"
            finally:
                await context.close()

    @staticmethod
    async def _has_visible(locator) -> bool:
        try:
            count = min(await locator.count(), 5)
            for index in range(count):
                if await locator.nth(index).is_visible():
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    async def _access_restricted_reason(page) -> str | None:
        """Detect a portal-imposed access denial, not an ordinary email OTP.

        An Expedia bot/access block is NOT a challenge that can be resolved by
        inserting an email code. Never repeatedly refresh or retry it.
        """
        try:
            body=(await page.locator("body").inner_text(timeout=4000))[:6000].casefold()
        except Exception:
            body=""
        triggers=(
            "l'accesso è temporaneamente limitato",
            "l’accesso è temporaneamente limitato",
            "your access to this site has been temporarily limited",
            "your access has been temporarily limited",
        )
        if any(item in body for item in triggers):
            return (
                "ACCESSO LIMITATO DAL PORTALE: Expedia/Vrbo ha mostrato una "
                "pagina di restrizione temporanea prima del login. "
                "Non è la richiesta del codice email e Velora non può "
                "procedere automaticamente. Nessun tentativo ripetuto: "
                "verifica l'accesso dal browser normale e, se il blocco "
                "persiste, usa l'assistenza del portale."
            )
        return None

    @staticmethod
    async def _expedia_robot_challenge(page) -> bool:
        """Detect the separate human-check page without solving or bypassing it."""
        try:
            title = (await page.title()).casefold()
            if "sei un robot" in title or "are you a robot" in title:
                return True
        except Exception:
            pass
        try:
            return await ManualPortalSessions._has_visible(
                page.locator("#app-captcha-pwa")
            )
        except Exception:
            return False

    @classmethod
    async def _require_access_not_blocked(cls, page) -> None:
        reason=await cls._access_restricted_reason(page)
        if reason:
            raise RuntimeError(reason)

    @staticmethod
    async def _needs_human_challenge(page) -> bool:
        selectors = (
            'input[autocomplete="one-time-code"],'
            'input[name*="otp" i],input[id*="otp" i],'
            'iframe[src*="captcha" i],iframe[title*="captcha" i],'
            'input[name*="verificationCode" i],'
            '#app-captcha-pwa'
        )
        if await ManualPortalSessions._has_visible(page.locator(selectors)):
            return True
        if await ManualPortalSessions._expedia_robot_challenge(page):
            return True
        try:
            text = (await page.locator("body").inner_text(timeout=4000))[:2800].lower()
            # Only use high-specificity challenge terms; do not flag banners.
            return any(term in text for term in (
                "inserisci il codice di verifica",
                "enter the verification code",
                "verify that you're human",
                "verifica che tu sia una persona",
                "codice temporaneo inviato",
                "mostraci il tuo lato umano",
                "non siamo sicuri se sei un essere umano o un robot",
                "show us your human side",
            ))
        except Exception:
            return False

    @staticmethod
    def _ensure_login_host(portal: str, url: str) -> None:
        host = (urlparse(url).hostname or "").lower()
        allowed = {
            "expedia": ("expedia.it", "expedia.com", "expediagroup.com"),
            "vrbo": ("vrbo.com", "expedia.com", "expediagroup.com"),
            "holidu": ("holidu.it", "holidu.com"),
        }[portal]
        if not any(host == domain or host.endswith("." + domain) for domain in allowed):
            raise RuntimeError("LOGIN INTERROTTO: dominio inatteso, credenziali non inserite.")

    @staticmethod
    async def _looks_signed_out(page) -> bool:
        signin = await ManualPortalSessions._signin_button(page)
        return signin is not None

    @staticmethod
    async def _signin_button(page):
        pattern = re.compile(r"^(accedi|sign in|log in|login)$", re.IGNORECASE)
        for role in ("button", "link"):
            loc = page.get_by_role(role, name=pattern)
            if await ManualPortalSessions._has_visible(loc):
                return loc.first
        return None

    @staticmethod
    async def _submit_button(page):
        pattern = re.compile(
            r"^(continua|continue|avanti|next|accedi|sign in|log in|login|conferma)$",
            re.IGNORECASE,
        )
        for role in ("button",):
            loc = page.get_by_role(role, name=pattern)
            if await ManualPortalSessions._has_visible(loc):
                return loc.first
        submit = page.locator('button[type="submit"],input[type="submit"]')
        if await ManualPortalSessions._has_visible(submit):
            return submit.first
        return None

    def begin(self, portal: str) -> dict:
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        with self.lock:
            if any(v["state"] in ("queued", "open", "awaiting_user", "authenticating") for v in self.state.values()):
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

    def navigate(self, portal: str, url: str) -> dict:
        """Only a user-triggered top-level navigation, never data extraction."""
        if portal not in PORTALS:
            raise ValueError("Portale non supportato")
        if not isinstance(url, str) or len(url)>2048:
            raise ValueError("URL annuncio non valido")
        parsed=urlparse(url)
        hosts={
            "expedia":("expedia.it","expedia.com"),
            "vrbo":("vrbo.com",),
            "holidu":("holidu.it","holidu.com"),
        }
        host=(parsed.hostname or "").lower()
        allowed=hosts[portal]
        if parsed.scheme!="https" or parsed.username or parsed.password or parsed.port not in (None,443) or not any(
                host==domain or host.endswith("."+domain) for domain in allowed):
            raise ValueError("Il link deve appartenere al portale selezionato e utilizzare HTTPS")
        with self.lock:
            if self.state[portal]["state"]!="open":
                raise RuntimeError("Apri prima il Chrome dell'agente ed effettua l'accesso.")
            self.pending_urls[portal]=url
            self.state[portal]["message"]="Apertura della scheda richiesta dall'utente. Continua la navigazione nel Chrome dedicato."
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
                self.pending_urls.pop(portal, None)

    async def _browser(self, portal: str, stop: threading.Event) -> None:
        config = PORTALS[portal]
        user_data_dir = self.profile_dir(portal)
        user_data_dir.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                channel="chrome",
                headless=False,
                chromium_sandbox=True,
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
                loop=asyncio.get_running_loop()
                deadline=loop.time()+SESSION_MAX_SECONDS
                while not stop.is_set() and loop.time()<deadline:
                    with self.lock:
                        next_url=self.pending_urls.pop(portal,None)
                    if next_url:
                        try:
                            await page.goto(next_url,wait_until="domcontentloaded",timeout=45000)
                            print(f"[SESSIONE] {config['name']} ({config['label']}) | NAVIGAZIONE | Apertura scheda richiesta dall'utente",flush=True)
                        except Exception as exc:
                            with self.lock:
                                self.state[portal]["message"]="Impossibile aprire la scheda: "+type(exc).__name__
                    await asyncio.sleep(0.6)
            finally:
                await context.close()


__all__ = ["PORTALS", "SESSION_MAX_SECONDS", "ManualPortalSessions"]
