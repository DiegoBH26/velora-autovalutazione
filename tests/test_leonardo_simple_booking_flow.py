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
                 and "Nessun calendario con mese, anno e giorni visibili" in n.value]
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

    def test_calendar_moves_year_then_month_and_confirms_day(self):
        from velora_direct_stays import _select_visual_calendar_date
        class Clickable:
            def __init__(self,scope):
                self.scope=scope
            async def count(self):
                return 1
            @property
            def first(self):
                return self
            async def click(self,timeout=0):
                action=self.scope.action
                if action["action"]=="day":
                    self.scope.selected=True
                elif action["kind"]=="year":
                    self.scope.year+=1
                elif action["kind"]=="month":
                    self.scope.month-=1
        class Calendar:
            def __init__(self,stagnant=False):
                self.year=2026
                self.month=11
                self.action={}
                self.selected=False
                self.stagnant=stagnant
            async def evaluate(self,script,target):
                goal=target["year"]*12+target["month"]
                now=self.year*12+self.month
                action={"action":"day" if now==goal else "nav",
                        "currentMonth":self.month,"currentYear":self.year,
                        "kind":"year" if self.year!=target["year"] else "month",
                        "direction":"forward" if goal>now else "backward"}
                self.action=action
                return action
            def locator(self,selector):
                parent=self
                if self.stagnant:
                    class Still(Clickable):
                        async def click(self,timeout=0):
                            pass
                    return Still(parent)
                return Clickable(parent)
        calendar=Calendar()
        trace=[]
        selected=asyncio.run(_select_visual_calendar_date(calendar,"2027-08-01",trace))
        self.assertTrue(selected)
        self.assertTrue(calendar.selected)
        self.assertEqual((calendar.year,calendar.month),(2027,8))
        self.assertIn("Navigazione year 11/2026 forward",trace)
        self.assertIn("Navigazione month 11/2027 backward",trace)
        no_move=Calendar(stagnant=True)
        fail_trace=[]
        self.assertFalse(asyncio.run(
            _select_visual_calendar_date(no_move,"2027-08-01",fail_trace)))
        self.assertTrue(any("rimasto" in item for item in fail_trace))

    def test_displayed_dates_required_before_declaring_success(self):
        import inspect
        from velora_direct_stays import _apply_dates,_visual_date_values
        body=inspect.getsource(_apply_dates)
        self.assertIn('visual=await _visual_date_values(scope)',body)
        self.assertIn('valid=all(_date_is_present(',body)
        self.assertIn('if not await _select_visual_calendar_date(scope,requested,path)',body)
        self.assertIn("Check-in e check-out 2027",body)
        helper=inspect.getsource(_visual_date_values)
        self.assertIn("fields={checkin:'',checkout:''}",helper)

    def test_real_official_homepage_prenota_pattern_maps_to_bedzzle(self):
        from booking_engine import detect_booking_engine
        homepage="https://www.specolizzi.it/"
        engine="https://booking.bedzzle.com/desktop/?apikey=public-example&lang=it"
        html='<nav><a href="'+engine+'">Prenota</a></nav>'
        result=detect_booking_engine(homepage,html,homepage)
        self.assertEqual(result["status"],"provider_identified")
        self.assertEqual(result["provider"],"Bedzzle")
        self.assertIn("apikey=public-example",result["url"])
        self.assertIn("link dal sito",result["mode"])

    def test_leonardo_prioritizes_commercial_search_over_photo_tour(self):
        network=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")
        first=network.index('elif agent == "official_site":')
        relevant=network[first:network.index("else:  # reviews only",first)]
        self.assertLess(relevant.index("await discover_direct_engine(site)"),
                        relevant.index("await probe_direct_stays("))
        self.assertLess(relevant.index("await probe_direct_stays("),
                        relevant.index("await build_site_audit("))
        self.assertLess(relevant.index("await probe_direct_stays("),
                        relevant.index("pilot.frontend_photo_audit("))
        self.assertIn('if not int(direct_stays.get("searchedTotal") or 0):',relevant)
        self.assertIn('"status":"deferred_until_direct_search"',relevant)

    def test_header_prenota_is_scored_above_other_booking_links(self):
        import inspect
        from velora_direct_stays import _navigate_booking_engine,discover_direct_engine
        body=inspect.getsource(_navigate_booking_engine)
        self.assertIn('diagnostic["ctaCandidates"]=len(candidates)',body)
        self.assertIn('diagnostic["ctaLabel"]=candidates[0][2]',body)
        self.assertIn('await candidates[0][1].click',body)
        self.assertIn('ctaClicked=True',body)
        self.assertIn("Prenota del sito ufficiale",body)
        preflight=inspect.getsource(discover_direct_engine)
        self.assertIn("detect_booking_engine(page.url,await page.content(),page.url)",preflight)
        self.assertNotIn("frontend_photo_audit",preflight)

    def test_calendar_keeps_correct_year(self):
        self.assertIn("01/08/2027",_date_renderings("2027-08-01"))
        self.assertNotIn("01/08/2026",_date_renderings("2027-08-01"))

    def test_results_are_collected_only_after_search(self):
        s=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
        self.assertIn('if sample["searchSubmitted"] else []',s)
        self.assertIn('"observedRoomPrices"',s)
        self.assertIn('new_pages=[p for p in context.pages',s)
        self.assertIn('_select_visual_calendar_date(scope,requested,path)',s)

if __name__=="__main__":
    unittest.main()
