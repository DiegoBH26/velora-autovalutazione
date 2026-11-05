"""Backend-only, audited specialist handoff regression checks."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
NETWORK=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")

class AgentMailboxContracts(unittest.TestCase):
    def test_source_parses(self):
        ast.parse(SERVER)
        ast.parse(NETWORK)

    def test_mailbox_is_bounded_and_structured(self):
        self.assertIn("MAILBOX_EVENT_TYPES=",SERVER)
        self.assertIn("MAILBOX_LIMIT=120",SERVER)
        self.assertIn('def agent_mailbox_publish(',SERVER)
        self.assertIn('"agent-mailbox.json"',SERVER)
        self.assertIn("temporary.replace(dest)",SERVER)
        self.assertIn("event_type not in MAILBOX_EVENT_TYPES",SERVER)
        self.assertIn('event.get("from")=="booking"',SERVER)
        self.assertIn('details.get("propertyName")==property_name',SERVER)
        self.assertIn('if k in {"requestedCheckin","requestedCheckout","checkin"',SERVER)
    
    def test_specialist_receive_booking_reference_without_cross_navigation(self):
        self.assertIn('agent_mailbox_reference(property_id,str(data.get("name") or ""))',SERVER)
        self.assertIn('agent_mailbox_result(property_id,agent_id)',SERVER)
        self.assertIn('event_type=("technical_block" if errors else',SERVER)
        self.assertIn('"pricing_read_failure" if weak and prices==0',SERVER)
        self.assertIn('if agent_id=="booking":',SERVER)

    def test_giove_compares_exact_windows_not_month(self):
        self.assertIn('str(row.get("requestedCheckin") or "")',NETWORK)
        self.assertIn('str(row.get("requestedCheckout") or "")',NETWORK)
        self.assertIn('all(booking_locks[window]==local_locks[window] for window in common)',NETWORK)

if __name__=="__main__":
    unittest.main()
