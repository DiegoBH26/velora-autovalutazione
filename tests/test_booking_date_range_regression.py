"""Booking reference date windows must honor the selected custom calendar."""
import ast
import unittest
from pathlib import Path

PILOT=(Path(__file__).resolve().parents[1]/"browser_audit_pilot.py").read_text(encoding="utf-8")

class BookingCalendarRangeRegression(unittest.TestCase):
    def test_python_parses(self):
        ast.parse(PILOT)

    def test_booking_reference_has_calendar_boundary_and_duplicate_guard(self):
        tree=ast.parse(PILOT)
        node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef)
                  and n.name=="booking_resolve_reference_stay")
        args=[x.arg for x in node.args.args]
        self.assertIn("allowed_checkout",args)
        self.assertIn("used_windows",args)
        function=ast.get_source_segment(PILOT,node)
        self.assertIn('candidate["checkout"]>allowed_checkout',function)
        self.assertIn('(candidate["checkin"],candidate["checkout"]) in (used_windows or set())',function)
        self.assertIn("within_period",function)

    def test_custom_selection_passes_to_booking_search(self):
        self.assertIn('range_checkout=str(custom_settings.get("end") or "") if custom_settings else None',PILOT)
        self.assertIn('allowed_checkout=range_checkout',PILOT)
        self.assertIn('used_windows=booked_windows if not reference_for_specialist else None',PILOT)
        self.assertIn('booked_windows.add((effective_stay["checkin"],effective_stay["checkout"]))',PILOT)

if __name__=="__main__":
    unittest.main()
