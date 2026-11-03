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
