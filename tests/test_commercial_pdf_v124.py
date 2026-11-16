"""Guard the four-page client-facing BarbarHouse frontend report and preserve exports."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
REPORT=(ROOT/"src/frontend-consulting-report.ts").read_text(encoding="utf-8")
AUTH=(ROOT/"src/AuthGate.tsx").read_text(encoding="utf-8")

class CommercialReport(unittest.TestCase):
    def test_isolated_web_report_and_four_pages(self):
        self.assertIn('if (isWebAudit) {',APP)
        self.assertIn('html = buildFrontendConsultingReportHtml({',APP)
        self.assertIn('let html = `',APP)
        self.assertIn('page(1,"Quadro generale e rating",p1)',REPORT)
        self.assertIn('page(2,"Tariffe e distribuzione OTA",p2)',REPORT)
        self.assertIn('page(3,"Sito diretto, immagini e recensioni",p3)',REPORT)
        self.assertIn('page(4,"Asimmetrie e priorità consulenziali",p4)',REPORT)
        self.assertIn('@page{size:A4;margin:0}',REPORT)

    def test_brand_and_account_attribution(self):
        for phrase in ('BarbarHouse','SCRAPING FRONTEND','Consulente · account di esecuzione'):
            self.assertIn(phrase,REPORT)
        self.assertIn('consultantName: profile.full_name.trim()',AUTH)
        self.assertIn('velora-scraping-operator:',APP)
        self.assertIn('scanningOperator' if 'scanningOperator' in APP else 'scrapingOperator',APP)
        self.assertIn('Non registrato per questa scansione',REPORT)

    def test_verified_tariff_ranges_are_separate(self):
        self.assertIn('quote.verified',REPORT) if 'quote.verified' in REPORT else self.assertIn('q.verified===true',REPORT)
        self.assertIn('q.pilotVerified===true',REPORT)
        self.assertIn('q.manualIdentityConfirmed!==false',REPORT)
        self.assertIn('const verified=eur.filter(q=>q.verified)',REPORT)
        self.assertIn('formatRange(verified.length?verified:observed)',REPORT)
        self.assertIn('Tariffe minime e massime per OTA',REPORT)
        self.assertIn('I prezzi USD non sono convertiti',REPORT) if 'I prezzi USD non sono convertiti' in REPORT else self.assertIn('Le tariffe USD non sono convertite',REPORT)

    def test_rating_is_source_labelled(self):
        self.assertIn('profile?.status==="sampled"',REPORT)
        self.assertIn('Booking.com',REPORT)
        self.assertIn('Google',REPORT)
        self.assertIn('RATING PUBBLICO',REPORT)
        self.assertIn('Rating pubblico non verificato',REPORT)

    def test_preserves_technical_exports_and_method(self):
        self.assertIn('Tariffe puntuali e delta tra OTA',APP)
        self.assertIn('Tabella completa delle valutazioni',APP)
        self.assertIn('pilotWrongListingReason',APP)
        self.assertIn('CONFRONTO NON DETERMINABILE',REPORT)
        self.assertIn('Nessun prezzo verificato',REPORT)

if __name__=="__main__":
    unittest.main()
