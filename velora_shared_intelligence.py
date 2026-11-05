"""Memoria interna di evidenze verificabili tra gli specialisti Velora.

Non contiene password, dati ospiti o screenshot. Una fonte non verificata non
può diventare attendibile solo perché un altro agente la ha osservata.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

CACHE_SCHEMA="velora-shared-evidence-v1"
MAX_AGE=timedelta(days=7)

def _path(runtime: Path, property_id: str) -> Path:
    key=hashlib.sha256(str(property_id).encode("utf-8")).hexdigest()[:32]
    return Path(runtime) / ".velora-shared-evidence" / (key+".json")

def _read(path: Path, property_id: str) -> dict:
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema")==CACHE_SCHEMA and data.get("propertyId")==property_id:
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {"schema":CACHE_SCHEMA,"propertyId":property_id,"agents":{}}

def read_peer_evidence(runtime: Path, property_id: str, *, skip_agent: str="") -> dict:
    data=_read(_path(runtime, property_id), property_id)
    result={}
    now=datetime.now(timezone.utc)
    for agent,entry in (data.get("agents") or {}).items():
        if agent==skip_agent or not isinstance(entry,dict):
            continue
        try:
            at=datetime.fromisoformat(str(entry["capturedAt"]).replace("Z","+00:00"))
            if at.tzinfo is None or now-at>MAX_AGE or at>now+timedelta(minutes=5):
                continue
        except (ValueError, KeyError, TypeError):
            continue
        result[agent]=entry
    return result

def store_peer_evidence(runtime: Path, property_id: str, agent: str, result: dict) -> None:
    path=_path(runtime,property_id)
    data=_read(path,property_id)
    evidence={"capturedAt":datetime.now(timezone.utc).isoformat(),"agent":agent}
    if agent=="booking":
        evidence["bookingReferenceStays"]=[
            {k:item.get(k) for k in ("requestedCheckin","requestedCheckout","checkin","checkout","adults")}
            for item in (result.get("bookingReferenceStays") or [])
            if item.get("checkin") and item.get("checkout")
        ][:80]
    if agent=="official_site":
        engine=result.get("bookingEngine") or {}
        evidence["bookingEngine"]={
            k:engine.get(k) for k in ("status","provider","url","mode","evidence")
        }
    profiles=result.get("otaProfiles") or {}
    if agent in profiles and isinstance(profiles[agent],dict):
        profile=profiles[agent]
        if profile.get("status")=="sampled" and profile.get("rating") is not None:
            evidence["rating"]={
                k:profile.get(k) for k in ("status","url","rating","ratingScale","reviewCount","evidence")
            }
    shared=result.get("sharedKnowledge") or {}
    if shared.get("propertyId")==property_id and not shared.get("listingIdentityQuarantined"):
        evidence["coverCandidate"]=shared.get("coverCandidate")
        evidence["mentionedAmenities"]=shared.get("mentionedAmenities") or []
    data.setdefault("agents",{})[agent]=evidence
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)
