"""Live-in-memory regression for assisted One Key OTP handoff (no network/browser)."""
import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path

# CI deliberately does not install browser dependencies: the handoff tests use
# a fake page, so provide only the import-time symbol, never a fake browser.
try:
    import playwright.async_api
except ModuleNotFoundError:
    package=types.ModuleType("playwright")
    package.__path__=[]
    async_api=types.ModuleType("playwright.async_api")
    async_api.async_playwright=None
    sys.modules.setdefault("playwright", package)
    sys.modules.setdefault("playwright.async_api", async_api)

from velora_portal_sessions import ManualPortalSessions


class FakeLocator:
    async def count(self):
        return 0
    async def inner_text(self, timeout=None):
        return ""


class FakeVerifiedPage:
    url = "https://www.expedia.it/"

    def locator(self, selector):
        return FakeLocator()

    def get_by_role(self, role, name=None):
        return FakeLocator()

    async def wait_for_timeout(self, duration):
        await asyncio.sleep(0)


class OtpHandoffTests(unittest.TestCase):
    def test_saved_email_readback_is_exact_and_survives_reopen(self):
        class FakeVault:
            def __init__(self):
                self.records={}
            def load(self,portal):
                return self.records.get(portal)
            def save(self,portal,email,password):
                self.records[portal]=(email,password)
            def saved_email(self,portal):
                stored=self.records.get(portal)
                return stored[0] if stored else None
            def remove(self,portal):
                self.records.pop(portal,None)
        with tempfile.TemporaryDirectory() as root:
            sessions=ManualPortalSessions(Path(root))
            sessions.vault=FakeVault()
            stored=sessions.save_credentials("expedia","user@example.com","")
            self.assertEqual(stored["savedEmail"],"user@example.com")
            self.assertTrue(stored["credentialSaved"])
            self.assertEqual(sessions.account_info("expedia")["savedEmail"],"user@example.com")
            sessions.save_credentials("holidu","another@example.com","private-test-password")
            saved=sessions.save_credentials("holidu","another@example.com","")
            self.assertEqual(saved["savedEmail"],"another@example.com")
            self.assertEqual(sessions.vault.load("holidu")[1],"private-test-password")
            removed=sessions.remove_credentials("expedia")
            self.assertFalse(removed["credentialSaved"])
            self.assertEqual(removed["savedEmail"],"")

    def test_save_refuses_unverified_windows_write(self):
        class MisreportingVault:
            def load(self,portal):
                return None
            def save(self,portal,email,password):
                pass
            def saved_email(self,portal):
                return None
        with tempfile.TemporaryDirectory() as root:
            sessions=ManualPortalSessions(Path(root))
            sessions.vault=MisreportingVault()
            with self.assertRaisesRegex(RuntimeError,"Salvataggio non confermato"):
                sessions.save_credentials("expedia","user@example.com","")

    def test_expedia_access_denial_is_not_an_otp_request(self):
        class BlockLocator(FakeLocator):
            async def inner_text(self, timeout=None):
                return (
                    "Mostraci il tuo lato umano... "
                    "Non siamo sicuri se sei un essere umano o un robot. "
                    "L'accesso è temporaneamente limitato."
                )
        class BlockedExpediaPage(FakeVerifiedPage):
            def locator(self, selector):
                return BlockLocator()
        async def run():
            with tempfile.TemporaryDirectory() as root:
                sessions=ManualPortalSessions(Path(root))
                page=BlockedExpediaPage()
                reason=await sessions._access_restricted_reason(page)
                self.assertIn("ACCESSO LIMITATO DAL PORTALE",reason)
                self.assertIn("Non è la richiesta del codice email",reason)
                with self.assertRaisesRegex(RuntimeError,"ACCESSO LIMITATO DAL PORTALE"):
                    await sessions._wait_for_human_login("expedia",page,"Inserisci codice")
                self.assertEqual(sessions.auth_resume_events,{})
                self.assertEqual(sessions.statuses()["expedia"]["state"],"idle")
        asyncio.run(run())

    def test_access_denial_status_is_visible_and_never_ready(self):
        class FakeVault:
            def exists(self,portal):
                return portal=="expedia"
        async def run():
            with tempfile.TemporaryDirectory() as root:
                sessions=ManualPortalSessions(Path(root))
                sessions.vault=FakeVault()
                async def denied(portal,require_confirmation=False):
                    raise RuntimeError(
                        "ACCESSO LIMITATO DAL PORTALE: blocco temporaneo prima del login"
                    )
                sessions.prepare_account_session=denied
                sessions.start_account_check("expedia")
                for _ in range(150):
                    if sessions.statuses()["expedia"]["state"]=="access_limited":
                        break
                    await asyncio.sleep(.005)
                state=sessions.statuses()["expedia"]
                self.assertEqual(state["state"],"access_limited")
                self.assertIn("blocco temporaneo",state["message"])
                self.assertNotEqual(state["state"],"ready")
        asyncio.run(run())

    def test_resume_is_not_allowed_without_pending_login(self):
        with tempfile.TemporaryDirectory() as root:
            sessions=ManualPortalSessions(Path(root))
            with self.assertRaisesRegex(RuntimeError, "Nessun codice"):
                sessions.resume_agent_login("expedia")

    def test_expedia_waits_for_the_user_then_resumes(self):
        async def run():
            with tempfile.TemporaryDirectory() as root:
                sessions=ManualPortalSessions(Path(root))
                task=asyncio.create_task(sessions._wait_for_human_login(
                    "expedia", FakeVerifiedPage(), "Inserisci il codice sul sito"
                ))
                for _ in range(100):
                    if sessions.statuses()["expedia"]["state"]=="awaiting_user":
                        break
                    await asyncio.sleep(.005)
                self.assertEqual(sessions.statuses()["expedia"]["state"],"awaiting_user")
                self.assertFalse(task.done())
                result=sessions.resume_agent_login("expedia")
                self.assertEqual(result["state"],"awaiting_user")
                message=await asyncio.wait_for(task,timeout=3)
                self.assertIn("sessione riutilizzata",message)
                self.assertEqual(sessions.statuses()["expedia"]["state"],"closed")
                self.assertEqual(sessions.auth_resume_events,{})
        asyncio.run(run())


    def test_standalone_expedia_login_has_its_own_ready_state(self):
        class FakeVault:
            def exists(self, portal):
                return portal == "expedia"
        async def run():
            with tempfile.TemporaryDirectory() as root:
                sessions=ManualPortalSessions(Path(root))
                sessions.vault=FakeVault()
                async def prepared(portal, require_confirmation=False):
                    self.assertEqual(portal,"expedia")
                    self.assertTrue(require_confirmation)
                    return "verifica completata manualmente; sessione riutilizzata su conferma dell'utente"
                sessions.prepare_account_session=prepared
                started=sessions.start_account_check("expedia")
                self.assertIn(started["state"],{"authenticating","ready"})
                for _ in range(150):
                    if sessions.statuses()["expedia"]["state"] == "ready":
                        break
                    await asyncio.sleep(.005)
                entry=sessions.statuses()["expedia"]
                self.assertEqual(entry["state"],"ready")
                self.assertIn("puoi avviare",entry["message"])
                self.assertFalse(bool(sessions.account_workers))
        asyncio.run(run())

    def test_standalone_login_requires_saved_local_email(self):
        with tempfile.TemporaryDirectory() as root:
            sessions=ManualPortalSessions(Path(root))
            sessions.vault=None
            with self.assertRaisesRegex(RuntimeError,"salva l'email"):
                sessions.start_account_check("vrbo")

    def test_incomplete_verification_fails_closed(self):
        class PageWithOtp(FakeVerifiedPage):
            url = "https://www.expedia.it/login"
        async def run():
            with tempfile.TemporaryDirectory() as root:
                sessions=ManualPortalSessions(Path(root))
                task=asyncio.create_task(sessions._wait_for_human_login(
                    "vrbo",PageWithOtp(),"Verifica manuale"
                ))
                for _ in range(100):
                    if sessions.statuses()["vrbo"]["state"]=="awaiting_user":
                        break
                    await asyncio.sleep(.005)
                sessions.resume_agent_login("vrbo")
                with self.assertRaisesRegex(RuntimeError,"ACCESSO NON COMPLETATO"):
                    await asyncio.wait_for(task,timeout=3)
                self.assertEqual(sessions.statuses()["vrbo"]["state"],"error")
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
