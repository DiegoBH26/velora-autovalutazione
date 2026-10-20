"""v119 static regression: aggregator referrals are not independent rates."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
AGENT=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")

class AggregatorReferralV119(unittest.TestCase):
    def test_syntax_and_version_alignment(self):
        ast.parse(PILOT)
        ast.parse(AGENT)
        self.assertIn('PILOT_BUILD = "velora-browser-pilot-v119"',PILOT)
        self.assertIn('EXPECTED_PILOT_BUILD="velora-browser-pilot-v119"',AGENT)

    def test_holidu_referral_is_not_a_tariff(self):
        self.assertIn('if channel=="holidu":',PILOT)
        self.assertIn('"status":"referral_observed"',PILOT)
        self.assertIn('"referralTo":"booking"',PILOT)
        self.assertIn('"identityVerified":False',PILOT)
        self.assertIn('nessuna tariffa autonoma Holidu',PILOT)
        self.assertIn('candidate_meta.get("status")=="referral_observed"',PILOT)

    def test_no_change_to_assistance_scope(self):
        self.assertIn('if channel in {"vrbo","expedia","holidu"} and callable(assist_callback):',PILOT)

if __name__=="__main__":
    unittest.main()
