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

    def test_windows_updater_downloads_new_modules(self):
        script=(ROOT/"AGGIORNA_VELORA_COMPLETO.bat").read_text(encoding="utf-8")
        for filename in ("velora_direct_commercial.py","velora_shared_intelligence.py"):
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
