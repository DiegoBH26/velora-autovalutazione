"""Regression for Leonardo -> UI and safe OTA specialist evidence reuse."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from velora_shared_intelligence import read_peer_evidence, store_peer_evidence

ROOT=Path(__file__).resolve().parents[1]

def booking_url_helpers():
    # Test public URL/provider decisions without requiring HTML parser packages
    # on the lightweight GitHub Pages build runner.
    import ast
    from urllib.parse import urljoin, urlparse, urlunparse, parse_qsl, urlencode
    source=(ROOT/"booking_engine.py").read_text(encoding="utf-8")
    tree=ast.parse(source)
    selected=[node for node in tree.body
              if isinstance(node,ast.FunctionDef)
              and node.name in {"_public_url","_provider"}]
    scope={"urljoin":urljoin,"urlparse":urlparse,"urlunparse":urlunparse,
           "parse_qsl":parse_qsl,"urlencode":urlencode}
    exec(compile(ast.Module(body=selected,type_ignores=[]),
                 str(ROOT/"booking_engine.py"),"exec"),scope)
    return scope["_public_url"],scope["_provider"]

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
        public_url,provider=booking_url_helpers()
        target=public_url("https://booking.bedzzle.com/desktop/","https://example.org/")
        self.assertEqual(provider("booking.bedzzle.com"),"Bedzzle")
        self.assertEqual(target,"https://booking.bedzzle.com/desktop/")
        app=(ROOT/"src"/"App.tsx").read_text(encoding="utf-8")
        self.assertIn("host === 'booking.bedzzle.com'",app)
        self.assertIn("const provider = engine.provider || resolved?.provider",app)

    def test_stay_lock_uses_booking_confirmed_shift_and_never_invents_guests(self):
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
        self.assertEqual(len(found),2)
        self.assertEqual({stay["guests"] for stay in found},{2,3})
        self.assertTrue(all(stay["checkin"]==checkin and stay["checkout"]==checkout for stay in found))
        self.assertTrue(any(stay["bookingConfirmation"]=="shifted_to_available_booking_dates" for stay in found))

    def test_leonardo_uses_reused_minerva_reference_and_no_preflight_gate(self):
        from velora_direct_stays import eligible_stays
        from datetime import date,timedelta
        first=(date.today()+timedelta(days=30)).isoformat()
        last=(date.today()+timedelta(days=33)).isoformat()
        dates=eligible_stays([{
            "status":"reused_minerva_lock", "checkin":first, "checkout":last,
            "requestedCheckin":first, "requestedCheckout":last, "adults":2
        }])
        self.assertEqual([(row["checkin"],row["checkout"],row["guests"]) for row in dates],
                         [(first,last,2)])
        source=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")
        self.assertIn('if booking_url:',source)
        self.assertNotIn('if (direct_verification.get("navigation")=="reached"',source)
        self.assertIn('"peerBookingDates": booking_windows',source)

    def test_bedzzle_public_booking_key_is_preserved(self):
        public_url,provider=booking_url_helpers()
        target="https://booking.bedzzle.com/desktop/?apikey=publicPropertyKey&lang=it&session=secret"
        resolved=public_url(target,"https://example.org/")
        self.assertEqual(provider("booking.bedzzle.com"),"Bedzzle")
        self.assertIn("apikey=publicPropertyKey",resolved)
        self.assertIn("lang=it",resolved)
        self.assertNotIn("session=",resolved)

    def test_direct_quotes_not_invented(self):
        import inspect
        from velora_direct_stays import probe_direct_stays
        source=inspect.getsource(probe_direct_stays)
        self.assertIn('"verifiedQuotes":[]',source)
        self.assertIn('visible_offer_candidates',source)

    def test_direct_first_date_search_without_booking_run(self):
        from datetime import date,timedelta
        from velora_direct_stays import planned_direct_stays,eligible_stays
        first=(date.today()+timedelta(days=50)).isoformat()
        last=(date.today()+timedelta(days=53)).isoformat()
        plan=[{"checkin":first,"checkout":last,"adults":2,"nights":3}]
        direct=planned_direct_stays(plan)
        self.assertEqual(direct[0]["status"],"direct_master_requested")
        self.assertEqual(direct[0]["source"],"direct_initial_plan")
        eligible=eligible_stays(direct)
        self.assertEqual([(stay["checkin"],stay["checkout"],stay["guests"]) for stay in eligible],
                         [(first,last,2)])

    def test_leonardo_first_and_explicit_engine_absence(self):
        network=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")
        app=(ROOT/"src"/"App.tsx").read_text(encoding="utf-8")
        self.assertIn('AGENTS = {\\n    "official_site"',network)
        self.assertIn('"status":"website_not_configured"',network)
        self.assertIn('"booking_engine_not_found" if engine_status=="not_found_in_page"',network)
        self.assertIn('pilot.custom_date_plan(today, custom_period)',network)
        self.assertIn('planned_direct_stays(plan,limit=direct_limit)',network)
        self.assertIn('direct_windows,limit=len(direct_windows) or 1',network)
        batch=app.index('async function launchAgentBatch(')
        self.assertLess(app.index('await startSpecialistAgent("official_site"',batch),
                        app.index('await startSpecialistAgent("booking"',batch))
        agents=app.index('const SPECIALIST_AGENTS:')
        self.assertLess(app.index('{id:"official_site"',agents),
                        app.index('{id:"booking"',agents))
        self.assertIn('directRoomParityFor',app)
        self.assertIn('6 · Camere / Sito diretto',app)
        self.assertIn('Perché Leonardo non è riuscito a cercare',app)

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
