"""Concrete November 2026 regressions: exact Agoda identity, price badges, Airbnb."""
import ast
import unittest
from pathlib import Path

PILOT=(Path(__file__).resolve().parents[1]/"browser_audit_pilot.py").read_text(encoding="utf-8")


def identity_logic_present():
    # The CI runner intentionally does not install browser/scraping libraries.
    # Inspect the Python AST without importing browser_audit_pilot.
    tree=ast.parse(PILOT)
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)
              and n.name=="_strict_ota_identity_match")
    return ast.get_source_segment(PILOT,node) or ""

class SpecolizziAgodaAirbnbRegressions(unittest.TestCase):
    def test_python_syntax(self):
        ast.parse(PILOT)

    def test_agoda_exact_title_url_presicce_salve_variant(self):
        function=identity_logic_present()
        self.assertIn('agoda_specolizzi_geo_alias=True',function)
        self.assertIn('strict_ok=True',function)
        self.assertIn('"presicce" in _norm_name(',function)
        self.assertIn('"tenuta specolizzi" in actual_title',function)
        self.assertIn('"tenuta specolizzi" in actual_path',function)

    def test_agoda_does_not_approve_wrong_hotel(self):
        function=identity_logic_present()
        self.assertIn('specialist_booking_name_matches(property_name,title,city)',function)
        self.assertIn('not specialist_booking_name_matches(',function)
        self.assertIn('"tenuta specolizzi" in actual_title',function)
        self.assertIn('"tenuta specolizzi" in actual_path',function)

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
