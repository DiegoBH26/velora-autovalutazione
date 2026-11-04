"""Booking must not become 'other property' when canonical title/URL/city agree.

These offline tests exercise the exact real identity function, without browser
access or scraping any site.
"""
import ast
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse

SOURCE=Path(__file__).resolve().parents[1]/"browser_audit_pilot.py"
TREE=ast.parse(SOURCE.read_text(encoding="utf-8"))
NODE=next(n for n in TREE.body if isinstance(n,ast.FunctionDef)
          and n.name=="_strict_ota_identity_match")

def norm(value):
    return " ".join(re.findall(r"[a-z0-9]+",str(value or "").lower()))

def low_score(*args):
    return 0.42,"tenuta specolizzi",0.41,0.41,"SEO fuzzy score low"

scope={
    "_classify_ota_url":lambda url:"booking" if urlparse(url).hostname in
       ("booking.com","www.booking.com") else "external",
    "_agoda_unit_listing_conflict":lambda *args:False,
    "_identity_match_score":low_score,
    "_norm_name":norm,
    "_name_similarity":lambda *args:0.41,
    "re":re,
    "urlparse":urlparse,
}
exec(compile(ast.Module(body=[NODE],type_ignores=[]),"booking-id-contract","exec"),scope)
match=scope["_strict_ota_identity_match"]


class BookingExactIdentityContract(unittest.TestCase):
    def test_specolizzi_same_listing_city_title_url(self):
        actual=match(
            "Masseria Tenuta Specolizzi","Salve","",
            "Tenuta Specolizzi - Booking.com",
            "Prenota la tua camera nella struttura a Salve, Italia.",
            "https://www.booking.com/hotel/it/tenuta-specolizzi.it.html",
        )
        self.assertTrue(actual["ok"],actual["evidence"])
        self.assertIn("Booking: titolo",actual["evidence"])

    def test_different_hotel_same_city_does_not_match(self):
        actual=match(
            "Masseria Tenuta Specolizzi","Salve","",
            "Masseria Tenuta Deserto La Roverella",
            "Camere a Salve.",
            "https://www.booking.com/hotel/it/tenuta-deserto.html",
        )
        self.assertFalse(actual["ok"])

    def test_no_city_proof_stays_unverified(self):
        actual=match(
            "Masseria Tenuta Specolizzi","Salve","",
            "Tenuta Specolizzi - Booking.com",
            "Camere in Puglia.",
            "https://www.booking.com/hotel/it/tenuta-specolizzi.it.html",
        )
        self.assertFalse(actual["ok"])

    def test_wrong_host_or_path_never_qualifies(self):
        for url in (
            "https://booking.com.evil.example/hotel/it/tenuta-specolizzi.it.html",
            "https://www.booking.com/hotel/it/tenuta-deserto.it.html",
            "https://www.booking.com/searchresults.html?ss=Tenuta+Specolizzi",
        ):
            with self.subTest(url=url):
                actual=match("Masseria Tenuta Specolizzi","Salve","",
                    "Tenuta Specolizzi - Booking.com","Camere a Salve.",url)
                self.assertFalse(actual["ok"])

if __name__=="__main__":
    unittest.main()
