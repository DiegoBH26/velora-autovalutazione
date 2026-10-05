#!/usr/bin/env python3
"""Pilota locale di osservazione OTA: nessun prezzo inventato o blocco aggirato.

Sceglie una data campione per ogni mese futuro, apre le schede pubbliche in
Chrome e salva lo stato della verifica. Un prezzo non entra nel report finché
date, camera, piano e totale non sono verificati come un unico preventivo.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import unicodedata
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
DATE_URL_ADAPTERS = {"booking", "airbnb"}
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
    try:
        absolute = href if href.startswith(("http://", "https://")) else ""
        parsed = urlparse(absolute or href)
        if not absolute and href.startswith("/url?"):
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            absolute = query.get("q") or query.get("url") or ""
        if not absolute and href.startswith("/link?"):
            query = dict(parse_qsl(parsed.query, keep_blank_values=True))
            absolute = query.get("url") or query.get("u") or ""
        if not absolute:
            return ""
        absolute = unquote(absolute)
        parsed = urlparse(absolute)
        host = (parsed.hostname or "").lower()
        if host == "booking.com" or host.endswith(".booking.com"):
            if "/hotel/" in parsed.path:
                return urlunparse(parsed._replace(query="", fragment=""))
    except Exception:
        return ""
    return ""


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


async def discover_booking_via_search_engine(context, property_name: str, city: str, address: str = "", website: str = "") -> dict:
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
            links = await page.evaluate(r"""() => Array.from(document.querySelectorAll('a[href]')).slice(0,500).map(a => {
              const box=a.closest('li, article, [data-testid], div') || a.parentElement;
              return {
                href: a.getAttribute('href') || '',
                text: (a.innerText || a.textContent || a.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim().slice(0,320),
                context: (box?.innerText || '').replace(/\s+/g,' ').trim().slice(0,900)
              };
            })""")
            candidates = []
            for item in links:
                url = booking_candidate_from_search_href(str(item.get("href", "")), page.url)
                if not url:
                    continue
                text = str(item.get("text", ""))
                context_text = str(item.get("context", ""))
                score,path_slug,text_score,url_score,reasons = _identity_match_score(
                    property_name,city,address,text,context_text,url
                )
                candidates.append((score, url, text, path_slug, text_score, url_score, reasons))
            candidates.sort(key=lambda row: row[0], reverse=True)
            if not candidates:
                continue
            score, url, text, path_slug, text_score, url_score, reasons = candidates[0]
            display_title = text.strip() if text.strip() and text.strip().lower() not in {"hotel", "booking.com"} else path_slug
            if score >= 0.70:
                return {
                    "status": "found",
                    "url": url,
                    "title": display_title[:220],
                    "score": round(score, 3),
                    "evidence": (
                        f"{engine_name}: trovata una pagina Booking.com compatibile con «{property_name}{' ' + city if city else ''}». "
                        f"Match identità {score:.0%}: {reasons}. URL osservato: {url}"
                    )[:900],
                    "searchUrl": search_url,
                    "discoveryMode": f"{engine_name} site-search",
                }
            return {
                "status": "needs_review",
                "url": url,
                "title": text[:220],
                "score": round(score, 3),
                "evidence": (
                    f"{engine_name}: risultato Booking.com trovato, ma match identità {score:.0%} ({reasons}) non sufficiente "
                    "per attribuirlo automaticamente alla struttura."
                )[:900],
                "searchUrl": search_url,
                "discoveryMode": f"{engine_name} site-search",
            }
        except Exception:
            pass
        finally:
            await page.close()
    return {
        "status": "not_found_in_search",
        "url": "",
        "title": "",
        "score": 0.0,
        "evidence": "Né la ricerca interna Booking.com né i motori di ricerca pubblici hanno restituito una scheda attribuibile con sufficiente certezza.",
        "searchUrl": "",
        "discoveryMode": "fallback exhausted",
    }


async def discover_booking_source(context, property_name: str, city: str, robots: dict, address: str = "", website: str = "") -> dict:
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
        fallback = await discover_booking_via_search_engine(context, property_name, city, address, website)
        if fallback.get("status") == "found":
            fallback["evidence"] = (
                "La ricerca interna Booking.com non è stata usata perché robots.txt non ne consente o non chiarisce l'accesso automatico. "
                + str(fallback.get("evidence") or "")
            )[:900]
            return fallback
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
            fallback = await discover_booking_via_search_engine(context, property_name, city, address, website)
            if fallback.get("status") == "found":
                fallback["evidence"] = (
                    f"Ricerca Booking.com eseguita per «{property_name}{' ' + city if city else ''}» senza scheda riconoscibile; "
                    + str(fallback.get("evidence") or "")
                )[:900]
                return fallback
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
        fallback = await discover_booking_via_search_engine(context, property_name, city, address, website)
        if fallback.get("status") == "found":
            fallback["evidence"] = (
                f"Il miglior risultato della ricerca Booking aveva match identità {score:.0%} ({reasons}); "
                + str(fallback.get("evidence") or "")
            )[:900]
            return fallback
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
                record.update(status="needs_human_review", evidence="Date visibili, ma camera/piano/tasse/prezzo finale non attribuibili automaticamente con sicurezza.")
        # Solo una breve traccia testuale: evita di salvare intere pagine e dati ospite.
        record["visibleExcerpt"] = re.sub(r"\s+", " ", body)[:350]
    except Exception as exc:
        record.update(status="navigation_error", evidence=f"{type(exc).__name__}: {str(exc)[:180]}")
    return record


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
              "discoveredSources": {}, "observations": []}
    output = Path(args.output)
    if args.dry_run:
        write_result(output, result)
        return result
    robots: dict[str, RobotFileParser | bool | None] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(locale="it-IT", timezone_id="Europe/Rome")
        try:
            if not sources.get("booking", {}).get("url"):
                official_identity_url=(sources.get("sito") or {}).get("url","")
                catalog_match=data.get("catalogMatch") if isinstance(data.get("catalogMatch"),dict) else {}
                if catalog_match:
                    print(
                        f"catalog identity: {data.get('name','')} · {data.get('city','')} · "
                        f"{data.get('address','')} · match {catalog_match.get('score','')} · {catalog_match.get('reason','')}",
                        flush=True,
                    )
                discovery = await discover_booking_source(
                    context,
                    data.get("name", ""),
                    data.get("city", ""),
                    robots,
                    address=data.get("address", ""),
                    website=official_identity_url,
                )
                result["discoveredSources"]["booking"] = discovery
                print(
                    f"booking discovery: {discovery.get('status')} · {discovery.get('title','')} · "
                    f"{discovery.get('evidence','')[:220]}",
                    flush=True,
                )
                if discovery.get("status") == "found" and discovery.get("url"):
                    sources["booking"] = {"label": "Booking.com", "url": discovery["url"]}
                    try:
                        property_path=Path(args.property)
                        if property_path.parent.name=="runtime-properties":
                            data["sources"]=sources
                            tmp_property=property_path.with_suffix(".tmp")
                            tmp_property.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                            tmp_property.replace(property_path)
                            discovery["saved"]=True
                            discovery["evidence"]=(str(discovery.get("evidence") or "")+" Scheda Booking registrata localmente per i controlli successivi.")[:900]
                    except OSError:
                        discovery["saved"]=False
            else:
                result["discoveredSources"]["booking"] = {
                    "status": "existing", "url": sources["booking"]["url"], "title": "",
                    "score": 1.0, "evidence": "Scheda Booking.com già registrata nella struttura."
                }

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
