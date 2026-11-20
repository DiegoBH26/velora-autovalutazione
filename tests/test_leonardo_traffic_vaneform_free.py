"""Vaneform optional free API contract: no fabricated visits and no leaked key."""
import ast
import unittest
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from velora_site_traffic import collect_site_traffic, _source_domain

ROOT=Path(__file__).resolve().parents[1]


class LeonardoTraffic(unittest.TestCase):
    def test_invalid_or_shared_site(self):
        self.assertEqual(_source_domain("http://127.0.0.1:3000")["status"] if
            "status" in _source_domain("http://127.0.0.1:3000") else
            _source_domain("http://127.0.0.1:3000")["scope"],"invalid_site")
        self.assertEqual(_source_domain("https://example.org/property/bb")["scope"],"domain_not_property")

    def test_missing_key_never_calls_provider(self):
        with patch.dict("os.environ",{},clear=True):
            result=collect_site_traffic("https://myhotel.it",fetch=lambda *args: self.fail("unexpected API call"))
        self.assertEqual(result["status"],"not_configured")
        self.assertIsNone(result["visitsMonthlyEstimate"])

    def test_monthly_traffic_with_source_provenance(self):
        def mocked(url,key):
            self.assertEqual(key,"test-api-key")
            self.assertTrue(url.startswith("https://vaneform.com/api/v1/domains/"))
            return {"status":"ready","scale":{"visits":1760,"estimate":"site",
                    "as_of":"2026-10-31","confidence":"medium",
                    "sources":{"search":0.6,"direct":0.4}}}
        result=collect_site_traffic("https://hotel-example.it/",api_key="test-api-key",fetch=mocked)
        self.assertEqual(result["wholeSiteVisits"],1760)
        self.assertEqual(result["sourcesPct"]["search"],60)
        self.assertEqual(result["month"],"2026-10-31")
        self.assertEqual(result["measurement"],"third_party_estimate")

    def test_uncached_domain_bulk_fallback_and_no_data(self):
        calls=[]
        def mocked(url,key):
            calls.append(url)
            if "/bulk?" in url:
                return {"items":[{"domain":"hotel-example.it",
                    "scale":{"visits":240,"estimate":"site","as_of":"2026-10-31"}}]}
            return {"status":"missing","scale":{"status":"missing"}}
        result=collect_site_traffic("https://hotel-example.it",api_key="test",fetch=mocked)
        self.assertEqual(result["wholeSiteVisits"],240)
        self.assertEqual(len(calls),2)

    def test_search_only_is_not_total_traffic(self):
        result=collect_site_traffic("https://hotel-example.it",api_key="test",
            fetch=lambda *args: {"scale":{"visits":555,"estimate":"search"}})
        self.assertEqual(result["estimateType"],"search")
        self.assertIsNone(result["wholeSiteVisits"])

    def test_shared_domain_never_attributed_to_one_property(self):
        result=collect_site_traffic("https://travelcompany.it/trullo.html",api_key="test",
            fetch=lambda *args: {"scale":{"visits":16000,"estimate":"site"}})
        self.assertEqual(result["scope"],"domain_not_property")
        self.assertIn("NON attribuibile",result["note"])

    def test_free_limit_produces_no_zero(self):
        def limit(url,key):
            raise HTTPError(url,429,"limit",None,None)
        result=collect_site_traffic("https://hotel-example.it",api_key="test",fetch=limit)
        self.assertEqual(result["status"],"limit_reached")
        self.assertIsNone(result["wholeSiteVisits"])

    def test_integration_in_leonardo_and_ui_and_report(self):
        network=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")
        installer=(ROOT/"AGGIORNA_VELORA_COMPLETO.bat").read_text(encoding="utf-8")
        app=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        report=(ROOT/"src/frontend-consulting-report.ts").read_text(encoding="utf-8")
        ast.parse(network)
        self.assertIn("traffic=await asyncio.to_thread(collect_site_traffic,site,cache_dir=output.parent)",network)
        self.assertIn('"siteTraffic": traffic,',network)
        self.assertIn("velora_site_traffic.py.new",installer)
        self.assertIn('move /Y "velora_site_traffic.py.new" "velora_site_traffic.py"',installer)
        self.assertIn('if not exist "velora_site_traffic.py"',installer)
        self.assertIn("except ModuleNotFoundError as exc:",network)
        self.assertIn('if exc.name != "velora_site_traffic":',network)
        self.assertIn('"module_not_installed"',network)
        self.assertIn("siteTraffic:agentId===\"official_site\"",app)
        self.assertIn("Leonardo · Visite mensili stimate",app)
        self.assertIn("Traffico stimato del sito diretto",report)


if __name__=="__main__":
    unittest.main()
