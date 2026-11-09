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
        from velora_direct_stays import _apply_dates_generic
        body=inspect.getsource(_apply_dates_generic)
        self.assertIn('visual=await _visual_date_values(scope)',body)
        self.assertIn('valid=all(_date_is_present(',body)
        self.assertIn('if not await _select_visual_calendar_date(scope,requested,path)',body)
        self.assertIn("Check-in e check-out 2027",body)
        helper=inspect.getsource(_visual_date_values)
        self.assertIn("fields={checkin:'',checkout:''}",helper)

    def test_real_official_homepage_prenota_pattern_maps_to_bedzzle(self):
        try:
            from booking_engine import detect_booking_engine
        except ModuleNotFoundError as exc:
            if exc.name=="selectolax":
                self.skipTest("selectolax assente nel runner: verifica DOM sul PC Windows")
            raise
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

    def test_bedzzle_uses_dedicated_date_boxes_before_generic_calendar(self):
        import inspect
        from unittest.mock import patch
        import velora_direct_stays as module
        body=inspect.getsource(module._apply_dates)
        self.assertIn('"booking.bedzzle.com" in str(getattr(scope,"url","")).lower()',body)
        self.assertIn('specialized=await _apply_bedzzle_dates(scope,stay)',body)
        self.assertIn('generic=await _apply_dates_generic(scope,stay)',body)
        navigation=inspect.getsource(module._bedzzle_navigate_calendar)
        self.assertIn("changeYear=year!==target.year",navigation)
        self.assertIn("previous=(year,month,state[\"kind\"]",navigation)
        self.assertIn("getUTCDay()+6",navigation)
        self.assertIn("data-velora-bedzzle-date",navigation)
        self.assertIn("cal.root",navigation)
        async def focus(scope,name):
            return {"found":True,"displayed":"09/11/2026"}
        async def select(scope,iso,trace):
            trace.append("Selezionato "+iso)
            return True
        async def display(scope):
            return {"checkin":"01/08/2027","checkout":"04/08/2027"}
        class Scope:
            url="https://booking.bedzzle.com/desktop/"
        stay={"checkin":"2027-08-01","checkout":"2027-08-04","guests":2}
        with patch.object(module,"_bedzzle_focus_box",focus), \
             patch.object(module,"_bedzzle_navigate_calendar",select), \
             patch.object(module,"_visual_date_values",display):
            applied=asyncio.run(module._apply_dates(Scope(),stay))
        self.assertTrue(applied["applied"])
        self.assertEqual(applied["method"],"bedzzle-calendar")
        self.assertEqual(applied["displayedDates"]["checkout"],"04/08/2027")
        async def unchanged(scope):
            return {"checkin":"09/11/2026","checkout":"11/11/2026"}
        with patch.object(module,"_bedzzle_focus_box",focus), \
             patch.object(module,"_bedzzle_navigate_calendar",select), \
             patch.object(module,"_visual_date_values",unchanged):
            rejected=asyncio.run(module._apply_dates(Scope(),stay))
        self.assertFalse(rejected["applied"])
        self.assertIn("non confermata",rejected["reason"])

    def test_bedzzle_calendar_javascript_is_valid_without_date_guesses(self):
        import ast
        import json
        import shutil
        import subprocess
        tree=ast.parse((ROOT/"velora_direct_stays.py").read_text(encoding="utf-8"))
        scripts=[n.value for n in ast.walk(tree)
                 if isinstance(n,ast.Constant) and isinstance(n.value,str)
                 and "data-velora-bedzzle-date" in n.value and "const MONTHS=" in n.value]
        self.assertEqual(len(scripts),1)
        script=scripts[0]
        self.assertNotIn("\x08",script)
        self.assertIn("const names=['Previous Month','Next Month','Previous Year','Next Year']",script)
        self.assertIn("data-velora-bedzzle-named-arrow",script)
        self.assertIn("mese/anno non leggibili",script)
        if shutil.which("node"):
            result=subprocess.run(["node","--check","-"],
              input="new Function("+json.dumps(script)+");",
              text=True,capture_output=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_empty_arrival_and_departure_boxes_supported(self):
        import inspect
        from velora_direct_stays import _bedzzle_focus_box,_wait_for_booking_search_form
        focus=inspect.getsource(_bedzzle_focus_box)
        self.assertIn("data\\s+(?:di\\s+)?arrivo",focus)
        self.assertIn("data\\s+(?:di\\s+)?partenza",focus)
        self.assertIn("input,button,[role=combobox]",focus)
        self.assertIn("Nessun campo",focus)
        self.assertNotIn("date.test(t)",focus)
        ready=inspect.getsource(_wait_for_booking_search_form)
        self.assertIn("checkin&&checkout",ready)
        self.assertIn("seconds=13",ready)

    def test_date_picker_fallback_traces_initial_failure(self):
        import inspect
        from velora_direct_stays import _apply_dates
        body=inspect.getsource(_apply_dates)
        self.assertIn("specialized=await _apply_bedzzle_dates(scope,stay)",body)
        self.assertIn("generic=await _apply_dates_generic(scope,stay)",body)
        self.assertIn('if specialized.get("namedControls"):',body)
        self.assertIn("bedzzle-plus-generic",body)

    def test_bedzzle_arrival_fields_javascript_and_italian_months(self):
        import ast,json,shutil,subprocess
        source=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
        tree=ast.parse(source)
        scripts=[node.value for node in ast.walk(tree)
                 if isinstance(node,ast.Constant) and isinstance(node.value,str)
                 and ("data-velora-bedzzle-focus" in node.value or
                      "const monthNames=['gennaio'" in node.value or
                      "Il booking engine si apre" in node.value)]
        self.assertGreaterEqual(len(scripts),2)
        for script in scripts:
            self.assertNotIn("\x08",script)
            if "document.querySelectorAll" in script and shutil.which("node"):
                check=subprocess.run(["node","--check","-"],
                    input="new Function("+json.dumps(script)+");",
                    capture_output=True,text=True,timeout=15)
                self.assertEqual(check.returncode,0,check.stderr)
        self.assertIn("const parsed=parseDate(t)",source)
        self.assertIn("data\\s+(?:di\\s+)?partenza",source)

    def test_bedzzle_exact_named_arrows_november_2027_to_august_2027(self):
        from unittest.mock import patch
        import velora_direct_stays as module
        class FakeControl:
            def __init__(self,scope,selector):
                self.scope=scope
                self.selector=selector
            async def count(self):return 1
            @property
            def first(self):return self
            async def click(self,timeout=0):
                if "data-velora-bedzzle-day" in self.selector:
                    self.scope.day_clicked=True
                    return
                name=self.selector.split('"')[1]
                self.scope.actions.append(name)
                if name=="previous-month":
                    self.scope.month-=1
                    if self.scope.month==0:
                        self.scope.year-=1
                        self.scope.month=12
                elif name=="next-month":
                    self.scope.month+=1
                    if self.scope.month==13:
                        self.scope.year+=1
                        self.scope.month=1
                elif name=="previous-year":self.scope.year-=1
                elif name=="next-year":self.scope.year+=1
        class FakeBedzzle:
            def __init__(self,year,month,stuck=False):
                self.year=year
                self.month=month
                self.day_clicked=False
                self.actions=[]
                self.stuck=stuck
            def locator(self,selector):
                control=FakeControl(self,selector)
                if self.stuck and 'data-velora-bedzzle-named-arrow' in selector:
                    async def no_click(timeout=0):
                        self.actions.append(selector.split('"')[1])
                    control.click=no_click
                return control
        async def header(scope):
            return {"ok":True,"year":scope.year,"month":scope.month,
                    "gridBounds":{"left":100,"right":450,"top":230,"bottom":460}}
        async def day(scope,iso,bounds):
            return {"found":True}
        with patch.object(module,"_bedzzle_named_calendar_state",header),\
             patch.object(module,"_bedzzle_named_calendar_day",day):
            bedzzle=FakeBedzzle(2027,11)
            trace=[]
            success=asyncio.run(module._bedzzle_navigate_calendar(
                bedzzle,"2027-08-01",trace))
            self.assertTrue(success)
            self.assertEqual(bedzzle.actions,
                             ["previous-month","previous-month","previous-month"])
            self.assertEqual((bedzzle.year,bedzzle.month),(2027,8))
            self.assertTrue(bedzzle.day_clicked)
            self.assertIn("Bedzzle: clic Previous Month da 11/2027",trace)
            from_2026=FakeBedzzle(2026,11)
            self.assertTrue(asyncio.run(module._bedzzle_navigate_calendar(
                from_2026,"2027-08-01",[])))
            self.assertEqual(from_2026.actions,
                ["next-year","previous-month","previous-month","previous-month"])
            stalled=FakeBedzzle(2027,11,stuck=True)
            stalled_trace=[]
            self.assertFalse(asyncio.run(module._bedzzle_navigate_calendar(
                stalled,"2027-08-01",stalled_trace)))
            self.assertTrue(any("non ha cambiato" in step for step in stalled_trace))

    def test_bedzzle_uses_weekday_column_for_august_first(self):
        from datetime import date
        self.assertEqual((date(2027,8,1).weekday(),date(2027,8,4).weekday()),
                         (6,2))
        source=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
        self.assertIn("const targetCol=(new Date(Date.UTC(",source)
        self.assertIn("data-velora-bedzzle-day",source)
        self.assertIn("Previous Month",source)

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
