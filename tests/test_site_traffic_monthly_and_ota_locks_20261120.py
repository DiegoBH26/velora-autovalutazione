"""Vaneform monthly and OTA first-window date-lock regression checks."""
import ast
from pathlib import Path
import tempfile
import unittest

from velora_site_traffic import collect_site_traffic

ROOT=Path(__file__).resolve().parents[1]


class TrafficMonthlyAndLocks(unittest.TestCase):
    def test_monthly_history_annual_complete_and_sources(self):
        payload={"status":"ready","scale":{
            "estimate":"site","visits":554,"as_of":"2026-10-01",
            "visits_mom_change_pct":14.94,"confidence":"medium",
            "monthly_visits":[
                {"month":f"2026-{m:02d}","visits":100+m} for m in range(1,11)
            ],
            "sources":{"search":.411,"direct":.229,"gen_ai":.014},
            "time_on_site_seconds":114,"pages_per_visit":3.68,"bounce_rate":.3114,
        }}
        result=collect_site_traffic("https://masseriamancini.it",api_key="test",
            fetch=lambda *args:payload)
        self.assertEqual(result["wholeSiteVisits"],554)
        self.assertEqual(result["sourcesPct"]["search"],41.1)
        self.assertEqual(result["sourcesPct"]["gen_ai"],1.4)
        self.assertEqual(len(result["monthlyVisits"]),10)
        self.assertEqual(result["monthlyVisits"][-1],{"month":"2026-10","visits":110})
        self.assertEqual(result["annualSummaries"][0]["monthsAvailable"],10)
        self.assertFalse(result["annualSummaries"][0]["completeYear"])
        self.assertEqual(result["annualSummaries"][0]["sumAvailableMonths"],sum(100+m for m in range(1,11)))
        self.assertEqual(result["bounceRatePct"],31.14)
        self.assertEqual(result["pagesPerVisit"],3.68)
        self.assertEqual(result["timeOnSiteSeconds"],114)

    def test_missing_months_never_filled_with_zero(self):
        payload={"scale":{
            "estimate":"site","visits":554,"as_of":"2026-10-01",
            "monthly_visits":[
                {"month":"2026-08","visits":600},
                {"month":"2026-09","visits":482},
                {"month":"2026-10","visits":554},
            ],
        }}
        data=collect_site_traffic("https://masseriamancini.it",api_key="test",
            fetch=lambda *args:payload)
        self.assertEqual(len(data["monthlyVisits"]),3)
        self.assertFalse(data["annualSummaries"][0]["completeYear"])
        self.assertEqual(data["annualSummaries"][0]["sumAvailableMonths"],1636)
        self.assertIn("2026-01",data["annualSummaries"][0]["monthsMissing"])
        self.assertNotIn("2026-10",data["annualSummaries"][0]["monthsMissing"])

    def test_complete_12_months_is_annual_total(self):
        payload={"scale":{
            "estimate":"site","visits":120,"as_of":"2026-12-01",
            "monthly_visits":[
                {"month":f"2026-{m:02d}","visits":120} for m in range(1,13)
            ],
        }}
        value=collect_site_traffic("https://masseriamancini.it",api_key="test",
            fetch=lambda *args:payload)
        self.assertTrue(value["annualSummaries"][0]["completeYear"])
        self.assertEqual(value["annualSummaries"][0]["sumAvailableMonths"],1440)

    def test_cache_upgrades_from_legacy_to_richer_monthly_history(self):
        payload={"scale":{"estimate":"site","visits":554,"as_of":"2026-10-01",
                          "monthly_visits":[{"month":"2026-10","visits":554}]}}
        calls=[]
        def fetch(*args):
            calls.append(1)
            return payload
        with tempfile.TemporaryDirectory() as folder:
            previous=collect_site_traffic("https://masseriamancini.it",
                api_key="test",fetch=fetch,cache_dir=folder)
            cached=collect_site_traffic("https://masseriamancini.it",
                api_key="test",fetch=fetch,cache_dir=folder)
            self.assertEqual(len(calls),1)
            self.assertEqual(previous["schemaVersion"],3)
            self.assertTrue(cached["cached"])

    def test_frontend_and_pdf_render_months_sources_and_partial_annual(self):
        ui=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        pdf=(ROOT/"src/frontend-consulting-report.ts").read_text(encoding="utf-8")
        self.assertIn("function SiteTrafficDetails",ui)
        self.assertIn("annualSummaries",ui)
        self.assertIn("SITE_TRAFFIC_LABELS",ui)
        self.assertIn("trafficMonthlyHtml",pdf)
        self.assertIn("trafficSourcesHtml",pdf)
        self.assertIn("annualTrafficHtml",pdf)
        self.assertIn("NON è un totale annuale completo",pdf)

    def test_lock_recalculated_after_booking_first_stay_selected(self):
        server=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
        pilot=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
        ast.parse(server)
        ast.parse(pilot)
        scope=server.split('locks=booking_result.get("bookingReferenceStays") or []',1)[1].split('expected_keys=[',1)[0]
        self.assertLess(scope.index("if (not direct_master and custom_period"),scope.index("expected_plan=("))
        self.assertIn('"dates_confirmed_prices_unverified"',server)
        self.assertIn('"dates_confirmed_prices_unverified" if lock_confirmed and has_price',pilot)
        self.assertIn('result["bookingPriceValidationStatus"]=',pilot)
        self.assertIn('selected_lock["status"]="booking_price_needs_validation"',pilot)

if __name__=="__main__":
    unittest.main()
