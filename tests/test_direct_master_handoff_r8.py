"""Offline regression: priced direct dates are the commercial master."""
import unittest
from datetime import date
from browser_audit_pilot import custom_date_plan
from velora_direct_stays import direct_master_candidate

STAY={"checkin":"2027-06-07","checkout":"2027-06-10","nights":3,"guests":2}
SAMPLE={
    "searchSubmitted":True,"datesConfirmedAfterSearch":True,
    "occupancyControl":{"confirmed":True},
    "quotes":[{"roomType":"Camera Classic","displayedAmount":121.0,
               "bookingActionVisible":True}],
}


class DirectMasterHandoff(unittest.TestCase):
    def test_june_daily_search_has_multiple_stays(self):
        plan=custom_date_plan(date(2026,11,10),{
            "start":"2027-06-01","end":"2027-06-30",
            "nights":3,"adults":2,"frequency":"daily"})
        self.assertEqual(len(plan),27)
        self.assertEqual(plan[0]["checkin"],"2027-06-01")
        self.assertEqual(plan[-1]["checkout"],"2027-06-30")

    def test_first_bookable_price_locks_dates(self):
        lock=direct_master_candidate(STAY,SAMPLE)
        self.assertEqual(lock["checkin"],"2027-06-07")
        self.assertEqual(lock["checkout"],"2027-06-10")
        self.assertEqual(lock["adults"],2)
        self.assertEqual(lock["priceCount"],1)

    def test_no_price_no_master(self):
        for change in ({"quotes":[]},
                       {"searchSubmitted":False},
                       {"datesConfirmedAfterSearch":False},
                       {"occupancyControl":{"confirmed":False}},
                       {"quotes":[{"roomType":"Camera Classic",
                                   "displayedAmount":121,"bookingActionVisible":False}]}):
            self.assertIsNone(direct_master_candidate(STAY,{**SAMPLE,**change}))


if __name__=="__main__":
    unittest.main()
