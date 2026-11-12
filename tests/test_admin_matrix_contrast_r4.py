"""UI-only R4 contract: admin access safety and accessible OTA evidence matrix."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTH = (ROOT / "src/AuthGate.tsx").read_text(encoding="utf-8")
ADMIN_CSS = (ROOT / "src/admin-console.css").read_text(encoding="utf-8")
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
DARK_CSS = (ROOT / "src/workspace-dark.css").read_text(encoding="utf-8")


class AdminConsoleR4(unittest.TestCase):
    def test_existing_security_and_registration_flow_are_preserved(self):
        for marker in (
            'function AdminPanel({ onClose }',
            'await invokePublicFunction("list-access-requests", {})',
            'await invokePublicFunction("approve-access", { requestId: request.id })',
            'if (!result.code || !result.email || !result.fullName || !result.expiresAt)',
            'await supabase.auth.updateUser({ password })',
            'if (profile.is_admin && showAdmin) return <AdminPanel',
            'request.status === "pending"',
            'request.status === "registered"',
            'request.status === "approved"',
            'navigator.clipboard.writeText(generated.code)',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, AUTH)

    def test_admin_kpis_use_real_request_states_not_fake_data(self):
        self.assertIn('requests.filter((request) => request.status === "pending")', AUTH)
        self.assertIn('requests.filter((request) => request.status !== "pending")', AUTH)
        self.assertIn('history.filter((request) => request.status === "approved").length', AUTH)
        self.assertIn('history.filter((request) => request.status === "registered").length', AUTH)
        self.assertIn('className="velora-admin"', AUTH)
        self.assertIn('import "./admin-console.css"', AUTH)
        self.assertIn("velora-admin__stats", ADMIN_CSS)
        self.assertIn("font-size:.95rem", ADMIN_CSS)
        self.assertIn("prefers-reduced-motion:reduce", ADMIN_CSS)

    def test_asymmetry_matrix_is_compact_accessible_and_keeps_checks(self):
        self.assertIn('className="velora-ota-matrix', APP)
        self.assertIn('className="velora-ota-matrix__item"', APP)
        self.assertIn('className="velora-ota-matrix__summary"', APP)
        for title in ("1 · Presenza scheda", "2 · Fotografie",
                      "3 · Tipologie / Booking", "4 · Tariffe / Booking",
                      "5 · Tariffe / Sito diretto", "6 · Camere / Sito diretto"):
            self.assertIn(title, APP)
        self.assertIn('aria-label={`Verifica presenza', APP)
        self.assertIn('onChange={event=>updateAnswer("audit-ota-"+row.otaId', APP)
        self.assertIn('identityVerified:verified', APP)
        self.assertIn('row.directComparison.matched.length>0', APP)
        self.assertIn('grid-template-columns:repeat(3,minmax(0,1fr))', DARK_CSS)
        self.assertIn('.velora-ota-matrix__cell-detail', DARK_CSS)
        self.assertIn('.velora-ota-matrix__item[data-status="missing"]', DARK_CSS)

    def test_no_ota_scraping_or_saved_archives_modified(self):
        for marker in ('SPECIALIST_AGENTS', 'launchAgentBatch([agent.id])',
                       'function openStructure(', 'function confirmCustomInterview()',
                       'function switchAssessmentMode(', 'localStorage.setItem('):
            self.assertIn(marker, APP)


if __name__ == "__main__":
    unittest.main()
