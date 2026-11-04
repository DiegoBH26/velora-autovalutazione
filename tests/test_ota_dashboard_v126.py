"""Protect the OTA command center, automated Expedia import and content evidence."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
WORKER=(ROOT/"chrome-companion-expedia/background.js").read_text(encoding="utf-8")

class OtaDashboardContracts(unittest.TestCase):
    def test_agents_remain_compact_and_review_moves_outside_cards(self):
        self.assertIn('grid items-stretch gap-3 md:grid-cols-3',APP)
        self.assertIn('grid items-stretch gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',APP)
        self.assertIn('min-h-[232px]',APP)
        self.assertIn('min-h-[110px]',APP)
        self.assertIn('group.id==="access"',APP)
        self.assertIn('Agenti con accesso',APP)
        self.assertIn('Altri agenti',APP)
        self.assertIn('Come funzionano gli accessi Expedia, Vrbo e Holidu',APP)
        self.assertIn("Accessi, credenziali e test avanzati",APP)
        self.assertIn("Expedia · risultati acquisiti",APP)
        self.assertIn("setExpediaReviewOpen(open=>!open)",APP)
        self.assertIn("Vedi prezzi nell'audit OTA",APP)
        self.assertIn('id={`velora-pricing-ota-${otaId}`}',APP)

    def test_single_acquisition_populates_ota_pricing_without_duplicate_form(self):
        self.assertIn("function importCompanionExpediaRates()",APP)
        self.assertIn("importCompanionExpediaRates();",APP)
        self.assertIn("if(!identityConfirmed)return;",APP)
        self.assertIn("if(!captured.checkin||!captured.checkout||captured.guests<1)return;",APP)
        self.assertIn("setRateQuotes(previous=>[...previous,...fresh])",APP)
        self.assertIn('setExpediaReviewOpen(false)',APP)
        self.assertIn('velora-pricing-details',APP)

    def test_audit_comparison_does_not_invent_photo_deltas(self):
        self.assertIn('OtaContentSnapshot',APP)
        self.assertIn('setOtaContentSnapshots(previous=>[',APP)
        self.assertIn('otaContentSnapshots:[]',APP)
        self.assertIn('Asimmetrie di presentazione OTA',APP)
        self.assertIn('Campione di Giove:',APP)
        self.assertIn('non equivale a una differenza tariffaria',APP)
        self.assertIn('images-and-page-text',APP)
        self.assertIn('foto',APP.lower())
        self.assertIn('const imageNodes=',WORKER)
        self.assertIn('photoAltSamples:[...photoAlts]',WORKER)
        self.assertNotIn('chrome.scripting.executeScript({target:{allFrames:true}',WORKER)

if __name__=="__main__":
    unittest.main()
