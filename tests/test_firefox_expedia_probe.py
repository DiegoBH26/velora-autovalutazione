"""Offline tests for the isolated Playwright Firefox Expedia access check.

No portal request, no browser install, no network, no Chrome-profile changes.
"""
import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path

try:
    import playwright.async_api
except ModuleNotFoundError:
    package=types.ModuleType("playwright")
    package.__path__=[]
    async_api=types.ModuleType("playwright.async_api")
    async_api.async_playwright=None
    sys.modules.setdefault("playwright",package)
    sys.modules.setdefault("playwright.async_api",async_api)

import velora_portal_sessions as portal_module
from velora_portal_sessions import ManualPortalSessions

ROOT=Path(__file__).resolve().parents[1]


class FakeControl:
    def __init__(self,page,visible):
        self.page=page
        self.visible=visible
        self.first=self
    async def count(self):
        return 1 if self.visible else 0
    async def is_visible(self):
        return self.visible
    def nth(self,index):
        return self
    async def click(self,**kwargs):
        self.page.signin_clicked+=1
        self.page.email_visible=True
    async def inner_text(self,**kwargs):
        return self.page.text

class FakePage:
    def __init__(self,stopped,blocked=False):
        self.url="about:blank"
        self.signin_clicked=0
        self.email_visible=False
        self.text=(
            "Mostraci il tuo lato umano... L'accesso è temporaneamente limitato."
            if blocked else
            "Expedia Acquista viaggi Accedi"
        )
        self.stop=stopped
    async def goto(self,url,**kwargs):
        self.url=url
        self.stop.set() # don't leave a test browser waiting five minutes
    async def wait_for_timeout(self,ms):
        await asyncio.sleep(0)
    def locator(self,selector):
        if selector=="body":
            return FakeControl(self,True)
        return FakeControl(self,self.email_visible and "email" in selector)
    def get_by_role(self,role,name=None):
        return FakeControl(self,role=="button" and not self.email_visible)

class FakeContext:
    def __init__(self,page):
        self.pages=[page]
        self.closed=False
    async def close(self):
        self.closed=True

class FakeFirefox:
    def __init__(self,exe,page,ctx):
        self.executable_path=str(exe)
        self.calls=[]
        self.ctx=ctx
    async def launch_persistent_context(self,**kwargs):
        self.calls.append(kwargs)
        return self.ctx

class PlaywrightContext:
    def __init__(self,firefox):
        self.playwright=types.SimpleNamespace(firefox=firefox)
    async def __aenter__(self):
        return self.playwright
    async def __aexit__(self,*args):
        return None

class FirefoxProbeTests(unittest.TestCase):
    def _run_with_fake_browser(self,blocked=False):
        with tempfile.TemporaryDirectory() as root:
            home=Path(root)
            exe=home/"firefox.exe"
            exe.touch()
            sessions=ManualPortalSessions(home)
            page=FakePage(sessions.firefox_stop,blocked=blocked)
            ctx=FakeContext(page)
            firefox=FakeFirefox(exe,page,ctx)
            old=portal_module.async_playwright
            portal_module.async_playwright=lambda:PlaywrightContext(firefox)
            try:
                asyncio.run(sessions._run_firefox_test())
            finally:
                portal_module.async_playwright=old
            result=sessions.firefox_test_status()
            self.assertEqual(result["state"],"closed")
            self.assertTrue(ctx.closed)
            self.assertEqual(len(firefox.calls),1)
            self.assertFalse(firefox.calls[0]["headless"])
            self.assertIn("firefox-test-profile",firefox.calls[0]["user_data_dir"])
            self.assertNotIn("chrome-profile",firefox.calls[0]["user_data_dir"])
            self.assertEqual(sessions.state["expedia"]["state"],"idle")
            return result,page

    def test_firefox_can_reach_one_key_email_form_without_claiming_login(self):
        result,page=self._run_with_fake_browser()
        self.assertEqual(result["result"],"login_reached")
        self.assertEqual(page.signin_clicked,1)
        self.assertIn("non significa",result["message"].lower())

    def test_anti_bot_restriction_is_recorded_not_bypassed(self):
        result,page=self._run_with_fake_browser(blocked=True)
        self.assertEqual(result["result"],"blocked")
        self.assertEqual(page.signin_clicked,0)

    def test_only_one_firefox_test_and_explicit_close(self):
        with tempfile.TemporaryDirectory() as root:
            sessions=ManualPortalSessions(Path(root))
            started=__import__("threading").Event()
            def fake_worker():
                started.set()
                sessions.firefox_stop.wait(2)
            sessions._firefox_test_worker=fake_worker
            sessions.start_firefox_test()
            self.assertTrue(started.wait(1))
            with self.assertRaisesRegex(RuntimeError,"già aperto"):
                sessions.start_firefox_test()
            sessions.close_firefox_test()
            self.assertTrue(sessions.firefox_stop.is_set())
            sessions.firefox_thread.join(timeout=1)

    def test_sources_keep_separate_browser_and_protected_routes(self):
        sessions=(ROOT/"velora_portal_sessions.py").read_text(encoding="utf-8")
        server=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
        app=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        self.assertIn('"playwright", "install", "firefox"',sessions)
        self.assertIn("sys.executable",sessions)
        self.assertIn("playwright.firefox.launch_persistent_context",sessions)
        self.assertIn("self._access_restricted_reason(page)",sessions)
        self.assertIn("login_reached",sessions)
        self.assertIn('"/api/portal-firefox/start"',server)
        self.assertIn('"/api/portal-firefox/finish"',server)
        self.assertIn('self.headers.get("X-Velora-Local-Token")!=STATE.token',server)
        self.assertIn("Firefox TEST · Expedia",app)
        self.assertIn("manageFirefoxTest",app)
        self.assertNotIn('firefoxTest?.state==="ready"',app)


if __name__=="__main__":
    unittest.main()
