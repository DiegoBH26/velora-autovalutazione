"""R10 regression: shared asymmetry semantics and generic booking-engine support."""
import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DIRECT=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
APP=(ROOT/"src"/"App.tsx").read_text(encoding="utf-8")


class UniversalDirectAndAsymmetryTests(unittest.TestCase):
    def test_python_parses(self):
        ast.parse(DIRECT)

    def test_provider_agnostic_date_and_cta_controls(self):
        self.assertIn("Provider-agnostic form strategy",DIRECT)
        self.assertIn("datafield:(e.getAttribute('data-field')",DIRECT)
        self.assertIn('anreise|ankunft|fecha.?entrada',DIRECT)
        self.assertIn('buscar(?: disponibilidad| habitaciones)?',DIRECT)
        self.assertIn('formatted=f"{m}/{d}/{y}"',DIRECT)
        self.assertIn('formatted=f"{y}-{m}-{d}"',DIRECT)
        self.assertIn('return await _apply_dates_generic(scope,stay)',DIRECT)

    def test_known_provider_retains_specialized_calendar(self):
        self.assertIn('_apply_bedzzle_dates(scope,stay)',DIRECT)

    def test_missing_listing_red_only_on_presence(self):
        self.assertIn('wrongOnly || explicitlyNotFound ? "missing"',APP)
        self.assertIn('const noComparableListing=presence==="missing";',APP)
        self.assertIn('const displayPhotosState=noComparableListing?"unverified"',APP)
        self.assertIn('const displayPriceState=noComparableListing?"unverified"',APP)

    def test_differences_without_verified_comparison_are_amber(self):
        self.assertIn('const photosState=photoDifference===null?"unverified":"candidate";',APP)
        self.assertIn('state==="candidate"||state==="blocked"?"bg-amber-400"',APP)

if __name__=="__main__":
    unittest.main()
