#!/usr/bin/env python3
"""Audit iniziale Velora dal solo sito ufficiale.

Usa Playwright/Chrome sul PC dell'utente. Raccoglie soltanto evidenze pubbliche:
pagine, contatti, privacy/cookie, CIN, servizi, fotografie e booking engine.
OTA, recensioni esterne, prezzi futuri e parita' tariffaria restano "non verificati"
finche' non vengono eseguiti i relativi adattatori.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from curl_cffi import requests
from playwright.async_api import async_playwright
from selectolax.lexbor import LexborHTMLParser

from booking_engine import detect_booking_engine

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "src" / "santantonio-audit.json"
BOT_UA = "VeloraAuditBot/1.0"

PAGE_WORDS = {
    "camere": ("camere", "camera", "rooms", "room", "suite", "alloggi", "accommodation", "appartament", "villa"),
    "gallery": ("gallery", "galleria", "foto", "photos"),
    "servizi": ("servizi", "services", "amenities", "spa", "wellness", "piscina", "pool", "ristorante", "restaurant"),
    "offerte": ("offerte", "offers", "promoz", "packages", "pacchetti"),
    "contatti": ("contatti", "contact", "dove siamo", "location"),
    "privacy": ("privacy", "cookie-policy", "cookie policy"),
    "booking": ("prenota", "booking", "book now", "reservation", "availability", "disponibilita"),
}
FEATURES = {
    "wifi": ("wi-fi", "wifi", "wireless"),
    "pool": ("piscina", "pool", "infinity pool"),
    "spa": ("spa", "wellness", "sauna", "hammam", "idromassaggio", "jacuzzi"),
    "restaurant": ("ristorante", "restaurant", "bistrot", "dining"),
    "breakfast": ("colazione", "breakfast"),
    "parking": ("parcheggio", "parking", "posto auto"),
    "transfer": ("transfer", "navetta", "shuttle"),
    "beach": ("spiaggia", "beach", "mare", "sea"),
    "family": ("famiglie", "family", "children", "bambini"),
    "couple": ("coppie", "couples", "romantic", "romantico"),
    "business": ("business", "meeting", "corporate"),
    "pet": ("pet friendly", "animali ammessi", "pets allowed"),
}
CIN_RE = re.compile(r"\bIT[0-9A-Z]{12,20}\b", re.I)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"(?:\+?39[\s./-]*)?(?:0\d{1,3}|3\d{2})[\s./-]*\d[\d\s./-]{5,12}")
PRICE_RE = re.compile(r"(?:€|EUR)\s*\d{1,5}(?:[.,]\d{2})?", re.I)


def clean(value, limit=4000):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def public_url(value):
    raw = str(value or "").strip()
    if raw and not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL del sito non valido")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("URL locale non consentito")
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is not None and not addr.is_global:
        raise ValueError("IP non pubblico non consentito")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))


def slugify(value, fallback_url=""):
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    if not text:
        text = (urlparse(fallback_url).hostname or "struttura").removeprefix("www.").split(".")[0]
    return re.sub(r"[^a-z0-9-]", "", text)[:72].strip("-") or "struttura"


def same_site(a, b):
    x = (urlparse(a).hostname or "").lower().removeprefix("www.")
    y = (urlparse(b).hostname or "").lower().removeprefix("www.")
    return bool(x and y and x == y)


def robots_allowed(url, cache):
    parsed = urlparse(url)
    origin = parsed.scheme + "://" + parsed.netloc
    if origin not in cache:
        try:
            r = requests.get(origin + "/robots.txt", timeout=12, headers={"User-Agent": BOT_UA})
            if r.status_code == 404:
                cache[origin] = True
            elif r.status_code == 200:
                p = RobotFileParser()
                p.parse(r.text.splitlines())
                cache[origin] = p
            else:
                cache[origin] = None
        except Exception:
            cache[origin] = None
    p = cache[origin]
    if isinstance(p, bool):
        return p
    return p.can_fetch(BOT_UA, url) if p else None


async def dismiss_cookie(page):
    selectors = [
        "button:has-text('Accetta tutti')", "button:has-text('Accetta')",
        "button:has-text('Consenti tutti')", "button:has-text('Accept all')",
        "button:has-text('Accept')", "button:has-text('Allow all')",
        "[role='button']:has-text('Accetta')", "[role='button']:has-text('Accept')",
    ]
    for selector in selectors:
        try:
            node = page.locator(selector).first
            if await node.count() and await node.is_visible(timeout=300):
                label = clean(await node.inner_text(timeout=500), 80) or selector
                await node.click(timeout=1200)
                await page.wait_for_timeout(250)
                return label
        except Exception:
            pass
    return ""


async def snapshot(page, url, mobile=False):
    response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(650)
    cookie_action = await dismiss_cookie(page)
    data = await page.evaluate("""() => {
      const abs = (u) => { try { return new URL(u, location.href).href; } catch { return ''; } };
      return {
        title: document.title || '',
        text: (document.body?.innerText || '').replace(/\s+/g,' ').trim().slice(0,40000),
        links: Array.from(document.querySelectorAll('a[href]')).slice(0,500).map(a => ({
          href: abs(a.getAttribute('href') || ''),
          text: (a.innerText || a.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim().slice(0,180)
        })).filter(x => x.href),
        images: Array.from(document.images).slice(0,250).map(img => ({
          src: abs(img.currentSrc || img.src || ''), alt: (img.alt || '').slice(0,180),
          naturalWidth: img.naturalWidth || 0, naturalHeight: img.naturalHeight || 0,
          width: img.clientWidth || 0, height: img.clientHeight || 0
        })).filter(x => x.src && !x.src.startsWith('data:')),
        viewportMeta: !!document.querySelector('meta[name="viewport"]'),
        horizontalOverflow: document.documentElement.scrollWidth > (window.innerWidth + 6)
      };
    }""")
    return {
        "url": page.url, "title": clean(data["title"], 240), "text": clean(data["text"], 40000),
        "html": (await page.content())[:1000000], "links": data["links"], "images": data["images"],
        "viewportMeta": bool(data["viewportMeta"]),
        "horizontalOverflow": bool(data["horizontalOverflow"]) if mobile else None,
        "cookieAction": cookie_action,
        "httpStatus": response.status if response else None,
    }


def classify(href, text):
    hay = (href + " " + text).lower()
    best = (0, "")
    for category, words in PAGE_WORDS.items():
        score = sum(2 if w in text.lower() else 1 for w in words if w in hay)
        if score > best[0]:
            best = (score, category)
    return best


def jsonld_facts(html):
    out = {"name": "", "city": "", "telephone": "", "email": ""}
    try:
        tree = LexborHTMLParser(html)
    except Exception:
        return out
    items = []
    def walk(v):
        if isinstance(v, list):
            for x in v: walk(x)
        elif isinstance(v, dict):
            items.append(v)
            if "@graph" in v: walk(v["@graph"])
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            walk(json.loads(node.text()))
        except Exception:
            pass
    accepted = {"hotel","lodgingbusiness","bedandbreakfast","motel","hostel","resort","vacationrental","accommodation","apartment","house"}
    lodging = None
    for item in items:
        types = item.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(str(t).lower().split("/")[-1] in accepted for t in types):
            lodging = item
            break
    if not lodging:
        return out
    out["name"] = clean(lodging.get("name"), 180)
    out["telephone"] = clean(lodging.get("telephone"), 80)
    out["email"] = clean(lodging.get("email"), 180)
    address = lodging.get("address")
    if isinstance(address, dict):
        out["city"] = clean(address.get("addressLocality"), 100)
    return out


def build_audit(payload, snaps, mobile):
    template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    home = snaps[0]
    all_text = " ".join(x["text"] for x in snaps).lower()
    links = [l for x in snaps for l in x["links"]]
    images = [i for x in snaps for i in x["images"]]
    ld = jsonld_facts(home["html"])

    requested = clean(payload.get("name"), 180)
    title_name = re.split(r"[|–—-]", home["title"])[0].strip() if home["title"] else ""
    name = requested or ld["name"] or title_name or (urlparse(home["url"]).hostname or "Struttura")
    website = public_url(payload.get("website") or home["url"])
    city = clean(payload.get("city"), 100) or ld["city"]
    province = clean(payload.get("province"), 10).upper()
    rooms = int(payload.get("rooms") or 0) if str(payload.get("rooms") or "").strip().isdigit() else 0
    property_id = slugify(name, website)
    if city and not property_id.endswith(slugify(city)):
        property_id = (property_id + "-" + slugify(city))[:79].strip("-")

    discovered = {}
    for x in snaps:
        hay = (x["url"] + " " + x["title"]).lower()
        for cat, words in PAGE_WORDS.items():
            if cat not in discovered and any(w in hay for w in words):
                discovered[cat] = x["url"]

    sources = {"sito": {"label": "Sito ufficiale", "url": website}}
    labels = {"camere":"Camere / alloggi","gallery":"Gallery","servizi":"Servizi","offerte":"Offerte","contatti":"Contatti","privacy":"Privacy"}
    for key, url in discovered.items():
        if key != "booking" and same_site(website, url):
            sources[key] = {"label": labels.get(key, key.title()), "url": url}

    engines = [detect_booking_engine(x["url"], x["html"], x["url"]) for x in snaps]
    rank = {"provider_identified":0,"request_only":1,"provider_unknown":2,"not_found_in_page":3,"not_applicable":4}
    engine = sorted(engines, key=lambda x: rank.get(x.get("status",""), 9))[0] if engines else {"status":"unverified","provider":"","url":"","mode":"","evidence":"Nessuna pagina esaminata."}
    if engine.get("url"):
        sources["engine"] = {"label":"Booking engine","url":engine["url"]}

    phones, emails, whatsapp = [], [], []
    for link in links:
        href = str(link.get("href",""))
        low = href.lower()
        if low.startswith("tel:"): phones.append(href.split(":",1)[1].split("?",1)[0])
        elif low.startswith("mailto:"): emails.append(href.split(":",1)[1].split("?",1)[0])
        elif "wa.me/" in low or "api.whatsapp.com" in low or "whatsapp.com/send" in low: whatsapp.append(href)
    if ld["telephone"]: phones.append(ld["telephone"])
    if ld["email"]: emails.append(ld["email"])
    if not phones: phones = [m.group(0) for m in PHONE_RE.finditer(home["text"])][:3]
    if not emails: emails = EMAIL_RE.findall(home["text"])[:3]
    phones = list(dict.fromkeys(clean(x,80) for x in phones if clean(x,80)))
    emails = list(dict.fromkeys(clean(x,180) for x in emails if clean(x,180)))
    whatsapp = list(dict.fromkeys(whatsapp))

    cin = list(dict.fromkeys(m.group(0).upper() for m in CIN_RE.finditer(" ".join(x["text"] for x in snaps))))
    privacy = any("privacy" in (str(l.get("href",""))+" "+str(l.get("text",""))).lower() for l in links)
    cookie = any(x["cookieAction"] for x in snaps) or "cookie" in all_text
    room_pages = [x for x in snaps if any(w in (x["url"]+" "+x["title"]).lower() for w in PAGE_WORDS["camere"])]
    room_text = " ".join(x["text"] for x in room_pages).lower()
    room_images = [i for x in room_pages for i in x["images"]]
    highres = [i for i in images if int(i.get("naturalWidth") or 0)>=1200 and int(i.get("naturalHeight") or 0)>=700]
    feature = {k:any(term in all_text for term in terms) for k,terms in FEATURES.items()}
    amenities = [k for k in ("wifi","pool","spa","restaurant","breakfast","parking","transfer","pet") if feature[k]]
    experiences = [k for k in ("pool","spa","restaurant","beach") if feature[k]]
    targets = [k for k in ("family","couple","business") if feature[k]]
    mobile_ok = bool(mobile and mobile["viewportMeta"] and mobile["horizontalOverflow"] is False)
    price_visible = bool(PRICE_RE.search(" ".join(x["text"] for x in snaps)))

    template.update({
        "id":property_id,"name":name,"city":city,"province":province,"rooms":rooms,
        "propertyType":clean(payload.get("propertyType"),100) or "Struttura ricettiva",
        "website":website,"auditedAt":date.today().isoformat(),"reportPath":"",
        "sources":sources,"bookingEngine":engine,
    })
    for ch in template["otaPresence"]:
        ch["status"]="unverified"; ch["finding"]="Da verificare sulla piattaforma pubblica; non dedotto dal solo sito ufficiale."; ch["source"]="sito"
    template["pricingAudit"] = {
        "capturedAt":date.today().isoformat(),
        "method":"Audit automatico iniziale del sito ufficiale. Tariffe future e delta richiedono preventivi omogenei; nessun prezzo viene stimato.",
        "direct":(
            "Booking engine diretto rilevato; tariffe future da campionare."
            if engine.get("status") in {"provider_identified","provider_unknown"}
            else "CTA di prenotazione presente, ma conduce a richiesta/contatto e non a disponibilità con prezzo e checkout."
            if engine.get("status") == "request_only"
            else "Percorso diretto da verificare."
        ),
        "policies":[{"otaId":c["id"],"plans":"Non verificato","promotions":"Non verificato","confidence":"Da verificare","source":"sito"} for c in template["otaPresence"]],
        "priceCalendar":{"from":date.today().isoformat(),"through":"","status":"Non verificato","reason":"Da campionare con browser locale.","metric":"Preventivo datato / notti","focus":"2 adulti; condizioni omogenee."},
    }
    template["reviewInsights"]={"googleRating":"Non verificato","method":"Recensioni esterne non incluse in questa fase.","strengths":[],"weaknesses":[]}
    template["photoAssessment"]={
        "score":0,
        "method":"Pre-check tecnico automatico; il voto commerciale/editoriale richiede revisione umana.",
        "strengths":f"Rilevate {len(images)} immagini, di cui {len(highres)} almeno 1200x700 px.",
        "gaps":"Coerenza, luce, styling, copertura tipologie e allineamento OTA da verificare.",
        "actions":"Valutare hero, camere, bagni, esterni e aree comuni prima del report definitivo.",
    }

    checks={c["id"]:c for c in template["checks"]}
    for c in checks.values():
        c["status"]="unverified"; c["evidence"]="Non verificato automaticamente in questa fase."; c["sources"]=["sito"]
    def setc(cid,status,evidence,src=None):
        if cid not in checks:
            return
        observed = clean(evidence, 900)
        if not observed.lower().startswith("esito:"):
            label = {
                "present": "Presente",
                "partial": "Parziale",
                "missing": "Non trovato",
                "unverified": "Da verificare",
                "not-applicable": "N/A",
            }.get(status, status)
            reason = {
                "present": "il requisito è supportato da un riscontro osservabile nel campione analizzato.",
                "partial": "il requisito è supportato solo in parte oppure manca un passaggio necessario per considerarlo completo.",
                "missing": "nel campione analizzato non è stato rilevato il requisito richiesto.",
                "unverified": "le evidenze raccolte non sono sufficienti per attribuire con sicurezza Presente, Parziale o Non trovato.",
                "not-applicable": "il requisito non è applicabile al caso analizzato.",
            }.get(status, "l'esito deriva dal riscontro riportato.")
            observed = f"Esito: {label}. Riscontro osservato: {observed} Motivo dell'esito: {reason}"
        checks[cid]["status"] = status
        checks[cid]["evidence"] = clean(observed, 1200)
        checks[cid]["sources"] = src or ["sito"]
    engine_status = (
        "present" if engine.get("status") == "provider_identified"
        else "partial" if engine.get("status") in {"provider_unknown", "request_only"}
        else "unverified"
    )
    engine_reason = clean(engine.get("evidence") or "Nessuna evidenza tecnica disponibile.", 700)
    if engine.get("status") == "provider_identified":
        engine_explanation = (
            "Esito: Presente. Riscontro osservato: è stato identificato un percorso di prenotazione transazionale "
            f"e il fornitore è {engine.get('provider') or 'riconoscibile dal percorso'}. Dettaglio tecnico: {engine_reason}"
        )
    elif engine.get("status") == "provider_unknown":
        engine_explanation = (
            "Esito: Parziale. Riscontro osservato: esiste un percorso con segnali di prenotazione, "
            "ma il fornitore o il completamento del flusso non sono identificabili con sufficiente certezza. "
            f"Dettaglio tecnico: {engine_reason}"
        )
    elif engine.get("status") == "request_only":
        engine_explanation = (
            "Esito: Parziale. Riscontro osservato: il sito presenta una CTA collegata alla prenotazione, "
            "ma il clic conduce a un contatto/modulo di richiesta invece di un motore con disponibilità, tariffa e checkout. "
            f"Dettaglio tecnico: {engine_reason}"
        )
    else:
        engine_explanation = (
            "Esito: Da verificare. Riscontro osservato: nel campione automatico non è stato identificato un percorso "
            "transazionale certo; questo non dimostra che il booking engine sia assente. "
            f"Dettaglio tecnico: {engine_reason}"
        )

    setc("q6","present" if len(home["text"])>500 else "partial",f"Homepage leggibile; campione di {len(snaps)} pagine.")
    setc("q7","present" if len(targets)>=2 else "partial","Target rilevati: "+(", ".join(targets) if targets else "nessuno esplicito nel campione"))
    setc("q8","present" if len(experiences)>=2 else "partial","Elementi della promessa: "+(", ".join(experiences) if experiences else "da chiarire"))
    setc("q9","present" if city else "partial","Localita' rilevata: "+(city or "non identificata automaticamente"))
    setc("q12","present" if mobile_ok else "partial","Test preliminare mobile 390 px: "+("viewport presente e nessun overflow orizzontale." if mobile_ok else "verifica visuale/performance ancora necessaria."))
    setc("q13",engine_status,engine_explanation,["engine"] if "engine" in sources else ["sito"])
    setc("q14","present" if room_pages and price_visible else "partial",f"Pagine camere: {len(room_pages)}; prezzo/testo tariffario visibile: {'si' if price_visible else 'non attribuibile a date precise'}.",["camere"] if "camere" in sources else ["sito"])
    trust=sum(bool(x) for x in (phones,emails,privacy,cin))
    setc("q15","present" if trust>=3 else "partial",f"Telefono {'si' if phones else 'no'}, email {'si' if emails else 'no'}, privacy {'si' if privacy else 'no'}, CIN {'si' if cin else 'no'}.")
    setc("q20","present" if urlparse(home["url"]).scheme=="https" else "missing","Sito servito in "+urlparse(home["url"]).scheme.upper()+".")
    setc("q21","partial" if cookie else "unverified","Banner/cookie "+("rilevato o gestito." if cookie else "non confermato nel campione."))
    setc("q22","present" if privacy else "partial","Privacy "+("rilevata." if privacy else "non rilevata nel campione."))
    setc("q24","unverified","Eventi marketing e consenso richiedono audit tecnico dedicato.")
    setc("q141","present" if cin else "partial","CIN: "+(", ".join(cin[:3]) if cin else "non rilevato nel campione."))
    setc("q221","present" if cin else "partial","Esposizione CIN "+("rilevata." if cin else "non rilevata nelle pagine campionate."))
    setc("q222","unverified","Coerenza CIN fra sito e OTA da verificare portale per portale.")
    setc("q261","present" if len(room_images)>=6 else "partial",f"Immagini su pagine camere: {len(room_images)}; qualita' editoriale da verificare.",["camere"] if "camere" in sources else ["sito"])
    setc("q263","partial",f"Immagini totali nel campione: {len(images)}; classificazione aree comuni da verificare.")
    setc("q264","partial","Esterni e contesto da verificare visivamente nella gallery.")
    setc("q266","present" if len(experiences)>=2 else "partial","Dettagli esperienziali: "+(", ".join(experiences) if experiences else "da verificare"))
    room_terms=sum(t in room_text for t in ("mq","m²","ospiti","guests","posti letto","letto","bed","bagno","bathroom"))
    setc("q269","present" if room_pages and room_terms>=3 else "partial",f"Pagine camere: {len(room_pages)}; indicatori capienza/dotazioni: {room_terms}.")
    setc("q272","present" if len(amenities)>=4 else "partial","Amenities: "+(", ".join(amenities) if amenities else "non rilevate con certezza"))
    setc("q279","present" if room_pages and len(room_text)>1200 else "partial",f"Descrizioni camere campionate: {len(room_pages)} pagine.")
    setc("q280","present" if len(experiences)>=3 else "partial","USP osservabili: "+(", ".join(experiences) if experiences else "da esplicitare"))
    setc("q307","present","Sito ufficiale raggiungibile: "+home["url"])
    for cid,label in (("q308","Presenza OTA"),("q309","Metasearch"),("q310","Profilo Google"),("q311","Coerenza contenuti"),("q314","Booking.com"),("q318","Google Hotels"),("q342","Risposte recensioni")):
        setc(cid,"unverified",label+": da verificare su fonte esterna.")
    for cid,label in (("q366","Comp set"),("q369","Recensioni competitive"),("q372","Percezione valore"),("q382","Pricing dinamico"),("q385","Parita tariffaria")):
        setc(cid,"unverified",label+": richiede dati esterni e preventivi omogenei.")
    setc(
        "q370",
        "partial" if engine_status != "unverified" or price_visible else "unverified",
        (
            "Riscontro osservato: il sito espone un percorso diretto, ma la verifica di prezzo/calendario non è ancora completa. "
            + engine_explanation
        ) if engine_status != "unverified" else
        "Riscontro osservato: nessun prezzo diretto attribuibile con certezza a date e condizioni precise; calendario futuro da verificare."
    )
    setc("q416","present" if phones else "partial","Telefono: "+(phones[0] if phones else "non rilevato."),["contatti"] if "contatti" in sources else ["sito"])
    setc("q417","present" if emails else "partial","Email: "+(emails[0] if emails else "non rilevata."),["contatti"] if "contatti" in sources else ["sito"])
    setc("q418","present" if whatsapp else "partial","WhatsApp "+("rilevato." if whatsapp else "non rilevato nel campione."))
    setc("q420",engine_status,engine_explanation+" Checkout e pagamento non vengono considerati verificati finché non sono completati dal test.",["engine"] if "engine" in sources else ["sito"])
    setc("q446","unverified","Tempo di risposta richiede test di contatto autorizzato.")
    for cid,label in (("q669","Pulizia"),("q670","Manutenzione"),("q720","Stato camere"),("q724","Manutenzioni visibili")):
        setc(cid,"unverified",label+": non deducibile in modo affidabile dal solo sito.")
    setc("q734","present" if feature["wifi"] else "partial","Wi-Fi "+("dichiarato nel sito." if feature["wifi"] else "non rilevato nel campione."))
    setc("q744","partial","Aspettative ospite: stagionalita', distanze e condizioni reali richiedono verifica.")
    offers="offerte" in discovered or any(k in all_text for k in ("offerta","offer","pacchetto","package","promoz"))
    setc("q756","present" if offers else "partial","Offerte dirette "+("rilevate." if offers else "non rilevate nel campione."),["offerte"] if "offerte" in sources else ["sito"])
    setc("q769","present" if len(amenities)>=3 else "partial","Servizi ancillari: "+(", ".join(amenities) if amenities else "da verificare"))

    template["checks"]=list(checks.values())
    template["reportNarrative"]={
        "summary1":f"Audit automatico iniziale di {name}: campionate {len(snaps)} pagine del sito ufficiale, {len(room_pages)} percorsi camere/alloggi e {len(images)} immagini.",
        "summary2":"Questa compilazione automatizza soltanto evidenze del sito. OTA, recensioni, prezzi futuri, piani tariffari, parita' e giudizio fotografico editoriale restano da completare.",
        "actions":[
            ["01  Distribuzione","Mappare le OTA e la corrispondenza delle unita'."],
            ["02  Pricing futuro","Campionare mesi futuri con preventivi omogenei e verificati."],
            ["03  Qualita' contenuti","Completare il giudizio editoriale delle foto e la coerenza sito/OTA."],
        ],
        "consulting":"L'audit automatico e' una base di lavoro, non misura la performance gestionale interna.",
        "channel":"La presenza sui canali esterni non viene inferita dal sito ufficiale.",
        "reviews":"Recensioni Google/Booking non analizzate in questa fase.",
        "photoNote":"Il pre-check automatico misura presenza/dimensioni tecniche; il voto /10 richiede valutazione editoriale.",
        "policy":"Piani tariffari e promozioni non vengono attribuiti senza quotazione datata verificabile.",
        "future":"Una data senza prezzo non equivale automaticamente a chiusura o stop-sell.",
        "identity":f"{city or 'Localita da verificare'}{(' ('+province+')') if province else ''} · camere/unita dichiarate: {rooms or 'n.d.'} · CIN: {cin[0] if cin else 'non rilevato nel campione'}.",
    }
    template["_autoAudit"]={
        "schema":"velora-site-audit-v1","generatedAt":datetime.now(timezone.utc).isoformat(),
        "pages":[{"url":x["url"],"title":x["title"],"cookieAction":x["cookieAction"]} for x in snaps],
        "mobile":{"viewportMeta":bool(mobile and mobile["viewportMeta"]),"horizontalOverflow":None if not mobile else mobile["horizontalOverflow"]},
        "facts":{"phones":phones,"emails":emails,"whatsapp":whatsapp,"cin":cin,"features":feature,"images":len(images),"highresImages":len(highres)},
    }
    return template


async def build_site_audit(payload):
    website=public_url(payload.get("website"))
    robots={}
    if await asyncio.to_thread(robots_allowed, website, robots) is False:
        raise RuntimeError("robots.txt non consente la visita automatica del sito ufficiale")

    async with async_playwright() as p:
        browser=await p.chromium.launch(channel="chrome", headless=True)
        context=await browser.new_context(locale="it-IT", timezone_id="Europe/Rome")
        snaps=[]
        try:
            page=await context.new_page()
            try:
                home=await snapshot(page, website)
            finally:
                await page.close()
            snaps.append(home)
            candidates=[]
            seen={home["url"].rstrip("/")}
            for link in home["links"]:
                href=str(link.get("href",""))
                if not href.startswith(("http://","https://")) or not same_site(home["url"],href):
                    continue
                clean_href=urlunparse(urlparse(href)._replace(fragment=""))
                if clean_href.rstrip("/") in seen:
                    continue
                score,cat=classify(clean_href,str(link.get("text","")))
                if score:
                    candidates.append((score,cat,clean_href))
            selected=[]; per={}
            for score,cat,href in sorted(candidates,key=lambda x:(-x[0],x[2])):
                if per.get(cat,0)>=2 or len(selected)>=11 or href.rstrip("/") in seen:
                    continue
                selected.append((cat,href)); per[cat]=per.get(cat,0)+1; seen.add(href.rstrip("/"))
            for _,href in selected:
                if await asyncio.to_thread(robots_allowed,href,robots) is False:
                    continue
                page=await context.new_page()
                try:
                    snaps.append(await snapshot(page,href))
                except Exception:
                    pass
                finally:
                    await page.close()
                await asyncio.sleep(0.35)
            page=await context.new_page()
            try:
                await page.set_viewport_size({"width":390,"height":844})
                mobile=await snapshot(page,website,mobile=True)
            except Exception:
                mobile=None
            finally:
                await page.close()
        finally:
            await browser.close()
    return build_audit(payload,snaps,mobile)


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("website")
    parser.add_argument("--name",default="")
    parser.add_argument("--city",default="")
    parser.add_argument("--province",default="")
    parser.add_argument("--rooms",default="")
    parser.add_argument("--output",default="audit-auto.json")
    args=parser.parse_args()
    result=asyncio.run(build_site_audit({"website":args.website,"name":args.name,"city":args.city,"province":args.province,"rooms":args.rooms}))
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(Path(args.output).resolve())
