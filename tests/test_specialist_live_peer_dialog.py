"""Execute the local peer dialogue state machine without network or Chrome."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")


def load_consultation():
    module=ast.parse(SOURCE)
    fn=next(n for n in module.body if isinstance(n,ast.FunctionDef)
            and n.name=="specialist_peer_consultation")
    messages=[]
    context={
        "agent_mailbox_publish":lambda prop,sender,event,details: messages.append(
            (prop,sender,event,details)),
        "agent_mailbox_reference":lambda prop,name: {
            "propertyName":name,
            "windows":[{"requestedCheckin":"2027-08-01",
                        "requestedCheckout":"2027-08-04",
                        "checkin":"2027-09-26",
                        "checkout":"2027-09-29"}],
        },
    }
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"peer-dialog-test","exec"),context)
    return context,messages


STAY={"requestedCheckin":"2027-08-01","requestedCheckout":"2027-08-04",
      "checkin":"2027-09-26","checkout":"2027-09-29"}

class SpecialistPeerDialog(unittest.TestCase):
    def test_agoda_requests_help_before_same_page_mapping(self):
        env,messages=load_consultation()
        decision=env["specialist_peer_consultation"](
            "hotel-1","agoda","Masseria Tenuta Specolizzi",
            "pricing_help",STAY,
            {"actualRoomNames":5,"numericEuroPrices":6},
        )
        self.assertEqual(decision["strategy"],"same_page_offer_mapping")
        self.assertEqual(decision["maxAttempts"],1)
        self.assertEqual([(sender,event) for _,sender,event,_ in messages],
            [("agoda","help_request"),("booking","help_reply"),("giove","review_decision")])
        self.assertIn("5 camere e 6 elementi di prezzo",messages[0][3]["message"])
        self.assertIn("corrispondenza",messages[1][3]["message"])

    def test_giove_blocks_mismatched_dates(self):
        env,messages=load_consultation()
        invalid={**STAY,"checkin":"2027-09-27"}
        decision=env["specialist_peer_consultation"](
            "hotel-1","agoda","Masseria Tenuta Specolizzi","pricing_help",
            invalid,{"actualRoomNames":5,"numericEuroPrices":6}
        )
        self.assertFalse(decision["approved"])
        self.assertNotIn("help_reply",[event for _,_,event,_ in messages])
        self.assertIn("blocked_no_exact_booking_lock",
            [item[3].get("decision") for item in messages])

    def test_airbnb_wrong_brand_is_shared_and_quarantined(self):
        env,messages=load_consultation()
        decision=env["specialist_peer_consultation"](
            "hotel-1","airbnb","Masseria Tenuta Specolizzi","identity_help",STAY,
            {"observedTitle":"Masseria Tenuta Deserto"}
        )
        self.assertEqual(decision["strategy"],"quarantine_wrong_property")
        self.assertEqual([(sender,event) for _,sender,event,_ in messages],
            [("airbnb","help_request"),("booking","help_reply"),("giove","review_decision")])

    def test_no_scope_escalation(self):
        env,messages=load_consultation()
        denied=env["specialist_peer_consultation"](
            "hotel-1","agoda","Hotel","execute_code",STAY,{})
        self.assertFalse(denied["approved"])
        self.assertEqual(messages,[])

if __name__=="__main__":
    unittest.main()
