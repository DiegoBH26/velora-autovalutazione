"""Controlled, auditable specialist messaging and Agoda recovery contracts."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")


class CollaborationContract(unittest.TestCase):
    def test_python_parses(self):
        ast.parse(SERVER)
        ast.parse(PILOT)

    def test_help_messages_refer_only_to_existing_booking_evidence(self):
        self.assertIn('"help_request","help_reply","review_decision"',SERVER)
        self.assertIn('"recipient":"booking"',SERVER)
        self.assertIn('"recipient":"agoda"',SERVER)
        self.assertIn('reference=agent_mailbox_reference(property_id,expected_name)',SERVER)
        self.assertIn('if not matching:',SERVER)
        self.assertIn('"decision":"blocked_no_exact_booking_lock"',SERVER)
        self.assertIn('"decision":"approved_one_same_page_recheck"',SERVER)
        self.assertIn('peer_callback=peer_callback',SERVER)
        self.assertIn('peer_callback("pricing_help",stay,',PILOT)
        self.assertIn('peer_callback("recovery_result",stay,',PILOT)
        self.assertIn('MAILBOX_LIMIT=120',SERVER)

    def test_giove_viewer_displays_real_message_text(self):
        self.assertIn('help_request:"Richiesta di aiuto tra agenti"',APP)
        self.assertIn('help_reply:"Risposta tecnica condivisa"',APP)
        self.assertIn('review_decision:"Giove · Controllo e limiti operativi"',APP)
        self.assertIn('event.details?.message',APP)

    def test_agoda_recovery_is_single_page_and_bounded(self):
        section=PILOT.split('elif channel == "agoda":\n                candidates=',1)[1].split(
            'elif channel in {"airbnb","vrbo"}:',1)[0]
        self.assertIn('same_page_room_grid_recheck',section)
        self.assertIn('scrollIntoView',section)
        self.assertIn('await page.wait_for_timeout(1300)',section)
        self.assertIn('recovered=await agoda_room_offer_visual_candidates(page,stay)',section)
        self.assertIn('if not record.get("quotes"):',section)
        self.assertNotIn('page.goto(',section)
        self.assertNotIn('page.reload(',section)


if __name__=="__main__":
    unittest.main()
