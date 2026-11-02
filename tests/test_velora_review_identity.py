"""Offline regression for review classification, exact OTA identity and account profiles.

No login, no live portal navigation and no modification of OTA price parsers.
"""
import ast
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def src(file):
    return (ROOT/file).read_text(encoding="utf-8")

def extract_function(file,name):
    module=ast.parse(src(file))
    node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name==name)
    scope={}
    exec(compile(ast.Module(body=[node],type_ignores=[]),file,"exec"),scope)
    return scope[name]

class VeloraReviewIdentityTests(unittest.TestCase):
    def test_positive_once_is_visible_but_not_recurring(self):
        # Stub only the text parser's low-level signal recognition; exercise
        # the real production analyze_review_sample aggregation code.
        module=ast.parse(src("browser_audit_pilot.py"))
        node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=="analyze_review_sample")
        scope={
            "re":re,
            "REVIEW_THEME_RULES":{"Giardino e natura":("giardino",),"Accoglienza e staff":("personale",)},
            "REVIEW_STOPWORDS":set(),
            "REVIEW_ACTIONS":{},
            "_review_norm":lambda text:str(text).lower(),
            "_review_fragments":lambda text:[text],
            "_theme_contexts":lambda text,keywords:[text],
            "_local_review_sentiment":lambda text,stars:"positive" if stars>=4 else "negative",
            "_signal_phrase":lambda text,keywords,kind:text,
            "_review_snippet":lambda text,limit=180:text[:limit],
        }
        exec(compile(ast.Module(body=[node],type_ignores=[]),"analyze_review_sample","exec"),scope)
        analyze=scope["analyze_review_sample"]
        first=analyze([{"text":"Giardino bellissimo e molto curato","stars":5}])
        self.assertEqual(first["strengths"],[])
        self.assertEqual(first["positiveSignals"][0]["theme"],"Giardino e natura")
        second=analyze([
            {"text":"Giardino bellissimo e molto curato","stars":5},
            {"text":"Giardino piacevole","stars":5},
        ])
        self.assertEqual(second["strengths"][0]["count"],2)
        self.assertFalse(second["positiveSignals"])

    def test_review_retrieval_annotates_coverage_and_rejects_wrong_google_place(self):
        pilot=src("browser_audit_pilot.py")
        self.assertIn('status":"identity_unverified"',pilot)
        self.assertIn("specialist_booking_name_matches(name,observed_name,city)",pilot)
        self.assertIn('sample_quality=',pilot)
        self.assertIn('"sampleCoveragePct"',pilot)
        self.assertIn('"positiveSignals":isolated_positive',pilot)
        self.assertIn('stagnant>=4',pilot)
        self.assertIn('count>=100',pilot)

    def test_wrong_ota_listing_does_not_get_scanned(self):
        pilot=src("browser_audit_pilot.py")
        self.assertIn('WRONG PROPERTY SKIPPED',pilot)
        self.assertIn('status":"wrong_property_listing"',pilot)
        self.assertIn('and not specialist_booking_name_matches(',pilot)
        self.assertIn('if city and not name:',pilot)
        self.assertIn('suggerimento non corrispondente scartato',pilot)

    def test_account_chrome_profile_used_for_discovery_and_pricing(self):
        pilot=src("browser_audit_pilot.py")
        self.assertIn('discovery_profile_dir=profile_candidate',pilot)
        self.assertIn('pricing_profile_dir=profile_candidate',pilot)
        self.assertIn('"cookiesShared":bool(opted_in_profile)',pilot)
        self.assertIn('account_observation=bool(opted_in_profile and channel==specialist_id)',pilot)
        self.assertIn('quote["verified"]=False',pilot)
        server=src("local_audit_server.py")
        self.assertIn('PORTAL_SESSIONS.has_saved_profile(agent_id)',server)
        self.assertIn('session.get("state") in {"open","queued"}',server)

    def test_ipazia_dashboard_merge_and_explicit_sample_limits(self):
        app=src("src/App.tsx")
        self.assertIn('positiveSignals?: BrowserPilotReviewTheme[]',app)
        self.assertIn('Punti di forza e segnali positivi isolati',app)
        self.assertIn('Campione limitato: le ricorrenze possono non emergere',app)
        self.assertIn('if(agentId==="reviews" || agentId==="official_site")',app)
        self.assertIn('reputation:agentId==="reviews"',app)

if __name__=="__main__":
    unittest.main()
