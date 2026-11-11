"""Booking reputation regression: no live OTA traffic, no price synthesis."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")

def merge_function():
    node=next(node for node in ast.parse(PILOT).body
              if isinstance(node,ast.FunctionDef) and node.name=="merge_observed_rating_profile")
    scope={"_plausible_ota_listing_url":lambda channel,url:
           channel=="booking" and url.startswith("https://www.booking.com/hotel/")}
    exec(compile(ast.Module(body=[node],type_ignores=[]),"browser_audit_pilot.py","exec"),scope)
    return scope["merge_observed_rating_profile"]

class BookingRatingTests(unittest.TestCase):
    def setUp(self):
        self.merge=merge_function()
        self.result={"discoveredSources":{"booking":{"status":"found","identityVerified":True}},
                     "otaProfiles":{}}
        self.record={"otaId":"booking","status":"quote_candidates",
                     "sourceIdentityVerified":True,
                     "finalUrl":"https://www.booking.com/hotel/it/masseria-tenuta-specolizzi.it.html",
                     "frontendSnapshot":{"ratingCandidate":{
                         "rating":9.1,"ratingScale":10,"reviewCount":183,
                         "evidence":"Rating sulla stessa scheda"}}}

    def test_rating_independent_of_price_rows(self):
        self.record["quotes"]=[]
        self.merge(self.result,self.record)
        self.assertEqual(self.result["otaProfiles"]["booking"]["rating"],9.1)
        self.assertEqual(self.result["otaProfiles"]["booking"]["ratingScale"],10)
        self.assertEqual(self.result["otaProfiles"]["booking"]["reviewCount"],183)
        self.assertEqual(self.result["otaProfiles"]["booking"]["status"],"sampled")

    def test_unverified_identity_rejected(self):
        for key,value in [("sourceIdentityVerified",False),("identityQuarantined",True),
                          ("identityUnverified",True),("identityCheck",{"verified":False})]:
            with self.subTest(key=key):
                record={**self.record,key:value}
                result={"discoveredSources":self.result["discoveredSources"],"otaProfiles":{}}
                self.merge(result,record)
                self.assertFalse(result["otaProfiles"])

    def test_nonexistent_or_invalid_score_not_used(self):
        for score in [0,-1,10.5,float("nan")]:
            with self.subTest(score=score):
                record={**self.record,"frontendSnapshot":{"ratingCandidate":{
                    "rating":score,"ratingScale":10}}}
                result={"discoveredSources":self.result["discoveredSources"],"otaProfiles":{}}
                self.merge(result,record)
                self.assertFalse(result["otaProfiles"])

    def test_disabled_ota_does_not_register_rating(self):
        self.record["status"]="login_required"
        self.merge(self.result,self.record)
        self.assertEqual(self.result["otaProfiles"],{})

    def test_panel_and_capture_link_present(self):
        self.assertIn('booking_rating=await page.evaluate',PILOT)
        self.assertIn('merge_observed_rating_profile(result,record)',PILOT)
        self.assertIn('otaProfiles: { ...(previous.otaProfiles || {}), ...(next.otaProfiles || {}) }',APP)
        self.assertIn('booking:"Booking.com"',APP)
        self.assertIn('Recensioni online e qualità fotografica',APP)

if __name__=="__main__":
    unittest.main()
