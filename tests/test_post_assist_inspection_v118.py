"""Static regression checks for post-assistance handling (v118).

Never access OTA websites in tests.
"""
import ast
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "browser_audit_pilot.py"
TEXT = SOURCE.read_text(encoding="utf-8")
TREE = ast.parse(TEXT, filename=str(SOURCE))

class PostAssistInspectionV118(unittest.TestCase):
    def test_pilot_version(self):
        self.assertIn('PILOT_BUILD = "velora-browser-pilot-v118"', TEXT)

    def test_assistance_only_on_problem_portals(self):
        self.assertIn('if channel in {"vrbo","expedia","holidu"} and callable(assist_callback):', TEXT)
        self.assertIn('assist_callback if assisted and channel in {"vrbo","expedia","holidu"} else None', TEXT)

    def test_no_reload_in_post_assist_loop(self):
        start = TEXT.index('                post_assist={}\n')
        end = TEXT.index('                record["navigationSteps"].append({', start)
        segment = TEXT[start:end]
        self.assertIn('for inspection in range(5):', segment)
        self.assertIn('postAssistInspection', segment)
        self.assertNotIn('page.goto(', segment)
        self.assertNotIn('page.reload(', segment)
        self.assertIn('if still.get("blocked"):', segment)
        self.assertIn('if still.get("visible"):', segment)

if __name__ == "__main__":
    unittest.main()
