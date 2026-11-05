"""Agoda room-grid regression guard: do not invent unavailable inventory."""
import ast
import unittest
from pathlib import Path

SOURCE=(Path(__file__).resolve().parents[1]/"browser_audit_pilot.py").read_text(encoding="utf-8")

class AgodaGridRegression(unittest.TestCase):
    def test_python_syntax(self):
        ast.parse(SOURCE)

    def test_room_grid_scroll_before_price_parsing(self):
        settle=SOURCE.split('elif channel == "agoda" and dates_confirmed:',1)[1].split(
            'elif channel in {"airbnb","vrbo"} and dates_confirmed:',1)[0]
        self.assertIn('scroll_into_view_if_needed',settle)
        self.assertIn('data-selenium="room-grid"',settle)
        self.assertIn('data-ppapi*="room-price"',settle)
        self.assertIn('snapshot_and_confirm()',settle)

    def test_sellout_not_inferred_from_generic_banner(self):
        start=SOURCE.index("explicit_sold_out=agoda_sold_out_message(body)")
        block=SOURCE[start:SOURCE.index('elif channel in {"airbnb","vrbo"}:',start)]
        self.assertIn('explicit_sold_out and eur_count==0 and room_count==0',block)
        self.assertIn('elif explicit_sold_out:',block)
        self.assertNotIn('status="no_public_rate"',block)
        self.assertIn('status="needs_human_review"',block)
        self.assertIn('non generare',block.lower())
        
    def test_parser_considers_offer_buttons_and_room_names(self):
        start=SOURCE.index("async def agoda_offer_row_candidates(")
        end=SOURCE.index("async def generic_ota_frontend_apply_dates(",start)
        parser=SOURCE[start:end]
        self.assertIn('prenota|book|reserve',parser)
        self.assertIn('roomRx=',parser)
        self.assertIn('priceRx=',parser)
        self.assertIn('wantedAdults',parser)

if __name__=="__main__":
    unittest.main()
