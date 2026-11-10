"""Offline regression: priced direct dates are the commercial master."""
import unittest
from datetime import date,timedelta
from velora_direct_stays import direct_master_candidate,planned_direct_stays,eligible_stays

STAY={"checkin":"2027-06-07","checkout":"2027-06-10","nights":3,"guests":2}
SAMPLE={
    "searchSubmitted":True,"datesConfirmedAfterSearch":True,
    "occupancyControl":{"confirmed":True},
    "quotes":[{"roomType":"Camera Classic","displayedAmount":121.0,
               "bookingActionVisible":True}],
}


class DirectMasterHandoff(unittest.TestCase):
    def test_june_daily_search_has_multiple_stays(self):
        first=date(2027,6,1)
        plan=[]
        for step in range(27):
            arrival=first+timedelta(days=step)
            checkout=arrival+timedelta(days=3)
            plan.append({"checkin":arrival.isoformat(),"checkout":checkout.isoformat(),
                         "nights":3,"adults":2})
        windows=planned_direct_stays(plan,limit=31)
        eligible=eligible_stays(windows,limit=31)
        self.assertEqual(len(eligible),27)
        self.assertEqual(eligible[0]["checkin"],"2027-06-01")
        self.assertEqual(eligible[-1]["checkout"],"2027-06-30")

    def test_first_bookable_price_locks_dates(self):
        lock=direct_master_candidate(STAY,SAMPLE)
        self.assertEqual(lock["checkin"],"2027-06-07")
        self.assertEqual(lock["checkout"],"2027-06-10")
        self.assertEqual(lock["adults"],2)
        self.assertEqual(lock["priceCount"],1)

    def test_confirmed_input_dates_and_guests_accepted(self):
        sample={**SAMPLE,"datesConfirmedAfterSearch":False,
                "controls":{"applied":True},
                "occupancyControl":{"confirmed":False},
                "occupancyAfterSearch":{"confirmed":True}}
        self.assertEqual(direct_master_candidate(STAY,sample)["checkin"],STAY["checkin"])

    def test_no_bookable_room_must_continue(self):
        sample={**SAMPLE,"quotes":[{"roomType":"Camera Classic",
                    "displayedAmount":121.0,"bookingActionVisible":False}]}
        self.assertIsNone(direct_master_candidate(STAY,sample))

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
