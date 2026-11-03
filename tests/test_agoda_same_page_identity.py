"""Agoda same-page identity regression: no rate-parser changes or network calls."""
import ast
import re
import unicodedata
import unittest
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import urlparse

SRC=(Path(__file__).resolve().parents[1]/"browser_audit_pilot.py").read_text(encoding="utf-8")
TREE=ast.parse(SRC)
ns={"re":re,"unicodedata":unicodedata,"SequenceMatcher":SequenceMatcher,"urlparse":urlparse}
names={"GENERIC_NAME_WORDS","IDENTITY_GENERIC_NAME_WORDS","OTA_META"}
for node in TREE.body:
    if isinstance(node,ast.Assign) and any(
        isinstance(t,ast.Name) and t.id in names for t in node.targets
    ):
        exec(compile(ast.Module(body=[node],type_ignores=[]),"agoda-consts","exec"),ns)
for name in ("_norm_name","_name_similarity","_identity_match_score",
             "_agoda_unit_listing_conflict","_classify_ota_url",
             "_plausible_ota_listing_url","_strict_ota_identity_match"):
    fn=next(node for node in TREE.body
            if isinstance(node,ast.FunctionDef) and node.name==name)
    exec(compile(ast.Module(body=[fn],type_ignores=[]),"agoda-identity","exec"),ns)


class AgodaSamePageIdentity(unittest.TestCase):
    def test_correct_property_with_locality_is_verifiable(self):
        url="https://www.agoda.com/it-it/agriturismo-villa-casale/hotel/salve-it.html"
        self.assertTrue(ns["_plausible_ota_listing_url"]("agoda",url))
        result=ns["_strict_ota_identity_match"](
            "Agriturismo Villa Casale","Salve","","Agriturismo Villa Casale",
            "Agriturismo Villa Casale a Salve. Camere disponibili e piscina.",url
        )
        self.assertTrue(result["ok"],result["evidence"])

    def test_nearby_different_villa_is_rejected(self):
        url="https://www.agoda.com/it-it/agriturismo-villa-luisa/hotel/salve-it.html"
        result=ns["_strict_ota_identity_match"](
            "Agriturismo Villa Casale","Salve","","Agriturismo Villa Luisa",
            "Agriturismo Villa Luisa a Salve. Foto e tariffe disponibili.",url
        )
        self.assertFalse(result["ok"],result["evidence"])

    def test_generic_agoda_search_is_not_listing(self):
        self.assertFalse(ns["_plausible_ota_listing_url"](
            "agoda","https://www.agoda.com/it-it/search?city=Salve"
        ))

    def test_live_observation_promotes_verified_agoda_only(self):
        observe=next(node for node in TREE.body if isinstance(node,ast.AsyncFunctionDef)
                     and node.name=="observe")
        source=ast.get_source_segment(SRC,observe)
        self.assertIn('if channel=="agoda":',source)
        self.assertIn('record["identityCheck"]=',source)
        self.assertIn('record["sourceIdentityVerified"]=True',source)
        self.assertIn('identity=_strict_ota_identity_match(',source)
        self.assertIn('_plausible_ota_listing_url("agoda",url)',source)
        run=next(node for node in TREE.body if isinstance(node,ast.AsyncFunctionDef)
                 and node.name=="run")
        s=ast.get_source_segment(SRC,run)
        self.assertIn('channel in {"vrbo","holidu","agoda"}',s)
        self.assertIn('unverified_source_ids.discard(channel)',s)
        self.assertIn('"verification":"page_identity_lock"',s)


if __name__=="__main__":
    unittest.main()
