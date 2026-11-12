"""UI contract: archive entry -> radar, larger sector labels, global legibility.

The existing question banks, archives, scraping agents and reports are unchanged.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
RADAR = (ROOT / "src/VeloraRadar.tsx").read_text(encoding="utf-8")
RADAR_CSS = (ROOT / "src/velora-radar.css").read_text(encoding="utf-8")
WORKSPACE = (ROOT / "src/workspace-dark.css").read_text(encoding="utf-8")
SHELL = (ROOT / "src/VeloraWorkspace.tsx").read_text(encoding="utf-8")


class RadarReadableR3(unittest.TestCase):
    def test_both_archive_entry_buttons_open_radar(self):
        start = APP.index('function openStructureAnalysis(structure:')
        body = APP[start:APP.index('const radarSectors:',start)]
        self.assertIn('setWorkspaceSection("panoramica")', body)
        self.assertNotIn('setWorkspaceSection(mode==="web-audit"?"audit":"rapida")', body)
        self.assertIn('openStructureAnalysis(structure, "web-audit")', APP)
        self.assertIn('openStructureAnalysis(structure, "quick-hotel-bb")', APP)
        self.assertIn('openStructure(structure);', body)

    def test_radar_never_requires_tiny_wedge_captions(self):
        self.assertIn('shortSectorNames: Record<string, string>', RADAR)
        self.assertIn('shortMacroNames', RADAR)
        self.assertIn('velora-radar__slice-index', RADAR)
        self.assertIn('velora-radar__slice-name', RADAR)
        self.assertIn('onClick={() => onSelect(sector.id)}', RADAR)
        self.assertIn('font-size:19px;', RADAR_CSS)
        self.assertIn('font-size:14.5px;', RADAR_CSS)
        self.assertIn('font-size:.93rem;', RADAR_CSS)

    def test_legibility_spans_entire_app(self):
        for marker in ('text-[9px]', 'text-[10px]', 'text-[11px]',
                       'text-[12px]', '[class~="text-xs"]',
                       '[class~="text-sm"]', 'text-[#6B4F06]',
                       '[data-velora-agent]', 'velora-core--archive'):
            with self.subTest(marker=marker):
                self.assertIn(marker, WORKSPACE)
        self.assertIn('RADAR · R5', SHELL)

    def test_no_data_logic_changed_for_ui(self):
        for marker in ('function openStructure(', 'function confirmCustomInterview()',
                       'function switchAssessmentMode(', 'browserPilotResult',
                       'rateQuotes', 'SPECIALIST_AGENTS', 'function saveDiagnosis('):
            self.assertIn(marker, APP)
        self.assertNotIn('localStorage.setItem', RADAR)
        self.assertNotIn('fetch(', RADAR)

if __name__ == "__main__":
    unittest.main()
