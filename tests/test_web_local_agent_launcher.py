"""Windows one-click agent launcher: maintain explicit user action and URL safety."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
BAT = (ROOT / "AGGIORNA_VELORA_COMPLETO.bat").read_text(encoding="utf-8")
PS1 = (ROOT / "VELORA_AVVIO_WEB.ps1").read_text(encoding="utf-8")
CSS = (ROOT / "src/velora-readability.css").read_text(encoding="utf-8")
INCLUSIVE = (ROOT / "src/velora-inclusive-dark.css").read_text(encoding="utf-8")


class LocalAgentWebLauncherTest(unittest.TestCase):
    def test_web_launch_is_click_only_and_existing_connection_still_checked(self):
        self.assertIn("function startAndConnectLocalAgent()", APP)
        self.assertIn('link.href = "velora-agent://start"', APP)
        self.assertIn('link.click()', APP)
        self.assertIn('connectLocalAgent(true)', APP)
        self.assertIn('data-velora-local-agent-status', APP)
        self.assertEqual(APP.count('data-velora-local-agent-connect'), 2)
        self.assertIn('Avvia / Collega agente', APP)

    def test_windows_protocol_requires_exact_fixed_uri_and_bat(self):
        self.assertIn('[switch]$Register', PS1)
        self.assertIn("^velora-agent://start/?$", PS1)
        self.assertIn("AVVIA_AGENTE_VELORA.bat", PS1)
        self.assertIn("HKCU:", PS1)
        self.assertIn('Start-Process -FilePath $env:ComSpec', PS1)
        self.assertIn('if ($Request -notmatch', PS1)

    def test_complete_updater_registers_only_after_network_validation(self):
        self.assertIn('VELORA_AVVIO_WEB.ps1.new', BAT)
        self.assertIn('VELORA_AVVIO_WEB.ps1" -Register', BAT)
        self.assertIn('errore_protocollo', BAT)
        self.assertLess(BAT.index("if errorlevel 1 goto :errore_import"),
                        BAT.index("powershell -NoProfile -ExecutionPolicy Bypass -File \"VELORA_AVVIO_WEB.ps1\" -Register"))
        self.assertIn("12/12 agenti importabili", BAT)

    def test_colors_are_legible_in_both_modes(self):
        self.assertIn('data-velora-local-agent-status', CSS)
        self.assertIn('data-velora-local-agent-connect', CSS)
        self.assertIn('data-velora-local-agent-status', INCLUSIVE)
        self.assertIn('data-velora-local-agent-connect', INCLUSIVE)


if __name__ == "__main__":
    unittest.main()
