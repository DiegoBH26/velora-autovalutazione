"""Local tests for discovery-time human pause, without contacting OTAs."""
import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "browser_audit_pilot.py"

def load_verifier(scope):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    node = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "verify_ota_candidate_page")
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["verify_ota_candidate_page"]

class FakePage:
    def __init__(self):
        self.url = "about:blank"
        self.closed = False
        self.loads = 0
    async def goto(self,url,**kwargs):
        self.url = url
        self.loads += 1
        return SimpleNamespace(status=200)
    async def wait_for_timeout(self,milliseconds):
        pass
    async def close(self):
        self.closed = True

class FakeContext:
    def __init__(self,page): self.page=page
    async def new_page(self): return self.page

class DiscoveryHumanPauseTest(unittest.IsolatedAsyncioTestCase):
    async def run_scenario(self, challenge, expected_handoff):
        page=FakePage()
        calls=[]
        async def dismiss(page): pass
        async def gate(page): return challenge
        async def handoff(page, callback, payload, ghost):
            calls.append((page.url,payload["type"]))
            return "skip"
        verifier=load_verifier({
            "asyncio": asyncio,
            "normalize_ota_listing_url":lambda c,u:u,
            "allowed_by_robots":lambda u,r:True,
            "dismiss_cookie":dismiss,
            "_visible_human_challenge":gate,
            "_human_assist":handoff,
            "OTA_META":{"vrbo":{"label":"Vrbo"}},
        })
        result=await verifier(
            FakeContext(page),"vrbo","https://www.vrbo.com/11118543ha",
            "Perla Saracena","Salve","",{},
            assist_callback=lambda payload:"skip",
        )
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertEqual(page.loads,1)
        self.assertTrue(page.closed)
        self.assertEqual(bool(calls),expected_handoff)
        if expected_handoff:
            self.assertEqual(calls[0][1],"visible_public_challenge")
        return result

    async def test_real_challenge_pauses_before_leaving_page(self):
        await self.run_scenario({"visible":True,"blocked":False,"reason":"puzzle"},True)

    async def test_hard_denial_is_not_presented_as_a_solvable_challenge(self):
        result=await self.run_scenario({"visible":False,"blocked":True,"reason":"blocked"},False)
        self.assertIn("Accesso negato",result["evidence"])

if __name__ == "__main__":
    unittest.main()
