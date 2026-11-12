"""Four OTA specialists: read-only, no-browser regression checks."""
import ast
import unittest
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlparse, urlunparse, urlencode

ROOT=Path(__file__).resolve().parents[1]
PILOT=(ROOT/"browser_audit_pilot.py").read_text(encoding="utf-8")
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")


class FourOtaSpecialistsContract(unittest.TestCase):
    def test_pilot_still_compiles(self):
        compile(PILOT,"browser_audit_pilot.py","exec")

    def test_date_url_keeps_requested_guest_count(self):
        module=ast.parse(PILOT)
        node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=="dated_url")
        code=compile(ast.Module(body=[node],type_ignores=[]),"<dated_url>","exec")
        env={
            "date":date,"urlparse":urlparse,"urlunparse":urlunparse,
            "parse_qsl":parse_qsl,"urlencode":urlencode,
            "DATE_URL_ADAPTERS":{"hotels","travelocity","trip","priceline"},
            "normalize_ota_listing_url":lambda channel,url:url,
        }
        exec(code,env)
        stay={"checkin":"2027-06-11","checkout":"2027-06-14",
              "nights":3,"adults":3}
        for channel,hostname in (("hotels","it.hotels.com"),
                                 ("travelocity","www.travelocity.com")):
            with self.subTest(channel=channel):
                url=env["dated_url"](channel,f"https://{hostname}/some-hotel",stay)
                query=dict(parse_qsl(urlparse(url).query))
                self.assertEqual(query["chkin"],stay["checkin"])
                self.assertEqual(query["chkout"],stay["checkout"])
                self.assertEqual(query["rm1"],"a3")
        url=env["dated_url"]("trip","https://it.trip.com/hotels/sample-hotel-detail-456",stay)
        query=dict(parse_qsl(urlparse(url).query))
        self.assertEqual(query["adult"],"3")
        self.assertEqual(query["checkIn"],stay["checkin"])
        self.assertEqual(query["checkOut"],stay["checkout"])
        # Priceline needs a real UI-confirmed date picker, never a forged URL.
        self.assertEqual(
            env["dated_url"]("priceline","https://www.priceline.com/relax/123",stay),
            "https://www.priceline.com/relax/123"
        )

    def test_date_checks_are_not_only_calendar_clicks(self):
        self.assertIn("async def specialist_ota_dom_dates_confirmed(",PILOT)
        self.assertIn("channel not in {\"hotels\",\"travelocity\",\"trip\",\"priceline\"}",PILOT)
        self.assertIn('if channel in {"agoda","hotels","travelocity","trip","priceline"}:',PILOT)
        self.assertIn('mode=f"{channel}-dom-fields+property-context"',PILOT)
        self.assertIn('f\'[role="gridcell"][aria-label*="{value}" i]\'',PILOT)
        self.assertIn('async def priceline_dom_dates_confirmed(',PILOT)

    def test_redirect_does_not_become_another_portal_price(self):
        self.assertIn('status="portal_redirect",finalUrl=page.url,quotes=[]',PILOT)
        self.assertIn('portal_redirect: "Reindirizzamento verso altro portale',APP)
        self.assertIn('"portal_redirect"}]',SERVER)
        self.assertIn('status="quote_candidates_unverified"',PILOT)


if __name__=="__main__":
    unittest.main()
