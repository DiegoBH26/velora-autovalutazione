"""Presence discovery is an evidence status, never a definitive absence claim."""
import ast
import unittest
from pathlib import Path

SRC=Path(__file__).resolve().parents[1]/"velora_agent_network.py"
SERVER=(Path(__file__).resolve().parents[1]/"local_audit_server.py").read_text(encoding="utf-8")
APP=(Path(__file__).resolve().parents[1]/"src/App.tsx").read_text(encoding="utf-8")
tree=ast.parse(SRC.read_text(encoding="utf-8"))
fn=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="classify_vrbo_presence")
scope={"_now":lambda:"2026-11-04T13:00:00+00:00"}
exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SRC),"exec"),scope)
classify=scope["classify_vrbo_presence"]

class VrboPresenceTest(unittest.TestCase):
    def test_candidate_listings_are_unverified(self):
        result=classify({
            "status":"found_candidates",
            "listingUrls":["https://www.vrbo.com/it-it/pdp/lo/42693330",
                           "https://www.vrbo.com/it-it/search?destination=Salve"],
            "evidence":"Vrbo: 1 scheda; Google: 8 risultati; Bing: 2 risultati; Brave: 0 risultati"
        },"tenuta-specolizzi","Tenuta Specolizzi")
        self.assertEqual(result["status"],"candidates_found")
        self.assertEqual(result["candidateUrls"],["https://www.vrbo.com/it-it/pdp/lo/42693330"])
        self.assertFalse(result["identityVerified"])
        self.assertFalse(result["absenceConfirmed"])
        self.assertFalse(result["pricingChecked"])

    def test_two_searches_without_listing_are_not_confirmed_absence(self):
        result=classify({"status":"not_found","listingUrls":[],
            "evidence":"Vrbo: 0 schede; Google: 4 risultati; Bing: 0 risultati; Brave: timeout"},
            "tenuta-specolizzi","Tenuta Specolizzi")
        self.assertEqual(result["status"],"not_identified")
        self.assertIn("non confermata",result["explanation"])
        self.assertFalse(result["absenceConfirmed"])

    def test_blocked_queries_are_inconclusive(self):
        result=classify({"status":"not_found","listingUrls":[],
            "evidence":"Google: TimeoutError; Bing: TimeoutError; Brave: TimeoutError"},
            "tenuta-specolizzi","Tenuta Specolizzi")
        self.assertEqual(result["status"],"inconclusive")
        self.assertFalse(result["absenceConfirmed"])

    def test_one_dashboard_and_isolated_ota_paths(self):
        self.assertIn("/api/vrbo-presence/start",SERVER)
        self.assertIn("/api/vrbo-presence/status",SERVER)
        self.assertIn("run_vrbo_presence_job",SERVER)
        self.assertIn("Apri Expedia + Vrbo + Holidu",APP)
        self.assertIn("function openThreeOtaPortals()",APP)
        self.assertIn('type:"OPEN_THREE_OTA_TABS"',APP)
        self.assertIn('setOtaTabLauncherSupported',APP)
        self.assertIn("function captureHoliduFromChrome()",APP)
        self.assertIn("function captureVrboFromChrome()",APP)
        self.assertIn("function captureExpediaFromChrome()",APP)
        self.assertIn('type:"CAPTURE_HOLIDU"',APP)
        workspace=APP.split('{otaWorkspaceOpen && <aside',1)[1].split('{vrboPresence.state!=="not_started"',1)[0]
        for importer in ("importCompanionExpediaRates", "importVrboCompanionRates", "importHoliduCompanionRates"):
            self.assertIn("onClick={"+importer+"}",workspace)
        self.assertIn('void startVrboPresenceCheck()',APP)
        self.assertIn("Chrome Companion 0.4",APP)
        self.assertNotIn("Chrome Companion 0.3",APP)

if __name__=="__main__":unittest.main()
