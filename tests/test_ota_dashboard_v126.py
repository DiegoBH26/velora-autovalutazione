"""Protect the OTA command center, automated Expedia import and content evidence."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
WORKER=(ROOT/"chrome-companion-expedia/background.js").read_text(encoding="utf-8")

class OtaDashboardContracts(unittest.TestCase):
    def test_agents_remain_compact_and_review_moves_outside_cards(self):
        self.assertIn('grid items-stretch gap-3 md:grid-cols-3',APP)
        self.assertIn('grid items-stretch gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4',APP)
        self.assertIn('min-h-[232px]',APP)
        self.assertIn('min-h-[110px]',APP)
        self.assertIn('group.id==="access"',APP)
        self.assertIn('Agenti con accesso',APP)
        self.assertIn('Altri agenti',APP)
        self.assertIn('Come funzionano gli accessi Expedia, Vrbo e Holidu',APP)
        self.assertIn("Accessi, credenziali e test avanzati",APP)
        self.assertIn("Expedia · risultati acquisiti",APP)
        self.assertIn("setExpediaReviewOpen(open=>!open)",APP)
        self.assertIn("Vedi prezzi nell'audit OTA",APP)
        self.assertIn('id={`velora-pricing-ota-${otaId}`}',APP)

    def test_single_acquisition_populates_ota_pricing_without_duplicate_form(self):
        self.assertIn("function importCompanionExpediaRates()",APP)
        self.assertIn("importCompanionExpediaRates();",APP)
        self.assertIn("if(!identityConfirmed)return;",APP)
        self.assertIn("if(!captured.checkin||!captured.checkout||captured.guests<1)return;",APP)
        self.assertIn("setRateQuotes(previous=>[...previous,...fresh])",APP)
        self.assertIn('setExpediaReviewOpen(false)',APP)
        self.assertIn('velora-pricing-details',APP)

    def test_price_accordion_distinguishes_observed_from_imported(self):
        # Pilot preview can contain valid-looking Booking prices that stay
        # quarantined because their listing identity is unverified.
        self.assertIn('const observed = pilotEligiblePriceObservations(',APP)
        self.assertIn('ANNUNCIO ESTRANEO SCARTATO',APP)
        self.assertIn('const pending = observed.length>0 && count===0;',APP)
        self.assertIn('prezz${observed.length === 1 ? "o osservato" : "i osservati"}',APP)
        self.assertIn('non ancora registrati nell\'archivio tariffe',APP)
        self.assertIn('pilotListingIdentityWarning(browserPilotResult,observation)',APP)
        self.assertIn('Nessun prezzo osservato né registrato',APP)
        self.assertNotIn('"Nessuna tariffa rilevata"',APP)

    def test_edited_structure_name_is_canonical_for_agent_requests(self):
        self.assertIn('data.name=ownerInfo.propertyName.trim()',APP)
        self.assertIn('[activeAuditDataBase,ownerInfo.propertyName,ownerInfo.city',APP)
        self.assertIn('name:activeAuditData.name,city:activeAuditData.city',APP)
        self.assertIn('name: ownerInfo.propertyName || item.name',APP)
        self.assertIn('auditData:item.auditData?',APP)
        self.assertIn('id="velora-structure-profile"',APP)
        self.assertIn('Modifica anagrafica struttura',APP)
        self.assertIn('Le correzioni sono salvate automaticamente',APP)

    def test_audit_comparison_does_not_invent_photo_deltas(self):
        self.assertIn('OtaContentSnapshot',APP)
        self.assertIn('setOtaContentSnapshots(previous=>[',APP)
        self.assertIn('otaContentSnapshots:[]',APP)
        self.assertIn('Barra delle asimmetrie · Sito diretto MASTER · Booking riferimento tra OTA',APP)
        self.assertIn('Sito diretto · MASTER commerciale',APP)
        self.assertIn('Tariffe / Sito diretto',APP)
        self.assertIn('const asymmetryWithDirect=[directMasterRow,...otaAsymmetryRows]',APP)
        self.assertIn('pricingAccordionIds.map((otaId)',APP)
        self.assertIn('id="velora-pricing-ota-sito"',APP)
        self.assertIn('Prezzi e asimmetrie · sito diretto master / Booking riferimento OTA · apri/chiudi',APP)
        self.assertIn('Tariffe puntuali · sito diretto MASTER e OTA · apri/chiudi',APP)
        self.assertIn('Campione di Giove:',APP)
        self.assertIn('non equivale a una differenza tariffaria',APP)
        self.assertIn('images-and-page-text',APP)
        self.assertIn('foto',APP.lower())
        self.assertIn('const imageNodes=',WORKER)
        self.assertIn('photoAltSamples:[...photoAlts]',WORKER)
        self.assertNotIn('chrome.scripting.executeScript({target:{allFrames:true}',WORKER)

if __name__=="__main__":
    unittest.main()
