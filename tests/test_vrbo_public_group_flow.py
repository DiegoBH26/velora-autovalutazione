"""Regression tests based on the public VRBO navigation screenshots (19 Oct 2026).

No live request, browser impersonation, captcha solving or old rate reuse.
"""
import ast
import asyncio
import json
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"browser_audit_pilot.py"

def load_function(name, dependencies):
    module=ast.parse(SOURCE.read_text(encoding="utf-8"),filename=str(SOURCE))
    node=next(x for x in module.body if isinstance(x,ast.AsyncFunctionDef if name.startswith("discover_vrbo") or name.startswith("vrbo_reveal") else ast.FunctionDef) and x.name==name)
    scope={"__file__":str(SOURCE),**dependencies}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),"exec"),scope)
    return scope[name]

class BrowserPage:
    def __init__(self): self.url="about:blank"; self.visits=[]; self.closed=False
    async def close(self): self.closed=True

class BrowserContext:
    def __init__(self): self.page=BrowserPage()
    async def new_page(self): return self.page

class VrboPublicGroupFlowTests(unittest.IsolatedAsyncioTestCase):
    def test_perla_user_source_is_candidate_not_rate_cache(self):
        fn=load_function("public_ota_source_hints",{
            "json":json,"Path":Path,"urlparse":urlparse,
            "_norm_name":lambda v:re.sub(r"[^a-z0-9 ]","",str(v).lower()),
            "normalize_ota_listing_url":lambda id,u:u,
            "_plausible_ota_listing_url":lambda id,u:id=="vrbo" and "/pdp/lo/" in u,
        })
        current={"name":"Perla Saracena Luxury Hotel & Restaurant",
                 "sources":{"sito":{"url":"https://www.perlasaracena.it/"}}}
        self.assertEqual(
            fn(current,"vrbo"),
            ["https://www.vrbo.com/it-it/pdp/lo/42693330"],
        )
        self.assertEqual(fn({**current,"name":"Another Hotel"},"vrbo"),[])
        self.assertEqual(fn({**current,"sources":{"sito":{"url":"https://otherhotel.it/"}}},"vrbo"),[])
        self.assertEqual(fn(current,"expedia"),[])

    async def test_grouped_pdp_precedes_single_unit_and_queries_group_first(self):
        context=BrowserContext()
        queries=[]
        group="https://www.vrbo.com/it-it/pdp/lo/42693330"
        unit="https://www.vrbo.com/11125202ha"
        async def search(page,query,engine):
            queries.append(query)
            return [
                {"href":unit,"text":"Hotel Perla Saracena - Camera Familiare","context":"Salve"},
                {"href":group,"text":"Perla Saracena Luxury Suites","context":"Salve"},
            ],""
        def score(name,city,address,label,snippet,url):
            return (0.95 if "/11125202ha" in url else 0.70,"",0.0,0.0,"name/city")
        fn=load_function("discover_vrbo_property_listings",{
            "asyncio":asyncio,"urlparse":urlparse,"_search_result_links":search,
            "_property_name_query_variants":lambda name:["perla saracena"],
            "_decode_search_target":lambda url:url,
            "_classify_ota_url":lambda url:"vrbo" if "vrbo.com" in url else "",
            "_plausible_ota_listing_url":lambda ch,url:"vrbo.com" in url,
            "_identity_match_score":score,"_name_similarity":lambda a,b:0.9,
            "normalize_ota_listing_url":lambda ch,url:url,
        })
        result=await fn(context,{"name":"Perla Saracena Luxury Hotel & Restaurant","city":"Salve"}, {})
        self.assertTrue(context.page.closed)
        self.assertEqual(result["listingUrls"][0],group)
        self.assertEqual(result["identityVerified"],False)
        self.assertIn("site:vrbo.com/it-it/pdp/lo/",queries[0])

    async def test_already_visible_rates_do_not_trigger_second_search(self):
        class Page:
            url="https://www.vrbo.com/it-it/pdp/lo/42693330"
        visited=[]
        async def quote(page,stay):
            return [{"roomType":"Appartamento Luxury","total":939}]
        async def submit(page,stay):
            visited.append("search")
            return "search"
        fn=load_function("vrbo_reveal_rates",{
            "vrbo_quote_candidates":quote,"vrbo_submit_search":submit,
        })
        detail=await fn(Page(),Page.url,{"nights":6})
        self.assertEqual(visited,[])
        self.assertIn("già visibili",detail)

if __name__=="__main__":
    unittest.main()
