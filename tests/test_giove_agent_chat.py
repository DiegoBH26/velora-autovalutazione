"""Read-only Giove agent mailbox UI and endpoint contracts."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")

class GioveChatTests(unittest.TestCase):
    def test_backend_syntax(self):
        ast.parse(SERVER)

    def test_chat_is_scoped_to_structure_and_read_only(self):
        self.assertIn('"/api/agents/chat"',SERVER)
        block=SERVER.split('if route=="/api/agents/chat":',1)[1].split('if route=="/api/agents/status":',1)[0]
        self.assertIn('agent_mailbox_path(property_id)',block)
        self.assertIn('payload.get("propertyId")!=property_id',block)
        self.assertIn('events[-120:]',block)
        self.assertIn('mode":"structured-events-read-only"',block)
        self.assertNotIn('agent_mailbox_publish(',block)

    def test_ui_is_real_and_refreshable(self):
        self.assertIn('Mostrami chat agenti',APP)
        self.assertIn('Nascondi chat agenti',APP)
        self.assertIn('async function loadAgentChat()',APP)
        self.assertIn('/api/agents/chat?propertyId=',APP)
        self.assertIn('data.propertyId!==activeAuditData.id',APP)
        self.assertIn('Aggiorna chat',APP)
        self.assertIn('Nessun messaggio registrato per questa struttura',APP)
        self.assertIn('Eventi reali della mailbox locale',APP)

if __name__=="__main__":
    unittest.main()
