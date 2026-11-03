"""Regression: assisted Expedia prices are attributed only to the active structure."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")


class ExpediaAssistedCapture(unittest.TestCase):
    def test_one_click_path_reuses_existing_rate_quote_archive(self):
        self.assertIn("function prepareExpediaAssistedRate()",APP)
        self.assertIn("prepareExpediaAssistedRate}",APP)
        self.assertIn("function showAssistedRateForm()",APP)
        self.assertIn('id="velora-pricing-details"',APP)
        self.assertIn('id="velora-manual-rate-form"',APP)
        self.assertIn("details.open=true",APP)
        self.assertIn("Registra tariffa che vedo",APP)
        self.assertIn('href="https://www.expedia.it/"',APP)
        self.assertIn("setRateQuotes((previous) => [...previous, quote]);",APP)
        self.assertIn('origin: "manual"',APP)

    def test_no_cross_property_date_or_ota_switch(self):
        self.assertIn("browserPilotResult?.propertyId===activeAuditData.id",APP)
        self.assertIn('row.otaId==="expedia"',APP)
        self.assertIn("rateDraft.otaId!==manualRateSource.otaId",APP)
        self.assertIn("manualRateSource?.locked",APP)
        self.assertIn("manualRateSource.listingName?.trim()",APP)
        self.assertIn("manualRateSource.identityConfirmed",APP)

    def test_source_and_identity_are_required_before_saving(self):
        self.assertIn("manualListingTitle: manualRateSource?.listingName?.trim()",APP)
        self.assertIn("manualIdentityConfirmed: Boolean(manualRateSource?.identityConfirmed)",APP)
        self.assertIn("sourceUrl: rateDraft.sourceUrl.trim()",APP)
        self.assertIn('["expedia.it","expedia.com","expedia.co.uk"',APP)
        self.assertIn("url.protocol===\"https:\"",APP)
        self.assertIn("non verificata dall'agente",APP)
        self.assertIn("solo con unità fisica confermata",APP)

    def test_assisted_dates_are_editable_and_nights_are_calculated(self):
        self.assertIn("function updateAssistedStay(checkin:string,checkout:string)",APP)
        self.assertIn("const nights=/^\\d{4}-\\d{2}-\\d{2}$/.test(checkin)",APP)
        self.assertIn('type="date" min={todayLocalIso()} value={manualRateSource.checkin}',APP)
        self.assertIn('type="date" min={manualRateSource.checkin||todayLocalIso()} value={manualRateSource.checkout}',APP)
        self.assertIn("updateAssistedStay(event.target.value,manualRateSource.checkout)",APP)
        self.assertIn("updateAssistedStay(manualRateSource.checkin,event.target.value)",APP)
        self.assertIn("setRateDraft(previous=>({",APP)
        self.assertIn("...previous,stayDate:checkin,nights,total:0,originalTotal:0,",APP)
        self.assertIn("manualRateSource.nights<1",APP)
        self.assertIn("le date precedenti sono solo un suggerimento".lower(),APP.lower())
        self.assertIn('locked:false,listingName:"",identityConfirmed:false,',APP)

    def test_multiple_rooms_keeps_stay_but_resets_prior_room_price(self):
        self.assertIn('setAssistedRateConfirmation(',APP)
        self.assertIn('if (manualRateSource) {\\n      setAssistedRateConfirmation('.replace("\\\\n","\\n"),APP)
        self.assertIn('setRateDraft(previous=>({\\n        ...previous,total:0,roomType:"",unitId:""'.replace("\\\\n","\\n"),APP)
        self.assertIn("Puoi inserire un’altra camera",APP)
        self.assertIn("assistedRateConfirmation &&",APP)
        self.assertIn("updateAssistedGuests(Number(event.target.value))",APP)

    def test_reports_do_not_mislabel_human_quotes_as_parser_verified(self):
        self.assertIn('quote.origin === "pilot" && quote.pilotVerified === true',APP)
        self.assertIn("validate automaticamente",APP)
        self.assertIn("quote.manualListingTitle",APP)
        self.assertIn("richiedi valutazione Rapid API",APP)
        self.assertIn("soggetto ad approvazione partner",APP)


if __name__=="__main__":
    unittest.main()
