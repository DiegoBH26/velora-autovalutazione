"""Guard against accidentally skipping reputation and photo analysis in a full OTA run."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")

class FullCoverageContract(unittest.TestCase):
    def test_ui_requests_full_scan(self):
        self.assertIn("pricingOnly: false", APP)
        self.assertNotIn("pricingOnly: true", APP)
    def test_agent_preserves_independent_audits(self):
        self.assertIn("if pricing_only:", PILOT)
        self.assertIn('reputation=await google_reputation_observation(context,data)', PILOT)
        self.assertIn('result["photoAudit"]', PILOT)
    def test_missing_evidence_explained(self):
        self.assertIn("Analisi recensioni non completata", APP)
        self.assertIn("Audit fotografico non completato", APP)

if __name__=="__main__":
    unittest.main()
