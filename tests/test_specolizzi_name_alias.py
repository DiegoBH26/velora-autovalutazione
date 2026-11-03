"""Exact name-alias regression: Tenuta Speculizzi/Specolizzi in Salve only.

Checks the real specialist Booking/OTA name guard without launching a browser.
"""
import ast
import re
import unicodedata
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
TREE=ast.parse(SOURCE)
scope={
    "re":re,
    "unicodedata":unicodedata,
    "IDENTITY_GENERIC_NAME_WORDS":{
        "hotel","aparthotel","resort","b&b","bb","bed","breakfast",
        "apartments","apartment","appartamenti","appartamento",
        "rooms","room","suite","suites","luxury","restaurant",
        "ristorante","boutique","spa","hotels","restaurants",
    },
}
for name in ("_norm_name", "specialist_booking_name_matches"):
    fn=next(n for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"identity-alias-test","exec"),scope)
matches=scope["specialist_booking_name_matches"]


class ExactSpecolizziAliasTests(unittest.TestCase):
    def test_site_expedia_spelling_for_same_salve_tenuta(self):
        self.assertTrue(matches("Tenuta Speculizzi","Tenuta Specolizzi","Salve"))
        self.assertTrue(matches("Tenuta Speculizzi","Masseria Tenuta Specolizzi","Salve"))
        self.assertTrue(matches("Tenuta Specolizzi","Masseria Tenuta Specolizzi","Salve"))

    def test_other_places_and_similar_names_remain_blocked(self):
        self.assertFalse(matches("Tenuta Speculizzi","Tenuta Specolizzi","Ostuni"))
        self.assertFalse(matches("Tenuta Speculizzi","Villa Specolizzi","Salve"))
        self.assertFalse(matches("Tenuta Speculizzi","Tenuta Specolizzi - Appartamento 3","Salve"))
        self.assertFalse(matches("Agriturismo Villa Casale","Agriturismo Villa Luisa","Salve"))
        self.assertFalse(matches("Tenuta Speculizzi","Tenuta Specola","Salve"))
        self.assertFalse(matches("Tenuta Speculizzi","Tenuta Specolizzi",""))

    def test_no_price_shortcuts_or_generic_fuzzy_allowlist(self):
        self.assertIn('official_specolizzi_alias',SOURCE)
        self.assertIn('if wrong_listing_name:',SOURCE)
        self.assertIn('WRONG PROPERTY SKIPPED',SOURCE)
        self.assertIn('_strict_ota_identity_match(',SOURCE)
        self.assertIn('if not source:',SOURCE)
        self.assertIn('record=describe_frontend_observation(channel,record)',SOURCE)


if __name__=="__main__":
    unittest.main()
