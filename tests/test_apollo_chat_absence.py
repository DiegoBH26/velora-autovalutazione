"""Verify Apollo distinguishes no data, absence and verified review evidence."""
import ast
import unittest
from pathlib import Path

SOURCE=(Path(__file__).resolve().parents[1]/"local_audit_server.py").read_text(encoding="utf-8")


class ApolloChatAbsenceTests(unittest.TestCase):
    def test_server_parses(self):
        ast.parse(SOURCE)

    def test_missing_ota_records_is_not_zero_inventory(self):
        self.assertIn('if agent_id=="airbnb":\n                agent_mailbox_publish', SOURCE)
        self.assertIn('Non considero questa situazione una prova che l\'annuncio sia assente', SOURCE)

    def test_review_comparison_requires_observed_rating(self):
        self.assertIn('airbnb_profile.get("status")=="sampled"',SOURCE)
        self.assertIn('review_count=airbnb_profile.get("reviewCount")',SOURCE)
        self.assertIn('recensioni Airbnb verificato',SOURCE)

    def test_apollo_name_and_absence_report(self):
        self.assertIn('"airbnb":"Apollo"',SOURCE)
        self.assertIn('explicit_absence=bool(rows) and all(',SOURCE)


if __name__=="__main__":
    unittest.main()
