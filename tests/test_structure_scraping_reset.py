"""Regression: the OTA/site/reviews reset is property-scoped and preserves logins.

All tests use temporary folders. No Chrome or OTA websites are accessed.
"""
import ast
import json
import re
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
SERVER=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
APP=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
TREE=ast.parse(SERVER)
FUNCTION=next(node for node in TREE.body
              if isinstance(node,ast.FunctionDef) and node.name=="reset_property_runtime")


class PropertyScrapingReset(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.runtime=root/"runtime-properties"
        self.audit=root/"runtime-audits"
        self.pilot=root/"pilot-results"
        self.agents=root/"specialist-agents"
        self.logins=root/"portal-sessions"
        for folder in (self.runtime,self.audit,self.pilot,self.agents,self.logins):
            folder.mkdir()
        self.cache=root/"ota-source-cache.json"
        self.cache.write_text(json.dumps({
            "site:one.test":{"name":"Villa Casale","site":"https://one.test"},
            "site:other.test":{"name":"Villa Uno","site":"https://other.test"},
        }),encoding="utf-8")
        self.states=SimpleNamespace(
            state=SimpleNamespace(lock=threading.Lock(),running=False,
                                  property_id="villa-casale",error="",
                                  property_path=self.runtime/"villa-casale.json"),
            auto=SimpleNamespace(lock=threading.Lock(),running=False,
                                 property_id="villa-casale",error="",message="",result=None),
            agent_lock=threading.Lock(),
            vrbo_presence_lock=threading.Lock(),
            vrbo_presence_runs={},
            agent_runs={
                ("villa-casale","booking"):{"state":"completed"},
                ("another-villa","booking"):{"state":"completed"},
            }
        )
        def identity(value):
            sources=value.get("sources") or {}
            site=(sources.get("sito") or {}).get("url") or value.get("website") or ""
            host=(urlparse(site).hostname or "").lower()
            return "site:"+host if host else "name:"+str(value.get("name") or "").lower()
        ns={
            "Path":Path, "json":json, "shutil":shutil,
            "STATE":self.states.state, "AUTO_STATE":self.states.auto,
            "AGENT_RUN_LOCK":self.states.agent_lock, "AGENT_RUNS":self.states.agent_runs,
            "VRBO_PRESENCE_LOCK":self.states.vrbo_presence_lock,
            "VRBO_PRESENCE_RUNS":self.states.vrbo_presence_runs,
            "RUNTIME_PROPERTIES":self.runtime, "AGENT_RESULTS":self.agents,
            "safe_property_id":lambda value: value if re.fullmatch(r"[a-z0-9-]{1,80}",str(value)) else (_ for _ in ()).throw(ValueError("ID")),
            "runtime_property_path":lambda pid:self.runtime/(pid+".json"),
            "auto_audit_output_path":lambda pid:self.audit/(pid+".json"),
            "result_path":lambda pid:self.pilot/("dati_strutture_pilot_"+pid+".json"),
            "_identity_key":identity,
            "_read_ota_cache":lambda:json.loads(self.cache.read_text(encoding="utf-8")),
            "_write_ota_cache":lambda data:self.cache.write_text(json.dumps(data),encoding="utf-8"),
        }
        exec(compile(ast.Module(body=[FUNCTION],type_ignores=[]),"reset-contract","exec"),ns)
        self.reset=ns["reset_property_runtime"]
        self.property={
            "name":"Villa Casale",
            "sources":{"sito":{"label":"Sito ufficiale","url":"https://one.test"}},
        }
        self.other={
            "name":"Villa Uno",
            "sources":{"sito":{"label":"Sito ufficiale","url":"https://other.test"}},
        }
        (self.runtime/"villa-casale.json").write_text(json.dumps(self.property),encoding="utf-8")
        (self.runtime/"another-villa.json").write_text(json.dumps(self.other),encoding="utf-8")
        for pid in ("villa-casale","another-villa"):
            (self.audit/(pid+".json")).write_text("{}",encoding="utf-8")
            (self.pilot/("dati_strutture_pilot_"+pid+".json")).write_text("{}",encoding="utf-8")
            folder=self.agents/pid/"booking"
            folder.mkdir(parents=True)
            (folder/"result.json").write_text("{}",encoding="utf-8")
        session=self.logins/"expedia"/"chrome-profile"
        session.mkdir(parents=True)
        (session/"Preferences").write_text("still logged in profile",encoding="utf-8")

    def test_reset_removes_only_selected_scraping_and_keeps_login(self):
        result=self.reset({"propertyId":"villa-casale","name":"Villa Casale",
                           "website":"https://one.test"})
        self.assertTrue(result["ok"])
        self.assertTrue(result["agentRunsReset"])
        self.assertTrue(result["portalLoginProfilesPreserved"])
        self.assertFalse((self.runtime/"villa-casale.json").exists())
        self.assertFalse((self.audit/"villa-casale.json").exists())
        self.assertFalse((self.pilot/"dati_strutture_pilot_villa-casale.json").exists())
        self.assertFalse((self.agents/"villa-casale").exists())
        self.assertTrue((self.agents/"another-villa"/"booking"/"result.json").exists())
        self.assertTrue((self.runtime/"another-villa.json").exists())
        self.assertTrue((self.logins/"expedia"/"chrome-profile"/"Preferences").exists())
        self.assertNotIn(("villa-casale","booking"),self.states.agent_runs)
        self.assertIn(("another-villa","booking"),self.states.agent_runs)
        cache=json.loads(self.cache.read_text(encoding="utf-8"))
        self.assertNotIn("site:one.test",cache)
        self.assertIn("site:other.test",cache)

    def test_active_specialist_prevents_partial_deletion(self):
        self.states.agent_runs[("villa-casale","expedia")]={"state":"running"}
        with self.assertRaisesRegex(RuntimeError,"Attendi"):
            self.reset({"propertyId":"villa-casale","website":"https://one.test"})
        self.assertTrue((self.agents/"villa-casale"/"booking"/"result.json").exists())
        self.assertTrue((self.runtime/"villa-casale.json").exists())

    def test_active_vrbo_presence_prevents_reset(self):
        self.states.vrbo_presence_runs["villa-casale"]={"state":"running"}
        with self.assertRaisesRegex(RuntimeError,"Attendi"):
            self.reset({"propertyId":"villa-casale","website":"https://one.test"})
        self.assertTrue((self.agents/"villa-casale"/"booking"/"result.json").exists())

    def test_shared_cache_is_preserved_for_other_property(self):
        (self.runtime/"another-villa.json").write_text(json.dumps(self.property),encoding="utf-8")
        outcome=self.reset({"propertyId":"villa-casale"})
        self.assertTrue(outcome["sharedCachePreserved"])
        self.assertIn("site:one.test",json.loads(self.cache.read_text(encoding="utf-8")))

    def test_frontend_uses_server_reset_and_keeps_interview(self):
        self.assertIn('localAgentUrl("/api/scraping/reset")',APP)
        self.assertIn('resetCurrentStructureScraping()',APP)
        self.assertIn('Reset scraping OTA, sito e recensioni',APP)
        self.assertIn('!key.startsWith("audit-")',APP)
        self.assertIn('auditData:blankAuditDataForStructure(',APP)
        self.assertIn('window.localStorage.removeItem("velora-browser-pilot:"+propertyId)',APP)
        self.assertIn('setSpecialistChecks(null)',APP)
        self.assertIn('setFrontendComparisons([])',APP)
        self.assertIn('"/api/scraping/reset"',SERVER)


if __name__=="__main__":
    unittest.main()
