"""Concrete November 2026 regressions: exact Agoda identity, price badges, Airbnb."""
import ast
import unittest
from pathlib import Path

PILOT=(Path(__file__).resolve().parents[1]/"browser_audit_pilot.py").read_text(encoding="utf-8")


def load_identity():
    tree=ast.parse(PILOT)
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
            and n.name=="_strict_ota_identity_match")
    import re
    from urllib.parse import urlparse
    import unicodedata
    # Use only these real helper functions from the same module, no browser/network.
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    import browser_audit_pilot as pilot
    return pilot._strict_ota_identity_match

class SpecolizziAgodaAirbnbRegressions(unittest.TestCase):
    def test_python_syntax(self):
        ast.parse(PILOT)

    def test_agoda_exact_title_url_presicce_salve_variant(self):
        match=load_identity()
        result=match(
            "Masseria Tenuta Specolizzi","Salve","",
            "Masseria Tenuta Specolizzi",
            "Masseria Tenuta Specolizzi Strada Provinciale 193 Presicce-Lido Marini",
            "https://www.agoda.com/it-it/tenuta-specolizzi_3/hotel/presicce-it.html"
        )
        self.assertTrue(result["ok"],result["evidence"])

    def test_agoda_does_not_approve_wrong_hotel(self):
        match=load_identity()
        result=match("Masseria Tenuta Specolizzi","Salve","","Masseria Tenuta Deserto",
            "Presicce Salve",
            "https://www.agoda.com/it-it/tenuta-deserto/hotel/presicce-it.html")
        self.assertFalse(result["ok"])

    def test_discount_badge_excluded_from_all_parsers(self):
        self.assertIn('discount|saving|coupon|badge|original-price|strike',PILOT)
        self.assertIn('applicato|applied|sconto|discount|risparmio|coupon',PILOT)
        self.assertIn('const isActualRate=el=>',PILOT)
        self.assertIn('priceEl.closest(\'del,s,strike',PILOT)

    def test_wrong_airbnb_id_not_reused_across_sessions(self):
        self.assertIn('rejection_path=output.parent/"airbnb-rejected-identities.json"',PILOT)
        self.assertIn('saved.get("propertyId")==data.get("id")',PILOT)
        self.assertIn('excluded=set(data.get("_runtimeRejectedAirbnbUrls") or [])',PILOT)
        self.assertIn('tmp_rejection.replace(rejection_path)',PILOT)
        self.assertIn('if normalize_ota_listing_url("airbnb",row[1]) not in excluded',PILOT)

if __name__=="__main__":
    unittest.main()
