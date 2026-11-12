"""Velora specialist manual-fallback and challenge classification regression."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")

class ManualOtaFallbackContract(unittest.TestCase):
    def test_a_robot_title_does_not_prove_wrong_property(self):
        self.assertIn("function pilotListingIdentityWarning(",APP)
        self.assertIn("technicalStatuses.has(observation.status)",APP)
        self.assertIn("sei un robot",APP)
        self.assertIn('function pilotWrongListingReason(',APP)
        self.assertIn('if(/^(sei un robot',APP)
        self.assertIn('if(expectedWords.some(word=>candidateWords.includes(word))) return "";',APP)

    def test_blocking_prioritized_over_unverified_candidate_in_matrix(self):
        self.assertIn(': anyBlocked ? "blocked"',APP)
        self.assertIn('presence==="blocked"?"Accesso limitato o login richiesto',APP)

    def test_four_manual_non_detection_controls_are_saved_not_confirmed_absence(self):
        self.assertIn('type ManualOtaId="expedia"|"vrbo"|"holidu"|"trip"|"priceline"|"hotels"|"travelocity"',APP)
        self.assertIn('manualOtaPresenceButton(agent.id as "trip"|"priceline"|"hotels"|"travelocity")',APP)
        for ota in ("trip","priceline","hotels","travelocity"):
            self.assertIn(f'"{ota}":(',SERVER)
        self.assertIn('"absenceConfirmed":False',SERVER)
        self.assertIn('read_manual_ota_presence',SERVER)

    def test_manual_price_recovery_is_disconnected_from_auto_validation(self):
        self.assertIn('navigateVelora("tariffe");',APP)
        self.assertIn('showAssistedRateForm();',APP)
        self.assertIn('["vrbo","expedia","holidu","trip","hotels","travelocity","priceline"]',APP)
        self.assertIn('status="login_required"',PILOT)
        self.assertIn('&& !/\\/(?:account|login|signin|sign-in|captcha|challenge)',APP)
        self.assertIn('origin: "manual"',APP)

if __name__=="__main__":
    unittest.main()
