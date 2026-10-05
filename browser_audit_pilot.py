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
from selectolax.parser import HTMLParser

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
        checkin=date.fromisoformat(stay["checkin"])
        checkout=date.fromisoformat(stay["checkout"])
        query.update(
            checkin=stay["checkin"], checkout=stay["checkout"],
            checkin_year=str(checkin.year), checkin_month=str(checkin.month), checkin_monthday=str(checkin.day),
            checkout_year=str(checkout.year), checkout_month=str(checkout.month), checkout_monthday=str(checkout.day),
            group_adults="2", no_rooms="1", group_children="0",
            selected_currency="EUR", lang="it-it",
        )
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
    """Conferma Booking solo se check-in e check-out sono nei rispettivi campi visibili."""
    start, end = date.fromisoformat(stay["checkin"]), date.fromisoformat(stay["checkout"])
    try:
        state = await page.evaluate(r"""() => {
          const visible = (el) => {
            if (!el || el.getAttribute('aria-hidden') === 'true') return false;
            const st=getComputedStyle(el);
            if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
            const r=el.getBoundingClientRect();
            return r.width>0 && r.height>0 && r.bottom>0 && r.right>0 && r.top<innerHeight && r.left<innerWidth;
          };
          const textOf = (el) => [
            el?.textContent || '',
            el?.getAttribute?.('value') || '',
            el?.getAttribute?.('aria-label') || '',
            el?.getAttribute?.('placeholder') || ''
          ].join(' ').replace(/\s+/g,' ').trim();

          const firstVisible = (selectors) => {
            for (const selector of selectors) {
              for (const el of Array.from(document.querySelectorAll(selector)).slice(0,20)) {
                if (visible(el)) return {selector, text:textOf(el), top:Math.round(el.getBoundingClientRect().top)};
              }
            }
            return null;
          };

          return {
            start: firstVisible([
              '[data-testid="date-display-field-start"]',
              'input[name="checkin"]',
              'button[aria-label*="check-in" i]',
              'button[aria-label*="arrivo" i]'
            ]),
            end: firstVisible([
              '[data-testid="date-display-field-end"]',
              'input[name="checkout"]',
              'button[aria-label*="check-out" i]',
              'button[aria-label*="partenza" i]'
            ]),
            container: firstVisible([
              '[data-testid="searchbox-dates-container"]'
            ])
          };
        }""")
    except Exception:
        return False, ""

    start_text=str((state.get("start") or {}).get("text") or "").lower()
    end_text=str((state.get("end") or {}).get("text") or "").lower()
    container_text=str((state.get("container") or {}).get("text") or "").lower()

    start_ok=any(value in start_text for value in _date_forms(start))
    end_ok=any(value in end_text for value in _date_forms(end))

    # Fallback solo se Booking usa un unico controllo date: nello stesso container
    # devono comparire entrambe le date, non una generica cella calendario.
    if not (start_ok and end_ok) and container_text:
        both=(
            any(value in container_text for value in _date_forms(start))
            and any(value in container_text for value in _date_forms(end))
        )
        if both and (not state.get("start") or not state.get("end")):
            start_ok=end_ok=True

    evidence=(
        f"start={start_text[:220] or 'n.d.'} | "
        f"end={end_text[:220] or 'n.d.'} | "
        f"container={container_text[:300] or 'n.d.'}"
    )
    return bool(start_ok and end_ok), evidence[:800]

def booking_url_dates_confirmed(url: str, stay: dict) -> bool:
    """Conferma che Booking abbia mantenuto esattamente le date richieste nella URL finale."""
    try:
        parsed=urlparse(url)
        query=dict(parse_qsl(parsed.query, keep_blank_values=True))
    except Exception:
        return False
    checkin=query.get("checkin") or query.get("check_in") or ""
    checkout=query.get("checkout") or query.get("check_out") or ""
    if checkin==stay["checkin"] and checkout==stay["checkout"]:
        return True
    try:
        start=date.fromisoformat(stay["checkin"])
        end=date.fromisoformat(stay["checkout"])
        legacy_start=(
            query.get("checkin_year")==str(start.year)
            and query.get("checkin_month")==str(start.month)
            and query.get("checkin_monthday")==str(start.day)
        )
        legacy_end=(
            query.get("checkout_year")==str(end.year)
            and query.get("checkout_month")==str(end.month)
            and query.get("checkout_monthday")==str(end.day)
        )
        return legacy_start and legacy_end
    except Exception:
        return False


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
    """Restituisce il primo nodo realmente visibile, anche quando il DOM contiene duplicati nascosti."""
    for selector in selectors:
        try:
            matches=page.locator(selector)
            count=min(await matches.count(),30)
            for idx in range(count):
                loc=matches.nth(idx)
                try:
                    if await loc.is_visible(timeout=350):
                        return loc, selector
                except Exception:
                    continue
        except Exception:
            pass
    return None, ""


async def booking_apply_dates_via_ui(page, stay: dict) -> tuple[bool, str]:
    """Imposta realmente check-in/check-out nel date picker Booking e verifica che restino applicati."""
    checkin=stay["checkin"]
    checkout=stay["checkout"]
    evidence=[]

    async def visible_date_state() -> str:
        try:
            values=await page.evaluate(r"""() => {
              const selectors = [
                '[data-testid="date-display-field-start"]',
                '[data-testid="date-display-field-end"]',
                '[data-testid="searchbox-dates-container"]',
                'input[name="checkin"]',
                'input[name="checkout"]'
              ];
              const visible = (el) => {
                if (!el || el.getAttribute('aria-hidden') === 'true') return false;
                const st=getComputedStyle(el);
                if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
                const r=el.getBoundingClientRect();
                return r.width>0 && r.height>0;
              };
              const out=[];
              for (const selector of selectors) {
                for (const el of Array.from(document.querySelectorAll(selector)).slice(0,20)) {
                  if (!visible(el)) continue;
                  const value=[
                    el.textContent || '',
                    el.getAttribute('value') || '',
                    el.getAttribute('aria-label') || '',
                    el.getAttribute('placeholder') || ''
                  ].join(' ').replace(/\s+/g,' ').trim();
                  if (value) out.push(value.slice(0,240));
                }
              }
              return [...new Set(out)];
            }""")
            return " | ".join(str(v) for v in values)[:700]
        except Exception:
            return ""

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
        await opener.click(timeout=2200)
        await page.wait_for_timeout(450)
        evidence.append(f"aperto con {opener_selector}")
    except Exception as exc:
        return False, f"date picker non apribile: {type(exc).__name__}"

    async def click_visible_date(target_iso: str) -> tuple[bool, str]:
        selector=f'[data-date="{target_iso}"]'
        try:
            matches=page.locator(selector)
            count=min(await matches.count(),40)
        except Exception:
            count=0
        for idx in range(count):
            node=matches.nth(idx)
            try:
                if not await node.is_visible(timeout=250):
                    continue
                if (await node.get_attribute("aria-disabled")) == "true":
                    continue
                # Booking può mettere data-date su uno span interno: prova prima il vero controllo cliccabile.
                clickable=node.locator("xpath=ancestor-or-self::*[self::button or @role='button'][1]")
                if await clickable.count() and await clickable.is_visible(timeout=250):
                    await clickable.click(timeout=2200)
                else:
                    await node.click(timeout=2200)
                await page.wait_for_timeout(420)
                return True, f"{target_iso} selezionata"
            except Exception:
                try:
                    await node.click(timeout=1800, force=True)
                    await page.wait_for_timeout(420)
                    return True, f"{target_iso} selezionata (click forzato)"
                except Exception:
                    continue
        return False, ""

    async def pick(target_iso: str) -> tuple[bool, str]:
        for step in range(22):
            clicked, clicked_ev = await click_visible_date(target_iso)
            if clicked:
                return True, clicked_ev
            next_button, next_selector = await _first_visible_locator(page, (
                '[data-testid="calendar-next-button"]',
                '[data-testid*="next-month"]',
                'button[aria-label*="mese successivo" i]',
                'button[aria-label*="mese seguente" i]',
                'button[aria-label*="next month" i]',
            ))
            if next_button is None:
                return False, f"{target_iso} non visibile e navigazione calendario non trovata"
            try:
                await next_button.click(timeout=1700)
                await page.wait_for_timeout(280)
                if step == 0:
                    evidence.append(f"navigazione calendario con {next_selector}")
            except Exception as exc:
                return False, f"navigazione calendario fallita: {type(exc).__name__}"
        return False, f"{target_iso} non raggiunta entro 22 mesi"

    ok_start, ev_start = await pick(checkin)
    evidence.append(ev_start)
    if not ok_start:
        evidence.append("campi visibili: " + (await visible_date_state() or "n.d."))
        return False, "; ".join(filter(None,evidence))

    # Booking, sulla scheda struttura, può impostare automaticamente il giorno
    # successivo come check-out e chiudere il calendario dopo il check-in.
    # Prima di navigare tra i mesi, prova quindi a riaprire esplicitamente
    # il campo check-out e selezionare la data richiesta.
    direct_end, direct_end_ev = await click_visible_date(checkout)
    if direct_end:
        ok_end, ev_end = True, direct_end_ev
    else:
        end_opener, end_selector = await _first_visible_locator(page, (
            '[data-testid="date-display-field-end"]',
            'button[data-testid="date-display-field-end"]',
            'button[aria-label*="check-out" i]',
            'button[aria-label*="partenza" i]',
            '[data-testid="searchbox-dates-container"]',
            '[data-testid="date-display-field-start"]',
        ))
        if end_opener is not None:
            try:
                end_label=re.sub(r"\s+"," ",(await end_opener.inner_text(timeout=500)) or "").strip()[:120]
            except Exception:
                end_label=""
            try:
                await end_opener.click(timeout=2200)
                await page.wait_for_timeout(650)
                evidence.append(
                    f"calendario riaperto per check-out con {end_selector}"
                    + (f" («{end_label}»)" if end_label else "")
                )
            except Exception as exc:
                evidence.append(f"riapertura check-out fallita: {type(exc).__name__}")

        direct_end, direct_end_ev = await click_visible_date(checkout)
        if direct_end:
            ok_end, ev_end = True, direct_end_ev
        else:
            ok_end, ev_end = await pick(checkout)

    evidence.append(ev_end)
    if not ok_end:
        debug_path=""
        try:
            debug_dir=Path(__file__).resolve().parent/"tmp"
            debug_dir.mkdir(parents=True,exist_ok=True)
            debug_file=debug_dir/f"booking-v17-checkout-failed-{stay['month']}.png"
            await page.screenshot(path=str(debug_file),full_page=False)
            debug_path=str(debug_file)
        except Exception:
            pass
        evidence.append("campi visibili: " + (await visible_date_state() or "n.d."))
        if debug_path:
            evidence.append("screenshot: " + debug_path)
        return False, "; ".join(filter(None,evidence))

    # NON dichiarare successo perché i nodi data-date sono stati cliccati:
    # i campi visibili del searchbox devono davvero contenere entrambe le date.
    pre_ok,pre_state=await booking_dom_dates_confirmed(page,stay)
    if not pre_ok:
        debug_path=""
        try:
            debug_dir=Path(__file__).resolve().parent/"tmp"
            debug_dir.mkdir(parents=True,exist_ok=True)
            debug_file=debug_dir/f"booking-v15-after-date-clicks-{stay['month']}.png"
            await page.screenshot(path=str(debug_file),full_page=False)
            debug_path=str(debug_file)
        except Exception:
            pass
        evidence.append("date cliccate ma campi Booking non aggiornati")
        evidence.append("campi visibili: " + (pre_state or await visible_date_state() or "n.d."))
        if debug_path:
            evidence.append("screenshot: " + debug_path)
        return False, "; ".join(filter(None,evidence))
    evidence.append("date confermate nei campi visibili prima di Cerca")

    submit, submit_selector = await _first_visible_locator(page, (
        '[data-testid="date-submit-button"]',
        '[data-testid="searchbox-submit-button"]',
        '[data-testid="searchbox-layout-wide"] button[type="submit"]',
        '[data-testid="searchbox-layout-wide"] button:has-text("Cerca")',
        '[data-testid="searchbox-layout-wide"] button:has-text("Search")',
        'form[role="search"] button[type="submit"]',
        'form[action*="searchresults"] button[type="submit"]',
    ))
    if submit is None:
        return False, "; ".join(evidence + ["date impostate ma pulsante Cerca non individuato"])

    try:
        await submit.click(timeout=2400)
        evidence.append(f"ricerca inviata con {submit_selector}")
    except Exception as exc:
        return False, "; ".join(evidence + [f"pulsante Cerca non cliccabile: {type(exc).__name__}"])

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=9000)
    except Exception:
        pass
    await page.wait_for_timeout(1700)

    # Conferma finale: dopo Cerca le date devono essere ancora leggibili nei campi, nella URL
    # o nel testo renderizzato. Se Booking le azzera, il tentativo NON è riuscito.
    try:
        body=(await page.locator("body").inner_text(timeout=6000))[:12000]
    except Exception:
        body=""
    post_dom,post_state=await booking_dom_dates_confirmed(page,stay)
    post_url=booking_url_dates_confirmed(page.url,stay)
    post_text=visible_dates_confirmed(body,stay)
    if not (post_dom or post_url or post_text):
        debug_path=""
        try:
            debug_dir=Path(__file__).resolve().parent/"tmp"
            debug_dir.mkdir(parents=True,exist_ok=True)
            debug_file=debug_dir/f"booking-v15-after-search-{stay['month']}.png"
            await page.screenshot(path=str(debug_file),full_page=False)
            debug_path=str(debug_file)
        except Exception:
            pass
        evidence.append("Booking ha perso le date dopo Cerca")
        evidence.append("campi finali: " + (post_state or await visible_date_state() or "n.d."))
        evidence.append("URL finale: " + page.url[:350])
        if debug_path:
            evidence.append("screenshot: " + debug_path)
        return False, "; ".join(filter(None,evidence))

    mode="campi visibili" if post_dom else "URL" if post_url else "testo visibile"
    evidence.append(f"date confermate dopo Cerca via {mode}")
    return True, "; ".join(filter(None,evidence))

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
        elif host.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
            absolute=query.get("uddg") or query.get("rut") or ""
        elif host.endswith("yahoo.com"):
            absolute=query.get("RU") or query.get("url") or absolute
            if absolute == raw:
                match=re.search(r"/RU=([^/]+)/RK=",parsed.path,re.I)
                if match:
                    absolute=unquote(match.group(1))
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



def _safe_node_text(node, limit: int = 1400) -> str:
    try:
        return re.sub(r"\s+"," ",node.text(separator=" ",strip=True) or "").strip()[:limit]
    except Exception:
        try:
            return re.sub(r"\s+"," ",node.text() or "").strip()[:limit]
        except Exception:
            return ""


def _free_http_search_links(query: str) -> tuple[list[dict], list[dict]]:
    """Metasearch gratuita: prova pagine pubbliche HTML di più motori senza API a pagamento."""
    engines=(
        ("Google HTTP","https://www.google.com/search",{"q":query,"hl":"it","num":"20","filter":"0"}),
        ("Bing HTTP","https://www.bing.com/search",{"q":query,"setlang":"it","count":"20"}),
        ("DuckDuckGo HTML","https://html.duckduckgo.com/html/",{"q":query}),
        ("Yahoo HTTP","https://search.yahoo.com/search",{"p":query}),
    )
    out=[]
    stats=[]
    seen=set()
    for engine,url,params in engines:
        try:
            response=requests.get(
                url,
                params=params,
                headers={
                    "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language":"it-IT,it;q=0.9,en;q=0.7",
                },
                impersonate="chrome",
                timeout=15,
                allow_redirects=True,
            )
            body=response.text or ""
            if response.status_code>=400:
                stats.append({"engine":engine,"query":query,"status":f"HTTP {response.status_code}","links":0})
                continue
            lowered=body.lower()
            if any(word in lowered for word in BLOCK_WORDS):
                stats.append({"engine":engine,"query":query,"status":"blocked","links":0})
                continue
            tree=HTMLParser(body)
            count=0
            for node in tree.css("a[href]")[:1400]:
                href=str((node.attributes or {}).get("href") or "")
                target=_decode_search_target(href)
                if not target:
                    continue
                parsed=urlparse(target)
                host=(parsed.hostname or "").lower()
                if any(token in host for token in ("google.com","google.it","bing.com","duckduckgo.com","yahoo.com")):
                    continue
                key=(engine,target)
                if key in seen:
                    continue
                seen.add(key)
                text_value=_safe_node_text(node,420)
                parent=node.parent
                context=_safe_node_text(parent,1500) if parent is not None else text_value
                out.append({
                    "url":target,
                    "text":text_value,
                    "context":context,
                    "engine":engine,
                    "query":query,
                })
                count+=1
            stats.append({"engine":engine,"query":query,"status":"ok","links":count})
        except Exception as exc:
            stats.append({"engine":engine,"query":query,"status":f"{type(exc).__name__}","links":0})
    return out,stats


def _clean_listing_url(url: str) -> str:
    try:
        parsed=urlparse(url)
        return urlunparse(parsed._replace(query="",fragment=""))
    except Exception:
        return url


def _strong_search_evidence(score: float, reasons: str, engines: set[str]) -> bool:
    reasons=(reasons or "").lower()
    location_signal=("citta coincidente" in reasons) or ("indirizzo" in reasons)
    if score>=0.90 and location_signal:
        return True
    if score>=0.84 and location_signal and len(engines)>=2:
        return True
    return False


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

    # HTTP metasearch multi-engine: spesso restituisce i link OTA anche quando il browser automatico
    # riceve una SERP incompleta o una pagina di consenso.
    for query in queries:
        http_items,http_stats=await asyncio.to_thread(_free_http_search_links,query)
        diagnostics["queryStats"].extend(http_stats)
        for item in http_items:
            target=str(item.get("url") or "")
            ota_id=_classify_ota_url(target)
            if not ota_id:
                continue
            score,path_slug,text_score,url_score,reasons=_identity_match_score(
                name,city,address,str(item.get("text") or ""),str(item.get("context") or ""),target
            )
            raw_candidates[ota_id].append((
                score,target,str(item.get("text") or ""),reasons,query,str(item.get("engine") or "HTTP search")
            ))
            diagnostics["candidates"]+=1

    diagnostics["status"]="results_collected" if diagnostics["candidates"] else "no_ota_candidates"

    for ota_id in OTA_DISCOVERY_ORDER:
        candidates=raw_candidates.get(ota_id) or []
        grouped={}
        for score,url,title,reasons,query,engine in candidates:
            clean=_clean_listing_url(url)
            entry=grouped.setdefault(clean,{
                "score":score,"url":url,"title":title,"reasons":reasons,
                "queries":set(),"engines":set(),
            })
            if score>entry["score"]:
                entry.update(score=score,url=url,title=title,reasons=reasons)
            entry["queries"].add(query)
            entry["engines"].add(engine)
        ordered=sorted(grouped.values(),key=lambda row:row["score"],reverse=True)
        weak=[]
        for entry in ordered[:10]:
            score=entry["score"]; url=entry["url"]; title=entry["title"]; reasons=entry["reasons"]
            engines=entry["engines"]; queries_used=entry["queries"]
            verify=await verify_ota_candidate_page(context,ota_id,url,name,city,address,robots)
            if verify.get("ok"):
                discoveries[ota_id]={
                    "status":"found",
                    "url":verify.get("url") or url,
                    "title":verify.get("title") or title,
                    "score":verify.get("score",score),
                    "evidence":(
                        f"Ricerca master gratuita: {OTA_META[ota_id]['label']} trovato tramite "
                        f"{', '.join(sorted(engines))}; match ricerca {score:.0%} ({reasons}). "
                        f"Pagina OTA verificata direttamente: {verify.get('score',0):.0%} ({verify.get('evidence','')})."
                    )[:900],
                    "searchUrl":"",
                    "discoveryMode":"free multi-engine search + page verification",
                    "verification":"page",
                }
                break
            if _strong_search_evidence(score,reasons,engines):
                discoveries[ota_id]={
                    "status":"found",
                    "url":_clean_listing_url(url),
                    "title":title[:220],
                    "score":round(score,3),
                    "evidence":(
                        f"Ricerca master gratuita: scheda {OTA_META[ota_id]['label']} attribuita tramite evidenza "
                        f"convergente nei risultati pubblici ({', '.join(sorted(engines))}). "
                        f"Match {score:.0%} ({reasons}); query: {' | '.join(sorted(queries_used))[:260]}. "
                        f"La pagina OTA non è stata validata direttamente ({verify.get('evidence','')}); "
                        "la successiva fase di scraping la controllerà senza aggirare eventuali blocchi."
                    )[:900],
                    "searchUrl":"",
                    "discoveryMode":"free multi-engine correlated search evidence",
                    "verification":"search_evidence",
                }
                break
            weak.append((score,url,title,reasons,engines,queries_used,verify.get("evidence","")))
        if ota_id not in discoveries and weak:
            score,url,title,reasons,engines,queries_used,verify_evidence=weak[0]
            discoveries[ota_id]={
                "status":"needs_review","url":url,"title":title[:220],"score":round(score,3),
                "evidence":(
                    f"Ricerca master gratuita: candidato {OTA_META[ota_id]['label']} trovato tramite "
                    f"{', '.join(sorted(engines))} ({score:.0%}, {reasons}) ma non abbastanza forte per "
                    f"attribuirlo automaticamente. {verify_evidence}"
                )[:900],
                "searchUrl":"",
                "discoveryMode":"free multi-engine candidate",
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

        http_items,http_stats=await asyncio.to_thread(_free_http_search_links,query)
        for item in http_items:
            target=str(item.get("url") or "")
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
                        f"Ricerca mirata gratuita {meta['label']} tramite {item.get('engine','HTTP search')}: «{query}». "
                        f"Pagina verificata con match {verify.get('score',0):.0%} ({verify.get('evidence','')})."
                    )[:900],
                    "searchUrl":"","discoveryMode":"free targeted multi-engine + page verification",
                }
            if _strong_search_evidence(score,reasons,{str(item.get("engine") or "HTTP search")}):
                return {
                    "status":"found","url":_clean_listing_url(target),
                    "title":str(item.get("text") or "")[:220],"score":round(score,3),
                    "evidence":(
                        f"Ricerca mirata gratuita {meta['label']} tramite {item.get('engine','HTTP search')}: "
                        f"candidato con match {score:.0%} ({reasons}). La pagina non è stata verificata direttamente; "
                        "viene accettata come fonte da controllare nella fase di scraping."
                    )[:900],
                    "searchUrl":"","discoveryMode":"free targeted search evidence",
                    "verification":"search_evidence",
                }
            weak.append((score,target,str(item.get("text") or ""),reasons,query,str(item.get("engine") or "HTTP search"),verify.get("evidence","")))

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
        "model":str(os.environ.get("VELORA_OPENAI_MODEL") or "gpt-6-luna"),
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
    if not out:
        # Fallback conservativo: cerca righe visibili con valuta e contesto tariffario.
        try:
            text_rows=await page.evaluate(r"""() => {
              const body=(document.body?.innerText || '');
              const lines=body.split(/\n+/).map(v=>v.replace(/\s+/g,' ').trim()).filter(Boolean);
              const out=[]; const seen=new Set();
              for (let i=0;i<lines.length;i++) {
                const line=lines[i];
                const low=line.toLowerCase();
                if (!/(€|eur|\$|usd|£|gbp)/i.test(line)) continue;
                const context=[lines[i-1]||'',line,lines[i+1]||''].join(' ').replace(/\s+/g,' ').trim();
                const c=context.toLowerCase();
                if (!/(notte|notti|night|nights|totale|total|soggiorno|stay|camera|room|prezzo|price)/i.test(c)) continue;
                if (seen.has(context)) continue;
                seen.add(context); out.push(context.slice(0,1200));
              }
              return out.slice(0,80);
            }""")
            for text_value in text_rows:
                total=_money_value(str(text_value))
                if total is None:
                    continue
                out.append({
                    "roomType":"Tipologia camera da verificare",
                    "total":round(total,2),"currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
                    "board":"Trattamento da verificare","refund":"Cancellazione da verificare",
                    "audience":"Pubblico senza login","taxes":"Da verificare nel dettaglio del preventivo",
                    "verified":False,
                    "evidence":"Fallback testo visibile: "+str(text_value)[:850],
                })
        except Exception:
            pass

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



def booking_path_key(url: str) -> str:
    try:
        path=(urlparse(url).path or "").lower().rstrip("/")
        path=re.sub(r"\.(?:it\.)?html?$","",path)
        return path
    except Exception:
        return ""


async def booking_source_title(page, source: str, robots: dict, fallback: str) -> tuple[str,str]:
    permission=await asyncio.to_thread(allowed_by_robots,source,robots)
    if permission is not True:
        return fallback,"Scheda Booking non riletta per titolo canonico: robots.txt non consente o non chiarisce l'accesso."
    try:
        response=await page.goto(source,wait_until="domcontentloaded",timeout=25000)
        if not response or response.status>=400:
            return fallback,f"Scheda Booking non riletta per titolo canonico: HTTP {response.status if response else 'n.d.'}."
        await dismiss_cookie(page)
        await page.wait_for_timeout(700)
        observed=""
        for selector in ('[data-testid="title"]','[data-testid="property-title"]','.pp-header__title','h1'):
            try:
                loc=page.locator(selector).first
                if await loc.count():
                    observed=re.sub(r"\s+"," ",(await loc.inner_text(timeout=500)) or "").strip()
                    if observed:
                        break
            except Exception:
                pass
        if not observed:
            try:
                observed=await page.evaluate(r"""() => (
                  document.querySelector('meta[property="og:title"]')?.content ||
                  document.querySelector('meta[name="twitter:title"]')?.content ||
                  document.title || ''
                ).replace(/\s+/g,' ').trim()""")
            except Exception:
                observed=""
        observed=observed or (await page.title())
        cleaned=re.sub(r"\s*[-|–—]\s*Booking\.com.*$","",observed,flags=re.I).strip()
        cleaned=re.sub(r"^Booking\.com\s*[:|–—-]\s*","",cleaned,flags=re.I).strip()
        if cleaned and len(cleaned)>=3 and _norm_name(cleaned) not in {"booking com","booking"}:
            return cleaned,f"Titolo canonico Booking osservato: «{cleaned}»."
        return fallback,"Titolo canonico Booking non ricavato; uso il nome struttura."
    except Exception as exc:
        return fallback,f"Titolo canonico Booking non ricavato: {type(exc).__name__}."


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


def booking_hotel_dated_url(hotel_id: str, stay: dict) -> str:
    hotel_id=re.sub(r"\D+","",str(hotel_id or ""))
    if not hotel_id:
        return ""
    return "https://www.booking.com/searchresults.it.html?" + urlencode({
        "dest_id": hotel_id,
        "dest_type": "hotel",
        "checkin": stay["checkin"],
        "checkout": stay["checkout"],
        "group_adults": str(stay.get("adults") or 2),
        "no_rooms": "1",
        "group_children": "0",
        "selected_currency": "EUR",
        "lang": "it-it",
    })


def booking_city_dated_url(city: str, stay: dict) -> str:
    """Fallback Booking v8: pagina destinazione datata, utile quando searchresults non rende le card."""
    slug=_slugify_booking(city)
    if not slug:
        return ""
    return "https://www.booking.com/city/it/" + slug + ".it.html?" + urlencode({
        "checkin": stay["checkin"],
        "checkout": stay["checkout"],
        "group_adults": str(stay.get("adults") or 2),
        "no_rooms": "1",
        "group_children": "0",
        "selected_currency": "EUR",
        "lang": "it-it",
    })


async def booking_result_cards(page) -> list[dict]:
    return await page.evaluate(r"""() => {
      const abs = (u) => { try { return new URL(u, location.href).href; } catch { return ''; } };
      const result = [];
      const seen = new Set();
      const cardNodes = Array.from(document.querySelectorAll(
        '[data-testid="property-card"], [data-testid*="property-card"], article'
      )).slice(0, 100);
      for (const card of cardNodes) {
        const link = card.querySelector(
          'a[data-testid="title-link"], a[href*="/hotel/"]'
        );
        const href = link ? abs(link.getAttribute('href') || '') : '';
        if (!href || !href.includes('/hotel/') || seen.has(href)) continue;
        seen.add(href);
        const titleNode = card.querySelector(
          '[data-testid="title"], [data-testid="property-title"], h2, h3'
        );
        const priceNode = card.querySelector(
          '[data-testid="price-and-discounted-price"], [data-testid*="price"], [class*="price"]'
        );
        let hotelId =
          card.getAttribute('data-hotelid') ||
          card.getAttribute('data-hotel-id') ||
          card.dataset?.hotelid ||
          card.dataset?.hotelId ||
          '';
        if (!hotelId) {
          const holder = card.querySelector('[data-hotelid],[data-hotel-id]');
          hotelId = holder?.getAttribute('data-hotelid') || holder?.getAttribute('data-hotel-id') || '';
        }
        result.push({
          href,
          hotelId: String(hotelId || '').replace(/\D+/g,'').slice(0,32),
          title: (titleNode?.textContent || link?.textContent || '').replace(/\s+/g,' ').trim().slice(0,240),
          text: (card.innerText || card.textContent || '').replace(/\s+/g,' ').trim().slice(0,2200),
          price: (priceNode?.textContent || '').replace(/\s+/g,' ').trim().slice(0,200)
        });
      }
      if (!result.length) {
        for (const link of Array.from(document.querySelectorAll('a[href*="/hotel/"]')).slice(0,120)) {
          const href=abs(link.getAttribute('href') || '');
          if (!href || seen.has(href)) continue;
          seen.add(href);
          const box=link.closest('li,article,[data-testid],div') || link.parentElement;
          let hotelId =
            box?.getAttribute?.('data-hotelid') ||
            box?.getAttribute?.('data-hotel-id') ||
            box?.dataset?.hotelid ||
            box?.dataset?.hotelId ||
            '';
          result.push({
            href,
            hotelId:String(hotelId || '').replace(/\D+/g,'').slice(0,32),
            title:(link.textContent || link.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim().slice(0,240),
            text:(box?.innerText || box?.textContent || '').replace(/\s+/g,' ').trim().slice(0,2200),
            price:''
          });
        }
      }
      return result;
    }""")


def booking_best_card(cards: list[dict], source: str, property_name: str, canonical_name: str, city: str):
    source_path=booking_path_key(source)
    best=None
    for item in cards:
        href=str(item.get("href") or "")
        candidate_path=booking_path_key(href)
        exact_path=bool(source_path and candidate_path and source_path==candidate_path)
        score=max(
            _name_similarity(property_name, str(item.get("title") or "")),
            _name_similarity(canonical_name, str(item.get("title") or "")),
        )
        if exact_path:
            score=1.0
        elif city and city.lower() in str(item.get("text") or "").lower():
            score=min(1.0, score+0.08)
        row=(score, exact_path, item)
        if best is None or row[0]>best[0]:
            best=row
    return best


async def booking_page_dates_confirmed(page, stay: dict, body: str = "") -> tuple[bool,str]:
    if booking_url_dates_confirmed(page.url,stay):
        return True,"url"
    if visible_dates_confirmed(body,stay):
        return True,"visible-text"
    dom_ok,dom_evidence=await booking_dom_dates_confirmed(page,stay)
    if dom_ok:
        return True,"dom-fields"
    return False,dom_evidence[:260]


async def booking_dated_search_observation(page, source: str, property_name: str, city: str, stay: dict, robots: dict) -> dict:
    """Booking v8: searchresults; se inconclusiva, pagina città datata e match sull'URL listing già noto."""
    canonical_name,canonical_evidence = await booking_source_title(page,source,robots,property_name)
    requested = booking_dated_search_url(canonical_name, city, stay)
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

    async def inspect_target(target_url: str, label: str) -> dict:
        permission=await asyncio.to_thread(allowed_by_robots,target_url,robots)
        if permission is not True:
            return {
                "ok":False,"label":label,"reason":"robots",
                "evidence":f"{label}: robots.txt non consente o non chiarisce l'accesso."
            }
        try:
            response=await page.goto(target_url,wait_until="domcontentloaded",timeout=25000)
            await dismiss_cookie(page)
            try:
                await page.locator("body").wait_for(state="visible",timeout=5000)
                await page.wait_for_timeout(1800)
            except PlaywrightTimeout:
                pass
            title=(await page.title())[:200]
            body=(await page.locator("body").inner_text(timeout=7000))[:14000]
            if response and response.status==429:
                return {
                    "ok":False,"label":label,"reason":"rate_limited","status":"rate_limited",
                    "finalUrl":page.url,"title":title,"body":body,
                    "evidence":f"{label}: HTTP 429."
                }
            if response and response.status>=400:
                return {
                    "ok":False,"label":label,"reason":"http_error","status":"http_error",
                    "finalUrl":page.url,"title":title,"body":body,
                    "evidence":f"{label}: HTTP {response.status}."
                }
            dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
            ui_evidence=""
            if not dates_ok:
                applied,ui_evidence=await booking_apply_dates_via_ui(page,stay)
                print(
                    f"{stay['month']} booking-search-date-picker [{label}]: {'applied' if applied else 'failed'} · {ui_evidence}",
                    flush=True,
                )
                if applied:
                    try:
                        await page.wait_for_timeout(1200)
                        title=(await page.title())[:200]
                        body=(await page.locator("body").inner_text(timeout=7000))[:14000]
                        dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
                        if dates_ok and not date_mode:
                            date_mode="ui-date-picker"
                    except Exception:
                        pass
            cards=await booking_result_cards(page)
            best=booking_best_card(cards,source,property_name,canonical_name,city)
            if label.startswith("searchresults Booking") and (not best or not best[1]):
                for _ in range(6):
                    await page.wait_for_timeout(700)
                    cards=await booking_result_cards(page)
                    best=booking_best_card(cards,source,property_name,canonical_name,city)
                    if best and best[1]:
                        break
            best_score=best[0] if best else 0.0
            best_exact=best[1] if best else False
            best_title=str((best[2] if best else {}).get("title") or "")
            best_price=str((best[2] if best else {}).get("price") or "")
            print(
                f"{stay['month']} booking-card-diagnostics [{label}]: "
                f"cards={len(cards)} · best={best_score:.0%} · exact_url={best_exact} · "
                f"title={best_title[:120]} · hotel_id={str((best[2] if best else {}).get('hotelId') or '')} · "
                f"price={best_price[:80]}",
                flush=True,
            )
            return {
                "ok":True,"label":label,"status":"ok","finalUrl":page.url,"title":title,
                "body":body,"cards":cards,"best":best,"datesOk":dates_ok,"dateMode":date_mode,
                "datePickerEvidence":ui_evidence,
                "evidence":(
                    f"{label}: {len(cards)} card; date {'confermate' if dates_ok else 'non confermate'} "
                    f"({date_mode or 'n.d.'}). "
                    + (f"Date picker: {ui_evidence}." if ui_evidence else "")
                )[:900],
            }
        except Exception as exc:
            return {
                "ok":False,"label":label,"reason":"navigation_error","status":"navigation_error",
                "evidence":f"{label}: {type(exc).__name__}: {str(exc)[:160]}",
            }

    primary=await inspect_target(requested,"searchresults Booking")
    chosen=primary
    best=primary.get("best") if primary.get("ok") else None

    # Se la ricerca interna non isola la scheda, usa la pagina della città con le stesse date.
    # Il match principale non dipende dal nome: confronta il path /hotel/... con la scheda Booking già verificata.
    if not best or best[0] < 0.68:
        city_url=booking_city_dated_url(city,stay)
        if city_url:
            city_result=await inspect_target(city_url,"pagina città Booking")
            city_best=city_result.get("best") if city_result.get("ok") else None
            if city_best and city_best[0] >= 0.68:
                chosen=city_result
                best=city_best
                record["requestedUrl"]=city_url
            elif city_result.get("ok") and (not chosen.get("ok") or len(city_result.get("cards") or []) > len(chosen.get("cards") or [])):
                chosen=city_result
                best=city_best

    # Se il fallback città trova l'URL esatto ma perde le date, usa prima
    # l'eventuale hotel_id della card per aprire una searchresults già vincolata
    # alla struttura esatta. È più robusto del solo testo libero.
    if chosen.get("label") == "pagina città Booking" and best and best[1] and not chosen.get("datesOk"):
        exact_hotel_id=str((best[2] or {}).get("hotelId") or "").strip()
        if exact_hotel_id:
            hotel_retry_url=booking_hotel_dated_url(exact_hotel_id,stay)
            hotel_retry=await inspect_target(hotel_retry_url,"searchresults Booking hotel-id")
            hotel_retry_best=hotel_retry.get("best") if hotel_retry.get("ok") else None
            print(
                f"{stay['month']} booking-hotel-id-retry: hotel_id={exact_hotel_id} · "
                f"exact_url={bool(hotel_retry_best and hotel_retry_best[1])} · "
                f"dates={bool(hotel_retry.get('datesOk'))}",
                flush=True,
            )
            if hotel_retry_best and hotel_retry_best[1]:
                chosen=hotel_retry
                best=hotel_retry_best
                record["requestedUrl"]=hotel_retry_url

    # Se l'hotel-id non basta, riprova la searchresults usando il titolo
    # realmente osservato sulla card Booking.
    if chosen.get("label") == "pagina città Booking" and best and best[1] and not chosen.get("datesOk"):
        observed_title=str((best[2] or {}).get("title") or "").strip()
        retry_name=observed_title or canonical_name
        if city and retry_name.lower().endswith(city.lower()):
            retry_name=retry_name[:-len(city)].strip()
        retry_url=booking_dated_search_url(retry_name,city,stay)
        retry=await inspect_target(retry_url,"searchresults Booking titolo osservato")
        retry_best=retry.get("best") if retry.get("ok") else None
        if retry_best and retry_best[1]:
            chosen=retry
            best=retry_best
            record["requestedUrl"]=retry_url
            print(
                f"{stay['month']} booking-observed-title-retry: exact_url=True · "
                f"name={retry_name} · dates={bool(retry.get('datesOk'))}",
                flush=True,
            )
        else:
            print(
                f"{stay['month']} booking-observed-title-retry: exact_url=False · name={retry_name}",
                flush=True,
            )

    record["finalUrl"]=str(chosen.get("finalUrl") or "")
    record["title"]=str(chosen.get("title") or "")[:200]

    if chosen.get("status") in {"rate_limited","http_error","navigation_error"} and not chosen.get("ok"):
        record.update(
            status=chosen.get("status") or "dated_search_inconclusive",
            evidence=(f"{canonical_evidence} {chosen.get('evidence','')}")[:900],
        )
        return record

    if not best or best[0] < 0.68:
        body=str(chosen.get("body") or "")
        primary_ev=str(primary.get("evidence") or "")
        chosen_ev=str(chosen.get("evidence") or "")
        record["evidence"]=(
            f"{canonical_evidence} Ricerca Booking con date {stay['checkin']} → {stay['checkout']} usando «{canonical_name}». "
            f"La scheda esatta non è stata isolata. {primary_ev} "
            + (f"Fallback: {chosen_ev}. " if chosen_ev and chosen_ev!=primary_ev else "")
            + f"Estratto: {re.sub(r'\s+', ' ', body)[:280]}"
        )[:900]
        return record

    score,exact_path,item=best
    card_text=str(item.get("text") or "")
    low=card_text.lower()
    dates_ok=bool(chosen.get("datesOk"))
    date_mode=str(chosen.get("dateMode") or "")
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
    unavailable_hit=next((term for term in unavailable_terms if term in low),"")
    total=_money_value(str(item.get("price") or "") or card_text)
    route_label=str(chosen.get("label") or "Booking")

    if dates_ok and unavailable_hit:
        record.update(
            status="no_public_rate",
            evidence=(
                f"{canonical_evidence} Date confermate ({date_mode}) {stay['checkin']} → {stay['checkout']} tramite {route_label}. "
                f"Scheda esatta {'per URL listing già noto' if exact_path else 'per nome'}: «{item.get('title','')}». "
                f"Il portale mostra indisponibilità («{unavailable_hit}»). "
                "Esito: nessuna tariffa pubblica prenotabile rilevata per queste date."
            )[:900],
        )
        return record

    if dates_ok and total is not None:
        quote={
            "roomType":"Tipologia camera da verificare",
            "total":round(total,2),
            "currency":"EUR",
            "nights":stay["nights"],
            "guests":stay["adults"],
            "board":"Trattamento da verificare",
            "refund":"Cancellazione da verificare",
            "audience":"Pubblico senza login",
            "taxes":"Da verificare nel dettaglio del preventivo",
            "verified":False,
            "evidence":card_text[:700],
        }
        record["quotes"]=[quote]
        record.update(
            status="quote_candidates_unverified",
            evidence=(
                f"Date confermate ({date_mode}) tramite {route_label}: {stay['checkin']} → {stay['checkout']}. "
                f"Scheda esatta {'per URL listing già noto' if exact_path else 'per nome'}: «{item.get('title','')}». "
                f"Prezzo visibile nella card: €{total:.2f}. "
                "Camera, tasse e condizioni restano da verificare prima del confronto."
            )[:900],
        )
        return record

    # v13: se abbiamo identificato con certezza la card esatta, aprila comunque.
    # Se la pagina elenco non ha mantenuto le date, il follow-through le applica
    # direttamente sulla scheda struttura tramite il date picker Booking.
    if exact_path:
        detail=await booking_follow_matched_listing(page,source,item,stay,robots)
        record["finalUrl"]=str(detail.get("finalUrl") or record.get("finalUrl") or "")
        record["title"]=str(detail.get("title") or record.get("title") or "")[:200]
        record["quotes"]=detail.get("quotes") or []
        detail_status=str(detail.get("status") or "dated_search_inconclusive")
        if detail_status in {
            "quote_candidates","quote_candidates_unverified","no_public_rate",
            "needs_human_review","rate_limited","http_error","navigation_error"
        }:
            record["status"]=detail_status
            record["evidence"]=(
                f"{canonical_evidence} {route_label}: scheda esatta «{item.get('title','')}» trovata "
                f"(URL listing identico). "
                f"Date nella pagina elenco: {'confermate (' + date_mode + ')' if dates_ok else 'non confermate'}; "
                f"follow-through scheda: {detail.get('evidence','')}"
            )[:900]
            return record

    if exact_path and not dates_ok:
        record["status"]="needs_human_review"
    record["evidence"]=(
        f"{canonical_evidence} {route_label}: scheda «{item.get('title','')}» individuata "
        f"(match {score:.0%}; {'URL listing identico' if exact_path else 'match nome/località'}). "
        f"Date {'confermate' if dates_ok else 'non confermate'} ({date_mode or 'n.d.'}); "
        + (f"Tentativo date picker: {chosen.get('datePickerEvidence','')}. " if chosen.get('datePickerEvidence') else "")
        + "Nessun prezzo o messaggio di indisponibilità attribuibile con sufficiente certezza nella card."
    )[:900]
    return record

async def booking_follow_matched_listing(page, source: str, item: dict, stay: dict, robots: dict) -> dict:
    """Booking v10: clicca la card esatta dalla pagina datata, preservando sessione e date."""
    href=str(item.get("href") or "").strip()
    if not href:
        return {"status":"needs_human_review","evidence":"Card Booking esatta trovata, ma senza URL apribile.","quotes":[]}
    source_path=booking_path_key(source)
    href_path=booking_path_key(href)
    if not source_path or href_path != source_path:
        return {"status":"needs_human_review","evidence":"La card Booking trovata non coincide con la scheda già verificata.","quotes":[]}

    # Siamo ancora sulla pagina Booking datata che ha confermato le date.
    # Prima scelta: cliccare la card reale, così Booking può trasferire il contesto tramite sessione/JS.
    clicked=False
    click_evidence=""
    try:
        links=page.locator('a[href*="/hotel/"]')
        count=min(await links.count(),140)
        for i in range(count):
            loc=links.nth(i)
            try:
                absolute=await loc.evaluate("(el) => el.href || ''")
            except Exception:
                continue
            if booking_path_key(str(absolute or "")) != source_path:
                continue
            try:
                await loc.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass
            try:
                await loc.click(timeout=2500)
                clicked=True
                click_evidence="card esatta cliccata dalla pagina Booking datata"
                try:
                    await page.wait_for_load_state("domcontentloaded",timeout=12000)
                except Exception:
                    pass
                await page.wait_for_timeout(1600)
                break
            except Exception as exc:
                click_evidence=f"click card fallito: {type(exc).__name__}"
                break
    except Exception as exc:
        click_evidence=f"ricerca link card fallita: {type(exc).__name__}"

    # Fallback prudente: URL della card con parametri data, senza aggirare blocchi.
    if not clicked:
        target=dated_url("booking",href,stay) or href
        permission=await asyncio.to_thread(allowed_by_robots,target,robots)
        if permission is not True:
            return {
                "status":"needs_human_review",
                "evidence":(
                    f"{click_evidence}. Scheda Booking datata non aperta: robots.txt non consente "
                    "o non chiarisce l'accesso."
                )[:900],
                "quotes":[],
            }
        try:
            response=await page.goto(target,wait_until="domcontentloaded",timeout=25000)
            await dismiss_cookie(page)
            try:
                await page.locator("body").wait_for(state="visible",timeout=5000)
                await page.wait_for_timeout(1800)
            except PlaywrightTimeout:
                pass
            if response and response.status==429:
                return {
                    "status":"rate_limited","finalUrl":page.url,"title":(await page.title())[:200],"quotes":[],
                    "evidence":"Scheda Booking datata: HTTP 429; il portale limita temporaneamente le richieste automatiche.",
                }
            if response and response.status>=400:
                return {
                    "status":"http_error","finalUrl":page.url,"title":(await page.title())[:200],"quotes":[],
                    "evidence":f"Scheda Booking datata: HTTP {response.status}.",
                }
        except Exception as exc:
            return {
                "status":"navigation_error","quotes":[],
                "evidence":f"Apertura della card Booking esatta non completata: {type(exc).__name__}: {str(exc)[:180]}",
            }

    try:
        await dismiss_cookie(page)
    except Exception:
        pass
    final_url=page.url
    title=(await page.title())[:200]
    try:
        body=(await page.locator("body").inner_text(timeout=7000))[:14000]
    except Exception:
        body=""

    dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
    ui_evidence=""
    if not dates_ok:
        applied,ui_evidence=await booking_apply_dates_via_ui(page,stay)
        print(
            f"{stay['month']} booking-detail-date-picker: {'applied' if applied else 'failed'} · {ui_evidence}",
            flush=True,
        )
        if applied:
            final_url=page.url
            title=(await page.title())[:200]
            try:
                body=(await page.locator("body").inner_text(timeout=7000))[:14000]
            except Exception:
                body=""
            dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
            if dates_ok and not date_mode:
                date_mode="ui-date-picker"

    if not dates_ok:
        debug_path=""
        try:
            debug_dir=Path(__file__).resolve().parent/"tmp"
            debug_dir.mkdir(parents=True,exist_ok=True)
            debug_file=debug_dir/f"booking-v16-date-failed-{stay['month']}.png"
            await page.screenshot(path=str(debug_file),full_page=False)
            debug_path=str(debug_file)
        except Exception:
            pass
        return {
            "status":"needs_human_review","finalUrl":final_url,"title":title,"quotes":[],
            "evidence":(
                f"{click_evidence or 'scheda esatta aperta'}. La pagina di partenza aveva le date confermate, "
                "ma la scheda dettaglio non le espone in modo verificabile; nessun prezzo viene usato. "
                + (f"Tentativo date picker: {ui_evidence}. " if ui_evidence else "")
                + (f"Screenshot diagnostico: {debug_path}." if debug_path else "")
            )[:900],
        }

    render_diag=await booking_settle_render(page)
    final_url=page.url
    title=(await page.title())[:200]
    try:
        body=(await page.locator("body").inner_text(timeout=7000))[:16000]
    except Exception:
        body=""
    dates_ok_after,date_mode_after=await booking_page_dates_confirmed(page,stay,body)
    if dates_ok_after:
        date_mode=date_mode_after or date_mode

    unavailable_hit=booking_unavailability_message(body)
    if unavailable_hit:
        return {
            "status":"no_public_rate","finalUrl":final_url,"title":title,"quotes":[],
            "evidence":(
                f"{click_evidence or 'scheda esatta aperta'}; date confermate ({date_mode or 'pagina renderizzata'}) "
                f"{stay['checkin']} → {stay['checkout']}. "
                f"Booking mostra indisponibilità («{unavailable_hit}»). "
                "Esito: nessuna tariffa pubblica prenotabile rilevata per queste date."
            )[:900],
        }

    candidates=await booking_quote_candidates(page,stay)
    verified=[item for item in candidates if item.get("verified")]
    if verified:
        first=verified[0]
        return {
            "status":"quote_candidates","finalUrl":final_url,"title":title,"quotes":candidates,
            "evidence":(
                f"{click_evidence or 'scheda esatta aperta'}; date confermate ({date_mode or 'pagina renderizzata'}). "
                f"Rilevati {len(candidates)} candidati camera/prezzo; {len(verified)} hanno un riferimento compatibile "
                f"con il totale soggiorno. Esempio: {first['roomType']} · €{first['total']:.2f} per {stay['nights']} notti."
            )[:900],
        }
    if candidates:
        first=candidates[0]
        return {
            "status":"quote_candidates_unverified","finalUrl":final_url,"title":title,"quotes":candidates,
            "evidence":(
                f"{click_evidence or 'scheda esatta aperta'}; date confermate ({date_mode or 'pagina renderizzata'}). "
                f"Rilevati {len(candidates)} candidati prezzo. Esempio €{first['total']:.2f}; "
                "camera, tasse e condizioni restano da verificare."
            )[:900],
        }

    diag=(
        f"DOM: testo {render_diag.get('bodyLength',len(body))} caratteri, "
        f"prezzi {render_diag.get('priceNodes',0)}, camere {render_diag.get('roomNodes',0)}, "
        f"blocchi disponibilità {render_diag.get('availabilityNodes',0)}, "
        f"reload {'sì' if render_diag.get('reloaded') else 'no'}."
    )
    field_ok,field_state=await booking_dom_dates_confirmed(page,stay)
    print(
        f"{stay['month']} booking-final-diagnostics: dates={field_ok} · {field_state} · {diag} · URL={page.url[:320]}",
        flush=True,
    )
    debug_path=""
    try:
        debug_dir=Path(__file__).resolve().parent/"tmp"
        debug_dir.mkdir(parents=True,exist_ok=True)
        debug_file=debug_dir/f"booking-v16-final-{stay['month']}.png"
        await page.screenshot(path=str(debug_file),full_page=False)
        debug_path=str(debug_file)
    except Exception:
        pass
    return {
        "status":"needs_human_review","finalUrl":final_url,"title":title,"quotes":[],
        "evidence":(
            f"{click_evidence or 'scheda esatta aperta'} e date confermate ({date_mode or 'pagina renderizzata'}), "
            "ma nessun prezzo o messaggio esplicito di indisponibilità è stato attribuito automaticamente. "
            + diag + " "
            + (f"Screenshot diagnostico: {debug_path}. " if debug_path else "")
            + f"Estratto: {re.sub(r'\\s+',' ',body)[:300]}"
        )[:900],
    }

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
        diagnostics["priceNodes"] > 0
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
        if response and response.status == 429:
            record.update(
                status="rate_limited",
                evidence=f"HTTP 429 · Il portale limita temporaneamente le richieste automatiche. Nessun aggiramento tentato. URL finale: {page.url}"
            )
        elif response and response.status >= 400:
            record.update(status="http_error", evidence=f"HTTP {response.status} · URL finale: {page.url}")
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
            known_ota_sources=[
                ota_id for ota_id in OTA_DISCOVERY_ORDER
                if ((sources.get(ota_id) or {}).get("url") if isinstance(sources.get(ota_id),dict) else "")
            ]
            quick_retest=bool(args.months == 1 and known_ota_sources)
            if quick_retest:
                master_discoveries={}
                master_diag={
                    "status":"reused_sources_quick_test",
                    "queries":[],
                    "candidates":len(known_ota_sources),
                    "knownSources":known_ota_sources,
                }
                print(
                    "master search: riuso schede OTA già verificate per il test di un mese · "
                    f"fonti note={','.join(known_ota_sources)}",
                    flush=True,
                )
            else:
                master_discoveries,master_diag=await discover_all_ota_sources(context,data,robots)
                query_preview=" | ".join((master_diag.get("queries") or [])[:3])
                print(
                    f"master search: {master_diag.get('status')} · varianti={len(master_diag.get('queries') or [])} · "
                    f"candidati OTA={master_diag.get('candidates',0)} · prime query: {query_preview[:240]}",
                    flush=True,
                )
            result["masterSearch"]=master_diag

            unresolved=[
                ota_id for ota_id in OTA_DISCOVERY_ORDER
                if (master_discoveries.get(ota_id) or {}).get("status")!="found"
                and not ((sources.get(ota_id) or {}).get("url") if isinstance(sources.get(ota_id),dict) else "")
            ]
            # Modalità gratuita: nessuna API a pagamento viene chiamata.
            result["aiWebSearch"]={
                "status":"disabled_free_mode",
                "discoveries":{},
                "evidence":"Velora usa esclusivamente ricerca web pubblica gratuita e browser locale.",
            }
            if unresolved and not quick_retest:
                print(
                    f"free discovery: OTA ancora irrisolte={len(unresolved)} · nessuna API a pagamento utilizzata",
                    flush=True,
                )
            elif quick_retest:
                print(
                    f"quick test: discovery saltata; scraping delle {len(known_ota_sources)} OTA già note",
                    flush=True,
                )

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
                        if quick_retest and channel in OTA_DISCOVERY_ORDER:
                            record = {"otaId": channel, **stay, "status": "source_not_retested", "quotes": [],
                                      "evidence": "Test rapido: discovery non ripetuta; questa OTA non ha ancora una scheda verificata salvata."}
                        else:
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
                            print(
                                f"{stay['month']} booking-dated-search: {dated_record.get('status')} · "
                                f"{str(dated_record.get('evidence') or '')[:260]}",
                                flush=True,
                            )
                            if dated_record.get("status") in {"quote_candidates", "quote_candidates_unverified", "no_public_rate", "needs_human_review"}:
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
                    print(
                        f"{stay['month']} {channel}: {record['status']} · {str(record.get('evidence') or '')[:240]}",
                        flush=True,
                    )
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
