"""Regression contract for the Velora interactive radar visual navigation.

The radar routes to existing modules.  It does not replace storage, scraping, interview
selection, report generators or browser-local audit archives.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
RADAR = (ROOT / "src/VeloraRadar.tsx").read_text(encoding="utf-8")
RADAR_CSS = (ROOT / "src/velora-radar.css").read_text(encoding="utf-8")
WORKSPACE_CSS = (ROOT / "src/workspace-dark.css").read_text(encoding="utf-8")

class RadarNavigationContract(unittest.TestCase):
    def test_panoramica_uses_real_clickable_radar(self):
        for text in ('<VeloraRadar', 'radarSectors: VeloraRadarSector[]',
                     'EXTERNAL_WEB_AUDIT_DATA.map((macro,index)',
                     'onSelect={(id)=>', 'navigateVelora("macroarea",id.slice(6))',
                     'onBack={workspaceSection==="macroaree"?'):
            self.assertIn(text, APP)

    def test_all_operational_sectors_and_existing_targets(self):
        sectors = ['struttura','intervista','personalizza','rapida','audit','macroaree',
                   'bookingengine','commerciale','scraping','mappa','piani','contenuti',
                   'asimmetrie','tariffe','recensioni','kpi','criticita','report']
        for sector in sectors:
            with self.subTest(sector=sector):
                self.assertIn('id:"'+sector+'"', APP)
                if sector not in ('macroaree','personalizza'):
                    self.assertIn('data-velora-view="'+sector+'"',WORKSPACE_CSS)

    def test_ota_accordion_blocks_have_their_existing_controls(self):
        for block in ['mappa','bookingengine','commerciale','scraping','piani',
                      'contenuti','asimmetrie','tariffe','recensioni','macro']:
            with self.subTest(block=block):
                self.assertIn('data-audit-block="'+block+'"', APP)
                self.assertIn('data-audit-block="'+block+'"', WORKSPACE_CSS)
        self.assertIn('id="velora-pricing-details"', APP)
        self.assertIn('id="velora-scraping-tools"', APP)
        self.assertIn('renderExternalWebAudit()', APP)

    def test_reopens_saved_interviews_and_legacy_archive_entries(self):
        self.assertIn('setWorkspaceSection("panoramica")', APP)
        self.assertIn('setWorkspaceSection("rapida");', APP)
        self.assertIn('setWorkspaceSection("panoramica");', APP)
        for marker in ['localStorage.setItem(ACTIVE_STRUCTURE_KEY',
                       'function confirmCustomInterview()',
                       'function openInterviewCustomizer()',
                       'function openStructureAnalysis(',
                       'setCustomQuickDraftIds(', 'setRateQuotes(',
                       'generatePrintableReport', 'exportJson', 'exportCsv']:
            self.assertIn(marker, APP)

    def test_visual_svg_is_fully_clickable_and_accessible(self):
        for marker in ['function wedgePath(', 'onClick={() => onSelect(sector.id)}',
                       'onKeyDown={(event) =>', 'event.key === "Enter"',
                       'aria-label={`Apri', 'role="button"', 'tabIndex={0}']:
            self.assertIn(marker, RADAR)
        self.assertNotIn('fetch(', RADAR)
        self.assertNotIn('localStorage.setItem', RADAR)
        self.assertNotIn('localStorage.getItem', RADAR)
        self.assertNotIn('resetAssessment(', RADAR)
        self.assertIn('@media(prefers-reduced-motion:reduce)', RADAR_CSS)

if __name__ == "__main__":
    unittest.main()
