"""Protect first-price handoff: daily dates are candidates, not a rate sweep."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
FRONT=(ROOT/"src/App.tsx").read_text(encoding="utf-8")


class FirstWindowHandoff(unittest.TestCase):
    def test_code_is_valid_python(self):
        ast.parse(PILOT)
        ast.parse(SERVER)

    def test_leonardo_keeps_first_real_price_as_master(self):
        direct=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
        self.assertIn('direct_master=direct_master_candidate(stay,sample)',direct)
        self.assertIn('result["masterStay"]=direct_master',direct)
        self.assertIn('result["status"]="first_price_needs_validation"',direct)

    def test_minerva_stops_on_first_price_instead_of_all_daily_dates(self):
        self.assertIn('if specialist_id=="booking" and direct_master.get("status")!="direct_price_observed":',PILOT)
        self.assertIn('"confirmed" if lock_confirmed and verified_price',PILOT)
        self.assertIn('"needs_validation" if has_price',PILOT)
        self.assertIn('result["bookingFallbackStatus"]=fallback_outcome',PILOT)
        self.assertIn('result["bookingSamplingHistory"]',PILOT)
        fragment=PILOT.split('if specialist_id=="booking" and direct_master.get("status")!="direct_price_observed":',1)[1].split('apply_booking_room_reference(result)',1)[0]
        self.assertIn('result["bookingReferenceStays"]=[selected_lock]',fragment)
        self.assertIn('result["plan"]=[{',fragment)
        self.assertIn('write_result(output,result)',fragment)
        self.assertIn('break',fragment)

    def test_only_confirmed_booking_window_reaches_other_otas(self):
        self.assertIn('"confirmed","dates_confirmed_prices_unverified"',SERVER)
        self.assertIn('"dates_confirmed_prices_unverified" if lock_confirmed and has_price',PILOT)
        self.assertIn('result["bookingPriceValidationStatus"]=',PILOT)
        fragment=SERVER.split('locks=booking_result.get("bookingReferenceStays") or []',1)[1].split('expected_keys=[',1)[0]
        self.assertLess(fragment.index('if (not direct_master and custom_period'),fragment.index('expected_plan=('),
                        "Expected plan must use Minerva narrowed dates")
        self.assertIn('requested_candidates=browser_pilot.custom_date_plan(',SERVER)
        self.assertIn('and (str(row.get("requestedCheckin"))',SERVER)
        self.assertIn('and str(candidate["checkout"])<=str(custom_period["end"])',SERVER)
        self.assertIn('data["_specialistBookingLocks"]=[dict(by_key[key]) for key in expected_keys]',SERVER)
        self.assertIn('if not expected_keys or any(key not in by_key for key in expected_keys)',SERVER)

    def test_ui_explains_candidate_dates(self):
        self.assertIn('Le date del campionamento sono tentativi',FRONT)


if __name__=="__main__":
    unittest.main()
