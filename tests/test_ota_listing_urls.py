"""Regression test for publicly discoverable OTA listing URLs.

Runs against the real URL predicates in browser_audit_pilot.py without needing
Playwright, Chrome, the local agent or paid search services.
Execute: python -m unittest discover -s tests -p "test_ota_listing_urls.py"
"""

import ast
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "browser_audit_pilot.py"


def load_real_url_predicates():
    module = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    meta = next(
        node.value for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "OTA_META" for t in node.targets)
    )
    required = {"_classify_ota_url", "_plausible_ota_listing_url"}
    functions = [
        node for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in required
    ]
    assert len(functions) == 2, "OTA URL functions missing from pilot"
    scope = {"OTA_META": ast.literal_eval(meta), "re": re, "urlparse": urlparse}
    extracted = ast.Module(body=functions, type_ignores=[])
    exec(compile(extracted, str(SOURCE), "exec"), scope)
    return scope["_classify_ota_url"], scope["_plausible_ota_listing_url"]


class OTAListingURLTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Python functions stored on the class become bound methods. Preserve
        # their original one-/two-argument signatures for these pure helpers.
        classify, plausible = load_real_url_predicates()
        cls.classify = staticmethod(classify)
        cls.plausible = staticmethod(plausible)

    def test_existing_airbnb_rooms_must_pass(self):
        for url in (
            "https://www.airbnb.it/rooms/50983754",
            "https://www.airbnb.it/rooms/858461556531097213",
            "https://www.airbnb.com/rooms/676640700783824471",
            "https://www.airbnb.it/rooms/37510992?check_in=2026-10-15&check_out=2026-10-18",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.classify(url), "airbnb")
                self.assertTrue(self.plausible("airbnb", url), url)

    def test_airbnb_search_is_not_a_listing(self):
        for url in (
            "https://www.airbnb.it/",
            "https://www.airbnb.it/s/Perla-Saracena/homes",
            "https://www.airbnb.it/experiences/1234567",
            "https://www.airbnb.it/rooms/not-an-id",
        ):
            with self.subTest(url=url):
                self.assertFalse(self.plausible("airbnb", url))

    def test_other_ota_numeric_listing_identifiers(self):
        urls = {
            "expedia": "https://www.expedia.it/Hotel-Example.h1234567.Informazioni-Hotel",
            "hotels": "https://it.hotels.com/ho123456",
            "vrbo": "https://www.vrbo.com/12345ha",
            "holidu": "https://www.holidu.it/d/1234567",
        }
        for ota_id, url in urls.items():
            with self.subTest(ota_id=ota_id):
                self.assertEqual(self.classify(url), ota_id)
                self.assertTrue(self.plausible(ota_id, url), url)

    def test_wrong_ota_is_rejected(self):
        url = "https://www.airbnb.it/rooms/50983754"
        self.assertFalse(self.plausible("vrbo", url))
        self.assertFalse(self.plausible("agoda", url))


if __name__ == "__main__":
    unittest.main()
