"""UI restyle safety contract: existing business logic and storage stay in place."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
SHELL=(ROOT/"src/VeloraWorkspace.tsx").read_text(encoding="utf-8")
CSS=(ROOT/"src/workspace-dark.css").read_text(encoding="utf-8")

class WorkspaceRestylingContract(unittest.TestCase):
    def test_all_original_modules_remain_accessible(self):
        for code in [
            'function renderExternalWebAudit()', 'function openInterviewCustomizer()',
            'function switchAssessmentMode(', 'renderExternalWebAudit()',
            'renderQuickSections(QUICK_HOTEL_BB_CORE_DATA, 0)',
            'ASSESSMENT_DATA', 'customQuickDraftIds', 'customQuickItemIds',
            'localPilotSelectedChannels', 'browserPilotResult', 'portalSessions',
            'generatePrintableReport', 'exportJson', 'exportCsv', 'resetAssessment',
            'id="velora-pricing-details"', 'function resetCurrentStructureScraping('
        ]:
            with self.subTest(code=code):
                self.assertIn(code,APP)

    def test_current_archives_and_persistence_unchanged(self):
        for code in [
            'function loadAnalyzedStructures(', 'velora-analyzed-structures-v1',
            'velora-browser-pilot:', 'velora-active-structure-v1',
            'localStorage.setItem(', 'savedInterviewTemplate(',
            'setRateQuotes(', 'persistSession: true'
        ]:
            if code == 'persistSession: true':
                self.assertIn(code,(ROOT/"src/supabase.ts").read_text(encoding="utf-8"))
            else:
                with self.subTest(code=code):
                    self.assertIn(code,APP)

    def test_new_navigation_is_visual_only_and_no_fake_management_kpis(self):
        self.assertIn('function navigateVelora(section: string)',APP)
        self.assertIn('id="velora-scraping-tools"',APP)
        self.assertIn('id="velora-report-actions"',APP)
        self.assertIn('id="velora-new-audit"',APP)
        self.assertIn('id="velora-assessment-content"',APP)
        self.assertIn('function VeloraWorkspace',SHELL)
        self.assertIn('PERCORSO DI VALUTAZIONE',SHELL)
        self.assertIn('aria-current={item.active ? "page" : undefined}',SHELL)
        self.assertIn('.velora-workspace',CSS)
        self.assertNotIn('ADR medio',SHELL)
        self.assertNotIn('RevPAR',SHELL)
        self.assertNotIn('Notti vendute',SHELL)

if __name__=="__main__":
    unittest.main()
