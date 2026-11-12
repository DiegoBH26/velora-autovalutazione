"""R6 regression: global dark legibility, OTA result navigation, bounded specialist runs."""
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
CSS=(ROOT/"src/workspace-dark.css").read_text(encoding="utf-8")
SHELL=(ROOT/"src/VeloraWorkspace.tsx").read_text(encoding="utf-8")
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")

def lightness(hex_value):
    rgb=[int(hex_value[i:i+2],16)/255 for i in (1,3,5)]
    linear=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb]
    return sum(a*b for a,b in zip(linear,(0.2126,0.7152,0.0722)))


class VeloraR6ContrastAndNavigation(unittest.TestCase):
    def test_every_light_pastel_background_in_app_has_dark_override(self):
        backgrounds=set(re.findall(r"bg-\[(#[0-9a-fA-F]{6})\]",APP))
        unhandled=[color for color in backgrounds if lightness(color)>=0.75
                   and "bg-["+color+"]" not in CSS]
        self.assertEqual(unhandled,[],f"Pastel surfaces missing dark contrast mapping: {unhandled}")

    def test_giove_chat_has_explicit_dark_container_and_cards(self):
        self.assertIn("data-velora-agent-chat",APP)
        self.assertIn("data-velora-chat-event",APP)
        self.assertIn("[data-velora-chat-event]",CSS)
        self.assertIn("background:#21354e!important",CSS)
        self.assertIn("color:#f1f7ff!important",CSS)

    def test_rate_results_reachable_with_single_click_from_agent_console(self):
        self.assertIn('aria-label="Consulta i risultati durante la scansione"',APP)
        self.assertIn('aria-label="Navigazione rapida ai dati delle scansioni"',APP)
        self.assertGreaterEqual(APP.count('onClick={()=>navigateVelora("tariffe")}'),2)
        self.assertGreaterEqual(APP.count('onClick={()=>navigateVelora("asimmetrie")}'),2)
        self.assertIn('onClick={()=>navigateVelora("report")}>Report completo',APP)
        self.assertIn('data-audit-block="tariffe" open={workspaceSection==="tariffe"}',APP)
        self.assertIn('id="velora-pricing-details"',APP)
        self.assertIn('data-velora-view={workspaceSection}',APP)
        self.assertIn('RADAR · R6',SHELL)

    def test_long_running_scan_is_explained_without_fake_eta(self):
        self.assertIn("const longRunning=Boolean(",APP)
        self.assertIn("La percentuale non è una stima del tempo residuo",APP)
        self.assertIn("runningAt?: string",APP)
        self.assertIn('AGENT_RUNS[key]["runningAt"]',SERVER)
        self.assertIn('slow_public_specialists={"hotels","travelocity","trip","priceline"}',SERVER)
        self.assertIn("asyncio.wait_for(coroutine,timeout=budget_seconds)",SERVER)
        self.assertIn("tempo limite di {budget_seconds//60} minuti superato",SERVER)
        self.assertIn('status:"failed"',APP)

if __name__=="__main__":
    unittest.main()
