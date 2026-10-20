"""Checks for custom calendar planning; no OTA network calls."""
import ast
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
AGENT=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")

tree=ast.parse(PILOT)
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="custom_date_plan")
ns={"date":date,"timedelta":timedelta}
exec(compile(ast.Module(body=[fn],type_ignores=[]),"<custom_date_plan>","exec"),ns)
custom_date_plan=ns["custom_date_plan"]

class CustomCalendarTests(unittest.TestCase):
    def test_august_weekly_3_nights(self):
        p=custom_date_plan(date(2026,10,20),{"start":"2027-08-01","end":"2027-08-31","nights":3,"adults":2,"frequency":"weekly"})
        self.assertEqual([r["checkin"] for r in p],["2027-08-01","2027-08-08","2027-08-15","2027-08-22"])
        self.assertTrue(all(r["checkout"]<="2027-08-31" and r["nights"]==3 and r["adults"]==2 for r in p))

    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            custom_date_plan(date(2026,10,20),{"start":"2027-08-30","end":"2027-08-31","nights":3,"adults":2,"frequency":"weekly"})

    def test_version_and_contract(self):
        ast.parse(AGENT)
        self.assertIn('PILOT_BUILD = "velora-browser-pilot-v122"',PILOT)
        self.assertIn('EXPECTED_PILOT_BUILD="velora-browser-pilot-v122"',AGENT)
        self.assertIn('customPeriod: months === "custom"',APP)
        self.assertIn('custom_period=custom_period',AGENT)
        self.assertIn('custom_date_plan(today,custom_settings)',PILOT)
if __name__=="__main__":
    unittest.main()
