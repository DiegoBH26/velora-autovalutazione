import unittest
from preventivi_crm_phase1 import discover_contact_channels, prepare_quote_draft

class TestPreventiviPhase1(unittest.TestCase):
    def test_form_detected_but_never_submitted(self):
        result=discover_contact_channels('<form action="/contact" method="post"><input name="email" required><input name="checkin"><button>Invia</button></form>', 'https://example.org/hotel')
        self.assertFalse(result["automaticSubmission"])
        self.assertEqual(result["channels"][0]["type"],"quote_or_contact_form")
        self.assertFalse(result["channels"][0]["submitAllowed"])

    def test_contact_and_engine_links(self):
        result=discover_contact_channels('<a href="mailto:info@example.org">Email</a><a href="/booking">Prenota ora</a>', 'https://example.org/')
        self.assertEqual([x["type"] for x in result["channels"]],["email_contact","booking_engine_candidate"])

    def test_identity_requires_explicit_authorization(self):
        with self.assertRaises(ValueError):
            prepare_quote_draft("Hotel","https://example.org",{"checkin":"2026-11-10","checkout":"2026-11-13","adults":2},"Mario","Rossi")

    def test_draft_is_not_approved_or_sent(self):
        draft=prepare_quote_draft("Hotel","https://example.org",{"checkin":"2026-11-10","checkout":"2026-11-13","adults":2},"Mario","Rossi",consent_to_use_identity=True)
        self.assertEqual(draft["requester"]["email"],"veloracon@gmail.com")
        self.assertFalse(draft["approved"])
        self.assertIsNone(draft["sentAt"])
        self.assertEqual(draft["status"],"draft_pending_manual_approval")
if __name__ == "__main__":
    unittest.main()
