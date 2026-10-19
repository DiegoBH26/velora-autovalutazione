"""Regression checks for the single-visit VRBO flow in Velora v117.

Do not contact OTA sites. No prices, CAPTCHA solving or automation evasion.
"""
import ast
import unittest
from pathlib import Path

SOURCE=Path(__file__).resolve().parents[1]/"browser_audit_pilot.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"),filename=str(SOURCE))
TEXT=SOURCE.read_text(encoding="utf-8")

def direct_vrbo_gate(channels, vrbo_public_hints):
    node=next(
        n.value for n in ast.walk(TREE) if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=="vrbo_single_direct_pricing" for t in n.targets)
    )
    return eval(compile(ast.Expression(node),"<vrbo-public-reference>", "eval"),
                {"bool":bool,"len":len},
                {"channels":channels,"vrbo_public_hints":vrbo_public_hints})

class VrboSingleOpenV117Tests(unittest.TestCase):
    def test_only_user_supplied_vrbo_reference_enables_shortcut(self):
        hint=["https://www.vrbo.com/it-it/pdp/lo/42693330"]
        self.assertTrue(direct_vrbo_gate(["vrbo"],hint))
        self.assertFalse(direct_vrbo_gate(["vrbo"],[]))
        self.assertFalse(direct_vrbo_gate(["booking","vrbo"],hint))
        self.assertFalse(direct_vrbo_gate(["agoda"],hint))
        self.assertFalse(direct_vrbo_gate(["airbnb"],hint))
        self.assertFalse(direct_vrbo_gate(["holidu"],hint))

    def test_observe_default_preserves_other_channels(self):
        function=next(n for n in TREE.body if isinstance(n,ast.AsyncFunctionDef) and n.name=="observe")
        self.assertIn("direct_public_source",[a.arg for a in function.args.args])
        self.assertEqual(len(function.args.defaults),5)  # property_name, city, assist_callback, ghost, direct_public_source
        self.assertIsInstance(function.args.defaults[-1],ast.Constant)
        self.assertIs(function.args.defaults[-1].value,False)

    def test_skip_redundant_discovery_but_keep_fresh_pricing(self):
        self.assertIn("vrbo-one-open-plan: verifica anticipata della pagina saltata",TEXT)
        self.assertIn('not (channel=="vrbo" and vrbo_single_direct_pricing)',TEXT)
        self.assertIn('direct_public_source=bool(channel=="vrbo" and vrbo_single_direct_pricing)',TEXT)
        self.assertIn('not direct_public_source:',TEXT)
        self.assertIn('"status":"skipped_known_public_listing"',TEXT)
        self.assertIn("identity=_strict_ota_identity_match(",TEXT)
        self.assertIn("vrbo_quote_candidates(page,stay)",TEXT)

    def test_block_not_misrepresented_as_interactive_challenge(self):
        self.assertIn("l'accesso è temporaneamente limitato",TEXT)
        self.assertIn("you have been blocked",TEXT)
        self.assertIn('status="rate_limited" if limited_status==429 else "human_verification_pending"',TEXT)

if __name__=="__main__":
    unittest.main()
