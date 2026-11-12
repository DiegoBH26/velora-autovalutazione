"""Velora R5: one four-sector entry point; two nested radars; existing data untouched."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
RADAR = (ROOT / "src/VeloraRadar.tsx").read_text(encoding="utf-8")
RADAR_CSS = (ROOT / "src/velora-radar.css").read_text(encoding="utf-8")
DARK = (ROOT / "src/workspace-dark.css").read_text(encoding="utf-8")
SHELL = (ROOT / "src/VeloraWorkspace.tsx").read_text(encoding="utf-8")


class FourSectorRadarContract(unittest.TestCase):
    def test_home_has_exactly_four_root_sectors(self):
        start = APP.index("const primaryRadarSectors: VeloraRadarSector[] = [")
        end = APP.index("];", start)
        root_sectors = APP[start:end]
        ids = re.findall(r'\bid:"([a-z]+)"', root_sectors)
        self.assertEqual(ids, ["auditradar", "kpi", "report", "macroaree"])
        for text in ('label:"AUDIT"', 'label:"KPI"', 'label:"REPORT"', 'label:"AREE"'):
            self.assertIn(text, root_sectors)
        self.assertIn('sectors={workspaceSection==="macroaree"?macroRadarSectors:workspaceSection==="auditradar"?auditRadarSectors:primaryRadarSectors}', APP)
        self.assertIn('mode={workspaceSection==="macroaree"?"macro":workspaceSection==="auditradar"?"audit":"main"}', APP)

    def test_audit_second_level_contains_existing_modules(self):
        match = re.search(r'const auditRadarIds = new Set\(\[(.*?)\]\);', APP)
        self.assertIsNotNone(match)
        ids = re.findall(r'"([a-z]+)"', match.group(1))
        self.assertEqual(len(ids), 11)
        self.assertEqual(set(ids), {
            "audit", "bookingengine", "commerciale", "scraping", "mappa",
            "piani", "contenuti", "asimmetrie", "tariffe", "recensioni",
            "criticita"
        })
        self.assertIn('const auditRadarSectors = radarSectors.filter(sector=>auditRadarIds.has(sector.id));', APP)
        self.assertIn('onClick:()=>navigateVelora("auditradar")', APP)
        self.assertIn('data-audit-block="scraping"', APP)
        self.assertIn('data-audit-block="commerciale"', APP)
        self.assertIn('data-audit-block="recensioni"', APP)

    def test_areas_second_level_keeps_all_macroareas_and_interview_tools(self):
        self.assertIn('EXTERNAL_WEB_AUDIT_DATA.map((macro,index)', APP)
        self.assertIn('workspaceSection==="macroaree" && (', APP)
        for dest in ['"struttura"', '"intervista"', '"personalizza"', '"rapida"']:
            self.assertIn('onClick={()=>navigateVelora(' + dest + ')', APP)
        self.assertIn('navigateVelora("macroarea",id.slice(6))', APP)
        self.assertIn('onBack={workspaceSection==="macroaree" || workspaceSection==="auditradar"?', APP)

    def test_kpi_and_report_open_real_sections_directly(self):
        self.assertIn('data-velora-view="kpi"', DARK)
        self.assertIn('data-velora-view="report"', DARK)
        self.assertIn('id="velora-kpi-summary"', APP)
        self.assertIn('id="velora-report-actions"', APP)
        for marker in ['generatePrintableReport', 'exportCsv', 'exportJson',
                       'flattenItems(EXTERNAL_WEB_AUDIT_DATA).filter',
                       'flattenItems(ASSESSMENT_DATA).filter',
                       'browserPilotResult.observations.length',
                       'rateQuotes.length']:
            self.assertIn(marker, APP)
        self.assertIn('Il generatore PDF sottostante è quello già presente', APP)

    def test_visual_radar_layout_and_storage_safety(self):
        self.assertIn('mode?: "main" | "macro" | "audit"', RADAR)
        self.assertIn('velora-radar--main', RADAR_CSS)
        self.assertIn('grid-template-columns:repeat(2,minmax(0,1fr))', RADAR_CSS)
        self.assertIn('RADAR · R5', SHELL)
        self.assertIn('function openStructureAnalysis(', APP)
        self.assertIn('function confirmCustomInterview()', APP)
        self.assertIn('localStorage.setItem(', APP)
        self.assertNotIn('localStorage.setItem(', RADAR)
        self.assertNotIn('resetAssessment(', RADAR)


if __name__ == "__main__":
    unittest.main()
