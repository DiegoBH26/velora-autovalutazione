"""Offline tests: Leonardo books no stay; selects search, reads visible prices."""
import asyncio
import unittest
from pathlib import Path
from velora_direct_stays import (
    _money,_PRICE_PATTERN,_date_renderings,
    _submit_availability_search,_visible_offer_candidates,
)
ROOT=Path(__file__).resolve().parents[1]

class Element:
    def __init__(self,label,hints):
        self.label,self.hints,self.clicked=label,hints,False
    async def evaluate(self,js):
        return self.hints if "getBoundingClientRect" in js else self.label
    async def is_enabled(self):
        return True
    async def click(self,timeout=0):
        self.clicked=True

class Controls:
    def __init__(self,values):
        self.values=values
    async def count(self):
        return len(self.values)
    def nth(self,n):
        return self.values[n]

class Scope:
    def __init__(self,values):
        self.values=values
    def locator(self,selector):
        return Controls(self.values)

class Results:
    async def evaluate(self,js):
        return [{"roomType":"Camera Deluxe","text":"Camera Deluxe € 240,00",
                 "hasBookingAction":True},
                {"roomType":"Suite","text":"Suite € 385,00",
                 "hasBookingAction":True}]

class TestLeonardoBookingFlow(unittest.TestCase):
    def test_price_reading_does_not_require_cancellation_policy(self):
        self.assertEqual(_money("€ 1.234,50"),1234.50)
        self.assertTrue(_PRICE_PATTERN.search("Camera EUR 240,00"))
        rows=asyncio.run(_visible_offer_candidates(Results()))
        self.assertEqual({r["roomType"] for r in rows},{"Camera Deluxe","Suite"})
        self.assertEqual({r["displayedAmount"] for r in rows},{240.0,385.0})

    def test_duplicate_menu_cta_is_not_the_search_button(self):
        menu=Element("VERIFICA DISPONIBILITÀ",
            {"y":100,"tag":"a","form":False,"inputs":0,"occupancy":False,
             "dates":False,"header":True})
        form=Element("VERIFICA DISPONIBILITÀ",
            {"y":740,"tag":"button","form":True,"inputs":4,"occupancy":True,
             "dates":True,"header":False})
        found=asyncio.run(_submit_availability_search(Scope([menu,form])))
        self.assertTrue(found["submitted"])
        self.assertTrue(form.clicked)
        self.assertFalse(menu.clicked)

    def test_browser_results_javascript_is_parseable(self):
        # Estrae la stringa JavaScript esatta dopo le escape di Python;
        # un \\b scritto male diventerebbe un carattere backspace.
        import ast
        import json
        import shutil
        import subprocess
        tree=ast.parse((ROOT/"velora_direct_stays.py").read_text(encoding="utf-8"))
        scripts=[n.value for n in ast.walk(tree)
                 if isinstance(n,ast.Constant) and isinstance(n.value,str)
                 and "const selectors=" in n.value and "roomType" in n.value]
        self.assertEqual(len(scripts),1)
        script=scripts[0]
        self.assertNotIn("\x08",script)
        self.assertIn("raw.split(/\\n+/)",script)
        if shutil.which("node"):
            js="new Function("+json.dumps(script)+");"
            proc=subprocess.run(["node","--check","-"],input=js,text=True,
                                capture_output=True,timeout=15)
            self.assertEqual(proc.returncode,0,proc.stderr)

    def test_calendar_supports_separate_and_combined_month_year(self):
        import ast
        source=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
        tree=ast.parse(source)
        scripts=[n.value for n in ast.walk(tree)
                 if isinstance(n,ast.Constant) and isinstance(n.value,str)
                 and "Calendario mensile non riconosciuto" in n.value]
        self.assertEqual(len(scripts),1)
        self.assertNotIn("\x08",scripts[0])
        self.assertIn("const combined=leaves.filter",scripts[0])
        self.assertIn("const year=Number",scripts[0])

    def test_engine_navigation_keeps_the_correct_structure(self):
        from velora_direct_stays import _engine_destination_matches
        expected="https://booking.bedzzle.com/desktop/?apikey=specolizzi-test&lang=it"
        self.assertTrue(_engine_destination_matches(
            "https://booking.bedzzle.com/desktop/?lang=it&apikey=specolizzi-test",expected))
        self.assertFalse(_engine_destination_matches(
            "https://booking.bedzzle.com/desktop/?apikey=another-hotel&lang=it",expected))
        self.assertFalse(_engine_destination_matches(
            "https://another-booking-platform.example/desktop/?apikey=specolizzi-test",expected))

    def test_leonardo_opens_from_site_and_reports_http_response(self):
        import inspect
        from velora_direct_stays import _navigate_booking_engine,probe_direct_stays
        helper=inspect.getsource(_navigate_booking_engine)
        self.assertIn("site_response=await page.goto(",helper)
        self.assertIn('await candidates[0][1].click',helper)
        self.assertIn('httpStatus=status',helper)
        runner=inspect.getsource(probe_direct_stays)
        self.assertIn('site_url=site_url',runner)
        self.assertIn('sample["navigation"]=navigation',runner)
        network=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")
        self.assertIn("ghost=ghost,site_url=site",network)

    def test_calendar_keeps_correct_year(self):
        self.assertIn("01/08/2027",_date_renderings("2027-08-01"))
        self.assertNotIn("01/08/2026",_date_renderings("2027-08-01"))

    def test_results_are_collected_only_after_search(self):
        s=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
        self.assertIn('if sample["searchSubmitted"] else []',s)
        self.assertIn('"observedRoomPrices"',s)
        self.assertIn('new_pages=[p for p in context.pages',s)
        self.assertIn('_select_visual_calendar_date(scope,value)',s)

if __name__=="__main__":
    unittest.main()
