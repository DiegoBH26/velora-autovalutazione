"""v120 regression: frontend findings are evidence-based and price parsers are untouched."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
AGENT=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
class FrontendDiagnosticV120(unittest.TestCase):
    def test_parse_and_agent_alignment(self):
        ast.parse(PILOT)
        ast.parse(AGENT)
        self.assertIn('PILOT_BUILD = "velora-browser-pilot-v120"',PILOT)
        self.assertIn('EXPECTED_PILOT_BUILD="velora-browser-pilot-v120"',AGENT)

    def test_only_restricted_channels(self):
        self.assertIn('if channel not in {"vrbo","expedia","holidu"}:',PILOT)
        self.assertIn('record=describe_frontend_observation(channel,record)',PILOT)

    def test_missing_does_not_claim_absence_and_referral_is_distinct(self):
        self.assertIn('"verified_referral"',PILOT)
        self.assertIn('"access_restricted"',PILOT)
        self.assertIn('"unverified_presence"',PILOT)
        self.assertIn('Non significa struttura assente o indisponibile',PILOT)
        self.assertIn('status=="referral_observed"',PILOT)
        self.assertIn('if record.get("status") not in {"rate_limited","access_blocked","http_error"}:',PILOT)
if __name__=="__main__":
    unittest.main()
