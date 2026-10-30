"""No-network regression checks for Velora specialist naming and legacy preservation.

The CI runner intentionally does not import browser_audit_pilot (Playwright and
Chrome are installed on the user's PC, not in the GitHub Pages builder).
"""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def assigned_dict(file: Path, name: str):
    root=ast.parse(file.read_text(encoding="utf-8"))
    for node in root.body:
        if isinstance(node,ast.Assign):
            if any(isinstance(t,ast.Name) and t.id==name for t in node.targets):
                return ast.literal_eval(node.value)
    raise AssertionError(f"{name} not found")

class AgentCatalogTest(unittest.TestCase):
    def setUp(self):
        self.module=ROOT/"velora_agent_network.py"
        self.server=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
        self.app=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        self.catalog=assigned_dict(self.module,"AGENTS")
        self.planned=assigned_dict(self.module,"FUTURE_AGENTS")

    def test_live_agents_named_uniquely(self):
        expected={"booking":"Minerva","agoda":"Galileo","airbnb":"Apollo",
                  "official_site":"Leonardo","reviews":"Ipazia"}
        self.assertEqual({k:v["name"] for k,v in self.catalog.items()},expected)
        self.assertEqual(len({v["name"] for v in self.catalog.values()}),5)

    def test_reserved_agents_not_runnable(self):
        self.assertEqual(self.planned["expedia"]["name"],"Ercole")
        self.assertEqual(self.planned["vrbo"]["name"],"Atlante")
        self.assertEqual(self.planned["holidu"]["name"],"Mercurio")
        self.assertTrue(set(self.planned).isdisjoint(self.catalog))
        self.assertEqual(len({v["name"] for v in list(self.catalog.values())+list(self.planned.values())}),
                         len(self.catalog)+len(self.planned))

    def test_manual_reviewer_and_cmd_labels(self):
        self.assertIn('REVIEWER_NAME = "Giove"',self.module.read_text(encoding="utf-8"))
        self.assertIn('print_giove_report(report)',self.server)
        self.assertIn('route=="/api/agents/validate"',self.server)
        self.assertIn('if active:',self.server)
        self.assertIn('result=="VALIDATO"',self.server)
        self.assertIn('Giove (Revisore / Validatore)',self.app)
        self.assertIn('✓ VALIDATO',self.app)

    def test_legacy_and_questions_untouched(self):
        self.assertIn('route=="/api/pilot/start"',self.server)
        self.assertIn('route=="/api/audit/start"',self.server)
        self.assertIn("SCREENSHOT_INTERVIEW_PRESET_IDS",self.app)
        self.assertIn("specialist-agents",self.server)
        self.assertIn("AGENT_WORK_SLOTS",self.server)

if __name__ == "__main__":
    unittest.main()
