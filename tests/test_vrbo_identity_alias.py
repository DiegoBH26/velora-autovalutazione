"""Regressions for VRBO multi-unit property identity.
The title shown in screenshots is a public brand alias, NOT a different hotel.
No real OTA requests or stored rates are used.
"""
import ast
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse

SOURCE=Path(__file__).resolve().parents[1]/"browser_audit_pilot.py"

def identity_fn():
    tree=ast.parse(SOURCE.read_text(encoding="utf-8"),filename=str(SOURCE))
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="_strict_ota_identity_match")
    def normalize(value):
        words=re.findall(r"[a-z0-9]+",str(value or "").lower())
        return " ".join(w for w in words if w not in {
            "hotel","restaurant","luxury","suites","suite","&","resort",
            "spa","appartamenti","rooms","room",
        })
    # Reproduce the observed 62% rating to test the exact user failure,
    # retaining the real strict identity implementation being exercised.
    def score(*args):
        return 0.62,"42693330",0.54,0.0,"nome 54%"
    scope={
        "_agoda_unit_listing_conflict":lambda *args:False,
        "_identity_match_score":score,
        "_norm_name":normalize,
        "_name_similarity":lambda a,b:0.54,
        "_classify_ota_url":lambda url:"vrbo" if "vrbo.com" in url else "holidu",
        "urlparse":urlparse,"re":re,
    }
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(SOURCE),"exec"),scope)
    return scope["_strict_ota_identity_match"]

class VrboIdentityAliasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.identity=staticmethod(identity_fn())

    def test_known_vrbo_group_commercial_alias_passes_with_city(self):
        actual=self.identity(
            "Perla Saracena Luxury Hotel & Restaurant","Salve","",
            "Perla Saracena Luxury Suites",
            "Perla Saracena Luxury Suites casa intera a Salve Puglia",
            "https://www.vrbo.com/it-it/pdp/lo/42693330",
        )
        self.assertTrue(actual["ok"],actual["evidence"])
        self.assertIn("denominazione commerciale alternativa",actual["evidence"])

    def test_seo_title_with_exact_brand_words_passes(self):
        actual=self.identity(
            "Perla Saracena Luxury Hotel & Restaurant","Salve","",
            "Perla Saracena Luxury Suites - Nuove recensioni prezzi e offerte",
            "Scegli le date. Salve Puglia",
            "https://www.vrbo.com/it-it/pdp/lo/42693330",
        )
        self.assertTrue(actual["ok"],actual["evidence"])

    def test_other_brand_same_city_does_not_pass(self):
        actual=self.identity(
            "Perla Saracena Luxury Hotel & Restaurant","Salve","",
            "Villa Elena Luxury Suites","Salve Puglia",
            "https://www.vrbo.com/it-it/pdp/lo/42693330",
        )
        self.assertFalse(actual["ok"])

    def test_correct_brand_without_city_does_not_pass(self):
        actual=self.identity(
            "Perla Saracena Luxury Hotel & Restaurant","Salve","",
            "Perla Saracena Luxury Suites","Struttura a Ostuni",
            "https://www.vrbo.com/it-it/pdp/lo/42693330",
        )
        self.assertFalse(actual["ok"])

    def test_single_unit_not_accepted_by_group_rule(self):
        actual=self.identity(
            "Perla Saracena Luxury Hotel & Restaurant","Salve","",
            "Perla Saracena Luxury Suites","Salve Puglia",
            "https://www.vrbo.com/11125202ha",
        )
        self.assertFalse(actual["ok"])

if __name__=="__main__":
    unittest.main()
