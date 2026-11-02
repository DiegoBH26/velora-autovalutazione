"""Offline tests for the specialist isolation and Giove identity contracts."""
import ast
import json
import tempfile
import unittest
from pathlib import Path

SOURCE=(Path(__file__).resolve().parents[1]/"velora_agent_network.py").read_text(encoding="utf-8")
TREE=ast.parse(SOURCE)
ns={"Path":Path,"json":json, "_now":lambda:"test-time",
    "REVIEWER_NAME":"Giove",
    "agent_display":lambda name:name,
    "validation_rows":lambda report:report["checks"],
    "AGENTS":{"expedia":{"kind":"ota"},"booking":{"kind":"ota"},
              "agoda":{"kind":"ota"},"airbnb":{"kind":"ota"}}}
for name in ("_listing_key","enforce_known_listing_identity",
             "enforce_portal_scope","quarantine_identity_mismatches","evaluate"):
    fn=next(node for node in TREE.body
            if isinstance(node,ast.FunctionDef) and node.name==name)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"specialist-contract","exec"),ns)

class AgentIdentityContracts(unittest.TestCase):
    def test_airbnb_wrong_listing_is_quarantined(self):
        data={"sources":{"airbnb":{"identityVerified":True,
              "url":"https://www.airbnb.com/rooms/1234567"}}}
        record={"observations":[{"otaId":"airbnb",
                "finalUrl":"https://www.airbnb.com/rooms/7654321",
                "quotes":[{"verified":True}]}]}
        ns["enforce_known_listing_identity"](record,"airbnb",data)
        self.assertTrue(record["observations"][0]["identityQuarantined"])
        self.assertFalse(record["observations"][0]["quotes"][0]["verified"])

    def test_multiple_airbnb_units_allowed_when_prevalidated(self):
        data={"sources":{"airbnb":{"identityVerified":True,
              "url":"https://www.airbnb.com/rooms/1234567",
              "listingUrls":["https://www.airbnb.com/rooms/7654321"]}}}
        record={"observations":[{"otaId":"airbnb",
                "finalUrl":"https://www.airbnb.com/rooms/7654321",
                "quotes":[{"verified":True}]}]}
        ns["enforce_known_listing_identity"](record,"airbnb",data)
        self.assertFalse(record["observations"][0].get("identityQuarantined"))

    def test_expedia_rejects_booking_domain_and_price(self):
        record={"observations":[{"otaId":"expedia",
            "finalUrl":"https://www.booking.com/hotel/it/falso.html",
            "quotes":[{"verified":True}]}]}
        ns["enforce_portal_scope"](record,"expedia")
        self.assertTrue(record["observations"][0]["portalScopeViolation"])
        self.assertFalse(record["observations"][0]["quotes"][0]["verified"])

    def test_holidu_referral_is_not_independent_rate(self):
        record={"observations":[{"otaId":"holidu",
            "status":"referral_observed","referralTo":"booking",
            "finalUrl":"https://www.booking.com/hotel/it/test.html",
            "quotes":[{"verified":True}]}]}
        ns["enforce_portal_scope"](record,"holidu")
        self.assertTrue(record["observations"][0]["portalReferralOnly"])
        self.assertFalse(record["observations"][0]["quotes"][0]["verified"])

    def test_giove_rejects_wrong_domain_and_requires_account(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/"expedia.json"
            p.write_text(json.dumps({
                "propertyId":"sample","sessionMode":"public",
                "observations":[{"otaId":"expedia","dateReference":"booking",
                    "checkin":"2027-08-01","bookingReferenceCheckin":"2027-08-01",
                    "checkout":"2027-08-04","bookingReferenceCheckout":"2027-08-04",
                    "finalUrl":"https://www.booking.com/hotel/it/wrong.html",
                    "quotes":[{"verified":True}],
                    "frontendSnapshot":{"sampleOnly":True,"photoOrderSample":[{"src":"a"}]}}]
            }),encoding="utf-8")
            result=ns["evaluate"]("sample",{"expedia":p})
            check={c["code"]:c["passed"] for c in result["checks"]}
            self.assertFalse(check["portal_scope"])
            self.assertFalse(check["account_profile"])
            self.assertFalse(check["prices"])

if __name__=="__main__":
    unittest.main()
