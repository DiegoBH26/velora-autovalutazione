"""Manual OTA presence: button, persistence, review and chat contracts."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")


class ManualOtaPresenceTests(unittest.TestCase):
    def test_server_parses_and_only_three_access_otas_are_valid(self):
        ast.parse(SERVER)
        self.assertIn('MANUAL_OTA_AGENT_NAMES={',SERVER)
        for ota in ("expedia","vrbo","holidu"):
            self.assertIn('"'+ota+'":(',SERVER)
        self.assertIn('if ota_id not in MANUAL_OTA_AGENT_NAMES:',SERVER)
        self.assertIn('if action not in {"not_found","clear"}:',SERVER)

    def test_server_persists_under_property_and_reports_operator_not_confirmed_absence(self):
        self.assertIn('manual-ota-presence.json',SERVER)
        self.assertIn('"status":"not_found_by_operator"',SERVER)
        self.assertIn('"absenceConfirmed":False',SERVER)
        self.assertIn('"source":"operator_manual_search"',SERVER)
        self.assertIn('agent_mailbox_publish(property_id,ota_id,"manual_presence"',SERVER)
        self.assertIn('temporary.replace(path)',SERVER)
        self.assertIn('"/api/ota-presence/manual"',SERVER)

    def test_ui_has_buttons_and_reversible_handling_for_all_three(self):
        for ota in ("expedia","vrbo","holidu"):
            self.assertIn('manualOtaPresenceButton("'+ota+'")',APP)
        self.assertIn('manualOtaPresenceButton(loginPortal)',APP)
        self.assertIn('action:"not_found"|"clear"',APP)
        self.assertIn('status:"not_found_by_operator"',APP)
        self.assertIn('window.confirm(',APP)
        self.assertIn('X-Velora-Local-Token',APP)

    def test_missing_listing_affects_presence_only(self):
        self.assertIn('const operatorNotFound=manual?.manualPresence?.status==="not_found_by_operator";',APP)
        self.assertIn('const explicitlyNotFound=operatorNotFound ||',APP)
        self.assertIn('const noComparableListing=presence==="missing"',APP)
        self.assertIn('const displayPriceState=noComparableListing?"unverified"',APP)
        self.assertIn('manual_presence:"Segnalazione manuale della presenza OTA"',APP)

if __name__=="__main__":
    unittest.main()
