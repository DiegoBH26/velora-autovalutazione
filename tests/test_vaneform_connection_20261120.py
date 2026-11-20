"""Vaneform diagnostic API is free and never reveals an API secret."""
import ast
import json
import unittest
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import patch

from velora_site_traffic import check_vaneform_connection, collect_site_traffic

ROOT=Path(__file__).resolve().parents[1]


def failed(url,status,code):
    payload=json.dumps({"error":{"code":code,"message":"not authorized"}}).encode()
    return HTTPError(url,status,"failure",{},BytesIO(payload))


class VaneformChecks(unittest.TestCase):
    def test_account_check_is_free_and_never_outputs_key(self):
        calls=[]
        key="vf_live_FAKE_PRIVATE_API_KEY"
        def api(url,supplied):
            calls.append(url)
            self.assertEqual(supplied,key)
            return {"plan":"free","credits":{"remaining":98},"other_secret":key}
        result=check_vaneform_connection(api_key=key,fetch=api)
        self.assertEqual(calls,["https://vaneform.com/api/v1/account"])
        self.assertEqual(result["status"],"connected")
        self.assertEqual(result["creditsRemaining"],98)
        self.assertNotIn(key,json.dumps(result))

    def test_no_key_and_placeholder_are_different(self):
        with patch.dict("os.environ",{},clear=True):
            self.assertEqual(check_vaneform_connection()["status"],"not_configured")
        self.assertEqual(check_vaneform_connection(api_key="INCOLLA_QUI_LA_TUA_CHIAVE")["status"],"invalid_format")

    def test_key_unauthorized_or_replaced_are_distinct(self):
        key="vf_live_FAKE_PRIVATE_API_KEY"
        for code,expected in [("unauthorized","unauthorized"),("invalid_api_key","invalid_key")]:
            with self.subTest(code=code):
                def reject(url,secret):
                    raise failed(url,401,code)
                result=check_vaneform_connection(api_key=key,fetch=reject)
                self.assertEqual(result["status"],expected)

    def test_traffic_lookup_propagates_real_error_code(self):
        key="vf_live_FAKE_PRIVATE_API_KEY"
        def reject(url,secret):
            raise failed(url,401,"invalid_api_key")
        res=collect_site_traffic("https://masseriamancini.it",api_key=key,fetch=reject)
        self.assertEqual(res["status"],"invalid_key")
        self.assertIsNone(res["wholeSiteVisits"])

    def test_safe_web_endpoint_and_traffic_only_refresh(self):
        server=(ROOT/"local_audit_server.py").read_text(encoding="utf-8")
        frontend=(ROOT/"src/App.tsx").read_text(encoding="utf-8")
        ast.parse(server)
        self.assertIn('route=="/api/traffic/account"',server)
        self.assertIn('"/api/traffic/refresh"',server)
        self.assertIn('self.headers.get("X-Velora-Local-Token")!=STATE.token',server)
        self.assertIn('site=str(official.get("url") or data.get("website")',server)
        self.assertIn('previous["siteTraffic"]=traffic',server)
        self.assertIn("Verifica collegamento Vaneform · 0 crediti",frontend)
        self.assertIn("Rileva solo visite · senza rifare Leonardo",frontend)
        self.assertIn('setTrafficLatest({propertyId:activeAuditData.id,siteTraffic})',frontend)

if __name__=="__main__":
    unittest.main()
