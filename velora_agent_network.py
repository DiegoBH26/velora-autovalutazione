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
from velora_direct_commercial import inspect_direct_booking, concise_engine_fields, follow_booking_cta
from velora_direct_stays import probe_direct_stays, planned_direct_stays, discover_direct_engine
from velora_shared_intelligence import read_peer_evidence, store_peer_evidence
from playwright.async_api import async_playwright

NETWORK_SCHEMA = "velora-specialist-network-v1"
REVIEWER_NAME = "Giove"
AGENTS = {
    "official_site": {"name": "Leonardo", "label": "Sito diretto · MASTER", "kind": "site", "ready": True, "knowledge": "booking engine, prezzi, disponibilita', foto e contenuti"},
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

def classify_vrbo_presence(discovery: dict, property_id: str, property_name: str) -> dict:
    """Summarise search evidence without turning lack of indexing into absence.

    This is a discovery-only result, deliberately independent from dates, pricing
    and account login. Search engine errors or anti-bot blocks are inconclusive.
    """
    import re
    from urllib.parse import urlparse

    raw_candidates = discovery.get("listingUrls") or []
    candidates = []
    for raw_url in raw_candidates[:20]:
        url = str(raw_url or "").strip()
        try:
            parsed = urlparse(url)
        except (ValueError,TypeError):
            continue
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower()
        if parsed.scheme != "https" or not (
            host == "vrbo.com" or host.endswith(".vrbo.com")
            or host == "vrbo.it" or host.endswith(".vrbo.it")
        ) or not ("/pdp/" in path or re.search(r"/\d+(ha|vb|vr)?/?$",path)):
            continue
        if url not in candidates:
            candidates.append(url)

    evidence = str(discovery.get("evidence") or "")[:600]
    engines = []
    for engine in ("Google","Bing","Brave"):
        match = re.search(r"(?:^|;\s*)"+engine+r": (\d+) risultati", evidence)
        engines.append({"engine":engine, "searched":bool(match), "results":int(match.group(1)) if match else None})

    usable_engines = sum(int(item["searched"]) for item in engines)
    if candidates:
        status = "candidates_found"
        label = "Possibili schede Vrbo individuate · identità da verificare"
        explanation = ("Sono stati trovati link a possibili annunci Vrbo, non ancora attribuiti con certezza "
                       "alla struttura. Nessun prezzo viene importato automaticamente.")
    elif usable_engines >= 2:
        status = "not_identified"
        label = "Nessuna scheda Vrbo individuata"
        explanation = ("La ricerca pubblica non ha trovato una scheda attribuibile alla struttura. "
                       "La presenza su Vrbo resta non confermata: un annuncio non indicizzato "
                       "o pubblicato con un altro nome potrebbe esistere.")
    else:
        status = "inconclusive"
        label = "Verifica Vrbo inconcludente"
        explanation = ("Le fonti di ricerca consultate non hanno fornito riscontri sufficienti. "
                       "Non si può concludere né che l'annuncio esista né che sia assente.")
    return {
        "schema":"velora-vrbo-presence-v1",
        "propertyId":property_id,
        "propertyName":property_name,
        "checkedAt":_now(),
        "status":status,
        "label":label,
        "explanation":explanation,
        "candidateUrls":candidates,
        "engines":engines,
        "evidence":evidence,
        "identityVerified":False,
        "pricingChecked":False,
        "absenceConfirmed":False,
    }


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

def enforce_portal_scope(result: dict, agent: str) -> dict:
    """Reject observations that end on another portal, without changing parsers."""
    from urllib.parse import urlparse
    domains = {
        "booking": ("booking.com",),
        "airbnb": ("airbnb.com", "airbnb.it"),
        "agoda": ("agoda.com",),
        "expedia": ("expedia.it", "expedia.com"),
        "vrbo": ("vrbo.com", "vrbo.it"),
        "holidu": ("holidu.it", "holidu.com"),
        "hotels": ("hotels.com",),
        "travelocity": ("travelocity.com",),
        "trip": ("trip.com",),
        "priceline": ("priceline.com",),
    }
    allowed = domains.get(agent, ())
    for obs in result.get("observations") or []:
        if obs.get("otaId") != agent:
            continue
        url = str(obs.get("finalUrl") or "")
        if not url:
            continue
        host = (urlparse(url).hostname or "").lower()
        if any(host == d or host.endswith("." + d) for d in allowed):
            continue
        # Holidu may legitimately redirect to Booking: preserve the referral
        # as a discovery finding, but NEVER as an independent Holidu rate.
        if (agent == "holidu" and obs.get("status") == "referral_observed"
                and obs.get("referralTo") == "booking"):
            for quote in obs.get("quotes") or []:
                quote["verified"] = False
            obs["portalReferralOnly"] = True
            continue
        obs["identityQuarantined"] = True
        obs["sourceIdentityVerified"] = False
        obs["portalScopeViolation"] = True
        obs["identityQuarantineReason"] = (
            f"ERRORE PORTALE: {agent_display(agent)} ha raggiunto un dominio esterno alla propria OTA"
        )
        for quote in obs.get("quotes") or []:
            quote["verified"] = False
            quote["identityRejected"] = True
    return result


def quarantine_identity_mismatches(result: dict, agent: str) -> dict:
    """Fail closed on wrong-property evidence before results reach the reviewer.

    Keep raw diagnostic observations, but never allow their quotes to be
    marked as verified. This does not alter the legacy OTA parsers.
    """
    if agent not in {"booking", "airbnb", "agoda", "expedia", "vrbo", "holidu",
                     "hotels", "travelocity", "trip", "priceline"}:
        return result
    bad_statuses = {"wrong_property_listing", "identity_mismatch", "wrong_property",
                    "listing_identity_mismatch"}
    for observation in result.get("observations") or []:
        if observation.get("otaId") != agent:
            continue
        check = observation.get("identityCheck") or {}
        # There are TWO distinct states: a proven mismatch (different hotel)
        # and a still-unverified identity (Booking found, name/city evidence
        # incomplete). The latter must NOT be labelled "other property".
        quarantine_reason=str(observation.get("identityQuarantineReason") or "").lower()
        prior_explicit_mismatch=bool(observation.get("identityQuarantined") and
            ("annuncio diverso" in quarantine_reason
             or "altra struttura" in quarantine_reason))
        explicit_wrong = (observation.get("status") in bad_statuses
                          or prior_explicit_mismatch
                          or bool(observation.get("portalScopeViolation")))
        unverified = (observation.get("sourceIdentityVerified") is False
                      or (isinstance(check, dict) and (check.get("verified") is False
                          or check.get("ok") is False)))
        if not explicit_wrong and not unverified:
            continue
        observation["sourceIdentityVerified"] = False
        if explicit_wrong:
            observation["identityQuarantined"] = True
            observation["identityQuarantineReason"] = (
                "ANNUNCIO ESTRANEO: la verifica ha rilevato una scheda di altra struttura"
            )
        else:
            observation.pop("identityQuarantined", None)
            observation.pop("identityQuarantineReason", None)
            observation["identityUnverified"] = True
            observation["identityVerificationNote"] = (
                "Identità non ancora verificata; annuncio diverso NON dimostrato"
            )
        for quote in observation.get("quotes") or []:
            quote["verified"] = False
            # Exclude from price deltas, not from the observed-price preview.
            if explicit_wrong:
                quote["identityRejected"] = True
            else:
                quote.pop("identityRejected", None)
    return result


def _listing_key(channel: str, url: str) -> str:
    """Canonical listing identifier, never the search/home page."""
    from urllib.parse import urlparse
    import re
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lower().rstrip("/")
    if not host or not path:
        return ""
    if channel == "airbnb":
        match = re.search(r"/rooms/(\d+)", path)
        return f"airbnb:{match.group(1)}" if match and host.endswith("airbnb.com") else ""
    if channel == "agoda":
        match = re.search(r"/(?:[a-z]{2}-[a-z]{2}/)?([^/]+)\.html", path)
        return f"agoda:{match.group(1)}" if match and host.endswith("agoda.com") else ""
    return f"{host}:{path}"


def enforce_known_listing_identity(result: dict, agent: str, data: dict) -> dict:
    """Reject drift away from explicitly saved, previously verified OTA listing IDs.

    A candidate or unverified source must not be converted into an identity lock.
    Airbnb may legitimately have multiple validated room IDs.
    """
    if agent not in {"airbnb", "agoda"}:
        return result
    source = (data.get("sources") or {}).get(agent) or {}
    saved_verified = isinstance(source,dict) and bool(
        source.get("identityVerified") is True or source.get("verified") is True
        or source.get("verification") == "page_identity_lock")
    if not saved_verified:
        fresh = (result.get("discoveredSources") or {}).get(agent) or {}
        fresh_verified = isinstance(fresh,dict) and bool(
            fresh.get("identityVerified") is True
            or fresh.get("verification") == "page_identity_lock"
            or fresh.get("status") == "existing_verified")
        # A candidate URL without verified provenance is never a trusted lock.
        if not fresh_verified:
            return result
        source=fresh
    urls = [source.get("url"), *(source.get("listingUrls") or [])]
    locks = {_listing_key(agent, url) for url in urls}
    locks.discard("")
    if not locks:
        return result
    result["knownListingIdentityLock"] = sorted(locks)
    for observation in result.get("observations") or []:
        if observation.get("otaId") != agent:
            continue
        observed = _listing_key(agent, observation.get("finalUrl") or
                               observation.get("sourceUrl") or "")
        if observed in locks:
            continue
        observation["identityQuarantined"] = True
        observation["sourceIdentityVerified"] = False
        observation["identityQuarantineReason"] = (
            "ERRORE IDENTITÀ: annuncio diverso dalle schede OTA precedentemente validate"
        )
        for quote in observation.get("quotes") or []:
            quote["verified"] = False
            quote["identityRejected"] = True
    return result


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def specialist_input_matches_property_id(data: dict) -> bool:
    """Guard against an agent scanning an unrelated name under a saved property ID.

    The guard applies only to experimental OTA agents; existing Booking,
    Airbnb and Agoda behavior is not changed. Slug tokens are advisory only
    unless a distinctive, non-locality identifier is present.
    """
    import re
    import unicodedata
    def compact(text):
        return re.sub(r"[^a-z0-9]", "", unicodedata.normalize(
            "NFKD", str(text or "")).encode("ascii", "ignore").decode("ascii").lower())
    property_id=str(data.get("id") or "")
    name=compact(data.get("name"))
    city=compact(data.get("city"))
    ignored={"tenuta","masseria","hotel","villa","resort","relais","suites","suite",
             "dimora","struttura","agriturismo","albergo","luxury","puglia","booking"}
    tokens=[t for t in re.split(r"[-_]+",property_id.lower()) if len(t)>=6
            and t not in ignored and t != city and not t.isdigit()]
    if not tokens or not name:
        return bool(name)
    if any(compact(token) in name for token in tokens):
        return True
    # The user corrected the typo of this SAME known Salve property, keeping
    # its stable archive ID ("...speculizzi..."). Do not mistake a filename
    # typo for an unrelated hotel. This is an exact, locality-bound exception:
    # no generic fuzzy match and no blanket bypass of OTA page identity.
    known_spelling_correction=(
        city=="salve"
        and "speculizzi" in tokens
        and name=="tenutaspecolizzi"
    )
    return known_spelling_correction


async def execute(agent: str, data: dict, property_file: Path, output: Path,
                  *, months: int = 1, custom_period: dict | None = None,
                  ghost: bool = False, assisted: bool = False,
                  assist_callback=None, authorized_profile_dir: Path | None = None,
                  peer_callback=None) -> dict:
    """Run an independently scoped specialist. Legacy parsers remain unchanged."""
    if agent not in AGENTS or not AGENTS[agent]["ready"]:
        raise ValueError("Agente non disponibile")
    if agent in {"expedia","vrbo","holidu"} and not specialist_input_matches_property_id(data):
        raise ValueError(
            "IDENTITY MISMATCH: il nome della struttura nello snapshot non è coerente "
            "con la struttura selezionata. Controlla nome e associazione prima di avviare l'OTA."
        )
    if AGENTS[agent]["kind"] == "ota":
        # Guard cached sources before any external browser navigation.
        from urllib.parse import urlparse
        allowed = {
            "booking": ("booking.com",), "airbnb": ("airbnb.com", "airbnb.it"),
            "agoda": ("agoda.com",), "expedia": ("expedia.com", "expedia.it"),
            "vrbo": ("vrbo.com", "vrbo.it"), "holidu": ("holidu.com", "holidu.it"),
            "hotels": ("hotels.com",), "travelocity": ("travelocity.com",),
            "trip": ("trip.com",), "priceline": ("priceline.com",),
        }
        saved = (data.get("sources") or {}).get(agent) or {}
        if isinstance(saved, dict):
            for target in [saved.get("url"), *(saved.get("listingUrls") or [])]:
                if not target:
                    continue
                url = urlparse(str(target))
                host = (url.hostname or "").lower()
                if url.scheme != "https" or not any(
                    host == d or host.endswith("." + d) for d in allowed.get(agent, ())
                ):
                    raise ValueError("ERRORE PORTALE: la scheda salvata per "
                        + agent_display(agent) + " appartiene a un dominio esterno alla propria OTA.")
        args = argparse.Namespace(
            property=str(property_file), output=str(output), channels=agent,
            months=months, today=None, dry_run=False, ghost=ghost,
            assisted=assisted, assist_callback=assist_callback if assisted else None,
            pricing_only=True, custom_period=custom_period,
            agent_id=agent, peer_callback=peer_callback,
            authorized_profile_dir=str(authorized_profile_dir) if authorized_profile_dir else None,
        )
        raw = await pilot.run(args)
        result = quarantine_identity_mismatches(enforce_portal_scope(enforce_known_listing_identity(_safe_result(raw, data["id"], agent), agent, data), agent), agent)
        # Gli osservatori OTA condividono ciò che hanno già visto nella scheda:
        # niente seconda ricerca per recuperare foto di copertina e servizi.
        observations = [
            o for o in result.get("observations") or []
            if o.get("otaId")==agent and o.get("sourceIdentityVerified") is not False
            and not o.get("identityQuarantined")
            and o.get("status") not in ("wrong_property_listing","identity_mismatch","wrong_property")
        ]
        samples = [
            o.get("frontendSnapshot") for o in observations
            if isinstance(o.get("frontendSnapshot"),dict)
            and o["frontendSnapshot"].get("sampleOnly")
        ]
        first = next((x for x in samples if x.get("photoOrderSample")), {})
        photo = (first.get("photoOrderSample") or [None])[0]
        # Riutilizza il rating osservato durante la STESSA visita OTA;
        # solo la scheda con identità esplicitamente confermata è ammessa.
        verified_rating = next((
            o["frontendSnapshot"]["ratingCandidate"]
            for o in observations
            if o.get("sourceIdentityVerified") is True
            and isinstance(o.get("frontendSnapshot"), dict)
            and isinstance(o["frontendSnapshot"].get("ratingCandidate"), dict)
        ), None)
        if verified_rating:
            result.setdefault("otaProfiles", {})[agent] = {
                "status": "sampled",
                "url": next((o.get("finalUrl") for o in observations
                             if o.get("sourceIdentityVerified") is True and o.get("finalUrl")), ""),
                "rating": verified_rating.get("rating"),
                "ratingScale": verified_rating.get("ratingScale"),
                "reviewCount": verified_rating.get("reviewCount"),
                "evidence": verified_rating.get("evidence", "")+
                    "; identità OTA verificata dallo specialista.",
            }
        result["sharedKnowledge"] = {
            "sourceAgent": agent, "propertyId": data["id"],
            "observedAt": _now(), "listingIdentityQuarantined": False,
            "coverCandidate": photo if isinstance(photo,dict) else None,
            "mentionedAmenities": first.get("mentionedAmenities") or [],
            "coverStatus": "sample_not_visually_verified",
            "verifiedDatedRates": sum(
                1 for o in observations for q in o.get("quotes") or []
                if q.get("verified") is True
            ),
            "note": "Campione acquisito durante la visita OTA; foto e servizi da validare prima di dichiarare un'asimmetria.",
        }
    elif agent == "official_site":
        peer_evidence = read_peer_evidence(property_file.parent, data["id"], skip_agent=agent)
        site = data.get("website") or (data.get("sources", {}).get("sito") or {}).get("url")
        if not site:
            result=_safe_result({
                "schema":NETWORK_SCHEMA,
                "bookingEngine":{"status":"not_found_in_page","provider":"","url":"",
                    "evidence":"Sito diretto non configurato nella scheda struttura: verifica impossibile."},
                "directCommercialAudit":{"status":"website_not_configured","samples":[],
                    "verifiedQuotes":[],"evidence":["Nessun sito diretto configurato. "
                    "Leonardo non puo' cercare prezzi o disponibilita'."]},
                "photoAudit":{},"navigationAudit":{},
                "evidence":"Sito ufficiale assente dall'anagrafica; OTA successive analizzabili separatamente.",
            },data["id"],agent)
            _write(output,result)
            return result
        # PRIORITÀ LEONARDO: il primo obiettivo è la ricerca commerciale,
        # non il tour delle tipologie camera o l'audit foto del sito.
        # Il preflight legge SOLO la homepage e individua la vera CTA Prenota.
        try:
            today=datetime.now().date()
            plan=(pilot.custom_date_plan(today, custom_period) if custom_period
                  else pilot.monthly_plan(today,limit=(13 if months==12 else max(1,months))))
            direct_limit=min(len(plan),31)
            direct_windows=planned_direct_stays(plan,limit=direct_limit)
            plan_error=""
        except (ValueError,KeyError,TypeError) as exc:
            plan=[]
            direct_windows=[]
            plan_error="Piano date del sito diretto non valido: "+str(exc)[:180]
        try:
            preflight_engine=await discover_direct_engine(site)
        except Exception as exc:
            preflight_engine={"status":"error","url":"","provider":"",
                              "evidence":["Discovery Prenota: "+type(exc).__name__]}
        booking_url=preflight_engine.get("url") or ""
        direct_stays={"status":"not_checked","samples":[],"verifiedQuotes":[],
                      "observedRoomPrices":[],"searchedTotal":0,"evidence":[]}
        if booking_url:
            try:
                direct_stays=await probe_direct_stays(
                    booking_url,direct_windows,limit=len(direct_windows) or 1,
                    ghost=ghost,site_url=site,debug_dir=output.parent)
            except Exception as exc:
                direct_stays={"status":"error","samples":[],"verifiedQuotes":[],
                              "observedRoomPrices":[],"searchedTotal":0,
                              "evidence":["Ricerca prezzi sito diretto non completata: "+
                                          type(exc).__name__]}
        else:
            direct_stays["status"]="preflight_booking_cta_not_found"
            direct_stays["evidence"].extend(preflight_engine.get("evidence") or [])
        direct_stays["executionPriority"]="commercial_before_site_and_photos"
        # Solo ora si analizzano contenuti, foto e navigazione generale.
        audit = await build_site_audit({
            "propertyId": data["id"],
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
        if not int(direct_stays.get("searchedTotal") or 0):
            # Quando il booking engine non ha ancora prodotto UNA ricerca,
            # non aprire le pagine camere in un secondo Chrome visibile.
            photos={"status":"deferred_until_direct_search",
                    "evidence":["Audit fotografico rinviato: prima Leonardo deve "+
                                "aprire Prenota, selezionare date e cercare camere."]}
        else:
            try:
                async with async_playwright() as playwright:
                    context=await pilot._launch_velora_context(playwright,profile,picture_data,"foto sito diretto",ghost)
                    try:
                        photos=await pilot.frontend_photo_audit(context,picture_data,{})
                    finally:
                        await context.close()
            except Exception as exc:
                photos={"status":"not_verified",
                        "evidence":["Audit fotografico non concluso: "+type(exc).__name__]}
        # Segue davvero la CTA di prenotazione per catturare la scheda/dominio
        # finale e l'eventuale parametro pubblico Bedzzle della struttura.
        try:
            cta_verification=await follow_booking_cta(site,audit.get("bookingEngine") or {})
        except Exception as exc:
            cta_verification={"status":"error","evidence":[type(exc).__name__]}
        if cta_verification.get("status")=="reached" and cta_verification.get("resolvedUrl"):
            from booking_engine import detect_booking_engine
            discovered=detect_booking_engine(
                cta_verification["resolvedUrl"],"",cta_verification["resolvedUrl"])
            if discovered.get("status")=="provider_identified":
                discovered["mode"]=cta_verification.get("connectionType") or "link dal sito"
                discovered["evidence"]=" ".join(cta_verification.get("evidence") or [])[:500]
                audit["bookingEngine"]=discovered
        # Leonardo pubblica risultati strutturati per la scheda booking engine.
        # L'audit fotografico consolidato resta invariato.
        try:
            direct_verification = await inspect_direct_booking(site, audit.get("bookingEngine") or {})
        except Exception as exc:
            # Un engine bloccato non deve cancellare un audit foto/sito riuscito.
            direct_verification = {
                "status": "error", "navigation": "not_tested",
                "availability": "not_verified", "datedPrices": [],
                "evidence": ["Verifica booking engine non conclusa: " + type(exc).__name__],
            }
        booking_windows=(peer_evidence.get("booking") or {}).get("bookingReferenceStays") or []
        if not booking_windows:
            # Solo a titolo di confronto storico, mai per scegliere il
            # periodo di una NUOVA ricerca sul sito diretto.
            previous_booking=property_file.parent.parent / "specialist-agents" / str(data["id"]) / "booking" / "result.json"
            try:
                prior=json.loads(previous_booking.read_text(encoding="utf-8"))
                if prior.get("propertyId")==data["id"]:
                    booking_windows=prior.get("bookingReferenceStays") or []
            except (OSError,ValueError,TypeError):
                pass
        # Un sito senza CTA nella discovery veloce può comunque avere un
        # engine rilevato dal successivo audit; tenta SOLO in questo caso.
        if not booking_url:
            booking_url=(audit.get("bookingEngine") or {}).get("url") or ""
            if booking_url:
                try:
                    direct_stays=await probe_direct_stays(
                        booking_url,direct_windows,limit=len(direct_windows) or 1,
                        ghost=ghost,site_url=site,debug_dir=output.parent)
                    direct_stays["executionPriority"]="fallback_after_site_audit"
                except Exception as exc:
                    direct_stays={"status":"error","samples":[],"verifiedQuotes":[],
                                  "observedRoomPrices":[],"searchedTotal":0,
                                  "evidence":["Ricerca prezzi dopo audit non conclusa: "+
                                              type(exc).__name__]}
            else:
                engine_status=(audit.get("bookingEngine") or {}).get("status") or ""
                direct_stays["status"]=(
                    "booking_engine_not_found" if engine_status=="not_found_in_page"
                    else "request_only_no_booking_engine" if engine_status=="request_only"
                    else "engine_url_missing")
                direct_stays.setdefault("evidence",[]).append(
                    "Non è stata individuata una destinazione pubblica del pulsante Prenota.")
        elif (audit.get("bookingEngine") or {}).get("status")!="provider_identified":
            audit["bookingEngine"]={
                "status":preflight_engine.get("status") or "provider_unknown",
                "provider":preflight_engine.get("provider") or "",
                "url":booking_url,"mode":"link dal sito",
                "evidence":"Link Prenota identificato sulla homepage prima dell'audit completo.",
            }
        # L'esito della vera ricerca commerciale prevale sulla sola ispezione
        # preliminare del motore fatta in una sessione separata.
        searched=int(direct_stays.get("searchedTotal") or 0)
        if searched:
            samples=direct_stays.get("samples") or []
            dates_ok=any(sample.get("datesConfirmedAfterSearch") is True
                         for sample in samples if sample.get("searchSubmitted") is True)
            guests_ok=any((sample.get("occupancyControl") or {}).get("confirmed") is True
                          for sample in samples if sample.get("searchSubmitted") is True)
            direct_verification["navigation"]="reached"
            direct_verification["status"]="commercial_search_observed"
            direct_verification["bookingFlow"]="availability_search_submitted"
            direct_verification["controls"]={
                "dates":bool(dates_ok),"guests":bool(guests_ok),"bookingAction":True}
            direct_verification["evidence"]=list(direct_verification.get("evidence") or [])+[
                f"Ricerca commerciale Leonardo: {searched} invii realmente eseguiti; "
                f"date confermate={dates_ok}; adulti confermati={guests_ok}. "
                "I prezzi sono mostrati separatamente dai preventivi omogenei."]
        elif direct_stays.get("status")=="search_not_executed":
            direct_verification["evidence"]=list(direct_verification.get("evidence") or [])+[
                "Ricerca commerciale non avviata: "+
                " | ".join((direct_stays.get("samples") or [{}])[0].get("evidence") or [])[:350]]
        direct_stays["referenceSource"]="sito_diretto"
        direct_stays["plannedStays"]=direct_windows
        direct_stays["plannedTotal"]=len(plan) if not plan_error else 0
        direct_stays["checkedTotal"]=len(direct_stays.get("samples") or [])
        if len(plan)>len(direct_windows):
            direct_stays.setdefault("evidence",[]).append(
                f"Periodo esteso: {len(direct_windows)} soggiorni analizzati "
                f"su {len(plan)} programmati (limite operativo massimo 31).")
        direct_stays["bookingHistoricalReference"]=bool(booking_windows)
        if plan_error:
            direct_stays.setdefault("evidence",[]).append(plan_error)
        if not direct_windows:
            direct_stays.setdefault("evidence",[]).append(
                "Nessuna finestra di soggiorno valida nel periodo scelto per il sito diretto.")
        if booking_windows:
            confirmed=set()
            for w in booking_windows:
                try:
                    adults=int(w.get("adults") or 0)
                except (ValueError,TypeError):
                    continue
                confirmed.add((str(w.get("checkin") or ""),
                               str(w.get("checkout") or ""),adults))
            direct_stays["bookingHistoricalDateMatches"]=sum(
                1 for w in direct_windows
                if (w.get("checkin"),w.get("checkout"),w.get("adults")) in confirmed)
        direct_verification["ctaNavigation"]=cta_verification
        engine_fields = concise_engine_fields(audit, direct_verification)
        audit["bookingEngineVerification"] = direct_verification
        audit["directCommercialAudit"] = direct_stays
        audit["bookingEngineFields"] = engine_fields
        result = _safe_result({
            "schema": NETWORK_SCHEMA, "propertyName":data.get("name",""), "auditData": audit, "photoAudit": photos,
            "bookingEngine": audit.get("bookingEngine") or {},
            "bookingEngineFields": engine_fields,
            "directBookingVerification": direct_verification,
            "directCommercialAudit": direct_stays,
            "masterSequence": ["official_site","booking","ota"],
            "navigationAudit": (audit.get("_autoAudit") or {}).get("navigationChecks") or {},
            "peerBookingDates": booking_windows,
            "evidence": "Audit sito e fotografie; percorso booking engine verificato solo nei limiti delle prove esplicite; prezzi datati ancora non confermati.",
        }, data["id"], agent)
    else:  # reviews only
        peer_evidence = read_peer_evidence(property_file.parent, data["id"], skip_agent=agent)
        profile = property_file.parent / "chrome-reviews"
        async with async_playwright() as playwright:
            context = await pilot._launch_velora_context(playwright, profile, data, "recensioni", ghost)
            try:
                google = await pilot.google_reputation_observation(context, data)
                # Profilazione pubblica OTA: solo rating e quantità recensioni.
                # I prezzi eventualmente visibili sono esclusi dall'output reviews.
                ota_profiles = {}
                for channel in ("booking", "agoda", "airbnb"):
                    cached=(peer_evidence.get(channel) or {}).get("rating") or {}
                    if cached.get("status")=="sampled" and cached.get("rating") is not None:
                        ota_profiles[channel]={**cached,"evidence":str(cached.get("evidence") or "")+
                            " · Condiviso dall'agente OTA; nessuna seconda navigazione."}
                        continue
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
            "otaProfiles": {channel:profile for channel,profile in ota_profiles.items()
                if profile.get("status")=="sampled" and (
                    (peer_evidence.get(channel) or {}).get("rating")
                    or ((data.get("sources") or {}).get(channel) or {}).get("identityVerified") is True
                )},
            "evidence": "Analisi Google e reputazione OTA; evidenze già confermate riutilizzate senza doppia visita.",
        }, data["id"], agent)
    _write(output, result)
    try:
        store_peer_evidence(property_file.parent, data["id"], agent, result)
    except (OSError, ValueError, TypeError):
        # La memoria ausiliaria non deve compromettere il risultato verificato.
        pass
    return result

def evaluate(property_id: str, outputs: dict[str, Path]) -> dict:
    """Explicit, read-only reviewer: green only for evidence actually verified."""
    checks = []
    def add(agent: str, code: str, label: str, ok: bool, reason: str):
        checks.append({"agentId": agent, "code": code, "label": label,
                       "passed": bool(ok), "status": "verified" if ok else "review",
                       "detail": reason[:500]})
    # Audit incrociato: la stessa finestra deve essere usata da OGNI OTA.
    # Agenti isolati potrebbero risolvere Booking a orari diversi; in tal caso
    # Giove NON conferma il confronto tra piattaforme.
    booking_locks={}
    frontend_samples={}
    reference_path=outputs.get("booking")
    if reference_path is not None:
        try:
            booking_report=json.loads(reference_path.read_text(encoding="utf-8"))
            if booking_report.get("propertyId")==property_id:
                for row in booking_report.get("bookingReferenceStays") or []:
                    key=(str(row.get("requestedCheckin") or ""),
                         str(row.get("requestedCheckout") or ""))
                    if all(key) and row.get("checkin") and row.get("checkout"):
                        booking_locks[key]=(row["checkin"],row["checkout"],row.get("adults"))
        except (OSError,ValueError):
            pass
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
            valid_prices = [q for o in observations for q in o.get("quotes", [])
                            if q.get("verified") and not o.get("identityQuarantined")
                            and o.get("sourceIdentityVerified") is not False
                            and o.get("status") not in {"wrong_property_listing", "identity_mismatch", "wrong_property"}]
            rejected = [o for o in observations if o.get("identityQuarantined")
                        or o.get("sourceIdentityVerified") is False
                        or o.get("status") in {"wrong_property_listing", "identity_mismatch", "wrong_property"}]
            add(agent, "listing_identity", "Identità scheda OTA", bool(observations) and not rejected,
                f"{len(rejected)} schede con ERRORE IDENTITÀ: le rispettive tariffe sono escluse")
            # Giove: independent audit of agent scope and authenticated profile.
            from urllib.parse import urlparse
            portal_domains = {
                "booking": ("booking.com",), "airbnb": ("airbnb.com", "airbnb.it"),
                "agoda": ("agoda.com",), "expedia": ("expedia.it", "expedia.com"),
                "vrbo": ("vrbo.com", "vrbo.it"), "holidu": ("holidu.it", "holidu.com"),
                "hotels": ("hotels.com",), "travelocity": ("travelocity.com",),
                "trip": ("trip.com",), "priceline": ("priceline.com",),
            }
            allowed = portal_domains.get(agent, ())
            wrong_domain = []
            for observation in observations:
                host = (urlparse(str(observation.get("finalUrl") or "")).hostname or "").lower()
                if (agent == "holidu" and observation.get("portalReferralOnly")
                        and observation.get("referralTo") == "booking"):
                    continue
                if host and not any(host == domain or host.endswith("." + domain)
                                    for domain in allowed):
                    wrong_domain.append(host)
            add(agent, "portal_scope", "Portale assegnato", bool(observations) and not wrong_domain,
                f"{len(wrong_domain)} pagine su un dominio non autorizzato per questo agente")
            account_required = agent in {"expedia", "vrbo", "holidu"}
            account_ok = result.get("sessionMode") == "registered_profile_opt_in"
            if account_required:
                add(agent, "account_profile", "Profilo account autorizzato", account_ok,
                    "Profilo Chrome dedicato selezionato; login effettivo non verificato"
                    if account_ok else "Scansione non effettuata con il profilo Account")
            if wrong_domain or (account_required and not account_ok) or result.get("propertyId") != property_id:
                valid_prices = []
            snapshots=[o.get("frontendSnapshot") for o in observations
                       if isinstance(o.get("frontendSnapshot"),dict)
                       and not o.get("identityQuarantined")
                       and o.get("sourceIdentityVerified") is not False
                       and o.get("frontendSnapshot",{}).get("sampleOnly")]
            usable=[s for s in snapshots if s.get("photoOrderSample") or s.get("mentionedAmenities")]
            add(agent, "frontend_sample", "Foto, servizi e condizioni nella scheda",
                bool(usable),
                f"{len(usable)} campioni frontend dalla scheda OTA; contenuto indicativo, "
                "non prova automatica di foto identiche o servizi effettivamente offerti")
            if usable:
                frontend_samples[agent]=usable[0]
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
            if agent != "booking":
                local_locks={
                    (str(row.get("requestedCheckin") or ""),
                     str(row.get("requestedCheckout") or "")): (
                        row.get("checkin"),row.get("checkout"),row.get("adults"))
                    for row in result.get("bookingReferenceStays") or []
                    if row.get("requestedCheckin") and row.get("requestedCheckout")
                    and row.get("checkin") and row.get("checkout")
                }
                common=set(booking_locks)&set(local_locks)
                consistent=bool(booking_locks and local_locks and
                    set(local_locks)==set(booking_locks) and
                    all(booking_locks[window]==local_locks[window] for window in common))
                add(agent,"shared_booking_lock","Stesse date Booking fra agenti",consistent,
                    f"Riferimento Minerva: {len(booking_locks)} finestre; {agent_display(agent)}: {len(local_locks)}."
                    + (" Date condivise confermate." if consistent else
                       " Date non confrontabili o Minerva non ancora eseguita: non validare il delta."))
        elif agent == "official_site":
            direct=result.get("directBookingVerification") or {}
            be=result.get("bookingEngine") or {}
            add(agent, "booking_engine_identification", "Fornitore booking engine",
                be.get("status")=="provider_identified" and bool(be.get("provider")),
                "Fornitore: "+str(be.get("provider") or "non identificato"))
            add(agent, "booking_engine_navigation", "Navigazione booking engine",
                direct.get("navigation")=="reached",
                "Navigazione: "+str(direct.get("navigation") or "non eseguita")
                +"; flusso transazionale NON ancora collaudato")
            commercial=result.get("directCommercialAudit") or {}
            samples_direct=commercial.get("samples") or []
            parity=bool(samples_direct) and bool(booking_locks) and all(
                (sample.get("checkin"),sample.get("checkout"),sample.get("guests"))
                in booking_locks.values()
                and (sample.get("checkin"),sample.get("checkout")) in booking_locks
                for sample in samples_direct
            )
            add(agent, "direct_booking_date_parity", "Date e ospiti sito diretto / Booking",
                parity,
                f"{len(samples_direct)} finestre sito diretto controllate rispetto a {len(booking_locks)} riferimenti Booking."
                + (" Date e ospiti coincidenti." if parity else " Confronto non convalidato."))
            searched_direct=[sample for sample in samples_direct
                             if sample.get("status")=="date_context_observed"
                             and sample.get("searchSubmitted") is True]
            add(agent, "direct_search_windows", "Ricerche datate sul booking engine diretto",
                bool(searched_direct),
                f"{len(searched_direct)} ricerche effettivamente inviate su "
                f"{len(samples_direct)} finestre del sito diretto. "
                f"Esito: {commercial.get('status','n.d.')}. "
                "Input date senza invio non provano la disponibilita'.")
            add(agent, "direct_dated_prices", "Tariffe dirette datate",
                bool(commercial.get("verifiedQuotes")),
                "Nessun prezzo diretto entra nel delta senza preventivo datato, stanza equivalente e condizioni verificate")
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
    # Il sito diretto e' MASTER di disponibilita'/prezzi; Booking deve
    # rispondere sulle finestre richieste da Leonardo. Se Booking le sposta,
    # segnalarlo come asimmetria POTENZIALE, non come conferma di sold-out.
    direct_path=outputs.get("official_site")
    booking_path=outputs.get("booking")
    if direct_path and booking_path:
        try:
            direct_report=json.loads(direct_path.read_text(encoding="utf-8"))
            booking_report=json.loads(booking_path.read_text(encoding="utf-8"))
            if (direct_report.get("propertyId")==property_id
                    and booking_report.get("propertyId")==property_id):
                master=direct_report.get("directCommercialAudit") or {}
                requested=master.get("plannedStays") or master.get("samples") or []
                booking_rows=booking_report.get("bookingReferenceStays") or []
                expected={
                    (str(w.get("checkin") or ""),str(w.get("checkout") or ""),
                     int(w.get("adults") or w.get("guests") or 0))
                    for w in requested if (w.get("adults") or w.get("guests"))
                }
                by_requested={
                    (str(w.get("requestedCheckin") or ""),
                     str(w.get("requestedCheckout") or ""),int(w.get("adults") or 0)):w
                    for w in booking_rows if w.get("requestedCheckin")
                    and w.get("requestedCheckout") and w.get("adults")
                }
                shared=expected & set(by_requested)
                shifted=[key for key in shared if (
                    str(by_requested[key].get("checkin") or "")!=key[0]
                    or str(by_requested[key].get("checkout") or "")!=key[1])]
                incomplete=expected-set(by_requested)
                green=bool(expected and shared) and not shifted and not incomplete
                add("booking","direct_master_date_alignment",
                    "Booking confrontato sulle date del sito diretto",
                    green,
                    f"Leonardo: {len(expected)} finestre richieste; Booking: "
                    f"{len(shared)} richieste corrispondenti, {len(shifted)} date spostate, "
                    f"{len(incomplete)} non confermate. "
                    +("Asimmetria potenziale: verificare la stessa camera sul diretto "
                      "prima di dichiarare l'inventario mancante su Booking."
                      if shifted or incomplete else "Date richieste allineate.")
                )
                direct_rates=master.get("verifiedQuotes") or []
                direct_available={
                    (str(q.get("checkin") or ""),str(q.get("checkout") or ""),
                     int(q.get("guests") or 0))
                    for q in direct_rates if q.get("verified") and q.get("guests")
                }
                availability_gaps=direct_available & set(shifted)
                if availability_gaps:
                    add("booking","direct_master_inventory_alert",
                        "Possibile differenza disponibilità diretto / Booking",
                        False,
                        f"{len(availability_gaps)} soggiorni con preventivo sul diretto "
                        "e ricerca Booking spostata. Verificare tipologia identica e "
                        "condizioni prima di qualificare l'asimmetria.")
        except (OSError,ValueError,TypeError,KeyError):
            add("booking","direct_master_date_alignment",
                "Booking confrontato sulle date del sito diretto",False,
                "Lettura dell'allineamento diretto/Booking non conclusa.")
    comparisons=[]
    cover_candidates={
        agent: (sample.get("photoOrderSample") or [None])[0]
        for agent,sample in frontend_samples.items()
        if sample.get("photoOrderSample")
    }
    sample_agents=sorted(frontend_samples)
    for left_index,left in enumerate(sample_agents):
        for right in sample_agents[left_index+1:]:
            a,b=frontend_samples[left],frontend_samples[right]
            left_amenities=set(a.get("mentionedAmenities") or [])
            right_amenities=set(b.get("mentionedAmenities") or [])
            differences=sorted(left_amenities.symmetric_difference(right_amenities))
            comparisons.append({
                "leftAgent":left,"rightAgent":right,
                "photoCountLeft":len(a.get("photoOrderSample") or []),
                "photoCountRight":len(b.get("photoOrderSample") or []),
                "differentServiceMentions":differences,
                "status":"indicative_review_required",
                "note":"Differenze nel campione visibile: non provano da sole asimmetrie reali né ordine foto identico.",
            })
    return {
        "schema": "velora-agent-validation-v1", "propertyId": property_id,
        "validatedAt": _now(), "checkedBy": "manual-trigger",
        "checks": checks, "rows": validation_rows({"checks": checks}), "reviewer": REVIEWER_NAME,
        "frontendComparisons":comparisons,
        "coverPhotoCandidates":cover_candidates,
        "coverComparisonStatus":"requires_visual_confirmation",
        "passed": sum(1 for c in checks if c["passed"]),
        "total": len(checks),
        "note": "Verde solo se il dato è verificato; assenza/blocco non equivalgono ad assenza dell'offerta."
    }
