"""Leonardo R11 protects real diagnostic evidence and calendar controls."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
DIRECT=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")


class LeonardoCalendarAndDiagnosticsR11(unittest.TestCase):
    def test_python_module_parses(self):
        ast.parse(DIRECT)

    def test_booking_date_fields_below_fold_are_allowed(self):
        focus=DIRECT.split("async def _bedzzle_focus_box(",1)[1].split(
            "async def _bedzzle_named_calendar_state(",1)[0]
        self.assertIn("return r.width>0&&r.height>0;",focus)
        self.assertNotIn("r.top<innerHeight",focus)

    def test_all_frames_provide_technical_diagnostics(self):
        self.assertIn('sample["frameDiagnostics"]=[]',DIRECT)
        self.assertIn('for candidate_frame in scopes[:12]',DIRECT)
        self.assertIn('sample["dateAttempts"]=attempts[:12]',DIRECT)
        self.assertIn('leonardo_calendario_non_compilato.png',DIRECT)
        self.assertIn('systemic_calendar_failure=(',DIRECT)

    def test_form_may_load_after_initial_navigation(self):
        self.assertIn("async def _wait_for_booking_search_form(page, *, seconds=25)",DIRECT)

    def test_ui_displays_saved_real_logs_with_no_fake_success(self):
        self.assertIn("function formatLeonardoTechnicalLog(result: BrowserPilotResult)",APP)
        self.assertIn("loadLeonardoTechnicalLog()",APP)
        self.assertIn("Leonardo · Log tecnico effettivo del booking engine",APP)
        self.assertIn("Ricerca NON eseguita",APP)
        self.assertIn("Copia log",APP)


if __name__=="__main__":
    unittest.main()
