"""Security and behavior contract for local Windows OTA credentials."""
import ast
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LocalAccountCredentialContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vault = (ROOT / "velora_portal_credentials.py").read_text(encoding="utf-8")
        cls.sessions = (ROOT / "velora_portal_sessions.py").read_text(encoding="utf-8")
        cls.server = (ROOT / "local_audit_server.py").read_text(encoding="utf-8")
        cls.frontend = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
        cls.updater = (ROOT / "AGGIORNA_VELORA_COMPLETO.bat").read_text(encoding="utf-8")

    def test_local_windows_vault_has_no_source_secrets(self):
        import velora_portal_credentials as vault
        self.assertEqual(vault.WindowsPortalVault.target("expedia"), "Velora/OTA/expedia")
        self.assertEqual(vault.WindowsPortalVault.target("vrbo"), "Velora/OTA/vrbo")
        with self.assertRaises(ValueError):
            vault.WindowsPortalVault.target("../other")
        if os.name != "nt":
            with self.assertRaises(RuntimeError):
                vault.WindowsPortalVault()
        self.assertIn("CredWriteW", self.vault)
        self.assertIn("CredReadW", self.vault)
        self.assertIn("CredDeleteW", self.vault)
        self.assertNotIn("json.dump(", self.vault)
        self.assertNotIn("subprocess", self.vault)

    def test_only_boolean_credential_status_is_exposed(self):
        ast.parse(self.sessions)
        self.assertIn('state["credentialSaved"]=self.has_credentials(portal)', self.sessions)
        self.assertIn("self.vault.save(portal, email, password)", self.sessions)
        self.assertIn("self.vault.remove(portal)", self.sessions)
        self.assertIn('{"credentialSaved": True, "profileSaved":', self.sessions)
        self.assertIn('{"credentialSaved": False, "profileSaved":', self.sessions)
        self.assertIn("chromium_sandbox=True", self.sessions)
        self.assertIn("def _ensure_login_host", self.sessions)
        self.assertIn("self._ensure_login_host(portal, page.url)", self.sessions)

    def test_login_does_not_bypass_otp_captcha_or_claim_email_login(self):
        self.assertIn("async def prepare_account_session", self.sessions)
        self.assertIn("codice email", self.sessions)
        self.assertIn("CAPTCHA", self.sessions)
        self.assertIn("VERIFICA UMANA", self.sessions)
        self.assertIn("il portale non ha presentato una password", self.sessions)
        self.assertIn("LOGIN NON CONFERMATO", self.sessions)
        self.assertIn("raise RuntimeError", self.sessions)

    def test_authenticated_local_api_routes_and_no_report_credentials(self):
        self.assertIn('"/api/portal-account/save"', self.server)
        self.assertIn('"/api/portal-account/remove"', self.server)
        self.assertIn('self.headers.get("X-Velora-Local-Token")!=STATE.token', self.server)
        self.assertIn("not self._allowed_origin()", self.server)
        self.assertIn("PORTAL_SESSIONS.prepare_account_session(agent_id)", self.server)
        self.assertIn("PORTAL_SESSIONS.has_credentials(agent_id)", self.server)
        self.assertNotIn('"password":', self.server)

    def test_browser_form_does_not_persist_passwords_online(self):
        self.assertIn("Configura credenziali", self.frontend)
        self.assertIn("Salva accesso sul PC", self.frontend)
        self.assertIn("Elimina accesso", self.frontend)
        self.assertIn('autoComplete="new-password"', self.frontend)
        self.assertIn('"/api/portal-account/"+action', self.frontend)
        self.assertIn('setPortalCredentialDrafts(old=>({...old,[portalId]:{email:"",password:""}}))', self.frontend)
        self.assertNotIn('localStorage.setItem("velora-credentials', self.frontend)
        self.assertIn("velora_portal_credentials.py.new", self.updater)


if __name__ == "__main__":
    unittest.main()
