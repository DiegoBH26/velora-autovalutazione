"""Static, no-browser regression checks for supervised OTA sessions."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class PortalSessionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module=(ROOT/"velora_portal_sessions.py").read_text(encoding="utf-8")
        cls.server=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
        cls.app=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        cls.updater=(ROOT/"AGGIORNA_VELORA_COMPLETO.bat").read_text(encoding="utf-8")

    def test_session_uses_separate_persistent_profiles_and_user_login(self):
        tree=ast.parse(self.module)
        self.assertTrue(any(isinstance(x,ast.ClassDef) and x.name=="ManualPortalSessions" for x in tree.body))
        self.assertIn('self.base / portal / "chrome-profile"',self.module)
        self.assertIn("launch_persistent_context",self.module)
        self.assertIn("headless=False",self.module)
        self.assertIn("SESSION_MAX_SECONDS",self.module)
        self.assertNotIn("storage_state(",self.module)
        self.assertNotIn("input(",self.module)

    def test_separate_named_portal_routes_are_protected(self):
        for route in ("/api/portal-session/start","/api/portal-session/finish","/api/portal-session/status"):
            self.assertIn(route,self.server)
        self.assertIn('self.headers.get("X-Velora-Local-Token")!=STATE.token',self.server)
        self.assertIn("PORTAL_SESSIONS.begin(portal_id)",self.server)
        self.assertIn("PORTAL_SESSIONS.finish(portal_id)",self.server)
        self.assertIn("PORTAL_SESSIONS.statuses()",self.server)
        self.assertIn("/api/portal-session/navigate",self.server)
        self.assertIn("PORTAL_SESSIONS.navigate(portal_id",self.server)
        self.assertIn('parsed.scheme!="https"',self.module)
        self.assertIn("self.pending_urls",self.module)

    def test_frontend_has_honest_manual_login_flow(self):
        for token in ("Apri accesso","Chiudi e conserva","▶ Pubblico","loginOpen","portalSessionMessage","openPortalListing"):
            self.assertIn(token,self.app)
        self.assertIn("manuale e locale",self.app)
        self.assertIn("LOGIN_PORTAL_IDS",self.app)
        self.assertIn("startSpecialistAgent(agent.id)",self.app)
        self.assertIn("SCREENSHOT_INTERVIEW_PRESET_IDS",self.app)

    def test_windows_updater_includes_file(self):
        self.assertIn("velora_portal_sessions.py.new",self.updater)
        self.assertIn('move /Y "velora_portal_sessions.py.new"',self.updater)
        self.assertIn("velora_agent_network.py.new",self.updater)

if __name__=="__main__":
    unittest.main()
