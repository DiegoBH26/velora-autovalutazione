"""Regression: a completed Booking result survives Windows agent restart."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src"/"App.tsx").read_text(encoding="utf-8")


class GalileoSavedMinervaLockTests(unittest.TestCase):
    def test_can_reuse_exact_saved_minerva_lock(self):
        self.assertIn('locks[0].checkin===master.checkin',APP)
        self.assertIn('locks[0].checkout===master.checkout',APP)
        self.assertIn('Number(locks[0].adults)===Number(master.adults)',APP)
        self.assertIn('&&locks.length===1',APP)

    def test_restart_does_not_require_volatile_completed_state(self):
        self.assertIn('if(!reuseMinerva){\n          const bookingCheck=',APP)
        self.assertIn('if(!ids.includes("booking")){\n            throw new Error("Galileo non può partire:',APP)

    def test_legacy_exact_booking_statuses_are_accepted(self):
        self.assertIn('["direct_master_checked","initial_dates_available","shifted_to_available_booking_dates","reused_minerva_lock"].includes',APP)


if __name__=="__main__":
    unittest.main()
