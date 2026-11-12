"""UI-only regression safety: radar hover stability and dark contrast (R2)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
RADAR_CSS = (ROOT / "src/velora-radar.css").read_text(encoding="utf-8")
DARK_CSS = (ROOT / "src/workspace-dark.css").read_text(encoding="utf-8")
SHELL = (ROOT / "src/VeloraWorkspace.tsx").read_text(encoding="utf-8")


class RadarContrastR2(unittest.TestCase):
    def test_hover_does_not_translate_sector_buttons(self):
        self.assertNotIn("transform:translateY(-1px)", RADAR_CSS)
        self.assertIn("transform: none!important", RADAR_CSS)

    def test_fixed_wheel_geometry_and_context(self):
        self.assertIn("align-items: start;", RADAR_CSS)
        self.assertIn("aspect-ratio: 1 / 1;", RADAR_CSS)
        self.assertIn("height: 140px;", RADAR_CSS)
        self.assertIn("flex: 0 0 auto;", RADAR_CSS)

    def test_ota_card_scoped_contrast_and_no_lost_agents(self):
        self.assertIn('data-velora-agent={agent.id}', APP)
        self.assertIn('data-velora-selected={selected ? "yes" : "no"}', APP)
        self.assertIn("[data-velora-agent]", DARK_CSS)
        self.assertIn("background-color: #1b2d45!important", DARK_CSS)
        self.assertIn("text-emerald-9", DARK_CSS)
        self.assertIn("text-rose-9", DARK_CSS)
        self.assertIn('SPECIALIST_AGENTS', APP)
        self.assertIn('launchAgentBatch([agent.id])', APP)

    def test_archive_and_other_translucent_panes_covered(self):
        self.assertIn('bg-[#FAF9FC]', DARK_CSS)
        self.assertIn('bg-white/', DARK_CSS)
        self.assertIn('RADAR · R4', SHELL)
        self.assertIn('function openStructure(', APP)
        self.assertIn('function confirmCustomInterview()', APP)

if __name__ == "__main__":
    unittest.main()
