"""v121 static regression for human verification on supplemental OTAs.

No web requests, CAPTCHA automation or login actions.
"""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
AGENT=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
EXTRA='{"vrbo","expedia","holidu","travelocity","trip","priceline"}'

class HumanAssistV121(unittest.TestCase):
    def test_code_parses_and_versions_match(self):
        ast.parse(PILOT)
        ast.parse(AGENT)
        self.assertIn('PILOT_BUILD = "velora-browser-pilot-v121"',PILOT)
        self.assertIn('EXPECTED_PILOT_BUILD="velora-browser-pilot-v121"',AGENT)

    def test_callback_scope_and_wait(self):
        self.assertIn('if channel in '+EXTRA+' and callable(assist_callback):',PILOT)
        self.assertIn('assist_callback if assisted and channel in '+EXTRA+' else None',PILOT)
        self.assertIn('timeout=1000 if assisted and channel in '+EXTRA,PILOT)
        self.assertIn('action=await _human_assist(page,assist_callback',PILOT)

    def test_others_not_forced_to_pause_without_challenge(self):
        self.assertIn('forced_portal_checkpoint=channel in {"vrbo","expedia"}',PILOT)
        self.assertIn('or (limited_status and channel in {"vrbo","expedia","holidu"})',PILOT)
        self.assertIn('"login_required"',PILOT)
if __name__=="__main__":
    unittest.main()
