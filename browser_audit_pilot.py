#!/usr/bin/env python3
"""Pilota locale di osservazione OTA: nessun prezzo inventato o blocco aggirato.

Sceglie una data campione per ogni mese futuro, apre le schede pubbliche in
Chrome e salva lo stato della verifica. Un prezzo non entra nel report finché
date, camera, piano e totale non sono verificati come un unico preventivo.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse, unquote
from urllib.robotparser import RobotFileParser

from curl_cffi import requests
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

from booking_engine import detect_booking_engine


SCHEMA = "velora-browser-audit-pilot-v1"
CHANNELS = ("sito", "booking", "airbnb", "expedia", "vrbo", "hotels", "agoda", "trip", "holidaycheck")
OTA_DISCOVERY_ORDER = ("booking", "airbnb", "expedia", "hotels", "vrbo", "agoda", "trip", "holidaycheck")
OTA_META = {
    "booking": {"label": "Booking.com", "domains": ("booking.com",)},
    "airbnb": {"label": "Airbnb", "domains": ("airbnb.com", "airbnb.it")},
    "expedia": {"label": "Expedia", "domains": ("expedia.com", "expedia.it")},
    "hotels": {"label": "Hotels.com", "domains": ("hotels.com",)},
    "vrbo": {"label": "Vrbo", "domains": ("vrbo.com", "vrbo.it")},
    "agoda": {"label": "Agoda", "domains": ("agoda.com",)},
    "trip": {"label": "Trip.com", "domains": ("trip.com",)},
    "holidaycheck": {"label": "HolidayCheck", "domains": ("holidaycheck.com", "holidaycheck.it")},
}
DATE_URL_ADAPTERS = set(CHANNELS) - {"sito", "holidaycheck"}
BLOCK_WORDS = (
    "captcha", "verify you are human", "are you a robot", "unusual traffic",
    "javascript is disabled", "access denied", "security check", "verifica di sicurezza",
)
PRICE_RE = re.compile(r"(?:€|EUR)\s*([0-9]{1,5}(?:[.,][0-9]{2})?)|([0-9]{1,5}(?:[.,][0-9]{2})?)\s*(?:€|EUR)", re.I)
GENERIC_NAME_WORDS = {
    "hotel", "aparthotel", "resort", "b&b", "bb", "bed", "breakfast", "apartments",
    "apartment", "appartamenti", "appartamento", "rooms", "room", "suite", "suites",
}


def monthly_plan(today: date, end_year: int | None = None, limit: int | None = None) -> list[dict]:
    """15-18 del mese, agosto 12-17; mai nel passato."""
    end_year = end_year or today.year + 1
    months: list[dict] = []
    year, month = today.year, today.month
    while (year, month) <= (end_year, 12):
        nights = 5 if month == 8 else 3
        checkin = date(year, month, 12 if month == 8 else 15)
        if checkin <= today:
            checkin = today + timedelta(days=2)
        checkout = checkin + timedelta(days=nights)
        if checkin.month == month and checkout.month == month:
            months.append({"month": f"{year:04d}-{month:02d}", "checkin": checkin.isoformat(),
                           "checkout": checkout.isoformat(), "nights": nights, "adults": 2})
            if limit and len(months) >= limit:
                break
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def dated_url(channel: str, base: str, stay: dict) -> str | None:
    """Solo parametri osservabili: una URL costruita non prova che il portale li applichi."""
    if channel not in DATE_URL_ADAPTERS:
        return None
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if channel == "booking":
        query.update(checkin=stay["checkin"], checkout=stay["checkout"],
                     group_adults="2", no_rooms="1", group_children="0")
    elif channel == "airbnb":
        query.update(check_in=stay["checkin"], check_out=stay["checkout"], adults="2")
    elif channel in {"expedia", "hotels"}:
        query.update(chkin=stay["checkin"], chkout=stay["checkout"], rm1="a2")
    elif channel == "vrbo":
        query.update(chkin=stay["checkin"], chkout=stay["checkout"], adults="2")
    elif channel == "agoda":
        query.update(checkIn=stay["checkin"], los=str(stay["nights"]), rooms="1", adults="2", children="0")
    elif channel == "trip":
        query.update(checkIn=stay["checkin"], checkOut=stay["checkout"], adult="2", children="0", crn="1")
    return urlunparse(parsed._replace(query=urlencode(query)))


def allowed_by_robots(url: str, cache: dict[str, RobotFileParser | bool | None]) -> bool | None:
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in cache:
        try:
            response = requests.get(origin + "/robots.txt", timeout=12,
                                    headers={"User-Agent": "VeloraAuditBot/1.0"})
            if response.status_code == 404:
                cache[origin] = True
            elif response.status_code == 200:
                parser = RobotFileParser()
                parser.parse(response.text.splitlines())
                cache[origin] = parser
            else:
                cache[origin] = None
        except Exception:
            cache[origin] = None
    parser = cache[origin]
    if isinstance(parser, bool):
        return parser
    return parser.can_fetch("VeloraAuditBot", url) if parser else None


MONTH_NAMES = {
    1: ("gen", "gennaio", "jan", "january"),
    2: ("feb", "febbraio", "february"),
    3: ("mar", "marzo", "march"),
    4: ("apr", "aprile", "april"),
    5: ("mag", "maggio", "may"),
    6: ("giu", "giugno", "jun", "june"),
    7: ("lug", "luglio", "jul", "july"),
    8: ("ago", "agosto", "aug", "august"),
    9: ("set", "sett", "settembre", "sep", "sept", "september"),
    10: ("ott", "ottobre", "oct", "october"),
    11: ("nov", "novembre", "november"),
    12: ("dic", "dicembre", "dec", "december"),
}


def _date_forms(day: date) -> tuple[str, ...]:
    forms = {
        day.isoformat(),
        f"{day.day:02d}/{day.month:02d}/{day.year}",
        f"{day.day}/{day.month}/{day.year}",
        f"{day.day:02d}-{day.month:02d}-{day.year}",
        f"{day.day}-{day.month}-{day.year}",
        f"{day.day:02d}.{day.month:02d}.{day.year}",
        f"{day.day}.{day.month}.{day.year}",
    }
    for month_name in MONTH_NAMES[day.month]:
        forms.update({
            f"{day.day} {month_name}",
            f"{day.day:02d} {month_name}",
            f"{month_name} {day.day}",
            f"{month_name} {day.day:02d}",
            f"{day.day} {month_name} {day.year}",
            f"{day.day:02d} {month_name} {day.year}",
            f"{month_name} {day.day} {day.year}",
            f"{month_name} {day.day:02d} {day.year}",
        })
    return tuple(forms)


def visible_dates_confirmed(text: str, stay: dict) -> bool:
    """Conservativo: check-in e check-out devono comparire nel contenuto renderizzato."""
    start, end = date.fromisoformat(stay["checkin"]), date.fromisoformat(stay["checkout"])
    lowered = re.sub(r"\s+", " ", (text or "").lower())
    return any(value in lowered for value in _date_forms(start)) and any(value in lowered for value in _date_forms(end))


async def booking_dom_dates_confirmed(page, stay: dict) -> tuple[bool, str]:
    """Conferma le date nello stato DOM Booking senza affidarsi ai soli parametri URL."""
    start, end = date.fromisoformat(stay["checkin"]), date.fromisoformat(stay["checkout"])
    try:
        values = await page.evaluate(r"""() => {
          const selectors = [
            '[data-testid="date-display-field-start"]',
            '[data-testid="date-display-field-end"]',
            'input[name="checkin"]',
            'input[name="checkout"]',
            '[data-date]',
            '[aria-label*="check-in" i]',
            '[aria-label*="check-out" i]',
            '[aria-label*="arrivo" i]',
            '[aria-label*="partenza" i]'
          ];
          const out = [];
          const seen = new Set();
          for (const selector of selectors) {
            for (const el of Array.from(document.querySelectorAll(selector)).slice(0, 80)) {
              const parts = [
                el.textContent || '',
                el.getAttribute('value') || '',
                el.getAttribute('data-date') || '',
                el.getAttribute('aria-label') || '',
                el.getAttribute('placeholder') || ''
              ];
              const value = parts.join(' ').replace(/\s+/g,' ').trim();
              if (value && !seen.has(value)) { seen.add(value); out.push(value.slice(0,300)); }
            }
          }
          return out;
        }""")
    except Exception:
        return False, ""
    combined = " | ".join(str(value) for value in values).lower()
    confirmed = any(value in combined for value in _date_forms(start)) and any(value in combined for value in _date_forms(end))
    return confirmed, combined[:700]

def booking_url_dates_confirmed(url: str, stay: dict) -> bool:
    """Conferma che Booking abbia mantenuto esattamente le date richieste nella URL finale."""
    try:
        parsed=urlparse(url)
        query=dict(parse_qsl(parsed.query, keep_blank_values=True))
    except Exception:
        return False
    checkin=query.get("checkin") or query.get("check_in") or ""
    checkout=query.get("checkout") or query.get("check_out") or ""
    return checkin==stay["checkin"] and checkout==stay["checkout"]


async def booking_property_rate_context(page) -> tuple[bool, str]:
    """Verifica che la pagina sia una scheda struttura con area disponibilita/camere caricata."""
    selectors=(
        '#hprt-table',
        '[data-testid="room-list"]',
        '[data-testid="room-card"]',
        '[data-testid="availability-block"]',
        '[data-testid="property-title"]',
    )
    found=[]
    for selector in selectors:
        try:
            loc=page.locator(selector).first
            if await loc.count():
                found.append(selector)
        except Exception:
            pass
    path=(urlparse(page.url).path or "").lower()
    is_property="/hotel/" in path
    has_rate_area=any(selector in found for selector in ('#hprt-table','[data-testid="room-list"]','[data-testid="room-card"]','[data-testid="availability-block"]'))
    return bool(is_property and has_rate_area), ", ".join(found[:6])


async def _first_visible_locator(page, selectors):
    for selector in selectors:
        try:
            loc=page.locator(selector).first
            if await loc.count() and await loc.is_visible(timeout=350):
                return loc, selector
        except Exception:
            pass
    return None, ""


async def booking_apply_dates_via_ui(page, stay: dict) -> tuple[bool, str]:
    """Prova a impostare check-in/check-out usando il date picker pubblico di Booking."""
    checkin=stay["checkin"]
    checkout=stay["checkout"]
    evidence=[]
    opener, opener_selector = await _first_visible_locator(page, (
        '[data-testid="date-display-field-start"]',
        'button[data-testid="date-display-field-start"]',
        '[data-testid="searchbox-dates-container"]',
        'button[aria-label*="check-in" i]',
        'button[aria-label*="arrivo" i]',
    ))
    if opener is None:
        return False, "date picker Booking non individuato"
    try:
        await opener.click(timeout=1800)
        await page.wait_for_timeout(350)
        evidence.append(f"aperto con {opener_selector}")
    except Exception as exc:
        return False, f"date picker non apribile: {type(exc).__name__}"

    async def pick(target_iso: str) -> tuple[bool, str]:
        target_selector=f'[data-date="{target_iso}"]'
        for step in range(20):
            try:
                target=page.locator(target_selector).first
                if await target.count() and await target.is_visible(timeout=250):
                    disabled = await target.get_attribute("aria-disabled")
                    if disabled == "true":
                        return False, f"{target_iso} presente ma non selezionabile"
                    await target.click(timeout=1800)
                    await page.wait_for_timeout(250)
                    return True, f"{target_iso} selezionata"
            except Exception:
                pass
            next_button, next_selector = await _first_visible_locator(page, (
                'button[aria-label*="mese successivo" i]',
                'button[aria-label*="successivo" i]',
                'button[aria-label*="next month" i]',
                'button[aria-label*="next" i]',
                '[data-testid="calendar-next-button"]',
                '[data-testid*="next-month"]',
            ))
            if next_button is None:
                return False, f"{target_iso} non visibile e navigazione calendario non trovata"
            try:
                await next_button.click(timeout=1500)
                await page.wait_for_timeout(220)
                if step == 0:
                    evidence.append(f"navigazione calendario con {next_selector}")
            except Exception as exc:
                return False, f"navigazione calendario fallita: {type(exc).__name__}"
        return False, f"{target_iso} non raggiunta entro 20 mesi"

    ok_start, ev_start = await pick(checkin)
    evidence.append(ev_start)
    if not ok_start:
        return False, "; ".join(evidence)
    ok_end, ev_end = await pick(checkout)
    evidence.append(ev_end)
    if not ok_end:
        return False, "; ".join(evidence)

    submit, submit_selector = await _first_visible_locator(page, (
        '[data-testid="date-submit-button"]',
        '[data-testid="searchbox-layout-wide"] button[type="submit"]',
        'form[role="search"] button[type="submit"]',
        'form[action*="searchresults"] button[type="submit"]',
    ))
    if submit is not None:
        try:
            await submit.click(timeout=1800)
            evidence.append(f"ricerca inviata con {submit_selector}")
        except Exception:
            evidence.append("date selezionate; pulsante ricerca non cliccabile")
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=8000)
    except Exception:
        pass
    await page.wait_for_timeout(1200)
    return True, "; ".join(evidence)

def _norm_name(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"\bb\s*&\s*b\b|\bb\s+and\s+b\b|\bbed\s*&?\s*breakfast\b", " ", ascii_text)
    tokens = [token for token in re.findall(r"[a-z0-9]+", ascii_text) if token not in GENERIC_NAME_WORDS]
    return " ".join(tokens)


def _name_similarity(expected: str, observed: str) -> float:
    left, right = _norm_name(expected), _norm_name(observed)
    if not left or not right:
        return 0.0
    ratio = SequenceMatcher(None, left, right).ratio()
    left_tokens, right_tokens = set(left.split()), set(right.split())
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    containment = len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens)))
    return max(ratio, 0.55 * overlap + 0.45 * containment)


async def dismiss_cookie(page) -> str:
    for selector in (
        "button:has-text('Accetta tutti')", "button:has-text('Accetta')",
        "button:has-text('Accept all')", "button:has-text('Accept')",
        "[id*='accept']", "[data-testid*='accept']",
    ):
        try:
            node = page.locator(selector).first
            if await node.count() and await node.is_visible(timeout=250):
                label = re.sub(r"\s+", " ", (await node.inner_text(timeout=500)) or selector)[:80]
                await node.click(timeout=1000)
                await page.wait_for_timeout(250)
                return label
        except Exception:
            pass
    return ""



def _decode_search_target(href: str) -> str:
    """Decodifica link diretti o redirect di Google/Bing senza limitarsi a Booking."""
    try:
        raw=str(href or "").strip()
        if not raw:
            return ""
        absolute=raw if raw.startswith(("http://","https://")) else ""
        parsed=urlparse(absolute or raw)
        if not absolute and raw.startswith(("/url?","/link?")):
            query=dict(parse_qsl(parsed.query,keep_blank_values=True))
            absolute=query.get("q") or query.get("url") or query.get("u") or ""
        if not absolute:
            return ""
        parsed=urlparse(absolute)
        host=(parsed.hostname or "").lower()
        query=dict(parse_qsl(parsed.query,keep_blank_values=True))
        if "google." in host and parsed.path in {"/url","/aclk"}:
            absolute=query.get("q") or query.get("url") or query.get("adurl") or ""
        elif host.endswith("bing.com") and parsed.path.startswith("/ck/"):
            encoded=query.get("u") or ""
            if encoded.startswith("a1"):
                token=encoded[2:] + "=" * (-len(encoded[2:]) % 4)
                try:
                    absolute=base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8","ignore")
                except Exception:
                    pass
        absolute=unquote(str(absolute or ""))
        parsed=urlparse(absolute)
        if parsed.scheme not in {"http","https"} or not parsed.hostname:
            return ""
        return urlunparse(parsed._replace(fragment=""))
    except Exception:
        return ""


def _classify_ota_url(url: str) -> str:
    try:
        host=(urlparse(url).hostname or "").lower().removeprefix("www.")
        path=(urlparse(url).path or "").lower()
    except Exception:
        return ""
    for ota_id,meta in OTA_META.items():
        if any(host==domain or host.endswith("." + domain) for domain in meta["domains"]):
            # Esclude home e pagine di ricerca chiaramente generiche.
            if path in {"","/"}:
                return ""
            if ota_id=="booking" and "/hotel/" not in path:
                return ""
            if ota_id=="airbnb" and not any(token in path for token in ("/rooms/","/hotel/")):
                return ""
            if ota_id in {"expedia","hotels"} and any(token in path.lower() for token in ("/hotel-search","/search")):
                return ""
            return ota_id
    return ""


def _master_identity_queries(property_name: str, city: str, address: str, phone: str = "", email: str = "", website: str = "") -> list[str]:
    """Varianti progressive: esatta -> libera/fuzzy -> identità alternative."""
    name=" ".join(property_name.split())
    city=" ".join(city.split())
    address=" ".join(address.split())
    normalized=_norm_name(name)
    location=address or city
    queries=[]

    # 1. Segnale forte, ma non unico: utile quando il nome è scritto esattamente come sulle OTA.
    if name and location:
        queries.append(f'"{name}" "{location}"')
    elif name:
        queries.append(f'"{name}"')

    # 2. Ricerca libera: consente a Google/Bing correzioni ortografiche e varianti B&B/BB.
    if name and location:
        queries.append(f"{name} {location}")
    elif name:
        queries.append(name)

    # 3. Nome normalizzato senza descrittori ricettivi (B&B, hotel, apartments...).
    if normalized and location:
        queries.append(f"{normalized} {location}")
    elif normalized:
        queries.append(normalized)

    # 4. Se abbiamo città e non indirizzo, prova anche solo nome normalizzato + città.
    if normalized and city and city.lower() not in normalized.lower():
        queries.append(f"{normalized} {city}")

    # 5. Segnali identitari alternativi dal sito ufficiale.
    if phone.strip():
        queries.append(f'"{phone.strip()}"')
    if email.strip():
        queries.append(f'"{email.strip()}"')
    try:
        host=(urlparse(website).hostname or "").lower().removeprefix("www.")
    except Exception:
        host=""
    if host:
        queries.append(host)

    out=[]
    seen=set()
    for query in queries:
        query=" ".join(query.split()).strip()
        if query and query.lower() not in seen:
            seen.add(query.lower())
            out.append(query)
    return out[:8]


async def _search_result_links(page, query: str, engine: str = "Google") -> tuple[list[dict], str]:
    if engine=="Google":
        url="https://www.google.com/search?" + urlencode({"q":query,"hl":"it","num":"20"})
    else:
        url="https://www.bing.com/search?" + urlencode({"q":query,"setlang":"it"})
    response=await page.goto(url,wait_until="domcontentloaded",timeout=30000)
    await page.wait_for_timeout(1200)
    await dismiss_cookie(page)
    body=(await page.locator("body").inner_text(timeout=7000))[:20000]
    if response and response.status>=400:
        return [],f"{engine}: HTTP {response.status}"
    if any(word in body.lower() for word in BLOCK_WORDS):
        return [],f"{engine}: pagina di verifica/blocco"
    links=await page.evaluate(r"""() => Array.from(document.querySelectorAll('a[href]')).slice(0,900).map(a => {
      const box=a.closest('div,li,article,[data-testid]') || a.parentElement;
      return {
        href:a.getAttribute('href') || '',
        text:(a.innerText || a.textContent || a.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim().slice(0,360),
        context:(box?.innerText || '').replace(/\s+/g,' ').trim().slice(0,1300)
      };
    })""")
    return links,url


async def verify_ota_candidate_page(context, ota_id: str, url: str, property_name: str, city: str, address: str, robots: dict) -> dict:
    permission=await asyncio.to_thread(allowed_by_robots,url,robots)
    if permission is not True:
        return {"ok":False,"score":0.0,"title":"","evidence":"Pagina candidata non verificata: robots.txt non consente o non chiarisce l'accesso."}
    page=await context.new_page()
    try:
        response=await page.goto(url,wait_until="domcontentloaded",timeout=25000)
        if not response or response.status>=400:
            return {"ok":False,"score":0.0,"title":"","evidence":f"Pagina candidata HTTP {response.status if response else 'n.d.'}."}
        await dismiss_cookie(page)
        await page.wait_for_timeout(900)
        body=(await page.locator("body").inner_text(timeout=6500))[:18000]
        if any(word in body.lower() for word in BLOCK_WORDS):
            return {"ok":False,"score":0.0,"title":"","evidence":"Il portale ha mostrato una verifica/blocco; nessun aggiramento tentato."}
        title=(await page.title())[:260]
        try:
            h1=page.locator("h1").first
            if await h1.count():
                h1_text=re.sub(r"\s+"," ",(await h1.inner_text(timeout=500)) or "").strip()
                if h1_text:
                    title=h1_text
        except Exception:
            pass
        score,path_slug,text_score,url_score,reasons=_identity_match_score(
            property_name,city,address,title,body[:2500],page.url
        )
        # La pagina candidata proviene già dal dominio OTA corretto: città/indirizzo sono segnali forti.
        ok=score>=0.70
        return {
            "ok":ok,"score":round(score,3),"title":title[:220],
            "url":urlunparse(urlparse(page.url)._replace(fragment="")),
            "evidence":reasons,
            "otaId":ota_id,
        }
    except Exception as exc:
        return {"ok":False,"score":0.0,"title":"","evidence":f"Verifica pagina fallita: {type(exc).__name__}: {str(exc)[:120]}"}
    finally:
        await page.close()


async def discover_otas_from_master_search(context, data: dict, robots: dict) -> tuple[dict, dict]:
    """FIRST/SECOND STEP: ricerca master progressiva, poi analisi dei risultati OTA."""
    name=str(data.get("name") or "")
    city=str(data.get("city") or "")
    address=str(data.get("address") or "")
    phone=str(data.get("phone") or "")
    email=str(data.get("email") or "")
    website=((data.get("sources") or {}).get("sito") or {}).get("url","")
    queries=_master_identity_queries(name,city,address,phone,email,website)
    diagnostics={"queries":queries,"engine":"Google","status":"pending","candidates":0,"queryStats":[]}
    if not queries:
        diagnostics.update(status="missing_identity")
        return {},diagnostics

    discoveries={}
    raw_candidates={ota_id:[] for ota_id in OTA_DISCOVERY_ORDER}

    # Google per primo, ma su più varianti: una query esatta non può bloccare l'intero flusso.
    for query in queries:
        page=await context.new_page()
        try:
            links,search_url=await _search_result_links(page,query,"Google")
            before=diagnostics["candidates"]
            for item in links:
                target=_decode_search_target(str(item.get("href") or ""))
                ota_id=_classify_ota_url(target)
                if not ota_id:
                    continue
                score,path_slug,text_score,url_score,reasons=_identity_match_score(
                    name,city,address,str(item.get("text") or ""),str(item.get("context") or ""),target
                )
                raw_candidates[ota_id].append((score,target,str(item.get("text") or ""),reasons,query,"Google"))
                diagnostics["candidates"]+=1
            diagnostics["queryStats"].append({
                "engine":"Google","query":query,"links":len(links),
                "otaCandidates":diagnostics["candidates"]-before,
                "searchUrl":search_url,
            })
        except Exception as exc:
            diagnostics["queryStats"].append({"engine":"Google","query":query,"error":f"{type(exc).__name__}: {str(exc)[:120]}"})
        finally:
            await page.close()

    # Bing RSS per le stesse varianti: non aspetta che Google sia completamente vuoto.
    for query in queries:
        before=diagnostics["candidates"]
        items=await asyncio.to_thread(_bing_rss_items,query)
        for item in items:
            target=_decode_search_target(str(item.get("link") or ""))
            ota_id=_classify_ota_url(target)
            if not ota_id:
                desc=unquote(str(item.get("description") or ""))
                for match in re.findall(r'https?://[^\s<>"\']+',desc,re.I):
                    candidate=_decode_search_target(match)
                    channel=_classify_ota_url(candidate)
                    if channel:
                        target,ota_id=candidate,channel
                        break
            if not ota_id:
                continue
            context_text=re.sub(r"<[^>]+>"," ",str(item.get("description") or ""))
            score,path_slug,text_score,url_score,reasons=_identity_match_score(
                name,city,address,str(item.get("title") or ""),context_text,target
            )
            raw_candidates[ota_id].append((score,target,str(item.get("title") or ""),reasons,query,"Bing RSS"))
            diagnostics["candidates"]+=1
        diagnostics["queryStats"].append({
            "engine":"Bing RSS","query":query,"links":len(items),
            "otaCandidates":diagnostics["candidates"]-before,
        })

    diagnostics["status"]="results_collected" if diagnostics["candidates"] else "no_ota_candidates"

    for ota_id in OTA_DISCOVERY_ORDER:
        candidates=raw_candidates.get(ota_id) or []
        best_by_url={}
        for row in candidates:
            if row[1] not in best_by_url or row[0]>best_by_url[row[1]][0]:
                best_by_url[row[1]]=row
        candidates=sorted(best_by_url.values(),key=lambda row:row[0],reverse=True)
        weak=[]
        for score,url,title,reasons,query,engine in candidates[:8]:
            verify=await verify_ota_candidate_page(context,ota_id,url,name,city,address,robots)
            if verify.get("ok"):
                discoveries[ota_id]={
                    "status":"found",
                    "url":verify.get("url") or url,
                    "title":verify.get("title") or title,
                    "score":verify.get("score",score),
                    "evidence":(
                        f"Ricerca master {engine} «{query}»: risultato {OTA_META[ota_id]['label']} trovato e verificato aprendo la pagina. "
                        f"Match risultato {score:.0%} ({reasons}); verifica pagina {verify.get('score',0):.0%} ({verify.get('evidence','')})."
                    )[:900],
                    "searchUrl":"",
                    "discoveryMode":"progressive master search + page verification",
                }
                break
            weak.append((score,url,title,reasons,query,engine,verify.get("evidence","")))
        if ota_id not in discoveries and weak:
            score,url,title,reasons,query,engine,verify_evidence=weak[0]
            discoveries[ota_id]={
                "status":"needs_review","url":url,"title":title[:220],"score":round(score,3),
                "evidence":(
                    f"Ricerca master {engine} «{query}»: candidato {OTA_META[ota_id]['label']} trovato "
                    f"({score:.0%}, {reasons}) ma non verificato con sufficiente certezza sulla pagina reale. {verify_evidence}"
                )[:900],
                "searchUrl":"",
                "discoveryMode":"progressive master search candidate",
            }
    return discoveries,diagnostics


async def discover_single_ota_targeted(context, ota_id: str, data: dict, robots: dict) -> dict:
    """THIRD STEP: ricerca mirata progressiva sul singolo portale."""
    meta=OTA_META[ota_id]
    name=str(data.get("name") or "")
    city=str(data.get("city") or "")
    address=str(data.get("address") or "")
    phone=str(data.get("phone") or "")
    normalized=_norm_name(name)
    location=address or city
    base_domain=meta["domains"][0]

    variants=[]
    if name and location:
        variants.append(f'site:{base_domain} "{name}" "{location}"')
        variants.append(f"site:{base_domain} {name} {location}")
    elif name:
        variants.append(f'site:{base_domain} "{name}"')
        variants.append(f"site:{base_domain} {name}")
    if normalized and location:
        variants.append(f"site:{base_domain} {normalized} {location}")
    elif normalized:
        variants.append(f"site:{base_domain} {normalized}")
    if phone:
        variants.append(f'site:{base_domain} "{phone}"')

    queries=[]
    seen=set()
    for query in variants:
        query=" ".join(query.split())
        if query.lower() not in seen:
            seen.add(query.lower()); queries.append(query)

    weak=[]
    for query in queries[:6]:
        page=await context.new_page()
        try:
            links,search_url=await _search_result_links(page,query,"Google")
            for item in links:
                target=_decode_search_target(str(item.get("href") or ""))
                if _classify_ota_url(target)!=ota_id:
                    continue
                score,path_slug,text_score,url_score,reasons=_identity_match_score(
                    name,city,address,str(item.get("text") or ""),str(item.get("context") or ""),target
                )
                verify=await verify_ota_candidate_page(context,ota_id,target,name,city,address,robots)
                if verify.get("ok"):
                    return {
                        "status":"found","url":verify.get("url") or target,
                        "title":verify.get("title") or str(item.get("text") or ""),
                        "score":verify.get("score",score),
                        "evidence":(
                            f"Ricerca mirata Google su {meta['label']}: «{query}». "
                            f"Pagina verificata con match {verify.get('score',0):.0%} ({verify.get('evidence','')})."
                        )[:900],
                        "searchUrl":search_url,"discoveryMode":"progressive targeted Google + page verification",
                    }
                weak.append((score,target,str(item.get("text") or ""),reasons,query,"Google",verify.get("evidence","")))
        except Exception:
            pass
        finally:
            await page.close()

        items=await asyncio.to_thread(_bing_rss_items,query)
        for item in items:
            target=_decode_search_target(str(item.get("link") or ""))
            if _classify_ota_url(target)!=ota_id:
                continue
            desc=re.sub(r"<[^>]+>"," ",str(item.get("description") or ""))
            score,path_slug,text_score,url_score,reasons=_identity_match_score(name,city,address,str(item.get("title") or ""),desc,target)
            verify=await verify_ota_candidate_page(context,ota_id,target,name,city,address,robots)
            if verify.get("ok"):
                return {
                    "status":"found","url":verify.get("url") or target,
                    "title":verify.get("title") or str(item.get("title") or ""),
                    "score":verify.get("score",score),
                    "evidence":(
                        f"Ricerca mirata {meta['label']} con Bing RSS: «{query}». "
                        f"Pagina verificata con match {verify.get('score',0):.0%} ({verify.get('evidence','')})."
                    )[:900],
                    "searchUrl":"https://www.bing.com/search?"+urlencode({"q":query}),
                    "discoveryMode":"progressive targeted Bing RSS + page verification",
                }
            weak.append((score,target,str(item.get("title") or ""),reasons,query,"Bing RSS",verify.get("evidence","")))

    weak.sort(key=lambda row:row[0],reverse=True)
    if weak:
        score,url,title,reasons,query,engine,verify_evidence=weak[0]
        return {
            "status":"needs_review","url":url,"title":title[:220],"score":round(score,3),
            "evidence":(
                f"Ricerca mirata {meta['label']} completata su più varianti. Miglior candidato da {engine}, query «{query}»: "
                f"{score:.0%} ({reasons}), ma pagina non verificata con sufficiente certezza. {verify_evidence}"
            )[:900],
            "searchUrl":"","discoveryMode":"progressive targeted search exhausted",
        }
    return {
        "status":"not_found_in_search","url":"","title":"","score":0.0,
        "evidence":f"Ricerca mirata {meta['label']} completata su {len(queries)} varianti senza una scheda verificabile.",
        "searchUrl":"","discoveryMode":"progressive targeted search exhausted",
    }


def _openai_api_key() -> str:
    return str(os.environ.get("VELORA_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()


def _extract_response_output_text(payload: dict) -> str:
    parts=[]
    for item in payload.get("output") or []:
        if not isinstance(item,dict) or item.get("type")!="message":
            continue
        for content in item.get("content") or []:
            if isinstance(content,dict) and content.get("type")=="output_text":
                parts.append(str(content.get("text") or ""))
    return "\n".join(parts).strip()


def _ai_discovery_schema() -> dict:
    return {
        "type":"object",
        "properties":{
            "property_match":{
                "type":"object",
                "properties":{
                    "canonical_name":{"type":"string"},
                    "city":{"type":"string"},
                    "address":{"type":"string"},
                    "summary":{"type":"string"},
                },
                "required":["canonical_name","city","address","summary"],
                "additionalProperties":False,
            },
            "listings":{
                "type":"array",
                "items":{
                    "type":"object",
                    "properties":{
                        "ota_id":{"type":"string","enum":list(OTA_DISCOVERY_ORDER)},
                        "status":{"type":"string","enum":["found","not_found","uncertain"]},
                        "url":{"type":"string"},
                        "title":{"type":"string"},
                        "confidence":{"type":"number","minimum":0,"maximum":1},
                        "evidence":{"type":"string"},
                    },
                    "required":["ota_id","status","url","title","confidence","evidence"],
                    "additionalProperties":False,
                },
            },
        },
        "required":["property_match","listings"],
        "additionalProperties":False,
    }


def _run_ai_web_search(data: dict) -> dict:
    """Fallback agentico: OpenAI web_search live. La chiave resta solo nell'ambiente locale."""
    api_key=_openai_api_key()
    if not api_key:
        return {"status":"not_configured","discoveries":{},"evidence":"VELORA_OPENAI_API_KEY non configurata sul PC."}

    sources=data.get("sources") or {}
    official=((sources.get("sito") or {}).get("url") if isinstance(sources.get("sito"),dict) else "") or ""
    identity={
        "name":str(data.get("name") or ""),
        "city":str(data.get("city") or ""),
        "province":str(data.get("province") or ""),
        "address":str(data.get("address") or ""),
        "phone":str(data.get("phone") or ""),
        "email":str(data.get("email") or ""),
        "official_website":official,
    }
    prompt=(
        "You are the web-discovery layer of Velora, a hospitality audit system. "
        "Use live web search to identify the exact public OTA listing pages belonging to ONE lodging property. "
        "The property name may contain typos or differ from OTA naming, so reason across name variants, physical address, city, "
        "official website, phone, email, snippets, and other public corroborating signals. "
        "Search broadly first, then use targeted searches for Booking.com, Airbnb, Expedia, Hotels.com, Vrbo, Agoda, Trip.com and HolidayCheck. "
        "Return FOUND only when the URL is a specific listing/profile page attributable to this exact property; never return a homepage, search page, "
        "destination page or guessed URL. If evidence is insufficient, return uncertain/not_found instead of inventing. "
        "Do not report Google Hotels as one of the OTA ids in the schema. "
        "Property identity JSON: " + json.dumps(identity,ensure_ascii=False)
    )
    payload={
        "model":str(os.environ.get("VELORA_OPENAI_MODEL") or "gpt-5.5"),
        "tools":[{"type":"web_search"}],
        "tool_choice":"required",
        "input":prompt,
        "text":{
            "format":{
                "type":"json_schema",
                "name":"velora_ota_discovery",
                "strict":True,
                "schema":_ai_discovery_schema(),
            }
        },
        "max_output_tokens":3500,
    }
    try:
        response=requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization":f"Bearer {api_key}",
                "Content-Type":"application/json",
            },
            json=payload,
            timeout=90,
        )
        if response.status_code>=400:
            detail=re.sub(r"\s+"," ",response.text or "")[:300]
            return {"status":"api_error","discoveries":{},"evidence":f"OpenAI API HTTP {response.status_code}: {detail}"}
        raw=response.json()
        text=_extract_response_output_text(raw)
        if not text:
            return {"status":"empty_response","discoveries":{},"evidence":"OpenAI web search non ha restituito output strutturato."}
        parsed=json.loads(text)
        discoveries={}
        for item in parsed.get("listings") or []:
            ota_id=str(item.get("ota_id") or "")
            status=str(item.get("status") or "")
            url=str(item.get("url") or "").strip()
            confidence=float(item.get("confidence") or 0)
            classified=_classify_ota_url(url) if url else ""
            if ota_id not in OTA_META:
                continue
            if status=="found" and url and classified==ota_id and confidence>=0.78:
                discoveries[ota_id]={
                    "status":"found",
                    "url":url,
                    "title":str(item.get("title") or "")[:220],
                    "score":round(confidence,3),
                    "evidence":(
                        "Fallback AI web search: scheda individuata tramite ricerca web live e attribuita alla struttura. "
                        + str(item.get("evidence") or "")
                    )[:900],
                    "searchUrl":"",
                    "discoveryMode":"OpenAI web_search fallback",
                    "verification":"web_search_evidence",
                }
            elif status in {"found","uncertain"} and url and classified==ota_id:
                discoveries[ota_id]={
                    "status":"needs_review",
                    "url":url,
                    "title":str(item.get("title") or "")[:220],
                    "score":round(confidence,3),
                    "evidence":(
                        "Fallback AI web search: candidato trovato ma confidenza insufficiente per accettarlo automaticamente. "
                        + str(item.get("evidence") or "")
                    )[:900],
                    "searchUrl":"",
                    "discoveryMode":"OpenAI web_search fallback",
                }
        return {
            "status":"ok",
            "discoveries":discoveries,
            "propertyMatch":parsed.get("property_match") or {},
            "evidence":f"OpenAI web search completata; {len(discoveries)} OTA candidate/risolte.",
        }
    except Exception as exc:
        return {
            "status":"error","discoveries":{},
            "evidence":f"OpenAI web search non completata: {type(exc).__name__}: {str(exc)[:220]}"
        }


async def discover_otas_with_ai_web_search(data: dict) -> dict:
    return await asyncio.to_thread(_run_ai_web_search,data)


async def discover_all_ota_sources(context, data: dict, robots: dict) -> tuple[dict,dict]:
    """Pipeline: master search -> analisi risultati -> ricerca mirata delle OTA mancanti."""
    discoveries,diagnostics=await discover_otas_from_master_search(context,data,robots)
    for ota_id in OTA_DISCOVERY_ORDER:
        current=discoveries.get(ota_id)
        if current and current.get("status")=="found":
            continue
        targeted=await discover_single_ota_targeted(context,ota_id,data,robots)
        if targeted.get("status")=="found":
            discoveries[ota_id]=targeted
        elif ota_id not in discoveries:
            discoveries[ota_id]=targeted
    return discoveries,diagnostics


async def generic_ota_quote_candidates(page, stay: dict) -> list[dict]:
    """FOURTH STEP: estrae prezzi visibili dal portale trovato, senza inventare condizioni."""
    rows=await page.evaluate(r"""() => {
      const selectors=[
        '[data-testid*="price"]','[class*="price"]','[data-stid*="price"]',
        '[data-testid*="room"]','[class*="room"]'
      ];
      const result=[]; const seen=new Set();
      for (const selector of selectors) {
        for (const node of Array.from(document.querySelectorAll(selector)).slice(0,160)) {
          const container=node.closest('article,li,tr,[data-testid*="room"],[class*="room"],div') || node;
          const text=(container.innerText || container.textContent || '').replace(/\s+/g,' ').trim();
          if (!text || text.length<8 || seen.has(text)) continue;
          seen.add(text); result.push(text.slice(0,1800));
        }
      }
      return result.slice(0,100);
    }""")
    out=[]
    for text_value in rows:
        total=_money_value(str(text_value))
        if total is None:
            continue
        low=str(text_value).lower()
        explicit=any(token in low for token in (f"{stay['nights']} nott","totale","total","price for","prezzo per"))
        out.append({
            "roomType":"Tipologia camera da verificare",
            "total":round(total,2),"currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
            "board":"Trattamento da verificare","refund":"Cancellazione da verificare",
            "audience":"Pubblico senza login","taxes":"Da verificare nel dettaglio del preventivo",
            "verified":False,
            "evidence":str(text_value)[:900] + (" | Totale soggiorno esplicito." if explicit else ""),
        })
    unique=[]; seen=set()
    for item in out:
        key=(item["total"],item["evidence"][:180])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:12]


def booking_search_url(property_name: str, city: str = "") -> str:
    query = " ".join(part for part in (property_name.strip(), city.strip()) if part)
    return "https://www.booking.com/searchresults.it.html?" + urlencode({
        "ss": query,
        "group_adults": "2",
        "no_rooms": "1",
        "group_children": "0",
    })


def external_search_urls(property_name: str, city: str = "", address: str = "", website: str = "") -> list[tuple[str, str]]:
    base = f'site:booking.com/hotel/ "{property_name.strip()}"'
    queries = [" ".join(part for part in (base, city.strip()) if part)]
    if address.strip():
        queries.append(" ".join(part for part in (base, f'"{address.strip()}"', city.strip()) if part))
    try:
        host=(urlparse(website).hostname or "").lower().removeprefix("www.")
    except Exception:
        host=""
    if host:
        queries.append(" ".join(part for part in (base, host, city.strip()) if part))
    result=[]
    seen=set()
    for query in queries:
        if not query or query in seen:
            continue
        seen.add(query)
        result.extend([
            ("Bing", "https://www.bing.com/search?" + urlencode({"q": query, "setlang": "it"})),
            ("Google", "https://www.google.com/search?" + urlencode({"q": query, "hl": "it"})),
        ])
    return result


def _slugify_booking(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    return "-".join(re.findall(r"[a-z0-9]+", ascii_text))


def booking_slug_candidates(property_name: str, city: str = "") -> list[str]:
    name = _slugify_booking(property_name)
    city_slug = _slugify_booking(city)
    candidates = []
    if name:
        candidates.append(name)
        if city_slug and not name.endswith("-" + city_slug):
            candidates.append(f"{name}-{city_slug}")
        # Booking usa spesso descrittori ricettivi nel path anche quando il nome ufficiale è più corto.
        for descriptor in ("aparthotel", "hotel", "resort", "suites", "apartments"):
            if descriptor not in name:
                expanded = f"{name}-{descriptor}"
                candidates.append(expanded)
                if city_slug:
                    candidates.append(f"{expanded}-{city_slug}")
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


async def discover_booking_via_direct_candidates(context, property_name: str, city: str, robots: dict) -> dict:
    checked = []
    for slug in booking_slug_candidates(property_name, city)[:14]:
        url = f"https://www.booking.com/hotel/it/{slug}.it.html"
        permission = await asyncio.to_thread(allowed_by_robots, url, robots)
        if permission is not True:
            checked.append(f"{slug}: robots")
            continue
        page = await context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await page.wait_for_timeout(900)
            if not response or response.status >= 400:
                checked.append(f"{slug}: HTTP {response.status if response else 'n.d.'}")
                continue
            body = (await page.locator("body").inner_text(timeout=6000))[:14000]
            lowered = body.lower()
            if any(word in lowered for word in BLOCK_WORDS):
                checked.append(f"{slug}: blocco")
                continue
            title = ""
            for selector in ('[data-testid="title"]', '[data-testid="property-title"]', '.pp-header__title', 'h1'):
                try:
                    loc = page.locator(selector).first
                    if await loc.count():
                        title = re.sub(r"\s+", " ", (await loc.inner_text(timeout=500)) or "").strip()
                        if title:
                            break
                except Exception:
                    pass
            observed = title or (await page.title())
            score = _name_similarity(property_name, observed)
            if city and city.lower() in body.lower():
                score = min(1.0, score + 0.08)
            checked.append(f"{slug}: {score:.0%}")
            if score >= 0.66:
                clean_url = urlunparse(urlparse(page.url)._replace(query="", fragment=""))
                return {
                    "status": "found",
                    "url": clean_url,
                    "title": observed[:220],
                    "score": round(score, 3),
                    "evidence": (
                        f"Booking.com: verificato direttamente il percorso candidato «{slug}». "
                        f"La pagina mostra «{observed}» con similarità {score:.0%} rispetto a «{property_name}». "
                        f"URL osservato: {clean_url}"
                    )[:900],
                    "searchUrl": "",
                    "discoveryMode": "direct-slug-candidate",
                }
        except Exception as exc:
            checked.append(f"{slug}: {type(exc).__name__}")
        finally:
            await page.close()
    return {
        "status": "not_found_in_candidates",
        "url": "",
        "title": "",
        "score": 0.0,
        "evidence": "Percorsi Booking candidati verificati senza corrispondenza sufficiente: " + ", ".join(checked[:10]),
        "searchUrl": "",
        "discoveryMode": "direct-slug-candidates",
    }


def booking_candidate_from_search_href(href: str, base_url: str) -> str:
    """Estrae URL Booking diretti anche da redirect Google/Bing."""
    try:
        raw=str(href or "").strip()
        absolute=raw if raw.startswith(("http://","https://")) else ""
        parsed=urlparse(absolute or raw)

        if not absolute and raw.startswith(("/url?","/link?")):
            query=dict(parse_qsl(parsed.query,keep_blank_values=True))
            absolute=query.get("q") or query.get("url") or query.get("u") or ""

        if absolute:
            parsed=urlparse(absolute)
            host=(parsed.hostname or "").lower()
            query=dict(parse_qsl(parsed.query,keep_blank_values=True))

            # Google redirect/click wrapper.
            if "google." in host and parsed.path in {"/url","/aclk"}:
                absolute=query.get("q") or query.get("url") or query.get("adurl") or absolute

            # Bing /ck/a spesso codifica il target in u=a1<base64>.
            if host.endswith("bing.com") and parsed.path.startswith("/ck/"):
                encoded=query.get("u") or ""
                if encoded.startswith("a1"):
                    token=encoded[2:]
                    token += "=" * (-len(token) % 4)
                    try:
                        absolute=base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8","ignore")
                    except Exception:
                        pass

        absolute=unquote(str(absolute or ""))
        parsed=urlparse(absolute)
        host=(parsed.hostname or "").lower()
        if host=="booking.com" or host.endswith(".booking.com"):
            if "/hotel/" in parsed.path:
                return urlunparse(parsed._replace(query="",fragment=""))
    except Exception:
        return ""
    return ""


async def discover_booking_from_official_site(context, website: str, robots: dict) -> dict:
    """Prima strategia: cerca una scheda Booking esplicitamente collegata dal sito ufficiale."""
    if not website:
        return {"status":"not_found","url":"","title":"","score":0.0,"evidence":"Sito ufficiale non disponibile.","discoveryMode":"official-site-links"}
    permission=await asyncio.to_thread(allowed_by_robots,website,robots)
    if permission is not True:
        return {"status":"not_found","url":"","title":"","score":0.0,"evidence":"Sito ufficiale non esaminato per link OTA: robots.txt non consente o non chiarisce l'accesso.","discoveryMode":"official-site-links"}
    page=await context.new_page()
    try:
        response=await page.goto(website,wait_until="domcontentloaded",timeout=25000)
        if not response or response.status>=400:
            return {"status":"not_found","url":"","title":"","score":0.0,"evidence":"Sito ufficiale non leggibile per cercare link Booking.","discoveryMode":"official-site-links"}
        await dismiss_cookie(page)
        await page.wait_for_timeout(700)
        links=await page.evaluate(r"""() => Array.from(document.querySelectorAll('a[href]')).slice(0,600).map(a => ({
          href: a.href || '',
          text: (a.innerText || a.textContent || a.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim().slice(0,240)
        }))""")
        candidates=[]
        for item in links:
            url=booking_candidate_from_search_href(str(item.get("href") or ""),page.url)
            if url:
                candidates.append((url,str(item.get("text") or "")))
        seen=set()
        unique=[]
        for url,text_value in candidates:
            if url in seen:
                continue
            seen.add(url)
            unique.append((url,text_value))
        if len(unique)==1:
            url,text_value=unique[0]
            return {
                "status":"found","url":url,"title":text_value[:220],"score":1.0,
                "evidence":f"Il sito ufficiale contiene un collegamento diretto a Booking.com: {url}",
                "searchUrl":website,"discoveryMode":"official-site-direct-link",
            }
        if len(unique)>1:
            return {
                "status":"needs_review","url":unique[0][0],"title":unique[0][1][:220],"score":0.5,
                "evidence":f"Il sito ufficiale contiene {len(unique)} collegamenti Booking; serve verificarne l'identità prima di scegliere.",
                "searchUrl":website,"discoveryMode":"official-site-multiple-links",
            }
        return {"status":"not_found","url":"","title":"","score":0.0,"evidence":"Nessun link Booking diretto osservato sul sito ufficiale.","searchUrl":website,"discoveryMode":"official-site-links"}
    except Exception as exc:
        return {"status":"not_found","url":"","title":"","score":0.0,"evidence":f"Ricerca link Booking sul sito ufficiale non completata: {type(exc).__name__}.","searchUrl":website,"discoveryMode":"official-site-links"}
    finally:
        await page.close()


async def verify_booking_candidate_page(context, url: str, property_name: str, city: str, address: str, robots: dict) -> dict:
    """Verifica semanticamente una pagina candidata Booking prima di accettarla."""
    permission=await asyncio.to_thread(allowed_by_robots,url,robots)
    if permission is not True:
        return {"ok":False,"score":0.0,"title":"","evidence":"Pagina candidata non verificata per robots.txt."}
    page=await context.new_page()
    try:
        response=await page.goto(url,wait_until="domcontentloaded",timeout=25000)
        if not response or response.status>=400:
            return {"ok":False,"score":0.0,"title":"","evidence":f"Pagina candidata HTTP {response.status if response else 'n.d.'}."}
        await dismiss_cookie(page)
        await page.wait_for_timeout(900)
        body=(await page.locator("body").inner_text(timeout=6500))[:16000]
        title=""
        for selector in ('[data-testid="title"]','[data-testid="property-title"]','.pp-header__title','h1'):
            try:
                loc=page.locator(selector).first
                if await loc.count():
                    title=re.sub(r"\s+"," ",(await loc.inner_text(timeout=500)) or "").strip()
                    if title:
                        break
            except Exception:
                pass
        observed=title or (await page.title())
        score=_name_similarity(property_name,observed)
        reasons=[f"nome pagina {score:.0%}"]
        norm_body=_norm_name(body)
        city_norm=_norm_name(city)
        if city_norm and city_norm in norm_body:
            score=min(1.0,score+0.08)
            reasons.append("città presente")
        address_norm=_norm_name(address)
        if address_norm:
            tokens={t for t in address_norm.split() if len(t)>=3 or t.isdigit()}
            body_tokens=set(norm_body.split())
            ratio=len(tokens & body_tokens)/max(1,len(tokens))
            if ratio>=0.60:
                score=min(1.0,score+0.16)
                reasons.append(f"indirizzo {ratio:.0%}")
            elif ratio>=0.30:
                score=min(1.0,score+0.07)
                reasons.append(f"indirizzo {ratio:.0%}")
        clean_url=urlunparse(urlparse(page.url)._replace(query="",fragment=""))
        return {
            "ok":score>=0.68,
            "score":round(score,3),
            "title":observed[:220],
            "url":clean_url,
            "evidence":", ".join(reasons),
        }
    except Exception as exc:
        return {"ok":False,"score":0.0,"title":"","evidence":f"Verifica pagina candidata fallita: {type(exc).__name__}."}
    finally:
        await page.close()


def _identity_match_score(property_name: str, city: str, address: str, title: str, snippet: str, url: str):
    path_slug=urlparse(url).path.rsplit("/",1)[-1].split(".")[0].replace("-"," ")
    combined=" ".join(part for part in (title, snippet, path_slug) if part)
    name_text_score=_name_similarity(property_name,title)
    name_slug_score=_name_similarity(property_name,path_slug)
    name_context_score=_name_similarity(property_name,snippet[:500])
    name_score=max(name_text_score,name_slug_score,name_context_score)
    score=name_score
    reasons=[f"nome {name_score:.0%}",f"url {name_slug_score:.0%}"]
    combined_norm=_norm_name(combined)
    city_norm=_norm_name(city)
    if city_norm and city_norm in combined_norm:
        score=min(1.0,score+0.08)
        reasons.append("citta coincidente")
    address_norm=_norm_name(address)
    if address_norm:
        address_tokens={t for t in address_norm.split() if len(t)>=3 or t.isdigit()}
        combined_tokens=set(combined_norm.split())
        ratio=len(address_tokens & combined_tokens)/max(1,len(address_tokens))
        if ratio>=0.60:
            score=min(1.0,score+0.14)
            reasons.append(f"indirizzo {ratio:.0%}")
        elif ratio>=0.30:
            score=min(1.0,score+0.06)
            reasons.append(f"indirizzo {ratio:.0%}")
    return score,path_slug,name_text_score,name_slug_score,", ".join(reasons)


async def discover_booking_via_search_engine(context, property_name: str, city: str, address: str = "", website: str = "", robots: dict | None = None) -> dict:
    robots = robots if robots is not None else {}
    weak=[]
    seen_urls=set()
    for engine_name, search_url in external_search_urls(property_name, city, address, website):
        page = await context.new_page()
        try:
            response = await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(1300)
            await dismiss_cookie(page)
            body = (await page.locator("body").inner_text(timeout=7000))[:18000]
            lowered = body.lower()
            if response and response.status >= 400:
                continue
            if any(word in lowered for word in BLOCK_WORDS):
                continue
            links = await page.evaluate(r"""() => Array.from(document.querySelectorAll('a[href]')).slice(0,700).map(a => {
              const box=a.closest('li, article, [data-testid], div') || a.parentElement;
              return {
                href: a.getAttribute('href') || '',
                text: (a.innerText || a.textContent || a.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim().slice(0,320),
                context: (box?.innerText || '').replace(/\s+/g,' ').trim().slice(0,1100)
              };
            })""")
            candidates=[]
            for item in links:
                url=booking_candidate_from_search_href(str(item.get("href","")),page.url)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                text_value=str(item.get("text",""))
                context_text=str(item.get("context",""))
                score,path_slug,text_score,url_score,reasons=_identity_match_score(
                    property_name,city,address,text_value,context_text,url
                )
                candidates.append((score,url,text_value,path_slug,reasons,engine_name,search_url))
            candidates.sort(key=lambda row:row[0],reverse=True)
            for score,url,text_value,path_slug,reasons,engine_name,current_search in candidates[:5]:
                generic=path_slug.lower() in {"","index","hotel","searchresults"}
                if generic:
                    weak.append((score,url,text_value,path_slug,reasons,engine_name,current_search))
                    continue
                if score>=0.70:
                    verify=await verify_booking_candidate_page(context,url,property_name,city,address,robots)
                    if verify.get("ok"):
                        return {
                            "status":"found","url":verify.get("url") or url,
                            "title":verify.get("title") or (text_value.strip() or path_slug),
                            "score":verify.get("score",score),
                            "evidence":(
                                f"{engine_name}: candidato trovato e verificato aprendo la pagina Booking. "
                                f"Ricerca {score:.0%} ({reasons}); verifica pagina {verify.get('score',0):.0%} ({verify.get('evidence','')})."
                            )[:900],
                            "searchUrl":current_search,
                            "discoveryMode":f"{engine_name} search + page verification",
                        }
                weak.append((score,url,text_value,path_slug,reasons,engine_name,current_search))
        except Exception:
            pass
        finally:
            await page.close()

    # Prova a verificare anche i migliori candidati deboli invece di fermarsi al primo snippet.
    weak.sort(key=lambda row:row[0],reverse=True)
    for score,url,text_value,path_slug,reasons,engine_name,current_search in weak[:6]:
        if path_slug.lower() in {"","index","hotel","searchresults"}:
            continue
        verify=await verify_booking_candidate_page(context,url,property_name,city,address,robots)
        if verify.get("ok"):
            return {
                "status":"found","url":verify.get("url") or url,
                "title":verify.get("title") or (text_value.strip() or path_slug),
                "score":verify.get("score",score),
                "evidence":(
                    f"{engine_name}: snippet debole ({score:.0%}) ma pagina Booking verificata direttamente "
                    f"con match {verify.get('score',0):.0%}: {verify.get('evidence','')}."
                )[:900],
                "searchUrl":current_search,
                "discoveryMode":f"{engine_name} weak-result page verification",
            }

    if weak:
        score,url,text_value,path_slug,reasons,engine_name,current_search=weak[0]
        return {
            "status":"needs_review","url":url,"title":(text_value.strip() or path_slug)[:220],"score":round(score,3),
            "evidence":(
                f"Ricerca esterna completata su tutte le varianti. Miglior candidato Booking: "
                f"{score:.0%} ({reasons}), ma la pagina non è stata verificata con sufficiente certezza."
            )[:900],
            "searchUrl":current_search,"discoveryMode":"all-search-variants-exhausted",
        }

    return {
        "status":"not_found_in_search","url":"","title":"","score":0.0,
        "evidence":"Tutte le varianti di ricerca pubblica sono state provate senza trovare una pagina Booking verificabile.",
        "searchUrl":"","discoveryMode":"fallback exhausted",
    }



def _rss_search_queries(property_name: str, city: str = "", address: str = "", website: str = "", phone: str = "", email: str = "") -> list[str]:
    queries=[]
    exact_name=f'"{property_name.strip()}"' if property_name.strip() else ""
    if exact_name:
        queries.append(" ".join(part for part in (exact_name, f'"{city.strip()}"' if city.strip() else "", "Booking.com") if part))
        queries.append(" ".join(part for part in ("site:booking.com/hotel/", exact_name, city.strip()) if part))
    if address.strip():
        queries.append(" ".join(part for part in (exact_name, f'"{address.strip()}"', "Booking.com") if part))
    if phone.strip():
        queries.append(f'"{phone.strip()}" Booking.com')
    if email.strip():
        queries.append(f'"{email.strip()}" Booking.com')
    try:
        host=(urlparse(website).hostname or "").lower().removeprefix("www.")
    except Exception:
        host=""
    if host:
        queries.append(f'"{host}" Booking.com')
    out=[]
    seen=set()
    for query in queries:
        query=" ".join(query.split())
        if query and query not in seen:
            seen.add(query)
            out.append(query)
    return out


def _bing_rss_items(query: str) -> list[dict]:
    try:
        response=requests.get(
            "https://www.bing.com/search",
            params={"q":query,"format":"rss","setlang":"it"},
            headers={"Accept":"application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"},
            impersonate="chrome",
            timeout=12,
        )
        if response.status_code >= 400:
            return []
        root=ET.fromstring(response.text)
        items=[]
        for item in root.findall(".//item")[:20]:
            title=(item.findtext("title") or "").strip()
            link=(item.findtext("link") or "").strip()
            description=(item.findtext("description") or "").strip()
            items.append({"title":title,"link":link,"description":description})
        return items
    except Exception:
        return []


async def discover_booking_via_rss(context, property_name: str, city: str, address: str, website: str, phone: str, email: str, robots: dict) -> dict:
    """Fallback testuale: usa risultati RSS pubblici e poi verifica la pagina Booking reale."""
    weak=[]
    seen=set()
    for query in _rss_search_queries(property_name,city,address,website,phone,email):
        items=await asyncio.to_thread(_bing_rss_items,query)
        for item in items:
            raw_link=str(item.get("link") or "")
            candidate=booking_candidate_from_search_href(raw_link,"https://www.bing.com/")
            if not candidate:
                # Alcuni feed mostrano l'URL Booking nella descrizione.
                desc=unquote(str(item.get("description") or ""))
                match=re.search(r'https?://[^\s<>"\']*booking\.com/hotel/[^\s<>"\']+',desc,re.I)
                if match:
                    candidate=booking_candidate_from_search_href(match.group(0),"https://www.bing.com/")
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            title=str(item.get("title") or "")
            description=re.sub(r"<[^>]+>"," ",str(item.get("description") or ""))
            score,path_slug,text_score,url_score,reasons=_identity_match_score(
                property_name,city,address,title,description,candidate
            )
            generic=path_slug.lower() in {"","index","hotel","searchresults"}
            if generic:
                weak.append((score,candidate,title,path_slug,reasons,query))
                continue
            verify=await verify_booking_candidate_page(context,candidate,property_name,city,address,robots)
            if verify.get("ok"):
                return {
                    "status":"found",
                    "url":verify.get("url") or candidate,
                    "title":verify.get("title") or title or path_slug,
                    "score":verify.get("score",score),
                    "evidence":(
                        f"Bing RSS: candidato trovato con query «{query}» e verificato aprendo Booking. "
                        f"Match ricerca {score:.0%} ({reasons}); verifica pagina {verify.get('score',0):.0%} "
                        f"({verify.get('evidence','')})."
                    )[:900],
                    "searchUrl":"https://www.bing.com/search?"+urlencode({"q":query}),
                    "discoveryMode":"Bing RSS + page verification",
                }
            weak.append((score,candidate,title,path_slug,reasons,query))

    weak.sort(key=lambda row:row[0],reverse=True)
    if weak:
        score,candidate,title,path_slug,reasons,query=weak[0]
        return {
            "status":"needs_review","url":candidate,"title":(title or path_slug)[:220],"score":round(score,3),
            "evidence":(
                f"Bing RSS ha trovato candidati Booking ma nessuno verificabile con sufficiente certezza. "
                f"Migliore: {score:.0%} ({reasons}) con query «{query}»."
            )[:900],
            "searchUrl":"https://www.bing.com/search?"+urlencode({"q":query}),
            "discoveryMode":"Bing RSS exhausted",
        }
    return {
        "status":"not_found_in_rss","url":"","title":"","score":0.0,
        "evidence":"Le ricerche RSS pubbliche non hanno restituito una pagina Booking verificabile.",
        "searchUrl":"","discoveryMode":"Bing RSS exhausted",
    }


async def discover_booking_source(context, property_name: str, city: str, robots: dict, address: str = "", website: str = "", phone: str = "", email: str = "") -> dict:
    official = await discover_booking_from_official_site(context, website, robots)
    if official.get("status") == "found":
        return official
    search_url = booking_search_url(property_name, city)
    permission = await asyncio.to_thread(allowed_by_robots, search_url, robots)
    if permission is not True:
        direct = await discover_booking_via_direct_candidates(context, property_name, city, robots)
        if direct.get("status") == "found":
            direct["evidence"] = (
                "La ricerca interna Booking.com non è stata usata perché robots.txt non ne consente o non chiarisce l'accesso automatico. "
                + str(direct.get("evidence") or "")
            )[:900]
            return direct
        fallback = await discover_booking_via_search_engine(context, property_name, city, address, website, robots)
        if fallback.get("status") == "found":
            fallback["evidence"] = (
                "La ricerca interna Booking.com non è stata usata perché robots.txt non ne consente o non chiarisce l'accesso automatico. "
                + str(fallback.get("evidence") or "")
            )[:900]
            return fallback
        rss = await discover_booking_via_rss(context, property_name, city, address, website, phone, email, robots)
        if rss.get("status") == "found":
            rss["evidence"] = (
                "La ricerca interna Booking.com non era utilizzabile; fallback RSS pubblico. "
                + str(rss.get("evidence") or "")
            )[:900]
            return rss
        return {
            "status": "robots_denied" if permission is False else "robots_unavailable",
            "url": "", "title": "", "score": 0.0,
            "evidence": (
                "Ricerca interna Booking.com non eseguita: robots.txt nega o non chiarisce l'accesso automatico. "
                + str(fallback.get("evidence") or "")
            )[:900],
            "searchUrl": search_url,
        }

    page = await context.new_page()
    try:
        response = await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1800)
        await dismiss_cookie(page)
        body = (await page.locator("body").inner_text(timeout=7000))[:20000]
        lowered = body.lower()
        if response and response.status >= 400:
            return {"status": "http_error", "url": "", "title": "", "score": 0.0,
                    "evidence": f"Ricerca Booking.com: HTTP {response.status}.", "searchUrl": search_url}
        if any(word in lowered for word in BLOCK_WORDS):
            return {"status": "blocked", "url": "", "title": "", "score": 0.0,
                    "evidence": "Booking.com ha mostrato una pagina di verifica/blocco; nessun aggiramento tentato.",
                    "searchUrl": search_url}

        cards = await page.evaluate(r"""() => {
          const abs = (u) => { try { return new URL(u, location.href).href; } catch { return ''; } };
          const result = [];
          const seen = new Set();
          const cardNodes = Array.from(document.querySelectorAll('[data-testid="property-card"]'));
          for (const card of cardNodes.slice(0, 40)) {
            const link = card.querySelector('a[data-testid="title-link"], a[href*="/hotel/"]');
            const titleNode = card.querySelector('[data-testid="title"], [data-testid="property-title"], h3');
            const href = link ? abs(link.getAttribute('href') || '') : '';
            const title = (titleNode?.textContent || link?.textContent || '').replace(/\s+/g,' ').trim();
            const text = (card.innerText || '').replace(/\s+/g,' ').trim().slice(0, 1200);
            if (href && title && !seen.has(href)) { seen.add(href); result.push({href, title, text}); }
          }
          if (!result.length) {
            for (const link of Array.from(document.querySelectorAll('a[href*="/hotel/"]')).slice(0, 80)) {
              const href = abs(link.getAttribute('href') || '');
              const title = (link.textContent || link.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim();
              if (href && title && !seen.has(href)) { seen.add(href); result.push({href, title, text: title}); }
            }
          }
          return result;
        }""")
        scored = []
        for item in cards:
            raw_url=str(item.get("href", ""))
            score,path_slug,text_score,url_score,reasons = _identity_match_score(
                property_name,
                city,
                address,
                str(item.get("title", "")),
                str(item.get("text", "")),
                raw_url,
            )
            scored.append((score, item, path_slug, text_score, url_score, reasons))
        scored.sort(key=lambda row: row[0], reverse=True)
        if not scored:
            direct = await discover_booking_via_direct_candidates(context, property_name, city, robots)
            if direct.get("status") == "found":
                direct["evidence"] = (
                    f"Ricerca Booking.com eseguita per «{property_name}{' ' + city if city else ''}» senza scheda riconoscibile; "
                    + str(direct.get("evidence") or "")
                )[:900]
                return direct
            fallback = await discover_booking_via_search_engine(context, property_name, city, address, website, robots)
            if fallback.get("status") == "found":
                fallback["evidence"] = (
                    f"Ricerca Booking.com eseguita per «{property_name}{' ' + city if city else ''}» senza scheda riconoscibile; "
                    + str(fallback.get("evidence") or "")
                )[:900]
                return fallback
            rss = await discover_booking_via_rss(context, property_name, city, address, website, phone, email, robots)
            if rss.get("status") == "found":
                rss["evidence"] = (
                    f"Ricerca Booking interna e browser-search non conclusive per «{property_name}»; "
                    + str(rss.get("evidence") or "")
                )[:900]
                return rss
            return {
                "status": "not_found_in_search", "url": "", "title": "", "score": 0.0,
                "evidence": (
                    f"Ricerca Booking.com eseguita per «{property_name}{' ' + city if city else ''}»: nessuna scheda struttura riconoscibile nel risultato visibile. "
                    + str(fallback.get("evidence") or "")
                )[:900],
                "searchUrl": search_url,
            }

        score, item, path_slug, text_score, url_score, reasons = scored[0]
        clean_url = urlunparse(urlparse(str(item.get("href", "")))._replace(query="", fragment=""))
        raw_title=str(item.get("title", "")).strip()
        generic_candidate = path_slug.lower() in {"", "index", "hotel", "searchresults"} or raw_title.lower() in {"", "hotel", "booking.com", "index"}
        display_title=raw_title if raw_title.lower() not in {"", "hotel", "booking.com", "index"} else path_slug
        if score >= 0.68 and not generic_candidate:
            return {
                "status": "found", "url": clean_url, "title": display_title[:220],
                "score": round(score, 3),
                "evidence": (
                    f"Booking.com: candidato trovato nella ricerca «{property_name}{' ' + city if city else ''}». "
                    f"Match identità {score:.0%}: {reasons}. URL osservato: {clean_url}"
                )[:900],
                "searchUrl": search_url,
                "discoveryMode": "Booking internal search + identity match",
            }

        # Un risultato interno generico (es. link «Hotel») non deve chiudere la discovery.
        # Prova i candidati diretti e poi i motori pubblici usando anche indirizzo/sito.
        direct = await discover_booking_via_direct_candidates(context, property_name, city, robots)
        if direct.get("status") == "found":
            direct["evidence"] = (
                f"Il miglior risultato della ricerca Booking aveva match identità {score:.0%} ({reasons}); "
                + str(direct.get("evidence") or "")
            )[:900]
            return direct
        fallback = await discover_booking_via_search_engine(context, property_name, city, address, website, robots)
        if fallback.get("status") == "found":
            fallback["evidence"] = (
                f"Il miglior risultato della ricerca Booking aveva match identità {score:.0%} ({reasons}); "
                + str(fallback.get("evidence") or "")
            )[:900]
            return fallback
        rss = await discover_booking_via_rss(context, property_name, city, address, website, phone, email, robots)
        if rss.get("status") == "found":
            rss["evidence"] = (
                f"Il candidato interno Booking era generico/debole ({score:.0%}); fallback RSS pubblico. "
                + str(rss.get("evidence") or "")
            )[:900]
            return rss
        return {
            "status": "needs_review", "url": clean_url, "title": display_title[:220],
            "score": round(score, 3),
            "evidence": (
                f"Booking.com: candidato interno «{display_title}» con match identità {score:.0%} ({reasons}), "
                "non sufficiente. Anche i controlli alternativi non hanno trovato una scheda attribuibile con certezza. "
                + str(fallback.get("evidence") or "")
            )[:900],
            "searchUrl": search_url,
            "discoveryMode": "identity fallback exhausted",
        }
    except Exception as exc:
        return {"status": "navigation_error", "url": "", "title": "", "score": 0.0,
                "evidence": f"Ricerca Booking.com non completata: {type(exc).__name__}: {str(exc)[:180]}",
                "searchUrl": search_url}
    finally:
        await page.close()


def _money_value(text: str) -> float | None:
    match = PRICE_RE.search(text or "")
    if not match:
        return None
    raw = (match.group(1) or match.group(2) or "").replace(".", "").replace(",", ".")
    try:
        value = float(raw)
        return value if value > 0 else None
    except ValueError:
        return None


async def booking_quote_candidates(page, stay: dict) -> list[dict]:
    """Raccoglie candidati camera/prezzo dalla scheda Booking, senza trasformarli automaticamente in ADR."""
    rows = await page.evaluate(r"""() => {
      const result = [];
      const seen = new Set();
      const add = (node, priceNode = null) => {
        if (!node) return;
        const text = (node.innerText || node.textContent || '').replace(/\s+/g,' ').trim();
        if (!text || text.length < 15 || seen.has(text)) return;
        const nameNode = node.querySelector(
          '.hprt-roomtype-link, [data-testid="room-name"], [data-testid*="room-name"], h2, h3, h4, strong'
        );
        const ownPrice = priceNode || node.querySelector(
          '.bui-price-display__value, [data-testid="price-and-discounted-price"], [data-testid*="price"], [class*="price"]'
        );
        seen.add(text);
        result.push({
          text: text.slice(0, 2200),
          room: (nameNode?.textContent || '').replace(/\s+/g,' ').trim().slice(0, 240),
          price: (ownPrice?.textContent || '').replace(/\s+/g,' ').trim().slice(0, 180)
        });
      };

      const rowSelectors = [
        '#hprt-table tbody tr',
        '#hprt-form tbody tr',
        '[data-testid="room-list"] > *',
        '[data-testid="room-card"]',
        '[data-testid*="room-card"]',
        '[data-testid="availability-block"]',
        '[data-testid*="availability"]'
      ];
      for (const selector of rowSelectors) {
        for (const row of Array.from(document.querySelectorAll(selector)).slice(0, 80)) add(row);
      }

      const priceSelectors = [
        '[data-testid="price-and-discounted-price"]',
        '[data-testid*="price"]',
        '.bui-price-display__value',
        '.prco-valign-middle-helper'
      ];
      for (const selector of priceSelectors) {
        for (const priceNode of Array.from(document.querySelectorAll(selector)).slice(0, 100)) {
          const container = priceNode.closest(
            'tr, [data-testid="room-card"], [data-testid*="room-card"], [data-testid="availability-block"], [data-testid*="room"]'
          ) || priceNode.parentElement?.parentElement || priceNode.parentElement;
          add(container, priceNode);
        }
      }
      return result.slice(0, 100);
    }""")
    out = []
    for row in rows:
        text = str(row.get("text", ""))
        room = str(row.get("room", "")).strip() or "Tipologia camera da verificare"
        price_text = str(row.get("price", "")).strip() or text
        total = _money_value(price_text)
        if total is None:
            continue
        low = text.lower()
        board = "Colazione inclusa" if any(x in low for x in ("colazione inclusa", "breakfast included")) else "Trattamento da verificare"
        refund = "Cancellazione gratuita" if any(x in low for x in ("cancellazione gratuita", "free cancellation")) else (
            "Non rimborsabile" if any(x in low for x in ("non rimborsabile", "non-refundable")) else "Cancellazione da verificare"
        )
        total_is_explicit = any(x in low for x in (
            f"{stay['nights']} nott", "prezzo per", "price for", "totale", "total",
        ))
        out.append({
            "roomType": room,
            "total": round(total, 2),
            "currency": "EUR",
            "nights": stay["nights"],
            "guests": stay["adults"],
            "board": board,
            "refund": refund,
            "audience": "Pubblico senza login",
            "taxes": "Da verificare nel dettaglio del preventivo",
            "verified": bool(total_is_explicit and room != "Tipologia camera da verificare"),
            "evidence": text[:900],
        })
    # Deduplica per camera/prezzo/testo simile.
    unique=[]
    seen=set()
    for item in out:
        key=(item["roomType"].lower(), item["total"], item["evidence"][:180].lower())
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:20]


def booking_unavailability_message(text: str) -> str:
    lowered=re.sub(r"\s+", " ", (text or "").lower())
    patterns=(
        "non disponibile per le date selezionate",
        "non disponibile nelle date selezionate",
        "non ci sono camere disponibili",
        "nessuna camera disponibile",
        "nessuna disponibilità",
        "al momento non disponibile",
        "struttura al completo",
        "completamente prenotata",
        "sold out",
        "not available for your dates",
        "not available on our site",
        "no rooms available",
        "no availability",
        "fully booked",
    )
    return next((pattern for pattern in patterns if pattern in lowered), "")


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)



def booking_dated_search_url(property_name: str, city: str, stay: dict) -> str:
    query = " ".join(part for part in (property_name.strip(), city.strip()) if part)
    return "https://www.booking.com/searchresults.it.html?" + urlencode({
        "ss": query,
        "checkin": stay["checkin"],
        "checkout": stay["checkout"],
        "group_adults": str(stay.get("adults") or 2),
        "no_rooms": "1",
        "group_children": "0",
    })


async def booking_dated_search_observation(page, source: str, property_name: str, city: str, stay: dict, robots: dict) -> dict:
    requested = booking_dated_search_url(property_name, city, stay)
    record = {
        "otaId": "booking",
        **stay,
        "sourceUrl": source,
        "requestedUrl": requested,
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "status": "dated_search_inconclusive",
        "finalUrl": "",
        "title": "",
        "evidence": "",
        "quotes": [],
    }
    permission = await asyncio.to_thread(allowed_by_robots, requested, robots)
    if permission is not True:
        record["evidence"] = "Ricerca Booking con date non eseguita: robots.txt non consente o non chiarisce l'accesso automatico."
        return record
    try:
        response = await page.goto(requested, wait_until="domcontentloaded", timeout=25000)
        await dismiss_cookie(page)
        try:
            await page.locator("body").wait_for(state="visible", timeout=5000)
            await page.wait_for_timeout(1600)
        except PlaywrightTimeout:
            pass
        record["finalUrl"] = page.url
        record["title"] = (await page.title())[:200]
        if response and response.status >= 400:
            record.update(status="http_error", evidence=f"Ricerca Booking con date: HTTP {response.status}.")
            return record

        final_dates_ok = booking_url_dates_confirmed(page.url, stay)
        cards = await page.evaluate(r"""() => {
          const abs = (u) => { try { return new URL(u, location.href).href; } catch { return ''; } };
          const result = [];
          for (const card of Array.from(document.querySelectorAll('[data-testid="property-card"]')).slice(0, 60)) {
            const link = card.querySelector('a[data-testid="title-link"], a[href*="/hotel/"]');
            const titleNode = card.querySelector('[data-testid="title"], [data-testid="property-title"], h3');
            const priceNode = card.querySelector('[data-testid="price-and-discounted-price"], [data-testid*="price"]');
            result.push({
              href: link ? abs(link.getAttribute('href') || '') : '',
              title: (titleNode?.textContent || link?.textContent || '').replace(/\s+/g,' ').trim().slice(0,240),
              text: (card.innerText || '').replace(/\s+/g,' ').trim().slice(0,1800),
              price: (priceNode?.textContent || '').replace(/\s+/g,' ').trim().slice(0,160)
            });
          }
          return result;
        }""")

        source_path=(urlparse(source).path or "").rstrip("/").lower()
        best=None
        for item in cards:
            href=str(item.get("href") or "")
            candidate_path=(urlparse(href).path or "").rstrip("/").lower()
            exact_path=bool(source_path and candidate_path and source_path==candidate_path)
            score=_name_similarity(property_name, str(item.get("title") or ""))
            if exact_path:
                score=1.0
            elif city and city.lower() in str(item.get("text") or "").lower():
                score=min(1.0, score+0.08)
            row=(score, exact_path, item)
            if best is None or row[0]>best[0]:
                best=row

        if not best or best[0] < 0.68:
            body=(await page.locator("body").inner_text(timeout=7000))[:9000]
            record["evidence"]=(
                f"Ricerca Booking con date {stay['checkin']} → {stay['checkout']} eseguita, "
                "ma la scheda esatta della struttura non è stata isolata con sufficiente certezza. "
                f"Date nella URL finale: {'sì' if final_dates_ok else 'no'}. "
                f"Estratto: {re.sub(r'\s+', ' ', body)[:280]}"
            )[:900]
            return record

        score, exact_path, item = best
        card_text=str(item.get("text") or "")
        low=card_text.lower()
        unavailable_terms=(
            "non disponibile per le date selezionate",
            "non disponibile nelle date selezionate",
            "nessuna disponibilità",
            "nessuna camera disponibile",
            "sold out",
            "not available for your dates",
            "no availability",
            "no rooms available",
        )
        unavailable_hit=next((term for term in unavailable_terms if term in low), "")
        total=_money_value(str(item.get("price") or "") or card_text)

        if final_dates_ok and unavailable_hit:
            record.update(
                status="no_public_rate",
                evidence=(
                    f"Date confermate nella ricerca Booking: {stay['checkin']} → {stay['checkout']}. "
                    f"Scheda esatta {'per URL' if exact_path else 'per nome'}: «{item.get('title','')}». "
                    f"Il portale mostra un messaggio di indisponibilità («{unavailable_hit}»). "
                    "Esito: nessuna tariffa pubblica prenotabile rilevata per queste date; la causa non è determinabile automaticamente."
                )[:900],
            )
            return record

        if final_dates_ok and total is not None:
            quote={
                "roomType": "Tipologia camera da verificare",
                "total": round(total,2),
                "currency": "EUR",
                "nights": stay["nights"],
                "guests": stay["adults"],
                "board": "Trattamento da verificare",
                "refund": "Cancellazione da verificare",
                "audience": "Pubblico senza login",
                "taxes": "Da verificare nel dettaglio del preventivo",
                "verified": False,
                "evidence": card_text[:700],
            }
            record["quotes"]=[quote]
            record.update(
                status="quote_candidates_unverified",
                evidence=(
                    f"Date confermate nella ricerca Booking: {stay['checkin']} → {stay['checkout']}. "
                    f"Scheda esatta {'per URL' if exact_path else 'per nome'}: «{item.get('title','')}». "
                    f"Prezzo totale visibile nel risultato: €{total:.2f}. "
                    "La tipologia fisica della camera e le condizioni restano da verificare prima di usare il dato nel delta."
                )[:900],
            )
            return record

        record["evidence"]=(
            f"Ricerca Booking con date {stay['checkin']} → {stay['checkout']} e scheda «{item.get('title','')}» individuata "
            f"(match {score:.0%}); date nella URL finale: {'sì' if final_dates_ok else 'no'}. "
            "Nessun prezzo o messaggio di indisponibilità attribuibile con sufficiente certezza nella card."
        )[:900]
        return record
    except Exception as exc:
        record.update(status="navigation_error", evidence=f"Ricerca Booking con date non completata: {type(exc).__name__}: {str(exc)[:180]}")
        return record


async def booking_settle_render(page) -> dict:
    """Attende e stimola il rendering della sezione disponibilita' senza aggirare blocchi."""
    diagnostics={"bodyLength":0,"priceNodes":0,"roomNodes":0,"availabilityNodes":0,"reloaded":False}
    async def inspect():
        try:
            return await page.evaluate(r"""() => {
              const bodyText=(document.body?.innerText || '').replace(/\s+/g,' ').trim();
              return {
                bodyLength: bodyText.length,
                priceNodes: document.querySelectorAll(
                  '[data-testid="price-and-discounted-price"], [data-testid*="price"], .bui-price-display__value, .prco-valign-middle-helper'
                ).length,
                roomNodes: document.querySelectorAll(
                  '#hprt-table tbody tr, #hprt-form tbody tr, [data-testid="room-card"], [data-testid*="room-card"], [data-testid="room-list"] > *'
                ).length,
                availabilityNodes: document.querySelectorAll(
                  '#hprt-table, #hprt-form, [data-testid="availability-block"], [data-testid*="availability"]'
                ).length
              };
            }""")
        except Exception:
            return {"bodyLength":0,"priceNodes":0,"roomNodes":0,"availabilityNodes":0}

    try:
        target, _ = await _first_visible_locator(page, (
            '#hprt-table',
            '#hprt-form',
            '[data-testid="availability-block"]',
            '[data-testid*="availability"]',
            '[data-testid="room-list"]',
        ))
        if target is not None:
            try:
                await target.scroll_into_view_if_needed(timeout=1200)
            except Exception:
                pass
        else:
            await page.evaluate("window.scrollTo(0, Math.min(document.body.scrollHeight, 1800))")
        await page.wait_for_timeout(2200)
    except Exception:
        pass

    diagnostics.update(await inspect())
    meaningful = (
        diagnostics["bodyLength"] >= 500
        or diagnostics["priceNodes"] > 0
        or diagnostics["roomNodes"] > 0
        or diagnostics["availabilityNodes"] > 0
    )
    if meaningful:
        return diagnostics

    # Una sola ricarica prudente: se il DOM e' rimasto quasi vuoto aspetta una seconda idratazione.
    try:
        await page.reload(wait_until="domcontentloaded", timeout=20000)
        diagnostics["reloaded"]=True
        await dismiss_cookie(page)
        await page.wait_for_timeout(3000)
        try:
            target, _ = await _first_visible_locator(page, (
                '#hprt-table',
                '#hprt-form',
                '[data-testid="availability-block"]',
                '[data-testid*="availability"]',
                '[data-testid="room-list"]',
            ))
            if target is not None:
                await target.scroll_into_view_if_needed(timeout=1200)
        except Exception:
            pass
        await page.wait_for_timeout(1600)
        diagnostics.update(await inspect())
        diagnostics["reloaded"]=True
    except Exception:
        pass
    return diagnostics


async def observe(page, channel: str, source: str, stay: dict, robots: dict) -> dict:
    requested = dated_url(channel, source, stay)
    record = {"otaId": channel, **stay, "sourceUrl": source, "requestedUrl": requested or source,
              "observedAt": datetime.now(timezone.utc).isoformat(), "status": "not_attempted",
              "finalUrl": "", "title": "", "evidence": "", "quotes": []}
    if requested is None:
        record.update(status="date_adapter_missing",
                      evidence="La scheda è nota, ma il pilota non conosce ancora un percorso verificato per applicare le date su questo portale.")
        return record
    permission = await asyncio.to_thread(allowed_by_robots, requested, robots)
    if permission is not True:
        record.update(status="robots_denied" if permission is False else "robots_unavailable",
                      evidence="Rilevazione non avviata: robots.txt nega o non chiarisce l'accesso automatico.")
        return record
    try:
        response = await page.goto(requested, wait_until="domcontentloaded", timeout=25000)
        if channel == "booking":
            await dismiss_cookie(page)
        # Il contenuto OTA spesso compare dopo il primo DOM; il limite resta breve.
        try:
            await page.locator("body").wait_for(state="visible", timeout=5000)
            await page.wait_for_timeout(1500)
        except PlaywrightTimeout:
            pass

        async def snapshot_and_confirm():
            current_title=(await page.title())[:200]
            current_body=(await page.locator("body").inner_text(timeout=7000))[:12000]
            confirmed=visible_dates_confirmed(current_body, stay)
            mode="visible-text" if confirmed else ""
            dom_excerpt=""
            if channel == "booking" and not confirmed:
                confirmed, dom_excerpt = await booking_dom_dates_confirmed(page, stay)
                if confirmed:
                    mode="booking-dom-fields"
            if channel == "booking" and not confirmed and booking_url_dates_confirmed(page.url, stay):
                property_context, context_evidence = await booking_property_rate_context(page)
                if property_context:
                    confirmed=True
                    mode="booking-final-url+rate-context"
                    dom_excerpt=(
                        "URL finale Booking mantiene check-in/check-out richiesti; "
                        f"contesto tariffario DOM: {context_evidence or 'scheda struttura'}"
                    )
            return current_title,current_body,confirmed,mode,dom_excerpt

        record["finalUrl"] = page.url
        record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
        ui_date_evidence=""
        if channel == "booking" and not dates_confirmed:
            applied, ui_date_evidence = await booking_apply_dates_via_ui(page, stay)
            if applied:
                record["finalUrl"] = page.url
                record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
                if dates_confirmed and not date_confirmation_mode:
                    date_confirmation_mode="booking-ui-date-picker"
        render_diag={}
        if channel == "booking" and dates_confirmed:
            render_diag = await booking_settle_render(page)
            record["finalUrl"] = page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
        text = (record["title"] + " " + body).lower()
        if response and response.status >= 400:
            record.update(status="http_error", evidence=f"HTTP {response.status}")
        elif any(word in text for word in BLOCK_WORDS):
            record.update(status="blocked", evidence="Il portale ha mostrato una pagina di verifica/blocco; nessun prezzo acquisito.")
        elif not body.strip():
            record.update(status="empty_page", evidence="Pagina senza contenuto leggibile nel campione.")
        elif not dates_confirmed:
            detail = f" Stato DOM date: {date_dom_excerpt}" if date_dom_excerpt else ""
            ui_detail = f" Tentativo date picker: {ui_date_evidence}." if ui_date_evidence else ""
            record.update(
                status="dates_unconfirmed",
                evidence=(
                    f"Le date richieste {stay['checkin']} → {stay['checkout']} non sono confermate nel contenuto visibile o nei campi data del portale; "
                    f"i prezzi non vengono utilizzati. URL finale: {page.url}." + detail + ui_detail
                )[:900],
            )
        else:
            if channel == "booking":
                unavailable_hit = booking_unavailability_message(body)
                if unavailable_hit:
                    record.update(
                        status="no_public_rate",
                        evidence=(
                            f"Date confermate ({date_confirmation_mode or 'pagina renderizzata'}): "
                            f"{stay['checkin']} → {stay['checkout']}. "
                            f"Booking mostra un messaggio di indisponibilità («{unavailable_hit}»). "
                            "Esito: nessuna tariffa pubblica prenotabile rilevata per queste date; "
                            "la causa non è determinabile automaticamente."
                        )[:900],
                    )
                    candidates = []
                else:
                    candidates = await booking_quote_candidates(page, stay)
                record["quotes"] = candidates
                verified = [item for item in candidates if item.get("verified")]
                if unavailable_hit:
                    pass
                elif verified:
                    first = verified[0]
                    record.update(
                        status="quote_candidates",
                        evidence=(
                            f"Date confermate ({date_confirmation_mode or 'pagina renderizzata'}). Rilevati {len(candidates)} candidati camera/prezzo; "
                            f"{len(verified)} riportano nella stessa riga un riferimento compatibile con totale/soggiorno. "
                            f"Esempio: {first['roomType']} · €{first['total']:.2f} per {stay['nights']} notti. "
                            "Tasse e identità fisica dell'unità restano da verificare prima del delta."
                        )
                    )
                elif candidates:
                    record.update(
                        status="quote_candidates_unverified",
                        evidence=(
                            f"Date confermate ({date_confirmation_mode or 'pagina renderizzata'}) e {len(candidates)} righe camera/prezzo rilevate, ma il totale del soggiorno "
                            "non è attribuibile automaticamente con sufficiente certezza."
                        )
                    )
                else:
                    excerpt=re.sub(r"\s+", " ", body)[:500]
                    diag=(
                        f"DOM: testo {render_diag.get('bodyLength', len(body))} caratteri, "
                        f"prezzi {render_diag.get('priceNodes', 0)}, camere {render_diag.get('roomNodes', 0)}, "
                        f"blocchi disponibilità {render_diag.get('availabilityNodes', 0)}, "
                        f"reload {'sì' if render_diag.get('reloaded') else 'no'}."
                    )
                    debug_path=""
                    try:
                        debug_dir=Path(__file__).resolve().parent/"tmp"
                        debug_dir.mkdir(parents=True,exist_ok=True)
                        debug_file=debug_dir/f"booking-debug-{stay['month']}.png"
                        await page.screenshot(path=str(debug_file), full_page=False)
                        debug_path=str(debug_file)
                    except Exception:
                        debug_path=""
                    record.update(
                        status="needs_human_review",
                        evidence=(
                            "Date confermate, ma nessun prezzo e nessun messaggio esplicito di indisponibilità sono stati "
                            "attribuiti automaticamente con sufficiente certezza nella scheda struttura. "
                            + diag + " "
                            + (f"Screenshot diagnostico: {debug_path}. " if debug_path else "")
                            + f"Estratto osservato: {excerpt}"
                        )[:900],
                    )
            else:
                candidates=await generic_ota_quote_candidates(page,stay)
                record["quotes"]=candidates
                if candidates:
                    first=candidates[0]
                    record.update(
                        status="quote_candidates_unverified",
                        evidence=(
                            f"Date confermate nel portale. Rilevati {len(candidates)} candidati prezzo visibili. "
                            f"Esempio €{first['total']:.2f}; camera, tasse e condizioni restano da verificare prima del confronto."
                        )[:900],
                    )
                else:
                    record.update(
                        status="needs_human_review",
                        evidence="Date visibili, ma nessun prezzo attribuibile automaticamente con sufficiente certezza nella pagina OTA."
                    )
        # Solo una breve traccia testuale: evita di salvare intere pagine e dati ospite.
        record["visibleExcerpt"] = re.sub(r"\s+", " ", body)[:350]
    except Exception as exc:
        record.update(status="navigation_error", evidence=f"{type(exc).__name__}: {str(exc)[:180]}")
    return record


def _is_generic_property_name(value: str) -> bool:
    norm=_norm_name(value)
    return not norm or norm in {"hotel","struttura","property","accommodation","alloggio"}


async def resolve_identity_from_official_site(context, data: dict, robots: dict) -> dict:
    """Arricchisce l'identita' dal sito ufficiale quando il catalogo Excel non basta o non contiene la struttura."""
    sources=data.get("sources") or {}
    official_url=((sources.get("sito") or {}).get("url") if isinstance(sources.get("sito"),dict) else "") or ""
    result={
        "source":"input",
        "officialUrl":official_url,
        "status":"input_only",
        "observed":{},
        "evidence":"Identità disponibile dai dati inseriti.",
    }
    if not official_url:
        result["evidence"]="Sito ufficiale non disponibile: uso i dati inseriti."
        return result

    catalog_match=data.get("catalogMatch") if isinstance(data.get("catalogMatch"),dict) else {}
    if catalog_match and catalog_match.get("score") == 1.0:
        result.update(
            source="catalog",
            status="catalog_match",
            evidence=(
                f"Identità confermata dal database locale: {data.get('name','')} · {data.get('city','')} · "
                f"{data.get('address','')} · {catalog_match.get('reason','')}"
            )[:900],
        )
        return result

    permission=await asyncio.to_thread(allowed_by_robots, official_url, robots)
    if permission is not True:
        result.update(
            status="official_site_not_read",
            evidence="Sito ufficiale non letto per la risoluzione identità: robots.txt nega o non chiarisce l'accesso automatico.",
        )
        return result

    page=await context.new_page()
    try:
        response=await page.goto(official_url,wait_until="domcontentloaded",timeout=25000)
        await dismiss_cookie(page)
        try:
            await page.locator("body").wait_for(state="visible",timeout=5000)
            await page.wait_for_timeout(900)
        except Exception:
            pass
        if response and response.status >= 400:
            result.update(status="official_site_http_error",evidence=f"Sito ufficiale: HTTP {response.status}.")
            return result

        observed=await page.evaluate(r"""() => {
          const text = (value) => (value || '').replace(/\s+/g,' ').trim();
          const out = {
            title: text(document.title),
            h1: text(document.querySelector('h1')?.textContent),
            siteName: text(document.querySelector('meta[property="og:site_name"]')?.content),
            name: '',
            streetAddress: '',
            city: '',
            region: '',
            postalCode: '',
            telephone: '',
            email: '',
            latitude: '',
            longitude: ''
          };
          const types = new Set([
            'hotel','lodgingbusiness','bedandbreakfast','hostel','motel','resort',
            'localbusiness','organization','apartment','accommodation'
          ]);
          const candidates = [];
          const walk = (value) => {
            if (!value) return;
            if (Array.isArray(value)) { for (const item of value) walk(item); return; }
            if (typeof value !== 'object') return;
            if (Array.isArray(value['@graph'])) walk(value['@graph']);
            const rawType=value['@type'];
            const allTypes=(Array.isArray(rawType)?rawType:[rawType]).filter(Boolean).map(v=>String(v).toLowerCase());
            if (allTypes.some(t=>types.has(t))) candidates.push(value);
          };
          for (const script of Array.from(document.querySelectorAll('script[type="application/ld+json"]')).slice(0,30)) {
            try { walk(JSON.parse(script.textContent || 'null')); } catch {}
          }
          const node=candidates[0] || {};
          const address=(node.address && typeof node.address === 'object') ? node.address : {};
          const geo=(node.geo && typeof node.geo === 'object') ? node.geo : {};
          out.name=text(node.name);
          out.streetAddress=text(address.streetAddress);
          out.city=text(address.addressLocality);
          out.region=text(address.addressRegion);
          out.postalCode=text(address.postalCode);
          out.telephone=text(node.telephone);
          out.email=text(node.email);
          out.latitude=text(geo.latitude);
          out.longitude=text(geo.longitude);

          if (!out.email) {
            const mail=document.querySelector('a[href^="mailto:"]')?.getAttribute('href') || '';
            out.email=text(mail.replace(/^mailto:/i,'').split('?')[0]);
          }
          if (!out.telephone) {
            const tel=document.querySelector('a[href^="tel:"]')?.getAttribute('href') || '';
            out.telephone=text(tel.replace(/^tel:/i,''));
          }
          return out;
        }""")

        result["observed"]=observed
        changed=[]
        if _is_generic_property_name(str(data.get("name") or "")):
            candidate=str(observed.get("name") or observed.get("siteName") or observed.get("h1") or "").strip()
            if candidate:
                data["name"]=candidate[:180]
                changed.append("nome")
        if not str(data.get("city") or "").strip() and observed.get("city"):
            data["city"]=str(observed["city"])[:100]
            changed.append("città")
        if not str(data.get("province") or "").strip() and observed.get("region"):
            data["province"]=str(observed["region"])[:20]
            changed.append("provincia")
        if not str(data.get("address") or "").strip() and observed.get("streetAddress"):
            address=str(observed["streetAddress"])
            if observed.get("postalCode"):
                address += f", {observed['postalCode']}"
            if observed.get("city"):
                address += f" {observed['city']}"
            data["address"]=address[:240]
            changed.append("indirizzo")
        if not str(data.get("email") or "").strip() and observed.get("email"):
            data["email"]=str(observed["email"])[:180]
            changed.append("email")
        if observed.get("telephone"):
            data["phone"]=str(observed["telephone"])[:80]
        if observed.get("latitude") and observed.get("longitude"):
            data["geo"]={"lat":observed["latitude"],"lng":observed["longitude"]}

        signals=[]
        for key,label in (("name","nome"),("city","città"),("streetAddress","indirizzo"),("telephone","telefono"),("email","email")):
            if observed.get(key):
                signals.append(f"{label}: {observed[key]}")
        result.update(
            source="official_site",
            status="resolved_from_official_site",
            evidence=(
                "Struttura non dipendente dal database Excel. Identità osservata sul sito ufficiale. "
                + ("; ".join(signals[:5]) if signals else f"titolo: {observed.get('title') or observed.get('h1') or 'n.d.'}")
                + (f". Campi arricchiti: {', '.join(changed)}." if changed else ". I dati inseriti erano già sufficienti.")
            )[:900],
        )
        return result
    except Exception as exc:
        result.update(
            status="official_site_error",
            evidence=f"Risoluzione identità dal sito ufficiale non completata: {type(exc).__name__}: {str(exc)[:180]}",
        )
        return result
    finally:
        await page.close()


async def run(args: argparse.Namespace) -> dict:
    data = json.loads(Path(args.property).read_text(encoding="utf-8-sig"))
    today = date.fromisoformat(args.today) if args.today else date.today()
    plan = monthly_plan(today, limit=args.months)
    channels = [part.strip() for part in args.channels.split(",") if part.strip()]
    unknown = set(channels) - set(CHANNELS)
    if unknown:
        raise ValueError(f"Canali sconosciuti: {', '.join(sorted(unknown))}")
    sources = data.get("sources", {})
    result = {"schema": SCHEMA, "propertyId": data["id"], "propertyName": data["name"],
              "createdAt": datetime.now(timezone.utc).isoformat(), "method": "Pilota locale, Chrome pubblico senza login; nessun bypass o prezzo stimato.",
              "plan": plan, "bookingEngine": {"status": "unverified", "provider": "", "url": "", "mode": "",
                                                  "evidence": "Non ancora esaminato."},
              "identityResolution": {}, "masterSearch": {}, "aiWebSearch": {}, "discoveredSources": {}, "observations": []}
    output = Path(args.output)
    if args.dry_run:
        write_result(output, result)
        return result
    robots: dict[str, RobotFileParser | bool | None] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(locale="it-IT", timezone_id="Europe/Rome")
        try:
            identity = await resolve_identity_from_official_site(context, data, robots)
            result["identityResolution"] = identity
            print(
                f"identity resolved: {identity.get('source')} · {data.get('name','')} · {data.get('city','')} · "
                f"{data.get('address','')} · {identity.get('status','')}",
                flush=True,
            )
            try:
                property_path=Path(args.property)
                if property_path.parent.name=="runtime-properties":
                    tmp_property=property_path.with_suffix(".tmp")
                    tmp_property.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                    tmp_property.replace(property_path)
            except OSError:
                pass

            official_identity_url=(sources.get("sito") or {}).get("url","")
            master_discoveries,master_diag=await discover_all_ota_sources(context,data,robots)
            result["masterSearch"]=master_diag
            query_preview=" | ".join((master_diag.get("queries") or [])[:3])
            print(
                f"master search: {master_diag.get('status')} · varianti={len(master_diag.get('queries') or [])} · "
                f"candidati OTA={master_diag.get('candidates',0)} · prime query: {query_preview[:240]}",
                flush=True,
            )

            unresolved=[
                ota_id for ota_id in OTA_DISCOVERY_ORDER
                if (master_discoveries.get(ota_id) or {}).get("status")!="found"
                and not ((sources.get(ota_id) or {}).get("url") if isinstance(sources.get(ota_id),dict) else "")
            ]
            ai_result={"status":"not_needed","discoveries":{}}
            if unresolved:
                ai_result=await discover_otas_with_ai_web_search(data)
                result["aiWebSearch"]=ai_result
                print(
                    f"ai web search: {ai_result.get('status')} · unresolved={len(unresolved)} · "
                    f"risolte={len(ai_result.get('discoveries') or {})} · {str(ai_result.get('evidence') or '')[:180]}",
                    flush=True,
                )
                for ota_id,discovery in (ai_result.get("discoveries") or {}).items():
                    current=master_discoveries.get(ota_id) or {}
                    if discovery.get("status")=="found" and current.get("status")!="found":
                        master_discoveries[ota_id]=discovery
                    elif ota_id not in master_discoveries:
                        master_discoveries[ota_id]=discovery
            else:
                result["aiWebSearch"]=ai_result

            for ota_id in OTA_DISCOVERY_ORDER:
                existing_url=(sources.get(ota_id) or {}).get("url") if isinstance(sources.get(ota_id),dict) else ""
                if existing_url:
                    result["discoveredSources"][ota_id]={
                        "status":"existing","url":existing_url,"title":"","score":1.0,
                        "evidence":f"{OTA_META[ota_id]['label']}: scheda già registrata nella struttura.",
                        "discoveryMode":"existing source",
                    }
                    continue
                discovery=master_discoveries.get(ota_id) or {}
                # Booking mantiene il proprio fallback specializzato se la pipeline master non chiude il match.
                if ota_id=="booking" and discovery.get("status")!="found":
                    specialized=await discover_booking_source(
                        context,
                        data.get("name",""),
                        data.get("city",""),
                        robots,
                        address=data.get("address",""),
                        website=official_identity_url,
                        phone=data.get("phone",""),
                        email=data.get("email",""),
                    )
                    if specialized.get("status")=="found" or not discovery:
                        discovery=specialized
                result["discoveredSources"][ota_id]=discovery
                print(
                    f"{ota_id} discovery: {discovery.get('status','n.d.')} · {discovery.get('title','')} · "
                    f"{str(discovery.get('evidence') or '')[:220]}",
                    flush=True,
                )
                if discovery.get("status")=="found" and discovery.get("url"):
                    sources[ota_id]={"label":OTA_META[ota_id]["label"],"url":discovery["url"]}

            # Salva tutte le schede OTA trovate insieme, non soltanto Booking.
            try:
                property_path=Path(args.property)
                if property_path.parent.name=="runtime-properties":
                    data["sources"]=sources
                    tmp_property=property_path.with_suffix(".tmp")
                    tmp_property.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                    tmp_property.replace(property_path)
            except OSError:
                pass


            official_url = sources.get("sito", {}).get("url", "")
            if official_url:
                permission = await asyncio.to_thread(allowed_by_robots, official_url, robots)
                if permission is True:
                    page = await context.new_page()
                    try:
                        await page.goto(official_url, wait_until="domcontentloaded", timeout=25000)
                        await page.wait_for_timeout(1500)
                        result["bookingEngine"] = detect_booking_engine(official_url, await page.content(), page.url)
                    except Exception as exc:
                        result["bookingEngine"]["evidence"] = f"Pagina ufficiale non leggibile: {type(exc).__name__}"
                    finally:
                        await page.close()
                else:
                    result["bookingEngine"]["evidence"] = "Pagina ufficiale non esaminata: robots.txt non consente o non chiarisce la visita."
            else:
                result["bookingEngine"]["evidence"] = "URL ufficiale non indicato."
            write_result(output, result)
            for stay in plan:
                for channel in channels:
                    source = sources.get(channel, {}).get("url", "")
                    if not source:
                        discovery = result.get("discoveredSources", {}).get(channel, {})
                        evidence = discovery.get("evidence") if isinstance(discovery, dict) else ""
                        record = {"otaId": channel, **stay, "status": "source_missing", "quotes": [],
                                  "evidence": evidence or "Nessuna scheda univoca conosciuta per questo portale."}
                    else:
                        if channel == "booking":
                            search_page = await context.new_page()
                            try:
                                dated_record = await booking_dated_search_observation(
                                    search_page,
                                    source,
                                    data.get("name", ""),
                                    data.get("city", ""),
                                    stay,
                                    robots,
                                )
                            finally:
                                await search_page.close()
                            if dated_record.get("status") in {"quote_candidates_unverified", "no_public_rate"}:
                                record = dated_record
                            else:
                                page = await context.new_page()
                                try:
                                    record = await observe(page, channel, source, stay, robots)
                                finally:
                                    await page.close()
                                if record.get("status") in {"dates_unconfirmed", "needs_human_review"}:
                                    record["evidence"] = (
                                        str(record.get("evidence") or "") +
                                        " | Ricerca Booking datata: " +
                                        str(dated_record.get("evidence") or "")
                                    )[:900]
                        else:
                            page = await context.new_page()
                            try:
                                record = await observe(page, channel, source, stay, robots)
                            finally:
                                await page.close()
                    result["observations"].append(record)
                    write_result(output, result)
                    if channel == "booking":
                        print(
                            f"{stay['month']} {channel}: {record['status']} · {str(record.get('evidence') or '')[:220]}",
                            flush=True,
                        )
                    else:
                        print(f"{stay['month']} {channel}: {record['status']}", flush=True)
                    await asyncio.sleep(1)
        finally:
            await browser.close()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--property", default="src/perla-saracena-audit.json")
    parser.add_argument("--output", default="dati_strutture_pilot.json")
    parser.add_argument("--channels", default=",".join(CHANNELS))
    parser.add_argument("--months", type=int, help="Solo i primi N mesi futuri (per test)")
    parser.add_argument("--today", help="Data ISO per test riproducibili")
    parser.add_argument("--dry-run", action="store_true", help="Genera solo il piano date")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
