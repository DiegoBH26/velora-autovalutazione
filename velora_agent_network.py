"""Velora specialist agents - isolated jobs reusing the verified legacy adapters.

No account creation, challenge bypass, aggressive retries, or credentials are
handled by this module. Each OTA worker uses its own Chrome profile and output.
The validator is read-only and runs solely on an explicit user request.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import browser_audit_pilot as pilot
from site_audit_builder import build_site_audit
from playwright.async_api import async_playwright

NETWORK_SCHEMA = "velora-specialist-network-v1"
REVIEWER_NAME = "Giove"
AGENTS = {
    "booking": {"name": "Minerva", "label": "Booking.com", "kind": "ota", "channel": "booking", "ready": True, "knowledge": "identità, date, camere, disponibilità, tariffe verificabili"},
    "agoda": {"name": "Galileo", "label": "Agoda", "kind": "ota", "channel": "agoda", "ready": True, "knowledge": "scheda hotel, date, candidate tariffarie, base prezzo"},
    "airbnb": {"name": "Apollo", "label": "Airbnb", "kind": "ota", "channel": "airbnb", "ready": True, "knowledge": "annunci multipli, identità, date e preventivi pubblici"},
    "expedia": {"name": "Ercole", "label": "Expedia", "kind": "ota", "channel": "expedia", "ready": True, "beta": True, "knowledge": "adapter pubblico storico; può essere bloccato"},
    "vrbo": {"name": "Atlante", "label": "Vrbo", "kind": "ota", "channel": "vrbo", "ready": True, "beta": True, "knowledge": "adapter pubblico storico; limita tentativi quando HTTP 429"},
    "holidu": {"name": "Mercurio", "label": "Holidu", "kind": "ota", "channel": "holidu", "ready": True, "beta": True, "knowledge": "adapter pubblico storico; registra redirect e assenza pagina propria"},
    "hotels": {"name": "Tesla", "label": "Hotels.com", "kind": "ota", "channel": "hotels", "ready": True, "beta": True, "knowledge": "adapter pubblico del pilot, controlli di identità e tariffe"},
    "travelocity": {"name": "Newton", "label": "Travelocity", "kind": "ota", "channel": "travelocity", "ready": True, "beta": True, "knowledge": "adapter pubblico del pilot, controllo redirect Expedia"},
    "trip": {"name": "Turing", "label": "Trip.com", "kind": "ota", "channel": "trip", "ready": True, "beta": True, "knowledge": "adapter pubblico del pilot; login richiesto se la pagina lo mostra"},
    "priceline": {"name": "Pitagora", "label": "Priceline", "kind": "ota", "channel": "priceline", "ready": True, "beta": True, "knowledge": "adapter pubblico del pilot, rilevazioni tariffarie da verificare"},
    "official_site": {"name": "Leonardo", "label": "Sito ufficiale", "kind": "site", "ready": True, "knowledge": "navigazione, contenuti, conversione, immagini e asimmetrie"},
    "reviews": {"name": "Ipazia", "label": "Recensioni", "kind": "reviews", "ready": True, "knowledge": "campioni recensioni, temi ricorrenti, reputazione Google"},
}
# Reserved names only. These agents have NOT been implemented or enabled.
FUTURE_AGENTS = {
    "tripadvisor": {"name": "Socrate", "label": "Tripadvisor"},
    "trivago": {"name": "Keplero", "label": "Trivago"},
    "googlehotels": {"name": "Euclide", "label": "Google Hotels"},
    "holidaycheck": {"name": "Archimede", "label": "HolidayCheck"},
}

def agent_display(agent_id: str) -> str:
    entry = AGENTS.get(agent_id) or FUTURE_AGENTS.get(agent_id)
    return f"{entry['name']} ({entry['label']})" if entry else agent_id

def validation_rows(report: dict) -> list[dict]:
    """Consistent, structured Giove check rows for CMD and UI."""
    rows = []
    for check in report.get("checks") or []:
        agent = check.get("agentId", "")
        rows.append({
            "agentId": agent, "agentName": agent_display(agent),
            "check": check.get("label", ""),
            "status": "VALIDATO" if check.get("passed") else "ERRORE",
            "details": check.get("detail", ""),
        })
    return rows

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _safe_result(value: dict, expected_id: str, agent: str) -> dict:
    result = dict(value)
    result["agentId"] = agent
    result["agentName"] = agent_display(agent)
    result["networkSchema"] = NETWORK_SCHEMA
    if result.get("propertyId") not in (None, expected_id):
        raise ValueError("Risultato ricevuto da un’altra struttura")
    result["propertyId"] = expected_id
    result["completedAt"] = _now()
    return result

def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

async def execute(agent: str, data: dict, property_file: Path, output: Path,
                  *, months: int = 1, custom_period: dict | None = None,
                  ghost: bool = False, assisted: bool = False,
                  assist_callback=None) -> dict:
    """Run an independently scoped specialist. Legacy parsers remain unchanged."""
    if agent not in AGENTS or not AGENTS[agent]["ready"]:
        raise ValueError("Agente non disponibile")
    if AGENTS[agent]["kind"] == "ota":
        args = argparse.Namespace(
            property=str(property_file), output=str(output), channels=agent,
            months=months, today=None, dry_run=False, ghost=ghost,
            assisted=assisted, assist_callback=assist_callback if assisted else None,
            pricing_only=True, custom_period=custom_period,
            agent_id=agent,
        )
        raw = await pilot.run(args)
        result = _safe_result(raw, data["id"], agent)
    elif agent == "official_site":
        site = data.get("website") or (data.get("sources", {}).get("sito") or {}).get("url")
        if not site:
            raise ValueError("Sito ufficiale non configurato")
        audit = await build_site_audit({
            "website": site,
            "name": data.get("name", ""),
            "city": data.get("city", ""),
            "province": data.get("province", ""),
            "rooms": str(data.get("rooms") or ""),
            "propertyType": data.get("propertyType", "Struttura ricettiva"),
        })
        # Recupera il collaudato audit fotografico multi-pagina, non un parser nuovo.
        profile = property_file.parent / "chrome-photos"
        picture_data={**data,"sources":{**(data.get("sources") or {}),
            "sito":{"label":"Sito ufficiale","url":site}}}
        async with async_playwright() as playwright:
            context=await pilot._launch_velora_context(playwright,profile,picture_data,"foto sito diretto",ghost)
            try:
                photos=await pilot.frontend_photo_audit(context,picture_data,{})
            finally:
                await context.close()
        result = _safe_result({
            "schema": NETWORK_SCHEMA, "auditData": audit,"photoAudit": photos,
            "evidence": "Audit navigazione sito + foto multi-pagina; nessuna tariffa OTA.",
        }, data["id"], agent)
    else:  # reviews only
        profile = property_file.parent / "chrome-reviews"
        async with async_playwright() as playwright:
            context = await pilot._launch_velora_context(playwright, profile, data, "recensioni", ghost)
            try:
                google = await pilot.google_reputation_observation(context, data)
                # Profilazione pubblica OTA: solo rating e quantità recensioni.
                # I prezzi eventualmente visibili sono esclusi dall'output reviews.
                ota_profiles = {}
                for channel in ("booking", "agoda", "airbnb"):
                    source = (data.get("sources") or {}).get(channel) or {}
                    url = source.get("url") if isinstance(source, dict) else ""
                    if not url:
                        ota_profiles[channel]={"status":"source_missing","evidence":"Scheda OTA non ancora verificata"}
                        continue
                    try:
                        item = await pilot.observe_ota_profile(context,channel,url,{})
                        ota_profiles[channel]={k:v for k,v in item.items()
                            if k in ("status","url","title","rating","ratingScale","reviewCount","recommendationRate","evidence")}
                    except Exception as exc:
                        ota_profiles[channel]={"status":"error","evidence":type(exc).__name__}
            finally:
                await context.close()
        result = _safe_result({
            "schema": NETWORK_SCHEMA, "reputation": google,"otaReviewProfiles": ota_profiles,
            "evidence": "Analisi Google + metriche reputazione OTA pubbliche, senza discovery prezzi né tariffe.",
        }, data["id"], agent)
    _write(output, result)
    return result

def evaluate(property_id: str, outputs: dict[str, Path]) -> dict:
    """Explicit, read-only reviewer: green only for evidence actually verified."""
    checks = []
    def add(agent: str, code: str, label: str, ok: bool, reason: str):
        checks.append({"agentId": agent, "code": code, "label": label,
                       "passed": bool(ok), "status": "verified" if ok else "review",
                       "detail": reason[:500]})
    for agent, path in outputs.items():
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            add(agent, "result", "Esito agente presente", False, "Nessun risultato valido per questo agente")
            continue
        add(agent, "property", "Associazione struttura", result.get("propertyId") == property_id,
            "Identificativo struttura coerente" if result.get("propertyId") == property_id else "Struttura non corrispondente")
        if AGENTS.get(agent, {}).get("kind") == "ota":
            observations = [o for o in result.get("observations", []) if o.get("otaId") == agent]
            valid_prices = [q for o in observations for q in o.get("quotes", []) if q.get("verified") and o.get("sourceIdentityVerified") is not False]
            date_ok = bool(observations) and all(
                o.get("dateReference") == "booking"
                and o.get("checkin") == o.get("bookingReferenceCheckin")
                and o.get("checkout") == o.get("bookingReferenceCheckout")
                for o in observations
            )
            add(agent, "dates", "Date identiche al riferimento Booking", date_ok,
                f"{len(observations)} campioni controllati; non assumere date valide se assenti")
            add(agent, "prices", "Tariffe verificate", bool(valid_prices),
                f"{len(valid_prices)} tariffe validate; i valori non confermati non entrano nel confronto")
            errors = [o for o in observations if o.get("status") in ("blocked", "rate_limited", "access_blocked", "login_required", "dates_mismatch_booking_reference", "robots_denied")]
            add(agent, "access", "Accesso pubblico senza blocchi", bool(observations) and not errors,
                f"{len(errors)} osservazioni con blocchi o date incoerenti")
        elif agent == "official_site":
            audit = result.get("auditData") or {}
            add(agent, "identity", "Sito ufficiale identificato", bool(audit.get("website")) and audit.get("id") == property_id,
                "Identità e sito del report devono corrispondere alla struttura selezionata")
            checks_site = audit.get("checks") or []
            positive = [c for c in checks_site if c.get("status") in {"present", "partial"}]
            add(agent, "site", "Evidenze verificabili del sito", bool(positive),
                f"{len(positive)} controlli con riscontro su {len(checks_site)}")
            photo=result.get("photoAudit") or {}
            add(agent,"photos","Qualità foto verificata",photo.get("status")=="sampled"
                and bool(photo.get("imageCount",0)),
                f"Stato {photo.get('status','n.d.')}; immagini {photo.get('imageCount',0)}")
        elif agent == "reviews":
            rep = result.get("reputation") or {}
            add(agent, "sample", "Campione recensioni verificato",
                rep.get("status") == "sampled" and bool(rep.get("sampleSize", 0)),
                f"Stato: {rep.get('status', 'n.d.')}; campione: {rep.get('sampleSize', 0)}")
    return {
        "schema": "velora-agent-validation-v1", "propertyId": property_id,
        "validatedAt": _now(), "checkedBy": "manual-trigger",
        "checks": checks, "rows": validation_rows({"checks": checks}), "reviewer": REVIEWER_NAME,
        "passed": sum(1 for c in checks if c["passed"]),
        "total": len(checks),
        "note": "Verde solo se il dato è verificato; assenza/blocco non equivalgono ad assenza dell'offerta."
    }
