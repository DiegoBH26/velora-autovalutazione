"""Static regression for assisted-session diagnostics (no CAPTCHA bypass)."""
import ast
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")

class SessionDiagnosticsV124(unittest.TestCase):
    def test_python_syntax(self):
        ast.parse(PILOT)
        ast.parse(SERVER)
    def test_manual_intervention_stays_explicit(self):
        self.assertIn("HUMAN_HANDOFF_START",PILOT)
        self.assertIn("HUMAN_HANDOFF_END",PILOT)
        self.assertIn("same_context=",PILOT)
        self.assertIn("cookiesShared",PILOT)
        self.assertIn('"velora-browser-pilot-v124"',PILOT)
        self.assertIn('"velora-browser-pilot-v124"',SERVER)

if __name__=="__main__":
    unittest.main()
