"""No-browser regression checks for unified Velora OTA dashboard."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class UnifiedDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        cls.server=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
        cls.pilot=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
        cls.agents=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")

    def test_one_dashboard_instead_of_duplicate_selectors(self):
        self.assertIn("Scraping, sito diretto e recensioni",self.app)
        self.assertEqual(self.app.count(">Configura test OTA</p>"),0)
        self.assertEqual(self.app.count(">OTA da analizzare</p>"),0)
        self.assertIn("LOCAL_PILOT_OTA_OPTIONS.map((ota)=>",self.app)
        self.assertIn("Avvia analisi selezionata",self.app)
        self.assertIn("Avvia tutti i 12 agenti",self.app)
        self.assertIn("Avvia Giove · Esegui check",self.app)
        self.assertIn("Modalità classica (compatibilità)",self.app)

    def test_ten_channels_and_beta_markers(self):
        for channel in ["booking","agoda","airbnb","vrbo","expedia","holidu",
                        "hotels","travelocity","trip","priceline"]:
            self.assertIn('"'+channel+'": {"name": ',self.agents)
        self.assertIn("agent?.beta",self.app)
        self.assertIn('"agent_id",""',self.pilot)
        self.assertIn("AGENT_WORK_SLOTS=threading.BoundedSemaphore(2)",self.server)

    def test_color_and_period_are_preserved(self):
        for color in ["emerald","sky","rose","blue","yellow","teal",
                      "orange","cyan","violet","indigo"]:
            self.assertIn("border-"+color+"-500",self.app)
        self.assertIn('localPilotPeriod === "custom"',self.app)
        self.assertIn("customPilotNights",self.app)
        self.assertIn("customPilotAdults",self.app)
        self.assertIn("customPilotFrequency",self.app)

if __name__=="__main__":
    unittest.main()
