"""Regression for Leonardo -> UI and safe OTA specialist evidence reuse."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from velora_shared_intelligence import read_peer_evidence, store_peer_evidence

ROOT=Path(__file__).resolve().parents[1]

class LeonardoSharedEvidenceTests(unittest.TestCase):
    def test_property_isolation_and_rating_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp)
            agent_result={
                "otaProfiles":{"booking":{"status":"sampled","url":"https://www.booking.com/hotel/it/example.html",
                    "rating":9.3,"ratingScale":10,"reviewCount":174,
                    "evidence":"AggregateRating JSON-LD"}},
                "sharedKnowledge":{"propertyId":"casa-a","coverCandidate":{"order":1,"src":"https://example.org/photo.jpg"},
                    "mentionedAmenities":["pool"],"listingIdentityQuarantined":False},
            }
            store_peer_evidence(runtime,"casa-a","booking",agent_result)
            assert read_peer_evidence(runtime,"casa-b")=={}
            saved=read_peer_evidence(runtime,"casa-a",skip_agent="reviews")
            assert saved["booking"]["rating"]["rating"]==9.3
            assert saved["booking"]["coverCandidate"]["order"]==1
            assert "booking" not in read_peer_evidence(runtime,"casa-a",skip_agent="booking")

    def test_unknown_rating_never_shared_as_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp)
            store_peer_evidence(runtime,"house-a","airbnb",{
                "otaProfiles":{"airbnb":{"status":"source_missing","rating":None}},
                "sharedKnowledge":{"propertyId":"different-house","coverCandidate":{"order":1}}
            })
            evidence=read_peer_evidence(runtime,"house-a")["airbnb"]
            assert "rating" not in evidence
            assert "coverCandidate" not in evidence

    def test_active_booking_dates_shared_without_changing_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime=Path(tmp)
            store_peer_evidence(runtime,"casa-a","booking",{
                "bookingReferenceStays":[{"requestedCheckin":"2027-08-01",
                    "requestedCheckout":"2027-08-04","checkin":"2027-09-26",
                    "checkout":"2027-09-29","adults":2}]
            })
            value=read_peer_evidence(runtime,"casa-a")["booking"]["bookingReferenceStays"][0]
            assert value["checkin"]=="2027-09-26"
            assert value["requestedCheckin"]=="2027-08-01"

    def test_bedzzle_booking_engine_domain(self):
        from booking_engine import detect_booking_engine
        result=detect_booking_engine(
            "https://example.org/",
            '<a href="https://booking.bedzzle.com/desktop/">Prenota</a>'
        )
        self.assertEqual(result["provider"], "Bedzzle")
        self.assertEqual(result["status"], "provider_identified")
        app=(ROOT/"src"/"App.tsx").read_text(encoding="utf-8")
        self.assertIn("host === 'booking.bedzzle.com'",app)
        self.assertIn("const provider = engine.provider || resolved?.provider",app)

    def test_stay_lock_no_shift_no_missing_guests(self):
        from velora_direct_stays import eligible_stays
        from datetime import date,timedelta
        checkin=(date.today()+timedelta(days=45)).isoformat()
        checkout=(date.today()+timedelta(days=48)).isoformat()
        rows=[
            {"status":"shifted_to_available_booking_dates","requestedCheckin":"2027-08-01",
             "requestedCheckout":"2027-08-04","checkin":checkin,"checkout":checkout,"adults":2},
            {"status":"initial_dates_available","requestedCheckin":checkin,
             "requestedCheckout":checkout,"checkin":checkin,"checkout":checkout,"adults":None},
            {"status":"initial_dates_available","requestedCheckin":checkin,
             "requestedCheckout":checkout,"checkin":checkin,"checkout":checkout,"adults":3}
        ]
        found=eligible_stays(rows)
        self.assertEqual(len(found),1)
        self.assertEqual(found[0]["guests"],3)
        self.assertEqual(found[0]["checkin"],checkin)
        self.assertEqual(found[0]["checkout"],checkout)

    def test_bedzzle_public_booking_key_is_preserved(self):
        from booking_engine import detect_booking_engine
        target="https://booking.bedzzle.com/desktop/?apikey=publicPropertyKey&lang=it&session=secret"
        engine=detect_booking_engine("https://example.org/",
            '<a href="'+target+'">Prenota</a>')
        self.assertEqual(engine["provider"],"Bedzzle")
        self.assertIn("apikey=publicPropertyKey",engine["url"])
        self.assertIn("lang=it",engine["url"])
        self.assertNotIn("session=",engine["url"])

    def test_direct_quotes_not_invented(self):
        import inspect
        from velora_direct_stays import probe_direct_stays
        source=inspect.getsource(probe_direct_stays)
        self.assertIn('"verifiedQuotes":[]',source)
        self.assertIn('visible_offer_candidates',source)

    def test_windows_updater_downloads_new_modules(self):
        script=(ROOT/"AGGIORNA_VELORA_COMPLETO.bat").read_text(encoding="utf-8")
        for filename in ("velora_direct_commercial.py","velora_direct_stays.py","velora_shared_intelligence.py"):
            assert "Scarico" in script
            assert filename+".new" in script
            assert 'move /Y "'+filename+'.new" "'+filename+'"' in script

    def test_ui_auto_imports_provider_without_manual_button(self):
        app=(ROOT/"src"/"App.tsx").read_text(encoding="utf-8")
        assert 'if (result.bookingEngine && (result.agentId==="official_site"' in app
        assert 'updateAnswer("audit-booking-engine-provider"' in app
        assert 'directBookingVerification:agentId==="official_site"' in app
        assert "Rating medio" in app
        assert ">Usa questo riscontro</button>" not in app

    def test_structured_results_keep_identity_and_never_fake_direct_rate(self):
        network=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")
        assert '"propertyId": data["id"]' in network
        assert '"peerBookingDates"' in network
        assert 'store_peer_evidence(property_file.parent' in network
        direct=(ROOT/"velora_direct_commercial.py").read_text(encoding="utf-8")
        assert '"datedPrices":[]' in direct
        assert '"availability":"not_verified"' in direct

if __name__=="__main__":
    unittest.main()
