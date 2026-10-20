"""Regression: a Booking+Airbnb scan must not verify Vrbo/other OTA listings."""
import ast
import unittest
from pathlib import Path
from datetime import date, timedelta

ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
AGENT=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")

class SelectedOtasOnly(unittest.TestCase):
    def test_parses(self):
        ast.parse(PILOT)
        ast.parse(AGENT)

    def test_master_verification_filtered_before_navigation(self):
        tree=ast.parse(PILOT)
        fn=next(x for x in tree.body if isinstance(x,ast.AsyncFunctionDef) and x.name=="discover_otas_from_master_search")
        segment=ast.get_source_segment(PILOT,fn)
        self.assertIn("if selected_ota_ids is not None and ota_id not in selected_ota_ids:",segment)
        self.assertLess(segment.index("if selected_ota_ids is not None and ota_id not in selected_ota_ids:"),segment.index("verify=await verify_ota_candidate_page("))
        self.assertIn("selected_ota_ids=target_order",PILOT)
        self.assertIn('selected_discovery_ids=[ota_id for ota_id in OTA_DISCOVERY_ORDER if ota_id in channels]',PILOT)

    def test_versions(self):
        self.assertIn('PILOT_BUILD = "velora-browser-pilot-v123"',PILOT)
        self.assertIn('EXPECTED_PILOT_BUILD="velora-browser-pilot-v123"',AGENT)

if __name__=="__main__":
    unittest.main()
