"""R6: result reading regressions using mocked browser frames."""
import unittest
from unittest.mock import patch

import velora_direct_stays as direct


class FakeFrame:
    def __init__(self, text, fields=None, url="https://engine.example/results"):
        self.url = url
        self.text = text
        self.fields = fields or ["2027-08-01", "2027-08-04"]
    def is_detached(self):
        return False
    async def evaluate(self, script):
        return {"text": self.text, "fields": self.fields,
                "url": self.url, "busy": False}


class FakePage:
    def __init__(self, frames):
        self.frames = frames


STAY = {"checkin": "2027-08-01", "checkout": "2027-08-04"}


class LeonardoR6ResultsTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_in_nested_frame(self):
        form = FakeFrame("Ricerca camere")
        result = FakeFrame("Camera Deluxe € 450")
        async def offers(frame):
            if frame is result:
                return [{"roomType": "Camera Deluxe", "displayedAmount": 450}]
            return []
        with patch.object(direct, "_visible_offer_candidates", side_effect=offers):
            state = await direct._read_booking_results(
                FakePage([form, result]), form, STAY, timeout_seconds=2)
        self.assertIs(state["frame"], result)
        self.assertTrue(state["resultsReady"])
        self.assertEqual(state["offers"][0]["displayedAmount"], 450)

    async def test_no_rates_does_not_mean_unavailable(self):
        frame = FakeFrame("Le migliori esperienze a partire da € 100")
        async def no_offers(frame):
            return []
        with patch.object(direct, "_visible_offer_candidates", side_effect=no_offers):
            state = await direct._read_booking_results(
                FakePage([frame]), frame, STAY, timeout_seconds=0.01)
        self.assertFalse(state["resultsReady"])
        self.assertFalse(state["emptyConfirmed"])

    async def test_explicit_unavailability(self):
        frame = FakeFrame("Non ci sono camere disponibili per le date indicate")
        async def no_offers(frame):
            return []
        with patch.object(direct, "_visible_offer_candidates", side_effect=no_offers):
            state = await direct._read_booking_results(
                FakePage([frame]), frame, STAY, timeout_seconds=2)
        self.assertTrue(state["resultsReady"])
        self.assertTrue(state["emptyConfirmed"])


if __name__ == "__main__":
    unittest.main()
