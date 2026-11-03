"""Regression contracts for the user-triggered normal-Chrome Expedia reader."""
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
EXT=ROOT/"chrome-companion-expedia"
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
BRIDGE=(EXT/"bridge.js").read_text(encoding="utf-8")
WORKER=(EXT/"background.js").read_text(encoding="utf-8")
DEPLOY=(ROOT/".github/workflows/deploy-pages.yml").read_text(encoding="utf-8")

class ExpediaChromeCompanion(unittest.TestCase):
    def test_extension_is_scoped_to_expedia_and_velora_only(self):
        manifest=json.loads((EXT/"manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"],3)
        self.assertNotIn("<all_urls>",str(manifest))
        self.assertNotIn("webRequest",str(manifest))
        self.assertNotIn("cookies",str(manifest["permissions"]))
        self.assertIn("https://diegobh26.github.io/velora-autovalutazione/*",manifest["content_scripts"][0]["matches"])
        self.assertIn("https://*.expedia.it/*",manifest["host_permissions"])
        self.assertIn('location.origin === ORIGIN',BRIDGE)
        self.assertIn('event.origin !== ORIGIN',BRIDGE)
        self.assertIn('CAPTURE_VISIBLE_EXPEDIA',BRIDGE)
        self.assertIn('COMPANION_PING',BRIDGE)

    def test_no_automated_login_or_captcha_bypass(self):
        self.assertIn("chrome.scripting.executeScript",WORKER)
        self.assertIn("visibleExpediaCapture",WORKER)
        self.assertIn("accesso è temporaneamente limitato",WORKER)
        self.assertNotIn("page.goto(",WORKER)
        self.assertNotIn("puppeteer",WORKER.lower())
        self.assertNotIn("proxy:",WORKER.lower())
        self.assertNotIn("password",WORKER.lower())
        self.assertNotIn("otp",WORKER.lower())

    def test_capture_only_visible_room_totals_with_identity_date_safety(self):
        self.assertIn('getClientRects()',WORKER)
        self.assertIn("per\\s+\\d{1,2}\\s+nott",WORKER)
        self.assertIn('confidence:"total-for-stay"',WORKER)
        self.assertIn('const seen=new Set();',WORKER)
        self.assertIn('const roomAction=',WORKER)
        self.assertIn('prenota(?: ora)?',WORKER)
        self.assertIn('pulsanti camera riconosciuti',WORKER)
        self.assertIn('Nessuna camera importabile:',APP)
        self.assertIn('sourceUrl:sanitized.toString()',WORKER)
        self.assertIn('schema:"velora-expedia-visible-v1"',WORKER)
        self.assertIn('const genericHeading=',WORKER)

    def test_bulk_import_not_manual_per_room_form(self):
        self.assertIn('function captureExpediaFromChrome()',APP)
        self.assertIn('function importCompanionExpediaRates()',APP)
        self.assertIn('Acquisisci camere da Chrome',APP)
        self.assertIn('Importa tutte le ',APP)
        self.assertIn('matchingExpediaProperty(',APP)
        self.assertIn('nearbyBookingRoom(',APP)
        self.assertIn('origin:"browser-assisted"',APP)
        self.assertIn('roomMatchStatus:"da verificare"',APP)
        self.assertIn('delta non validato',APP)
        self.assertIn('captured.propertyId!==activeAuditData.id',APP)
        self.assertIn('setRateQuotes(previous=>[...previous,...fresh])',APP)
        self.assertIn("noopener noreferrer",APP)

    def test_distribution_zip_is_built_by_pages_workflow(self):
        self.assertIn("node --check chrome-companion-expedia/background.js",DEPLOY)
        self.assertIn("node --check chrome-companion-expedia/bridge.js",DEPLOY)
        self.assertIn('velora-expedia-companion.zip',DEPLOY)
        self.assertIn('velora-expedia-companion.zip',APP)
        self.assertTrue((EXT/"LEGGIMI.txt").exists())

if __name__=="__main__":
    unittest.main()
