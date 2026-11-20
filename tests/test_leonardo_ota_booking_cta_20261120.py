"""Leonardo must never confuse an official hotel's OTA CTA with its own booking engine."""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


class DirectCtaToOtaTests(unittest.TestCase):
    @staticmethod
    def detector():
        try:
            from booking_engine import detect_booking_engine
            return detect_booking_engine
        except ModuleNotFoundError as exc:
            if exc.name=="selectolax":
                raise unittest.SkipTest("selectolax non installato")
            raise

    def test_masseria_mancini_prenota_ora_to_booking(self):
        detector=self.detector()
        source="https://www.masseriamancini.it/boutique-hotel/"
        html=('''<html><a href="https://www.booking.com/hotel/it/masseria-mancini-polignano-a-mare.it.html">
                  Prenota ora</a></html>''')
        found=detector(source,html,source)
        self.assertEqual(found["status"],"ota_redirect")
        self.assertEqual(found["provider"],"")
        self.assertEqual(found["url"],"")
        self.assertEqual(found["otaName"],"Booking.com")
        self.assertEqual(found["otaSourcePage"],source)
        self.assertIn("booking.com/hotel",found["otaUrl"])

    def test_bookitbutton_is_also_booking_ota_not_bedzzle(self):
        detector=self.detector()
        html='<a href="https://bookitbutton.booking.com/hotel/it/demo.it.html?aid=4">Prenota ora</a>'
        out=detector("https://hotel.it",html)
        self.assertEqual(out["otaName"],"Booking.com")
        self.assertEqual(out["status"],"ota_redirect")

    def test_real_bedzzle_booking_engine_wins_over_ota(self):
        detector=self.detector()
        html='''<a href="https://www.booking.com/hotel/it/abc.html">Prenota ora</a>
        <a href="https://booking.bedzzle.com/desktop/?apikey=PUBLIC-DEMO">Prenota sul nostro sito</a>'''
        out=detector("https://hotel.it/",html)
        self.assertEqual(out["status"],"provider_identified")
        self.assertEqual(out["provider"],"Bedzzle")

    def test_kross_and_ermes_are_not_ota(self):
        detector=self.detector()
        for url,provider in [
            ("https://book.krossbooking.com/it/property/demo","Kross Booking"),
            ("https://book.ermeshotels.com/it/hotel/demo","ErmesHotels")]:
            with self.subTest(provider=provider):
                found=detector("https://hotel.it",'<a href="'+url+'">Prenota ora</a>')
                self.assertEqual(found["status"],"provider_identified")
                self.assertEqual(found["provider"],provider)

    def test_unrelated_booking_link_not_assumed_to_be_booking_cta(self):
        detector=self.detector()
        html='<footer><a href="https://www.booking.com">Booking.com</a></footer>'
        found=detector("https://hotel.it",html)
        self.assertNotEqual(found["status"],"ota_redirect")

    def test_other_otas_named_without_fabricating_direct_prices(self):
        detector=self.detector()
        for host,name in [("www.airbnb.com","Airbnb"),
                          ("www.expedia.com","Expedia"),("www.vrbo.com","Vrbo")]:
            with self.subTest(host=host):
                found=detector("https://hotel.it",
                    '<a href="https://'+host+'/rooms/example">Prenota ora</a>')
                self.assertEqual(found["status"],"ota_redirect")
                self.assertEqual(found["otaName"],name)

    def test_preflight_follows_real_hotel_dimora_page_link(self):
        # Masseria Mancini places "Prenota ora" on the boutique-hotel page,
        # not the homepage; the preflight must discover the linked page.
        from velora_direct_stays import _booking_discovery_pages
        links=[
            {"href":"/wedding/","text":"Wedding"},
            {"href":"/boutique-hotel/","text":"Hotel Dimora"},
            {"href":"/contatti/","text":"Contatti"},
            {"href":"https://www.booking.com/hotel/it/other.html","text":"Prenota ora"},
        ]
        found=_booking_discovery_pages("https://www.masseriamancini.it/",links)
        self.assertEqual(found,["https://www.masseriamancini.it/boutique-hotel/"])
        self.assertTrue(all("booking.com" not in item for item in found))

    def test_complete_preflight_visits_hotel_dimora_and_detects_booking(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import patch, AsyncMock
        try:
            from velora_direct_stays import discover_direct_engine
            import site_audit_builder
        except ModuleNotFoundError as exc:
            if exc.name in {"selectolax","playwright"}:
                self.skipTest("Optional browser-parser dependencies absent")
            raise
        visited=[]
        home="https://www.masseriamancini.it/"
        rooms=home+"boutique-hotel/"

        class FakePage:
            url=home
            async def goto(self,url,**kwargs):
                self.url=url
                visited.append(url)
                return SimpleNamespace(status=200)
            async def wait_for_timeout(self,delay):pass
            async def content(self):
                if self.url==home:
                    return '<a href="/boutique-hotel/">Hotel Dimora</a>'
                return '<a href="https://www.booking.com/hotel/it/masseria-mancini-polignano-a-mare.it.html">Prenota ora</a>'
            async def eval_on_selector_all(self,selector,script):
                return [{"href":"/boutique-hotel/","text":"Hotel Dimora"},
                        {"href":"/wedding/","text":"Wedding"}]

        class FakeContext:
            async def new_page(self):return FakePage()
            async def close(self):pass

        class FakeBrowser:
            async def new_context(self,**kwargs):return FakeContext()
            async def close(self):pass

        class FakeChromium:
            async def launch(self,**kwargs):return FakeBrowser()

        class FakePlaywright:
            async def __aenter__(self):return SimpleNamespace(chromium=FakeChromium())
            async def __aexit__(self,*args):pass

        with (patch("playwright.async_api.async_playwright",
                    return_value=FakePlaywright()),
              patch.object(site_audit_builder,"robots_allowed",return_value=True),
              patch.object(site_audit_builder,"dismiss_cookie",
                           new=AsyncMock(return_value=""))):
            result=asyncio.run(discover_direct_engine(home))
        self.assertEqual(visited,[home,rooms])
        self.assertEqual(result["status"],"ota_redirect")
        self.assertEqual(result["otaName"],"Booking.com")
        self.assertEqual(result["otaSourcePage"],rooms)
        self.assertEqual(result["url"],"")
        self.assertEqual(len(result["pagesInspected"]),2)

    def test_preflight_preserves_ota_result_for_later_site_audit(self):
        network=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")
        preflight=(ROOT/"velora_direct_stays.py").read_text(encoding="utf-8")
        self.assertIn("while index<len(pages) and index<=5:",preflight)
        self.assertIn("pages.extend(_booking_discovery_pages(page.url,links,max_pages=5))",preflight)
        self.assertIn('if (preflight_engine.get("status")=="ota_redirect"',network)
        self.assertIn('"otaName":preflight_engine.get("otaName") or ""',network)
        self.assertIn('"otaSourcePage":preflight_engine.get("otaSourcePage") or ""',network)
        self.assertIn('if engine_status=="ota_redirect":',network)

    def test_audit_crawls_hotel_pages_and_honors_ota_result(self):
        builder=(ROOT/"site_audit_builder.py").read_text(encoding="utf-8")
        self.assertIn('"boutique-hotel"',builder)
        self.assertIn('"ota_redirect":',builder)
        network=(ROOT/"velora_agent_network.py").read_text(encoding="utf-8")
        self.assertIn('if cta_verification.get("status")=="ota_redirect_verified":',network)
        self.assertIn('"ota_redirect_no_direct_engine"',network)
        self.assertIn('"bookingEngine": audit.get("bookingEngine") or {}',network)
        ast.parse(network)
        ast.parse((ROOT/"velora_direct_commercial.py").read_text(encoding="utf-8"))

    def test_report_and_ui_show_ota_and_traffic_in_same_scan(self):
        app=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        report=(ROOT/"src/frontend-consulting-report.ts").read_text(encoding="utf-8")
        self.assertIn("NESSUN BOOKING ENGINE DIRETTO RILEVATO",app)
        self.assertIn("Visite mensili stimate del sito diretto (Vaneform)",app)
        self.assertIn('bookingToOta=directStatus==="ota_redirect"',report)
        self.assertIn('Pulsante Prenota → ',report)


if __name__=="__main__":
    unittest.main()
