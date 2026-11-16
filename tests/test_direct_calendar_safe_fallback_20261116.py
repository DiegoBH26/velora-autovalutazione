"""Regression: a failed direct-site calendar must not suppress Booking/reviews.

No dates or prices are invented: only a confirmed direct master locks a
comparison. Booking must discover and confirm its own dates otherwise.
"""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
DIRECT=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")


class LeonardoFallbackFlowTest(unittest.TestCase):
    def test_direct_engine_parses(self):
        ast.parse(DIRECT)

    def test_exact_calendar_days_before_visual_month_fallback(self):
        self.assertIn("already_open=False",DIRECT)
        self.assertIn("if not already_open:",DIRECT)
        self.assertIn("explicit-iso-calendar",DIRECT)
        self.assertIn("_select_explicit_calendar_date(\n                    scope,scope.locator(\"body\"),requested,already_open=True)",DIRECT)
        self.assertIn("_select_visual_calendar_date(scope,requested,path)",DIRECT)

    def test_no_silent_direct_master_invention(self):
        self.assertIn("if direct_master.get(\"status\")==\"direct_price_observed\"", (ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8"))
        self.assertIn("siteReport.directCommercialAudit?.masterStay?.checkin",APP)
        self.assertIn("il sito diretto rimane non verificato e non produce delta",APP)
        self.assertNotIn(". Rete fermata prima di Booking.", APP)

    def test_booking_continues_and_reviews_are_independent(self):
        flow=APP.split("async function launchAgentBatch(",1)[1].split("async function loadAgentChat(",1)[0]
        self.assertIn('await startSpecialistAgent("booking",false,"public"',flow)
        self.assertIn('if(ids.includes("reviews"))',flow)
        self.assertIn('await startSpecialistAgent("reviews",false,"public"',flow)
        self.assertIn('id!=="official_site" && id!=="reviews"',flow)
        self.assertNotIn("Galileo non può partire: manca un risultato Minerva",flow)
        self.assertIn("Booking non ha confermato tutte le finestre",flow)


if __name__=="__main__":
    unittest.main()
