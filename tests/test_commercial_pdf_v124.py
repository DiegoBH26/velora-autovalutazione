"""Protect the four-page commercial PDF from technical-table regressions."""
import unittest
from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"src/App.tsx").read_text(encoding="utf-8")
class CommercialReport(unittest.TestCase):
    def test_has_isolated_web_override(self):
        self.assertIn('if (isWebAudit) {\n      const pilot =', APP)
        self.assertIn('page(1,p1)+page(2,p2)+page(3,p3)+page(4,p4)', APP)
        self.assertIn('let html = `', APP)
    def test_preserves_full_technical_export_source(self):
        self.assertIn('Tariffe puntuali e delta tra OTA', APP)
        self.assertIn('Tabella completa delle valutazioni', APP)
    def test_commercial_method_caveats(self):
        self.assertIn('Una verifica bloccata', APP) if 'Una verifica bloccata' in APP else self.assertIn('blocco del portale non dimostra', APP)
        self.assertIn('Limiti: audit frontend', APP)
if __name__=="__main__":
    unittest.main()
