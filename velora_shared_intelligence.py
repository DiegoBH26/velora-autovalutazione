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

def _folder(runtime: Path, property_id: str) -> Path:
    key=hashlib.sha256(str(property_id).encode("utf-8")).hexdigest()[:32]
    return Path(runtime) / ".velora-shared-evidence" / key

def read_peer_evidence(runtime: Path, property_id: str, *, skip_agent: str="") -> dict:
    folder=_folder(runtime, property_id)
    result={}
    now=datetime.now(timezone.utc)
    for path in folder.glob("*.json"):
        try:
            entry=json.loads(path.read_text(encoding="utf-8"))
            agent=entry.get("agent")
            if entry.get("schema")!=CACHE_SCHEMA or entry.get("propertyId")!=property_id:
                continue
            if not agent or agent==skip_agent or not isinstance(entry,dict):
                continue
            at=datetime.fromisoformat(str(entry["capturedAt"]).replace("Z","+00:00"))
            if at.tzinfo is None or now-at>MAX_AGE or at>now+timedelta(minutes=5):
                continue
        except (OSError, ValueError, KeyError, TypeError):
            continue
        result[agent]=entry
    return result

def store_peer_evidence(runtime: Path, property_id: str, agent: str, result: dict) -> None:
    if not agent.replace("_","").isalnum():
        raise ValueError("ID agente non valido")
    path=_folder(runtime,property_id) / (agent+".json")
    evidence={"schema":CACHE_SCHEMA,"propertyId":property_id,
              "capturedAt":datetime.now(timezone.utc).isoformat(),"agent":agent}
    if agent=="booking":
        evidence["bookingReferenceStays"]=[
            {k:item.get(k) for k in ("requestedCheckin","requestedCheckout","checkin","checkout","adults","status")}
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
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
    tmp.replace(path)
