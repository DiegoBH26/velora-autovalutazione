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
        explicit_wrong = observation.get("status") in bad_statuses
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
                  assist_callback=None, authorized_profile_dir: Path | None = None) -> dict:
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
            agent_id=agent,
            authorized_profile_dir=str(authorized_profile_dir) if authorized_profile_dir else None,
        )
        raw = await pilot.run(args)
        result = quarantine_identity_mismatches(enforce_portal_scope(enforce_known_listing_identity(_safe_result(raw, data["id"], agent), agent, data), agent), agent)
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
                    month=str(row.get("month") or "")
                    if month and row.get("checkin") and row.get("checkout"):
                        booking_locks[month]=(row["checkin"],row["checkout"],row.get("adults"))
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
                    str(row.get("month") or ""): (
                        row.get("checkin"),row.get("checkout"),row.get("adults"))
                    for row in result.get("bookingReferenceStays") or []
                    if row.get("month") and row.get("checkin") and row.get("checkout")
                }
                common=set(booking_locks)&set(local_locks)
                consistent=bool(booking_locks and local_locks and
                    set(local_locks)==set(booking_locks) and
                    all(booking_locks[month]==local_locks[month] for month in common))
                add(agent,"shared_booking_lock","Stesse date Booking fra agenti",consistent,
                    f"Riferimento Minerva: {len(booking_locks)} finestre; {agent_display(agent)}: {len(local_locks)}."
                    + (" Date condivise confermate." if consistent else
                       " Date non confrontabili o Minerva non ancora eseguita: non validare il delta."))
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
    comparisons=[]
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
        "passed": sum(1 for c in checks if c["passed"]),
        "total": len(checks),
        "note": "Verde solo se il dato è verificato; assenza/blocco non equivalgono ad assenza dell'offerta."
    }
