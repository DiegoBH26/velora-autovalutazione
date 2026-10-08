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
import time
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


PILOT_BUILD = "velora-browser-pilot-v95"
SCHEMA = "velora-browser-audit-pilot-v1"
CHANNELS = ("sito", "booking", "airbnb", "expedia", "vrbo", "holidu", "hotels", "agoda", "trip", "priceline", "travelocity", "tripadvisor", "trivago", "googlehotels", "holidaycheck")
OTA_DISCOVERY_ORDER = ("booking", "airbnb", "expedia", "hotels", "vrbo", "holidu", "agoda", "trip", "priceline", "travelocity", "tripadvisor", "trivago", "googlehotels", "holidaycheck")
OTA_META = {
    "booking": {"label": "Booking.com", "domains": ("booking.com",)},
    "airbnb": {"label": "Airbnb", "domains": ("airbnb.com", "airbnb.it")},
    "expedia": {"label": "Expedia", "domains": ("expedia.com", "expedia.it")},
    "hotels": {"label": "Hotels.com", "domains": ("hotels.com",)},
    "vrbo": {"label": "Vrbo", "domains": ("vrbo.com", "vrbo.it")},
    "holidu": {"label": "Holidu", "domains": ("holidu.com", "holidu.it")},
    "agoda": {"label": "Agoda", "domains": ("agoda.com",)},
    "trip": {"label": "Trip.com", "domains": ("trip.com",)},
    "priceline": {"label": "Priceline", "domains": ("priceline.com",)},
    "travelocity": {"label": "Travelocity", "domains": ("travelocity.com",)},
    "tripadvisor": {"label": "Tripadvisor", "domains": ("tripadvisor.com", "tripadvisor.it")},
    "trivago": {"label": "Trivago", "domains": ("trivago.com", "trivago.it")},
    "googlehotels": {"label": "Google Hotels", "domains": ("google.com", "google.it")},
    "holidaycheck": {"label": "HolidayCheck", "domains": ("holidaycheck.com", "holidaycheck.it")},
}
DATE_URL_ADAPTERS = set(CHANNELS) - {"sito", "holidaycheck", "tripadvisor", "trivago", "googlehotels"}
PROFILE_AUDIT_CHANNELS = ("tripadvisor", "trivago", "googlehotels", "holidaycheck")
PUBLIC_FRONTEND_PRICING_CHANNELS = {"airbnb","expedia","vrbo","holidu","hotels","agoda","trip","priceline","travelocity"}
FRONTEND_FIRST_CHANNELS = set(PUBLIC_FRONTEND_PRICING_CHANNELS)
AUTO_SOURCE_DISCOVERY_TIMEOUT=28
AUTO_OTA_OBSERVE_TIMEOUT=55
HUMAN_ASSIST_TIMEOUT=120
BLOCK_WORDS = (
    "captcha", "verify you are human", "are you a robot", "unusual traffic",
    "javascript is disabled", "access denied", "security check", "verifica di sicurezza",
    "mostra di essere umano", "dimostra di essere umano", "show you're human", "prove you're human",
)
PRICE_RE = re.compile(r"(?:€|EUR)\s*([0-9]{1,5}(?:[.,][0-9]{2})?)|([0-9]{1,5}(?:[.,][0-9]{2})?)\s*(?:€|EUR)", re.I)
GENERIC_NAME_WORDS = {
    "hotel", "aparthotel", "resort", "b&b", "bb", "bed", "breakfast", "apartments",
    "apartment", "appartamenti", "appartamento", "rooms", "room", "suite", "suites",
}

# Descrittori commerciali che cambiano spesso tra sito ufficiale e OTA.
# Non sono parte dell'identità stabile della struttura: es. "Luxury Suites"
# e "Luxury Hotel & Restaurant" devono continuare a riconoscere "Perla Saracena".
IDENTITY_GENERIC_NAME_WORDS = GENERIC_NAME_WORDS | {
    "luxury", "restaurant", "ristorante", "boutique", "spa",
    "hotel", "hotels", "restaurant", "restaurants",
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
    base = normalize_ota_listing_url(channel, base)
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
        query.update(
            check_in=stay["checkin"], check_out=stay["checkout"], adults="2",
            locale="it", currency="EUR",
        )
    elif channel in {"expedia", "hotels", "travelocity"}:
        query.update(chkin=stay["checkin"], chkout=stay["checkout"], rm1="a2", currency="EUR")
    elif channel == "vrbo":
        query.update(chkin=stay["checkin"], chkout=stay["checkout"], d1=stay["checkin"], d2=stay["checkout"], startDate=stay["checkin"], endDate=stay["checkout"], adults="2", currency="EUR")
    elif channel == "holidu":
        query.update(checkin=stay["checkin"], checkout=stay["checkout"], adults="2", currency="EUR")
    elif channel == "agoda":
        # Mantiene esplicitamente sia arrivo sia partenza. "los" resta come controllo
        # ridondante della durata, utile nei layout Agoda che espongono solo check-in + notti.
        query.update(
            checkIn=stay["checkin"], checkOut=stay["checkout"], los=str(stay["nights"]),
            rooms="1", adults=str(stay.get("adults") or 2), children="0",
            currency="EUR", locale="it-it",
        )
    elif channel == "trip":
        query.update(checkIn=stay["checkin"], checkOut=stay["checkout"], adult="2", children="0", crn="1", curr="EUR", locale="it-IT")
    elif channel == "priceline":
        # Priceline viene datato tramite UI: la scheda resta invariata finché
        # il date picker non conferma il soggiorno richiesto.
        return base
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

    # Booking può renderizzare più searchbox contemporaneamente (header/sticky/body).
    # Non usare un "Cerca" globale: individua il contenitore che mostra davvero
    # entrambe le date appena selezionate e clicca il submit DI QUELLO STESSO BOX.
    submit=None
    submit_selector=""
    try:
        start_forms=list(_date_forms(date.fromisoformat(checkin)))
        end_forms=list(_date_forms(date.fromisoformat(checkout)))
        scoped=await page.evaluate(r"""({startForms,endForms}) => {
          const visible=(el) => {
            if (!el || el.getAttribute('aria-hidden')==='true') return false;
            const st=getComputedStyle(el);
            if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
            const r=el.getBoundingClientRect();
            return r.width>0 && r.height>0;
          };
          const textOf=(el) => [
            el?.textContent || '',
            el?.getAttribute?.('value') || '',
            el?.getAttribute?.('aria-label') || '',
            el?.getAttribute?.('placeholder') || ''
          ].join(' ').replace(/\s+/g,' ').trim().toLowerCase();

          document.querySelectorAll('[data-velora-searchbox-target]').forEach(el => el.removeAttribute('data-velora-searchbox-target'));

          const roots=[
            ...document.querySelectorAll('[data-testid="searchbox-layout-wide"]'),
            ...document.querySelectorAll('form[role="search"]'),
            ...document.querySelectorAll('form[action*="searchresults"]')
          ].filter((el,i,arr) => arr.indexOf(el)===i && visible(el));

          for (let i=0;i<roots.length;i++) {
            const root=roots[i];
            const start=root.querySelector('[data-testid="date-display-field-start"], input[name="checkin"]');
            const end=root.querySelector('[data-testid="date-display-field-end"], input[name="checkout"]');
            const container=root.querySelector('[data-testid="searchbox-dates-container"]');
            const s=textOf(start);
            const e=textOf(end);
            const both=textOf(container);
            const startOk=startForms.some(v => s.includes(String(v).toLowerCase())) ||
                          startForms.some(v => both.includes(String(v).toLowerCase()));
            const endOk=endForms.some(v => e.includes(String(v).toLowerCase())) ||
                        endForms.some(v => both.includes(String(v).toLowerCase()));
            const button=root.querySelector(
              '[data-testid="date-submit-button"], [data-testid="searchbox-submit-button"], button[type="submit"]'
            );
            if (startOk && endOk && button && visible(button)) {
              root.setAttribute('data-velora-searchbox-target','1');
              return {
                index:i,
                start:s.slice(0,120),
                end:e.slice(0,120),
                container:both.slice(0,180),
                buttonText:textOf(button).slice(0,100)
              };
            }
          }
          return null;
        }""",{"startForms":start_forms,"endForms":end_forms})
        if scoped:
            root=page.locator('[data-velora-searchbox-target="1"]').first
            candidates=root.locator(
                '[data-testid="date-submit-button"], [data-testid="searchbox-submit-button"], button[type="submit"]'
            )
            count=min(await candidates.count(),12)
            for idx in range(count):
                candidate=candidates.nth(idx)
                try:
                    if await candidate.is_visible(timeout=250):
                        submit=candidate
                        submit_selector=(
                            f"stesso searchbox date (box {scoped.get('index')}; "
                            f"button={scoped.get('buttonText') or 'submit'})"
                        )
                        break
                except Exception:
                    continue
    except Exception as exc:
        evidence.append(f"ricerca submit nello stesso searchbox fallita: {type(exc).__name__}")

    # Fallback soltanto se Booking non espone un contenitore associabile.
    if submit is None:
        submit, submit_selector = await _first_visible_locator(page, (
            '[data-testid="date-submit-button"]',
            '[data-testid="searchbox-submit-button"]',
            '[data-testid="searchbox-layout-wide"] button[type="submit"]',
            '[data-testid="searchbox-layout-wide"] button:has-text("Cerca")',
            '[data-testid="searchbox-layout-wide"] button:has-text("Search")',
            'form[role="search"] button[type="submit"]',
            'form[action*="searchresults"] button[type="submit"]',
        ))
        if submit is not None:
            submit_selector="fallback globale: " + submit_selector

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

    # Booking può lasciare le date nel DOM per un istante e poi azzerarle
    # quando completa la navigazione/idratazione React. Verifica che restino
    # stabili prima di dichiarare il tentativo riuscito.
    await page.wait_for_timeout(3200)
    try:
        stable_body=(await page.locator("body").inner_text(timeout=6000))[:12000]
    except Exception:
        stable_body=""
    stable_dom,stable_state=await booking_dom_dates_confirmed(page,stay)
    stable_url=booking_url_dates_confirmed(page.url,stay)
    stable_text=visible_dates_confirmed(stable_body,stay)
    if not (stable_dom or stable_url or stable_text):
        evidence.append(f"date confermate transitoriamente via {mode}, poi perse dopo stabilizzazione")
        evidence.append("campi stabilizzati: " + (stable_state or await visible_date_state() or "n.d."))
        evidence.append("URL stabilizzato: " + page.url[:350])
        return False, "; ".join(filter(None,evidence))

    stable_mode="campi visibili" if stable_dom else "URL" if stable_url else "testo visibile"
    evidence.append(f"date confermate e stabili dopo Cerca via {stable_mode}")
    return True, "; ".join(filter(None,evidence))

def _norm_name(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    ascii_text = re.sub(r"\bb\s*&\s*b\b|\bb\s+and\s+b\b|\bbed\s*&?\s*breakfast\b", " ", ascii_text)
    tokens = [token for token in re.findall(r"[a-z0-9]+", ascii_text) if token not in IDENTITY_GENERIC_NAME_WORDS]
    return " ".join(tokens)


def _property_name_query_variants(value: str) -> list[str]:
    """Varianti di ricerca stabili: mai lasciare '&' o descrittori commerciali come nome distintivo."""
    original=" ".join(str(value or "").split()).strip()
    normalized=_norm_name(original)
    full_without_symbols=re.sub(r"\s*&\s*"," ",original)
    full_without_symbols=re.sub(r"\s+"," ",full_without_symbols).strip()

    variants=[]
    for candidate in (normalized,full_without_symbols,original):
        candidate=" ".join(str(candidate or "").split()).strip()
        if not candidate:
            continue
        # Una variante composta solo da punteggiatura/simboli non deve mai entrare nelle query.
        if not re.search(r"[A-Za-zÀ-ÿ0-9]",candidate):
            continue
        key=_norm_name(candidate) or candidate.lower()
        if key and all((_norm_name(item) or item.lower()) != key for item in variants):
            variants.append(candidate)
    return variants[:4]


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
            if ota_id=="holidu" and "/d/" not in path:
                return ""
            if ota_id in {"expedia","hotels","travelocity"} and any(token in path.lower() for token in ("/hotel-search","/search")):
                return ""
            if ota_id=="priceline" and any(token in path.lower() for token in ("/search","/hotels/")) and "/relax/" not in path:
                return ""
            if ota_id=="tripadvisor" and any(token in path.lower() for token in ("/search","/searchresults")):
                return ""
            if ota_id=="googlehotels" and "/travel/hotels/" not in path:
                return ""
            return ota_id
    return ""


def _plausible_ota_listing_url(ota_id: str, url: str) -> bool:
    """Scarta pagine generiche/search/partner prima che diventino sorgenti tariffarie."""
    if _classify_ota_url(url) != ota_id:
        return False
    try:
        path=(urlparse(url).path or "").lower()
    except Exception:
        return False
    if ota_id=="airbnb":
        return bool(re.search(r"/rooms/\\d+",path))
    if ota_id in {"expedia","travelocity"}:
        return bool(re.search(r"\\.h\\d+\\.",path) or "hotel-information" in path or "informazioni-hotel" in path) and not any(token in path for token in ("travel-guide","hotel-search","top-10","/search"))
    if ota_id=="hotels":
        return bool(re.search(r"/ho\\d+",path) or "hotel-information" in path or "informazioni-hotel" in path)
    if ota_id=="vrbo":
        return bool("/pdp/" in path or re.search(r"/\\d+(?:ha|vb|vr)?/?$",path) or "/vacation-rental/" in path or "/holiday-rental/" in path)
    if ota_id=="holidu":
        return bool(re.search(r"/d/\\d+",path))
    if ota_id=="agoda":
        return "/hotel/" in path and not any(token in path for token in ("/partners/","partnersearch","/search"))
    if ota_id=="trip":
        # Trip.com usa /hotels/<citta>-hotel-detail-<id>/... per le schede.
        # Non accettare più le pagine elenco città (es. /hotels/barcelona-hotels-list-40795/):
        # in v78 potevano diventare una falsa source della struttura.
        return bool(re.search(r"hotel-detail-\d+",path)) and not any(
            token in path for token in ("/hot/","top-10","ranking","hotels-list","hotel-list")
        )
    if ota_id=="priceline":
        return "/relax/" in path or "hotel-deals" in path
    return True


def normalize_ota_listing_url(ota_id: str, url: str) -> str:
    """Normalizza una scheda OTA senza cambiare la struttura identificata."""
    try:
        parsed=urlparse(str(url or ""))
        if parsed.scheme not in {"http","https"} or not parsed.hostname:
            return str(url or "")
        query=dict(parse_qsl(parsed.query,keep_blank_values=True))
        path=parsed.path or ""
        if ota_id=="airbnb" and "/rooms/" in path.lower():
            return urlunparse(parsed._replace(
                netloc="www.airbnb.it",
                query=urlencode({"locale":"it","currency":"EUR"}),
                fragment="",
            ))
        if ota_id=="vrbo" and "/pdp/" in path.lower():
            return urlunparse(parsed._replace(query="",fragment=""))
        if ota_id=="holidu" and "/d/" in path.lower():
            return urlunparse(parsed._replace(query="",fragment=""))
        tracking_prefixes=("utm_","referrer","source_","semcid","siteid","gclid","fbclid","rfrr","pwa_","_x_")
        clean_query={
            key:value for key,value in query.items()
            if not any(str(key).lower().startswith(prefix) for prefix in tracking_prefixes)
        }
        return urlunparse(parsed._replace(query=urlencode(clean_query),fragment=""))
    except Exception:
        return str(url or "")


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
        url="https://www.google.com/search?" + urlencode({"q":query,"hl":"it","num":"30","udm":"14"})
    elif engine=="Bing":
        url="https://www.bing.com/search?" + urlencode({"q":query,"setlang":"it"})
    elif engine=="Brave":
        url="https://search.brave.com/search?" + urlencode({"q":query,"source":"web"})
    elif engine=="DuckDuckGo":
        url="https://duckduckgo.com/?" + urlencode({"q":query,"ia":"web"})
    else:
        return [],f"{engine}: motore non configurato"
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


def _free_http_search_links(
    query: str,
    preferred_domains: tuple[str, ...] = (),
) -> tuple[list[dict], list[dict]]:
    """Metasearch gratuita. In ricerca mirata prova prima Yahoo e si ferma appena trova il dominio OTA."""
    engines=(
        ("Yahoo HTTP","https://search.yahoo.com/search",{"p":query}),
        ("Bing HTTP","https://www.bing.com/search",{"q":query,"setlang":"it","count":"20"}),
        ("Google HTTP","https://www.google.com/search",{"q":query,"hl":"it","num":"20","filter":"0"}),
        ("DuckDuckGo HTML","https://html.duckduckgo.com/html/",{"q":query}),
    )
    out=[]
    stats=[]
    seen=set()
    preferred=tuple(str(domain or "").lower().removeprefix("www.") for domain in preferred_domains if domain)
    for engine,url,params in engines:
        engine_hits=0
        try:
            response=requests.get(
                url,
                params=params,
                headers={
                    "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language":"it-IT,it;q=0.9,en;q=0.7",
                },
                impersonate="chrome",
                timeout=5,
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
                host=(parsed.hostname or "").lower().removeprefix("www.")
                search_engine_host=any(token in host for token in ("google.com","google.it","bing.com","duckduckgo.com","yahoo.com"))
                google_hotels_target=(
                    host in {"google.com","google.it","www.google.com","www.google.it"}
                    and (parsed.path or "").lower().startswith("/travel/hotels")
                    and preferred
                    and any(domain in {"google.com","google.it"} for domain in preferred)
                )
                if search_engine_host and not google_hotels_target:
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
                if preferred and any(host==domain or host.endswith("."+domain) for domain in preferred):
                    engine_hits+=1
            stats.append({"engine":engine,"query":query,"status":"ok","links":count})
            if preferred and engine_hits:
                break
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



def _agoda_unit_listing_conflict(property_name: str, url: str, title: str="") -> bool:
    """Rifiuta le singole unità numerate quando si cerca il complesso/hotel principale.

    Esempio: un hotel da confrontare su Booking NON è automaticamente la scheda
    Agoda '3074 ... Camera Familiare by Barbarhouse', anche quando brand e località
    si somigliano. È una scheda commercialmente distinta.
    """
    try:
        parsed=urlparse(str(url or ""))
        host=str(parsed.hostname or "").lower()
        path=str(parsed.path or "").lower()
        if not (host=="agoda.com" or host.endswith(".agoda.com")):
            return False
        segments=[part for part in path.strip("/").split("/") if part]
        slug=next((part for part in segments if re.match(r"^\d{3,6}[-_]",part)), "")
        if not slug:
            return False
        # _norm_name elimina parole generiche (inclusi 'hotel' e 'restaurant'):
        # qui serve invece conservare il tipo di attività della richiesta.
        expected=" ".join(re.findall(
            r"[a-z0-9]+",
            unicodedata.normalize("NFKD",str(property_name or ""))
            .encode("ascii","ignore").decode("ascii").lower(),
        ))
        if not expected or re.match(r"^\d{3,6}\b",expected):
            return False
        hotel_brand=bool(re.search(
            r"\b(hotel|restaurant|ristorante|resort|boutique|agriresort|masseria|relais)\b",
            expected,
        ))
        # Se si sta auditando un hotel principale non accettare un codice camera
        # 3074-... (o simile) come se fosse la scheda dell'intero hotel.
        return bool(hotel_brand)
    except Exception:
        return False


def _strict_ota_identity_match(
    property_name: str,
    city: str,
    address: str,
    title: str,
    body: str,
    url: str,
) -> dict:
    """Blocco identità conservativo per impedire prezzi di strutture omonime/simili."""
    if _agoda_unit_listing_conflict(property_name,url,title):
        return {
            "ok":False,"score":0.0,"nameScore":0.0,"cityMatch":False,
            "addressRatio":0.0,
            "evidence":(
                "AGODA UNITÀ DIVERSA: URL numerato di singola unità/camera "
                "non equiparabile automaticamente alla scheda hotel principale. "
                "Cercare la scheda ufficiale dell'intera struttura."
            )
        }
    score,path_slug,title_score,slug_score,reasons=_identity_match_score(
        property_name,city,address,title,body[:3500],url
    )
    combined=_norm_name(" ".join(part for part in (title,body[:6000],path_slug) if part))
    city_norm=_norm_name(city)
    city_match=bool(city_norm and city_norm in combined)

    address_norm=_norm_name(address)
    address_ratio=0.0
    if address_norm:
        address_tokens={token for token in address_norm.split() if len(token)>=3 or token.isdigit()}
        combined_tokens=set(combined.split())
        if address_tokens:
            address_ratio=len(address_tokens & combined_tokens)/len(address_tokens)

    name_score=max(
        _name_similarity(property_name,title),
        _name_similarity(property_name,path_slug),
    )
    geo_ok=city_match or address_ratio>=0.50
    name_ok=name_score>=0.54
    strict_ok=bool(geo_ok and name_ok and score>=0.66)

    # Airbnb vende le camere/suite con titoli specifici e può mostrare il nome
    # della marina/frazione anziché il comune registrato in anagrafica.
    # Non rifiutare automaticamente "Hotel <brand> - Suite ..." solo perché
    # il titolo/indirizzo Airbnb non ripete il comune.
    airbnb_brand_verified=False
    if _classify_ota_url(url)=="airbnb" and re.search(r"/rooms/\d+",urlparse(url).path,re.I):
        strong_brand=_airbnb_listing_brand_match(property_name,title)
        title_hotel=bool(re.search(r"\b(hotel|camera in hotel|room in hotel)\b",title,re.I))
        # Dev'essere una scheda che parla davvero della struttura indicata,
        # non un risultato generico nella navigazione/suggerimenti.
        canonical_words=[
            token for token in _norm_name(property_name).split()
            if len(token)>=3 and token not in {
                "hotel","luxury","restaurant","ristorante","boutique",
                "resort","barbarhouse","suite","suites"
            }
        ][:2]
        body_norm=_norm_name(body[:5500])
        body_brand=bool(canonical_words and all(token in body_norm.split() for token in canonical_words))
        if strong_brand and title_hotel and body_brand and name_score>=0.48:
            airbnb_brand_verified=True
            strict_ok=True

    evidence_parts=[
        f"nome {name_score:.0%}",
        f"città {'confermata' if city_match else 'non confermata'}",
        f"indirizzo {address_ratio:.0%}" if address_norm else "indirizzo n.d.",
        f"score complessivo {score:.0%}",
    ]
    if airbnb_brand_verified:
        evidence_parts.append(
            "Airbnb: brand completo identificato nella testata e nella descrizione "
            "dell'annuncio camera/hotel; la località può essere una marina o frazione"
        )
        if not geo_ok:
            evidence_parts.append(
                "ATTENZIONE: comune non confermato testualmente; possibile località subordinata, "
                "verificare geografia prima di interpretare il delta"
            )
    if not strict_ok:
        evidence_parts.append("BLOCCATA: identità geografica/nome non sufficientemente confermati")
    return {
        "ok":strict_ok,
        "score":round(score,3),
        "nameScore":round(name_score,3),
        "cityMatch":city_match,
        "addressRatio":round(address_ratio,3),
        "evidence":" · ".join(evidence_parts),
    }


async def verify_ota_candidate_page(
    context,
    ota_id: str,
    url: str,
    property_name: str,
    city: str,
    address: str,
    robots: dict,
    page=None,
) -> dict:
    url=normalize_ota_listing_url(ota_id,url)
    permission=await asyncio.to_thread(allowed_by_robots,url,robots)
    if permission is False:
        return {
            "ok":False,"score":0.0,"title":"","url":url,
            "presenceDetected":True,
            "evidence":"Pagina OTA individuata, ma robots.txt nega l'accesso automatico: presenza registrata, contenuto non letto."
        }
    robots_note="robots.txt non disponibile/chiarificatore; verifica eseguita solo nel browser pubblico. " if permission is None else ""

    own_page=page is None
    if own_page:
        page=await context.new_page()
    try:
        # Riusa la stessa scheda di verifica quando viene fornita dal chiamante:
        # riduce drasticamente i continui flash about:blank durante la discovery.
        response=await page.goto(url,wait_until="domcontentloaded",timeout=25000)
        http_status=response.status if response else 0
        await dismiss_cookie(page)
        await page.wait_for_timeout(1100)
        try:
            body=(await page.locator("body").inner_text(timeout=6500))[:18000]
        except Exception:
            body=""
        title=(await page.title())[:260]
        auth_wall=ota_auth_wall(page.url,title,body)
        if auth_wall:
            return {
                "ok":False,"score":0.0,"title":title[:220],
                "url":urlunparse(urlparse(page.url)._replace(fragment="")),
                "evidence":f"Pagina candidata non utilizzata: {auth_wall}.",
                "httpStatus":http_status,
            }
        if any(word in body.lower() for word in BLOCK_WORDS):
            return {
                "ok":False,"score":0.0,"title":title[:220],
                "url":urlunparse(urlparse(page.url)._replace(fragment="")),
                "evidence":"Il portale ha mostrato una verifica/blocco; nessun aggiramento tentato.",
                "httpStatus":http_status,
            }
        if http_status>=400 and http_status not in {403,429}:
            return {
                "ok":False,"score":0.0,"title":title[:220],
                "url":urlunparse(urlparse(page.url)._replace(fragment="")),
                "evidence":f"Pagina candidata HTTP {http_status}.",
                "httpStatus":http_status,
            }
        if http_status in {403,429} and len(body.strip())<500:
            return {
                "ok":False,"score":0.0,"title":title[:220],
                "url":urlunparse(urlparse(page.url)._replace(fragment="")),
                "evidence":f"HTTP {http_status} e contenuto renderizzato insufficiente per verificare l'identità.",
                "httpStatus":http_status,
            }
        try:
            h1=page.locator("h1").first
            if await h1.count():
                h1_text=re.sub(r"\s+"," ",(await h1.inner_text(timeout=500)) or "").strip()
                if h1_text:
                    title=h1_text
        except Exception:
            pass
        identity=_strict_ota_identity_match(
            property_name,city,address,title,body,page.url
        )
        return {
            "ok":bool(identity.get("ok")),
            "score":identity.get("score",0.0),
            "title":title[:220],
            "url":urlunparse(urlparse(page.url)._replace(fragment="")),
            "evidence":(
                (f"HTTP {http_status} ma pagina completa renderizzata nel browser; " if http_status in {403,429} else "")
                + robots_note
                + identity.get("evidence","")
            )[:900],
            "httpStatus":http_status,
            "renderedDespiteHttpError":http_status in {403,429},
            "identity":{
                "nameScore":identity.get("nameScore",0.0),
                "cityMatch":bool(identity.get("cityMatch")),
                "addressRatio":identity.get("addressRatio",0.0),
            },
            "otaId":ota_id,
        }
    except Exception as exc:
        return {"ok":False,"score":0.0,"title":"","evidence":f"Verifica pagina fallita: {type(exc).__name__}: {str(exc)[:120]}"}
    finally:
        if own_page:
            try:
                await page.close()
            except Exception:
                pass


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

    # Google per primo, ma riutilizzando UNA sola scheda per tutte le varianti:
    # evita l'apertura/chiusura continua di about:blank.
    search_page=await context.new_page()
    try:
        for query in queries:
            try:
                links,search_url=await _search_result_links(search_page,query,"Google")
                before=diagnostics["candidates"]
                for item in links:
                    target=_decode_search_target(str(item.get("href") or ""))
                    ota_id=_classify_ota_url(target)
                    if not ota_id:
                        continue
                    if ota_id=="agoda" and _agoda_unit_listing_conflict(
                        name,target,str(item.get("text") or "")
                    ):
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
        try:
            await search_page.close()
        except Exception:
            pass

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

    verify_page=await context.new_page()
    try:
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
                verify=await verify_ota_candidate_page(context,ota_id,url,name,city,address,robots,page=verify_page)
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
                        "verification":"page_identity_lock","identityVerified":True,
                    }
                    break
                if _strong_search_evidence(score,reasons,engines):
                    weak.append((
                        score,url,title,reasons,engines,queries_used,
                        "Evidenza di ricerca forte ma NON sufficiente: la pagina OTA non ha superato la verifica identità diretta. "
                        + str(verify.get("evidence") or "")
                    ))
                    continue
                weak.append((score,url,title,reasons,engines,queries_used,verify.get("evidence","")))
            if ota_id not in discoveries and weak:
                score,url,title,reasons,engines,queries_used,verify_evidence=weak[0]
                discoveries[ota_id]={
                    "status":"not_verified_present","url":"","candidateUrl":normalize_ota_listing_url(ota_id,url),"title":title[:220],"score":round(score,3),
                    "presenceDetected":True,
                    "evidence":(
                        f"Ricerca master gratuita: esiste un candidato {OTA_META[ota_id]['label']} ma NON è stato "
                        f"attribuito alla struttura. Match {score:.0%} ({reasons}); {verify_evidence}. "
                        "La pagina viene registrata come presenza OTA; eventuali prezzi restano rilevati da verificare finché l'identità non è confermata."
                    )[:900],
                    "searchUrl":"",
                    "discoveryMode":"candidate rejected by identity lock",
                    "identityVerified":False,
                }
    finally:
        try:
            await verify_page.close()
        except Exception:
            pass
    return discoveries,diagnostics


def _airbnb_listing_brand_match(expected_name: str, listing_title: str) -> bool:
    """Stesso brand in testata, anche quando il nome termina con una tipologia.

    Non è sufficiente un nome generico; richiede almeno due token significativi
    consecutivi. Una località frazionaria non deve cancellare un candidato prima
    della verifica effettiva della pagina.
    """
    expected=_norm_name(expected_name)
    actual=_norm_name(listing_title)
    ignored={
        "hotel","luxury","restaurant","ristorante","resort","boutique",
        "suite","suites","room","rooms","barbarhouse","apartment","apartments"
    }
    tokens=[token for token in expected.split() if len(token)>=3 and token not in ignored]
    if len(tokens)<2:
        return False
    brand=" ".join(tokens[:2])
    return bool(re.search(r"(?<![a-z0-9])"+re.escape(brand)+r"(?![a-z0-9])",actual))


def _airbnb_index_urls_from_html(html_source: str) -> list[str]:
    """Recupera link /rooms/ dalle risposte pubbliche SERP anche se non sono <a>.

    Alcuni motori impacchettano il risultato in JSON/script invece del normale
    attributo href. Nessuna richiesta nascosta ad Airbnb, solo URL pubblici
    leggibili nell'HTML della ricerca già effettuata.
    """
    import html as html_module
    raw=html_module.unescape(str(html_source or ""))
    for _ in range(2):
        raw=unquote(raw)
    raw=raw.replace(r"\/","/").replace(r"\u002F","/").replace(r"\u002f","/")
    raw=raw.replace(r"\u003A",":").replace(r"\u003a",":")
    hits=[]
    for match in re.finditer(
        r'https?://(?:www\.)?airbnb\.(?:it|com)/rooms/(\d{5,24})',
        raw,re.I,
    ):
        host="airbnb.it" if ".it/" in match.group(0).lower() else "airbnb.com"
        url=f"https://www.{host}/rooms/{match.group(1)}"
        if url not in hits:
            hits.append(url)
    return hits[:35]


async def airbnb_frontend_search_property_listings(context, data: dict, robots: dict) -> tuple[list[dict],list[str]]:
    """Percorso Airbnb dal suo motore pubblico: home → destinazione → risultati → /rooms/.

    Non è una SERP Google: consulta Airbnb direttamente, senza login o API interne.
    Cerca per brand e poi località, raccoglie le schede, rimanda la prova identità
    alla verifica della singola scheda prima del pricing.
    """
    name=str(data.get("name") or "").strip()
    city=str(data.get("city") or "").strip()
    address=str(data.get("address") or "").strip()
    tokens=[
        token for token in _norm_name(name).split()
        if len(token)>=3 and token not in {
            "hotel","restaurant","ristorante","luxury","boutique","resort",
            "suite","suites","barbarhouse","rooms","room","apartment","apartments",
        }
    ]
    brand=" ".join(tokens[:2]) or name
    home="https://www.airbnb.it/"
    diagnostics=[]
    if await asyncio.to_thread(allowed_by_robots,home,robots) is False:
        return [],["Airbnb homepage: robots.txt nega scraping"]
    page=None
    found={}
    try:
        page=await context.new_page()
        response=await page.goto(home,wait_until="domcontentloaded",timeout=18000)
        await dismiss_cookie(page)
        await page.wait_for_timeout(800)
        if response and response.status in {403,429}:
            return [],[f"Airbnb homepage: HTTP {response.status}"]
        diagnostics.append("Airbnb homepage caricata")

        async def collect_cards(label: str) -> int:
            try:
                links=await page.evaluate(r"""() => {
                    const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
                    return Array.from(document.querySelectorAll('a[href*="/rooms/"]')).slice(0,700).map(a=>{
                        const card=a.closest(
                          '[data-testid="card-container"],[data-testid*="listing"],article,li,section'
                        ) || a.parentElement?.parentElement || a;
                        return {
                          url:a.href,
                          title:clean(a.innerText||a.textContent||a.getAttribute('aria-label')).slice(0,320),
                          context:clean(card?.innerText||card?.textContent).slice(0,750),
                        };
                    });
                }""")
            except Exception as exc:
                diagnostics.append(f"{label}: cards={type(exc).__name__}")
                return 0
            added=0
            for item in links:
                url=normalize_ota_listing_url("airbnb",str(item.get("url") or ""))
                if not _plausible_ota_listing_url("airbnb",url):
                    continue
                title=str(item.get("title") or "")
                snippet=str(item.get("context") or "")
                # Un risultato può essere titolato solo "Suite Familiare":
                # in quel caso non attribuirlo per vicinanza, serve il brand nel
                # contesto della card; se manca, non attribuire false identità.
                if not (
                    _airbnb_listing_brand_match(name,title)
                    or _airbnb_listing_brand_match(name,snippet)
                    or _name_similarity(name,title)>=0.53
                    or _name_similarity(name,snippet)>=0.58
                ):
                    continue
                match=re.search(r"/rooms/(\d+)",urlparse(url).path,re.I)
                if not match:
                    continue
                rid=match.group(1)
                if rid not in found:
                    found[rid]={"url":url,"title":title or snippet[:140],
                                "context":snippet}
                    added+=1
            diagnostics.append(f"{label}: {len(links)} card Airbnb · {added} brand match")
            return added

        await collect_cards("Airbnb home")
        opener_selectors=(
            'button:has-text("Dove vuoi andare")',
            'button:has-text("Where to")',
            '[data-testid*="structured-search-input-field-query"]',
            '[data-testid*="little-search-location"]',
            'button[aria-label*="Dove" i]',
            'button[aria-label*="Where" i]',
            '[role="button"][aria-label*="Where" i]',
        )
        field_selectors=(
            'input[data-testid*="structured-search-input-field-query"]',
            'input[placeholder*="Cerca" i]',
            'input[placeholder*="destinazione" i]',
            'input[placeholder*="search destinations" i]',
            'input[placeholder*="where" i]',
            'input[aria-label*="Dove" i]',
            'input[aria-label*="Where" i]',
            'input[role="combobox"]',
            'input[type="search"]',
        )
        queries=[brand]
        if city and _norm_name(city)!=_norm_name(brand):
            queries.append(city)
        if address and _norm_name(address) not in {_norm_name(city),_norm_name(brand)}:
            queries.append(address)
        for term in queries[:2]:
            if len(found)>=5:
                break
            try:
                opener,_=await _first_visible_locator(page,opener_selectors)
                if opener is not None:
                    try:
                        await opener.click(timeout=1500)
                    except Exception:
                        pass
                field,selected_selector=await _first_visible_locator(page,field_selectors)
                if field is None:
                    diagnostics.append(f"Airbnb ricerca «{term}»: input destinazione assente")
                    continue
                await field.click(timeout=1500)
                await field.fill(term,timeout=2000)
                await page.wait_for_timeout(800)
                # L'utente conferma un suggerimento esplicito anziché scrivere
                # in un campo HTML non utilizzato dal motore.
                suggestions=page.locator(
                    '[role="option"],[data-testid*="option"],'
                    '[data-testid*="destination-result"],[data-testid*="prediction"]'
                )
                clicked=False
                try:
                    for idx in range(min(await suggestions.count(),12)):
                        loc=suggestions.nth(idx)
                        if await loc.is_visible(timeout=150):
                            await loc.click(timeout=1300)
                            clicked=True
                            break
                except Exception:
                    pass
                if not clicked:
                    await field.press("Enter",timeout=1300)
                action,_=await _first_visible_locator(page,(
                    'button:has-text("Cerca")','button:has-text("Search")',
                    '[data-testid="structured-search-input-search-button"]',
                    '[data-testid*="search-button"]',
                ))
                if action is not None:
                    try:
                        await action.click(timeout=2500)
                    except Exception:
                        pass
                await page.wait_for_timeout(1800)
                await collect_cards(f"Airbnb ricerca «{term}»")
                for offset in (0.35,0.72):
                    try:
                        await page.evaluate(
                            "(p) => window.scrollTo(0,Math.floor(document.body.scrollHeight*p))",
                            offset
                        )
                        await page.wait_for_timeout(450)
                        await collect_cards(f"Airbnb ricerca «{term}» scroll")
                    except Exception:
                        break
                diagnostics.append(f"Airbnb ricerca «{term}»: url={page.url[:150]}")
            except Exception as exc:
                diagnostics.append(
                    f"Airbnb ricerca «{term}»: {type(exc).__name__}: {str(exc)[:100]}"
                )
                continue
    except Exception as exc:
        diagnostics.append(f"Airbnb home browser: {type(exc).__name__}: {str(exc)[:110]}")
        # Ricerca pubblica Airbnb tramite URL della pagina risultati, utile
        # quando il nuovo componente React non espone un input testuale leggibile.
        # Non è una API privata e non inventa annunci: scansiona le card reali.
        if not found:
            for search_term in queries[:2]:
                try:
                    safe_term=re.sub(r"[^a-z0-9 -]","",str(search_term).lower()).strip()
                    path_term=re.sub(r"\s+","-",safe_term) or "homes"
                    search_url=(
                        "https://www.airbnb.it/s/"+path_term+"/homes?"
                        + urlencode({"query":search_term,"adults":"2"})
                    )
                    result=await page.goto(
                        search_url,wait_until="domcontentloaded",timeout=13000,
                    )
                    await dismiss_cookie(page)
                    await page.wait_for_timeout(1400)
                    if result and result.status in {403,429}:
                        diagnostics.append(f"Airbnb risultati «{search_term}»: HTTP {result.status}")
                        continue
                    await collect_cards(f"Airbnb risultati «{search_term}»")
                    for fraction in (0.3,0.65,0.9):
                        await page.evaluate(
                            "(f)=>window.scrollTo(0,Math.floor(document.body.scrollHeight*f))",
                            fraction,
                        )
                        await page.wait_for_timeout(300)
                        await collect_cards(f"Airbnb risultati «{search_term}» scroll")
                    diagnostics.append(
                        f"Airbnb pagina risultati «{search_term}»: {page.url[:135]}"
                    )
                    if found:
                        break
                except Exception as exc:
                    diagnostics.append(
                        f"Airbnb risultati «{search_term}»: {type(exc).__name__}"
                    )
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass

    return list(found.values())[:14],diagnostics


async def discover_airbnb_property_listings(context, data: dict, robots: dict) -> dict:
    """Discovery Airbnb per complessi con PIÙ annunci camera: Google → Airbnb → verifica.

    A differenza di un hotel OTA unico, Airbnb espone spesso /rooms/ per ogni tipologia.
    I candidati sono trovati dinamicamente (senza ID o URL di strutture hardcoded).
    Non usa login, account, tariffe member o API a pagamento.
    """
    name=str(data.get("name") or "").strip()
    city=str(data.get("city") or "").strip()
    address=str(data.get("address") or "").strip()
    brand=_norm_name(name) or name
    # Le singole camere Airbnb spesso sono indicizzate col solo brand breve
    # seguito dalla tipologia: l'esatta ragione sociale hotel è troppo lunga.
    tokens=[token for token in brand.split() if len(token)>2 and token not in {
        "luxury","hotel","restaurant","ristorante","resort","boutique",
        "suites","suite","rooms","room","apartment","apartments","barbarhouse"
    }]
    distinctive=" ".join(tokens[:5])
    core_brand=" ".join(tokens[:2]) if len(tokens)>=2 else distinctive
    if not core_brand:
        return {"status":"not_found","url":"","identityVerified":False,
                "evidence":"Airbnb: nome distintivo non disponibile."}

    # Zero identificativi di strutture fissati nel software: ricerca pubblica
    # dello stesso brand adattabile a qualunque hotel, B&B o appartamento.
    query_variants=[
        f'site:airbnb.it/rooms/ "{core_brand}"',
        f'site:airbnb.com/rooms/ "{core_brand}"',
        f'"Hotel {core_brand}" Airbnb',
        f'"{core_brand}" Airbnb camere',
        f'site:airbnb.it/rooms/ "{distinctive}"',
        f'site:airbnb.com/rooms/ "{distinctive}"',
    ]
    if city:
        query_variants.extend((
            f'"{core_brand}" "{city}" Airbnb',
            f'site:airbnb.it/rooms/ "{core_brand}" "{city}"',
        ))
    query_variants=list(dict.fromkeys(query_variants))
    hits={}
    diagnostics=[]
    search_page=await context.new_page()
    try:
        # Il Google/Bing visibile nel browser è prioritario: la ricerca locale
        # non dipende più da Yahoo/Bing HTTP che consumavano il watchdog.
        browser_searches=[
            ("Google",query_variants[0]),
            ("Bing",query_variants[2]),
            ("Brave",query_variants[2]),
            ("DuckDuckGo",query_variants[0]),
        ]
        for idx,(engine,query) in enumerate(browser_searches):
            if len(hits)>=5:
                break
            try:
                links,url=await asyncio.wait_for(
                    _search_result_links(search_page,query,engine),
                    timeout=8,
                )
                diagnostics.append(f"{engine} {idx+1}: {len(links)} link")
            except Exception as exc:
                diagnostics.append(f"{engine} {idx+1}: {type(exc).__name__}")
                continue
            # Alcune SERP pubbliche espongono gli URL rooms solo nel sorgente
            # HTML/JSON della risposta, non tra i link cliccabili.
            try:
                raw_index_page=await search_page.content()
                extracted=_airbnb_index_urls_from_html(raw_index_page)
                diagnostics.append(f"{engine} {idx+1}: {len(extracted)} URL rooms nel sorgente")
                for index_url in extracted:
                    links.append({
                        "href":index_url,"text":f"{core_brand} Airbnb",
                        "context":"Risultato Airbnb rooms indicizzato; identità da verificare nella scheda",
                    })
            except Exception as extract_exc:
                diagnostics.append(f"{engine} {idx+1}: sorgente {type(extract_exc).__name__}")
            for item in links:
                target=_decode_search_target(str(item.get("href") or ""))
                if not _plausible_ota_listing_url("airbnb",target):
                    continue
                match=re.search(r"/rooms/(\d+)",urlparse(target).path,re.I)
                if not match:
                    continue
                title=str(item.get("text") or "")
                snippet=str(item.get("context") or "")
                score,_,_,_,reasons=_identity_match_score(name,city,address,title,snippet,target)
                name_score=_name_similarity(name,title)
                # Non richiede la stessa città nella SERP: una struttura a Salve
                # può pubblicare le singole camere con la marina "Torre Pali".
                if not (_airbnb_listing_brand_match(name,title) or name_score>=0.49 or score>=0.58):
                    continue
                rid=match.group(1)
                if rid not in hits or score>hits[rid][0]:
                    hits[rid]=(score,normalize_ota_listing_url("airbnb",target),
                               title,reasons)
            print(
                f"airbnb-browser-search {engine}: SERP={len(links)} links · "
                f"annunci Airbnb candidati={len(hits)}",
                flush=True,
            )
            if len(hits)>=5:
                break
    finally:
        try:
            await search_page.close()
        except Exception:
            pass

    # Fallback realmente indipendente dalle pagine HTML di Google:
    # Bing RSS pubblica URL e titoli anche quando la SERP browser non espone link.
    if len(hits)<5:
        for q in (
            f'site:airbnb.com/rooms/ "{core_brand}"',
            f'"Hotel {core_brand}" site:airbnb.it/rooms/',
        ):
            try:
                rss_items=await asyncio.wait_for(
                    asyncio.to_thread(_bing_rss_items,q),timeout=7,
                )
                diagnostics.append(f"Bing RSS: {len(rss_items)} risultati")
            except Exception as exc:
                diagnostics.append(f"Bing RSS: {type(exc).__name__}")
                continue
            for item in rss_items:
                title=str(item.get("title") or "")
                desc=str(item.get("description") or "")
                raw_links=[str(item.get("link") or "")]
                raw_links+=_airbnb_index_urls_from_html(desc)
                for target in raw_links:
                    target=_decode_search_target(target)
                    if not _plausible_ota_listing_url("airbnb",target):
                        continue
                    match=re.search(r"/rooms/(\d+)",urlparse(target).path,re.I)
                    if not match:
                        continue
                    score,_,_,_,reasons=_identity_match_score(
                        name,city,address,title,desc,target,
                    )
                    if not (
                        _airbnb_listing_brand_match(name,title)
                        or _name_similarity(name,title)>=0.49 or score>=0.58
                    ):
                        continue
                    rid=match.group(1)
                    if rid not in hits or score>hits[rid][0]:
                        hits[rid]=(score,normalize_ota_listing_url("airbnb",target),
                                   title,reasons)
            if len(hits)>=5:
                break

    # Se il motore di ricerca nel browser non ha restituito annunci, prova
    # UNA ricerca metasearch gratuita mirata con timeout separato.
    if not hits:
        query=f'site:airbnb.it/rooms/ "{core_brand}"'
        try:
            http_items,_=await asyncio.wait_for(
                asyncio.to_thread(_free_http_search_links,query,("airbnb.it","airbnb.com")),
                timeout=9,
            )
            diagnostics.append(f"metasearch pubblico: {len(http_items)} risultati")
            for item in http_items:
                target=_decode_search_target(str(item.get("url") or item.get("link") or ""))
                if not _plausible_ota_listing_url("airbnb",target):
                    continue
                match=re.search(r"/rooms/(\d+)",urlparse(target).path,re.I)
                if not match:
                    continue
                title=str(item.get("title") or item.get("text") or "")
                snippet=str(item.get("context") or item.get("description") or "")
                score,_,_,_,reasons=_identity_match_score(name,city,address,title,snippet,target)
                if not (_airbnb_listing_brand_match(name,title) or _name_similarity(name,title)>=0.49 or score>=0.58):
                    continue
                rid=match.group(1)
                if rid not in hits or score>hits[rid][0]:
                    hits[rid]=(score,normalize_ota_listing_url("airbnb",target),
                               title,reasons)
        except Exception as exc:
            diagnostics.append(f"metasearch: {type(exc).__name__}")

    # Ultima strada autonoma: eseguire la ricerca reale dentro Airbnb,
    # non pretendere che Google/Bing espongano la URL della camera.
    if len(hits)<2:
        try:
            internal,internal_diag=await asyncio.wait_for(
                airbnb_frontend_search_property_listings(context,data,robots),
                timeout=42,
            )
            diagnostics.extend(internal_diag[:16])
            for item in internal:
                url=str(item.get("url") or "")
                match=re.search(r"/rooms/(\d+)",urlparse(url).path,re.I)
                if not match:
                    continue
                title=str(item.get("title") or "")
                snippet=str(item.get("context") or "")
                score,_,_,_,reasons=_identity_match_score(
                    name,city,address,title,snippet,url
                )
                rid=match.group(1)
                if rid not in hits or score>hits[rid][0]:
                    hits[rid]=(score,url,title,reasons)
        except Exception as exc:
            diagnostics.append(f"Airbnb frontend interno: {type(exc).__name__}")

    ranked=sorted(hits.values(),key=lambda row:row[0],reverse=True)
    print(
        f"airbnb-indexed-discovery: candidati={len(ranked)} · "
        f"query brand={core_brand} · {'; '.join(diagnostics[-14:])[:1050]}",
        flush=True,
    )
    verified=[]
    failed=[]
    # Verifica ogni candidato sul SUO annuncio prima di estrarre tariffe.
    for score,url,title,reasons in ranked[:5]:
        try:
            check=await asyncio.wait_for(
                verify_ota_candidate_page(context,"airbnb",url,name,city,address,robots),
                timeout=11,
            )
        except Exception as exc:
            failed.append(f"{urlparse(url).path[-35:]}: {type(exc).__name__}")
            continue
        if check.get("ok"):
            actual_url=normalize_ota_listing_url("airbnb",str(check.get("url") or url))
            verified.append({
                "url":actual_url,"title":str(check.get("title") or title),
                "score":check.get("score",score),
                "identityVerified":True,
                "evidence":str(check.get("evidence") or "")[:330],
            })
            print(
                f"airbnb-listing-verified: {actual_url[:200]} · {str(check.get('title') or title)[:100]}",
                flush=True,
            )
        else:
            failed.append(f"{urlparse(url).path[-35:]}: {str(check.get('evidence') or '')[:85]}")

    if verified:
        primary=verified[0]
        return {
            "status":"found","url":primary["url"],
            "title":primary["title"],"score":primary["score"],
            "identityVerified":True,"verification":"page_identity_lock",
            "listingUrls":[item["url"] for item in verified],
            "listings":verified,
            "candidateUrls":[item[1] for item in ranked[:12]],
            "presenceDetected":True,
            "discoveryMode":"Airbnb Google public indexed rooms + strict page verification",
            "evidence":(
                f"Airbnb: {len(verified)} annunci camera/unità verificati per la struttura; "
                f"prima scheda: {primary['title']}. "
                f"Ricerca senza ID hardcoded; {'; '.join(diagnostics)}. "
                f"Altri candidati non confermati: {len(failed)}."
            )[:900],
        }
    if ranked:
        return {
            "status":"not_verified_present","url":"",
            "candidateUrl":ranked[0][1],
            "candidateUrls":[item[1] for item in ranked[:12]],
            "identityVerified":False,"presenceDetected":True,
            "evidence":(
                f"Airbnb: {len(ranked)} annunci candidati trovati, ma la verifica "
                f"nome/località nel frontend non è conclusiva. {'; '.join(failed[:3])}"
            )[:900],
            "discoveryMode":"Airbnb indexed candidates awaiting identity verification",
        }
    return {
        "status":"not_found","url":"","identityVerified":False,
        "evidence":(
            f"Airbnb: nessun annuncio /rooms/ emerso dalla ricerca pubblica con "
            f"«{core_brand}». {'; '.join(diagnostics)}. "
            "Questo esito non dimostra che la struttura non sia su Airbnb."
        )[:900],
        "discoveryMode":"Airbnb public Google/Bing index and metasearch exhausted",
    }


async def discover_single_ota_targeted(context, ota_id: str, data: dict, robots: dict) -> dict:
    """Discovery mirata multi-strada: site search, indice RSS e browser search."""
    if ota_id=="airbnb":
        # Non iniziare altre 12 ricerche generiche dopo il percorso dedicato:
        # consumavano il watchdog e nascondevano l'esito reale.
        return await discover_airbnb_property_listings(context,data,robots)
    meta=OTA_META[ota_id]
    name=str(data.get("name") or "")
    city=str(data.get("city") or "")
    address=str(data.get("address") or "")
    location=city or address
    variants=_property_name_query_variants(name)
    distinctive=(variants[0] if variants else name).strip()

    site_queries=[]
    for variant in variants[:3]:
        for domain in meta["domains"]:
            scope=(
                f"site:{domain}/travel/hotels"
                if ota_id=="googlehotels"
                else f"site:{domain}"
            )
            if variant and location:
                site_queries.append(f'{scope} "{variant}" "{location}"')
            if variant:
                site_queries.append(f'{scope} "{variant}"')

    # I motori non sempre rispettano bene site: per Airbnb/Holidu/Priceline.
    # Aggiungi query libere col nome del portale: è il caso reale di Perla Saracena,
    # che gli indici pubblici trovano come "Hotel Perla Saracena ..." su Airbnb.
    broad_queries=[]
    for variant in variants[:2]:
        if variant and location:
            broad_queries.append(f'"{variant}" "{location}" {meta["label"]}')
        if variant:
            broad_queries.append(f'"{variant}" {meta["label"]}')
    if distinctive:
        broad_queries.append(f'"Hotel {distinctive}" {meta["label"]}')

    # In v79 le prime 8 query erano quasi tutte site: e le query libere non venivano
    # mai raggiunte per OTA con più domini/varianti (caso Airbnb). Intercala subito
    # le query libere: servono quando l'indice conosce la pagina ma non la restituisce con site:.
    if ota_id in FRONTEND_FIRST_CHANNELS:
        ordered_queries=[*broad_queries[:5],*site_queries[:7],*broad_queries[5:],*site_queries[7:]]
    else:
        ordered_queries=[*site_queries[:4],*broad_queries[:5],*site_queries[4:],*broad_queries[5:]]
    queries=list(dict.fromkeys(query for query in ordered_queries if query))[:16]
    if not queries:
        return {
            "status":"not_verified_present","url":"","title":"","score":0.0,
            "presenceDetected":False,
            "evidence":f"Ricerca mirata {meta['label']} saltata: nome struttura non disponibile.",
            "searchUrl":"","discoveryMode":"targeted discovery","identityVerified":False,
        }

    candidates=[]
    used_query=""

    def collect_items(items, query, engine_label=""):
        nonlocal used_query
        used_query=query or used_query
        for item in items or []:
            target=str(item.get("url") or item.get("link") or "")
            if not target:
                continue
            target=_decode_search_target(target) or target
            if _classify_ota_url(target)!=ota_id or not _plausible_ota_listing_url(ota_id,target):
                continue
            text_value=str(item.get("text") or item.get("title") or "")
            if ota_id=="agoda" and _agoda_unit_listing_conflict(name,target,text_value):
                continue
            context_value=str(item.get("context") or item.get("description") or "")
            score,path_slug,text_score,url_score,reasons=_identity_match_score(
                name,city,address,text_value,context_value,target
            )
            candidates.append((
                score,target,text_value,reasons,
                str(item.get("engine") or engine_label or "search index")
            ))

    # 1) HTTP metasearch: rapido e gratuito.
    for query in queries[:12]:
        try:
            http_items,_=await asyncio.wait_for(
                asyncio.to_thread(_free_http_search_links,query,tuple(meta["domains"])),
                timeout=8,
            )
        except asyncio.TimeoutError:
            continue
        except Exception:
            continue
        collect_items(http_items,query)
        if candidates:
            break

    # 2) Bing RSS: spesso espone risultati che la SERP HTML nasconde.
    if not candidates:
        for query in broad_queries[:3] or queries[:3]:
            try:
                rss_items=await asyncio.wait_for(
                    asyncio.to_thread(_bing_rss_items,query),
                    timeout=6,
                )
            except Exception:
                continue
            collect_items(rss_items,query,"Bing RSS")
            if candidates:
                break

    # 3) Ultimo fallback: vera SERP nel browser pubblico, una sola query forte.
    # Nessuna API a pagamento e nessun hard-code della struttura.
    if not candidates and distinctive:
        search_query=f'"{distinctive}" {meta["label"]}'
        search_page=None
        try:
            search_page=await context.new_page()
            links,_=await asyncio.wait_for(
                _search_result_links(search_page,search_query,"Google"),
                timeout=12,
            )
            browser_items=[]
            for item in links:
                browser_items.append({
                    "url":_decode_search_target(str(item.get("href") or "")),
                    "text":str(item.get("text") or ""),
                    "context":str(item.get("context") or ""),
                    "engine":"Google browser",
                })
            collect_items(browser_items,search_query,"Google browser")
        except Exception:
            pass
        finally:
            if search_page is not None:
                try:
                    await search_page.close()
                except Exception:
                    pass

    # Deduplica URL e conserva il punteggio più alto.
    grouped={}
    for row in candidates:
        score,target,title,reasons,engine=row
        clean=normalize_ota_listing_url(ota_id,target)
        old=grouped.get(clean)
        if not old or score>old[0]:
            grouped[clean]=(score,clean,title,reasons,engine)
    candidates=sorted(grouped.values(),key=lambda row:row[0],reverse=True)

    if candidates:
        score,target,title,reasons,engine=candidates[0]
        candidate_urls=[row[1] for row in candidates[:8]]
        if score < 0.38:
            return {
                "status":"not_verified_present","url":"","candidateUrl":target,
                "candidateUrls":candidate_urls,
                "title":title[:220],"score":round(score,3),
                "presenceDetected":True,
                "evidence":(
                    f"Ricerca mirata {meta['label']}: candidato pubblico trovato ma identità ancora debole "
                    f"({score:.0%}: {reasons}). Presenza candidata registrata; nessun prezzo viene attribuito."
                )[:900],
                "searchUrl":"","discoveryMode":"weak candidate retained","identityVerified":False,
            }
        return {
            "status":"not_verified_present","url":"",
            "candidateUrl":target,
            "candidateUrls":candidate_urls,
            "title":title[:220],"score":round(score,3),"presenceDetected":True,
            "evidence":(
                f"Ricerca mirata {meta['label']} tramite {engine} con brand «{distinctive}». "
                f"Candidato pubblico trovato con match {score:.0%} ({reasons}); query «{used_query}». "
                "Presenza registrata; identità e tariffe saranno verificate nella fase pricing."
            )[:900],
            "searchUrl":"","discoveryMode":"multi-path targeted candidate deferred to pricing","identityVerified":False,
        }
    return {
        "status":"not_verified_present","url":"","title":"","score":0.0,
        "presenceDetected":False,
        "evidence":(
            f"Ricerca mirata {meta['label']} completata con brand «{distinctive}» su più indici pubblici: "
            "nessun candidato è emerso in questo passaggio automatico. "
            "Questo esito non dimostra che la struttura sia assente dal portale."
        )[:900],
        "searchUrl":"","discoveryMode":"targeted multi-path no candidate","identityVerified":False,
    }

async def discover_all_ota_sources(
    context, data: dict, robots: dict, on_progress=None, selected_ota_ids=None
) -> tuple[dict,dict]:
    """Discovery limitata ai soli canali selezionati dall'utente."""
    target_order=[
        ota_id for ota_id in OTA_DISCOVERY_ORDER
        if not selected_ota_ids or ota_id in set(selected_ota_ids)
    ]
    discoveries,diagnostics=await discover_otas_from_master_search(context,data,robots)
    discoveries={ota_id:value for ota_id,value in discoveries.items() if ota_id in target_order}
    diagnostics["selectedOtas"]=target_order
    total=len(target_order)
    if on_progress:
        await on_progress({
            "stage":"targeted",
            "completed":0,
            "total":total,
            "otaId":"",
            "label":"Ricerca master completata",
        },discoveries,diagnostics)

    for index,ota_id in enumerate(target_order, start=1):
        current=discoveries.get(ota_id)
        if ota_id=="agoda" and current:
            cached_candidate=current.get("url") or current.get("candidateUrl") or ""
            if _agoda_unit_listing_conflict(data.get("name",""),cached_candidate,current.get("title","")):
                discoveries.pop(ota_id,None)
                current=None

        # La ricerca master ha già interrogato più motori e più varianti.
        # Non rifare da zero la stessa ricerca per ogni OTA se esiste già un candidato:
        # era la causa principale dei 10-15 minuti di attesa apparentemente "bloccata".
        # Booking viene risolto più avanti dal flusso specializzato, molto più affidabile.
        needs_targeted = (
            ota_id != "booking"
            and (
                ota_id=="airbnb" or (

                not current
                or (
                    current.get("status")!="found"
                    and not current.get("candidateUrl")
                ))
            )
        )
        if needs_targeted:
            try:
                targeted=await asyncio.wait_for(
                    discover_single_ota_targeted(context,ota_id,data,robots),
                    timeout=155 if ota_id=="airbnb" else 38,
                )
            except asyncio.TimeoutError:
                targeted={
                    "status":"not_verified_present","url":"","title":"","score":0.0,
                    "evidence":(
                        f"Ricerca mirata {OTA_META[ota_id]['label']} fermata dal watchdog; "
                        "nessuna conclusione di assenza viene registrata. La scansione prosegue sulle altre OTA."
                    ),
                    "searchUrl":"",
                    "discoveryMode":"targeted watchdog timeout",
                    "identityVerified":False,
                }
            except Exception as exc:
                targeted={
                    "status":"not_verified_present","url":"","title":"","score":0.0,
                    "evidence":(
                        f"Ricerca mirata {OTA_META[ota_id]['label']} non completata: "
                        f"{type(exc).__name__}: {str(exc)[:180]}. La scansione prosegue."
                    ),
                    "searchUrl":"",
                    "discoveryMode":"targeted isolated error",
                    "identityVerified":False,
                }
            if ota_id=="airbnb":
                # Conserva anche candidati emersi dal metasearch master, ma rendi
                # SEMPRE visibile la diagnostica della ricerca specializzata.
                if current and current.get("identityVerified") is True and current.get("url") and targeted.get("status")!="found":
                    current["airbnbDiscoveryDiagnostics"]=str(targeted.get("evidence") or "")[:850]
                    discoveries[ota_id]=current
                else:
                    prior_urls=[]
                    if current:
                        for value in [current.get("url"),current.get("candidateUrl"),*(current.get("candidateUrls") or [])]:
                            if value and _plausible_ota_listing_url("airbnb",value) and value not in prior_urls:
                                prior_urls.append(value)
                    if targeted.get("status")!="found" and prior_urls:
                        targeted["candidateUrls"]=list(dict.fromkeys(
                            (targeted.get("candidateUrls") or [])+prior_urls
                        ))[:12]
                        if not targeted.get("candidateUrl"):
                            targeted["candidateUrl"]=prior_urls[0]
                        targeted["presenceDetected"]=True
                        targeted["evidence"]=(
                            str(targeted.get("evidence") or "")
                            + f" | Metasearch master: {len(prior_urls)} ulteriori URL Airbnb candidati da verificare."
                        )[:1050]
                    discoveries[ota_id]=targeted
            elif targeted.get("status")=="found":
                discoveries[ota_id]=targeted
            elif ota_id not in discoveries:
                discoveries[ota_id]=targeted
        if on_progress:
            await on_progress({
                "stage":"targeted",
                "completed":index,
                "total":total,
                "otaId":ota_id,
                "label":OTA_META[ota_id]["label"],
            },discoveries,diagnostics)
    return discoveries,diagnostics



def agoda_url_dates_confirmed(url: str, stay: dict) -> bool:
    """Conferma i parametri Agoda solo quando check-in e durata coincidono con il campione."""
    try:
        query=dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
    except Exception:
        return False
    normalized={str(key).lower(): str(value) for key,value in query.items()}
    checkin=normalized.get("checkin") or normalized.get("check_in") or ""
    checkout=normalized.get("checkout") or normalized.get("check_out") or ""
    los=normalized.get("los") or normalized.get("lengthofstay") or normalized.get("nights") or ""
    if checkin != stay["checkin"]:
        return False
    if checkout:
        return checkout == stay["checkout"]
    try:
        return int(los) == int(stay["nights"])
    except (TypeError,ValueError):
        return False


async def agoda_dom_dates_confirmed(page, stay: dict) -> tuple[bool,str]:
    """Legge i controlli data visibili di Agoda senza usare il solo testo generico della pagina."""
    try:
        state=await page.evaluate(r"""() => {
          const visible=(el) => {
            if (!el || el.getAttribute('aria-hidden') === 'true') return false;
            const st=getComputedStyle(el);
            if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
            const r=el.getBoundingClientRect();
            return r.width>0 && r.height>0;
          };
          const textOf=(el) => [
            el?.textContent || '',
            el?.getAttribute?.('value') || '',
            el?.getAttribute?.('aria-label') || '',
            el?.getAttribute?.('placeholder') || ''
          ].join(' ').replace(/\s+/g,' ').trim();
          const firstVisible=(selectors) => {
            for (const selector of selectors) {
              for (const el of Array.from(document.querySelectorAll(selector)).slice(0,30)) {
                if (visible(el)) return {selector,text:textOf(el)};
              }
            }
            return null;
          };
          return {
            start:firstVisible([
              '[data-selenium="checkInText"]',
              '[data-element-name*="check-in" i]',
              '[data-element-name*="checkin" i]',
              'input[name*="checkin" i]',
              'button[aria-label*="check-in" i]',
              'button[aria-label*="arrivo" i]'
            ]),
            end:firstVisible([
              '[data-selenium="checkOutText"]',
              '[data-element-name*="check-out" i]',
              '[data-element-name*="checkout" i]',
              'input[name*="checkout" i]',
              'button[aria-label*="check-out" i]',
              'button[aria-label*="partenza" i]'
            ]),
            hotel:firstVisible([
              '[data-selenium="hotel-header-name"]',
              '[data-selenium="hotel-name"]',
              'h1'
            ])
          };
        }""")
    except Exception:
        return False,""
    start=date.fromisoformat(stay["checkin"])
    end=date.fromisoformat(stay["checkout"])
    start_text=str((state.get("start") or {}).get("text") or "").lower()
    end_text=str((state.get("end") or {}).get("text") or "").lower()
    start_ok=any(value in start_text for value in _date_forms(start))
    end_ok=any(value in end_text for value in _date_forms(end))
    evidence=(
        f"start={start_text[:240] or 'n.d.'} | "
        f"end={end_text[:240] or 'n.d.'} | "
        f"hotel={str((state.get('hotel') or {}).get('text') or '')[:220] or 'n.d.'}"
    )
    return bool(start_ok and end_ok),evidence[:800]


async def agoda_actual_rate_dom_diagnostics(page) -> dict:
    """Conta prezzi EUR numerici e vere intestazioni camera (non banner/searchbox)."""
    try:
        return await page.evaluate(r"""() => {
          const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
          const visible=el=>{
            if(!el) return false;
            const s=getComputedStyle(el),r=el.getBoundingClientRect();
            return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0;
          };
          const money=/(?:€|EUR)\s*\d{1,6}(?:[.,]\d{1,2})?|\d{1,6}(?:[.,]\d{1,2})?\s*(?:€|EUR)/i;
          const priceSelectors='[data-selenium*="price" i],[data-ppapi*="price" i],[data-element-name*="price" i],[class*="price" i]';
          const roomSelectors='[data-selenium="room-name"],[data-ppapi*="room-name" i],[data-element-name*="room-name" i],h2,h3,h4';
          const allPrices=Array.from(document.querySelectorAll(priceSelectors)).filter(visible).slice(0,350);
          const numeric=allPrices.map(el=>clean(el.innerText||el.textContent).slice(0,400))
            .filter(text=>money.test(text));
          const roomTexts=Array.from(document.querySelectorAll(roomSelectors)).filter(visible)
            .map(el=>clean(el.innerText||el.textContent).slice(0,260))
            .filter(text=>text&&text.length<220&&
              /\b(camera|room|suite|matrimoniale|familiare|double|twin|king|queen|premium|deluxe|superior|tripla|quadrupla|apartment|appartamento)\b/i.test(text)&&
              !/inizia a digitare|premi invio|freccia|selezionare/i.test(text));
          return {
            totalPriceContainers:allPrices.length,
            numericEuroPrices:numeric.length,
            numericPriceSamples:Array.from(new Set(numeric)).slice(0,5),
            actualRoomNames:roomTexts.length,
            roomSamples:Array.from(new Set(roomTexts)).slice(0,5),
            bannerSamples:allPrices.map(el=>clean(el.innerText||el.textContent).slice(0,100))
              .filter(text=>text&&!money.test(text)).slice(0,4),
          };
        }""")
    except Exception as exc:
        return {"numericEuroPrices":0,"actualRoomNames":0,"error":type(exc).__name__}


def agoda_sold_out_message(body: str) -> str:
    """Solo indisponibilità esplicita, non la mancata lettura del prezzo."""
    text=re.sub(r"\s+"," ",str(body or "")).lower()
    patterns=(
        r"we.?re sold out on your dates",
        r"sold out for (?:your|these|selected) dates",
        r"no rooms available for (?:your|these|the selected) dates",
        r"no availability for (?:your|these|the selected) dates",
        r"nessuna camera disponibile per (?:le|queste) date",
        r"non ci sono camere disponibili per (?:le|queste) date",
        r"al completo (?:per|nelle) (?:le|queste) date",
        r"struttura al completo per le date",
    )
    for pattern in patterns:
        hit=re.search(pattern,text,re.I)
        if hit:
            return hit.group(0)[:180]
    return ""


async def agoda_property_rate_context(page) -> tuple[bool,str]:
    """Conferma che Agoda sia su una scheda struttura con contenuto camere/prezzi renderizzato."""
    selectors=(
        '[data-selenium="hotel-header-name"]',
        '[data-selenium="room-grid"]',
        '[data-selenium="room-name"]',
        '[data-selenium="display-price"]',
        '[data-selenium*="room-price"]',
        '[data-ppapi*="room-price" i]',
        '[data-ppapi*="price" i]',
        '[data-element-name*="room" i]',
    )
    found=[]
    for selector in selectors:
        try:
            loc=page.locator(selector).first
            if await loc.count() and await loc.is_visible(timeout=350):
                found.append(selector)
        except Exception:
            pass
    path=(urlparse(page.url).path or "").lower()
    property_path="/hotel/" in path or "/accommodation/" in path
    has_identity=any(item in found for item in (
        '[data-selenium="hotel-header-name"]',
        '[data-selenium="room-grid"]',
        '[data-selenium="room-name"]',
    ))
    has_rate_area=any(item in found for item in (
        '[data-selenium="display-price"]',
        '[data-selenium*="room-price"]',
        '[data-selenium="room-grid"]',
        '[data-selenium="room-name"]',
    ))
    return bool(property_path and has_identity and has_rate_area),", ".join(found[:8])



def _price_fields(displayed_amount: float, displayed_basis: str, stay: dict) -> dict:
    """Normalizza qualsiasi tariffa in €/notte + totale senza perdere il dato originale."""
    nights=max(1,int(stay.get("nights") or 1))
    amount=round(float(displayed_amount),2)
    if displayed_basis=="nightly":
        nightly=amount
        total=round(amount*nights,2)
        derivation=f"€{amount:.2f} mostrati a notte × {nights} notti = €{total:.2f} totale."
    elif displayed_basis=="stay-total":
        total=amount
        nightly=round(amount/nights,2)
        derivation=f"€{amount:.2f} totale mostrato ÷ {nights} notti = €{nightly:.2f}/notte."
    else:
        raise ValueError("Base prezzo non verificata")
    return {
        "total":total,
        "nightlyRate":nightly,
        "displayedAmount":amount,
        "displayedBasis":displayed_basis,
        "priceDerivation":derivation,
    }


async def agoda_visible_rate_candidates(page, stay: dict) -> list[dict]:
    """Fallback Agoda: prezzo visibile + camera nello stesso blocco; base locale o pagina univoca."""
    rows=await page.evaluate(r"""() => {
      const clean=(value) => String(value || '').replace(/\s+/g,' ').trim();
      const visible=(el) => {
        if (!el) return false;
        const st=getComputedStyle(el);
        if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
        if ((st.textDecorationLine || '').includes('line-through')) return false;
        const r=el.getBoundingClientRect();
        return r.width>0 && r.height>0;
      };
      const priceOnly=/^(?:€\s*)?\d{1,5}(?:[.,]\d{1,2})?\s*€?$/;
      const roomRx=/\b(room|camera|suite|apartment|appartamento|studio|villa|double|twin|family|king|queen|deluxe|superior|quadrupla|tripla|matrimoniale)\b/i;
      const basisRx=/\b(a notte|per notte|per night|nightly|totale soggiorno|prezzo totale|stay total|total for|per stay|media per notte|price per room per night)\b/i;
      const nodes=Array.from(document.querySelectorAll('span,strong,b,div')).filter(el => {
        if (!visible(el)) return false;
        const own=clean(el.textContent);
        return own.length<=40 && priceOnly.test(own);
      }).slice(0,300);
      const out=[]; const seen=new Set();
      for (const priceNode of nodes) {
        const price=clean(priceNode.textContent);
        let container=priceNode;
        let chosen=null;
        for (let depth=0; depth<9 && container; depth++,container=container.parentElement) {
          const text=clean(container.innerText || container.textContent);
          if (!text || text.length>6500) continue;
          const headings=Array.from(container.querySelectorAll(
            'h1,h2,h3,h4,[data-selenium="room-name"],[data-ppapi*="room-name" i],[data-element-name*="room-name" i]'
          )).map(el=>clean(el.textContent)).filter(Boolean);
          const room=headings.find(v=>roomRx.test(v)) || headings[0] || '';
          if (!room) continue;
          const basisText=basisRx.test(text) ? text : '';
          chosen={price,room:room.slice(0,240),text:text.slice(0,4200),hasLocalBasis:Boolean(basisText)};
          if (basisText) break;
        }
        if (!chosen) continue;
        const key=(chosen.room+'|'+chosen.price+'|'+chosen.text.slice(0,500)).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key); out.push(chosen);
      }
      return out.slice(0,80);
    }""")

    page_basis=""
    try:
        page_text=(await page.locator("body").inner_text(timeout=3500)).lower()
        nightly_hits=bool(re.search(
            r"\b(price per night|per night|a notte|per notte|nightly|prezzo per camera per notte|media per notte)\b",
            page_text,re.I
        ))
        total_hits=bool(re.search(
            r"\b(total price|prezzo totale|totale soggiorno|stay total|per stay|totale per il soggiorno)\b",
            page_text,re.I
        ))
        if nightly_hits and not total_hits:
            page_basis="nightly"
        elif total_hits and not nightly_hits:
            page_basis="stay-total"
    except Exception:
        page_basis=""

    out=[]
    for row in rows:
        room=str(row.get("room") or "").strip()
        text=str(row.get("text") or "").strip()
        price=_money_value(str(row.get("price") or ""))
        if not room or price is None or not text:
            continue
        low=text.lower()
        if re.search(r"\b(a notte|per notte|per night|nightly|prezzo per camera per notte|media per notte|price per room per night)\b",low,re.I):
            basis="nightly"
        elif re.search(r"\b(totale soggiorno|prezzo totale|stay total|total for|per stay|totale per il soggiorno)\b",low,re.I):
            basis="stay-total"
        else:
            basis=page_basis
        if basis not in {"nightly","stay-total"}:
            continue
        fields=_price_fields(price,basis,stay)
        board="Colazione inclusa" if any(x in low for x in ("colazione inclusa","breakfast included")) else "Trattamento da verificare"
        if any(x in low for x in ("cancellazione gratuita","free cancellation")):
            refund="Cancellazione gratuita"
        elif any(x in low for x in ("non rimborsabile","non-refundable","non refundable")):
            refund="Non rimborsabile"
        else:
            refund="Cancellazione da verificare"
        taxes=(
            "Tasse e costi indicati come inclusi"
            if any(x in low for x in ("tasse e costi inclusi","taxes and fees included","incl. taxes"))
            else "Da verificare nel dettaglio del preventivo"
        )
        out.append({
            "roomType":room,
            "ratePlan":" · ".join(x for x in (
                refund if refund!="Cancellazione da verificare" else "",
                board if board!="Trattamento da verificare" else ""
            ) if x) or "Piano tariffario da verificare",
            **fields,
            "currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
            "board":board,"refund":refund,"audience":"Pubblico senza login","taxes":taxes,
            "verified":True,
            "evidence":(fields["priceDerivation"]+" "+text)[:1200],
        })
    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item["nightlyRate"],item.get("ratePlan","").lower())
        if key in seen:
            continue
        seen.add(key); unique.append(item)
    return unique[:40]


async def agoda_geometric_rate_candidates(page, stay: dict) -> list[dict]:
    """Ultimo fallback Agoda: abbina prezzo e camera visibili per prossimità geometrica.
    È volutamente NON validato: mostra il dato reale osservato ma non alimenta il delta OTA.
    """
    payload=await page.evaluate(r"""() => {
      const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
      const visible=el=>{
        if(!el) return false;
        const st=getComputedStyle(el);
        if(st.display==='none'||st.visibility==='hidden'||Number(st.opacity||'1')===0) return false;
        if((st.textDecorationLine||'').includes('line-through')) return false;
        const r=el.getBoundingClientRect();
        return r.width>0&&r.height>0;
      };
      const priceRx=/(?:€|EUR)\s*\d{1,5}(?:[.,]\d{1,2})?|\d{1,5}(?:[.,]\d{1,2})?\s*(?:€|EUR)/i;
      const roomRx=/\b(room|camera|suite|apartment|appartamento|studio|villa|double|twin|family|king|queen|deluxe|superior|quadrupla|tripla|matrimoniale|familiare)\b/i;

      const priceSelectors=[
        '[data-selenium*="price" i]','[data-ppapi*="price" i]',
        '[data-element-name*="price" i]','[class*="price" i]'
      ];
      const roomSelectors=[
        '[data-selenium*="room-name" i]','[data-ppapi*="room-name" i]',
        '[data-ppapi*="room-title" i]','[data-element-name*="room-name" i]',
        '[data-element-name*="room-title" i]','[class*="room-name" i]',
        '[class*="room-title" i]','h2','h3','h4'
      ];

      const prices=[]; const pSeen=new Set();
      for(const sel of priceSelectors){
        for(const el of Array.from(document.querySelectorAll(sel)).slice(0,220)){
          if(!visible(el)) continue;
          const text=clean(el.innerText||el.textContent);
          const match=text.match(priceRx);
          if(!match) continue;
          const r=el.getBoundingClientRect();
          const key=match[0]+'|'+Math.round(r.top)+'|'+Math.round(r.left);
          if(pSeen.has(key)) continue; pSeen.add(key);
          prices.push({el,text:match[0],top:r.top,left:r.left,width:r.width});
        }
      }

      const rooms=[]; const rSeen=new Set();
      for(const sel of roomSelectors){
        for(const el of Array.from(document.querySelectorAll(sel)).slice(0,260)){
          if(!visible(el)) continue;
          const text=clean(el.innerText||el.textContent);
          if(!text||text.length>260||!roomRx.test(text)) continue;
          const r=el.getBoundingClientRect();
          const key=text.toLowerCase()+'|'+Math.round(r.top);
          if(rSeen.has(key)) continue; rSeen.add(key);
          rooms.push({el,text,top:r.top,bottom:r.bottom,left:r.left});
        }
      }

      const out=[];
      for(const price of prices.slice(0,80)){
        let best=null; let bestScore=1e9;
        for(const room of rooms){
          const vertical = room.bottom<=price.top+120
            ? Math.max(0,price.top-room.bottom)
            : Math.abs(room.top-price.top)+650;
          const horizontal=Math.abs(room.left-price.left)*0.15;
          const score=vertical+horizontal;
          if(score<bestScore && vertical<1700){best=room;bestScore=score;}
        }
        if(!best) continue;

        let container=price.el;
        let context='';
        for(let depth=0;depth<9&&container;depth++,container=container.parentElement){
          const t=clean(container.innerText||container.textContent);
          if(!t||t.length>9000) continue;
          if(t.toLowerCase().includes(best.text.toLowerCase()) && priceRx.test(t)){
            context=t.slice(0,6500);
            break;
          }
        }
        if(!context) context=(best.text+' '+price.text).slice(0,1200);
        const low=context.toLowerCase();
        let basis='';
        if(/(prezzo totale|totale soggiorno|stay total|total price|total for|per stay|prezzo per .* notti|price for .* nights)/i.test(low)) basis='stay-total';
        else if(/(per notte|a notte|per night|nightly|price per room per night|prezzo per camera per notte|media per notte)/i.test(low)) basis='nightly';

        out.push({
          room:best.text.slice(0,240),
          price:price.text,
          basis,
          context,
          proximity:Math.round(bestScore)
        });
      }
      return out.slice(0,80);
    }""")

    page_basis=""
    try:
        page_text=(await page.locator("body").inner_text(timeout=3500)).lower()
        nightly=bool(re.search(r"\b(per night|a notte|per notte|nightly|price per room per night|prezzo per camera per notte|media per notte)\b",page_text,re.I))
        total=bool(re.search(r"\b(total price|prezzo totale|totale soggiorno|stay total|per stay|totale per il soggiorno)\b",page_text,re.I))
        if nightly and not total:
            page_basis="nightly"
        elif total and not nightly:
            page_basis="stay-total"
    except Exception:
        pass

    out=[]
    for row in payload:
        room=str(row.get("room") or "").strip()
        price=_money_value(str(row.get("price") or ""))
        basis=str(row.get("basis") or "") or page_basis
        if not room or price is None or basis not in {"nightly","stay-total"}:
            continue
        fields=_price_fields(price,basis,stay)
        context=str(row.get("context") or "")
        low=context.lower()
        board="Colazione inclusa" if any(x in low for x in ("colazione inclusa","breakfast included")) else "Trattamento da verificare"
        if any(x in low for x in ("cancellazione gratuita","free cancellation")):
            refund="Cancellazione gratuita"
        elif any(x in low for x in ("non rimborsabile","non-refundable","non refundable")):
            refund="Non rimborsabile"
        else:
            refund="Cancellazione da verificare"
        out.append({
            "roomType":room,
            "ratePlan":"Piano tariffario da verificare",
            **fields,
            "currency":"EUR",
            "nights":stay["nights"],
            "guests":stay["adults"],
            "board":board,
            "refund":refund,
            "audience":"Pubblico senza login",
            "taxes":"Da verificare nel dettaglio del preventivo",
            "verified":False,
            "comparisonWarning":"Prezzo Agoda reale osservato e associato alla camera per prossimità frontend; da validare prima del delta.",
            "evidence":(
                f"Fallback geometrico Agoda · distanza DOM {int(row.get('proximity') or 0)} · "
                + fields["priceDerivation"]+" "+context[:700]
            )[:1200],
        })
    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item["total"])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:30]


async def agoda_quote_candidates(page, stay: dict) -> list[dict]:
    """Raccoglie prezzi Agoda associati a camera; la base può essere locale, di griglia o pagina univoca."""
    rows=await page.evaluate(r"""() => {
      const result=[]; const seen=new Set();
      const clean=(value) => String(value || '').replace(/\s+/g,' ').trim();
      const visible=(el) => {
        if (!el) return false;
        const st=getComputedStyle(el);
        if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
        if ((st.textDecorationLine || '').includes('line-through')) return false;
        const r=el.getBoundingClientRect();
        return r.width>0 && r.height>0;
      };
      const priceSelectors=[
        '[data-selenium="display-price"]',
        '[data-selenium="room-price"]',
        '[data-selenium*="current-price"]',
        '[data-ppapi*="room-price" i]',
        '[data-ppapi*="price" i]',
        '[data-element-name*="price" i]',
        '[class*="price" i]'
      ];
      const roomSelectors=[
        '[data-selenium="room-name"]',
        '[data-ppapi*="room-name" i]',
        '[data-ppapi*="room-title" i]',
        '[data-element-name*="room-name" i]',
        '[data-element-name*="room-title" i]',
        'h2','h3','h4'
      ];
      const pick=(node,selectors) => {
        for (const selector of selectors) {
          const matches=Array.from(node.querySelectorAll(selector)).filter(visible);
          if (matches.length) return matches[0];
        }
        return null;
      };
      const containers=Array.from(document.querySelectorAll(
        '[data-selenium="room-grid"], [data-selenium="room-item"], [data-ppapi*="room" i], ' +
        '[data-element-name*="room-card" i], [data-element-name*="room-grid" i], tr, [role="row"]'
      )).slice(0,220);
      for (const container of containers) {
        if (!visible(container)) continue;
        const priceNode=pick(container,priceSelectors);
        if (!priceNode) continue;
        const price=clean(priceNode.textContent).slice(0,180);
        if (!price || !/(€|EUR|\d)/i.test(price)) continue;
        let room='';
        for (const selector of roomSelectors) {
          const node=container.querySelector(selector);
          const candidate=clean(node?.textContent);
          if (!candidate) continue;
          if (selector==='h2' || selector==='h3' || selector==='h4') {
            if (!/\b(room|camera|suite|apartment|appartamento|studio|villa|double|twin|family|king|queen|deluxe|superior|quadrupla|tripla|matrimoniale)\b/i.test(candidate)) continue;
          }
          room=candidate.slice(0,240); break;
        }
        const text=clean(container.innerText || container.textContent).slice(0,4200);
        if (!text || !room) continue;
        const low=text.toLowerCase();
        let basis='';
        if (/(total price|total for|prezzo totale|totale soggiorno|stay total|per stay|price for .* nights?|prezzo per .* notti)/i.test(low)) basis='stay-total';
        else if (/(per night|\/night|a notte|per notte|nightly|price per room per night|prezzo per camera per notte|media per notte)/i.test(low)) basis='nightly';

        if (!basis) {
          const grid=container.closest(
            '[data-selenium="room-grid"], [data-element-name*="room-grid" i], [data-ppapi*="room" i], table, [role="table"]'
          );
          const headerText=clean(
            Array.from(grid?.querySelectorAll(
              'th,[role="columnheader"],[data-selenium*="price"],[data-ppapi*="price"],[data-element-name*="price"]'
            ) || []).slice(0,60).map(el=>el.textContent || '').join(' ')
          ).toLowerCase();
          if (/(total price|prezzo totale|totale soggiorno|stay total|per stay)/i.test(headerText)) basis='stay-total';
          else if (/(per night|a notte|per notte|nightly|price per room per night|prezzo per camera per notte|media per notte)/i.test(headerText)) basis='nightly';
        }
        const key=(room+'|'+price+'|'+basis+'|'+text.slice(0,700)).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        result.push({room,price,text,basis,isolated:true});
      }
      return result.slice(0,160);
    }""")

    page_basis=""
    try:
        page_text=(await page.locator("body").inner_text(timeout=3500)).lower()
        nightly_hits=bool(re.search(
            r"\b(price per night|per night|a notte|per notte|nightly|prezzo per camera per notte|media per notte)\b",
            page_text,re.I
        ))
        total_hits=bool(re.search(
            r"\b(total price|prezzo totale|totale soggiorno|stay total|per stay|totale per il soggiorno)\b",
            page_text,re.I
        ))
        if nightly_hits and not total_hits:
            page_basis="nightly"
        elif total_hits and not nightly_hits:
            page_basis="stay-total"
    except Exception:
        page_basis=""

    out=[]
    for row in rows:
        room=str(row.get("room") or "").strip()
        price=_money_value(str(row.get("price") or ""))
        if not room or price is None:
            continue
        basis=str(row.get("basis") or "") or page_basis
        text=str(row.get("text") or "")
        low=text.lower()
        if basis not in {"nightly","stay-total"}:
            continue
        fields=_price_fields(price,basis,stay)
        total=fields["total"]

        if any(token in low for token in ("breakfast included","colazione inclusa","colazione compresa")):
            board="Colazione inclusa"
        elif any(token in low for token in ("room only","solo pernottamento","senza colazione")):
            board="Solo pernottamento"
        else:
            board="Trattamento da verificare"

        if any(token in low for token in ("free cancellation","cancellazione gratuita")):
            refund="Cancellazione gratuita"
        elif any(token in low for token in ("non-refundable","non refundable","non rimborsabile")):
            refund="Non rimborsabile"
        else:
            refund="Cancellazione da verificare"

        if any(token in low for token in ("taxes and fees included","incl. taxes","tasse incluse","imposte incluse")):
            taxes="Tasse e commissioni indicate come incluse"
        elif any(token in low for token in ("excluding taxes","taxes excluded","tasse escluse","imposte escluse")):
            taxes="Tasse indicate come escluse"
        else:
            taxes="Da verificare nel dettaglio del preventivo"

        plan_parts=[]
        if refund!="Cancellazione da verificare":
            plan_parts.append(refund)
        if board!="Trattamento da verificare":
            plan_parts.append(board)
        if any(token in low for token in ("pay at the property","paga in struttura","pay at property")):
            plan_parts.append("Pagamento in struttura")
        if any(token in low for token in ("pay now","prepay","prepayment","pagamento anticipato")):
            plan_parts.append("Pagamento anticipato")
        rate_plan=" · ".join(dict.fromkeys(plan_parts)) or "Piano tariffario da verificare"

        verified=bool(row.get("isolated") and room and basis in {"stay-total","nightly"})
        basis_note=(
            f"Prezzo per notte visibile (€{price:.2f}) × {stay['nights']} notti = €{total:.2f}."
            if basis=="nightly"
            else "Totale soggiorno indicato nel blocco tariffario."
        )
        out.append({
            "roomType":room,
            "ratePlan":rate_plan,
            **fields,
            "currency":"EUR",
            "nights":stay["nights"],
            "guests":stay["adults"],
            "board":board,
            "refund":refund,
            "audience":"Pubblico senza login",
            "taxes":taxes,
            "verified":verified,
            "evidence":(basis_note+" "+text)[:1100],
        })

    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item.get("ratePlan","").lower(),item["total"])
        if key in seen:
            continue
        seen.add(key); unique.append(item)
    return unique[:40]


def airbnb_url_dates_confirmed(url: str, stay: dict) -> bool:
    try:
        query={str(key).lower():str(value) for key,value in parse_qsl(urlparse(url).query,keep_blank_values=True)}
    except Exception:
        return False
    return (
        (query.get("check_in") or query.get("checkin") or "") == stay["checkin"]
        and (query.get("check_out") or query.get("checkout") or "") == stay["checkout"]
    )


def vrbo_url_dates_confirmed(url: str, stay: dict) -> bool:
    try:
        query={str(key).lower():str(value) for key,value in parse_qsl(urlparse(url).query,keep_blank_values=True)}
    except Exception:
        return False
    start=(query.get("chkin") or query.get("checkin") or query.get("check_in") or query.get("d1") or query.get("startdate") or "")
    end=(query.get("chkout") or query.get("checkout") or query.get("check_out") or query.get("d2") or query.get("enddate") or "")
    return start == stay["checkin"] and end == stay["checkout"]

async def listing_property_rate_context(page, channel: str) -> tuple[bool,str]:
    selector_map={
        "airbnb":(
            '[data-testid="book-it-default"]',
            '[data-section-id="BOOK_IT_SIDEBAR"]',
            '[data-plugin-in-point-id="BOOK_IT_SIDEBAR"]',
            '[data-testid*="price"]',
            'h1',
        ),
        "vrbo":(
            '[data-stid="price-lockup-text"]',
            '[data-stid*="price"]',
            '[data-stid*="book"]',
            '[data-testid*="price"]',
            'h1',
        ),
    }
    found=[]
    for selector in selector_map.get(channel,()):
        try:
            loc=page.locator(selector).first
            if await loc.count() and await loc.is_visible(timeout=350):
                found.append(selector)
        except Exception:
            pass
    path=(urlparse(page.url).path or "").lower()
    if channel=="airbnb":
        property_path="/rooms/" in path
        has_rate=any(item in found for item in (
            '[data-testid="book-it-default"]',
            '[data-section-id="BOOK_IT_SIDEBAR"]',
            '[data-plugin-in-point-id="BOOK_IT_SIDEBAR"]',
            '[data-testid*="price"]',
        ))
    else:
        property_path=bool(
            re.search(r'/(?:p|property)/?\d+',path)
            or "/pdp/" in path
            or re.search(r'/\d+(?:ha|vb|vr)?/?$',path)
            or "/vacation-rental/" in path
            or "/holiday-rental/" in path
            or "/affitto-vacanze/" in path
        )
        has_rate=any(item in found for item in (
            '[data-stid="price-lockup-text"]',
            '[data-stid*="price"]',
            '[data-stid*="book"]',
            '[data-testid*="price"]',
        ))
    return bool(property_path and "h1" in found and has_rate),", ".join(found[:8])


async def listing_sidebar_quote_candidates(page, stay: dict, channel: str) -> list[dict]:
    """Parser conservativo per schede singole Airbnb/Vrbo con riepilogo prezzo visibile."""
    containers={
        "airbnb":[
            '[data-testid="book-it-default"]',
            '[data-section-id="BOOK_IT_SIDEBAR"]',
            '[data-plugin-in-point-id="BOOK_IT_SIDEBAR"]',
        ],
        "vrbo":[
            '[data-stid*="price"]',
            '[data-stid*="book"]',
            '[data-testid*="price"]',
            'aside',
        ],
    }.get(channel,[])
    rows=await page.evaluate(r"""(selectors) => {
      const clean=(value) => String(value || '').replace(/\s+/g,' ').trim();
      const visible=(el) => {
        if (!el) return false;
        const st=getComputedStyle(el);
        if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
        if ((st.textDecorationLine || '').includes('line-through')) return false;
        const r=el.getBoundingClientRect();
        return r.width>0 && r.height>0;
      };
      const title=clean(document.querySelector('h1')?.textContent).slice(0,260);
      const out=[]; const seen=new Set();
      for (const selector of selectors) {
        for (const root of Array.from(document.querySelectorAll(selector)).slice(0,30)) {
          if (!visible(root)) continue;
          const candidates=[root,...Array.from(root.querySelectorAll('div,span,p,li')).slice(0,240)];
          for (const node of candidates) {
            if (!visible(node)) continue;
            const own=clean(node.textContent);
            if (!/(€|eur)\s*[0-9]|[0-9]\s*(€|eur)/i.test(own)) continue;
            const box=node.closest('li,[data-testid*="price"],[data-stid*="price"],div') || node;
            const text=clean(box.innerText || box.textContent);
            if (!text || text.length<4 || text.length>1300) continue;
            const low=text.toLowerCase();
            const hasBasis=/(total|totale|per stay|soggiorno|per night|\/night|a notte|per notte|nightly|x\s*\d+\s*nights?|x\s*\d+\s*notti?)/i.test(low);
            if (!hasBasis) continue;
            const key=(title+'|'+text).toLowerCase();
            if (seen.has(key)) continue;
            seen.add(key);
            out.push({title,text});
          }
        }
      }
      return out.slice(0,80);
    }""",containers)

    out=[]
    for row in rows:
        title=str(row.get("title") or "").strip()
        text=str(row.get("text") or "").strip()
        if not title or not text:
            continue
        low=text.lower()
        values=[_money_value(match.group(0)) for match in PRICE_RE.finditer(text)]
        values=[value for value in values if value is not None]
        if not values:
            continue

        basis=""
        total=None
        # Nei riepiloghi laterali il totale compare spesso dopo le singole voci;
        # quando è esplicito preferiamo l'ultimo importo visibile del blocco.
        if re.search(r'\b(total|totale|stay total|per stay|soggiorno)\b',low):
            total=values[-1]
            basis="stay-total"
        elif re.search(r'(per night|/night|a notte|per notte|nightly)',low):
            total=values[0]*int(stay["nights"])
            basis="nightly"
        else:
            nights_match=re.search(r'(?:x|×)\s*'+re.escape(str(stay["nights"]))+r'\s*(?:nights?|notti?)',low)
            if nights_match:
                total=values[0]*int(stay["nights"])
                basis="nightly"
        if total is None:
            continue

        if any(token in low for token in ("breakfast included","colazione inclusa","colazione compresa")):
            board="Colazione inclusa"
        elif any(token in low for token in ("room only","solo pernottamento","senza colazione")):
            board="Solo pernottamento"
        else:
            board="Trattamento da verificare"

        if any(token in low for token in ("free cancellation","cancellazione gratuita","fully refundable")):
            refund="Cancellazione gratuita"
        elif any(token in low for token in ("non-refundable","non refundable","non rimborsabile")):
            refund="Non rimborsabile"
        else:
            refund="Cancellazione da verificare"

        if any(token in low for token in ("taxes included","incl. taxes","tasse incluse","imposte incluse")):
            taxes="Tasse indicate come incluse"
        elif any(token in low for token in ("before taxes","excluding taxes","taxes excluded","tasse escluse","imposte escluse")):
            taxes="Tasse indicate come escluse"
        else:
            taxes="Da verificare nel dettaglio del preventivo"

        rate_plan=" · ".join(part for part in (refund if refund!="Cancellazione da verificare" else "",board if board!="Trattamento da verificare" else "") if part) or "Piano tariffario da verificare"
        evidence_prefix=(
            f"Prezzo per notte visibile (€{values[0]:.2f}) × {stay['nights']} notti = €{total:.2f}. "
            if basis=="nightly"
            else "Totale soggiorno esplicito nel riepilogo prezzo. "
        )
        out.append({
            "roomType":title[:240],
            "ratePlan":rate_plan,
            "total":round(float(total),2),
            "currency":"EUR",
            "nights":stay["nights"],
            "guests":stay["adults"],
            "board":board,
            "refund":refund,
            "audience":"Pubblico senza login",
            "taxes":taxes,
            "verified":True,
            "evidence":(evidence_prefix+text)[:1100],
        })

    # Se esiste un totale soggiorno esplicito, evita di conservare anche la stessa tariffa
    # derivata dal prezzo notte del medesimo riepilogo.
    stay_totals=[item for item in out if item["evidence"].startswith("Totale soggiorno")]
    source=stay_totals or out
    unique=[]; seen=set()
    for item in source:
        key=(item["roomType"].lower(),item.get("ratePlan","").lower(),item["total"])
        if key in seen:
            continue
        seen.add(key); unique.append(item)
    return unique[:12]



async def airbnb_prepare_frontend(page, stay: dict) -> tuple[bool,str]:
    """Replica il flusso utente Airbnb: date -> 2 adulti -> chiusura popup -> box tariffe."""
    evidence=[]
    checkin=stay["checkin"]
    checkout=stay["checkout"]
    adults=int(stay.get("adults") or 2)

    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(250)
    except Exception:
        pass

    async def visible_body() -> str:
        try:
            return re.sub(r"\s+"," ",(await page.locator("body").inner_text(timeout=6000)) or "")[:22000]
        except Exception:
            return ""

    async def sidebar_ready() -> tuple[bool,str]:
        try:
            state=await page.evaluate(r"""({adults}) => {
              const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
              const visible=el=>{
                if(!el) return false;
                const st=getComputedStyle(el);
                if(st.display==='none'||st.visibility==='hidden'||Number(st.opacity||'1')===0) return false;
                const r=el.getBoundingClientRect();
                return r.width>0&&r.height>0;
              };
              const buttons=Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
              const reserve=buttons.find(el=>/^(prenota|reserve|book)$/i.test(clean(el.innerText||el.textContent)))
                || buttons.find(el=>/(prenota|reserve|book)/i.test(clean(el.innerText||el.textContent)));
              let root=reserve?.closest('[data-testid="book-it-default"],[data-section-id="BOOK_IT_SIDEBAR"],aside,section') || null;
              if(!root && reserve){
                let n=reserve.parentElement;
                while(n && n!==document.body){
                  const t=clean(n.innerText||n.textContent);
                  if(t.length>30 && t.length<3500 && /(€|eur)/i.test(t)){root=n;break}
                  n=n.parentElement;
                }
              }
              if(!root){
                root=Array.from(document.querySelectorAll('[data-testid="book-it-default"],[data-section-id="BOOK_IT_SIDEBAR"],aside'))
                  .find(el=>visible(el) && /(€|eur|aggiungi le date|add dates)/i.test(clean(el.innerText||el.textContent))) || null;
              }
              const text=clean(root?.innerText||root?.textContent);
              const hasPrice=/(€|eur)\s*[0-9]|[0-9][0-9.,\s]*\s*(€|eur)/i.test(text);
              const hasBook=/(prenota|reserve|book)/i.test(text);
              const hasGuests=new RegExp(String(adults)+'\\s*(ospiti|guests?)','i').test(text);
              return {ok:!!root && hasPrice && hasBook, text:text.slice(0,1800), hasGuests};
            }""",{"adults":adults})
            return bool(state.get("ok")),str(state.get("text") or "")
        except Exception:
            return False,""

    ready,ready_text=await sidebar_ready()
    if ready and airbnb_url_dates_confirmed(page.url,stay):
        evidence.append("box Airbnb già popolato · URL con identiche date Booking")
        return True,"; ".join(evidence)+" | "+ready_text[:500]

    try:
        body=(await visible_body()).lower()
        needs_dates=any(token in body for token in (
            "aggiungi le date per conoscere i prezzi","aggiungi una data",
            "add dates for prices","add dates","add a date"
        ))
        if needs_dates:
            trigger,_=await _first_visible_locator(page,(
                'button:has-text("Aggiungi una data")',
                'button:has-text("Add a date")',
                'button:has-text("CHECK-IN")',
                'button:has-text("Check-in")',
                '[data-testid*="change-dates"]',
                '[data-testid*="check-in"]',
            ))
            if trigger is not None:
                try:
                    await trigger.scroll_into_view_if_needed(timeout=1200)
                except Exception:
                    pass
                await trigger.click(timeout=2200)
                await page.wait_for_timeout(700)

                async def click_day(iso_date: str) -> bool:
                    target=date.fromisoformat(iso_date)
                    labels=[
                        iso_date,
                        f"{target.day}/{target.month}/{target.year}",
                        f"{target.day} {MONTH_NAMES[target.month][1]} {target.year}",
                    ]
                    for selector in (
                        f'[data-testid*="{iso_date}"]',
                        f'[data-date="{iso_date}"]',
                        f'button[aria-label*="{iso_date}"]',
                    ):
                        try:
                            loc=page.locator(selector).first
                            if await loc.count() and await loc.is_visible(timeout=300):
                                await loc.click(timeout=1800)
                                return True
                        except Exception:
                            pass
                    try:
                        state=await page.evaluate(r"""(labels) => {
                          const clean=v=>String(v||'').replace(/\s+/g,' ').trim().toLowerCase();
                          const visible=el=>{
                            if(!el) return false;
                            const st=getComputedStyle(el);
                            if(st.display==='none'||st.visibility==='hidden') return false;
                            const r=el.getBoundingClientRect(); return r.width>0&&r.height>0;
                          };
                          document.querySelectorAll('[data-velora-airbnb-day]').forEach(el=>el.removeAttribute('data-velora-airbnb-day'));
                          const nodes=Array.from(document.querySelectorAll('button,[role="button"],[data-testid*="calendar"]')).filter(visible);
                          for(const el of nodes){
                            const hay=clean((el.getAttribute('aria-label')||'')+' '+(el.textContent||''));
                            if(labels.some(v=>hay.includes(clean(v)))){
                              el.setAttribute('data-velora-airbnb-day','1'); return true;
                            }
                          }
                          return false;
                        }""",labels)
                        if state:
                            loc=page.locator('[data-velora-airbnb-day="1"]').first
                            await loc.click(timeout=1800)
                            return True
                    except Exception:
                        pass
                    return False

                start_ok=await click_day(checkin)
                await page.wait_for_timeout(350)
                end_ok=await click_day(checkout)
                await page.wait_for_timeout(900)
                evidence.append(f"date picker Airbnb: check-in={'ok' if start_ok else 'no'} check-out={'ok' if end_ok else 'no'}")
    except Exception as exc:
        evidence.append(f"date picker Airbnb: {type(exc).__name__}")

    try:
        guest_trigger,_=await _first_visible_locator(page,(
            'button:has-text("ospite")',
            'button:has-text("ospiti")',
            'button:has-text("guest")',
            'button:has-text("guests")',
            '[data-testid*="guest"]',
        ))
        if guest_trigger is not None:
            try:
                await guest_trigger.scroll_into_view_if_needed(timeout=1000)
            except Exception:
                pass
            await guest_trigger.click(timeout=1800)
            await page.wait_for_timeout(450)

            guest_state=await page.evaluate(r"""(targetAdults) => {
              const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
              const visible=el=>{
                if(!el) return false;
                const st=getComputedStyle(el);
                if(st.display==='none'||st.visibility==='hidden') return false;
                const r=el.getBoundingClientRect(); return r.width>0&&r.height>0;
              };
              document.querySelectorAll('[data-velora-adult-minus],[data-velora-adult-plus]').forEach(el=>{
                el.removeAttribute('data-velora-adult-minus'); el.removeAttribute('data-velora-adult-plus');
              });
              const labels=Array.from(document.querySelectorAll('div,span,p')).filter(el=>visible(el) && /^(adulti|adults)$/i.test(clean(el.textContent)));
              for(const label of labels){
                let row=label;
                for(let i=0;i<5 && row;i++,row=row.parentElement){
                  const buttons=Array.from(row.querySelectorAll('button')).filter(visible);
                  const nums=Array.from(row.querySelectorAll('span,div')).map(el=>clean(el.textContent)).filter(v=>/^\d+$/.test(v));
                  const current=nums.length ? Number(nums[nums.length-1]) : NaN;
                  if(buttons.length>=2 && Number.isFinite(current)){
                    buttons[0].setAttribute('data-velora-adult-minus','1');
                    buttons[buttons.length-1].setAttribute('data-velora-adult-plus','1');
                    return {current,target:targetAdults};
                  }
                }
              }
              return null;
            }""",adults)

            if guest_state and Number.isFinite(Number(guest_state.get("current"))):
                current=int(guest_state["current"])
                while current<adults:
                    await page.locator('[data-velora-adult-plus="1"]').click(timeout=1200)
                    current+=1
                    await page.wait_for_timeout(180)
                while current>adults:
                    await page.locator('[data-velora-adult-minus="1"]').click(timeout=1200)
                    current-=1
                    await page.wait_for_timeout(180)
                evidence.append(f"ospiti Airbnb: {adults} adulti")
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(450)
            except Exception:
                pass
    except Exception as exc:
        evidence.append(f"ospiti Airbnb: {type(exc).__name__}")

    try:
        reserve,_=await _first_visible_locator(page,(
            'button:has-text("Prenota")',
            'button:has-text("Reserve")',
            'button:has-text("Book")',
            '[data-testid="book-it-default"] button',
        ))
        if reserve is not None:
            await reserve.scroll_into_view_if_needed(timeout=1200)
        await page.wait_for_timeout(1000)
    except Exception:
        pass

    ready,ready_text=await sidebar_ready()
    evidence.append("box tariffario Airbnb " + ("pronto" if ready else "non ancora riconosciuto"))
    return ready,("; ".join(evidence)+" | "+ready_text[:700])[:1100]


async def airbnb_quote_candidates(page, stay: dict) -> list[dict]:
    """Legge il box Airbnb come lo vede l'utente: TARIFFE + totale per ciascun piano."""
    payload=await page.evaluate(r"""() => {
      const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
      const visible=el=>{
        if(!el) return false;
        const st=getComputedStyle(el);
        if(st.display==='none'||st.visibility==='hidden'||Number(st.opacity||'1')===0) return false;
        const r=el.getBoundingClientRect(); return r.width>0&&r.height>0;
      };
      const title=clean(document.querySelector('h1')?.textContent).slice(0,260);
      const buttons=Array.from(document.querySelectorAll('button,[role="button"]')).filter(visible);
      const reserve=buttons.find(el=>/^(prenota|reserve|book)$/i.test(clean(el.innerText||el.textContent)))
        || buttons.find(el=>/(prenota|reserve|book)/i.test(clean(el.innerText||el.textContent)));
      let root=reserve?.closest('[data-testid="book-it-default"],[data-section-id="BOOK_IT_SIDEBAR"],aside,section') || null;
      if(!root && reserve){
        let n=reserve.parentElement;
        while(n&&n!==document.body){
          const t=clean(n.innerText||n.textContent);
          if(t.length>40&&t.length<4200&&/(€|eur)/i.test(t)){root=n;break}
          n=n.parentElement;
        }
      }
      if(!root){
        root=Array.from(document.querySelectorAll('[data-testid="book-it-default"],[data-section-id="BOOK_IT_SIDEBAR"],aside'))
          .find(el=>visible(el)&&/(€|eur)/i.test(clean(el.innerText||el.textContent))) || null;
      }
      if(!root) return {title,rootText:'',plans:[]};

      const rootText=clean(root.innerText||root.textContent).slice(0,4200);
      const nodes=Array.from(root.querySelectorAll('div,li,label,[role="radio"],button')).filter(visible);
      const plans=[]; const seen=new Set();
      for(const node of nodes){
        const text=clean(node.innerText||node.textContent);
        if(!text||text.length<8||text.length>900) continue;
        if(!/(€|eur)\s*[0-9]|[0-9][0-9.,\s]*\s*(€|eur)/i.test(text)) continue;
        if(!/(rimborsabile|non rimborsabile|refundable|non-refundable|non refundable)/i.test(text)) continue;
        if(!/(totale|total)/i.test(text)) continue;
        const key=text.toLowerCase();
        if(seen.has(key)) continue;
        seen.add(key); plans.push(text);
      }
      return {title,rootText,plans:plans.slice(0,12)};
    }""")

    title=str(payload.get("title") or "").strip() or "Alloggio Airbnb"
    root_text=str(payload.get("rootText") or "")
    plan_rows=[str(item or "") for item in (payload.get("plans") or []) if str(item or "").strip()]
    rows=plan_rows[:] if plan_rows else ([root_text] if root_text else [])

    out=[]
    for text in rows:
        low=text.lower()
        values=[_money_value(match.group(0)) for match in PRICE_RE.finditer(text)]
        values=[value for value in values if value is not None]
        if not values or not re.search(r'\b(totale|total)\b',low):
            continue
        total=values[-1]

        if "non rimborsabile" in low or "non-refundable" in low or "non refundable" in low:
            refund="Non rimborsabile"
        elif "rimborsabile" in low or "refundable" in low:
            refund="Rimborsabile"
        else:
            refund="Cancellazione da verificare"

        board="Colazione inclusa" if ("colazione" in low or "breakfast" in low) else "Trattamento da verificare"
        fields=_price_fields(total,"stay-total",stay)
        out.append({
            "roomType":title[:240],
            "ratePlan":refund,
            **fields,
            "currency":"EUR",
            "nights":stay["nights"],
            "guests":stay["adults"],
            "board":board,
            "refund":refund,
            "audience":"Pubblico senza login",
            "taxes":"Da verificare nel dettaglio del preventivo",
            "verified":True,
            "evidence":(
                f"Airbnb frontend: date {stay['checkin']}→{stay['checkout']}, {stay['adults']} adulti; "
                f"piano «{refund}» con totale esplicito €{total:.2f}. Contesto: {text[:700]}"
            )[:1100],
        })

    unique=[]; seen=set()
    for item in out:
        key=(item.get("ratePlan","").lower(),item["total"])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:8]



OTA_FRONTEND_SEARCH_HOME={
    "airbnb":"https://www.airbnb.it/",
    "expedia":"https://www.expedia.it/",
    "hotels":"https://it.hotels.com/",
    "travelocity":"https://www.travelocity.com/",
    "vrbo":"https://www.vrbo.com/",
    "holidu":"https://www.holidu.it/",
    "agoda":"https://www.agoda.com/it-it/",
    "trip":"https://it.trip.com/",
    "priceline":"https://www.priceline.com/",
}


async def frontend_discover_ota_source(
    context, channel: str, data: dict, stay: dict, robots: dict,
    assist_callback=None, ghost: bool = False,
) -> dict:
    """Trova una scheda direttamente nel portale, senza dipendere dalla discovery esterna."""
    home=OTA_FRONTEND_SEARCH_HOME.get(channel,"")
    label=OTA_META.get(channel,{}).get("label",channel)
    if channel=="airbnb":
        # Airbnb per hotel/complessi: ricerca per singole /rooms/ nei risultati Google.
        # La sola ricerca "destinazione" interna trova città, non nomi di hotel.
        indexed=await discover_airbnb_property_listings(context,data,robots)
        if indexed.get("status")=="found":
            return indexed
        print(
            f"airbnb frontend discovery: indice pubblico non conclusivo · "
            f"{str(indexed.get('evidence') or '')[:380]} · provo anche home Airbnb",
            flush=True,
        )
    if not home:
        return {"status":"unsupported","url":"","evidence":f"{label}: ricerca frontend interna non configurata."}

    permission=await asyncio.to_thread(allowed_by_robots,home,robots)
    if permission is False:
        return {"status":"robots_denied","url":"","evidence":f"{label}: robots.txt nega la ricerca frontend automatica."}

    name=str(data.get("name") or "").strip()
    city=str(data.get("city") or "").strip()
    address=str(data.get("address") or "").strip()
    variants=_property_name_query_variants(name)
    distinctive=(variants[0] if variants else name).strip()
    queries=[]
    for variant in variants[:3]:
        if variant and city:
            queries.append(f"{variant} {city}")
        if variant:
            queries.append(variant)
    # Solo come ultimo fallback usa la località da sola: non deve prevalere sul brand.
    if city:
        queries.append(city)
    queries=list(dict.fromkeys(q for q in queries if q))[:7]
    if not queries:
        return {"status":"not_found","url":"","evidence":f"{label}: nome/località non disponibili per la ricerca interna."}

    page=await context.new_page()
    try:
        response=await page.goto(home,wait_until="domcontentloaded",timeout=22000)
        await dismiss_cookie(page)
        await page.wait_for_timeout(900)
        if response and response.status>=500:
            return {"status":"http_error","url":"","evidence":f"{label}: homepage HTTP {response.status}."}

        async def find_candidate() -> dict | None:
            try:
                current_title=(await page.title())[:260]
                body=(await page.locator("body").inner_text(timeout=5500))[:18000]
            except Exception:
                current_title=""; body=""
            if _plausible_ota_listing_url(channel,page.url):
                strict=_strict_ota_identity_match(name,city,address,current_title,body[:6000],page.url)
                if strict.get("ok"):
                    return {
                        "status":"found","url":normalize_ota_listing_url(channel,page.url),
                        "title":current_title,"score":strict.get("score",1.0),"identityVerified":True,
                        "evidence":f"{label}: scheda raggiunta dalla ricerca interna; {strict.get('evidence','identità verificata')}.",
                        "discoveryMode":"OTA frontend internal search + strict identity lock",
                    }
            try:
                links=await page.evaluate(r"""() => Array.from(document.querySelectorAll('a[href]')).slice(0,1200).map(a=>{
                  const box=a.closest('article,li,[data-stid],[data-testid],section,div') || a.parentElement;
                  return {
                    href:a.href || '',
                    text:String(a.innerText||a.textContent||a.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim().slice(0,320),
                    context:String(box?.innerText||'').replace(/\s+/g,' ').trim().slice(0,1500)
                  };
                })""")
            except Exception:
                links=[]
            ranked=[]
            seen=set()
            for item in links:
                target=str(item.get("href") or "")
                if not target or target in seen:
                    continue
                seen.add(target)
                if _classify_ota_url(target)!=channel or not _plausible_ota_listing_url(channel,target):
                    continue
                score,_,_,_,reasons=_identity_match_score(
                    name,city,address,str(item.get("text") or ""),str(item.get("context") or ""),target
                )
                ranked.append((score,target,str(item.get("text") or ""),reasons))
            ranked.sort(key=lambda row:row[0],reverse=True)
            for score,target,title,reasons in ranked[:4]:
                if score<0.38:
                    continue
                try:
                    verification=await verify_ota_candidate_page(
                        context,channel,target,name,city,address,robots
                    )
                except Exception:
                    verification={}
                if verification.get("ok"):
                    return {
                        "status":"found",
                        "url":verification.get("url") or normalize_ota_listing_url(channel,target),
                        "title":verification.get("title") or title[:240],
                        "score":verification.get("score",score),
                        "identityVerified":True,
                        "evidence":(
                            f"{label}: risultato interno verificato sulla scheda reale; "
                            f"{verification.get('evidence','identità verificata')}."
                        )[:900],
                        "discoveryMode":"OTA frontend results + strict page verification",
                    }
            return None

        opener_selectors=(
            'button:has-text("Dove vuoi andare")','button:has-text("Where to")',
            'button:has-text("Destinazione")','button:has-text("Destination")',
            '[data-stid*="destination"]','[data-testid*="destination"]',
            '[data-element-name*="search-box"]',
        )
        input_selectors=(
            'input[placeholder*="dove" i]','input[placeholder*="where" i]',
            'input[placeholder*="destin" i]','input[placeholder*="localit" i]',
            'input[placeholder*="location" i]','input[placeholder*="cerca" i]',
            'input[placeholder*="search" i]','input[aria-label*="dove" i]',
            'input[aria-label*="where" i]','input[aria-label*="destin" i]',
            '[data-stid*="destination"] input','[data-testid*="destination"] input',
            'input[name*="destination" i]','input[name*="query" i]','input[type="search"]',
        )
        action_selectors=(
            'button:has-text("Cerca")','button:has-text("Search")',
            'button:has-text("Trova")','button:has-text("Find")',
            '[data-testid*="search"]','[data-stid*="search"]',
        )

        for query in queries:
            existing=await find_candidate()
            if existing:
                return existing

            opener,_=await _first_visible_locator(page,opener_selectors)
            if opener is not None:
                try:
                    await opener.click(timeout=1800)
                    await page.wait_for_timeout(300)
                except Exception:
                    pass

            field,_=await _first_visible_locator(page,input_selectors)
            if field is None:
                continue
            try:
                await field.click(timeout=1200)
                await field.fill(query,timeout=1800)
                await page.wait_for_timeout(900)
            except Exception:
                continue

            option=None
            best_score=-1.0
            try:
                options=page.locator(
                    '[role="option"], [data-stid*="destination-result"], [data-testid*="suggest"], '
                    '[data-testid*="option"], li'
                )
                count=min(await options.count(),40)
                for idx in range(count):
                    candidate=options.nth(idx)
                    try:
                        if not await candidate.is_visible(timeout=160):
                            continue
                        text_value=re.sub(r"\s+"," ",(await candidate.inner_text(timeout=350)) or "").strip()
                    except Exception:
                        continue
                    if not text_value or len(text_value)>500:
                        continue
                    score=max(_name_similarity(distinctive,text_value),_name_similarity(name,text_value))
                    if city and _norm_name(city) in _norm_name(text_value):
                        score=min(1.0,score+0.08)
                    if score>best_score:
                        best_score=score
                        option=candidate
            except Exception:
                option=None

            if option is not None and best_score>=0.25:
                try:
                    await option.click(timeout=1800)
                    await page.wait_for_timeout(700)
                except Exception:
                    option=None
            if option is None:
                try:
                    await field.press("Enter")
                    await page.wait_for_timeout(700)
                except Exception:
                    pass

            action,_=await _first_visible_locator(page,action_selectors)
            if action is not None:
                try:
                    await action.click(timeout=2200)
                except Exception:
                    pass
            try:
                await page.wait_for_load_state("domcontentloaded",timeout=7000)
            except Exception:
                pass
            await page.wait_for_timeout(1300)

            candidate=await find_candidate()
            if candidate:
                return candidate

        if callable(assist_callback):
            action=await _human_assist(
                page,assist_callback,{
                    "type":"source_selection",
                    "otaId":channel,
                    "label":label,
                    "reason":"La ricerca automatica non ha individuato una scheda verificabile.",
                    "instructions":(
                        f"Nel Chrome aperto cerca «{name}» a «{city}» su {label} e apri la scheda ESATTA della struttura. "
                        "Se compare un consenso/cookie o una verifica del portale, completala manualmente. "
                        "Non è necessario effettuare login. Quando sei sulla scheda corretta torna su Velora e premi «Ho completato · riprendi»."
                    ),
                    "propertyName":name,
                    "city":city,
                    "stay":stay,
                },ghost,
            )
            if action in {"continue","done"}:
                identity=await _current_page_identity(page,channel,data)
                if identity.get("ok"):
                    if ghost:
                        await _set_interaction_window(page,False)
                    return {
                        "status":"found","url":identity.get("url") or page.url,
                        "title":identity.get("title") or "",
                        "score":identity.get("score",1.0),
                        "identityVerified":True,
                        "evidence":f"{label}: scheda selezionata manualmente e poi verificata da Velora; {identity.get('evidence','')}.",
                        "discoveryMode":"human-assisted source selection + strict identity lock",
                    }
                if ghost:
                    await _set_interaction_window(page,False)
                return {
                    "status":"not_found","url":"","identityVerified":False,
                    "evidence":(
                        f"{label}: intervento manuale concluso, ma la pagina aperta non supera il controllo identità "
                        f"nome + località/indirizzo. {identity.get('evidence','')}"
                    )[:900],
                    "discoveryMode":"human-assisted source selection rejected by identity lock",
                }
            if ghost:
                await _set_interaction_window(page,False)

        return {
            "status":"not_found","url":"","identityVerified":False,
            "evidence":f"{label}: ricerca interna eseguita con nome distintivo/località, ma nessuna scheda attribuibile è emersa.",
            "discoveryMode":"OTA frontend internal search exhausted",
        }
    except Exception as exc:
        return {
            "status":"error","url":"","identityVerified":False,
            "evidence":f"{label}: ricerca interna non completata ({type(exc).__name__}: {str(exc)[:180]}).",
        }
    finally:
        try:
            await page.close()
        except Exception:
            pass


def frontend_entry_url(channel: str, source: str, stay: dict) -> str | None:
    """Pricing pubblico: usa il frontend reale, senza deep-link artificiali."""
    clean=normalize_ota_listing_url(channel,source)
    if channel=="airbnb":
        # Annuncio singolo Airbnb: usa la scheda verificata, con le date Booking
        # e gli adulti già richiesti nel frontend pubblico. Il parser verifica
        # le date effettivamente applicate prima di accettare prezzi.
        return dated_url("airbnb",clean,stay)
    if channel=="agoda":
        # Agoda viene interrogata come farebbe un utente: homepage -> ricerca struttura
        # -> date/ospiti -> Cerca -> card struttura -> pagina camere/tariffe.
        return "https://www.agoda.com/it-it/"
    if channel in PUBLIC_FRONTEND_PRICING_CHANNELS:
        return clean
    return dated_url(channel,clean,stay)


def _agoda_search_term(property_name: str, source: str) -> str:
    """Riduce il nome alla parte distintiva usata nella ricerca Agoda."""
    raw=str(property_name or "").strip()
    if not raw:
        slug=(urlparse(source).path or "").split("/hotel/")[0].strip("/").split("/")[-1]
        raw=re.sub(r"^\d+[-_ ]*","",slug.replace("-"," ").replace("_"," "))
    tokens=[]
    for token in re.findall(r"[A-Za-zÀ-ÿ0-9&']+",raw):
        low=token.lower()
        if low in IDENTITY_GENERIC_NAME_WORDS or low in {
            "by","barbarhouse","camera","matrimoniale","familiare","standard","accessibile",
            "premium","deluxe","superior","vista","mare"
        }:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return " ".join(tokens[:5]).strip() or raw[:80]


async def agoda_visible_date_state(page, stay: dict) -> dict:
    """Legge separatamente check-in e check-out mostrati nel searchbox Agoda."""
    try:
        state=await page.evaluate(r"""() => {
          const visible=(el) => {
            if(!el || el.getAttribute('aria-hidden')==='true') return false;
            const s=getComputedStyle(el); const r=el.getBoundingClientRect();
            return s.display!=='none' && s.visibility!=='hidden' && Number(s.opacity||'1')!==0 &&
                   r.width>0 && r.height>0;
          };
          const textOf=(el) => [
            el?.textContent||'', el?.getAttribute?.('value')||'',
            el?.getAttribute?.('aria-label')||'', el?.getAttribute?.('placeholder')||''
          ].join(' ').replace(/\s+/g,' ').trim();
          const first=(sels) => {
            for(const sel of sels){
              for(const el of Array.from(document.querySelectorAll(sel)).slice(0,40)){
                if(visible(el)) return {selector:sel,text:textOf(el)};
              }
            }
            return null;
          };
          return {
            start:first([
              '[data-selenium="checkInText"]',
              '[data-element-name*="check-in" i]',
              '[data-element-name*="checkin" i]',
              '[data-selenium*="checkin" i]',
              'input[name*="checkin" i]',
              'button[aria-label*="check-in" i]'
            ]),
            end:first([
              '[data-selenium="checkOutText"]',
              '[data-element-name*="check-out" i]',
              '[data-element-name*="checkout" i]',
              '[data-selenium*="checkout" i]',
              'input[name*="checkout" i]',
              'button[aria-label*="check-out" i]'
            ])
          };
        }""")
    except Exception:
        state={}
    start=date.fromisoformat(stay["checkin"])
    end=date.fromisoformat(stay["checkout"])
    start_text=str((state.get("start") or {}).get("text") or "").lower()
    end_text=str((state.get("end") or {}).get("text") or "").lower()
    return {
        "startText":start_text,
        "endText":end_text,
        "startOk":any(value in start_text for value in _date_forms(start)),
        "endOk":any(value in end_text for value in _date_forms(end)),
        "startSelector":str((state.get("start") or {}).get("selector") or ""),
        "endSelector":str((state.get("end") or {}).get("selector") or ""),
    }


async def agoda_direct_listing_with_dates(
    page, source: str, stay: dict, reason: str=""
) -> tuple[bool,str]:
    """Fallback deterministico Agoda sulla scheda ESATTA già scoperta.

    Non legge mai prezzi dalla homepage. Se il date picker della home non espone
    elementi cliccabili, apre la stessa scheda Agoda verificata aggiungendo le
    identiche date Booking, 2 adulti e 1 camera; poi controlla che il browser sia
    realmente rimasto su una pagina hotel e porta in vista camere/tariffe.
    """
    listing=normalize_ota_listing_url("agoda",source)
    parsed=urlparse(listing or "")
    path=(parsed.path or "").lower()
    if not listing or ("/hotel/" not in path and "/accommodation/" not in path):
        return False,"fallback scheda datata non disponibile: sorgente Agoda non è una scheda hotel verificata"

    target=dated_url("agoda",listing,stay) or listing
    try:
        response=await page.goto(target,wait_until="domcontentloaded",timeout=25000)
        if response and response.status in {403,429}:
            return False,f"fallback scheda datata bloccato da HTTP {response.status}"
        await dismiss_cookie(page)
        await page.wait_for_timeout(1800)
    except Exception as exc:
        return False,f"fallback scheda datata non caricata ({type(exc).__name__}: {str(exc)[:140]})"

    final_path=(urlparse(page.url).path or "").lower()
    if "/hotel/" not in final_path and "/accommodation/" not in final_path:
        return False,f"fallback scheda datata ha lasciato la pagina hotel · URL finale: {page.url[:280]}"

    # Tenta di portare il frontend alla griglia camere/offerte, senza login.
    offer,_=await _first_visible_locator(page,(
        'button:has-text("Vedi offerta")','a:has-text("Vedi offerta")',
        'button:has-text("See offer")','a:has-text("See offer")',
        'button:has-text("Camere")','a:has-text("Camere")',
        '[data-selenium*="room" i]',
    ))
    if offer is not None:
        try:
            await offer.scroll_into_view_if_needed(timeout=1400)
            await offer.click(timeout=2000)
            await page.wait_for_timeout(1000)
        except Exception:
            pass
    try:
        for fraction in (0.34,0.50,0.66,0.78):
            await page.evaluate(f"window.scrollTo(0, Math.floor(document.body.scrollHeight*{fraction}))")
            await page.wait_for_timeout(450)
            ok,_=await agoda_property_rate_context(page)
            if ok:
                break
    except Exception:
        pass

    dom_ok,dom_ev=await agoda_dom_dates_confirmed(page,stay)
    url_ok=agoda_url_dates_confirmed(page.url,stay)
    property_ok,property_ev=await agoda_property_rate_context(page)

    # Il browser deve avere applicato almeno una prova data verificabile e deve
    # trovarsi sulla scheda hotel. La presenza dell'area tariffaria viene riportata
    # separatamente: se non ci sono offerte pubbliche, il parser restituirà zero quote.
    confirmed=bool(dom_ok or url_ok)
    if not confirmed:
        return False,(
            f"fallback scheda datata aperto ma date non confermate · "
            f"DOM={dom_ev or 'n.d.'} · URL finale: {page.url[:300]}"
        )[:900]

    evidence=(
        f"fallback Agoda scheda esatta con BOOKING LOCK "
        f"{stay['checkin']}→{stay['checkout']} · {stay.get('nights')} notti · "
        f"{stay.get('adults',2)} adulti"
    )
    if reason:
        evidence+=f" · attivato perché: {reason}"
    evidence+=(
        f" · conferma date={'DOM' if dom_ok else 'URL finale'}"
        f" · pagina hotel confermata"
        f" · area camere/prezzi={'sì' if property_ok else 'non ancora visibile'}"
        f" · {property_ev or dom_ev or ''}"
        f" · URL finale: {page.url[:320]}"
    )
    return True,evidence[:1200]


async def agoda_prepare_frontend(
    page, source: str, stay: dict, property_name: str="", city: str=""
) -> tuple[bool,str]:
    """Replica il flusso Agoda pubblico mostrato da un utente reale.

    Homepage -> nome struttura -> suggerimento struttura (non singola unità) ->
    date -> 2 adulti -> Cerca -> card struttura -> pagina hotel -> Vedi offerta/camere.
    """
    evidence=[]
    target_name=_agoda_search_term(property_name,source)
    target_city=str(city or "").strip()

    try:
        await dismiss_cookie(page)
    except Exception:
        pass

    destination,_=await _first_visible_locator(page,(
        'input[placeholder*="Inserisci una destinazione" i]',
        'input[placeholder*="destinazione" i]',
        'input[placeholder*="destination" i]',
        'input[data-selenium*="search" i]',
        '[data-selenium="textInput"] input',
        '[data-selenium="textInput"]',
        '[data-selenium*="searchTextBox" i]',
        '[data-element-name*="search" i] input',
        'input[aria-label*="destinazione" i]',
        'input[aria-label*="destination" i]',
    ))
    if destination is None:
        direct_ok,direct_ev=await agoda_direct_listing_with_dates(
            page,source,stay,"campo destinazione/struttura non individuato nella homepage"
        )
        if direct_ok:
            return True,direct_ev
        return False,f"Agoda: campo destinazione/struttura non individuato nella homepage · {direct_ev}"

    try:
        await destination.click(timeout=1800)
        try:
            await destination.fill(target_name,timeout=2200)
        except Exception:
            await page.keyboard.press("Control+A")
            await page.keyboard.type(target_name,delay=35)
        await page.wait_for_timeout(1100)
        evidence.append(f"ricerca struttura «{target_name}»")
    except Exception as exc:
        return False,f"Agoda: impossibile compilare la ricerca struttura ({type(exc).__name__})"

    # Preferisce la struttura principale: penalizza risultati numerati/unità Barbarhouse.
    try:
        suggestion=await page.evaluate(r"""({name,city}) => {
          const norm=v=>String(v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'')
            .replace(/[^a-z0-9]+/g,' ').replace(/\s+/g,' ').trim();
          const visible=el=>{
            if(!el) return false; const s=getComputedStyle(el); const r=el.getBoundingClientRect();
            return s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity||'1')!==0&&r.width>0&&r.height>0;
          };
          const wanted=norm(name).split(' ').filter(x=>x.length>2);
          const cityNorm=norm(city);
          const roots=Array.from(document.querySelectorAll(
            '[role="option"],li,[data-selenium*="suggest" i],[data-element-name*="suggest" i],[class*="suggest" i]'
          )).filter(visible).slice(0,160);
          let best=null;
          for(const el of roots){
            const text=String(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
            if(!text||text.length<4||text.length>520) continue;
            const n=norm(text);
            const matched=wanted.filter(t=>n.includes(t)).length;
            if(!matched) continue;
            let score=matched*28;
            if(wanted.length && matched===wanted.length) score+=45;
            if(cityNorm && n.includes(cityNorm)) score+=35;
            if(/hotel\s*&?\s*restaurant|hotel\s+and\s+restaurant/i.test(text)) score+=30;
            if(/^\s*\d{3,}\b/.test(text)) score-=60;
            if(/barbarhouse/i.test(text)) score-=22;
            if(/camera|matrimoniale|suite\s+-|familiare|deluxe|standard|accessibile/i.test(text) && /^\s*\d{3,}/.test(text)) score-=35;
            if(!best||score>best.score) best={score,text,el};
          }
          if(!best) return null;
          best.el.setAttribute('data-velora-agoda-suggestion','1');
          return {score:best.score,text:best.text.slice(0,320)};
        }""",{"name":target_name,"city":target_city})
    except Exception:
        suggestion=None

    if suggestion:
        try:
            await page.locator('[data-velora-agoda-suggestion="1"]').first.click(timeout=2400)
            await page.wait_for_timeout(700)
            evidence.append("suggerimento struttura principale selezionato")
        except Exception:
            suggestion=None
    if not suggestion:
        try:
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(650)
            evidence.append("primo suggerimento ricerca selezionato")
        except Exception:
            direct_ok,direct_ev=await agoda_direct_listing_with_dates(
                page,source,stay,"nessun suggerimento struttura selezionabile"
            )
            if direct_ok:
                return True,(" · ".join(evidence+[direct_ev]))[:1200]
            return False,f"Agoda: nessun suggerimento struttura selezionabile · {direct_ev}"

    date_state=await agoda_visible_date_state(page,stay)
    evidence.append(
        "date iniziali: "
        f"check-in={date_state.get('startText') or 'n.d.'} · "
        f"check-out={date_state.get('endText') or 'n.d.'}"
    )

    async def open_date_control(kind: str) -> bool:
        selectors=(
            (
                '[data-selenium="checkInText"]',
                '[data-element-name*="check-in" i]',
                '[data-element-name*="checkin" i]',
                '[data-selenium*="checkin" i]',
                'button[aria-label*="check-in" i]',
                'input[name*="checkin" i]',
            )
            if kind=="start" else
            (
                '[data-selenium="checkOutText"]',
                '[data-element-name*="check-out" i]',
                '[data-element-name*="checkout" i]',
                '[data-selenium*="checkout" i]',
                'button[aria-label*="check-out" i]',
                'input[name*="checkout" i]',
            )
        )
        node,selector=await _first_visible_locator(page,selectors)
        if node is None:
            # Il widget desktop spesso usa un unico blocco date cliccabile.
            node,selector=await _first_visible_locator(page,(
                '[data-selenium*="date" i]',
                '[data-element-name*="date" i]',
                '[class*="SearchBox"] [class*="date" i]',
            ))
        if node is None:
            return False
        try:
            await node.click(timeout=2200)
        except Exception:
            try:
                await node.click(timeout=1800,force=True)
            except Exception:
                return False
        await page.wait_for_timeout(900)
        evidence.append(f"calendario aperto per {kind} con {selector}")
        return True

    async def mark_and_click_day(target_iso: str) -> tuple[bool,str]:
        target=date.fromisoformat(target_iso)
        month_words=list(MONTH_NAMES[target.month])
        forms=list(_date_forms(target))
        try:
            result=await page.evaluate(r"""({iso,day,year,months,forms}) => {
              const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
              const norm=v=>clean(v).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');
              const visible=el=>{
                if(!el) return false; const s=getComputedStyle(el); const r=el.getBoundingClientRect();
                return s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity||'1')!==0&&
                       r.width>8&&r.height>8&&r.bottom>0&&r.right>0&&r.top<innerHeight&&r.left<innerWidth;
              };
              const attrs=el=>[
                el?.textContent||'', el?.getAttribute?.('aria-label')||'',
                el?.getAttribute?.('data-date')||'', el?.getAttribute?.('data-value')||'',
                el?.getAttribute?.('data-selenium-date')||'', el?.getAttribute?.('title')||'',
                el?.getAttribute?.('datetime')||''
              ].join(' ');
              document.querySelectorAll('[data-velora-agoda-day]').forEach(el=>el.removeAttribute('data-velora-agoda-day'));

              const all=Array.from(document.querySelectorAll(
                'button,[role="button"],td,[data-date],[data-value],[aria-label],[class*="day" i],span,div'
              )).filter(visible).slice(0,2500);

              let best=null;
              for(const raw of all){
                const own=clean(raw.textContent);
                const attrText=norm(attrs(raw));
                const exactForm=forms.some(f=>attrText.includes(norm(f)));
                const ownDay=own===String(day)||own===String(day).padStart(2,'0');
                if(!exactForm && !ownDay) continue;

                const clickable=raw.closest('button,[role="button"],td,[data-date],[data-value]')||raw;
                if(!visible(clickable)) continue;
                if(clickable.getAttribute('aria-disabled')==='true'||clickable.hasAttribute('disabled')) {
                  // Se è già il giorno selezionato non serve cliccarlo; viene gestito dal controllo campo.
                  continue;
                }

                let score=exactForm?160:0, context='',p=clickable;
                for(let depth=0;depth<10&&p;depth++,p=p.parentElement){
                  const t=norm((p.innerText||p.textContent||'').slice(0,3500));
                  context+=' '+t;
                  const meta=norm(
                    String(p.className||'')+' '+
                    String(p.getAttribute?.('data-selenium')||'')+' '+
                    String(p.getAttribute?.('data-element-name')||'')+' '+
                    String(p.getAttribute?.('role')||'')
                  );
                  if(/calendar|datepicker|date picker|daypicker|month|datepanel/.test(meta)) score+=25;
                }
                if(months.some(m=>context.includes(norm(m)))) score+=70;
                if(context.includes(String(year))) score+=55;
                const aria=norm(clickable.getAttribute?.('aria-label')||'');
                if(months.some(m=>aria.includes(norm(m)))) score+=80;
                if(aria.includes(String(year))) score+=65;
                const r=clickable.getBoundingClientRect();
                if(r.width>=18&&r.width<=110&&r.height>=18&&r.height<=110) score+=20;
                // Preferisci il calendario centrale, non numeri omonimi nel resto pagina.
                if(r.top>120 && r.top<innerHeight-20) score+=10;
                if(!best||score>best.score) best={el:clickable,score,text:clean(attrs(clickable)).slice(0,180)};
              }
              if(!best||best.score<45) return null;
              best.el.setAttribute('data-velora-agoda-day','1');
              return {score:best.score,text:best.text};
            }""",{
                "iso":target_iso,"day":target.day,"year":target.year,
                "months":month_words,"forms":forms
            })
        except Exception:
            result=None
        if not result:
            return False,"nessun giorno candidato"
        node=page.locator('[data-velora-agoda-day="1"]').first
        try:
            await node.click(timeout=2200)
        except Exception:
            try:
                await node.click(timeout=1800,force=True)
            except Exception:
                try:
                    await page.evaluate(r"""() => document.querySelector('[data-velora-agoda-day="1"]')?.click()""")
                except Exception:
                    return False,f"giorno trovato ma non cliccabile ({result})"
        await page.wait_for_timeout(550)
        return True,f"{target_iso} selezionata ({result.get('text','')[:120]})"

    async def next_month() -> bool:
        node,_=await _first_visible_locator(page,(
            'button[aria-label*="next month" i]',
            'button[aria-label*="mese successivo" i]',
            'button[aria-label*="successivo" i]',
            '[data-selenium*="next" i]',
            '[data-element-name*="next" i]',
            '[class*="calendar" i] button:has-text("›")',
            '[class*="calendar" i] button:has-text(">")',
        ))
        if node is None:
            return False
        try:
            await node.click(timeout=1800)
        except Exception:
            try: await node.click(timeout=1500,force=True)
            except Exception: return False
        await page.wait_for_timeout(380)
        return True

    async def pick(target_iso: str) -> tuple[bool,str]:
        for step in range(15):
            ok,ev=await mark_and_click_day(target_iso)
            if ok:
                return True,ev
            if not await next_month():
                return False,ev
        return False,f"{target_iso} non raggiunta entro 15 mesi"

    # Non tentare di ricliccare una data che Agoda mostra già correttamente:
    # spesso il giorno selezionato è disabilitato nel calendario e v87 lo interpretava come errore.
    if date_state.get("startOk"):
        evidence.append(f"check-in {stay['checkin']} già corretto")
    else:
        if not await open_date_control("start"):
            direct_ok,direct_ev=await agoda_direct_listing_with_dates(
                page,source,stay,"controllo check-in homepage non apribile"
            )
            if direct_ok:
                return True,(" · ".join(evidence+[direct_ev]))[:1200]
            return False,f"Agoda: controllo check-in non apribile · {direct_ev}"
        ok,ev=await pick(stay["checkin"])
        evidence.append(ev)
        if not ok:
            direct_ok,direct_ev=await agoda_direct_listing_with_dates(
                page,source,stay,
                f"check-in {stay['checkin']} non selezionabile nel calendario pubblico · {ev}"
            )
            if direct_ok:
                return True,(" · ".join(evidence+[direct_ev]))[:1200]
            return False,(
                f"Agoda: check-in {stay['checkin']} non selezionabile nel calendario pubblico · {ev} · "
                f"{direct_ev}"
            )[:1200]

    # Rileggi i campi dopo il check-in: Agoda può chiudere/riaprire il calendario automaticamente.
    date_state=await agoda_visible_date_state(page,stay)
    if date_state.get("endOk"):
        evidence.append(f"check-out {stay['checkout']} già corretto")
    else:
        if not await open_date_control("end"):
            direct_ok,direct_ev=await agoda_direct_listing_with_dates(
                page,source,stay,"controllo check-out homepage non apribile"
            )
            if direct_ok:
                return True,(" · ".join(evidence+[direct_ev]))[:1200]
            return False,f"Agoda: controllo check-out non apribile · {direct_ev}"
        ok,ev=await pick(stay["checkout"])
        evidence.append(ev)
        if not ok:
            direct_ok,direct_ev=await agoda_direct_listing_with_dates(
                page,source,stay,
                f"check-out {stay['checkout']} non selezionabile nel calendario pubblico · {ev}"
            )
            if direct_ok:
                return True,(" · ".join(evidence+[direct_ev]))[:1200]
            return False,(
                f"Agoda: check-out {stay['checkout']} non selezionabile nel calendario pubblico · {ev} · "
                f"{direct_ev}"
            )[:1200]

    date_state=await agoda_visible_date_state(page,stay)
    if not (date_state.get("startOk") and date_state.get("endOk")):
        ui_reason=(
            "selezione date non confermata nei campi visibili · "
            f"check-in={date_state.get('startText') or 'n.d.'} · "
            f"check-out={date_state.get('endText') or 'n.d.'}"
        )
        direct_ok,direct_ev=await agoda_direct_listing_with_dates(page,source,stay,ui_reason)
        if direct_ok:
            return True,(" · ".join(evidence+[direct_ev]))[:1200]
        return False,f"Agoda: {ui_reason} · {direct_ev}"[:1200]
    evidence.append("date confermate nei campi Agoda prima di Cerca")

    # Agoda apre di norma con 2 adulti/1 camera. Se il riepilogo visibile lo conferma,
    # non tocca il controllo ospiti.
    try:
        guest_text=(await page.locator("body").inner_text(timeout=4500))[:9000]
    except Exception:
        guest_text=""
    if re.search(r"\b2\s*(?:adulti|adults)\b",guest_text,re.I):
        evidence.append("2 adulti confermati")
    else:
        guest_trigger,_=await _first_visible_locator(page,(
            '[data-selenium*="occupancy" i]','[data-element-name*="occupancy" i]',
            '[data-element-name*="guest" i]','button:has-text("adulti")','button:has-text("adults")',
        ))
        if guest_trigger is not None:
            try:
                await guest_trigger.click(timeout=1800)
                await page.wait_for_timeout(300)
                state=await page.evaluate(r"""(target) => {
                  const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
                  const vis=el=>{if(!el)return false;const s=getComputedStyle(el);const r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
                  document.querySelectorAll('[data-velora-agoda-minus],[data-velora-agoda-plus]').forEach(el=>{el.removeAttribute('data-velora-agoda-minus');el.removeAttribute('data-velora-agoda-plus')});
                  for(const label of Array.from(document.querySelectorAll('div,span,p,label')).filter(vis)){
                    if(!/^(adulti|adults)$/i.test(clean(label.textContent))) continue;
                    let row=label;
                    for(let d=0;d<6&&row;d++,row=row.parentElement){
                      const buttons=Array.from(row.querySelectorAll('button')).filter(vis);
                      const nums=Array.from(row.querySelectorAll('span,div')).map(el=>clean(el.textContent)).filter(v=>/^\d+$/.test(v));
                      if(buttons.length>=2&&nums.length){
                        const current=Number(nums[nums.length-1]);
                        if(!Number.isFinite(current)) continue;
                        buttons[0].setAttribute('data-velora-agoda-minus','1');
                        buttons[buttons.length-1].setAttribute('data-velora-agoda-plus','1');
                        return {current,target};
                      }
                    }
                  }
                  return null;
                }""",int(stay.get("adults") or 2))
                if state:
                    current=int(state["current"]); target=int(stay.get("adults") or 2)
                    while current<target:
                        await page.locator('[data-velora-agoda-plus="1"]').click(timeout=1000); current+=1
                        await page.wait_for_timeout(120)
                    while current>target:
                        await page.locator('[data-velora-agoda-minus="1"]').click(timeout=1000); current-=1
                        await page.wait_for_timeout(120)
                    evidence.append(f"ospiti {target} adulti")
                try: await page.keyboard.press("Escape")
                except Exception: pass
            except Exception:
                pass

    search,_=await _first_visible_locator(page,(
        'button:has-text("CERCA")','button:has-text("Cerca")','button:has-text("Search")',
        '[data-selenium="searchButton"]','[data-selenium*="search" i]',
        '[data-element-name*="search" i] button',
    ))
    if search is None:
        direct_ok,direct_ev=await agoda_direct_listing_with_dates(
            page,source,stay,"pulsante Cerca non individuato"
        )
        if direct_ok:
            return True,(" · ".join(evidence+[direct_ev]))[:1200]
        return False,f"Agoda: pulsante Cerca non individuato · {direct_ev}"
    try:
        await search.click(timeout=2400)
        evidence.append("Cerca cliccato")
        try: await page.wait_for_load_state("domcontentloaded",timeout=8000)
        except Exception: pass
        await page.wait_for_timeout(1800)
        await dismiss_cookie(page)
    except Exception as exc:
        direct_ok,direct_ev=await agoda_direct_listing_with_dates(
            page,source,stay,f"ricerca homepage non avviata ({type(exc).__name__})"
        )
        if direct_ok:
            return True,(" · ".join(evidence+[direct_ev]))[:1200]
        return False,f"Agoda: ricerca non avviata ({type(exc).__name__}) · {direct_ev}"

    # Se siamo nella lista risultati, entra nella card della struttura principale,
    # non nelle singole unità numerate.
    if "/hotel/" not in (urlparse(page.url).path or "").lower():
        try:
            card=await page.evaluate(r"""({name,city}) => {
              const norm=v=>String(v||'').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-z0-9]+/g,' ').replace(/\s+/g,' ').trim();
              const visible=el=>{if(!el)return false;const s=getComputedStyle(el);const r=el.getBoundingClientRect();return s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0};
              const wanted=norm(name).split(' ').filter(x=>x.length>2), cityNorm=norm(city);
              let best=null;
              const roots=Array.from(document.querySelectorAll('article,li,[data-selenium*="hotel" i],[data-element-name*="property" i],div')).filter(visible).slice(0,500);
              for(const root of roots){
                const text=String(root.innerText||root.textContent||'').replace(/\s+/g,' ').trim();
                if(!text||text.length<20||text.length>3200) continue;
                const n=norm(text), matched=wanted.filter(t=>n.includes(t)).length;
                if(!matched) continue;
                const links=Array.from(root.querySelectorAll('a[href]')).filter(visible);
                const link=links.find(a=>/\/hotel\//i.test(a.getAttribute('href')||''))||links[0];
                if(!link) continue;
                let score=matched*30;
                if(wanted.length&&matched===wanted.length) score+=50;
                if(cityNorm&&n.includes(cityNorm)) score+=35;
                if(/hotel\s*&?\s*restaurant|hotel\s+and\s+restaurant/i.test(text)) score+=25;
                if(/^\s*\d{3,}\b/.test(text)||/barbarhouse/i.test(text)) score-=35;
                if(!best||score>best.score) best={score,text,url:link.href};
              }
              return best ? {score:best.score,text:best.text.slice(0,260),url:best.url} : null;
            }""",{"name":target_name,"city":target_city})
        except Exception:
            card=None
        if not card or not card.get("url"):
            direct_ok,direct_ev=await agoda_direct_listing_with_dates(
                page,source,stay,"risultati caricati ma card struttura principale non individuata"
            )
            if direct_ok:
                return True,(" · ".join(evidence+[direct_ev]))[:1200]
            return False,(
                "Agoda: risultati caricati, ma la card della struttura principale non è stata individuata · "
                f"{direct_ev}"
            )[:1200]
        try:
            await page.goto(str(card["url"]),wait_until="domcontentloaded",timeout=22000)
            await dismiss_cookie(page)
            await page.wait_for_timeout(1500)
            evidence.append("card struttura principale aperta")
        except Exception as exc:
            direct_ok,direct_ev=await agoda_direct_listing_with_dates(
                page,source,stay,f"apertura card struttura non completata ({type(exc).__name__})"
            )
            if direct_ok:
                return True,(" · ".join(evidence+[direct_ev]))[:1200]
            return False,f"Agoda: apertura card struttura non completata ({type(exc).__name__}) · {direct_ev}"

    # Sulla scheda hotel, porta il frontend fino alle offerte/camere.
    offer,_=await _first_visible_locator(page,(
        'button:has-text("Vedi offerta")','a:has-text("Vedi offerta")',
        'button:has-text("See offer")','a:has-text("See offer")',
        'button:has-text("Camere")','a:has-text("Camere")',
        '[data-selenium*="room" i]',
    ))
    if offer is not None:
        try:
            await offer.scroll_into_view_if_needed(timeout=1200)
            await offer.click(timeout=1800)
            await page.wait_for_timeout(1200)
            evidence.append("area offerte/camere aperta")
        except Exception:
            pass
    try:
        for fraction in (0.42,0.58,0.72):
            await page.evaluate(f"window.scrollTo(0, Math.floor(document.body.scrollHeight*{fraction}))")
            await page.wait_for_timeout(500)
            body=(await page.locator("body").inner_text(timeout=4500))[:22000]
            if re.search(r"\b(a notte|per notte|per night)\b",body,re.I) and re.search(r"\b(?:€|EUR)\s*\d|\d\s*(?:€|EUR)",body,re.I):
                break
    except Exception:
        pass

    confirmed,dom_evidence=await agoda_dom_dates_confirmed(page,stay)
    if not confirmed:
        try:
            body=(await page.locator("body").inner_text(timeout=5000))[:16000]
        except Exception:
            body=""
        confirmed=visible_dates_confirmed(body,stay) or agoda_url_dates_confirmed(page.url,stay)
    if confirmed:
        evidence.append("date confermate nella scheda hotel")
    else:
        evidence.append("date non riconfermate nella scheda hotel")
    if dom_evidence:
        evidence.append(dom_evidence[:260])
    return confirmed,(" · ".join(evidence))[:1200]


async def agoda_room_offer_visual_candidates(page, stay: dict) -> list[dict]:
    """Parser visuale Agoda per il layout camere/offerte mostrato nel frontend italiano."""
    payload=await page.evaluate(r"""(wantedAdults) => {
      const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
      const visible=el=>{
        if(!el)return false; const s=getComputedStyle(el); const r=el.getBoundingClientRect();
        return s.display!=='none'&&s.visibility!=='hidden'&&Number(s.opacity||'1')!==0&&r.width>0&&r.height>0;
      };
      const money=/(?:€|EUR)\s*([0-9]{1,5}(?:[.,][0-9]{1,2})?)|([0-9]{1,5}(?:[.,][0-9]{1,2})?)\s*(?:€|EUR)/i;
      const roomRx=/\b(camera|suite|appartamento|apartment|room|studio|villa|matrimoniale|deluxe|superior|familiare|family|tripla|quadrupla|king|queen|twin|double)\b/i;
      const roomNodes=Array.from(document.querySelectorAll(
        'h2,h3,h4,[data-selenium="room-name"],[data-element-name*="room-name" i],[data-ppapi*="room-name" i]'
      )).filter(visible).map(el=>{
        const r=el.getBoundingClientRect(), text=clean(el.textContent);
        return {el,text,left:r.left,top:r.top,bottom:r.bottom};
      }).filter(x=>x.text&&x.text.length<260&&roomRx.test(x.text));

      const out=[],seen=new Set();
      const priceNodes=Array.from(document.querySelectorAll('span,strong,b,div')).filter(visible).filter(el=>{
        const t=clean(el.textContent);
        return t.length<=55&&money.test(t);
      }).slice(0,500);

      for(const priceEl of priceNodes){
        const pr=priceEl.getBoundingClientRect();
        let box=priceEl, text='';
        for(let d=0;d<7&&box;d++,box=box.parentElement){
          const t=clean(box.innerText||box.textContent);
          if(t.length>=20&&t.length<=2600&&/(a notte|per notte|per night)/i.test(t)&&money.test(t)){
            text=t; break;
          }
        }
        if(!box||!text) continue;
        const low=text.toLowerCase();
        const adultMatch=text.match(/\b(\d+)\s*(?:adulti|adults?)\b/i);
        if(adultMatch&&Number(adultMatch[1])!==Number(wantedAdults)) continue;
        if(/numero massimo di persone.*superato|massimo di persone.*superato|maximum occupancy.*exceed|max occupancy.*exceed/i.test(low)) continue;

        // Camera più vicina verticalmente sopra o sulla stessa riga della tariffa.
        let best=null;
        for(const room of roomNodes){
          const dy=pr.top-room.top;
          if(dy < -80 || dy > 950) continue;
          const score=Math.abs(dy) + Math.max(0,room.left-pr.left)*0.05;
          if(!best||score<best.score) best={...room,score};
        }
        if(!best) continue;
        const price=clean(priceEl.textContent);
        const key=(best.text+'|'+price+'|'+text.slice(0,700)).toLowerCase();
        if(seen.has(key)) continue;
        seen.add(key);
        out.push({room:best.text,price,text,dy:Math.round(pr.top-best.top)});
      }
      return out.slice(0,100);
    }""",int(stay.get("adults") or 2))

    out=[]
    for row in payload:
        room=str(row.get("room") or "").strip()
        text=str(row.get("text") or "").strip()
        price=_money_value(str(row.get("price") or ""))
        if not room or not text or price is None or price<=0:
            continue
        low=text.lower()
        fields=_price_fields(price,"nightly",stay)
        board="Colazione inclusa" if any(x in low for x in ("colazione inclusa","breakfast included")) else "Trattamento da verificare"
        if any(x in low for x in ("cancellazione gratuita","free cancellation")):
            refund="Cancellazione gratuita"
        elif any(x in low for x in ("non rimborsabile","non-refundable","non refundable")):
            refund="Non rimborsabile"
        else:
            refund="Cancellazione da verificare"
        taxes="Tasse e costi inclusi" if any(x in low for x in ("tasse e costi inclusi","tasse incluse","taxes included","taxes and fees included")) else "Da verificare nel dettaglio del preventivo"
        out.append({
            "roomType":room[:240],
            "ratePlan":" · ".join(x for x in (
                refund if refund!="Cancellazione da verificare" else "",
                board if board!="Trattamento da verificare" else ""
            ) if x) or "Piano tariffario pubblico",
            **fields,
            "currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
            "board":board,"refund":refund,"audience":"Pubblico senza login","taxes":taxes,
            "verified":True,
            "evidence":(
                fields["priceDerivation"]+
                f" Agoda frontend: camera associata visualmente alla riga tariffa (Δy {row.get('dy','?')}px). "+
                text
            )[:1200],
        })
    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item["nightlyRate"],item["refund"],item["board"])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:40]


async def agoda_offer_row_candidates(page, stay: dict) -> list[dict]:
    """Parser Agoda aderente al frontend: una riga offerta vicino al pulsante Prenota/Book."""
    rows=await page.evaluate(r"""(wantedAdults) => {
      const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
      const visible=el=>{
        if(!el)return false; const s=getComputedStyle(el); const r=el.getBoundingClientRect();
        if(s.display==='none'||s.visibility==='hidden'||Number(s.opacity||'1')===0||r.width<=0||r.height<=0) return false;
        if((s.textDecorationLine||'').includes('line-through')) return false;
        return true;
      };
      const roomRx=/\b(room|camera|suite|apartment|appartamento|studio|villa|double|twin|family|king|queen|deluxe|superior|quadrupla|tripla|matrimoniale)\b/i;
      const priceRx=/(?:€|EUR)\s*([0-9]{1,5}(?:[.,][0-9]{1,2})?)|([0-9]{1,5}(?:[.,][0-9]{1,2})?)\s*(?:€|EUR)/i;
      const out=[],seen=new Set();
      const buttons=Array.from(document.querySelectorAll('button,a,[role="button"]')).filter(visible)
        .filter(el=>/^(prenota|book|reserve)$/i.test(clean(el.innerText||el.textContent||el.getAttribute('aria-label')||'')));
      for(const button of buttons.slice(0,120)){
        let offer=button, offerText='';
        for(let d=0;d<7&&offer;d++,offer=offer.parentElement){
          const t=clean(offer.innerText||offer.textContent);
          if(t.length>25&&t.length<2400&&priceRx.test(t)&&/(a notte|per notte|per night)/i.test(t)){offerText=t;break}
        }
        if(!offer||!offerText) continue;
        const low=offerText.toLowerCase();
        if(/numero massimo di persone.*superato|massimo di persone.*superato|maximum occupancy.*exceed|max occupancy.*exceed/i.test(low)) continue;
        const adultMatch=offerText.match(/\b(\d+)\s*(?:adulti|adults?)\b/i);
        if(adultMatch&&Number(adultMatch[1])!==Number(wantedAdults)) continue;

        let room='',root=offer;
        for(let d=0;d<9&&root;d++,root=root.parentElement){
          const heads=Array.from(root.querySelectorAll('h2,h3,h4,[data-selenium="room-name"],[data-element-name*="room-name" i],[data-ppapi*="room-name" i]'))
            .filter(visible).map(el=>clean(el.textContent)).filter(v=>v&&v.length<260);
          room=heads.find(v=>roomRx.test(v))||'';
          if(room) break;
        }
        if(!room) continue;

        const priceNodes=Array.from(offer.querySelectorAll('span,strong,b,div')).filter(visible)
          .map(el=>clean(el.textContent)).filter(v=>v.length<=45&&priceRx.test(v));
        let priceText=priceNodes.find(v=>priceRx.test(v))||'';
        if(!priceText){
          const m=offerText.match(priceRx); priceText=m?m[0]:'';
        }
        if(!priceText) continue;
        const key=(room+'|'+priceText+'|'+offerText.slice(0,700)).toLowerCase();
        if(seen.has(key)) continue;
        seen.add(key); out.push({room,price:priceText,text:offerText});
      }
      return out.slice(0,80);
    }""",int(stay.get("adults") or 2))

    out=[]
    for row in rows:
        room=str(row.get("room") or "").strip()
        text=str(row.get("text") or "").strip()
        price=_money_value(str(row.get("price") or ""))
        if not room or not text or price is None or price<=0:
            continue
        low=text.lower()
        fields=_price_fields(price,"nightly",stay)
        board="Colazione inclusa" if any(x in low for x in ("colazione inclusa","breakfast included")) else "Trattamento da verificare"
        if any(x in low for x in ("cancellazione gratuita","free cancellation")):
            refund="Cancellazione gratuita"
        elif any(x in low for x in ("non rimborsabile","non-refundable","non refundable")):
            refund="Non rimborsabile"
        else:
            refund="Cancellazione da verificare"
        taxes=(
            "Tasse e costi inclusi"
            if any(x in low for x in ("tasse e costi inclusi","tasse incluse","taxes and fees included","taxes included"))
            else "Da verificare nel dettaglio del preventivo"
        )
        out.append({
            "roomType":room[:240],
            "ratePlan":" · ".join(x for x in (
                refund if refund!="Cancellazione da verificare" else "",
                board if board!="Trattamento da verificare" else ""
            ) if x) or "Piano tariffario pubblico",
            **fields,
            "currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
            "board":board,"refund":refund,"audience":"Pubblico senza login","taxes":taxes,
            "verified":True,
            "evidence":(fields["priceDerivation"]+" Riga offerta Agoda frontend: "+text)[:1200],
        })
    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item["nightlyRate"],item["refund"],item["board"])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:40]


async def generic_ota_frontend_apply_dates(page, channel: str, stay: dict) -> tuple[bool,str]:
    """Fallback frontend reale per OTA: apre il date picker, sceglie le date e conferma la ricerca."""
    label=OTA_META.get(channel,{}).get("label",channel)
    evidence=[]
    opener_selectors={
        "airbnb":(
            'button:has-text("Aggiungi una data")',
            'button:has-text("Check-in")',
            'button[aria-label*="check-in" i]',
            'button[aria-label*="date" i]',
            '[data-testid*="change-dates"]',
            '[data-testid*="date"]',
        ),
        "vrbo":(
            'button[aria-label*="check-in" i]','button[aria-label*="date" i]',
            '[data-stid*="date"]','[data-testid*="date"]',
            'button:has-text("Check-in")','button:has-text("Date")',
        ),
        "expedia":(
            'button[data-stid*="open-date-picker"]','button[aria-label*="date" i]',
            '[data-stid*="date"]','button:has-text("Date")','button:has-text("Check-in")',
        ),
        "hotels":(
            'button[data-stid*="open-date-picker"]','button[aria-label*="date" i]',
            '[data-stid*="date"]','button:has-text("Date")','button:has-text("Check-in")',
        ),
        "travelocity":(
            'button[data-stid*="open-date-picker"]','button[aria-label*="date" i]',
            '[data-stid*="date"]','button:has-text("Date")','button:has-text("Check-in")',
        ),
        "holidu":(
            'button:has-text("Select dates")','button:has-text("Choose dates")',
            'button:has-text("Date")','[data-testid*="date" i]',
            'button[aria-label*="check-in" i]','input[placeholder*="check-in" i]',
        ),
        "agoda":(
            '[data-selenium="checkInText"]','[data-element-name*="check-in" i]',
            '[data-element-name*="checkin" i]','button[aria-label*="check-in" i]',
            'input[name*="checkin" i]',
        ),
        "trip":(
            '[data-testid*="checkin" i]','[class*="checkin" i]',
            'button[aria-label*="check-in" i]','input[placeholder*="check-in" i]',
            'button:has-text("Check-in")',
        ),
    }.get(channel,())

    opener,_=await _first_visible_locator(page,opener_selectors)
    if opener is None:
        return False,f"{label}: controllo date frontend non individuato"
    try:
        await opener.scroll_into_view_if_needed(timeout=1200)
    except Exception:
        pass
    try:
        await opener.click(timeout=2200)
        await page.wait_for_timeout(550)
        evidence.append("date picker aperto")
    except Exception as exc:
        return False,f"{label}: date picker non apribile ({type(exc).__name__})"

    async def click_day(target_iso: str) -> bool:
        target=date.fromisoformat(target_iso)
        labels=[
            target_iso,
            f"{target.day}/{target.month}/{target.year}",
            f"{target.day:02d}/{target.month:02d}/{target.year}",
            f"{target.day} {MONTH_NAMES[target.month][1]} {target.year}",
            target.strftime("%B %d, %Y"),
            target.strftime("%b %d, %Y"),
        ]
        selectors=[
            f'[data-date="{target_iso}"]',
            f'[data-testid*="{target_iso}"]',
            f'[data-selenium*="{target_iso}"]',
            f'button[aria-label*="{target_iso}"]',
        ]
        for value in labels:
            selectors.extend((
                f'button[aria-label*="{value}" i]',
                f'[role="button"][aria-label*="{value}" i]',
            ))
        for selector in selectors:
            try:
                matches=page.locator(selector)
                count=min(await matches.count(),25)
            except Exception:
                count=0
            for idx in range(count):
                node=matches.nth(idx)
                try:
                    if not await node.is_visible(timeout=220):
                        continue
                    if (await node.get_attribute("aria-disabled"))=="true":
                        continue
                    await node.click(timeout=1800)
                    await page.wait_for_timeout(280)
                    return True
                except Exception:
                    continue
        return False

    async def next_month() -> bool:
        node,_=await _first_visible_locator(page,(
            'button[aria-label*="next month" i]',
            'button[aria-label*="mese successivo" i]',
            'button[aria-label*="next" i]',
            '[data-testid*="next-month" i]',
            '[data-stid*="next-month" i]',
            '[data-selenium*="next-month" i]',
        ))
        if node is None:
            return False
        try:
            await node.click(timeout=1600)
            await page.wait_for_timeout(250)
            return True
        except Exception:
            return False

    async def pick(target_iso: str) -> bool:
        for _ in range(20):
            if await click_day(target_iso):
                return True
            if not await next_month():
                return False
        return False

    start_ok=await pick(stay["checkin"])
    if not start_ok:
        return False,f"{label}: check-in {stay['checkin']} non selezionabile dal frontend"
    evidence.append(f"check-in {stay['checkin']}")
    end_ok=await pick(stay["checkout"])
    if not end_ok:
        return False,f"{label}: check-out {stay['checkout']} non selezionabile dal frontend"
    evidence.append(f"check-out {stay['checkout']}")

    # Imposta gli ospiti quando il frontend espone un selettore standard.
    try:
        guest_trigger,_=await _first_visible_locator(page,(
            'button:has-text("Ospiti")','button:has-text("Guests")',
            '[data-testid*="guest" i]','[data-stid*="guest" i]',
            '[data-element-name*="guest" i]',
        ))
        if guest_trigger is not None:
            await guest_trigger.click(timeout=1800)
            await page.wait_for_timeout(350)
            state=await page.evaluate(r"""(target) => {
              const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
              const visible=el=>{
                if(!el) return false; const st=getComputedStyle(el);
                if(st.display==='none'||st.visibility==='hidden') return false;
                const r=el.getBoundingClientRect(); return r.width>0&&r.height>0;
              };
              document.querySelectorAll('[data-velora-minus],[data-velora-plus]').forEach(el=>{
                el.removeAttribute('data-velora-minus'); el.removeAttribute('data-velora-plus');
              });
              const labels=Array.from(document.querySelectorAll('div,span,p,label')).filter(el =>
                visible(el) && /^(adulti|adults)$/i.test(clean(el.textContent))
              );
              for(const label of labels){
                let row=label;
                for(let depth=0;depth<6&&row;depth++,row=row.parentElement){
                  const buttons=Array.from(row.querySelectorAll('button')).filter(visible);
                  const nums=Array.from(row.querySelectorAll('span,div')).map(el=>clean(el.textContent)).filter(v=>/^\d+$/.test(v));
                  const current=nums.length?Number(nums[nums.length-1]):NaN;
                  if(buttons.length>=2&&Number.isFinite(current)){
                    buttons[0].setAttribute('data-velora-minus','1');
                    buttons[buttons.length-1].setAttribute('data-velora-plus','1');
                    return {current,target};
                  }
                }
              }
              return null;
            }""",int(stay.get("adults") or 2))
            if state and Number.isFinite(Number(state.get("current"))):
                current=int(state["current"]); target=int(stay.get("adults") or 2)
                while current<target:
                    await page.locator('[data-velora-plus="1"]').click(timeout=1100); current+=1
                    await page.wait_for_timeout(150)
                while current>target:
                    await page.locator('[data-velora-minus="1"]').click(timeout=1100); current-=1
                    await page.wait_for_timeout(150)
                evidence.append(f"ospiti {target} adulti")
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            await page.wait_for_timeout(250)
    except Exception:
        pass

    # Conferma/chiude il calendario. Evita CTA di pagamento: solo Search/Done/Apply/Availability.
    action,_=await _first_visible_locator(page,(
        'button:has-text("Cerca")','button:has-text("Search")',
        'button:has-text("Applica")','button:has-text("Apply")',
        'button:has-text("Fatto")','button:has-text("Done")',
        'button:has-text("Aggiorna")','button:has-text("Update")',
        'button:has-text("Controlla disponibilità")','button:has-text("Check availability")',
        '[data-testid*="search"]','[data-stid*="search"]',
    ))
    if action is not None:
        try:
            await action.click(timeout=2200)
            await page.wait_for_timeout(1400)
            evidence.append("ricerca frontend confermata")
        except Exception:
            pass
    else:
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        await page.wait_for_timeout(600)

    # Conferma specifica per portale dopo l'interazione.
    confirmed=False
    confirm_evidence=""
    try:
        body=(await page.locator("body").inner_text(timeout=6000))[:14000]
    except Exception:
        body=""
    if visible_dates_confirmed(body,stay):
        confirmed=True
        confirm_evidence="date visibili nella pagina"
    elif channel=="vrbo":
        confirmed=vrbo_url_dates_confirmed(page.url,stay)
        confirm_evidence="date URL Vrbo" if confirmed else ""
    elif channel=="holidu":
        confirmed=holidu_url_dates_confirmed(page.url,stay)
        confirm_evidence="date URL Holidu" if confirmed else ""
    elif channel in {"expedia","hotels","travelocity"}:
        confirmed=expedia_group_url_dates_confirmed(page.url,stay)
        confirm_evidence="date URL Expedia-group" if confirmed else ""
    elif channel=="agoda":
        confirmed,confirm_evidence=await agoda_dom_dates_confirmed(page,stay)
        if not confirmed:
            confirmed=agoda_url_dates_confirmed(page.url,stay)
            if confirmed: confirm_evidence="date URL Agoda"
    elif channel=="trip":
        confirmed=trip_url_dates_confirmed(page.url,stay)
        confirm_evidence="date URL Trip.com" if confirmed else ""

    if not confirmed and start_ok and end_ok:
        low=(body or "").lower()
        if body.strip() and not any(word in low for word in BLOCK_WORDS):
            confirmed=True
            confirm_evidence="check-in/check-out selezionati direttamente nel calendario frontend"
    if confirmed:
        evidence.append(confirm_evidence or "date confermate")
    return confirmed,(" · ".join(evidence))[:900]


async def vrbo_reveal_rates(page, source: str, stay: dict) -> str:
    """Vrbo: se Cerca apre i risultati, rientra nella stessa PDP e porta a vista le unità."""
    evidence=[]
    clean_source=normalize_ota_listing_url("vrbo",source)
    source_path=(urlparse(clean_source).path or "").rstrip("/")
    listing_id=""
    match=re.search(r"/(\d{5,})(?:/)?$",source_path)
    if match:
        listing_id=match.group(1)

    current_path=(urlparse(page.url).path or "").rstrip("/")
    if source_path and current_path!=source_path and listing_id:
        try:
            link=page.locator(f'a[href*="{listing_id}"]').first
            if await link.count() and await link.is_visible(timeout=700):
                await link.click(timeout=2200)
                await page.wait_for_timeout(1600)
                await dismiss_cookie(page)
                evidence.append("stessa struttura riaperta dalla lista risultati")
        except Exception as exc:
            evidence.append(f"rientro PDP: {type(exc).__name__}")

    for selector in (
        'button:has-text("Seleziona la tua unità")',
        'a:has-text("Seleziona la tua unità")',
        'button:has-text("Tariffe")',
        'a:has-text("Tariffe")',
        'button:has-text("Choose your unit")',
        'button:has-text("Rates")',
    ):
        try:
            node=page.locator(selector).first
            if await node.count() and await node.is_visible(timeout=350):
                await node.scroll_into_view_if_needed(timeout=1200)
                try:
                    await node.click(timeout=1800)
                except Exception:
                    pass
                await page.wait_for_timeout(1000)
                evidence.append("area unità/tariffe aperta")
                break
        except Exception:
            pass

    try:
        for fraction in (0.45,0.65,0.80,0.92):
            await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight*{fraction})")
            await page.wait_for_timeout(600)
            body=(await page.locator("body").inner_text(timeout=4500))[:22000]
            if (
                ("condizioni di cancellazione" in body.lower() or "cancellation" in body.lower())
                and re.search(r'\d[\d.,]*\s*€',body)
            ):
                evidence.append("card unità con prezzi renderizzate")
                break
    except Exception:
        pass
    return " · ".join(evidence)[:900] or "Vrbo: area tariffaria non individuata"


async def vrbo_quote_candidates(page, stay: dict) -> list[dict]:
    """Estrae card unità Vrbo con totale, €/notte e supplementi di cancellazione."""
    rows=await page.evaluate(r"""(nights) => {
      const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
      const visible=el=>{
        if(!el) return false; const st=getComputedStyle(el);
        if(st.display==='none'||st.visibility==='hidden'||Number(st.opacity||'1')===0) return false;
        const r=el.getBoundingClientRect(); return r.width>0&&r.height>0;
      };
      const out=[]; const seen=new Set();
      for(const node of Array.from(document.querySelectorAll('article,section,li,div')).filter(visible)){
        const text=clean(node.innerText||node.textContent);
        if(!text||text.length<80||text.length>4200) continue;
        const low=text.toLowerCase();
        if(!/(condizioni di cancellazione|cancellation)/i.test(low)) continue;
        if(!new RegExp('(?:per|for)\\s*'+nights+'\\s*(?:notti|nights?)','i').test(text)) continue;
        if(!/(€|eur)/i.test(text)) continue;
        let room='';
        for(const sel of ['h2','h3','h4','[data-stid*="room-name"]','[data-testid*="room-name"]']){
          const h=node.querySelector(sel); const v=clean(h?.textContent);
          if(v&&v.length<260){room=v;break}
        }
        if(!room) continue;
        const key=(room+'|'+text.slice(-900)).toLowerCase();
        if(seen.has(key)) continue;
        seen.add(key); out.push({room,text});
      }
      return out.slice(0,30);
    }""",int(stay["nights"]))

    out=[]
    total_rx=re.compile(r'([0-9]{1,5}(?:[.,][0-9]{1,2})?)\s*€\s*(?:per|for)\s*'+re.escape(str(stay["nights"]))+r'\s*(?:notti|nights?)',re.I)
    nightly_rx=re.compile(r'([0-9]{1,5}(?:[.,][0-9]{1,2})?)\s*€\s*(?:a notte|per notte|per night)',re.I)
    partial_rx=re.compile(r'(?:parzialmente rimborsabile|partially refundable)[^€+]{0,80}\+\s*([0-9]{1,5}(?:[.,][0-9]{1,2})?)\s*€',re.I)
    for row in rows:
        room=str(row.get("room") or "").strip()
        text=str(row.get("text") or "").strip()
        if not room or not text:
            continue
        total_match=total_rx.search(text)
        if not total_match:
            continue
        total=_localized_number(total_match.group(1))
        if total is None or total<=0:
            continue
        nightly_match=nightly_rx.search(text)
        nightly=_localized_number(nightly_match.group(1)) if nightly_match else None
        low=text.lower()
        board="Colazione inclusa" if ("colazione inclusa" in low or "breakfast included" in low) else "Trattamento da verificare"
        taxes=(
            "Tasse e oneri inclusi"
            if any(token in low for token in ("tasse e oneri inclusi","taxes and fees included","taxes included"))
            else "Da verificare nel dettaglio del preventivo"
        )
        base_fields=_price_fields(float(total),"stay-total",stay)
        if nightly is not None and abs(float(nightly)-base_fields["nightlyRate"])<=1.5:
            base_fields["nightlyRate"]=round(float(nightly),2)
            base_fields["priceDerivation"]+=f" Vrbo mostra anche €{float(nightly):.2f}/notte."
        out.append({
            "roomType":room[:240],"ratePlan":"Non rimborsabile",**base_fields,
            "currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
            "board":board,"refund":"Non rimborsabile","audience":"Pubblico senza login",
            "taxes":taxes,"verified":True,
            "evidence":("Vrbo card unità: totale e durata espliciti. "+text[:850])[:1100],
        })
        extra=partial_rx.search(text)
        if extra:
            surcharge=_localized_number(extra.group(1))
            if surcharge is not None and surcharge>=0:
                partial_total=round(float(total)+float(surcharge),2)
                fields=_price_fields(partial_total,"stay-total",stay)
                out.append({
                    "roomType":room[:240],"ratePlan":"Parzialmente rimborsabile",**fields,
                    "currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
                    "board":board,"refund":"Parzialmente rimborsabile","audience":"Pubblico senza login",
                    "taxes":taxes,"verified":True,
                    "evidence":(
                        f"Vrbo card unità: base €{float(total):.2f} + supplemento cancellazione "
                        f"€{float(surcharge):.2f} = €{partial_total:.2f}. "+text[:760]
                    )[:1100],
                })
    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item["ratePlan"].lower(),item["total"])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:24]



def holidu_url_dates_confirmed(url: str, stay: dict) -> bool:
    try:
        query={str(k).lower():str(v) for k,v in parse_qsl(urlparse(url).query,keep_blank_values=True)}
    except Exception:
        return False
    return (
        (query.get("checkin") or query.get("check_in") or "")==stay["checkin"]
        and (query.get("checkout") or query.get("check_out") or "")==stay["checkout"]
    )


async def holidu_reveal_rates(page, source: str, stay: dict) -> str:
    clean=normalize_ota_listing_url("holidu",source)
    source_path=(urlparse(clean).path or "").rstrip("/")
    match=re.search(r"/d/(\d+)",source_path,re.I)
    offer_id=match.group(1) if match else ""
    evidence=[]
    current_path=(urlparse(page.url).path or "").rstrip("/")
    if offer_id and "/d/" not in current_path.lower():
        try:
            link=page.locator(f'a[href*="/d/{offer_id}"]').first
            if await link.count() and await link.is_visible(timeout=700):
                await link.click(timeout=2200)
                await page.wait_for_timeout(1500)
                await dismiss_cookie(page)
                evidence.append("stessa proprietà riaperta dai risultati Holidu")
        except Exception as exc:
            evidence.append(f"rientro proprietà Holidu: {type(exc).__name__}")
    try:
        reserve,_=await _first_visible_locator(page,(
            'button:has-text("Reserve")','button:has-text("Prenota")',
            'button:has-text("Book")','button:has-text("Select dates")',
        ))
        if reserve is not None:
            await reserve.scroll_into_view_if_needed(timeout=1200)
        await page.wait_for_timeout(900)
        body=(await page.locator("body").inner_text(timeout=5000))[:18000]
        if "total price" in body.lower() or re.search(r'€\s*\d+[.,]?\d*\s*[x×]\s*\d+\s*nights?',body,re.I):
            evidence.append("riepilogo Holidu con totale soggiorno renderizzato")
    except Exception:
        pass
    return " · ".join(evidence)[:900] or "Holidu: riepilogo tariffario non individuato"


async def holidu_quote_candidates(page, stay: dict) -> list[dict]:
    payload=await page.evaluate(r"""() => {
      const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
      const visible=el=>{
        if(!el) return false; const st=getComputedStyle(el);
        if(st.display==='none'||st.visibility==='hidden'||Number(st.opacity||'1')===0) return false;
        const r=el.getBoundingClientRect(); return r.width>0&&r.height>0;
      };
      const title=clean(document.querySelector('h1')?.textContent).slice(0,260);
      const buttons=Array.from(document.querySelectorAll('button')).filter(visible);
      const reserve=buttons.find(el=>/^(reserve|prenota|book)$/i.test(clean(el.textContent)));
      let root=reserve?.closest('aside,section,article,div') || null;
      if(reserve){
        let n=reserve.parentElement;
        while(n&&n!==document.body){
          const t=clean(n.innerText||n.textContent);
          if(t.length>50&&t.length<3200&&/(total price|€|eur)/i.test(t)){root=n;break}
          n=n.parentElement;
        }
      }
      if(!root){
        root=Array.from(document.querySelectorAll('aside,section,article,div')).find(el=>{
          if(!visible(el)) return false;
          const t=clean(el.innerText||el.textContent);
          return t.length>50&&t.length<3200&&/(total price)/i.test(t)&&/(€|eur)/i.test(t);
        })||null;
      }
      return {title,text:clean(root?.innerText||root?.textContent).slice(0,3200)};
    }""")
    title=str(payload.get("title") or "").strip() or "Alloggio Holidu"
    text=str(payload.get("text") or "").strip()
    if not text:
        return []
    low=text.lower()
    values=[_money_value(match.group(0)) for match in PRICE_RE.finditer(text)]
    values=[v for v in values if v is not None]
    if not values:
        return []
    total=values[-1] if ("total price" in low or re.search(r'\b(total|totale)\b',low)) else None
    if total is None:
        return []
    fields=_price_fields(float(total),"stay-total",stay)
    refund=(
        "Cancellazione gratuita" if "free cancellation" in low or "cancellazione gratuita" in low
        else "Non rimborsabile" if "non-refundable" in low or "non rimborsabile" in low
        else "Cancellazione da verificare"
    )
    return [{
        "roomType":title[:240],
        "ratePlan":refund if refund!="Cancellazione da verificare" else "Piano tariffario da verificare",
        **fields,
        "currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
        "board":"Trattamento da verificare","refund":refund,
        "audience":"Pubblico senza login","taxes":"Da verificare nel dettaglio del preventivo",
        "verified":True,
        "evidence":(
            f"Holidu frontend: date {stay['checkin']}→{stay['checkout']}, {stay['adults']} adulti; "
            f"totale soggiorno esplicito €{float(total):.2f}. Contesto: {text[:760]}"
        )[:1100],
    }]

def expedia_group_url_dates_confirmed(url: str, stay: dict) -> bool:
    try:
        query={str(key).lower():str(value) for key,value in parse_qsl(urlparse(url).query,keep_blank_values=True)}
    except Exception:
        return False
    return (
        (query.get("chkin") or query.get("checkin") or query.get("check_in") or "") == stay["checkin"]
        and (query.get("chkout") or query.get("checkout") or query.get("check_out") or "") == stay["checkout"]
    )



async def expedia_group_reveal_rates(page, channel: str) -> str:
    """Porta Expedia/Hotels/Travelocity alla sezione camere prima del parsing."""
    label=OTA_META[channel]["label"]
    # Prima prova CTA esplicite che aprono/scrollano la disponibilità.
    selectors=(
        "button:has-text('Seleziona una camera')",
        "button:has-text('Scegli una camera')",
        "button:has-text('Vedi camere')",
        "button:has-text('Mostra camere')",
        "button:has-text('Choose a room')",
        "button:has-text('Select a room')",
        "button:has-text('View rooms')",
        "a:has-text('Seleziona una camera')",
        "a:has-text('Choose a room')",
        '[data-stid*="select-room"]',
        '[data-stid*="rooms"]',
    )
    for selector in selectors:
        try:
            node=page.locator(selector).first
            if await node.count() and await node.is_visible(timeout=350):
                try:
                    await node.scroll_into_view_if_needed(timeout=1200)
                except Exception:
                    pass
                text=re.sub(r"\s+"," ",(await node.inner_text(timeout=500)) or selector).strip()[:100]
                try:
                    await node.click(timeout=1800)
                except Exception:
                    # Alcune CTA sono ancore/scroll target non cliccabili dal browser automation.
                    try:
                        await node.evaluate("(el)=>el.click()")
                    except Exception:
                        pass
                await page.wait_for_timeout(1800)
                return f"{label}: CTA camere aperta «{text}»"

        except Exception:
            pass

    # Fallback: raggiunge direttamente un contenitore camere/offerte se già nel DOM.
    for selector in (
        '[data-stid*="room-card"]',
        '[data-stid*="room-offer"]',
        '[data-stid*="room-list"]',
        '[data-testid*="room-card"]',
        '[data-testid*="room"]',
        '[id*="room"]',
    ):
        try:
            node=page.locator(selector).first
            if await node.count():
                await node.scroll_into_view_if_needed(timeout=1400)
                await page.wait_for_timeout(1400)
                return f"{label}: sezione camere raggiunta via {selector}"
        except Exception:
            pass

    # Ultimo tentativo: scroll progressivo per innescare lazy rendering delle offerte.
    try:
        for fraction in (0.45,0.65,0.82):
            await page.evaluate(f"window.scrollTo(0, document.body.scrollHeight*{fraction})")
            await page.wait_for_timeout(850)
            count=await page.locator(
                '[data-stid*="room-card"], [data-stid*="room-offer"], [data-stid*="price"], [data-testid*="room"], [data-testid*="price"]'
            ).count()
            if count:
                return f"{label}: lazy rendering camere attivato dopo scroll ({count} nodi tariffari)"
    except Exception:
        pass
    return f"{label}: CTA/sezione camere non individuata"


async def expedia_group_property_rate_context(page, channel: str) -> tuple[bool,str]:
    selectors=(
        '[data-stid="content-hotel-title"]',
        '[data-stid*="room"]',
        '[data-stid="price-lockup-text"]',
        '[data-stid*="price"]',
        '[data-testid*="room"]',
        'h1',
    )
    found=[]
    for selector in selectors:
        try:
            loc=page.locator(selector).first
            if await loc.count() and await loc.is_visible(timeout=350):
                found.append(selector)
        except Exception:
            pass
    path=(urlparse(page.url).path or "").lower()
    not_search=not any(token in path for token in ("/hotel-search","/searchresults","/search"))
    has_identity="h1" in found or '[data-stid="content-hotel-title"]' in found
    has_rate=any(item in found for item in (
        '[data-stid*="room"]',
        '[data-stid="price-lockup-text"]',
        '[data-stid*="price"]',
        '[data-testid*="room"]',
    ))
    # Una scheda hotel esatta può essere confermata anche prima che Expedia abbia
    # lazy-renderizzato le camere. La presenza tariffaria viene verificata dopo
    # expedia_group_reveal_rates().
    return bool(not_search and has_identity),(
        ", ".join(found[:8]) + (" · rate-context presente" if has_rate else " · rate-context da aprire")
    )


async def expedia_group_quote_candidates(page, stay: dict, channel: str) -> list[dict]:
    """Estrae camera e prezzo da card tariffarie Expedia/Hotels.com, evitando il solo prezzo hero."""
    rows=await page.evaluate(r"""() => {
      const clean=(value) => String(value || '').replace(/\s+/g,' ').trim();
      const visible=(el) => {
        if (!el) return false;
        const st=getComputedStyle(el);
        if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
        if ((st.textDecorationLine || '').includes('line-through')) return false;
        const r=el.getBoundingClientRect();
        return r.width>0 && r.height>0;
      };
      const priceSelectors=[
        '[data-stid="price-lockup-text"]',
        '[data-stid*="price"]',
        '[data-testid*="price"]'
      ];
      const roomSelectors=[
        '[data-stid*="room-name"]',
        '[data-testid*="room-name"]',
        '[data-stid*="room-title"]',
        'h2','h3','h4'
      ];
      let cards=Array.from(document.querySelectorAll(
        '[data-stid*="room-card"], [data-stid*="room-offer"], [data-stid*="room-list"] > *, ' +
        '[data-stid*="property-offer"], [data-stid*="offer-card"], ' +
        '[data-testid*="room-card"], [data-testid*="room"], [data-testid*="offer"]'
      )).slice(0,220);

      // Expedia cambia spesso il markup. Se i data-* specifici non producono card,
      // risale dai nodi prezzo al contenitore più vicino con testo camera/offerta.
      if (!cards.length) {
        const priceNodes=Array.from(document.querySelectorAll(
          '[data-stid*="price"], [data-testid*="price"], [class*="price" i]'
        )).filter(visible).slice(0,180);
        cards=priceNodes.map(node =>
          node.closest('article,li,section,[role="group"],[data-stid],[data-testid],div') || node.parentElement
        ).filter(Boolean);
      }
      const out=[]; const seen=new Set();
      for (const card of cards) {
        if (!visible(card)) continue;
        let room='';
        for (const selector of roomSelectors) {
          const node=card.querySelector(selector);
          const value=clean(node?.textContent);
          if (!value) continue;
          if ((selector==='h2'||selector==='h3'||selector==='h4') &&
              !/\b(room|camera|suite|apartment|appartamento|studio|double|twin|family|king|queen|deluxe|superior)\b/i.test(value)) continue;
          room=value.slice(0,240); break;
        }
        if (!room) continue;
        let priceNode=null;
        for (const selector of priceSelectors) {
          const candidates=Array.from(card.querySelectorAll(selector)).filter(visible);
          if (candidates.length) { priceNode=candidates[0]; break; }
        }
        if (!priceNode) continue;
        const price=clean(priceNode.textContent).slice(0,180);
        const text=clean(card.innerText || card.textContent).slice(0,2600);
        if (!price || !text) continue;
        const low=text.toLowerCase();
        let basis='';
        if (/(total|totale|for the stay|for your stay|per stay|soggiorno|for \d+ nights?|per \d+ notti?)/i.test(low)) basis='stay-total';
        else if (/(per night|\/night|a notte|per notte|nightly)/i.test(low)) basis='nightly';
        const key=(room+'|'+price+'|'+basis+'|'+text.slice(0,900)).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({room,price,text,basis});
      }
      return out.slice(0,120);
    }""")

    out=[]
    for row in rows:
        room=str(row.get("room") or "").strip()
        price=_money_value(str(row.get("price") or ""))
        text=str(row.get("text") or "").strip()
        basis=str(row.get("basis") or "")
        if not room or price is None or not basis:
            continue
        total=price*int(stay["nights"]) if basis=="nightly" else price
        low=text.lower()

        if any(token in low for token in ("breakfast included","colazione inclusa","colazione compresa")):
            board="Colazione inclusa"
        elif any(token in low for token in ("room only","solo pernottamento","senza colazione")):
            board="Solo pernottamento"
        else:
            board="Trattamento da verificare"

        if any(token in low for token in ("fully refundable","free cancellation","cancellazione gratuita")):
            refund="Cancellazione gratuita"
        elif any(token in low for token in ("non-refundable","non refundable","non rimborsabile")):
            refund="Non rimborsabile"
        else:
            refund="Cancellazione da verificare"

        if any(token in low for token in ("taxes and fees included","includes taxes","tasse incluse","imposte incluse")):
            taxes="Tasse e commissioni indicate come incluse"
        elif any(token in low for token in ("excluding taxes","taxes excluded","before taxes","tasse escluse","imposte escluse")):
            taxes="Tasse indicate come escluse"
        else:
            taxes="Da verificare nel dettaglio del preventivo"

        if any(token in low for token in ("member price","member rate","members save","prezzo soci","tariffa soci","sign in","accedi per","app price","mobile app price")):
            continue
        audience="Pubblico senza login"
        plan_parts=[]
        if refund!="Cancellazione da verificare": plan_parts.append(refund)
        if board!="Trattamento da verificare": plan_parts.append(board)
        if audience!="Pubblico senza login": plan_parts.append("Member")
        rate_plan=" · ".join(dict.fromkeys(plan_parts)) or "Piano tariffario da verificare"
        basis_note=(
            f"Prezzo per notte visibile (€{price:.2f}) × {stay['nights']} notti = €{total:.2f}. "
            if basis=="nightly"
            else "Totale soggiorno indicato nel blocco camera. "
        )
        out.append({
            "roomType":room,
            "ratePlan":rate_plan,
            "total":round(total,2),
            "currency":"EUR",
            "nights":stay["nights"],
            "guests":stay["adults"],
            "board":board,
            "refund":refund,
            "audience":audience,
            "taxes":taxes,
            "verified":True,
            "evidence":(basis_note+text)[:1100],
        })

    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item.get("ratePlan","").lower(),item["total"])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:40]



async def expedia_group_semantic_quote_candidates(page, stay: dict, channel: str) -> list[dict]:
    """Fallback frontend: conserva prezzi con durata esplicita anche se il markup OTA cambia."""
    rows=await page.evaluate(r"""(nights) => {
      const clean=v=>String(v||'').replace(/\s+/g,' ').trim();
      const visible=el=>{
        if(!el) return false;
        const st=getComputedStyle(el);
        if(st.display==='none'||st.visibility==='hidden'||Number(st.opacity||'1')===0) return false;
        const r=el.getBoundingClientRect(); return r.width>0&&r.height>0;
      };
      const duration=new RegExp('(?:per|for)\\s*'+nights+'\\s*(?:notti|nights?)','i');
      const nightly=/(a notte|per notte|per night|\/night)/i;
      const euro=/(€|eur)\s*[0-9]|[0-9][0-9.,\s]*\s*(€|eur)/i;
      const out=[]; const seen=new Set();
      for(const node of Array.from(document.querySelectorAll('article,li,section,div')).filter(visible)){
        const text=clean(node.innerText||node.textContent);
        if(text.length<35||text.length>2800||!euro.test(text)) continue;
        if(!duration.test(text) && !nightly.test(text)) continue;
        let room='';
        for(const sel of ['[data-stid*="room-name"]','[data-testid*="room-name"]','h2','h3','h4']){
          const v=clean(node.querySelector(sel)?.textContent);
          if(v && v.length<260){room=v;break}
        }
        const key=(room+'|'+text).toLowerCase();
        if(seen.has(key)) continue;
        seen.add(key); out.push({room,text});
      }
      out.sort((a,b)=>a.text.length-b.text.length);
      return out.slice(0,60);
    }""",int(stay["nights"]))

    total_rx=re.compile(
        r'(?:(?:€|EUR)\s*[0-9]{1,6}(?:[.,][0-9]{1,2})?|[0-9]{1,6}(?:[.,][0-9]{1,2})?\s*(?:€|EUR))'
        r'\s*(?:per|for)\s*'+re.escape(str(stay["nights"]))+r'\s*(?:notti|nights?)',
        re.I,
    )
    nightly_rx=re.compile(
        r'(?:(?:€|EUR)\s*[0-9]{1,6}(?:[.,][0-9]{1,2})?|[0-9]{1,6}(?:[.,][0-9]{1,2})?\s*(?:€|EUR))'
        r'\s*(?:a notte|per notte|per night|/night)',
        re.I,
    )
    try:
        property_title=(await page.locator("h1").first.inner_text(timeout=700)).strip()
    except Exception:
        property_title=OTA_META[channel]["label"]+" · unità disponibile"

    out=[]
    for row in rows:
        text=str(row.get("text") or "").strip()
        room=str(row.get("room") or "").strip()
        if not text:
            continue
        total_match=total_rx.search(text)
        nightly_match=nightly_rx.search(text)
        basis=""
        amount=None
        if total_match:
            amount=_money_value(total_match.group(0))
            basis="stay-total"
        elif nightly_match:
            amount=_money_value(nightly_match.group(0))
            basis="nightly"
        if amount is None or amount<=0:
            continue
        fields=_price_fields(float(amount),basis,stay)
        low=text.lower()
        board="Colazione inclusa" if any(t in low for t in ("colazione inclusa","breakfast included")) else "Trattamento da verificare"
        refund=(
            "Cancellazione gratuita" if any(t in low for t in ("cancellazione gratuita","free cancellation","fully refundable"))
            else "Non rimborsabile" if any(t in low for t in ("non rimborsabile","non-refundable","non refundable"))
            else "Cancellazione da verificare"
        )
        room_known=bool(room and re.search(
            r'\b(room|camera|suite|apartment|appartamento|studio|double|twin|family|familiare|king|queen|deluxe|superior|casa|attico|villa)\b',
            room,re.I
        ))
        out.append({
            "roomType":(room if room_known else property_title+" · tipologia da verificare")[:240],
            "ratePlan":refund if refund!="Cancellazione da verificare" else "Piano tariffario da verificare",
            **fields,
            "currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
            "board":board,"refund":refund,"audience":"Pubblico senza login",
            "taxes":"Da verificare nel dettaglio del preventivo",
            "verified":bool(room_known),
            "evidence":(
                f"{OTA_META[channel]['label']} frontend: prezzo e durata espliciti nel medesimo blocco. "
                + text[:900]
            )[:1100],
        })

    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item["total"])
        if key in seen:
            continue
        seen.add(key); unique.append(item)
    return unique[:30]


def trip_url_dates_confirmed(url: str, stay: dict) -> bool:
    try:
        query={str(key).lower():str(value) for key,value in parse_qsl(urlparse(url).query,keep_blank_values=True)}
    except Exception:
        return False
    return (
        (query.get("checkin") or query.get("check_in") or "") == stay["checkin"]
        and (query.get("checkout") or query.get("check_out") or "") == stay["checkout"]
    )


async def trip_property_rate_context(page) -> tuple[bool,str]:
    selectors=(
        '[data-testid*="room"]',
        '[class*="room-list" i]',
        '[class*="room-card" i]',
        '[class*="room-item" i]',
        '[class*="price" i]',
        'h1',
    )
    found=[]
    for selector in selectors:
        try:
            loc=page.locator(selector).first
            if await loc.count() and await loc.is_visible(timeout=350):
                found.append(selector)
        except Exception:
            pass
    path=(urlparse(page.url).path or "").lower()
    property_path=(
        "hotel-detail" in path
        or "/hotel/" in path
        or ("/hotels/" in path and "search" not in path)
    )
    has_rate=any(item in found for item in (
        '[data-testid*="room"]',
        '[class*="room-list" i]',
        '[class*="room-card" i]',
        '[class*="room-item" i]',
    )) and '[class*="price" i]' in found
    return bool(property_path and "h1" in found and has_rate),", ".join(found[:8])


async def trip_quote_candidates(page, stay: dict) -> list[dict]:
    rows=await page.evaluate(r"""() => {
      const clean=(value) => String(value || '').replace(/\s+/g,' ').trim();
      const visible=(el) => {
        if (!el) return false;
        const st=getComputedStyle(el);
        if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
        if ((st.textDecorationLine || '').includes('line-through')) return false;
        const r=el.getBoundingClientRect();
        return r.width>0 && r.height>0;
      };
      const cards=Array.from(document.querySelectorAll(
        '[data-testid*="room-card"], [data-testid*="room-item"], [class*="room-card" i], ' +
        '[class*="room-item" i], [class*="room-list" i] > *, tr'
      )).slice(0,180);
      const out=[]; const seen=new Set();
      for (const card of cards) {
        if (!visible(card)) continue;
        let room='';
        for (const selector of ['[data-testid*="room-name"]','[class*="room-name" i]','[class*="room-title" i]','h3','h4']) {
          const node=card.querySelector(selector);
          const value=clean(node?.textContent);
          if (!value) continue;
          if ((selector==='h3'||selector==='h4') &&
              !/\b(room|camera|suite|apartment|appartamento|studio|double|twin|family|king|queen|deluxe|superior)\b/i.test(value)) continue;
          room=value.slice(0,240); break;
        }
        if (!room) continue;
        let priceNode=null;
        for (const selector of ['[data-testid*="price"]','[class*="price" i]']) {
          const matches=Array.from(card.querySelectorAll(selector)).filter(visible);
          if (matches.length) { priceNode=matches[0]; break; }
        }
        if (!priceNode) continue;
        const price=clean(priceNode.textContent).slice(0,180);
        const text=clean(card.innerText || card.textContent).slice(0,2600);
        if (!price || !text) continue;
        const low=text.toLowerCase();
        let basis='';
        if (/(total|totale|for the stay|per stay|soggiorno|for \d+ nights?|per \d+ notti?)/i.test(low)) basis='stay-total';
        else if (/(per night|\/night|a notte|per notte|nightly)/i.test(low)) basis='nightly';
        if (!basis) continue;
        const key=(room+'|'+price+'|'+basis+'|'+text.slice(0,900)).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({room,price,text,basis});
      }
      return out.slice(0,120);
    }""")

    out=[]
    for row in rows:
        room=str(row.get("room") or "").strip()
        price=_money_value(str(row.get("price") or ""))
        text=str(row.get("text") or "").strip()
        basis=str(row.get("basis") or "")
        if not room or price is None or not basis:
            continue
        total=price*int(stay["nights"]) if basis=="nightly" else price
        low=text.lower()
        board=(
            "Colazione inclusa" if any(token in low for token in ("breakfast included","colazione inclusa","colazione compresa"))
            else "Solo pernottamento" if any(token in low for token in ("room only","solo pernottamento","senza colazione"))
            else "Trattamento da verificare"
        )
        refund=(
            "Cancellazione gratuita" if any(token in low for token in ("free cancellation","cancellazione gratuita","fully refundable"))
            else "Non rimborsabile" if any(token in low for token in ("non-refundable","non refundable","non rimborsabile"))
            else "Cancellazione da verificare"
        )
        taxes=(
            "Tasse e commissioni indicate come incluse"
            if any(token in low for token in ("taxes included","taxes and fees included","tasse incluse","imposte incluse"))
            else "Tasse indicate come escluse"
            if any(token in low for token in ("taxes excluded","excluding taxes","before taxes","tasse escluse","imposte escluse"))
            else "Da verificare nel dettaglio del preventivo"
        )
        if any(token in low for token in ("member price","member rate","members save","sign in","accedi per","app price","mobile app price")):
            continue
        audience="Pubblico senza login"
        plan_parts=[]
        if refund!="Cancellazione da verificare": plan_parts.append(refund)
        if board!="Trattamento da verificare": plan_parts.append(board)
        if audience!="Pubblico senza login": plan_parts.append("Member")
        rate_plan=" · ".join(dict.fromkeys(plan_parts)) or "Piano tariffario da verificare"
        basis_note=(
            f"Prezzo per notte visibile (€{price:.2f}) × {stay['nights']} notti = €{total:.2f}. "
            if basis=="nightly"
            else "Totale soggiorno indicato nel blocco camera. "
        )
        out.append({
            "roomType":room,
            "ratePlan":rate_plan,
            "total":round(total,2),
            "currency":"EUR",
            "nights":stay["nights"],
            "guests":stay["adults"],
            "board":board,
            "refund":refund,
            "audience":audience,
            "taxes":taxes,
            "verified":True,
            "evidence":(basis_note+text)[:1100],
        })
    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item.get("ratePlan","").lower(),item["total"])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:40]



async def priceline_dom_dates_confirmed(page, stay: dict) -> tuple[bool,str]:
    try:
        state=await page.evaluate(r"""() => {
          const visible=(el) => {
            if (!el || el.getAttribute('aria-hidden') === 'true') return false;
            const st=getComputedStyle(el);
            if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
            const r=el.getBoundingClientRect();
            return r.width>0 && r.height>0;
          };
          const txt=(el) => [
            el?.textContent || '',
            el?.getAttribute?.('value') || '',
            el?.getAttribute?.('aria-label') || '',
            el?.getAttribute?.('placeholder') || ''
          ].join(' ').replace(/\s+/g,' ').trim();
          const find=(selectors) => {
            for (const selector of selectors) {
              for (const el of Array.from(document.querySelectorAll(selector)).slice(0,40)) {
                if (visible(el)) return {selector,text:txt(el)};
              }
            }
            return null;
          };
          return {
            start:find([
              'input[aria-label*="check-in" i]',
              'button[aria-label*="check-in" i]',
              'input[placeholder*="check-in" i]',
              '[data-testid*="check-in" i]',
              '[data-test*="check-in" i]'
            ]),
            end:find([
              'input[aria-label*="check-out" i]',
              'button[aria-label*="check-out" i]',
              'input[placeholder*="check-out" i]',
              '[data-testid*="check-out" i]',
              '[data-test*="check-out" i]'
            ]),
            title:find(['h1'])
          };
        }""")
    except Exception:
        return False,""
    start=date.fromisoformat(stay["checkin"])
    end=date.fromisoformat(stay["checkout"])
    start_text=str((state.get("start") or {}).get("text") or "").lower()
    end_text=str((state.get("end") or {}).get("text") or "").lower()
    start_ok=any(value in start_text for value in _date_forms(start))
    end_ok=any(value in end_text for value in _date_forms(end))
    evidence=(
        f"start={start_text[:240] or 'n.d.'} | "
        f"end={end_text[:240] or 'n.d.'} | "
        f"title={str((state.get('title') or {}).get('text') or '')[:240] or 'n.d.'}"
    )
    return bool(start_ok and end_ok),evidence[:800]


async def priceline_apply_dates_via_ui(page, stay: dict) -> tuple[bool,str]:
    evidence=[]
    opener,_=await _first_visible_locator(page,(
        'input[aria-label*="check-in" i]',
        'button[aria-label*="check-in" i]',
        'input[placeholder*="check-in" i]',
        '[data-testid*="check-in" i]',
        '[data-test*="check-in" i]',
        'button:has-text("Select date")',
    ))
    if opener is None:
        return False,"date picker Priceline non individuato"
    try:
        await opener.click(timeout=2500)
        await page.wait_for_timeout(450)
        evidence.append("date picker aperto")
    except Exception as exc:
        return False,f"date picker Priceline non apribile: {type(exc).__name__}"

    async def click_target(target_iso: str) -> bool:
        target=date.fromisoformat(target_iso)
        labels=[
            target_iso,
            target.strftime("%B %d, %Y"),
            target.strftime("%b %d, %Y"),
            target.strftime("%d %B %Y"),
        ]
        selectors=[f'[data-date="{target_iso}"]',f'[data-testid="{target_iso}"]']
        for label in labels:
            selectors.extend([
                f'button[aria-label*="{label}" i]',
                f'[role="button"][aria-label*="{label}" i]',
            ])
        for selector in selectors:
            try:
                matches=page.locator(selector)
                count=min(await matches.count(),30)
            except Exception:
                count=0
            for idx in range(count):
                node=matches.nth(idx)
                try:
                    if not await node.is_visible(timeout=250):
                        continue
                    if (await node.get_attribute("aria-disabled"))=="true":
                        continue
                    await node.click(timeout=2200)
                    await page.wait_for_timeout(350)
                    return True
                except Exception:
                    continue
        return False

    async def pick(target_iso: str) -> bool:
        for _ in range(20):
            if await click_target(target_iso):
                return True
            nxt,_=await _first_visible_locator(page,(
                'button[aria-label*="next month" i]',
                'button[aria-label*="mese successivo" i]',
                '[data-testid*="next-month" i]',
                '[data-test*="next-month" i]',
            ))
            if nxt is None:
                return False
            try:
                await nxt.click(timeout=1800)
                await page.wait_for_timeout(250)
            except Exception:
                return False
        return False

    if not await pick(stay["checkin"]):
        return False,"check-in Priceline non selezionabile"
    evidence.append(f"check-in {stay['checkin']} selezionato")
    if not await pick(stay["checkout"]):
        return False,"check-out Priceline non selezionabile"
    evidence.append(f"check-out {stay['checkout']} selezionato")

    search,_=await _first_visible_locator(page,(
        'button:has-text("Search")',
        'button:has-text("Cerca")',
        'button[type="submit"]',
        '[data-testid*="search" i]',
    ))
    if search is not None:
        try:
            await search.click(timeout=2200)
            await page.wait_for_timeout(1400)
            evidence.append("ricerca confermata")
        except Exception:
            pass

    confirmed,dom_evidence=await priceline_dom_dates_confirmed(page,stay)
    if not confirmed:
        body=(await page.locator("body").inner_text(timeout=5000))[:8000]
        confirmed=visible_dates_confirmed(body,stay)
    return confirmed,(" · ".join(evidence)+" | "+dom_evidence)[:900]


async def priceline_property_rate_context(page) -> tuple[bool,str]:
    selectors=(
        'h1',
        '[class*="room" i]',
        '[data-testid*="room" i]',
        '[class*="price" i]',
        '[data-testid*="price" i]',
    )
    found=[]
    for selector in selectors:
        try:
            loc=page.locator(selector).first
            if await loc.count() and await loc.is_visible(timeout=350):
                found.append(selector)
        except Exception:
            pass
    path=(urlparse(page.url).path or "").lower()
    property_path="/hotel-deals/" in path and ("/h" in path or "/relax/" in path)
    has_room=any(item in found for item in ('[class*="room" i]','[data-testid*="room" i]'))
    has_price=any(item in found for item in ('[class*="price" i]','[data-testid*="price" i]'))
    return bool(property_path and "h1" in found and has_room and has_price),", ".join(found[:8])


async def priceline_quote_candidates(page, stay: dict) -> list[dict]:
    rows=await page.evaluate(r"""() => {
      const clean=(value) => String(value || '').replace(/\s+/g,' ').trim();
      const visible=(el) => {
        if (!el) return false;
        const st=getComputedStyle(el);
        if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
        if ((st.textDecorationLine || '').includes('line-through')) return false;
        const r=el.getBoundingClientRect();
        return r.width>0 && r.height>0;
      };
      const cards=Array.from(document.querySelectorAll(
        '[data-testid*="room" i], [class*="room-card" i], [class*="room-option" i], ' +
        '[class*="room-item" i], section, article'
      )).slice(0,180);
      const out=[]; const seen=new Set();
      for (const card of cards) {
        if (!visible(card)) continue;
        const text=clean(card.innerText || card.textContent);
        if (!text || text.length<20 || text.length>3200) continue;
        let room='';
        for (const selector of ['[data-testid*="room-name" i]','[class*="room-name" i]','[class*="room-title" i]','h2','h3','h4']) {
          const node=card.querySelector(selector);
          const value=clean(node?.textContent);
          if (!value) continue;
          if ((selector==='h2'||selector==='h3'||selector==='h4') &&
              !/\b(room|camera|suite|apartment|appartamento|studio|double|twin|family|king|queen|deluxe|superior)\b/i.test(value)) continue;
          room=value.slice(0,240); break;
        }
        if (!room) continue;
        let price='';
        for (const selector of ['[data-testid*="price" i]','[class*="price" i]']) {
          const matches=Array.from(card.querySelectorAll(selector)).filter(visible);
          const candidate=clean(matches[0]?.textContent);
          if (candidate && /(€|eur)\s*[0-9]|[0-9]\s*(€|eur)/i.test(candidate)) {
            price=candidate.slice(0,180); break;
          }
        }
        if (!price) {
          const match=text.match(/(?:€|EUR)\s*[0-9]{1,5}(?:[.,][0-9]{2})?|[0-9]{1,5}(?:[.,][0-9]{2})?\s*(?:€|EUR)/i);
          price=clean(match?.[0]);
        }
        if (!price) continue;
        const low=text.toLowerCase();
        let basis='';
        if (/(total|totale|for the stay|per stay|soggiorno|for \d+ nights?|per \d+ notti?)/i.test(low)) basis='stay-total';
        else if (/(per night|\/night|a notte|per notte|nightly)/i.test(low)) basis='nightly';
        if (!basis) continue;
        const key=(room+'|'+price+'|'+basis+'|'+text.slice(0,900)).toLowerCase();
        if (seen.has(key)) continue;
        seen.add(key);
        out.push({room,price,text:text.slice(0,2600),basis});
      }
      return out.slice(0,100);
    }""")

    out=[]
    for row in rows:
        room=str(row.get("room") or "").strip()
        price=_money_value(str(row.get("price") or ""))
        text=str(row.get("text") or "").strip()
        basis=str(row.get("basis") or "")
        if not room or price is None or not basis:
            continue
        total=price*int(stay["nights"]) if basis=="nightly" else price
        low=text.lower()
        board=(
            "Colazione inclusa" if any(token in low for token in ("free breakfast","breakfast included","colazione inclusa"))
            else "Solo pernottamento" if any(token in low for token in ("room only","solo pernottamento"))
            else "Trattamento da verificare"
        )
        refund=(
            "Cancellazione gratuita" if any(token in low for token in ("free cancellation","fully refundable","cancellazione gratuita"))
            else "Non rimborsabile" if any(token in low for token in ("non-refundable","non refundable","non rimborsabile"))
            else "Cancellazione da verificare"
        )
        if any(token in low for token in ("vip member","member price","member rate","members save","sign in","app price","mobile app price")):
            continue
        audience="Pubblico senza login"
        taxes=(
            "Tasse e commissioni indicate come incluse"
            if any(token in low for token in ("taxes included","taxes and fees included","tasse incluse"))
            else "Tasse indicate come escluse"
            if any(token in low for token in ("taxes excluded","excluding taxes","before taxes","tasse escluse"))
            else "Da verificare nel dettaglio del preventivo"
        )
        plan_parts=[]
        if refund!="Cancellazione da verificare": plan_parts.append(refund)
        if board!="Trattamento da verificare": plan_parts.append(board)
        if audience!="Pubblico senza login": plan_parts.append("VIP/member")
        rate_plan=" · ".join(dict.fromkeys(plan_parts)) or "Piano tariffario da verificare"
        basis_note=(
            f"Prezzo per notte visibile (€{price:.2f}) × {stay['nights']} notti = €{total:.2f}. "
            if basis=="nightly"
            else "Totale soggiorno indicato nel blocco camera. "
        )
        out.append({
            "roomType":room,
            "ratePlan":rate_plan,
            "total":round(total,2),
            "currency":"EUR",
            "nights":stay["nights"],
            "guests":stay["adults"],
            "board":board,
            "refund":refund,
            "audience":audience,
            "taxes":taxes,
            "verified":True,
            "evidence":(basis_note+text)[:1100],
        })
    unique=[]; seen=set()
    for item in out:
        key=(item["roomType"].lower(),item.get("ratePlan","").lower(),item["total"])
        if key in seen: continue
        seen.add(key); unique.append(item)
    return unique[:40]



def _localized_number(value: str) -> float | None:
    raw=str(value or "").strip().replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw=raw.replace(".","").replace(",",".")
        else:
            raw=raw.replace(",","")
    elif "," in raw:
        raw=raw.replace(",",".")
    try:
        return float(raw)
    except ValueError:
        return None


def _profile_rating(body: str) -> tuple[float | None,float | None]:
    text=re.sub(r"\s+"," ",body or "")
    patterns=(
        r'(\d{1,2}(?:[.,]\d+)?)\s*(?:/|su|von|of)\s*(5|6|10)\b',
        r'(?:rating|valutazione|bewertung|punteggio|score)\D{0,25}(\d{1,2}(?:[.,]\d+)?)\s*(?:/|su|von|of)?\s*(5|6|10)?',
    )
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if not match:
            continue
        value=_localized_number(match.group(1))
        scale=_localized_number(match.group(2) or "") if len(match.groups())>1 else None
        if value is None:
            continue
        if scale is None:
            if 0 <= value <= 5:
                scale=5.0
            elif value <= 6:
                scale=6.0
            elif value <= 10:
                scale=10.0
        if scale and 0 <= value <= scale:
            return round(value,2),scale
    return None,None


def _profile_review_count(body: str) -> int | None:
    text=re.sub(r"\s+"," ",body or "")
    patterns=(
        r'([0-9][0-9.,\s]{0,12})\s+(?:verified\s+)?(?:reviews?|recensioni|bewertungen|bewertung|opinioni)\b',
        r'(?:reviews?|recensioni|bewertungen|bewertung|opinioni)\D{0,20}([0-9][0-9.,\s]{0,12})',
    )
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if not match:
            continue
        digits=re.sub(r"\D","",match.group(1))
        if digits:
            try:
                value=int(digits)
                if 0 < value < 10_000_000:
                    return value
            except ValueError:
                pass
    return None


def _profile_recommendation(body: str) -> float | None:
    text=re.sub(r"\s+"," ",body or "")
    patterns=(
        r'(\d{1,3}(?:[.,]\d+)?)\s*%\s*(?:recommend|weiterempfehl|consigl)',
        r'(?:recommend|weiterempfehl|consigl)[^%]{0,40}(\d{1,3}(?:[.,]\d+)?)\s*%',
    )
    for pattern in patterns:
        match=re.search(pattern,text,re.I)
        if match:
            value=_localized_number(match.group(1))
            if value is not None and 0 <= value <= 100:
                return round(value,1)
    return None



def ota_auth_wall(url: str, title: str = "", body: str = "") -> str:
    """Riconosce redirect verso login/account che non sono pagine tariffarie pubbliche."""
    try:
        parsed=urlparse(url)
        path=(parsed.path or "").lower()
    except Exception:
        path=""
    text=(str(title or "")+" "+str(body or "")[:1800]).lower()
    path_tokens=(
        "/account/signin","/account/login","/signin","/sign-in","/login","/register",
        "/member/login","/user/login","/auth/",
    )
    if any(token in path for token in path_tokens):
        return "redirect alla pagina login/account"
    if (
        any(token in text for token in ("sign in/register","please enter an email address","continue with google","accedi o registrati"))
        and not any(token in text for token in ("camera","room","prezzo","price","availability","disponibil"))
    ):
        return "pagina login/account rilevata dal contenuto"
    return ""


def _commercial_ota_from_host(host: str) -> str:
    normalized=str(host or "").lower().removeprefix("www.")
    for ota_id,meta in OTA_META.items():
        if ota_id in PROFILE_AUDIT_CHANNELS:
            continue
        if any(normalized==domain or normalized.endswith("."+domain) for domain in meta["domains"]):
            return ota_id
    return ""


async def apply_metasearch_assist(
    context,
    data: dict,
    result: dict,
    sources: dict,
    robots: dict,
    unverified_source_ids: set[str] | None = None,
) -> list[dict]:
    """Usa link commerciali dei metasearch come scorciatoie, ma sempre con identity lock."""
    candidates=[]
    seen=set()
    for profile_id,profile in (result.get("otaProfiles") or {}).items():
        for item in (profile.get("commercialLinks") or []):
            url=str(item.get("url") or "").strip()
            ota_id=str(item.get("otaId") or "") or _commercial_ota_from_host(str(item.get("host") or ""))
            if not url or not ota_id or ota_id in PROFILE_AUDIT_CHANNELS:
                continue
            key=(ota_id,_clean_listing_url(url))
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "otaId":ota_id,
                "url":url,
                "text":str(item.get("text") or "")[:220],
                "via":profile_id,
            })

    accepted=[]
    for candidate in candidates[:40]:
        ota_id=candidate["otaId"]
        if (sources.get(ota_id) or {}).get("url") and ota_id not in (unverified_source_ids or set()):
            continue
        verification=await verify_ota_candidate_page(
            context,
            ota_id,
            candidate["url"],
            data.get("name",""),
            data.get("city",""),
            data.get("address",""),
            robots,
        )
        if not verification.get("ok"):
            continue
        final_url=verification.get("url") or candidate["url"]
        sources[ota_id]={"label":OTA_META[ota_id]["label"],"url":final_url}
        if unverified_source_ids is not None:
            unverified_source_ids.discard(ota_id)
        result.setdefault("discoveredSources",{})[ota_id]={
            "status":"found",
            "url":final_url,
            "title":verification.get("title") or candidate.get("text") or "",
            "score":verification.get("score",1.0),
            "identityVerified":True,
            "verification":"page_identity_lock",
            "discoveryMode":"metasearch assist + strict identity verification",
            "evidence":(
                f"{OTA_META[ota_id]['label']} raggiunta tramite link commerciale presente su "
                f"{OTA_META.get(candidate['via'],{}).get('label',candidate['via'])}; "
                f"identità verificata direttamente: {verification.get('evidence','')}."
            )[:900],
        }
        accepted.append({
            "otaId":ota_id,
            "url":final_url,
            "via":candidate["via"],
            "evidence":verification.get("evidence",""),
        })
        print(
            f"metasearch assist: {ota_id} accettata via {candidate['via']} · "
            f"{str(verification.get('evidence') or '')[:220]}",
            flush=True,
        )
    return accepted


async def observe_ota_profile(context, ota_id: str, source: str, robots: dict) -> dict:
    """Profilo pubblico per metasearch/review portals: identità, reputazione e link commerciali."""
    permission=await asyncio.to_thread(allowed_by_robots,source,robots)
    if permission is not True:
        return {
            "status":"robots_denied" if permission is False else "robots_unavailable",
            "url":source,"title":"","rating":None,"ratingScale":None,"reviewCount":None,
            "recommendationRate":None,"visiblePrices":[],"outboundHosts":[],
            "evidence":"Profilo non letto: robots.txt nega o non chiarisce l'accesso automatico."
        }
    page=await context.new_page()
    try:
        response=await page.goto(source,wait_until="domcontentloaded",timeout=25000)
        if not response:
            return {"status":"navigation_error","url":source,"evidence":"Nessuna risposta HTTP dalla scheda."}
        if response.status==429:
            return {"status":"rate_limited","url":page.url,"evidence":"HTTP 429: portale temporaneamente limitato."}
        if response.status>=400:
            return {"status":"http_error","url":page.url,"evidence":f"HTTP {response.status} sulla scheda pubblica."}
        await dismiss_cookie(page)
        await page.wait_for_timeout(1400)
        body=(await page.locator("body").inner_text(timeout=7000))[:24000]
        title=(await page.title())[:240]
        try:
            h1=page.locator("h1").first
            if await h1.count() and await h1.is_visible(timeout=300):
                h1_text=re.sub(r"\s+"," ",(await h1.inner_text(timeout=600)) or "").strip()
                if h1_text:
                    title=h1_text[:240]
        except Exception:
            pass
        low=(title+" "+body).lower()
        if any(word in low for word in BLOCK_WORDS):
            return {
                "status":"blocked","url":page.url,"title":title,
                "evidence":"Il portale ha mostrato una verifica/blocco; nessun aggiramento tentato."
            }

        rating,scale=_profile_rating(body)
        review_count=_profile_review_count(body)
        recommendation=_profile_recommendation(body)

        visible_prices=[]
        seen_prices=set()
        for match in PRICE_RE.finditer(body):
            raw=match.group(0)
            value=_money_value(raw)
            if value is None or value in seen_prices:
                continue
            seen_prices.add(value)
            visible_prices.append({"amount":round(value,2),"currency":"EUR","text":raw[:80]})
            if len(visible_prices)>=8:
                break

        own_domains=tuple(OTA_META.get(ota_id,{}).get("domains") or ())
        try:
            outbound_links=await page.evaluate(r"""(ownDomains) => {
              const out=[]; const seen=new Set();
              for (const a of Array.from(document.querySelectorAll('a[href]')).slice(0,900)) {
                try {
                  const u=new URL(a.href,location.href);
                  const host=u.hostname.toLowerCase().replace(/^www\./,'');
                  if (!host || ownDomains.some(d => host===d || host.endsWith('.'+d))) continue;
                  if (!/^https?:$/.test(u.protocol)) continue;
                  const url=u.href.split('#')[0];
                  const key=host+'|'+url;
                  if (seen.has(key)) continue;
                  seen.add(key);
                  out.push({
                    host,
                    url,
                    text:String(a.innerText || a.textContent || a.getAttribute('aria-label') || '').replace(/\s+/g,' ').trim().slice(0,220)
                  });
                } catch {}
              }
              return out.slice(0,80);
            }""",list(own_domains))
        except Exception:
            outbound_links=[]

        outbound=[]
        for item in outbound_links:
            host=str(item.get("host") or "")
            if host and host not in outbound:
                outbound.append(host)

        commercial_links=[]
        for item in outbound_links:
            host=str(item.get("host") or "")
            linked_ota=_commercial_ota_from_host(host)
            if linked_ota:
                commercial_links.append({
                    "host":host,
                    "url":str(item.get("url") or ""),
                    "text":str(item.get("text") or "")[:220],
                    "otaId":linked_ota,
                })
        commercial_hosts=[]
        for item in commercial_links:
            host=item["host"]
            if host not in commercial_hosts:
                commercial_hosts.append(host)

        evidence_parts=[]
        if rating is not None:
            evidence_parts.append(f"rating {rating:g}/{scale:g}")
        if review_count:
            evidence_parts.append(f"{review_count} recensioni")
        if recommendation is not None:
            evidence_parts.append(f"raccomandazione {recommendation:g}%")
        if visible_prices:
            evidence_parts.append(f"{len(visible_prices)} prezzi EUR visibili non attribuiti a una camera")
        if commercial_hosts:
            evidence_parts.append("link commerciali: "+", ".join(commercial_hosts[:8]))
        if not evidence_parts:
            evidence_parts.append("scheda leggibile, ma metriche strutturate non riconosciute con sufficiente certezza")

        return {
            "status":"sampled",
            "url":urlunparse(urlparse(page.url)._replace(fragment="")),
            "title":title,
            "rating":rating,
            "ratingScale":scale,
            "reviewCount":review_count,
            "recommendationRate":recommendation,
            "visiblePrices":visible_prices,
            "outboundHosts":outbound,
            "commercialHosts":commercial_hosts,
            "commercialLinks":commercial_links[:30],
            "visibleExcerpt":re.sub(r"\s+"," ",body)[:700],
            "evidence":" · ".join(evidence_parts)[:1000],
        }
    except Exception as exc:
        return {
            "status":"navigation_error","url":source,
            "evidence":f"{type(exc).__name__}: {str(exc)[:180]}"
        }
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def generic_ota_quote_candidates(page, stay: dict) -> list[dict]:
    """Fallback frontend: usa importi visibili con base esplicita; valida solo se identifica anche l'unità."""
    rows=await page.evaluate(r"""() => {
      const selectors=[
        '[data-testid*="price"]','[class*="price"]','[data-stid*="price"]',
        '[data-testid*="room"]','[class*="room"]'
      ];
      const result=[]; const seen=new Set();
      for (const selector of selectors) {
        for (const node of Array.from(document.querySelectorAll(selector)).slice(0,180)) {
          const container=node.closest('article,li,tr,section,[data-testid*="room"],[class*="room"],div') || node;
          const text=(container.innerText || container.textContent || '').replace(/\s+/g,' ').trim();
          if (!text || text.length<8 || text.length>2400 || seen.has(text)) continue;
          const low=text.toLowerCase();
          if (!/(a notte|per notte|per night|nightly|totale soggiorno|prezzo totale|stay total|total for|per stay|per \d+ notti|for \d+ nights)/i.test(low)) continue;
          let room='';
          for(const sel of ['h2','h3','h4','[data-testid*="room-name"]','[data-stid*="room-name"]','[class*="room-name" i]']){
            const h=container.querySelector(sel); const v=(h?.textContent||'').replace(/\s+/g,' ').trim();
            if(v&&v.length<260){room=v;break}
          }
          seen.add(text); result.push({text,room});
        }
      }
      return result.slice(0,100);
    }""")
    out=[]
    for row in rows:
        text=str((row or {}).get("text") or "")
        room=str((row or {}).get("room") or "").strip()
        low=text.lower()
        if re.search(r"\b(a notte|per notte|per night|nightly)\b",low,re.I):
            basis="nightly"
        elif re.search(r"\b(totale soggiorno|prezzo totale|stay total|total for|per stay|per \d+ notti|for \d+ nights)\b",low,re.I):
            basis="stay-total"
        else:
            continue
        amount=_money_value(text)
        if amount is None:
            continue
        fields=_price_fields(amount,basis,stay)
        refund=(
            "Cancellazione gratuita" if any(x in low for x in ("cancellazione gratuita","free cancellation","fully refundable"))
            else "Non rimborsabile" if any(x in low for x in ("non rimborsabile","non-refundable","non refundable"))
            else "Cancellazione da verificare"
        )
        board="Colazione inclusa" if any(x in low for x in ("colazione inclusa","breakfast included")) else "Trattamento da verificare"
        out.append({
            "roomType":room or "Tipologia camera da verificare",
            **fields,
            "currency":"EUR","nights":stay["nights"],"guests":stay["adults"],
            "board":board,"refund":refund,
            "audience":"Pubblico senza login","taxes":"Da verificare nel dettaglio del preventivo",
            "verified":bool(room),
            "evidence":(fields["priceDerivation"]+" Contesto: "+text[:900])[:1200],
        })
    unique=[]; seen=set()
    for item in out:
        key=(item["displayedAmount"],item["displayedBasis"],item["evidence"][:180])
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
    """Raccoglie camera, piano e prezzo dalla scheda Booking con date già confermate."""
    rows = await page.evaluate(r"""() => {
      const result = [];
      const seen = new Set();
      const clean = (value) => String(value || '').replace(/\s+/g,' ').trim();

      const primaryPriceSelectors = [
        '[data-testid="price-and-discounted-price"]',
        '[data-testid="price-for-x-nights"]',
        '.bui-price-display__value',
        '.prco-valign-middle-helper'
      ];
      const visible=(el) => {
        if (!el) return false;
        const st=getComputedStyle(el);
        if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity||'1')===0) return false;
        if (st.textDecorationLine && st.textDecorationLine.includes('line-through')) return false;
        const r=el.getBoundingClientRect();
        return r.width>0 && r.height>0;
      };
      const pickPrice=(node) => {
        if (!node) return null;
        for (const selector of primaryPriceSelectors) {
          const found=Array.from(node.querySelectorAll(selector)).filter(visible);
          if (found.length) return found[0];
        }
        return null;
      };

      const explicitRoom = (node) => {
        if (!node) return '';
        const direct=node.querySelector(
          '.hprt-roomtype-link, [data-testid="room-name"], [data-testid*="room-name"]'
        );
        if (direct) return clean(direct.textContent).slice(0,240);
        const heading=node.querySelector('h2,h3,h4');
        const headingText=clean(heading?.textContent);
        if (/\b(camera|room|suite|appartamento|apartment|monolocale|studio|matrimoniale|tripla|quadrupla|singola|double|triple|family)\b/i.test(headingText)) {
          return headingText.slice(0,240);
        }
        return '';
      };

      const add = (node, priceNode = null, inheritedRoom = '') => {
        if (!node) return;
        const text = clean(node.innerText || node.textContent);
        if (!text || text.length < 10) return;
        const ownPrice = priceNode || pickPrice(node);
        const priceText = clean(ownPrice?.textContent).slice(0,180);
        if (!priceText) return;
        const room = explicitRoom(node) || clean(inheritedRoom).slice(0,240);
        const dedupeKey=(room+'|'+priceText+'|'+text.slice(0,700)).toLowerCase();
        if (seen.has(dedupeKey)) return;
        seen.add(dedupeKey);
        result.push({
          text: text.slice(0,2400),
          room,
          price: priceText,
          priceIsolated: true
        });
      };

      // Layout classico Booking: la cella col nome camera può avere rowspan,
      // quindi le righe tariffarie successive ereditano la stessa camera.
      for (const tableSelector of ['#hprt-table tbody tr','#hprt-form tbody tr']) {
        let currentRoom='';
        for (const row of Array.from(document.querySelectorAll(tableSelector)).slice(0,120)) {
          const foundRoom=explicitRoom(row);
          if (foundRoom) currentRoom=foundRoom;
          const priceNode=pickPrice(row);
          add(row,priceNode,currentRoom);
        }
      }

      // Layout moderno a card.
      const cards=Array.from(document.querySelectorAll(
        '[data-testid="room-card"], [data-testid*="room-card"], [data-testid="room-list"] > *, ' +
        '[data-testid="availability-block"], [data-testid*="availability"]'
      )).slice(0,100);
      for (const card of cards) {
        const room=explicitRoom(card);
        const priceNode=pickPrice(card);
        if (priceNode) {
          const container=priceNode.closest(
            'tr, [data-testid="room-card"], [data-testid*="room-card"], ' +
            '[data-testid="availability-block"], [data-testid*="room"]'
          ) || card;
          add(container,priceNode,room);
        } else {
          add(card,null,room);
        }
      }

      return result.slice(0,140);
    }""")

    out = []
    for row in rows:
        text = str(row.get("text", ""))
        room = str(row.get("room", "")).strip() or "Tipologia camera da verificare"
        price_text = str(row.get("price", "")).strip()
        total = _money_value(price_text)
        if total is None:
            continue

        low = text.lower()
        board = "Colazione inclusa" if any(x in low for x in (
            "colazione inclusa", "breakfast included", "colazione compresa"
        )) else "Trattamento da verificare"

        if any(x in low for x in ("cancellazione gratuita", "free cancellation")):
            refund = "Cancellazione gratuita"
        elif any(x in low for x in ("parzialmente rimborsabile", "partially refundable")):
            refund = "Parzialmente rimborsabile"
        elif any(x in low for x in ("non rimborsabile", "non-refundable", "non refundable")):
            refund = "Non rimborsabile"
        else:
            refund = "Cancellazione da verificare"

        plan_parts=[]
        if refund != "Cancellazione da verificare":
            plan_parts.append(refund)
        if board != "Trattamento da verificare":
            plan_parts.append(board)
        if any(x in low for x in ("paga in anticipo", "pay in advance", "pagamento anticipato")):
            plan_parts.append("Pagamento anticipato")
        if any(x in low for x in ("genius", "mobile rate", "tariffa mobile")):
            plan_parts.append("Promozione visibile")
        rate_plan=" · ".join(dict.fromkeys(plan_parts)) or "Piano tariffario da verificare"

        # Questa funzione viene chiamata soltanto sulla scheda Booking esatta
        # con le date già confermate. Un nodo prezzo isolato + una camera
        # identificata è sufficiente per considerare la riga letta dal parser;
        # tasse e confrontabilità tra OTA restano comunque separate.
        parser_verified = bool(
            row.get("priceIsolated")
            and room != "Tipologia camera da verificare"
        )

        booking_price_fields=_price_fields(total,"stay-total",stay)
        out.append({
            "roomType": room,
            "ratePlan": rate_plan,
            **booking_price_fields,
            "currency": "EUR",
            "nights": stay["nights"],
            "guests": stay["adults"],
            "board": board,
            "refund": refund,
            "audience": "Pubblico senza login",
            "taxes": "Da verificare nel dettaglio del preventivo",
            "verified": parser_verified,
            "evidence": text[:1100],
        })

    # Deduplica per camera + piano + prezzo.
    unique=[]
    seen=set()
    for item in out:
        key=(
            item["roomType"].lower(),
            item.get("ratePlan","").lower(),
            item["total"],
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:40]


def booking_unavailability_message(text: str) -> str:
    lowered=re.sub(r"\s+", " ", (text or "").lower())
    patterns=(
        "non disponibile per le date selezionate",
        "non disponibile nelle date selezionate",
        "non disponibile sul nostro sito nelle tue date",
        "questa struttura non è disponibile sul nostro sito nelle tue date",
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


def write_result(path: Path, result: dict) -> bool:
    """Salvataggio progressivo resiliente ai lock temporanei di Windows/OneDrive.

    I risultati runtime vengono normalmente salvati fuori dalla cartella OneDrive
    dall'agente locale. Questo retry resta come seconda protezione contro antivirus,
    indicizzazione o altri lock brevi del filesystem.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload=json.dumps(result, ensure_ascii=False, indent=2)
    temporary=path.with_name(f".{path.name}.{os.getpid()}.tmp")
    last_error=None

    for attempt in range(8):
        try:
            temporary.write_text(payload,encoding="utf-8")
            os.replace(str(temporary),str(path))
            return True
        except PermissionError as exc:
            last_error=exc
            time.sleep(0.18*(attempt+1))
        except OSError as exc:
            last_error=exc
            # Condivisione/lock Windows: lascia una breve finestra al processo che
            # sta leggendo o sincronizzando il file; altri errori verranno comunque
            # riprovati e registrati senza interrompere l'intero audit.
            time.sleep(0.12*(attempt+1))

    try:
        if temporary.exists():
            temporary.unlink()
    except OSError:
        pass

    print(
        f"warning: salvataggio progressivo non riuscito dopo retry · "
        f"{path} · {type(last_error).__name__ if last_error else 'OSError'}: {str(last_error)[:180] if last_error else ''}",
        flush=True,
    )
    return False




PUBLIC_MEMBER_TOKENS=(
    "member price","member rate","members save","member only","members only",
    "vip member","vip access","sign in to","sign in for","sign in and save",
    "accedi per","accedi e risparmia","effettua l'accesso","tariffa soci","prezzo soci",
    "logged in","login required","app price","mobile app price","prezzo app",
)


def public_quote_without_login(quote: dict) -> bool:
    """Accetta solo tariffe pubbliche, senza falsi negativi dovuti al testo circostante."""
    audience=str(quote.get("audience") or "").strip().lower()
    rate_plan=str(quote.get("ratePlan") or "").strip().lower()
    evidence=str(quote.get("evidence") or "").strip().lower()
    warning=str(quote.get("comparisonWarning") or "").strip().lower()

    explicit_public=audience in {"pubblico senza login","public without login","pubblico"}
    if audience and not explicit_public:
        return False

    # Se il parser ha già isolato la riga come pubblica, controlla soltanto il piano
    # e gli avvisi della riga. Non usare l'intero evidence: Booking/Agoda possono
    # includere nella stessa porzione DOM banner generici "Accedi/member" non riferiti
    # alla tariffa estratta.
    if explicit_public:
        scoped=" ".join((rate_plan,warning))
        return not any(token in scoped for token in PUBLIC_MEMBER_TOKENS)

    # Se manca un'audience esplicita, resta conservativo.
    combined=" ".join((rate_plan,evidence,warning))
    return not any(token in combined for token in PUBLIC_MEMBER_TOKENS)


def normalize_quote_price_fields(quote: dict) -> dict:
    """Garantisce sempre €/notte + totale, preservando quale valore mostrava il portale."""
    try:
        nights=max(1,int(quote.get("nights") or 1))
        total=float(quote.get("total"))
    except Exception:
        return quote

    nightly=quote.get("nightlyRate")
    try:
        nightly=float(nightly) if nightly is not None else total/nights
    except Exception:
        nightly=total/nights

    evidence=str(quote.get("evidence") or "")
    low=evidence.lower()
    basis=str(quote.get("displayedBasis") or "").strip()
    if basis not in {"nightly","stay-total"}:
        if any(token in low for token in ("prezzo per notte visibile","mostrati a notte"," a notte","per notte","per night","nightly")):
            basis="nightly"
        elif any(token in low for token in ("totale soggiorno","totale mostrato","stay total","total for","per stay")):
            basis="stay-total"
        else:
            basis="unknown"

    displayed=quote.get("displayedAmount")
    try:
        displayed=float(displayed) if displayed is not None else None
    except Exception:
        displayed=None
    if displayed is None:
        if basis=="nightly":
            displayed=nightly
        elif basis=="stay-total":
            displayed=total

    quote["total"]=round(total,2)
    quote["nightlyRate"]=round(nightly,2)
    quote["displayedBasis"]=basis
    if displayed is not None:
        quote["displayedAmount"]=round(displayed,2)

    if not quote.get("priceDerivation"):
        if basis=="nightly" and displayed is not None:
            quote["priceDerivation"]=(
                f"Portale: €{displayed:.2f}/notte · totale calcolato: "
                f"€{displayed:.2f} × {nights} = €{total:.2f}."
            )
        elif basis=="stay-total" and displayed is not None:
            quote["priceDerivation"]=(
                f"Portale: €{displayed:.2f} totale · prezzo/notte calcolato: "
                f"€{displayed:.2f} ÷ {nights} = €{nightly:.2f}."
            )
        else:
            quote["priceDerivation"]=(
                f"Totale registrato €{total:.2f} su {nights} notti · "
                f"equivalente €{nightly:.2f}/notte; base mostrata dal portale non confermata."
            )
    return quote


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


def booking_exact_results_dated_url(current_url: str, stay: dict) -> str:
    """Mantiene il blocco destinazione Booking esattamente come il portale lo genera.

    Per alcune destinazioni Booking usa una query non standard:
    dest_id=...;dest_type=latlong;latitude=...;longitude=...
    I punti e virgola fanno parte del blocco destinazione atteso dal portale.
    Non vanno trasformati in '&' né percent-encoded. Le date invece vengono
    aggiunte come normali parametri '&checkin=...&checkout=...'.
    """
    parsed=urlparse(current_url)
    if "/searchresults" not in parsed.path:
        return ""

    raw_query=parsed.query or ""
    if not raw_query:
        return ""

    # Preferisci il blocco destinazione osservato direttamente dopo la
    # selezione autocomplete. Include i ';' così come Booking li ha emessi.
    destination_blob=""
    match=re.search(
        r"(dest_id=[^&]+(?:;dest_type=[^&;]+)?(?:;latitude=[^&;]+)?(?:;longitude=[^&;]+)?)",
        raw_query,
        flags=re.I,
    )
    if match:
        destination_blob=match.group(1)
    else:
        # Fallback conservativo per eventuali searchresults con ss=...
        pairs=parse_qsl(raw_query,keep_blank_values=True)
        query=dict(pairs)
        if query.get("ss"):
            destination_blob=urlencode({"ss":query["ss"]})
        elif query.get("dest_id"):
            destination_blob=urlencode({
                key:query[key] for key in ("dest_id","dest_type","latitude","longitude")
                if query.get(key)
            })

    if not destination_blob:
        return ""

    date_query=urlencode({
        "checkin":stay["checkin"],
        "checkout":stay["checkout"],
        "group_adults":str(stay.get("adults") or 2),
        "no_rooms":"1",
        "group_children":"0",
        "selected_currency":"EUR",
        "lang":"it-it",
    })
    base=urlunparse(parsed._replace(query="",fragment=""))
    return f"{base}?{destination_blob}&{date_query}"



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


async def booking_select_exact_destination(page, property_name: str, city: str) -> tuple[bool, str, str]:
    """Prova a selezionare la struttura dal suggeritore destinazione di Booking."""
    field, selector = await _first_visible_locator(page, (
        'input[name="ss"]',
        '[data-testid="destination-container"] input',
        'input[placeholder*="destinazione" i]',
        'input[placeholder*="destination" i]',
    ))
    if field is None:
        return False, "campo destinazione Booking non trovato", ""

    input_method=""
    first_error=""
    try:
        try:
            await field.scroll_into_view_if_needed(timeout=1200)
        except Exception:
            pass
        await field.click(timeout=2200)
        await field.fill(property_name,timeout=2600)
        input_method="click+fill"
    except Exception as exc:
        first_error=type(exc).__name__
        # Sulla home Booking il campo può risultare visibile ma essere coperto
        # da un layer/animazione. Riprova con focus + tastiera, più vicino al
        # comportamento di un utente reale.
        try:
            try:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(250)
            except Exception:
                pass
            try:
                await field.click(timeout=1600,force=True)
            except Exception:
                await field.focus(timeout=1600)
            try:
                await field.press("Control+A",timeout=1200)
                await field.press("Backspace",timeout=1200)
            except Exception:
                pass
            await field.type(property_name,delay=55,timeout=6000)
            input_method="focus+type"
        except Exception as exc2:
            # Ultimo tentativo: apri il contenitore destinazione e recupera
            # nuovamente l'input, perché Booking può sostituirlo durante l'hydration.
            try:
                container, _ = await _first_visible_locator(page,(
                    '[data-testid="destination-container"]',
                    '[data-testid="destination-container"] button',
                ))
                if container is not None:
                    await container.click(timeout=1800,force=True)
                    await page.wait_for_timeout(350)
                field2, selector2 = await _first_visible_locator(page,(
                    'input[name="ss"]',
                    '[data-testid="destination-container"] input',
                    'input[placeholder*="destinazione" i]',
                    'input[placeholder*="destination" i]',
                ))
                if field2 is None:
                    raise RuntimeError("destination input missing after reopen")
                try:
                    await field2.fill(property_name,timeout=3000)
                    input_method=f"reopen+fill ({selector2})"
                except Exception:
                    await field2.focus(timeout=1600)
                    await field2.press("Control+A",timeout=1200)
                    await field2.type(property_name,delay=60,timeout=6000)
                    input_method=f"reopen+type ({selector2})"
                field=field2
            except Exception as exc3:
                return False, (
                    f"campo destinazione non compilabile: {first_error or type(exc).__name__} "
                    f"→ {type(exc2).__name__} → {type(exc3).__name__}"
                ), ""

    await page.wait_for_timeout(1100)

    options=[]
    selectors=(
        '[data-testid="autocomplete-result"]',
        '[data-testid="autocomplete-results"] li',
        '[role="option"]',
        'li[data-i]',
    )
    for opt_selector in selectors:
        try:
            locs=page.locator(opt_selector)
            count=min(await locs.count(),30)
            for idx in range(count):
                loc=locs.nth(idx)
                try:
                    if not await loc.is_visible(timeout=180):
                        continue
                    txt=re.sub(r"\s+"," ",(await loc.inner_text(timeout=500)) or "").strip()
                    if txt:
                        options.append((loc,txt,opt_selector))
                except Exception:
                    continue
        except Exception:
            pass
        if options:
            break

    if not options:
        # Booking home può accettare .fill() ma non attivare il suggeritore.
        # Riprova con veri eventi tastiera, carattere per carattere.
        try:
            try:
                await field.click(timeout=1600,force=True)
            except Exception:
                await field.focus(timeout=1600)
            try:
                await field.press("Control+A",timeout=1000)
                await field.press("Backspace",timeout=1000)
            except Exception:
                pass
            await field.type(property_name,delay=85,timeout=8000)
            input_method=(input_method+"→keyboard-retry").strip("→")
            await page.wait_for_timeout(2200)
        except Exception:
            pass

        retry_selectors=(
            '[data-testid="autocomplete-result"]',
            '[data-testid="autocomplete-results"] li',
            '[data-testid*="autocomplete"] [role="option"]',
            '[data-testid*="autocomplete"] li',
            '[role="listbox"] [role="option"]',
            '[role="option"]',
            'li[data-i]',
        )
        for opt_selector in retry_selectors:
            try:
                locs=page.locator(opt_selector)
                count=min(await locs.count(),40)
                for idx in range(count):
                    loc=locs.nth(idx)
                    try:
                        if not await loc.is_visible(timeout=220):
                            continue
                        txt=re.sub(r"\s+"," ",(await loc.inner_text(timeout=600)) or "").strip()
                        if txt:
                            options.append((loc,txt,opt_selector))
                    except Exception:
                        continue
            except Exception:
                pass
            if options:
                break

    if not options:
        try:
            current_value=await field.input_value(timeout=1000)
        except Exception:
            current_value=""
        return False,(
            f"nessun suggerimento destinazione visibile; "
            f"input={input_method or 'n.d.'}; valore=«{current_value[:100]}»"
        ), ""

    ranked=[]
    for loc,txt,opt_selector in options:
        score=_name_similarity(property_name,txt)
        low=txt.lower()
        if city and city.lower() in low:
            score=min(1.0,score+0.12)
        ranked.append((score,loc,txt,opt_selector))
    ranked.sort(key=lambda item:item[0],reverse=True)
    score,loc,txt,opt_selector=ranked[0]
    if score < 0.58:
        preview=" | ".join(item[2][:90] for item in ranked[:3])
        return False,f"suggerimenti trovati ma nessun match sicuro; migliori: {preview[:280]}",""

    try:
        await loc.click(timeout=2200)
        await page.wait_for_timeout(900)
        return True,(
            f"selezionato suggerimento «{txt[:140]}» (match {score:.0%}) con {opt_selector}; "
            f"input={input_method or 'n.d.'}"
        ),txt[:300]
    except Exception as exc:
        return False,f"suggerimento esatto trovato ma non cliccabile: {type(exc).__name__}",""


async def booking_search_form_diagnostics(page) -> str:
    """Raccoglie solo i campi ricerca Booking utili a capire cosa verrà inviato."""
    try:
        data=await page.evaluate(r"""() => {
          const submit=document.querySelector(
            '[data-testid="searchbox-submit-button"], [data-testid="searchbox-layout-wide"] button[type="submit"], form[role="search"] button[type="submit"]'
          );
          const form=submit?.closest('form') || document.querySelector('form[role="search"], form[action*="searchresults"]');
          const names=[
            'ss','dest_id','dest_type','latitude','longitude',
            'checkin','checkout',
            'checkin_year','checkin_month','checkin_monthday',
            'checkout_year','checkout_month','checkout_monthday',
            'group_adults','no_rooms','group_children'
          ];
          const values={};
          for (const name of names) {
            const nodes=Array.from((form || document).querySelectorAll('[name="'+name+'"]')).slice(0,8);
            if (!nodes.length) continue;
            values[name]=nodes.map(el => ({
              value: String(el.value ?? el.getAttribute('value') ?? '').slice(0,120),
              type: String(el.type || '').slice(0,30),
              disabled: !!el.disabled
            }));
          }
          return {
            action: form ? String(form.action || form.getAttribute('action') || '').slice(0,220) : '',
            method: form ? String(form.method || '').slice(0,20) : '',
            values
          };
        }""")
        compact=[]
        for key,items in (data.get("values") or {}).items():
            vals="|".join(
                str(item.get("value") or "") + ("[disabled]" if item.get("disabled") else "")
                for item in items
            )
            compact.append(f"{key}={vals[:180]}")
        return (
            f"action={data.get('action') or 'n.d.'} · method={data.get('method') or 'n.d.'} · "
            + " · ".join(compact)
        )[:1400]
    except Exception as exc:
        return f"diagnostica form fallita: {type(exc).__name__}"


async def booking_clean_ui_search(page, source: str, property_name: str, canonical_name: str, city: str, stay: dict, robots: dict) -> dict:
    """Riproduce il flusso utente pulito: Booking home -> destinazione -> date -> Cerca."""
    home="https://www.booking.com/index.it.html?lang=it-it&selected_currency=EUR"
    permission=await asyncio.to_thread(allowed_by_robots,home,robots)
    if permission is not True:
        return {"ok":False,"label":"Booking home UI","reason":"robots","evidence":"Booking home: robots.txt non consente o non chiarisce l'accesso."}

    try:
        response=await page.goto(home,wait_until="domcontentloaded",timeout=25000)
        await dismiss_cookie(page)
        try:
            await page.locator("body").wait_for(state="visible",timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(1800)
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(250)
        except Exception:
            pass

        if response and response.status==429:
            return {"ok":False,"label":"Booking home UI","reason":"rate_limited","status":"rate_limited","evidence":"Booking home UI: HTTP 429."}
        if response and response.status>=400:
            return {"ok":False,"label":"Booking home UI","reason":"http_error","status":"http_error","evidence":f"Booking home UI: HTTP {response.status}."}

        dest_ok,dest_evidence,dest_text=await booking_select_exact_destination(
            page,canonical_name or property_name,city
        )
        print(
            f"{stay['month']} booking-clean-destination-picker: "
            f"{'applied' if dest_ok else 'failed'} · {dest_evidence}",
            flush=True,
        )
        if not dest_ok:
            return {
                "ok":False,"label":"Booking home UI","reason":"destination_not_selected",
                "evidence":f"Booking home UI: destinazione non selezionata. {dest_evidence}"
            }

        # Sequenza intenzionale: PRIMA destinazione, POI date, POI un solo Cerca.
        applied,date_evidence=await booking_apply_dates_via_ui(page,stay)
        print(
            f"{stay['month']} booking-clean-date-picker: "
            f"{'applied' if applied else 'failed'} · {date_evidence}",
            flush=True,
        )
        if not applied:
            form_diag=await booking_search_form_diagnostics(page)
            print(
                f"{stay['month']} booking-clean-form-diagnostics: {form_diag}",
                flush=True,
            )

        try:
            await page.wait_for_timeout(1800)
            title=(await page.title())[:200]
            body=(await page.locator("body").inner_text(timeout=7000))[:16000]
        except Exception:
            title=(await page.title())[:200]
            body=""

        dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
        cards=await booking_result_cards(page)
        best=booking_best_card(cards,source,property_name,canonical_name,city)
        for _ in range(8):
            if best and best[1]:
                break
            await page.wait_for_timeout(650)
            cards=await booking_result_cards(page)
            best=booking_best_card(cards,source,property_name,canonical_name,city)

        best_score=best[0] if best else 0.0
        best_exact=bool(best and best[1])
        best_title=str((best[2] if best else {}).get("title") or "")
        best_price=str((best[2] if best else {}).get("price") or "")

        print(
            f"{stay['month']} booking-clean-ui-search: "
            f"dates={dates_ok} · exact_url={best_exact} · cards={len(cards)} · "
            f"best={best_score:.0%} · title={best_title[:120]} · price={best_price[:80]} · "
            f"url={page.url[:340]}",
            flush=True,
        )

        return {
            "ok":True,
            "label":"Booking home UI",
            "status":"ok",
            "finalUrl":page.url,
            "title":title,
            "body":body,
            "cards":cards,
            "best":best,
            "datesOk":dates_ok,
            "dateMode":date_mode,
            "datePickerEvidence":date_evidence,
            "destinationEvidence":dest_evidence,
            "destinationText":dest_text,
            "evidence":(
                f"Booking home UI: destinazione selezionata prima delle date; "
                f"date {'confermate' if dates_ok else 'non confermate'} ({date_mode or 'n.d.'}); "
                f"scheda esatta {'trovata' if best_exact else 'non trovata'}."
            )[:900],
        }
    except Exception as exc:
        return {
            "ok":False,"label":"Booking home UI","reason":"navigation_error","status":"navigation_error",
            "evidence":f"Booking home UI: {type(exc).__name__}: {str(exc)[:180]}",
        }


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

            destination_evidence=""
            destination_text=""
            if label.startswith("searchresults Booking") and (not best or not best[1]):
                dest_ok,destination_evidence,destination_text=await booking_select_exact_destination(page,canonical_name or property_name,city)
                print(
                    f"{stay['month']} booking-destination-picker [{label}]: "
                    f"{'applied' if dest_ok else 'failed'} · {destination_evidence}",
                    flush=True,
                )
                if dest_ok:
                    # Dopo la scelta della destinazione Booking può mostrare ancora
                    # le date vecchie ma azzerarle internamente al submit. Per evitare
                    # questo falso stato, reimpostiamo SEMPRE le date dopo aver scelto
                    # il suggerimento esatto; l'helper preme già Cerca.
                    applied2,ui_evidence2=await booking_apply_dates_via_ui(page,stay)
                    print(
                        f"{stay['month']} booking-search-date-picker-after-destination [{label}]: "
                        f"{'applied' if applied2 else 'failed'} · {ui_evidence2}",
                        flush=True,
                    )
                    if not applied2:
                        form_diag=await booking_search_form_diagnostics(page)
                        print(
                            f"{stay['month']} booking-search-form-diagnostics [{label}]: {form_diag}",
                            flush=True,
                        )
                    if ui_evidence2:
                        ui_evidence=(ui_evidence+" | "+ui_evidence2).strip(" |")

                    if applied2:
                        try:
                            await page.wait_for_timeout(1400)
                            body=(await page.locator("body").inner_text(timeout=7000))[:14000]
                            dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
                        except Exception:
                            dates_ok=False
                    else:
                        # Fallback: se il date picker non è riapribile ma i campi
                        # risultano già validi, invia comunque la ricerca una volta.
                        try:
                            body=(await page.locator("body").inner_text(timeout=7000))[:14000]
                        except Exception:
                            body=""
                        dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
                        if dates_ok:
                            submit,submit_selector=await _first_visible_locator(page,(
                                '[data-testid="searchbox-submit-button"]',
                                '[data-testid="searchbox-layout-wide"] button[type="submit"]',
                                '[data-testid="searchbox-layout-wide"] button:has-text("Cerca")',
                                '[data-testid="searchbox-layout-wide"] button:has-text("Search")',
                                'form[role="search"] button[type="submit"]',
                                'form[action*="searchresults"] button[type="submit"]',
                            ))
                            if submit is not None:
                                try:
                                    await submit.click(timeout=2400)
                                    try:
                                        await page.wait_for_load_state("domcontentloaded",timeout=9000)
                                    except Exception:
                                        pass
                                    await page.wait_for_timeout(1600)
                                    print(
                                        f"{stay['month']} booking-destination-search-submit [{label}]: "
                                        f"applied · {submit_selector}",
                                        flush=True,
                                    )
                                except Exception as exc:
                                    print(
                                        f"{stay['month']} booking-destination-search-submit [{label}]: "
                                        f"failed · {type(exc).__name__}",
                                        flush=True,
                                    )
                        try:
                            body=(await page.locator("body").inner_text(timeout=7000))[:14000]
                            dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
                        except Exception:
                            pass

                    for _ in range(10):
                        await page.wait_for_timeout(650)
                        cards=await booking_result_cards(page)
                        best=booking_best_card(cards,source,property_name,canonical_name,city)
                        if best and best[1]:
                            break

                    # La destinazione esatta ora è presente nei risultati. Prima di
                    # riaprire il calendario, conserva il contesto destinazione della
                    # searchresults corrente e aggiungi le date direttamente alla sua URL.
                    # Così evitiamo il date picker che Booking rende instabile dopo il submit.
                    if best and best[1] and not dates_ok:
                        exact_results_url=booking_exact_results_dated_url(page.url,stay) or ""
                        if exact_results_url and "/searchresults" in exact_results_url:
                            try:
                                response2=await page.goto(
                                    exact_results_url,
                                    wait_until="domcontentloaded",
                                    timeout=25000,
                                )
                                await dismiss_cookie(page)
                                await page.wait_for_timeout(1800)
                                try:
                                    body=(await page.locator("body").inner_text(timeout=7000))[:14000]
                                except Exception:
                                    body=""
                                dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
                                cards=await booking_result_cards(page)
                                best=booking_best_card(cards,source,property_name,canonical_name,city)
                                print(
                                    f"{stay['month']} booking-exact-results-dated-url [{label}]: "
                                    f"status={getattr(response2,'status',None)} · "
                                    f"dates={dates_ok} · exact_url={bool(best and best[1])} · "
                                    f"url={page.url[:320]} · requested={exact_results_url[:320]}",
                                    flush=True,
                                )
                            except Exception as exc:
                                print(
                                    f"{stay['month']} booking-exact-results-dated-url [{label}]: "
                                    f"failed · {type(exc).__name__}: {str(exc)[:120]}",
                                    flush=True,
                                )

                    # Secondo tentativo: usa il testo ESATTO restituito
                    # dall'autocomplete Booking come ss, mantenendo le date nella URL.
                    # È diverso dal nome catalogo abbreviato usato nel primo search.
                    if not dates_ok and destination_text:
                        suggestion_url=booking_dated_search_url(destination_text,"",stay)
                        try:
                            response3=await page.goto(
                                suggestion_url,
                                wait_until="domcontentloaded",
                                timeout=25000,
                            )
                            await dismiss_cookie(page)
                            await page.wait_for_timeout(1800)
                            try:
                                body=(await page.locator("body").inner_text(timeout=7000))[:14000]
                            except Exception:
                                body=""
                            dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
                            cards=await booking_result_cards(page)
                            best=booking_best_card(cards,source,property_name,canonical_name,city)
                            print(
                                f"{stay['month']} booking-exact-suggestion-dated-search [{label}]: "
                                f"status={getattr(response3,'status',None)} · dates={dates_ok} · "
                                f"exact_url={bool(best and best[1])} · cards={len(cards)} · "
                                f"url={page.url[:320]}",
                                flush=True,
                            )
                        except Exception as exc:
                            print(
                                f"{stay['month']} booking-exact-suggestion-dated-search [{label}]: "
                                f"failed · {type(exc).__name__}: {str(exc)[:120]}",
                                flush=True,
                            )

                    # Fallback: solo se la URL datata non ha funzionato, prova ancora
                    # il calendario sulla searchresults esatta.
                    if best and best[1] and not dates_ok:
                        applied3,ui_evidence3=await booking_apply_dates_via_ui(page,stay)
                        print(
                            f"{stay['month']} booking-search-date-picker-on-exact-results [{label}]: "
                            f"{'applied' if applied3 else 'failed'} · {ui_evidence3}",
                            flush=True,
                        )
                        if ui_evidence3:
                            ui_evidence=(ui_evidence+" | "+ui_evidence3).strip(" |")
                        if applied3:
                            try:
                                await page.wait_for_timeout(1400)
                                body=(await page.locator("body").inner_text(timeout=7000))[:14000]
                                dates_ok,date_mode=await booking_page_dates_confirmed(page,stay,body)
                            except Exception:
                                pass
                            for _ in range(8):
                                await page.wait_for_timeout(650)
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
                    + (f"Date picker: {ui_evidence}. " if ui_evidence else "")
                    + (f"Destinazione: {destination_evidence}." if destination_evidence else "")
                )[:900],
            }
        except Exception as exc:
            return {
                "ok":False,"label":label,"reason":"navigation_error","status":"navigation_error",
                "evidence":f"{label}: {type(exc).__name__}: {str(exc)[:160]}",
            }

    # Prima strategia: riproduci un vero flusso utente partendo dalla home,
    # scegliendo la destinazione PRIMA delle date. I log v32 hanno dimostrato
    # che modificare la destinazione su una searchresults già datata azzera le date.
    clean=await booking_clean_ui_search(
        page,source,property_name,canonical_name,city,stay,robots
    )
    clean_best=clean.get("best") if clean.get("ok") else None
    if clean.get("ok") and clean.get("datesOk") and clean_best and clean_best[1]:
        primary=clean
        record["requestedUrl"]=str(clean.get("finalUrl") or requested)
    else:
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
    # La card può contenere importi promozionali o testi non riferiti al
    # preventivo della struttura. Considera prezzo-card solo il nodo prezzo
    # esplicitamente isolato dal parser; per la scheda esatta prevale sempre
    # il dettaglio Booking.
    total=_money_value(str(item.get("price") or ""))
    route_label=str(chosen.get("label") or "Booking")

    # Quando la card è quella esatta e le date sono confermate, la scheda
    # dettaglio è la fonte primaria per camere, piani tariffari e prezzi.
    # Non fermarti su testi generici della card risultati.
    if exact_path and dates_ok:
        detail=await booking_follow_matched_listing(page,source,item,stay,robots)
        detail_status=str(detail.get("status") or "dated_search_inconclusive")
        print(
            f"{stay['month']} booking-exact-detail-first: "
            f"status={detail_status} · quotes={len(detail.get('quotes') or [])} · "
            f"url={str(detail.get('finalUrl') or '')[:300]}",
            flush=True,
        )
        if detail_status in {
            "quote_candidates","quote_candidates_unverified","no_public_rate",
            "needs_human_review","rate_limited","http_error","navigation_error"
        }:
            record["finalUrl"]=str(detail.get("finalUrl") or chosen.get("finalUrl") or "")
            record["title"]=str(detail.get("title") or chosen.get("title") or "")[:200]
            record["quotes"]=detail.get("quotes") or []
            record["status"]=detail_status
            record["evidence"]=(
                f"{canonical_evidence} {route_label}: scheda esatta «{item.get('title','')}» trovata "
                f"(URL listing identico); date confermate ({date_mode or 'n.d.'}). "
                f"Dettaglio scheda: {detail.get('evidence','')}"
            )[:900]
            return record

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


def shifted_reference_stay(stay: dict, offset_days: int) -> dict:
    """Sposta il soggiorno mantenendo notti/ospiti e riallinea il mese alla data reale."""
    start=date.fromisoformat(stay["checkin"]) + timedelta(days=offset_days)
    nights=int(stay.get("nights") or 1)
    end=start + timedelta(days=nights)
    return {
        **stay,
        "month":start.strftime("%Y-%m"),
        "checkin":start.isoformat(),
        "checkout":end.isoformat(),
        "nights":nights,
    }


async def booking_resolve_reference_stay(
    context,
    source: str,
    property_name: str,
    city: str,
    stay: dict,
    robots: dict,
    initial_record: dict,
) -> tuple[dict, dict, dict]:
    """Trova una finestra Booking tariffata prima di interrogare le altre OTA.

    Cambia data soltanto quando Booking ha dichiarato esplicitamente assenza di
    tariffa pubblica. Stati tecnici/inconcludenti non vengono interpretati come
    indisponibilità. Mantiene notti e ospiti invariati.
    """
    # Booking deve fornire almeno una tariffa strutturata/validata per diventare
    # il riferimento delle date del confronto multi-OTA. Un prezzo visibile ma
    # non attribuito alla camera non basta: in quel caso Velora prova altre date.
    initial_status=str(initial_record.get("status") or "")
    initial_verified=any(bool(item.get("verified")) for item in (initial_record.get("quotes") or []))
    if initial_status=="quote_candidates" and initial_verified:
        return stay,initial_record,{
            "status":"initial_dates_available",
            "requestedCheckin":stay["checkin"],
            "requestedCheckout":stay["checkout"],
            "resolvedCheckin":stay["checkin"],
            "resolvedCheckout":stay["checkout"],
            "attempts":1,
        }

    # Se Booking è tecnicamente irraggiungibile/bloccato non cambiare data:
    # spostare il soggiorno non risolverebbe il problema e aumenterebbe le richieste.
    if initial_status in {"rate_limited","blocked","robots_denied","robots_unavailable","http_error","navigation_error"}:
        return stay,initial_record,{
            "status":"initial_dates_technical_stop",
            "requestedCheckin":stay["checkin"],
            "requestedCheckout":stay["checkout"],
            "resolvedCheckin":stay["checkin"],
            "resolvedCheckout":stay["checkout"],
            "attempts":1,
            "evidence":"Booking non ha restituito un esito tariffario affidabile per un limite tecnico; nessuno spostamento automatico applicato.",
        }

    # Ricerca progressiva ma contenuta: abbastanza ampia per trovare una finestra
    # prenotabile senza trasformare un singolo mese in decine di richieste.
    offsets=[1,2,3,5,7,10,14,21,28,42,56]
    carrier=await context.new_page()
    attempts=1
    try:
        for offset in offsets:
            candidate=shifted_reference_stay(stay,offset)
            attempts+=1
            probe=await booking_probe_direct_dated_detail(carrier,source,candidate,robots)
            probe_status=str((probe or {}).get("status") or "inconclusive")
            print(
                f"{stay['month']} booking-reference-date-search: +{offset}g "
                f"{candidate['checkin']}→{candidate['checkout']} · {probe_status}",
                flush=True,
            )

            probe_verified=any(bool(item.get("verified")) for item in ((probe or {}).get("quotes") or []))
            if probe_status=="quote_candidates" and probe_verified:
                resolved={
                    "otaId":"booking",
                    **candidate,
                    "sourceUrl":source,
                    "requestedUrl":dated_url("booking",source,candidate) or source,
                    "observedAt":datetime.now(timezone.utc).isoformat(),
                    "status":probe_status,
                    "finalUrl":str((probe or {}).get("finalUrl") or ""),
                    "title":str((probe or {}).get("title") or "")[:200],
                    "quotes":(probe or {}).get("quotes") or [],
                    "evidence":(
                        f"Date Booking di riferimento trovate automaticamente dopo indisponibilità iniziale: "
                        f"{stay['checkin']} → {stay['checkout']} sostituite con "
                        f"{candidate['checkin']} → {candidate['checkout']} mantenendo "
                        f"{candidate['nights']} notti e {candidate.get('adults',2)} ospiti. "
                        f"{str((probe or {}).get('evidence') or '')}"
                    )[:900],
                }
                return candidate,resolved,{
                    "status":"shifted_to_available_booking_dates",
                    "requestedCheckin":stay["checkin"],
                    "requestedCheckout":stay["checkout"],
                    "resolvedCheckin":candidate["checkin"],
                    "resolvedCheckout":candidate["checkout"],
                    "offsetDays":offset,
                    "attempts":attempts,
                    "evidence":"La stessa finestra Booking verrà usata per tutte le altre OTA del confronto.",
                }

            if probe_status=="rate_limited":
                return stay,initial_record,{
                    "status":"stopped_rate_limited",
                    "requestedCheckin":stay["checkin"],
                    "requestedCheckout":stay["checkout"],
                    "resolvedCheckin":stay["checkin"],
                    "resolvedCheckout":stay["checkout"],
                    "attempts":attempts,
                    "evidence":"Ricerca di una nuova data Booking interrotta per rate limit; nessun bypass eseguito.",
                }

            await asyncio.sleep(0.7)
    finally:
        try:
            await carrier.close()
        except Exception:
            pass

    initial_record["evidence"]=(
        str(initial_record.get("evidence") or "") +
        " | Velora ha cercato automaticamente una finestra Booking tariffata "
        "nelle date successive (stessa durata), senza trovarne una entro l'orizzonte di ricerca."
    )[:900]
    return stay,initial_record,{
        "status":"no_available_booking_date_found",
        "requestedCheckin":stay["checkin"],
        "requestedCheckout":stay["checkout"],
        "resolvedCheckin":stay["checkin"],
        "resolvedCheckout":stay["checkout"],
        "attempts":attempts,
    }


async def booking_probe_direct_dated_detail(page, source: str, stay: dict, robots: dict) -> dict | None:
    """Prova la scheda Booking esatta con date direttamente nella URL, su una nuova tab.

    La pagina risultati ha già confermato l'identità della struttura. Questa prova
    evita di dipendere dal trasferimento JS/sessione della searchresults alla scheda.
    """
    target=dated_url("booking",source,stay) or ""
    if not target:
        return None
    permission=await asyncio.to_thread(allowed_by_robots,target,robots)
    if permission is not True:
        return None

    probe=None
    try:
        probe=await page.context.new_page()
        response=await probe.goto(target,wait_until="domcontentloaded",timeout=25000)
        await dismiss_cookie(probe)
        try:
            await probe.locator("body").wait_for(state="visible",timeout=5000)
        except Exception:
            pass
        await probe.wait_for_timeout(1800)

        if response and response.status==429:
            return {
                "status":"rate_limited","finalUrl":probe.url,"title":(await probe.title())[:200],
                "quotes":[],"evidence":"Scheda Booking diretta datata: HTTP 429."
            }
        if response and response.status>=400:
            return None

        try:
            body=(await probe.locator("body").inner_text(timeout=7000))[:16000]
        except Exception:
            body=""
        dates_ok,date_mode=await booking_page_dates_confirmed(probe,stay,body)
        print(
            f"{stay['month']} booking-direct-dated-detail: "
            f"status={getattr(response,'status',None)} · dates={dates_ok} · "
            f"url={probe.url[:340]} · requested={target[:340]}",
            flush=True,
        )
        if not dates_ok:
            return None

        reveal_evidence=await booking_reveal_rates(probe,stay)
        print(
            f"{stay['month']} booking-reveal-rates [direct detail]: {reveal_evidence}",
            flush=True,
        )
        render_diag=await booking_settle_render(probe)
        try:
            body=(await probe.locator("body").inner_text(timeout=7000))[:18000]
        except Exception:
            body=""

        candidates=await booking_quote_candidates(probe,stay)
        verified=[item for item in candidates if item.get("verified")]
        unavailable_hit=booking_unavailability_message(body)
        print(
            f"{stay['month']} booking-rate-diagnostics [direct detail]: "
            f"candidates={len(candidates)} · verified={len(verified)} · "
            f"unavailable={unavailable_hit or 'no'}",
            flush=True,
        )
        if candidates:
            preview=" | ".join(
                f"{item.get('roomType','')[:45]} / {item.get('ratePlan','')[:55]} / €{item.get('total')}"
                for item in candidates[:6]
            )
            print(
                f"{stay['month']} booking-rate-preview [direct detail]: {preview[:900]}",
                flush=True,
            )

        # Un messaggio generico di indisponibilità può convivere nella pagina con
        # camere/tariffe realmente prenotabili (es. una tipologia o un piano non
        # disponibile). Se ci sono prezzi attribuibili, prevalgono le tariffe.
        if not candidates and unavailable_hit:
            return {
                "status":"no_public_rate","finalUrl":probe.url,"title":(await probe.title())[:200],
                "quotes":[],
                "evidence":(
                    f"Scheda Booking esatta aperta direttamente con date confermate "
                    f"({date_mode or 'pagina renderizzata'}) {stay['checkin']} → {stay['checkout']}. "
                    f"Nessuna riga camera/prezzo rilevata e Booking mostra indisponibilità («{unavailable_hit}»)."
                )[:900],
            }
        if verified:
            first=verified[0]
            return {
                "status":"quote_candidates","finalUrl":probe.url,"title":(await probe.title())[:200],
                "quotes":candidates,
                "evidence":(
                    f"Scheda Booking esatta aperta direttamente con date confermate "
                    f"({date_mode or 'pagina renderizzata'}). Rilevati {len(candidates)} candidati "
                    f"camera/prezzo; esempio {first['roomType']} · €{first['total']:.2f}."
                )[:900],
            }
        if candidates:
            first=candidates[0]
            return {
                "status":"quote_candidates_unverified","finalUrl":probe.url,"title":(await probe.title())[:200],
                "quotes":candidates,
                "evidence":(
                    f"Scheda Booking esatta aperta direttamente con date confermate "
                    f"({date_mode or 'pagina renderizzata'}). Rilevati {len(candidates)} candidati "
                    f"prezzo; esempio €{first['total']:.2f}; camera/tasse/condizioni da verificare."
                )[:900],
            }

        return {
            "status":"needs_human_review","finalUrl":probe.url,"title":(await probe.title())[:200],
            "quotes":[],
            "evidence":(
                f"Scheda Booking esatta aperta direttamente con date confermate "
                f"({date_mode or 'pagina renderizzata'}), ma nessun prezzo o messaggio di "
                f"indisponibilità attribuibile con certezza. DOM: prezzi {render_diag.get('priceNodes',0)}, "
                f"camere {render_diag.get('roomNodes',0)}, disponibilità {render_diag.get('availabilityNodes',0)}."
            )[:900],
        }
    except Exception as exc:
        print(
            f"{stay['month']} booking-direct-dated-detail: failed · "
            f"{type(exc).__name__}: {str(exc)[:140]}",
            flush=True,
        )
        return None
    finally:
        if probe is not None:
            try:
                await probe.close()
            except Exception:
                pass


async def booking_follow_matched_listing(page, source: str, item: dict, stay: dict, robots: dict) -> dict:
    """Booking v10: clicca la card esatta dalla pagina datata, preservando sessione e date."""
    href=str(item.get("href") or "").strip()
    if not href:
        return {"status":"needs_human_review","evidence":"Card Booking esatta trovata, ma senza URL apribile.","quotes":[]}
    source_path=booking_path_key(source)
    href_path=booking_path_key(href)
    if not source_path or href_path != source_path:
        return {"status":"needs_human_review","evidence":"La card Booking trovata non coincide con la scheda già verificata.","quotes":[]}

    # Prima prova la scheda esatta con le date direttamente nella URL, ma in
    # una nuova tab: se Booking le mantiene, possiamo leggere disponibilità
    # senza dipendere dal fragile trasferimento di stato della searchresults.
    direct=await booking_probe_direct_dated_detail(page,source,stay,robots)
    if direct is not None:
        return direct

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
    reveal_evidence=await booking_reveal_rates(page,stay)
    print(
        f"{stay['month']} booking-reveal-rates [follow listing]: {reveal_evidence}",
        flush=True,
    )
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

    candidates=await booking_quote_candidates(page,stay)
    verified=[item for item in candidates if item.get("verified")]
    unavailable_hit=booking_unavailability_message(body)
    print(
        f"{stay['month']} booking-rate-diagnostics [follow listing]: "
        f"candidates={len(candidates)} · verified={len(verified)} · "
        f"unavailable={unavailable_hit or 'no'}",
        flush=True,
    )
    if not candidates and unavailable_hit:
        return {
            "status":"no_public_rate","finalUrl":final_url,"title":title,"quotes":[],
            "evidence":(
                f"{click_evidence or 'scheda esatta aperta'}; date confermate ({date_mode or 'pagina renderizzata'}) "
                f"{stay['checkin']} → {stay['checkout']}. "
                f"Nessuna riga camera/prezzo rilevata e Booking mostra indisponibilità («{unavailable_hit}»). "
                "Esito: nessuna tariffa pubblica prenotabile rilevata per queste date."
            )[:900],
        }
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

async def booking_reveal_rates(page, stay: dict) -> str:
    """Porta la scheda Booking fino alla sezione camere/tariffe come farebbe un utente.

    Non esegue prenotazioni: clicca al massimo un controllo di disponibilità/prezzi
    e poi si ferma sulla tabella/lista camere.
    """
    try:
        existing=await page.evaluate(r"""() => {
          const visible=(el) => {
            if (!el) return false;
            const st=getComputedStyle(el);
            if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
            const r=el.getBoundingClientRect();
            return r.width>0 && r.height>0;
          };
          const selectors=[
            '#hprt-table','#hprt-form','[data-testid="room-list"]',
            '[data-testid="room-card"]','[data-testid*="room-card"]',
            '[data-testid="availability-block"]'
          ];
          return selectors.some(sel => Array.from(document.querySelectorAll(sel)).some(visible));
        }""")
        if existing:
            target,_=await _first_visible_locator(page,(
                '#hprt-table','#hprt-form','[data-testid="room-list"]',
                '[data-testid="room-card"]','[data-testid*="room-card"]',
                '[data-testid="availability-block"]',
            ))
            if target is not None:
                try:
                    await target.scroll_into_view_if_needed(timeout=1600)
                    await page.wait_for_timeout(900)
                except Exception:
                    pass
            return "tariffe già visibili; sezione camere portata in vista"

        # Individua un CTA che apra/scorra alla disponibilità. Evita pulsanti di
        # acquisto/finalizzazione: qui ci fermiamo alla visualizzazione delle tariffe.
        candidate=await page.evaluate(r"""() => {
          const visible=(el) => {
            if (!el) return false;
            const st=getComputedStyle(el);
            if (st.display==='none' || st.visibility==='hidden' || Number(st.opacity || '1')===0) return false;
            const r=el.getBoundingClientRect();
            return r.width>0 && r.height>0;
          };
          const good=[
            'vedi disponibilità','verifica disponibilità','mostra disponibilità',
            'mostra prezzi','vedi prezzi','controlla disponibilità',
            'seleziona le camere','scegli la camera','scegli una camera',
            'see availability','check availability','show prices',
            'select rooms','choose a room'
          ];
          const bad=[
            'prenota ora','book now','conferma','confirm','paga','pay',
            'completa','complete booking','finalizza'
          ];
          const nodes=Array.from(document.querySelectorAll('button,a,[role="button"]')).filter(visible);
          for (let i=0;i<nodes.length;i++) {
            const el=nodes[i];
            const txt=(el.innerText || el.textContent || el.getAttribute('aria-label') || '')
              .replace(/\s+/g,' ').trim().toLowerCase();
            if (!txt || bad.some(term => txt.includes(term))) continue;
            if (good.some(term => txt.includes(term))) {
              el.setAttribute('data-velora-rate-cta','1');
              return {text:txt.slice(0,140),tag:el.tagName};
            }
          }
          return null;
        }""")
        if candidate:
            cta=page.locator('[data-velora-rate-cta="1"]').first
            await cta.scroll_into_view_if_needed(timeout=1500)
            await page.wait_for_timeout(300)
            await cta.click(timeout=2600)
            await page.wait_for_timeout(1800)
            try:
                await page.wait_for_load_state("domcontentloaded",timeout=7000)
            except Exception:
                pass
            target,_=await _first_visible_locator(page,(
                '#hprt-table','#hprt-form','[data-testid="room-list"]',
                '[data-testid="room-card"]','[data-testid*="room-card"]',
                '[data-testid="availability-block"]',
            ))
            if target is not None:
                try:
                    await target.scroll_into_view_if_needed(timeout=1600)
                    await page.wait_for_timeout(1200)
                except Exception:
                    pass
            return f"CTA tariffe cliccata: {candidate.get('text') or candidate.get('tag')}"

        # Ultimo tentativo non invasivo: usa un'ancora/elemento disponibilità già presente.
        target,_=await _first_visible_locator(page,(
            '#availability','#hprt-table','#hprt-form',
            '[data-testid="availability-block"]','[data-testid="room-list"]',
        ))
        if target is not None:
            await target.scroll_into_view_if_needed(timeout=1600)
            await page.wait_for_timeout(1000)
            return "sezione disponibilità raggiunta senza CTA"

        return "nessun CTA tariffe individuato"
    except Exception as exc:
        return f"apertura tariffe fallita: {type(exc).__name__}"


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


async def observe(
    page, channel: str, source: str, stay: dict, robots: dict,
    property_name: str="", city: str=""
) -> dict:
    requested = frontend_entry_url(channel, source, stay)
    record = {"otaId": channel, **stay, "sourceUrl": source, "requestedUrl": requested or source,
              "observedAt": datetime.now(timezone.utc).isoformat(), "status": "not_attempted",
              "finalUrl": "", "title": "", "evidence": "", "quotes": []}
    if requested is None:
        record.update(status="date_adapter_missing",
                      evidence="La scheda è nota, ma il pilota non conosce ancora un percorso verificato per applicare le date su questo portale.")
        return record
    permission = await asyncio.to_thread(allowed_by_robots, requested, robots)
    if permission is False:
        record.update(
            status="robots_denied",
            evidence="Scheda OTA presente, ma robots.txt nega l'accesso automatico: presenza registrata, prezzi non letti."
        )
        return record
    if permission is None:
        record["robotsNotice"]="robots.txt non disponibile/chiarificatore; lettura effettuata nel browser pubblico senza bypass."
    try:
        response = await page.goto(requested, wait_until="domcontentloaded", timeout=22000)
        if channel in {"booking","agoda","airbnb","vrbo","expedia","hotels","travelocity","trip","priceline","tripadvisor","trivago","googlehotels"}:
            await dismiss_cookie(page)
        # Il contenuto OTA spesso compare dopo il primo DOM; il limite resta breve.
        try:
            await page.locator("body").wait_for(state="visible", timeout=4200)
            await page.wait_for_timeout(1100)
        except PlaywrightTimeout:
            pass

        # 429/403 non devono consumare un intero ciclo né chiedere intervento umano
        # quando il portale non ha reso disponibile un frontend pubblico utilizzabile.
        if response and response.status in {403,429}:
            try:
                early=await page.evaluate(r"""() => {
                  const body=(document.body?.innerText || '').replace(/\s+/g,' ').trim();
                  const visible=el=>{
                    if(!el) return false; const s=getComputedStyle(el); const r=el.getBoundingClientRect();
                    return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0;
                  };
                  const selectors=[
                    'input','button','[data-testid*="date" i]','[data-stid*="date" i]',
                    '[data-testid*="price" i]','[data-stid*="price" i]','[class*="price" i]',
                    '[data-testid*="room" i]','[data-stid*="room" i]','[class*="room" i]'
                  ];
                  let interactive=0;
                  for(const sel of selectors){
                    interactive += Array.from(document.querySelectorAll(sel)).filter(visible).slice(0,40).length;
                  }
                  return {bodyLength:body.length,interactive};
                }""")
            except Exception:
                early={"bodyLength":0,"interactive":0}
            if int(early.get("bodyLength") or 0)<700 and int(early.get("interactive") or 0)<3:
                record["finalUrl"]=page.url
                record["title"]=(await page.title())[:200]
                record.update(
                    status="rate_limited" if response.status==429 else "http_error",
                    evidence=(
                        f"HTTP {response.status} · frontend pubblico non disponibile in questa sessione "
                        f"(contenuto insufficiente). Nessun login, retry aggressivo o intervento utente: "
                        "Velora passa automaticamente alla OTA successiva."
                    ),
                )
                return record

        airbnb_ui_evidence=""
        if channel=="airbnb":
            try:
                _,airbnb_ui_evidence=await airbnb_prepare_frontend(page,stay)
            except Exception as exc:
                airbnb_ui_evidence=f"Airbnb frontend: {type(exc).__name__}: {str(exc)[:160]}"

        async def snapshot_and_confirm():
            current_title=(await page.title())[:200]
            current_body=(await page.locator("body").inner_text(timeout=7000))[:12000]
            # Agoda: mai confermare le date dal testo generico della pagina.
            # La homepage può contenere numeri/date incidentali (es. offerte/carousel)
            # e in v85 questo poteva produrre un falso positivo, saltando il vero flusso
            # homepage -> struttura -> date -> Cerca -> camere/tariffe.
            if channel=="agoda":
                confirmed=False
                mode=""
            else:
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
            if channel == "agoda" and not confirmed:
                agoda_path=(urlparse(page.url).path or "").lower().rstrip("/")
                agoda_home=agoda_path in {"","/it-it","/en-us","/"}
                if not agoda_home:
                    confirmed, dom_excerpt = await agoda_dom_dates_confirmed(page, stay)
                    if confirmed:
                        mode="agoda-dom-fields"
                    if not confirmed and agoda_url_dates_confirmed(page.url, stay):
                        property_context, context_evidence = await agoda_property_rate_context(page)
                        if property_context:
                            confirmed=True
                            mode="agoda-final-url+rate-context"
                            dom_excerpt=(
                                "URL finale Agoda mantiene check-in e durata richiesti; "
                                f"contesto tariffario DOM: {context_evidence or 'scheda struttura'}"
                            )
                else:
                    dom_excerpt="Homepage Agoda: date eventualmente presenti nel widget non valgono come conferma della scheda struttura."
            if channel == "airbnb" and not confirmed and airbnb_url_dates_confirmed(page.url, stay):
                property_context, context_evidence = await listing_property_rate_context(page,"airbnb")
                if property_context:
                    confirmed=True
                    mode="airbnb-final-url+rate-context"
                    dom_excerpt=(
                        "URL finale Airbnb mantiene check-in/check-out richiesti; "
                        f"contesto tariffario DOM: {context_evidence or 'scheda struttura'}"
                        + (f" | {airbnb_ui_evidence}" if airbnb_ui_evidence else "")
                    )
            if channel == "vrbo" and not confirmed and vrbo_url_dates_confirmed(page.url, stay):
                property_context, context_evidence = await listing_property_rate_context(page,"vrbo")
                if property_context:
                    confirmed=True
                    mode="vrbo-final-url+rate-context"
                    dom_excerpt=(
                        "URL finale Vrbo mantiene check-in/check-out richiesti; "
                        f"contesto tariffario DOM: {context_evidence or 'scheda struttura'}"
                    )
            if channel == "holidu" and not confirmed and holidu_url_dates_confirmed(page.url, stay):
                confirmed=True
                mode="holidu-final-url"
                dom_excerpt="URL finale Holidu mantiene check-in/check-out richiesti."
            if channel in {"expedia","hotels","travelocity"} and not confirmed and expedia_group_url_dates_confirmed(page.url, stay):
                property_context, context_evidence = await expedia_group_property_rate_context(page,channel)
                if property_context:
                    confirmed=True
                    mode=f"{channel}-final-url+rate-context"
                    dom_excerpt=(
                        f"URL finale {OTA_META[channel]['label']} mantiene check-in/check-out richiesti; "
                        f"contesto tariffario DOM: {context_evidence or 'scheda struttura'}"
                    )
            if channel == "trip" and not confirmed and trip_url_dates_confirmed(page.url, stay):
                property_context, context_evidence = await trip_property_rate_context(page)
                if property_context:
                    confirmed=True
                    mode="trip-final-url+rate-context"
                    dom_excerpt=(
                        "URL finale Trip.com mantiene check-in/check-out richiesti; "
                        f"contesto tariffario DOM: {context_evidence or 'scheda struttura'}"
                    )
            if channel == "priceline" and not confirmed:
                confirmed, dom_excerpt = await priceline_dom_dates_confirmed(page, stay)
                if confirmed:
                    property_context, context_evidence = await priceline_property_rate_context(page)
                    if property_context:
                        mode="priceline-dom-fields+rate-context"
                        dom_excerpt=(dom_excerpt+" | "+context_evidence)[:800]
                    else:
                        confirmed=False
            return current_title,current_body,confirmed,mode,dom_excerpt

        record["finalUrl"] = page.url
        record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
        auth_wall=ota_auth_wall(page.url,record["title"],body)
        if auth_wall:
            record.update(
                status="login_required",
                evidence=(
                    f"{OTA_META.get(channel,{}).get('label',channel)} ha reindirizzato verso una pagina di login/account "
                    f"({auth_wall}). FLUSSO PUBBLICO INTERROTTO: Velora non effettua e non tenterà mai login, "
                    f"registrazione o accesso account; nessun prezzo di questa pagina viene usato. URL finale: {page.url}"
                )[:900],
            )
            return record
        ui_date_evidence=""
        if channel == "booking" and not dates_confirmed:
            applied, ui_date_evidence = await booking_apply_dates_via_ui(page, stay)
            if applied:
                record["finalUrl"] = page.url
                record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
                if dates_confirmed and not date_confirmation_mode:
                    date_confirmation_mode="booking-ui-date-picker"
        elif channel == "priceline" and not dates_confirmed:
            applied, ui_date_evidence = await priceline_apply_dates_via_ui(page, stay)
            if applied:
                record["finalUrl"] = page.url
                record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
                if dates_confirmed and not date_confirmation_mode:
                    date_confirmation_mode="priceline-ui-date-picker"
        elif channel == "agoda" and (
            not dates_confirmed
            or (urlparse(page.url).path or "").lower().rstrip("/") in {"","/it-it","/en-us","/"}
        ):
            print(
                f"{stay['month']} agoda-frontend-flow: START · url={page.url[:260]} · "
                f"property={property_name[:120]} · city={city[:80]}",
                flush=True,
            )
            applied, ui_date_evidence = await agoda_prepare_frontend(
                page,source,stay,property_name=property_name,city=city
            )
            print(
                f"{stay['month']} agoda-frontend-flow: applied={applied} · "
                f"url={page.url[:320]} · {ui_date_evidence[:700]}",
                flush=True,
            )
            record["finalUrl"] = page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
            if applied and dates_confirmed:
                date_confirmation_mode="agoda-home-search+frontend"
            elif applied and not dates_confirmed:
                # Il helper ha completato la UI ma la conferma finale non deve dipendere
                # dal testo generico: prova una volta il DOM Agoda e la URL della scheda.
                dom_ok,dom_ev=await agoda_dom_dates_confirmed(page,stay)
                url_ok=agoda_url_dates_confirmed(page.url,stay)
                property_ok,property_ev=await agoda_property_rate_context(page)
                if dom_ok or (url_ok and property_ok):
                    dates_confirmed=True
                    date_confirmation_mode="agoda-home-search+frontend"
                    date_dom_excerpt=(dom_ev or property_ev or "Agoda frontend completato")[:800]
        elif channel in {"airbnb","vrbo","holidu","expedia","hotels","travelocity","trip"} and not dates_confirmed:
            applied, ui_date_evidence = await generic_ota_frontend_apply_dates(page,channel,stay)
            if applied:
                record["finalUrl"] = page.url
                record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
                if dates_confirmed and not date_confirmation_mode:
                    date_confirmation_mode=f"{channel}-frontend-date-picker"
        render_diag={}
        if channel == "booking" and dates_confirmed:
            render_diag = await booking_settle_render(page)
            record["finalUrl"] = page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
        elif channel == "agoda" and dates_confirmed:
            try:
                await page.locator(
                    '[data-selenium="display-price"], [data-selenium="room-price"], [data-selenium="room-name"]'
                ).first.wait_for(state="visible",timeout=4500)
            except Exception:
                await page.wait_for_timeout(1200)
            record["finalUrl"] = page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
        elif channel in {"airbnb","vrbo"} and dates_confirmed:
            vrbo_reveal_evidence=""
            if channel=="vrbo":
                vrbo_reveal_evidence=await vrbo_reveal_rates(page,source,stay)
            try:
                selectors=(
                    '[data-testid="book-it-default"], [data-section-id="BOOK_IT_SIDEBAR"], [data-testid*="price"]'
                    if channel=="airbnb"
                    else '[data-stid*="price"], [data-stid*="book"], [data-testid*="price"]'
                )
                await page.locator(selectors).first.wait_for(state="visible",timeout=4500)
            except Exception:
                await page.wait_for_timeout(1200)
            record["finalUrl"] = page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
            if channel=="vrbo" and vrbo_reveal_evidence:
                date_dom_excerpt=(str(date_dom_excerpt or "")+" | "+vrbo_reveal_evidence)[:800]
        elif channel == "holidu" and dates_confirmed:
            holidu_evidence=await holidu_reveal_rates(page,source,stay)
            await page.wait_for_timeout(900)
            record["finalUrl"]=page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
            date_dom_excerpt=(str(date_dom_excerpt or "")+" | "+holidu_evidence)[:800]
        elif channel in {"expedia","hotels","travelocity"} and dates_confirmed:
            reveal_evidence=await expedia_group_reveal_rates(page,channel)
            try:
                await page.locator(
                    '[data-stid*="room-card"], [data-stid*="room-offer"], [data-stid*="room"], '
                    '[data-stid="price-lockup-text"], [data-stid*="price"], '
                    '[data-testid*="room"], [data-testid*="price"]'
                ).first.wait_for(state="visible",timeout=6500)
            except Exception:
                await page.wait_for_timeout(1800)
            record["finalUrl"] = page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
            date_dom_excerpt=(str(date_dom_excerpt or "")+" | "+reveal_evidence)[:800]
        elif channel == "trip" and dates_confirmed:
            try:
                await page.locator(
                    '[data-testid*="room"], [class*="room-card" i], [class*="room-item" i], [class*="price" i]'
                ).first.wait_for(state="visible",timeout=5000)
            except Exception:
                await page.wait_for_timeout(1400)
            record["finalUrl"] = page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
        elif channel == "priceline" and dates_confirmed:
            try:
                await page.locator(
                    '[data-testid*="room" i], [class*="room" i], [data-testid*="price" i], [class*="price" i]'
                ).first.wait_for(state="visible",timeout=5000)
            except Exception:
                await page.wait_for_timeout(1400)
            record["finalUrl"] = page.url
            record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
        if response and response.status in {403,429}:
            # Alcune OTA restituiscono 403/429 sul documento iniziale ma completano comunque
            # il frontend pubblico già aperto nel browser. Aspetta il rendering, senza retry
            # aggressivi né bypass, e valuta ciò che l'utente vedrebbe realmente.
            try:
                await page.wait_for_timeout(2600)
                await page.evaluate("window.scrollTo(0, Math.floor(document.body.scrollHeight*0.35))")
                await page.wait_for_timeout(700)
                record["finalUrl"] = page.url
                record["title"], body, dates_confirmed, date_confirmation_mode, date_dom_excerpt = await snapshot_and_confirm()
            except Exception:
                pass
        text = (record["title"] + " " + body).lower()
        if channel=="agoda" and _agoda_unit_listing_conflict(property_name,page.url,record["title"]):
            record.update(
                status="wrong_property_listing",
                finalUrl=page.url,
                quotes=[],
                evidence=(
                    "Agoda: pagina numerata relativa a singola unità/camera, "
                    "non confermata come hotel principale richiesto. "
                    "Questa scheda non può contribuire al confronto Booking/OTA. "
                    f"URL: {page.url[:500]}"
                )[:900],
            )
            return record
        if channel=="agoda":
            agoda_path=(urlparse(page.url).path or "").lower().rstrip("/")
            if agoda_path in {"","/it-it","/en-us","/"}:
                dates_confirmed=False
                date_confirmation_mode=""
                date_dom_excerpt=(
                    "Agoda è rimasta sulla homepage: il flusso struttura/date/Cerca non è arrivato "
                    "alla scheda hotel. Nessun prezzo della homepage può essere considerato tariffa struttura."
                )
        post_auth_wall=ota_auth_wall(page.url,record["title"],body)
        if post_auth_wall:
            record.update(
                status="login_required",
                evidence=(
                    f"{OTA_META.get(channel,{}).get('label',channel)} ha portato il flusso pubblico verso login/account "
                    f"({post_auth_wall}). Velora NON procede: nessun login, registrazione o account viene mai tentato. "
                    f"URL finale: {page.url}"
                )[:900],
            )
            return record
        soft_http_status=response.status if response and response.status in {403,429} else 0
        rendered_usable=bool(
            soft_http_status
            and dates_confirmed
            and len(body.strip())>=700
            and not any(word in text for word in BLOCK_WORDS)
            and not ota_auth_wall(page.url,record["title"],body)
        )
        if response and response.status in {403,429} and not rendered_usable:
            record.update(
                status="rate_limited" if response.status==429 else "http_error",
                evidence=(
                    f"HTTP {response.status} · il browser non ha renderizzato contenuto tariffario sufficiente "
                    f"con le date richieste. Nessun aggiramento tentato. URL finale: {page.url}"
                )[:900],
            )
        elif response and response.status >= 400 and response.status not in {403,429}:
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
                candidates = await booking_quote_candidates(page, stay)
                record["quotes"] = candidates
                verified = [item for item in candidates if item.get("verified")]
                unavailable_hit = booking_unavailability_message(body)
                print(
                    f"{stay['month']} booking-rate-diagnostics [observe]: "
                    f"candidates={len(candidates)} · verified={len(verified)} · "
                    f"unavailable={unavailable_hit or 'no'}",
                    flush=True,
                )
                if not candidates and unavailable_hit:
                    record.update(
                        status="no_public_rate",
                        evidence=(
                            f"Date confermate ({date_confirmation_mode or 'pagina renderizzata'}): "
                            f"{stay['checkin']} → {stay['checkout']}. "
                            f"Nessuna riga camera/prezzo rilevata e Booking mostra un messaggio di indisponibilità («{unavailable_hit}»). "
                            "Esito: nessuna tariffa pubblica prenotabile rilevata per queste date."
                        )[:900],
                    )
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
                    fallback=await generic_ota_quote_candidates(page,stay)
                    if fallback:
                        record["quotes"]=fallback
                        record.update(
                            status="quote_candidates_unverified",
                            evidence=(
                                f"Date Booking confermate ({date_confirmation_mode or 'pagina renderizzata'}). "
                                f"Il parser strutturato non ha associato camera e piano, ma ha isolato {len(fallback)} "
                                "importi EUR nel contesto tariffario della scheda. Questi prezzi restano non validati; "
                                "Velora continuerà comunque a cercare una finestra Booking con almeno una tariffa strutturata "
                                "prima di fissare le date del confronto multi-OTA."
                            )[:900],
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
            elif channel == "agoda":
                candidates=await agoda_room_offer_visual_candidates(page,stay)
                if not candidates:
                    candidates=await agoda_offer_row_candidates(page,stay)
                if not candidates:
                    candidates=await agoda_quote_candidates(page,stay)
                record["quotes"]=candidates
                agoda_debug=await agoda_actual_rate_dom_diagnostics(page)
                record["rateDiagnostics"]=agoda_debug
                print(
                    f"{stay['month']} agoda-rate-diagnostics: candidates={len(candidates)} · "
                    f"numericEuroPrices={agoda_debug.get('numericEuroPrices',0)} · "
                    f"actualRoomNames={agoda_debug.get('actualRoomNames',0)} · "
                    f"numericSamples={str(agoda_debug.get('numericPriceSamples') or [])[:310]} · "
                    f"bannerOnly={str(agoda_debug.get('bannerSamples') or [])[:220]} · "
                    f"url={page.url[:260]}",
                    flush=True,
                )
                verified=[item for item in candidates if item.get("verified")]
                if verified:
                    first=verified[0]
                    record.update(
                        status="quote_candidates",
                        evidence=(
                            f"Date Agoda confermate ({date_confirmation_mode or 'pagina renderizzata'}). "
                            f"Rilevate {len(candidates)} righe camera/prezzo; {len(verified)} hanno camera e base prezzo "
                            f"attribuite nello stesso blocco tariffario. Esempio: {first['roomType']} · "
                            f"€{first['total']:.2f} per {stay['nights']} notti. "
                            "Tasse e identità fisica dell'unità restano separate dal delta OTA finché non sono comparabili."
                        )[:900],
                    )
                elif candidates:
                    first=candidates[0]
                    record.update(
                        status="quote_candidates_unverified",
                        evidence=(
                            f"Date Agoda confermate. Rilevati {len(candidates)} prezzi visibili, ma la base del prezzo "
                            f"non è abbastanza esplicita per validarli automaticamente. Esempio €{first['total']:.2f}."
                        )[:900],
                    )
                else:
                    fallback=await agoda_visible_rate_candidates(page,stay)
                    record["quotes"]=fallback
                    if fallback:
                        record.update(
                            status="quote_candidates",
                            evidence=(
                                f"Date Agoda confermate. Il fallback specifico Agoda ha associato {len(fallback)} prezzi "
                                f"a camera + base prezzo esplicita. Esempio: {fallback[0]['roomType']} · "
                                f"€{fallback[0]['nightlyRate']:.2f}/notte · €{fallback[0]['total']:.2f} totale."
                            )[:900],
                        )
                    else:
                        geometric=await agoda_geometric_rate_candidates(page,stay)
                        record["quotes"]=geometric
                        if geometric:
                            record.update(
                                status="quote_candidates_unverified",
                                evidence=(
                                    f"Date Agoda confermate. Il parser strutturato non ha chiuso il match, ma il frontend mostra "
                                    f"{len(geometric)} prezzo/i associabili a una camera per prossimità visiva. "
                                    f"I valori vengono mostrati come reali osservati ma restano esclusi dal delta finché non validati. "
                                    f"Esempio: {geometric[0]['roomType']} · €{geometric[0]['nightlyRate']:.2f}/notte."
                                )[:900],
                            )
                        else:
                            explicit_sold_out=agoda_sold_out_message(body)
                            eur_count=int(agoda_debug.get("numericEuroPrices") or 0)
                            room_count=int(agoda_debug.get("actualRoomNames") or 0)
                            if explicit_sold_out:
                                record.update(
                                    status="no_public_rate",
                                    evidence=(
                                        f"Agoda: nessuna disponibilità pubblica per "
                                        f"{stay['checkin']}→{stay['checkout']} (2 adulti). "
                                        f"Messaggio esplicito sulla scheda: «{explicit_sold_out}». "
                                        "Nessun prezzo inventato."
                                    )[:900],
                                )
                            elif eur_count==0:
                                record.update(
                                    status="needs_human_review",
                                    evidence=(
                                        "Scheda Agoda letta con le date richieste, ma nel frontend non "
                                        "compare alcun importo numerico in euro attribuibile a un'offerta. "
                                        f"Camere identificate: {room_count}. "
                                        "I banner (es. «Pareggiamo il prezzo più basso!») non sono tariffe. "
                                        "La disponibilità non è dimostrata."
                                    )[:900],
                                )
                            else:
                                record.update(
                                    status="needs_human_review",
                                    evidence=(
                                        f"Agoda mostra {eur_count} elemento/i con importo EUR e "
                                        f"{room_count} intestazione/i camera, ma non è verificata "
                                        "l'associazione prezzo/camera/base tariffaria. "
                                        "Importi esclusi dal confronto finché non validati."
                                    )[:900],
                                )
            elif channel in {"airbnb","vrbo"}:
                candidates=(
                    await airbnb_quote_candidates(page,stay)
                    if channel=="airbnb"
                    else await vrbo_quote_candidates(page,stay)
                )
                record["quotes"]=candidates
                if candidates:
                    first=candidates[0]
                    label=OTA_META[channel]["label"]
                    record.update(
                        status="quote_candidates",
                        evidence=(
                            f"Date {label} confermate ({date_confirmation_mode or 'pagina renderizzata'}). "
                            f"Rilevati {len(candidates)} preventivi con scheda struttura e base prezzo esplicita. "
                            f"Esempio: {first['roomType']} · €{first['total']:.2f} per {stay['nights']} notti. "
                            "Il delta con Booking resta escluso finché l'identità della stessa unità fisica e le condizioni non coincidono."
                        )[:900],
                    )
                else:
                    fallback=await generic_ota_quote_candidates(page,stay)
                    record["quotes"]=fallback
                    if fallback:
                        record.update(
                            status="quote_candidates_unverified",
                            evidence=(
                                f"Date {OTA_META[channel]['label']} confermate. Nessun preventivo strutturato è stato attribuito "
                                f"alla camera, ma Velora ha isolato {len(fallback)} importi EUR nel contesto tariffario visibile. "
                                "Gli importi restano da verificare e non alimentano il delta OTA."
                            )[:900],
                        )
                    else:
                        record.update(
                            status="needs_human_review",
                            evidence=f"Date {OTA_META[channel]['label']} confermate, ma nessun riepilogo prezzo attribuibile automaticamente con sufficiente certezza."
                        )
            elif channel == "holidu":
                candidates=await holidu_quote_candidates(page,stay)
                record["quotes"]=candidates
                if candidates:
                    first=candidates[0]
                    record.update(
                        status="quote_candidates",
                        evidence=(
                            f"Date Holidu confermate ({date_confirmation_mode or 'pagina renderizzata'}). "
                            f"Rilevata tariffa frontend per {first['roomType']} · €{first['total']:.2f} per {stay['nights']} notti."
                        )[:900],
                    )
                else:
                    fallback=await generic_ota_quote_candidates(page,stay)
                    record["quotes"]=fallback
                    record.update(
                        status="quote_candidates_unverified" if fallback else "needs_human_review",
                        evidence=(f"Date Holidu confermate. Rilevati {len(fallback)} prezzi visibili da verificare." if fallback else "Date Holidu confermate, ma nessun riepilogo prezzo attribuibile automaticamente.")[:900],
                    )
            elif channel in {"expedia","hotels","travelocity"}:
                candidates=await expedia_group_quote_candidates(page,stay,channel)
                record["quotes"]=candidates
                if candidates:
                    first=candidates[0]
                    label=OTA_META[channel]["label"]
                    record.update(
                        status="quote_candidates",
                        evidence=(
                            f"Date {label} confermate ({date_confirmation_mode or 'pagina renderizzata'}). "
                            f"Rilevate {len(candidates)} righe camera/prezzo con base tariffaria esplicita. "
                            f"Esempio: {first['roomType']} · €{first['total']:.2f} per {stay['nights']} notti. "
                            "Eventuali tariffe member sono etichettate e non vengono confuse con il prezzo pubblico."
                        )[:900],
                    )
                else:
                    semantic=await expedia_group_semantic_quote_candidates(page,stay,channel)
                    fallback=semantic or await generic_ota_quote_candidates(page,stay)
                    record["quotes"]=fallback
                    verified_semantic=[item for item in fallback if item.get("verified")]
                    if fallback:
                        record.update(
                            status="quote_candidates" if verified_semantic else "quote_candidates_unverified",
                            evidence=(
                                f"Date {OTA_META[channel]['label']} confermate. Il parser strutturato non ha chiuso il match, "
                                f"ma il frontend mostra {len(fallback)} prezzo/i con durata esplicita. "
                                + ("Camera e prezzo sono associati nello stesso blocco." if verified_semantic else "La tipologia camera resta da verificare: il prezzo viene mostrato ma non entra nel delta.")
                            )[:900],
                        )
                    else:
                        record.update(
                            status="needs_human_review",
                            evidence=f"Date {OTA_META[channel]['label']} confermate, ma nessun prezzo con durata esplicita è stato isolato nel frontend."
                        )
            elif channel == "trip":
                candidates=await trip_quote_candidates(page,stay)
                record["quotes"]=candidates
                if candidates:
                    first=candidates[0]
                    record.update(
                        status="quote_candidates",
                        evidence=(
                            f"Date Trip.com confermate ({date_confirmation_mode or 'pagina renderizzata'}). "
                            f"Rilevate {len(candidates)} righe camera/prezzo con base tariffaria esplicita. "
                            f"Esempio: {first['roomType']} · €{first['total']:.2f} per {stay['nights']} notti. "
                            "Le tariffe member vengono mantenute distinte dal prezzo pubblico."
                        )[:900],
                    )
                else:
                    fallback=await generic_ota_quote_candidates(page,stay)
                    record["quotes"]=fallback
                    if fallback:
                        record.update(
                            status="quote_candidates_unverified",
                            evidence=(
                                f"Date Trip.com confermate. Il parser delle card non ha attribuito camera e piano, "
                                f"ma sono stati isolati {len(fallback)} importi EUR nel contesto tariffario visibile. "
                                "Restano non validati."
                            )[:900],
                        )
                    else:
                        record.update(
                            status="needs_human_review",
                            evidence="Date Trip.com confermate, ma nessuna card camera/prezzo attribuibile automaticamente con sufficiente certezza."
                        )
            elif channel == "priceline":
                candidates=await priceline_quote_candidates(page,stay)
                record["quotes"]=candidates
                if candidates:
                    first=candidates[0]
                    record.update(
                        status="quote_candidates",
                        evidence=(
                            f"Date Priceline confermate ({date_confirmation_mode or 'date picker'}). "
                            f"Rilevate {len(candidates)} righe camera/prezzo con base tariffaria esplicita. "
                            f"Esempio: {first['roomType']} · €{first['total']:.2f} per {stay['nights']} notti. "
                            "Le tariffe VIP/member restano distinte dal prezzo pubblico."
                        )[:900],
                    )
                else:
                    fallback=await generic_ota_quote_candidates(page,stay)
                    record["quotes"]=fallback
                    if fallback:
                        record.update(
                            status="quote_candidates_unverified",
                            evidence=(
                                f"Date Priceline confermate. Il parser delle card non ha attribuito camera e piano, "
                                f"ma sono stati isolati {len(fallback)} importi EUR nel contesto tariffario visibile. "
                                "Restano non validati."
                            )[:900],
                        )
                    else:
                        record.update(
                            status="needs_human_review",
                            evidence="Date Priceline confermate, ma nessuna card camera/prezzo attribuibile automaticamente con sufficiente certezza."
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
        if soft_http_status and record.get("status") in {"quote_candidates","quote_candidates_unverified"}:
            record["evidence"]=(
                f"HTTP {soft_http_status} iniziale, ma la scheda completa è stata renderizzata nel browser "
                f"con date confermate. {str(record.get('evidence') or '')}"
            )[:900]
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



REVIEW_THEME_RULES = {
    "Mare e posizione": ("posizione","location","mare","spiaggia","beach","vicino al mare","a piedi","walking","centrale","centro"),
    "Pulizia": ("pulizia","pulito","pulita","clean","cleanliness","igiene","sporco","sporca","sporchi","muffa","polvere"),
    "Accoglienza e staff": ("staff","personale","host","proprietario","accoglienza","gentile","disponibile","friendly","helpful","reception"),
    "Colazione": ("colazione","breakfast","buffet","cornetto","caffè","caffe"),
    "Camera e comfort": ("camera","room","letto","bed","materasso","comfort","confort","spaziosa","spazioso","piccola","small"),
    "Bagno e doccia": ("bagno","bathroom","doccia","shower","wc","toilet"),
    "Acqua calda": ("acqua fredda","acqua calda","hot water","cold water","acqua tiepida"),
    "Climatizzazione": ("aria condizionata","condizionatore","air conditioning","a/c","ventilatore","climatizzazione"),
    "Tranquillità e rumore": ("tranquillità","tranquillita","silenzio","quiet","rumore","rumoroso","rumorosa","noise","noisy","insonorizz"),
    "Parcheggio": ("parcheggio","parking","posto auto","garage"),
    "Wi-Fi": ("wifi","wi-fi","internet","connessione"),
    "Rapporto qualità/prezzo": ("qualità prezzo","qualita prezzo","value for money","prezzo","price","costoso","expensive"),
    "Piscina e area relax": ("piscina","pool","spa","jacuzzi","idromassaggio","wellness","relax"),
    "Servizi e dotazioni": ("servizi","services","dotazioni","amenities","ristorante","restaurant"),
    "Manutenzione": ("manutenzione","maintenance","rotto","rotta","broken","vecchio","vecchia","datato","datata","malfunzion"),
}

REVIEW_ACTIONS = {
    "Mare e posizione": "Valorizzare il vantaggio logistico con distanze reali, mappe e tempi a piedi nei canali di vendita.",
    "Pulizia": "Verificare standard, checklist e controllo qualità; se il tema è positivo e ricorrente, valorizzarlo nella comunicazione.",
    "Accoglienza e staff": "Formalizzare standard di benvenuto, tempi di risposta e gestione delle richieste degli ospiti.",
    "Colazione": "Allineare promessa, fotografie, orari e composizione reale della colazione sui diversi canali.",
    "Camera e comfort": "Verificare stanza per stanza dotazioni, comfort e corrispondenza tra descrizione, foto e aspettative.",
    "Bagno e doccia": "Controllare manutenzione, dimensioni percepite, pressione, dotazioni e qualità fotografica dei bagni.",
    "Acqua calda": "Verificare produzione, temperatura e continuità dell'acqua calda nelle fasce di maggiore utilizzo.",
    "Climatizzazione": "Verificare efficienza, manutenzione e corretta comunicazione della climatizzazione per ogni tipologia.",
    "Tranquillità e rumore": "Individuare le camere più esposte e intervenire su insonorizzazione, assegnazione e informazione preventiva.",
    "Parcheggio": "Chiarire disponibilità, costi, distanza e modalità di accesso su sito, OTA e messaggi pre-arrivo.",
    "Wi-Fi": "Verificare copertura reale per aree/camere e allineare la promessa sui canali.",
    "Rapporto qualità/prezzo": "Confrontare prezzo, dotazioni e promessa percepita; intervenire su pricing o presentazione dove il valore non è chiaro.",
    "Piscina e area relax": "Verificare stato, temperatura, pulizia e comunicazione della piscina; valorizzarla se emerge come elemento distintivo.",
    "Servizi e dotazioni": "Allineare servizi realmente disponibili, stagionalità, costi e fotografie su sito e OTA.",
    "Manutenzione": "Aprire una checklist per camera/area con priorità, responsabile e tempi di chiusura dei difetti ricorrenti.",
}

REVIEW_POSITIVE_CUES = (
    "ottim","eccellent","stupend","fantastic","perfett","bellissim","bello","bella","gradevol","piacevol",
    "pulit","impeccabil","curat","comodo","comoda","spazios","tranquill","silenzios","gentil","disponibil",
    "consigliat","buon","buona","super","facile","vicin","relax","meravigli","accoglient","top"
)

REVIEW_NEGATIVE_CUES = (
    "sporco","sporca","sporchi","sporche","muffa","fredd","rumoros","rotto","rotta","rotti","rotte",
    "non funz","malfunzion","assente","assenza","manca","mancava","mancano","mancante","scomodo","scomoda",
    "vecchio","vecchia","vecchi","vecchie","datato","datata","datati","datate","deludent","pessim","male","difficil",
    "odore","costos","caro","cara","lontan","piccol","strett","caldo eccessivo","problema","problemi","peccato",
    "poca pulizia","poco pulit","scarsa pulizia","scarsa manutenzione","trascurat","da rinnovare","da rifare",
    "trattamento da 2","esperienza negativa","unico punto a favore","unico aspetto positivo"
)

REVIEW_NEGATIVE_PATTERNS = (
    r"\bsenza\s+(?:aria\s+condizionata|condizionatore|climatizzazione|frigo(?:\s*bar)?|wifi|wi-fi|internet|acqua\s+calda|ascensore|parcheggio|servizi?)\b",
    r"\b(?:non|mai)\s+(?:funziona|funzionava|pulit[oaie]|disponibile|presente)\b",
    r"\b(?:poca|scarsa)\s+(?:pulizia|igiene|manutenzione|cura)\b",
    r"\b(?:troppo|molto)\s+(?:vecchi[oaie]|rumoros[oaie]|piccol[oaie]|car[oaie])\b",
)

REVIEW_STOPWORDS = {
    "che","con","per","una","uno","un","del","della","delle","dei","degli","nel","nella","nelle","non","sono","era","molto",
    "anche","più","piu","come","ma","si","sì","the","and","for","was","were","very","with","this","that","from","have","had",
    "our","your","you","they","their","hotel","struttura","camera","room","posto","place","stay","soggiorno","giorni","night","nights",
    "altro","alla","tutto","tutti","valutare","viaggio","viaggiovacanza","tornerai","tornerei"
}

def _review_norm(value: str) -> str:
    text=unicodedata.normalize("NFKD",str(value or "")).encode("ascii","ignore").decode("ascii").lower()
    return re.sub(r"\s+"," ",text).strip()

def _review_snippet(value: str, limit: int = 180) -> str:
    text=re.sub(r"\s+"," ",str(value or "")).strip()
    if len(text)<=limit:
        return text
    cut=text[:limit].rsplit(" ",1)[0].rstrip(" ,;:-")
    return cut+"…"

def _review_fragments(text: str) -> list[str]:
    # Google talvolta concatena frasi senza spazio dopo il punto.
    normalized=re.sub(r"([.!?;])(?=[A-ZÀ-Ý0-9])",r"\1 ",str(text or ""))
    pieces=re.split(r"(?<=[.!?;])\s+|\n+",normalized)
    return [re.sub(r"\s+"," ",piece).strip() for piece in pieces if piece and piece.strip()]

def _theme_contexts(fragment: str, keywords: tuple[str,...]) -> list[str]:
    """Isola il contesto vicino al termine che ha attivato il tema.

    Evita che una recensione lunga e negativa venga copiata per intero dentro
    un tema positivo soltanto perché contiene, molto più avanti, una parola come
    'vicino' o 'prezzo'.
    """
    clean=re.sub(r"\s+"," ",str(fragment or "")).strip()
    if not clean:
        return []
    words=clean.split()
    normalized=[_review_norm(word.strip(".,;:!?()[]{}\"'")) for word in words]
    contexts=[]
    seen=set()
    for keyword in keywords:
        key_parts=_review_norm(keyword).split()
        if not key_parts:
            continue
        first=key_parts[0]
        for idx,word in enumerate(normalized):
            if not first or not (first in word or word in first):
                continue
            lo=max(0,idx-5)
            hi=min(len(words),idx+9)
            snippet=" ".join(words[lo:hi]).strip(" ,;:-")
            marker=_review_norm(snippet)
            if snippet and marker not in seen:
                seen.add(marker)
                contexts.append(snippet)
            if len(contexts)>=4:
                return contexts
    return contexts or [clean]

def _local_review_sentiment(fragment: str, star) -> str:
    norm=_review_norm(fragment)
    neg=sum(1 for cue in REVIEW_NEGATIVE_CUES if _review_norm(cue) in norm)
    neg+=sum(1 for pattern in REVIEW_NEGATIVE_PATTERNS if re.search(pattern,norm,re.I))
    pos=sum(1 for cue in REVIEW_POSITIVE_CUES if _review_norm(cue) in norm)

    # Nei costrutti contrastivi ("bello ma vecchio", "pulita però rumorosa")
    # la critica successiva pesa di più sul contesto locale.
    if re.search(r"\b(?:ma|pero|tuttavia|purtroppo)\b",norm):
        tail=re.split(r"\b(?:ma|pero|tuttavia|purtroppo)\b",norm,maxsplit=1)[-1]
        if any(_review_norm(cue) in tail for cue in REVIEW_NEGATIVE_CUES) or any(
            re.search(pattern,tail,re.I) for pattern in REVIEW_NEGATIVE_PATTERNS
        ):
            neg+=2

    if neg and neg>=pos:
        return "negative"
    if pos:
        return "positive"
    # Le stelle sono solo fallback quando il contesto locale non esprime polarità.
    if isinstance(star,(int,float)):
        if star>=4:
            return "positive"
        if star<=3:
            return "negative"
    return "neutral"

def _signal_phrase(fragment: str, keywords: tuple[str,...], sentiment: str) -> str:
    """Restituisce una breve espressione concreta, non una parola generica."""
    clean=re.sub(r"\s+"," ",str(fragment or "")).strip()
    if not clean:
        return ""
    words=clean.split()
    norm_words=[_review_norm(word.strip(".,;:!?()[]{}\"'")) for word in words]
    keyword_tokens=[]
    for keyword in keywords:
        first=_review_norm(keyword).split(" ")[0]
        if first:
            keyword_tokens.append(first)
    hit=None
    for idx,word in enumerate(norm_words):
        if any(token and (token in word or word in token) for token in keyword_tokens):
            hit=idx
            break
    if hit is None:
        return _review_snippet(clean,90)
    lo=max(0,hit-3)
    hi=min(len(words),hit+5)
    phrase=" ".join(words[lo:hi]).strip(" ,;:-")
    return _review_snippet(phrase,100)

def analyze_review_sample(reviews: list[dict]) -> dict:
    theme_stats={
        theme:{
            "positive":0,"negative":0,"neutral":0,
            "examplesPositive":[],"examplesNegative":[],
            "phrasesPositive":[],"phrasesNegative":[]
        } for theme in REVIEW_THEME_RULES
    }
    words={}
    stars=[]
    responses=0

    for review in reviews:
        text=str(review.get("text") or "").strip()
        if not text:
            continue
        star=review.get("stars")
        if isinstance(star,(int,float)) and star>0:
            stars.append(float(star))
        if review.get("hasResponse"):
            responses+=1

        tokens=re.findall(r"[a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ'-]{2,}",text.lower())
        for token in tokens:
            base=_review_norm(token)
            if len(base)<4 or base in REVIEW_STOPWORDS:
                continue
            words[base]=words.get(base,0)+1

        fragments=_review_fragments(text) or [text]
        for theme,keywords in REVIEW_THEME_RULES.items():
            matched_contexts=[]
            for fragment in fragments:
                norm=_review_norm(fragment)
                if any(_review_norm(keyword) in norm for keyword in keywords):
                    matched_contexts.extend(_theme_contexts(fragment,keywords))
            if not matched_contexts:
                continue

            # Un tema conta al massimo una volta per recensione. Sentiment ed esempio
            # vengono calcolati sul contesto vicino alla parola-tema, non sull'intera
            # recensione. Se nello stesso tema compare una critica esplicita, prevale.
            sentiments=[_local_review_sentiment(context,star) for context in matched_contexts]
            if "negative" in sentiments:
                sentiment="negative"
                chosen=matched_contexts[sentiments.index("negative")]
            elif "positive" in sentiments:
                sentiment="positive"
                chosen=matched_contexts[sentiments.index("positive")]
            else:
                sentiment=_local_review_sentiment(matched_contexts[0],star)
                chosen=matched_contexts[0]

            stat=theme_stats[theme]
            stat[sentiment]+=1
            phrase=_signal_phrase(chosen,keywords,sentiment)
            if sentiment=="positive":
                if len(stat["examplesPositive"])<4:
                    stat["examplesPositive"].append(_review_snippet(chosen))
                if phrase and phrase not in stat["phrasesPositive"] and len(stat["phrasesPositive"])<6:
                    stat["phrasesPositive"].append(phrase)
            elif sentiment=="negative":
                if len(stat["examplesNegative"])<4:
                    stat["examplesNegative"].append(_review_snippet(chosen))
                if phrase and phrase not in stat["phrasesNegative"] and len(stat["phrasesNegative"])<6:
                    stat["phrasesNegative"].append(phrase)

    strengths=[]
    weaknesses=[]
    isolated=[]
    recurring_themes=[]
    for theme,stat in theme_stats.items():
        pos=int(stat["positive"])
        neg=int(stat["negative"])

        if pos>=2:
            item={
                "theme":theme,
                "count":pos,
                "weight":"alta" if pos>=4 else "media",
                "phrases":stat["phrasesPositive"][:4],
                "examples":stat["examplesPositive"][:3],
            }
            strengths.append(item)
            recurring_themes.append({**item,"sentiment":"positivo"})

        if neg>=2:
            item={
                "theme":theme,
                "count":neg,
                "weight":"alta" if neg>=3 else "media",
                "phrases":stat["phrasesNegative"][:4],
                "examples":stat["examplesNegative"][:3],
                "action":REVIEW_ACTIONS.get(theme,"Verificare il tema nel dettaglio e definire un intervento misurabile."),
            }
            weaknesses.append(item)
            recurring_themes.append({**item,"sentiment":"negativo"})
        elif neg==1:
            isolated.append({
                "theme":theme,
                "count":1,
                "phrases":stat["phrasesNegative"][:3],
                "examples":stat["examplesNegative"][:2],
                "action":"Monitorare il tema prima di classificarlo come criticità ricorrente.",
            })

    strengths.sort(key=lambda item:(item["count"],item["theme"]),reverse=True)
    weaknesses.sort(key=lambda item:(item["count"],item["theme"]),reverse=True)
    recurring_themes.sort(key=lambda item:(item["count"],item["sentiment"]=="negativo",item["theme"]),reverse=True)
    isolated.sort(key=lambda item:item["theme"])

    # Le parole singole restano solo come supporto diagnostico. Nel frontend
    # mostreremo i temi ricorrenti, che sono molto più utili commercialmente.
    keywords=sorted(words.items(),key=lambda item:(item[1],item[0]),reverse=True)[:18]
    average=round(sum(stars)/len(stars),2) if stars else None
    return {
        "sampleSize":len(reviews),
        "sampleAverage":average,
        "responseCount":responses,
        "responseRate":round(100*responses/len(reviews),1) if reviews else 0,
        "strengths":strengths[:10],
        "weaknesses":weaknesses[:10],
        "isolatedSignals":isolated[:10],
        "recurringThemes":recurring_themes[:14],
        "keywords":[{"word":word,"count":count} for word,count in keywords],
    }

async def google_reputation_observation(context, data: dict) -> dict:
    """Campione pubblico Google Maps: rating, volume, recensioni, temi ed esempi."""
    name=str(data.get("name") or "").strip()
    city=str(data.get("city") or "").strip()
    if not name:
        return {"status":"missing_identity","evidence":"Nome struttura non disponibile per la ricerca Google."}

    query=" ".join(part for part in (name,city) if part).strip()
    url="https://www.google.com/maps/search/?" + urlencode({"api":"1","query":query})
    page=await context.new_page()
    try:
        await page.goto(url,wait_until="domcontentloaded",timeout=30000)
        for selector in (
            "button:has-text('Accetta tutto')","button:has-text('Accetta')",
            "button:has-text('Accept all')","button:has-text('Accept')",
            "button:has-text('Rifiuta tutto')","button:has-text('Reject all')",
        ):
            try:
                loc=page.locator(selector).first
                if await loc.count() and await loc.is_visible(timeout=300):
                    await loc.click(timeout=1200)
                    await page.wait_for_timeout(500)
                    break
            except Exception:
                pass
        await page.wait_for_timeout(3000)

        # Se la ricerca restituisce più luoghi, seleziona il nome più vicino.
        try:
            candidates=page.locator('a[href*="/maps/place/"]')
            count=min(await candidates.count(),40)
            ranked=[]
            for idx in range(count):
                loc=candidates.nth(idx)
                try:
                    txt=re.sub(r"\s+"," ",(await loc.get_attribute("aria-label") or await loc.inner_text(timeout=450) or "")).strip()
                    href=await loc.get_attribute("href") or ""
                    if txt and href:
                        ranked.append((_name_similarity(name,txt),loc,txt,href))
                except Exception:
                    continue
            if ranked:
                ranked.sort(key=lambda item:item[0],reverse=True)
                score,loc,txt,_=ranked[0]
                if score>=0.50:
                    await loc.click(timeout=2400)
                    await page.wait_for_timeout(2600)
        except Exception:
            pass

        observed_name=""
        for selector in ("h1.DUwDvf","h1","[role='main'] h1"):
            try:
                loc=page.locator(selector).first
                if await loc.count() and await loc.is_visible(timeout=350):
                    observed_name=re.sub(r"\s+"," ",await loc.inner_text(timeout=700)).strip()
                    if observed_name:
                        break
            except Exception:
                pass

        # Rating e numero recensioni soltanto dall'header della scheda, mai dalle singole review.
        meta=await page.evaluate(r"""() => {
          const clean=(v)=>String(v||'').replace(/\s+/g,' ').trim();
          const parseRating=(v)=>{
            const m=clean(v).match(/(?:^|\s)([1-5](?:[.,]\d{1,2})?)(?:\s|$)/);
            return m ? m[1] : '';
          };
          const ratingCandidates=[
            document.querySelector('.MW4etd'),
            document.querySelector('.F7nice span[aria-hidden="true"]'),
            document.querySelector('div.F7nice')
          ].filter(Boolean);
          let rating='';
          for (const el of ratingCandidates) {
            const candidate=parseRating(el.textContent);
            if (candidate) { rating=candidate; break; }
          }

          const reviewCandidates=[
            document.querySelector('button[jsaction*="moreReviews"]'),
            document.querySelector('button[aria-label*="recension" i]'),
            document.querySelector('button[aria-label*="review" i]'),
            document.querySelector('.UY7F9')
          ].filter(Boolean);
          let reviews='';
          for (const el of reviewCandidates) {
            const hay=clean((el.getAttribute?.('aria-label')||'')+' '+(el.textContent||''));
            const m=hay.match(/([\d.\s]+)\s*(?:recensioni|reviews)\b/i);
            if (m) { reviews=m[1]; break; }
          }
          return {rating,reviews};
        }""")
        rating=None
        review_count=None
        if meta.get("rating"):
            try:
                rating=float(str(meta["rating"]).replace(",","."))
            except ValueError:
                rating=None
        if meta.get("reviews"):
            digits=re.sub(r"\D+","",str(meta["reviews"]))
            review_count=int(digits) if digits else None

        # Apri esplicitamente la sezione/pannello recensioni e verifica che
        # il click abbia realmente esposto contenuto recensioni.
        review_button=None
        review_button_label=""
        review_open_evidence=""
        try:
            baseline=await page.evaluate(r"""() => ({
              reviewId:document.querySelectorAll('[data-review-id]').length,
              articles:document.querySelectorAll('[role="article"]').length,
              stars:document.querySelectorAll('[role="img"][aria-label*="stell" i], [role="img"][aria-label*="star" i]').length,
              sorters:document.querySelectorAll('button[aria-label*="ordina recensioni" i],button[aria-label*="sort reviews" i]').length
            })""")
        except Exception:
            baseline={"reviewId":0,"articles":0,"stars":0,"sorters":0}

        review_selectors=(
            "[role='tab']:has-text('Recensioni')",
            "[role='tab']:has-text('Reviews')",
            "[role='tab'][aria-label*='recension' i]",
            "[role='tab'][aria-label*='review' i]",
            "button[jsaction*='moreReviews']",
            "button[aria-label*='recension' i]",
            "button[aria-label*='review' i]",
            "button:has-text('recensioni')",
            "button:has-text('reviews')",
        )
        opened=False
        for selector in review_selectors:
            try:
                locs=page.locator(selector)
                count=min(await locs.count(),25)
            except Exception:
                continue
            for idx in range(count):
                item=locs.nth(idx)
                try:
                    if not await item.is_visible(timeout=250):
                        continue
                    label=re.sub(r"\s+"," ",(
                        await item.get_attribute("aria-label")
                        or await item.inner_text(timeout=350)
                        or selector
                    )).strip()[:180]
                    try:
                        await item.click(timeout=2200)
                    except Exception:
                        await item.click(timeout=1600,force=True)
                    await page.wait_for_timeout(1800)
                    try:
                        state=await page.evaluate(r"""() => ({
                          reviewId:document.querySelectorAll('[data-review-id]').length,
                          articles:document.querySelectorAll('[role="article"]').length,
                          stars:document.querySelectorAll('[role="img"][aria-label*="stell" i], [role="img"][aria-label*="star" i]').length,
                          sorters:document.querySelectorAll('button[aria-label*="ordina recensioni" i],button[aria-label*="sort reviews" i]').length,
                          recentText:/più recenti|most recent|newest/i.test(document.body.innerText||'')
                        })""")
                    except Exception:
                        state={}
                    review_button=item
                    review_button_label=label
                    review_open_evidence=(
                        f"{selector} → reviewId={state.get('reviewId',0)}, "
                        f"articles={state.get('articles',0)}, stars={state.get('stars',0)}, "
                        f"sort={state.get('sorters',0)}"
                    )
                    opened=bool(
                        state.get("reviewId",0)>baseline.get("reviewId",0)
                        or state.get("articles",0)>baseline.get("articles",0)
                        or state.get("stars",0)>baseline.get("stars",0)+1
                        or state.get("sorters",0)>0
                        or state.get("recentText")
                    )
                    if opened:
                        break
                except Exception:
                    continue
            if opened:
                break

        if review_button is not None and not opened:
            try:
                await review_button.focus(timeout=1000)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(1600)
                review_open_evidence += " · retry Enter"
            except Exception:
                pass

        # Ordina per più recenti quando disponibile.
        try:
            sort_button=None
            for selector in (
                "button[aria-label*='ordina recensioni' i]","button[aria-label*='sort reviews' i]",
                "button[jsaction*='reviewSort']","button:has-text('Ordina')","button:has-text('Sort')",
            ):
                loc=page.locator(selector).first
                if await loc.count() and await loc.is_visible(timeout=250):
                    sort_button=loc; break
            if sort_button is not None:
                await sort_button.click(timeout=1600)
                await page.wait_for_timeout(550)
                for selector in (
                    "[role='menuitemradio']:has-text('Più recenti')",
                    "[role='menuitemradio']:has-text('Newest')",
                    "div[role='menuitemradio']:has-text('Più recenti')",
                ):
                    opt=page.locator(selector).first
                    if await opt.count() and await opt.is_visible(timeout=250):
                        await opt.click(timeout=1600)
                        await page.wait_for_timeout(1200)
                        break
        except Exception:
            pass

        card_selector="div.jftiEf[data-review-id], div[data-review-id], div.jftiEf, div[role=\"article\"]"
        # Carica un campione consistente; scroll del pannello recensioni, non della pagina generica.
        for _ in range(12):
            try:
                cards=page.locator(card_selector)
                count=await cards.count()
                if count:
                    last=cards.nth(count-1)
                    await last.scroll_into_view_if_needed(timeout=1300)
                    try:
                        await page.evaluate(r"""(el) => {
                          let p=el;
                          while (p && p!==document.body) {
                            const st=getComputedStyle(p);
                            if (/(auto|scroll)/.test(st.overflowY) && p.scrollHeight>p.clientHeight+50) {
                              p.scrollTop=p.scrollHeight;
                              break;
                            }
                            p=p.parentElement;
                          }
                        }""",await last.element_handle())
                    except Exception:
                        pass
                await page.wait_for_timeout(650)
            except Exception:
                break

        # Espandi il testo delle recensioni visibili.
        try:
            more=page.locator("button:has-text('Altro'), button:has-text('More')")
            for idx in range(min(await more.count(),35)):
                item=more.nth(idx)
                try:
                    if await item.is_visible(timeout=120):
                        await item.click(timeout=600)
                except Exception:
                    pass
        except Exception:
            pass

        reviews=[]
        try:
            reviews=await page.evaluate(r"""() => {
              const clean=(v)=>String(v||'').replace(/\s+/g,' ').trim();
              let cards=Array.from(document.querySelectorAll('div.jftiEf[data-review-id], div[data-review-id], div.jftiEf, div[role="article"]'));
              if (!cards.length) {
                const starNodes=Array.from(document.querySelectorAll('[role="img"][aria-label*="stell" i], [role="img"][aria-label*="star" i]'));
                const inferred=[];
                for (const star of starNodes) {
                  let node=star.parentElement;
                  for (let depth=0; node && depth<7; depth+=1, node=node.parentElement) {
                    const text=(node.innerText || node.textContent || '').replace(/\s+/g,' ').trim();
                    if (text.length>=25 && text.length<=3500 && (
                      node.querySelector('.wiI7pd,[data-review-text],span[jsname="bN97Pc"],.MyEned') ||
                      /(giorn|settiman|mes|ann|day|week|month|year)/i.test(text)
                    )) {
                      inferred.push(node);
                      break;
                    }
                  }
                }
                cards=inferred;
              }
              const seen=new Set();
              const out=[];
              for (const card of cards) {
                const id=card.getAttribute('data-review-id') || clean(card.textContent).slice(0,120);
                if (!id || seen.has(id)) continue;
                seen.add(id);
                const textNode=card.querySelector('.wiI7pd,[data-review-text],span[jsname="bN97Pc"],.MyEned,[class*="review-text"]');
                let text=clean(textNode?.textContent || '');
                if (!text) {
                  const rawLines=String(card.innerText || card.textContent || '').split(/\n+/).map(clean).filter(Boolean);
                  const filtered=rawLines.filter((line) => {
                    const low=line.toLowerCase();
                    if (line.length<4) return false;
                    if (/^\d(?:[.,]\d)?$/.test(line)) return false;
                    if (/^\d+\s*(?:recensioni|reviews)$/i.test(line)) return false;
                    if (/(?:stella|stelle|star|stars)$/i.test(line)) return false;
                    if (/^(?:local guide|guida locale)$/i.test(line)) return false;
                    if (/^(?:altro|more|condividi|share|mi piace|like)$/i.test(line)) return false;
                    if (/^(?:\d+|una|un)\s+(?:giorn|settiman|mes|ann|day|week|month|year)/i.test(low)) return false;
                    return true;
                  });
                  if (filtered.length>2) filtered.shift();
                  text=clean(filtered.join(' '));
                }
                if (!text) continue;
                const starNode=card.querySelector('span[role="img"][aria-label*="stell" i],span[role="img"][aria-label*="star" i],[role="img"][aria-label*="stell" i],[role="img"][aria-label*="star" i]');
                const starAria=clean(starNode?.getAttribute('aria-label'));
                const starMatch=starAria.match(/([1-5](?:[.,]\d)?)/);
                const dateNode=card.querySelector('.rsqaWe,.xRkPPb,.DU9Pgb');
                const hasResponse=!!card.querySelector('.CDe7pd,[data-review-owner-response],.wiI7pd + div .CDe7pd');
                out.push({
                  text:text.slice(0,2200),
                  stars:starMatch ? Number(starMatch[1].replace(',','.')) : null,
                  date:clean(dateNode?.textContent).slice(0,100),
                  hasResponse
                });
                if (out.length>=60) break;
              }
              return out;
            }""")
        except Exception:
            reviews=[]

        # Se la scheda espone un bottone recensioni ma non abbiamo estratto card,
        # non inventare rating/analisi: rendi il limite esplicito.
        analysis=analyze_review_sample(reviews)
        try:
            dom_diag=await page.evaluate(r"""() => ({
              reviewId:document.querySelectorAll('[data-review-id]').length,
              articles:document.querySelectorAll('[role="article"]').length,
              stars:document.querySelectorAll('[role="img"][aria-label*="stell" i], [role="img"][aria-label*="star" i]').length
            })""")
            print(
                f"reputation dom: reviewId={dom_diag.get('reviewId',0)} · articles={dom_diag.get('articles',0)} · stars={dom_diag.get('stars',0)}",
                flush=True,
            )
        except Exception:
            pass
        preview=" | ".join(_review_snippet(str(item.get("text") or ""),110) for item in reviews[:2])
        print(
            f"reputation open: {review_open_evidence or 'nessun cambio DOM confermato'}",
            flush=True,
        )
        print(
            f"reputation diagnostics: name={observed_name or name} · button={review_button_label or 'n.d.'} · "
            f"rating={rating if rating is not None else 'n.d.'} · reviews={review_count if review_count is not None else 'n.d.'} · "
            f"cards={len(reviews)} · preview={preview[:260]} · url={page.url[:260]}",
            flush=True,
        )
        return {
            "status":"sampled" if reviews else "listing_found_no_reviews",
            "source":"Google Maps pubblico",
            "url":page.url,
            "name":observed_name or name,
            "rating":rating,
            "reviewCount":review_count,
            **analysis,
            "evidence":(
                f"Google Maps: scheda «{observed_name or name}»; "
                f"rating {rating if rating is not None else 'n.d.'}; "
                f"recensioni totali {review_count if review_count is not None else 'n.d.'}; "
                f"campione testuale analizzato {len(reviews)}."
            )[:900],
        }
    except Exception as exc:
        return {
            "status":"error","source":"Google Maps pubblico","url":page.url if page else url,
            "evidence":f"Analisi Google non completata: {type(exc).__name__}: {str(exc)[:180]}",
            "sampleSize":0,"strengths":[],"weaknesses":[],"isolatedSignals":[],"keywords":[],
        }
    finally:
        try:
            await page.close()
        except Exception:
            pass

async def frontend_photo_audit(context, data: dict, robots: dict) -> dict:
    """Audit fotografico frontend multi-pagina: img, lazy-load e background CSS pubblici."""
    source=((data.get("sources") or {}).get("sito") or {}).get("url","")
    if not source:
        return {"status":"source_missing","score":0,"evidence":"Sito ufficiale non disponibile."}
    permission=await asyncio.to_thread(allowed_by_robots,source,robots)
    if permission is not True:
        return {"status":"robots_denied","score":0,"evidence":"Sito ufficiale non analizzato per immagini: robots.txt non consente o non chiarisce l'accesso."}

    base_host=(urlparse(source).hostname or "").lower().removeprefix("www.")
    page=await context.new_page()
    try:
        pages=[source]
        seen_pages=set()
        collected=[]
        page_summaries=[]

        async def inspect_page(target: str):
            response=await page.goto(target,wait_until="domcontentloaded",timeout=25000)
            await dismiss_cookie(page)
            # Stimola lazy-loading con scroll progressivo.
            try:
                for ratio in (0.25,0.55,0.85,1.0):
                    await page.evaluate("(r)=>window.scrollTo(0, Math.floor(document.body.scrollHeight*r))",ratio)
                    await page.wait_for_timeout(350)
                await page.evaluate("window.scrollTo(0,0)")
            except Exception:
                pass
            await page.wait_for_timeout(650)
            payload=await page.evaluate(r"""() => {
              const abs=(u)=>{try{return new URL(u,location.href).href}catch{return ''}};
              const clean=(v)=>String(v||'').replace(/\s+/g,' ').trim();
              const pickSrc=(img)=>{
                const attrs=[
                  img.currentSrc,img.src,img.getAttribute('data-src'),img.getAttribute('data-lazy-src'),
                  img.getAttribute('data-original'),img.getAttribute('data-bg')
                ].filter(Boolean);
                if (attrs.length) return abs(attrs[0]);
                const srcset=img.getAttribute('srcset') || img.getAttribute('data-srcset') || '';
                if (srcset) {
                  const parts=srcset.split(',').map(x=>x.trim().split(/\s+/)[0]).filter(Boolean);
                  if (parts.length) return abs(parts[parts.length-1]);
                }
                return '';
              };
              const images=[];
              for (const img of Array.from(document.querySelectorAll('img')).slice(0,450)) {
                const r=img.getBoundingClientRect();
                const src=pickSrc(img);
                if (!src || src.startsWith('data:')) continue;
                images.push({
                  src, alt:clean(img.alt).slice(0,180),
                  naturalWidth:Number(img.naturalWidth||0), naturalHeight:Number(img.naturalHeight||0),
                  displayedWidth:Math.round(r.width||img.clientWidth||0), displayedHeight:Math.round(r.height||img.clientHeight||0),
                  kind:'img'
                });
              }
              for (const source of Array.from(document.querySelectorAll('picture source[srcset], source[data-srcset]')).slice(0,150)) {
                const raw=source.getAttribute('srcset') || source.getAttribute('data-srcset') || '';
                const parts=raw.split(',').map(x=>x.trim().split(/\s+/)[0]).filter(Boolean);
                if (!parts.length) continue;
                images.push({src:abs(parts[parts.length-1]),alt:'',naturalWidth:0,naturalHeight:0,displayedWidth:0,displayedHeight:0,kind:'srcset'});
              }
              for (const el of Array.from(document.querySelectorAll('body *')).slice(0,1800)) {
                const bg=getComputedStyle(el).backgroundImage || '';
                if (!bg || bg==='none') continue;
                const m=bg.match(/url\(["']?([^"')]+)["']?\)/);
                if (!m) continue;
                const r=el.getBoundingClientRect();
                if (r.width<280 || r.height<120) continue;
                images.push({
                  src:abs(m[1]),alt:clean(el.getAttribute('aria-label')||el.getAttribute('title')||'').slice(0,180),
                  naturalWidth:0,naturalHeight:0,displayedWidth:Math.round(r.width),displayedHeight:Math.round(r.height),kind:'background'
                });
              }
              const og=document.querySelector('meta[property="og:image"]')?.content || document.querySelector('meta[name="twitter:image"]')?.content || '';
              if (og) images.push({src:abs(og),alt:'hero social',naturalWidth:0,naturalHeight:0,displayedWidth:1200,displayedHeight:630,kind:'meta'});
              const links=Array.from(document.querySelectorAll('a[href]')).slice(0,600).map(a=>({
                href:abs(a.getAttribute('href')||''),text:clean(a.innerText||a.getAttribute('aria-label')||'').slice(0,160)
              })).filter(x=>x.href);
              return {images,links,title:document.title||''};
            }""")
            return response,payload

        # Home + pagine editorialmente rilevanti dello stesso sito.
        while pages and len(seen_pages)<7:
            target=pages.pop(0)
            norm=target.split("#")[0]
            if norm in seen_pages:
                continue
            seen_pages.add(norm)
            try:
                response,payload=await inspect_page(norm)
            except Exception:
                continue
            page_title=str(payload.get("title") or "")[:180]
            page_summaries.append({"url":page.url,"title":page_title,"status":getattr(response,"status",None)})
            for image_item in (payload.get("images") or []):
                enriched=dict(image_item)
                enriched["pageUrl"]=page.url
                enriched["pageTitle"]=page_title
                collected.append(enriched)

            ranked=[]
            for link in payload.get("links") or []:
                href=str(link.get("href") or "").split("#")[0]
                parsed=urlparse(href)
                host=(parsed.hostname or "").lower().removeprefix("www.")
                if parsed.scheme not in {"http","https"} or host!=base_host or href in seen_pages:
                    continue
                hay=_review_norm((link.get("text") or "")+" "+parsed.path)
                score=sum(1 for word in (
                    "gallery","galleria","foto","photo","camere","camera","room","rooms","suite",
                    "servizi","services","piscina","pool","spa","wellness","colazione","breakfast",
                    "ristorante","restaurant","struttura","hotel","agriturismo"
                ) if word in hay)
                if score:
                    ranked.append((score,href))
            ranked.sort(reverse=True)
            for _,href in ranked[:5]:
                if href not in pages and href not in seen_pages:
                    pages.append(href)

        unique={}
        for item in collected:
            src=str(item.get("src") or "")
            if not src or src.startswith("data:"):
                continue
            key=re.sub(r"[?#].*$","",src).lower()
            if key and key not in unique:
                unique[key]=item
            elif key:
                # conserva le dimensioni migliori viste sulla stessa immagine
                previous=unique[key]
                if max(int(item.get("naturalWidth") or 0),int(item.get("displayedWidth") or 0)) > max(int(previous.get("naturalWidth") or 0),int(previous.get("displayedWidth") or 0)):
                    unique[key]=item

        images=list(unique.values())
        relevant=[]
        for img in images:
            width=max(int(img.get("naturalWidth") or 0),int(img.get("displayedWidth") or 0))
            height=max(int(img.get("naturalHeight") or 0),int(img.get("displayedHeight") or 0))
            path=(urlparse(str(img.get("src") or "")).path or "").lower()
            looks_image=bool(re.search(r"\.(?:jpe?g|png|webp|avif)(?:$|/)",path))
            if width>=420 or (looks_image and (height>=240 or str(img.get("kind")) in {"srcset","meta"})):
                relevant.append(img)

        dimension_known=[img for img in relevant if int(img.get("naturalWidth") or 0)>0 and int(img.get("naturalHeight") or 0)>0]
        highres=[img for img in dimension_known if int(img.get("naturalWidth") or 0)>=1200 and int(img.get("naturalHeight") or 0)>=700]
        alt_ok=[img for img in relevant if len(str(img.get("alt") or "").strip())>=4 and str(img.get("alt") or "").lower() not in {"image","foto","photo"}]

        categories={
            "camere":("camera","room","suite","bed","letto"),
            "bagni":("bagno","bathroom","doccia","shower"),
            "esterni":("esterno","exterior","facciata","garden","giardino","terrazza","terrace"),
            "piscina/wellness":("piscina","pool","spa","wellness","jacuzzi","idromassaggio"),
            "colazione/food":("colazione","breakfast","restaurant","ristorante","food","cucina"),
            "esperienza/lifestyle":("ospiti","guest","couple","coppia","family","famiglia","experience","lifestyle"),
        }
        category_counts={key:0 for key in categories}
        for img in relevant:
            hay=_review_norm(
                (img.get("alt") or "")+" "+(img.get("src") or "")+" "+
                (img.get("pageTitle") or "")+" "+(img.get("pageUrl") or "")
            )
            for key,words in categories.items():
                if any(_review_norm(word) in hay for word in words):
                    category_counts[key]+=1

        total=len(relevant)
        covered=sum(1 for value in category_counts.values() if value>0)
        known_ratio=(len(dimension_known)/total) if total else 0
        highres_ratio=(len(highres)/len(dimension_known)) if dimension_known else 0
        alt_ratio=(len(alt_ok)/total) if total else 0

        # Punteggio solo su segnali effettivamente osservabili. Se le dimensioni
        # naturali non sono disponibili, la componente risoluzione pesa meno.
        volume_score=min(1.0,total/24) * 2.0
        semantic_evidence=sum(
            1 for img in relevant
            if len(str(img.get("alt") or "").strip())>=4
            or any(word in _review_norm((img.get("pageTitle") or "")+" "+(img.get("pageUrl") or ""))
                   for words in categories.values() for word in map(_review_norm,words))
        )
        coverage_weight=3.5 if semantic_evidence>=max(3,min(6,total//3 if total else 0)) else 0.0
        coverage_score=(covered/max(1,len(categories))) * coverage_weight if coverage_weight else 0.0
        metadata_score=min(1.0,alt_ratio/0.7) * 1.5
        resolution_weight=2.0 if known_ratio>=0.35 else 0.8
        resolution_score=min(1.0,highres_ratio/0.65) * resolution_weight
        visual_presence=sum(1 for img in relevant if int(img.get("displayedWidth") or 0)>=900 or str(img.get("kind")) in {"background","meta"})
        hero_score=min(1.0,visual_presence/4) * 1.0
        max_score=2.0+coverage_weight+1.5+resolution_weight+1.0
        raw=volume_score+coverage_score+metadata_score+resolution_score+hero_score
        score=round(10*raw/max_score,1) if total else 0.0

        strengths=[]
        gaps=[]
        if total>=20: strengths.append(f"Buona ampiezza del campione fotografico ({total} immagini rilevanti su {len(page_summaries)} pagine).")
        elif total: gaps.append(f"Copertura fotografica limitata nel campione ({total} immagini rilevanti su {len(page_summaries)} pagine).")
        else: gaps.append(f"Nessuna immagine editoriale rilevante isolata automaticamente nelle {len(page_summaries)} pagine campionate.")
        if dimension_known:
            if highres_ratio>=0.6: strengths.append(f"Buona quota di immagini con dimensioni note ad alta risoluzione ({len(highres)}/{len(dimension_known)}).")
            else: gaps.append(f"Solo {len(highres)}/{len(dimension_known)} immagini con dimensioni note raggiungono almeno 1200×700 px.")
        else:
            gaps.append("Dimensioni naturali non esposte dal frontend: la risoluzione non può essere giudicata con certezza.")
        if total:
            if alt_ratio>=0.65: strengths.append(f"Alt text utile su una quota significativa delle immagini ({len(alt_ok)}/{total}).")
            else: gaps.append(f"Alt text assente o poco descrittivo su molte immagini ({len(alt_ok)}/{total} utili).")
        missing=[key for key,value in category_counts.items() if value==0]
        if covered>=4: strengths.append("Il campione copre più aree dell'esperienza, non soltanto le camere.")
        if missing:
            if coverage_weight:
                gaps.append("Categorie non chiaramente riconoscibili da metadati/URL/pagina: "+", ".join(missing)+".")
            else:
                gaps.append("Copertura semantica delle immagini non valutabile con sufficiente certezza: metadati e contesto pagina sono troppo poveri per penalizzare la gallery.")

        actions=[]
        if "esperienza/lifestyle" in missing: actions.append("Integrare immagini lifestyle con persone e momenti d'uso reali.")
        if "bagni" in missing: actions.append("Assicurare almeno una fotografia chiara del bagno per ogni tipologia.")
        if dimension_known and highres_ratio<0.6: actions.append("Sostituire le immagini a bassa risoluzione nelle posizioni principali.")
        if total and alt_ratio<0.65: actions.append("Scrivere alt text descrittivi e coerenti con tipologie e servizi.")
        if total<20: actions.append("Ampliare la copertura fotografica di camere, servizi, esterni e dettagli.")
        if not actions: actions.append("Verificare ora ordine gallery, luce, styling e coerenza visiva tra sito e OTA.")

        return {
            "status":"sampled" if total else "no_images_isolated",
            "source":"Sito ufficiale","url":source,"score":score,
            "pagesSampled":len(page_summaries),"imageCount":total,
            "knownDimensionCount":len(dimension_known),"highResolutionCount":len(highres),"altTextCount":len(alt_ok),
            "categoryCounts":category_counts,
            "components":{
                "volume":round(volume_score,2),
                "resolution":round(resolution_score,2),
                "metadata":round(metadata_score,2),
                "coverage":round(coverage_score,2),
                "hero":round(hero_score,2),
            },
            "strengths":strengths,"gaps":gaps,"actions":actions,
            "evidence":(
                f"Audit fotografico frontend multi-pagina: {len(page_summaries)} pagine, {total} immagini rilevanti, "
                f"{len(dimension_known)} con dimensioni naturali note, {len(highres)} ad alta risoluzione, "
                f"{len(alt_ok)} con alt text utile, {covered}/{len(categories)} categorie riconoscibili "
                f"(copertura {'conteggiata' if coverage_weight else 'non penalizzata per bassa confidenza semantica'}). "
                "Il punteggio usa solo segnali frontend osservabili; luce, composizione e styling richiedono lettura visiva."
            )[:900],
        }
    except Exception as exc:
        return {"status":"error","score":0,"evidence":f"Audit fotografico non completato: {type(exc).__name__}: {str(exc)[:180]}"}
    finally:
        try:
            await page.close()
        except Exception:
            pass



ROOM_GENERIC_TOKENS={
    "camera","camere","room","rooms","chambre","habitacion","stanza","alloggio",
    "con","with","per","the","di","da","del","della","and","e","accesso"
}
ROOM_CANONICAL_TOKENS={
    "matrimoniale":"double","doppia":"double","double":"double",
    "quadrupla":"quadruple","quadruple":"quadruple","quad":"quadruple",
    "tripla":"triple","triple":"triple",
    "singola":"single","single":"single",
    "familiare":"family","family":"family",
    "appartamento":"apartment","apartment":"apartment",
    "suite":"suite","junior":"junior","deluxe":"deluxe","superior":"superior","standard":"standard",
    "twin":"twin","queen":"queen","king":"king",
    "disabili":"accessible","disabile":"accessible","accessibile":"accessible","accessible":"accessible",
}
ROOM_CAPACITY_TOKENS={"single","double","triple","quadruple","family","twin"}


def _room_signature(value: str) -> dict:
    norm=_norm_name(value)
    raw_tokens=[token for token in norm.split() if token]
    tokens=[]
    for token in raw_tokens:
        canonical=ROOM_CANONICAL_TOKENS.get(token,token)
        if canonical in ROOM_GENERIC_TOKENS or len(canonical)<2:
            continue
        tokens.append(canonical)
    informative=[token for token in tokens if token not in {"letto","letti","bed","beds","ospiti","guest","guests"}]
    capacities={token for token in informative if token in ROOM_CAPACITY_TOKENS}
    return {
        "text":" ".join(informative),
        "tokens":set(informative),
        "capacities":capacities,
    }


def _room_match_score(reference: str, candidate: str) -> float:
    ref=_room_signature(reference)
    cand=_room_signature(candidate)
    if not ref["tokens"] or not cand["tokens"]:
        return 0.0
    if ref["capacities"] and cand["capacities"] and ref["capacities"].isdisjoint(cand["capacities"]):
        return 0.0
    inter=len(ref["tokens"] & cand["tokens"])
    union=len(ref["tokens"] | cand["tokens"])
    jaccard=inter/union if union else 0.0
    sequence=SequenceMatcher(None,ref["text"],cand["text"]).ratio()
    contains=1.0 if ref["text"] in cand["text"] or cand["text"] in ref["text"] else 0.0
    capacity_bonus=0.10 if ref["capacities"] and ref["capacities"]==cand["capacities"] else 0.0
    return round(min(1.0,0.48*sequence+0.42*jaccard+0.10*contains+capacity_bonus),3)


def _quote_nightly_value(quote: dict) -> float:
    try:
        nightly=quote.get("nightlyRate")
        if nightly is not None:
            return float(nightly)
        return float(quote.get("total") or 0)/max(1,int(quote.get("nights") or 1))
    except Exception:
        return 999999.0


def _usable_room_name(value: str) -> bool:
    norm=_norm_name(value)
    return bool(
        norm
        and norm not in {"tipologia camera da verificare","camera da verificare","room to verify","da verificare"}
        and "verificare" not in norm
    )


def apply_booking_room_reference(result: dict) -> None:
    """Seleziona una camera Booking reference e una sola famiglia comparabile per ogni OTA/data.

    - Booking è sempre il punto di partenza.
    - Se una OTA espone la stessa tipologia, vengono selezionate solo le righe di quella tipologia.
    - Se non esiste una corrispondenza sufficientemente forte, viene mostrata una sola tariffa alternativa
      con avviso esplicito e senza referenceRoomKey: quindi non può produrre delta.
    """
    observations=result.get("observations") or []
    stays={}
    for obs in observations:
        key=(str(obs.get("checkin") or ""),str(obs.get("checkout") or ""))
        if not all(key):
            continue
        stays.setdefault(key,[]).append(obs)

    room_references=[]
    for (checkin,checkout),group in stays.items():
        booking_quotes=[]
        for obs in group:
            if obs.get("otaId")!="booking":
                continue
            for quote in obs.get("quotes") or []:
                if quote.get("verified") and _usable_room_name(str(quote.get("roomType") or "")):
                    booking_quotes.append(quote)
        if not booking_quotes:
            continue

        # Candidati Booking unici per nome stanza; sceglie quello che ha più corrispondenze
        # sulle altre OTA. A parità usa la tariffa/notte più bassa.
        room_candidates={}
        for quote in booking_quotes:
            room=str(quote.get("roomType") or "").strip()
            sig=_room_signature(room)["text"] or _norm_name(room)
            old=room_candidates.get(sig)
            if old is None or _quote_nightly_value(quote)<_quote_nightly_value(old):
                room_candidates[sig]=quote

        scored=[]
        for sig,booking_quote in room_candidates.items():
            room=str(booking_quote.get("roomType") or "")
            matched_otas=set()
            best_scores={}
            for obs in group:
                ota_id=str(obs.get("otaId") or "")
                if ota_id=="booking":
                    continue
                best=0.0
                for quote in obs.get("quotes") or []:
                    if not quote.get("verified"):
                        continue
                    candidate_room=str(quote.get("roomType") or "")
                    if not _usable_room_name(candidate_room):
                        continue
                    best=max(best,_room_match_score(room,candidate_room))
                best_scores[ota_id]=best
                if best>=0.74:
                    matched_otas.add(ota_id)
            scored.append((
                len(matched_otas),
                -_quote_nightly_value(booking_quote),
                sig,
                booking_quote,
                best_scores,
            ))
        scored.sort(reverse=True,key=lambda row:(row[0],row[1]))
        match_count,_,reference_sig,reference_quote,best_scores=scored[0]
        reference_room=str(reference_quote.get("roomType") or "").strip()
        reference_key=f"booking-ref:{checkin}:{reference_sig}"

        room_references.append({
            "checkin":checkin,
            "checkout":checkout,
            "roomType":reference_room,
            "referenceRoomKey":reference_key,
            "matchedOtas":match_count,
            "evidence":(
                f"Camera reference scelta da Booking: {reference_room}. "
                f"Corrispondenza sufficientemente forte rilevata su {match_count} OTA."
            ),
        })

        for obs in group:
            ota_id=str(obs.get("otaId") or "")
            quotes=obs.get("quotes") or []
            if not quotes:
                continue
            for quote in quotes:
                quote["comparisonSelected"]=False
                quote["bookingReferenceRoom"]=reference_room
                quote["referenceRoomKey"]=""
                quote["roomMatchScore"]=0.0
                quote["roomMatchStatus"]="not-selected"
                quote["comparisonWarning"]=""

            if ota_id=="booking":
                selected=[]
                for quote in quotes:
                    score=_room_match_score(reference_room,str(quote.get("roomType") or ""))
                    if score>=0.90:
                        quote["comparisonSelected"]=True
                        quote["referenceRoomKey"]=reference_key
                        quote["roomMatchScore"]=score
                        quote["roomMatchStatus"]="booking-reference"
                        selected.append(quote)
                if not selected:
                    reference_quote["comparisonSelected"]=True
                    reference_quote["referenceRoomKey"]=reference_key
                    reference_quote["roomMatchScore"]=1.0
                    reference_quote["roomMatchStatus"]="booking-reference"
                continue

            room_groups={}
            for quote in quotes:
                if not quote.get("verified"):
                    continue
                room=str(quote.get("roomType") or "")
                if not _usable_room_name(room):
                    continue
                sig=_room_signature(room)["text"] or _norm_name(room)
                room_groups.setdefault(sig,[]).append(quote)

            best_sig=""
            best_score=0.0
            for sig,items in room_groups.items():
                score=max(_room_match_score(reference_room,str(item.get("roomType") or "")) for item in items)
                if score>best_score:
                    best_score=score
                    best_sig=sig

            if best_sig and best_score>=0.74:
                for quote in room_groups[best_sig]:
                    quote["comparisonSelected"]=True
                    quote["referenceRoomKey"]=reference_key
                    quote["roomMatchScore"]=best_score
                    quote["roomMatchStatus"]="same-room"
            else:
                # Nessuna camera uguale: mostra UNA sola alternativa utile, preferendo
                # una riga verificata e poi il prezzo/notte più basso.
                candidates=[quote for quote in quotes if _usable_room_name(str(quote.get("roomType") or ""))]
                if not candidates:
                    candidates=list(quotes)
                if candidates:
                    fallback=sorted(
                        candidates,
                        key=lambda quote:(0 if quote.get("verified") else 1,_quote_nightly_value(quote))
                    )[0]
                    fallback["comparisonSelected"]=True
                    fallback["referenceRoomKey"]=""
                    fallback["roomMatchScore"]=_room_match_score(reference_room,str(fallback.get("roomType") or ""))
                    fallback["roomMatchStatus"]="different-room-fallback"
                    fallback["comparisonWarning"]=(
                        f"ATTENZIONE: camera diversa dalla reference Booking «{reference_room}». "
                        "Mostrata solo perché su questa OTA non è stata trovata la stessa tipologia; "
                        "questa tariffa non entra nel delta comparativo."
                    )

    # Una mancata corrispondenza con la camera reference non è motivo
    # per nascondere tariffe pubbliche realmente osservate.
    for observation in observations:
        for quote in observation.get("quotes") or []:
            if quote.get("comparisonSelected") is False:
                quote["comparisonSelected"]=True
                if observation.get("otaId")!="booking" and not quote.get("referenceRoomKey"):
                    quote["comparisonWarning"]=(
                        "Tariffa OTA conservata integralmente. Camera o condizioni "
                        "non necessariamente comparabili con la reference Booking; "
                        "eventuali delta devono essere marcati come indicativi."
                    )
    result["roomReferences"]=room_references



def _browser_closed_exception(exc: Exception) -> bool:
    lowered=f"{type(exc).__name__}: {str(exc)}".lower()
    return (
        "targetclosederror" in lowered
        or "target page, context or browser has been closed" in lowered
        or "context or browser has been closed" in lowered
        or "browser has been closed" in lowered
        or "browsercontext.new_page" in lowered and "closed" in lowered
    )



async def _set_interaction_window(page, visible: bool) -> None:
    """Mostra o minimizza Chrome senza cambiare pagina/sessione."""
    try:
        await page.bring_to_front()
    except Exception:
        pass
    try:
        cdp=await page.context.new_cdp_session(page)
        info=await cdp.send("Browser.getWindowForTarget")
        if visible:
            await cdp.send("Browser.setWindowBounds",{
                "windowId":info["windowId"],
                "bounds":{"windowState":"normal","left":80,"top":60,"width":1380,"height":920},
            })
        else:
            await cdp.send("Browser.setWindowBounds",{
                "windowId":info["windowId"],
                "bounds":{"windowState":"minimized"},
            })
        await cdp.detach()
    except Exception:
        pass


async def _human_assist(page, callback, payload: dict, ghost: bool = False) -> str:
    """Handoff esplicito all'utente. Nessun CAPTCHA o login viene automatizzato."""
    if not callable(callback):
        return "disabled"
    payload=dict(payload or {})
    payload.setdefault("url",str(page.url or ""))
    payload.setdefault("requestedAt",datetime.now(timezone.utc).isoformat())
    await _set_interaction_window(page,True)
    print(
        f"ASSISTENZA UMANA RICHIESTA · {payload.get('label') or payload.get('otaId') or 'OTA'} · "
        f"{str(payload.get('reason') or '')[:220]}",
        flush=True,
    )
    try:
        action=await asyncio.to_thread(callback,payload)
    except Exception as exc:
        print(f"assistenza umana non disponibile: {type(exc).__name__}: {str(exc)[:160]}",flush=True)
        action="error"
    return str(action or "timeout").lower()


async def _current_page_identity(page, ota_id: str, data: dict) -> dict:
    """Verifica la pagina lasciata aperta dall'utente senza rinavigare."""
    try:
        url=str(page.url or "")
        title=(await page.title())[:260]
        body=(await page.locator("body").inner_text(timeout=6000))[:18000]
    except Exception:
        return {"ok":False,"url":str(getattr(page,"url","") or ""),"title":"","evidence":"Pagina non leggibile dopo l'intervento."}
    if _classify_ota_url(url)!=ota_id or not _plausible_ota_listing_url(ota_id,url):
        return {"ok":False,"url":url,"title":title,"evidence":"La pagina aperta non è una scheda struttura valida del portale."}
    identity=_strict_ota_identity_match(
        str(data.get("name") or ""),
        str(data.get("city") or ""),
        str(data.get("address") or ""),
        title,body,url,
    )
    return {**identity,"url":normalize_ota_listing_url(ota_id,url),"title":title,"body":body}


async def _launch_velora_context(playwright, profile_dir: Path, data: dict, phase_label: str, ghost: bool = False):
    """Apre una sessione Chrome persistente dedicata a una singola fase dell'audit."""
    profile_dir.mkdir(parents=True,exist_ok=True)
    last_exc=None
    for attempt in range(3):
        try:
            context=await playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=False,
                locale="it-IT",
                timezone_id="Europe/Rome",
                viewport={"width":1440,"height":1000},
                chromium_sandbox=True,
                args=[
                    "--start-minimized",
                    "--window-position=-32000,-32000",
                    "--window-size=1,1",
                ] if ghost else [],
            )
            anchor_page=context.pages[0] if context.pages else await context.new_page()
            try:
                property_label=str(data.get("name") or "Struttura")
                await anchor_page.set_content(
                    f"""<!doctype html>
                    <html><head><meta charset="utf-8"><title>Velora · {phase_label}</title>
                    <style>
                      body{{font-family:Arial,sans-serif;background:#f7f7f4;color:#20211f;margin:0;padding:48px}}
                      .card{{max-width:720px;margin:8vh auto;background:white;border:1px solid #deded8;border-radius:18px;padding:34px;box-shadow:0 10px 35px rgba(0,0,0,.06)}}
                      h1{{font-size:28px;margin:0 0 12px}} p{{font-size:17px;line-height:1.5;margin:8px 0}}
                      .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;background:#35a853;margin-right:9px}}
                    </style></head><body><div class="card">
                    <h1><span class="dot"></span>Velora sta lavorando</h1>
                    <p><strong>{property_label}</strong></p>
                    <p>Fase: <strong>{phase_label}</strong></p>
                    <p>Questa scheda resta aperta come controllo. Le schede operative possono aprirsi e chiudersi durante la scansione.</p>
                    </div></body></html>""",
                    wait_until="domcontentloaded",
                    timeout=5000,
                )
            except Exception:
                pass
            if ghost:
                try:
                    cdp=await context.new_cdp_session(anchor_page)
                    info=await cdp.send("Browser.getWindowForTarget")
                    await cdp.send("Browser.setWindowBounds",{
                        "windowId":info["windowId"],
                        "bounds":{"windowState":"minimized"},
                    })
                    await cdp.detach()
                except Exception:
                    pass
            print(
                f"browser mode: {'Ghost/minimizzato' if ghost else 'Chrome persistente visibile'} · fase={phase_label} · profilo={profile_dir} · watchdog finestra attivo",
                flush=True,
            )
            return context
        except Exception as exc:
            last_exc=exc
            if attempt<2:
                await asyncio.sleep(1.2+attempt)
    raise RuntimeError(
        f"Impossibile aprire Chrome per la fase {phase_label}: "
        f"{type(last_exc).__name__ if last_exc else 'errore'}: {str(last_exc)[:180] if last_exc else ''}"
    )


async def run(args: argparse.Namespace) -> dict:
    data = json.loads(Path(args.property).read_text(encoding="utf-8-sig"))
    today = date.fromisoformat(args.today) if args.today else date.today()
    # "12 mesi" = da questo mese fino allo stesso mese dell'anno prossimo:
    # 13 campioni inclusivi (es. ottobre 2026 → ottobre 2027).
    plan_limit = 13 if args.months == 12 else args.months
    plan = monthly_plan(today, limit=plan_limit)
    channels = [part.strip() for part in args.channels.split(",") if part.strip()]
    unknown = set(channels) - set(CHANNELS)
    if unknown:
        raise ValueError(f"Canali sconosciuti: {', '.join(sorted(unknown))}")
    sources = dict(data.get("sources") or {})
    # v91: una source vecchia e non equivalente NON deve attivare il quick retest.
    # Prima rimuovi il falso match numerato, così parte la nuova discovery mirata.
    if "agoda" in [part.strip() for part in args.channels.split(",")]:
        old_agoda=(sources.get("agoda") or {}).get("url","") if isinstance(sources.get("agoda"),dict) else ""
        if old_agoda and _agoda_unit_listing_conflict(data.get("name",""),old_agoda):
            sources.pop("agoda",None)
            data["sources"]=sources
            print(
                "agoda identity reset: scheda numerata di singola unità rifiutata; "
                "la discovery riparte dalla scheda hotel principale · "
                + old_agoda[:230],
                flush=True,
            )
    ghost=bool(getattr(args,"ghost",False))
    assisted=bool(getattr(args,"assisted",False))
    pricing_only=bool(getattr(args,"pricing_only",False))
    assist_callback=getattr(args,"assist_callback",None) if assisted else None
    result = {"schema": SCHEMA, "propertyId": data["id"], "propertyName": data["name"],
              "createdAt": datetime.now(timezone.utc).isoformat(), "method": "Pilota locale, solo frontend pubblico senza login: scheda → date → ospiti → cerca → tariffe; nessun account, registrazione, tariffa member/app o bypass.",
              "plan": plan, "bookingEngine": {"status": "unverified", "provider": "", "url": "", "mode": "",
                                                  "evidence": "Non ancora esaminato."},
              "identityResolution": {}, "masterSearch": {}, "aiWebSearch": {}, "discoveredSources": {}, "otaProfiles": {},
              "reputation": {}, "photoAudit": {}, "bookingDateResolution": [], "bookingReferenceStays": [], "discoveryProgress": {},
              "browserPhases": [], "observations": []}
    output = Path(args.output)
    if args.dry_run:
        write_result(output, result)
        return result
    robots: dict[str, RobotFileParser | bool | None] = {}
    async with async_playwright() as playwright:
        # Discovery e pricing usano profili distinti. Una sessione lunga di ricerca
        # non può più trascinare con sé un BrowserContext instabile nella fase prezzi.
        discovery_profile_dir=Path(__file__).resolve().parent/"velora-browser-profile-discovery"
        pricing_profile_dir=Path(__file__).resolve().parent/"velora-browser-profile-pricing"
        context=await _launch_velora_context(
            playwright,discovery_profile_dir,data,"discovery OTA",ghost
        )
        result["browserPhases"].append({
            "phase":"discovery","status":"running","profile":str(discovery_profile_dir)
        })
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

            if pricing_only:
                result["reputation"]={"status":"skipped_pricing_test","evidence":"Test OTA selettivo: reputazione non rieseguita."}
                result["photoAudit"]={"status":"skipped_pricing_test","evidence":"Test OTA selettivo: audit fotografico non rieseguito."}
                write_result(output,result)
            else:
                reputation=await google_reputation_observation(context,data)
                result["reputation"]=reputation
                print(
                    f"reputation: {reputation.get('status','n.d.')} · "
                    f"rating={reputation.get('rating','n.d.')} · reviews={reputation.get('reviewCount','n.d.')} · "
                    f"sample={reputation.get('sampleSize',0)} · strengths={len(reputation.get('strengths') or [])} · "
                    f"weaknesses={len(reputation.get('weaknesses') or [])}",
                    flush=True,
                )
                write_result(output,result)
    
                photo_audit=await frontend_photo_audit(context,data,robots)
                result["photoAudit"]=photo_audit
                print(
                    f"photo audit: {photo_audit.get('status','n.d.')} · score={photo_audit.get('score',0)} · "
                    f"pages={photo_audit.get('pagesSampled',0)} · images={photo_audit.get('imageCount',0)} · "
                    f"known-dim={photo_audit.get('knownDimensionCount',0)} · highres={photo_audit.get('highResolutionCount',0)} · "
                    f"alt={photo_audit.get('altTextCount',0)}",
                    flush=True,
                )
                write_result(output,result)
    
            official_identity_url=(sources.get("sito") or {}).get("url","")
            known_ota_sources=[
                ota_id for ota_id in OTA_DISCOVERY_ORDER
                if ((sources.get(ota_id) or {}).get("url") if isinstance(sources.get(ota_id),dict) else "")
            ]
            single_ota_scan=len(channels)==1 and channels[0] in OTA_DISCOVERY_ORDER
            single_ota_id=channels[0] if single_ota_scan else ""
            single_ota_known=bool(single_ota_id and single_ota_id in known_ota_sources)

            selected_discovery_ids=[ota_id for ota_id in OTA_DISCOVERY_ORDER if ota_id in channels]
            missing_discovery_ids=[
                ota_id for ota_id in selected_discovery_ids
                if ota_id not in known_ota_sources
                or (
                    ota_id=="airbnb"
                    and len(((sources.get("airbnb") or {}).get("listingUrls") or []))<2
                )
            ]
            # Test diagnostico: le schede già note non vengono riscoperte ad ogni prova.
            # Quando aggiungi una nuova OTA, Velora fa discovery soltanto di quella/e mancanti.
            quick_retest=bool(pricing_only and selected_discovery_ids and not missing_discovery_ids)
            discovery_target_ids=missing_discovery_ids if pricing_only else selected_discovery_ids

            if quick_retest:
                master_discoveries={}
                master_diag={
                    "status":"reused_selected_sources",
                    "queries":[],
                    "candidates":len(selected_discovery_ids),
                    "knownSources":known_ota_sources,
                    "selectedChannels":selected_discovery_ids,
                }
                result["discoveryProgress"]={
                    "stage":"reused",
                    "completed":len(selected_discovery_ids),
                    "total":len(selected_discovery_ids),
                    "otaId":"",
                    "label":"Schede OTA selezionate già note",
                    "updatedAt":datetime.now(timezone.utc).isoformat(),
                }
                print(
                    "master search: riuso schede selezionate già note · "
                    f"canali={','.join(selected_discovery_ids)}",
                    flush=True,
                )
            else:
                result["discoveryProgress"]={
                    "stage":"master",
                    "completed":0,
                    "total":len(discovery_target_ids),
                    "otaId":"",
                    "label":"Discovery OTA selezionate",
                    "updatedAt":datetime.now(timezone.utc).isoformat(),
                }
                write_result(output,result)

                async def save_discovery_progress(progress,partial,diag):
                    progress=dict(progress)
                    progress["updatedAt"]=datetime.now(timezone.utc).isoformat()
                    result["discoveryProgress"]=progress
                    result["masterSearch"]=diag
                    for partial_id,partial_value in partial.items():
                        result["discoveredSources"][partial_id]=partial_value
                    write_result(output,result)
                    print(
                        f"discovery progress: {progress.get('completed',0)}/{progress.get('total',len(discovery_target_ids))} · "
                        f"{progress.get('label','')}",
                        flush=True,
                    )

                master_discoveries,master_diag=await discover_all_ota_sources(
                    context,data,robots,on_progress=save_discovery_progress,
                    selected_ota_ids=discovery_target_ids,
                )
                master_diag["mode"]="selected_channels_only"
                query_preview=" | ".join((master_diag.get("queries") or [])[:3])
                print(
                    f"master search: {master_diag.get('status')} · modalità=solo OTA selezionate · "
                    f"target={','.join(discovery_target_ids)} · "
                    f"varianti={len(master_diag.get('queries') or [])} · "
                    f"candidati OTA={master_diag.get('candidates',0)} · prime query: {query_preview[:240]}",
                    flush=True,
                )
            result["masterSearch"]=master_diag

            unresolved=[
                ota_id for ota_id in selected_discovery_ids
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
                    "discovery saltata: tutte le OTA selezionate hanno già una scheda registrata; "
                    "Velora passa direttamente alla verifica frontend.",
                    flush=True,
                )

            # CHECKPOINT: la discovery è ormai patrimonio del risultato.
            # Da qui in poi usa una sessione Chrome FRESCA dedicata alle tariffe.
            # Se la sessione discovery è già morta, la chiusura viene ignorata:
            # non si rifanno reputazione, foto e 14 ricerche OTA.
            result["browserPhases"].append({
                "phase":"discovery",
                "status":"completed",
                "candidates":len(result.get("discoveredSources") or {}),
            })
            write_result(output,result)
            try:
                await context.close()
            except Exception:
                pass
            await asyncio.sleep(0.8)
            context=await _launch_velora_context(
                playwright,pricing_profile_dir,data,"verifica schede e tariffe",ghost
            )
            result["browserPhases"].append({
                "phase":"pricing","status":"running","profile":str(pricing_profile_dir)
            })
            write_result(output,result)
            print(
                "browser phase switch: discovery salvata · nuova sessione Chrome dedicata a schede/prezzi",
                flush=True,
            )

            async def restart_pricing_context(reason: str):
                nonlocal context
                try:
                    await context.close()
                except Exception:
                    pass
                await asyncio.sleep(0.8)
                context=await _launch_velora_context(
                    playwright,pricing_profile_dir,data,"verifica schede e tariffe · recovery",ghost
                )
                result["browserPhases"].append({
                    "phase":"pricing",
                    "status":"restarted",
                    "reason":reason[:220],
                })
                write_result(output,result)
                print(
                    f"WATCHDOG PRICING: sessione Chrome riaperta senza perdere la discovery · {reason[:180]}",
                    flush=True,
                )
                return context

            async def ensure_pricing_context(reason: str):
                nonlocal context
                probe=None
                try:
                    probe=await context.new_page()
                    await probe.close()
                    return context
                except Exception as exc:
                    if probe is not None:
                        try:
                            await probe.close()
                        except Exception:
                            pass
                    if _browser_closed_exception(exc):
                        return await restart_pricing_context(reason)
                    raise

            unverified_source_ids=set()
            for ota_id in selected_discovery_ids:
                existing_url=(sources.get(ota_id) or {}).get("url") if isinstance(sources.get(ota_id),dict) else ""
                if existing_url:
                    try:
                        verification=await verify_ota_candidate_page(
                            context,
                            ota_id,
                            existing_url,
                            data.get("name",""),
                            data.get("city",""),
                            data.get("address",""),
                            robots,
                        )
                    except Exception as exc:
                        if not _browser_closed_exception(exc):
                            raise
                        await restart_pricing_context(f"verifica scheda {ota_id}: {type(exc).__name__}")
                        verification=await verify_ota_candidate_page(
                            context,
                            ota_id,
                            existing_url,
                            data.get("name",""),
                            data.get("city",""),
                            data.get("address",""),
                            robots,
                        )
                    if verification.get("ok"):
                        result["discoveredSources"][ota_id]={
                            "status":"existing_verified",
                            "url":verification.get("url") or existing_url,
                            "title":verification.get("title") or "",
                            "score":verification.get("score",1.0),
                            "evidence":(
                                f"{OTA_META[ota_id]['label']}: scheda già registrata e identità riconfermata prima dello scraping. "
                                + str(verification.get("evidence") or "")
                            )[:900],
                            "discoveryMode":"existing source + strict identity verification",
                            "verification":"page_identity_lock",
                        }
                        sources[ota_id]={
                            "label":OTA_META[ota_id]["label"],
                            "url":verification.get("url") or existing_url,
                            **(
                                {"listingUrls":list((sources.get("airbnb") or {}).get("listingUrls") or [])}
                                if ota_id=="airbnb" else {}
                            ),
                        }
                        if ota_id=="airbnb" and sources[ota_id].get("listingUrls"):
                            result["discoveredSources"][ota_id]["listingUrls"]=sources[ota_id]["listingUrls"]
                        continue
                    existing_url=normalize_ota_listing_url(ota_id,existing_url)
                    sources[ota_id]={"label":OTA_META[ota_id]["label"],"url":existing_url}
                    unverified_source_ids.add(ota_id)
                    result["discoveredSources"][ota_id]={
                        "status":"existing_unverified",
                        "url":"",
                        "candidateUrl":existing_url,
                        "title":verification.get("title") or "",
                        "score":verification.get("score",0.0),
                        "presenceDetected":True,
                        "identityVerified":False,
                        "evidence":(
                            f"{OTA_META[ota_id]['label']}: pagina già nota e raggiunta, ma identità non riconfermata. "
                            f"Presenza conservata; eventuali prezzi restano da verificare. {verification.get('evidence','')}"
                        )[:900],
                        "discoveryMode":"existing candidate preserved",
                    }
                    print(
                        f"{ota_id} existing source preserved as candidate · "
                        f"{str(verification.get('evidence') or '')[:260]}",
                        flush=True,
                    )
                discovery=master_discoveries.get(ota_id) or {}

                # Se la prima scheda è vecchia/sbagliata (es. HTTP 410 Airbnb),
                # prova i candidati alternativi della stessa ricerca prima di rinunciare.
                if ota_id!="booking" and discovery.get("identityVerified") is not True:
                    alternative_urls=[]
                    for value in [
                        discovery.get("candidateUrl"),
                        *(discovery.get("candidateUrls") or []),
                    ]:
                        clean_value=normalize_ota_listing_url(ota_id,str(value or ""))
                        if clean_value and clean_value not in alternative_urls and _plausible_ota_listing_url(ota_id,clean_value):
                            alternative_urls.append(clean_value)
                    for alternative_url in alternative_urls[:3]:
                        try:
                            alternative_check=await asyncio.wait_for(
                                verify_ota_candidate_page(
                                    context,ota_id,alternative_url,
                                    data.get("name",""),data.get("city",""),data.get("address",""),robots,
                                ),
                                timeout=18,
                            )
                        except Exception:
                            continue
                        if not alternative_check.get("ok"):
                            continue
                        discovery={
                            "status":"found",
                            "url":alternative_check.get("url") or alternative_url,
                            "title":alternative_check.get("title") or discovery.get("title",""),
                            "score":alternative_check.get("score",discovery.get("score",1.0)),
                            "presenceDetected":True,
                            "identityVerified":True,
                            "verification":"page_identity_lock",
                            "discoveryMode":"ranked candidate verification",
                            "evidence":(
                                f"{OTA_META[ota_id]['label']}: candidato alternativo verificato prima del pricing. "
                                + str(alternative_check.get("evidence") or "")
                            )[:900],
                        }
                        print(
                            f"{ota_id} candidate verified for pricing · {str(discovery.get('url') or '')[:180]}",
                            flush=True,
                        )
                        break

                # Booking mantiene il proprio fallback specializzato se la pipeline master non chiude il match.
                if ota_id=="booking" and discovery.get("status")!="found":
                    await ensure_pricing_context("prima della discovery Booking specializzata")
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
                if (
                    discovery.get("status")=="found"
                    and discovery.get("url")
                    and (ota_id=="booking" or discovery.get("identityVerified") is True)
                ):
                    sources[ota_id]={
                        "label":OTA_META[ota_id]["label"],
                        "url":normalize_ota_listing_url(ota_id,discovery["url"]),
                        **(
                            {"listingUrls":list(discovery.get("listingUrls") or [])}
                            if ota_id=="airbnb" else {}
                        ),
                    }
                    unverified_source_ids.discard(ota_id)
                else:
                    candidate_url=normalize_ota_listing_url(
                        ota_id,
                        discovery.get("candidateUrl") or (
                            discovery.get("url") if discovery.get("presenceDetected") else ""
                        ),
                    )
                    if candidate_url and _classify_ota_url(candidate_url)==ota_id and _plausible_ota_listing_url(ota_id,candidate_url):
                        sources[ota_id]={"label":OTA_META[ota_id]["label"],"url":candidate_url}
                        unverified_source_ids.add(ota_id)
                        discovery["presenceDetected"]=True
                        discovery["candidateUrl"]=candidate_url
                        print(
                            f"{ota_id} candidate source retained for observation only · {candidate_url[:180]}",
                            flush=True,
                        )
                    elif discovery.get("status")=="found" and ota_id!="booking":
                        print(
                            f"{ota_id} discovery found rejected: manca identityVerified=true · "
                            f"{str(discovery.get('url') or '')[:180]}",
                            flush=True,
                        )

            # Per i portali non adatti al confronto tariffario mensile raccoglie comunque
            # un profilo pubblico strutturato: reputazione, prezzi generici e link commerciali.
            selected_profile_ids=[ota_id for ota_id in PROFILE_AUDIT_CHANNELS if ota_id in channels]
            run_profile_audit = bool(selected_profile_ids) and not pricing_only
            if run_profile_audit:
                await ensure_pricing_context("prima dei profili OTA")
                for ota_id in selected_profile_ids:
                    profile_source=(sources.get(ota_id) or {}).get("url") if isinstance(sources.get(ota_id),dict) else ""
                    if profile_source:
                        profile=await observe_ota_profile(context,ota_id,profile_source,robots)
                    else:
                        profile={
                            "status":"source_missing","url":"","title":"",
                            "evidence":f"Nessuna scheda {OTA_META[ota_id]['label']} verificata da profilare."
                        }
                    result["otaProfiles"][ota_id]=profile
                    print(
                        f"{ota_id} profile: {profile.get('status','n.d.')} · "
                        f"{str(profile.get('evidence') or '')[:240]}",
                        flush=True,
                    )
                    write_result(output,result)

            await ensure_pricing_context("prima del metasearch assist")
            metasearch_assist=await apply_metasearch_assist(
                context,data,result,sources,robots,unverified_source_ids
            )
            result["metasearchAssist"]=metasearch_assist
            if metasearch_assist:
                print(
                    "metasearch assist completato · " +
                    ", ".join(f"{item['otaId']} via {item['via']}" for item in metasearch_assist),
                    flush=True,
                )
                write_result(output,result)

            # Salva tutte le schede OTA trovate insieme, non soltanto Booking.
            try:
                property_path=Path(args.property)
                if property_path.parent.name=="runtime-properties":
                    persisted_sources={
                        source_id:source for source_id,source in sources.items()
                        if source_id=="sito" or source_id not in unverified_source_ids
                    }
                    data["sources"]=persisted_sources
                    tmp_property=property_path.with_suffix(".tmp")
                    tmp_property.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
                    tmp_property.replace(property_path)
            except OSError:
                pass


            official_url = sources.get("sito", {}).get("url", "")
            await ensure_pricing_context("prima della verifica booking engine diretto")
            if pricing_only:
                result["bookingEngine"]={
                    "status":"skipped_pricing_test","provider":"","url":"","mode":"",
                    "evidence":"Test OTA selettivo: booking engine del sito ufficiale non rieseguito."
                }
            elif official_url:
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

            # REGOLA DI CONFRONTO: Booking determina SEMPRE le date di riferimento,
            # anche quando l'utente non ha selezionato Booking come canale da mostrare.
            # Le altre OTA non scelgono mai date proprie: ricevono la finestra esatta
            # risolta su Booking (stessa durata e stessi ospiti).
            booking_reference_source=(sources.get("booking") or {}).get("url","") if isinstance(sources.get("booking"),dict) else ""
            if not booking_reference_source:
                try:
                    ref_discovery=await asyncio.wait_for(
                        discover_booking_source(
                            context,
                            data.get("name",""),
                            data.get("city",""),
                            robots,
                            data.get("address",""),
                            (sources.get("sito") or {}).get("url","") if isinstance(sources.get("sito"),dict) else "",
                            data.get("phone",""),
                            data.get("email",""),
                        ),
                        timeout=45,
                    )
                except Exception as exc:
                    ref_discovery={
                        "status":"error","url":"",
                        "evidence":f"Booking reference discovery fallita: {type(exc).__name__}: {str(exc)[:180]}"
                    }
                if ref_discovery.get("status")=="found" and ref_discovery.get("url"):
                    booking_reference_source=normalize_ota_listing_url("booking",str(ref_discovery["url"]))
                    sources["booking"]={"label":"Booking.com","url":booking_reference_source}
                    result.setdefault("discoveredSources",{})["bookingReference"]={
                        **ref_discovery,
                        "url":booking_reference_source,
                        "evidence":(
                            "Booking usato come riferimento date per tutte le OTA. "
                            + str(ref_discovery.get("evidence") or "")
                        )[:900],
                    }
                    print(
                        f"booking-reference-source: trovato · {booking_reference_source[:260]}",
                        flush=True,
                    )
                else:
                    print(
                        "booking-reference-source: NON disponibile · "
                        f"{str(ref_discovery.get('evidence') or ref_discovery.get('status') or '')[:260]}",
                        flush=True,
                    )

            for stay_index,planned_stay in enumerate(list(plan)):
                await ensure_pricing_context(f"inizio campione tariffario {planned_stay.get('month','')}")
                effective_stay=dict(planned_stay)
                precomputed_booking=None

                # Booking è il riferimento temporale del confronto multi-OTA.
                # Viene interrogato prima di tutti gli altri canali. Se dichiara
                # esplicitamente indisponibilità, cerca una finestra successiva
                # con la stessa durata; le altre OTA useranno esattamente quelle date.
                booking_source=booking_reference_source or (
                    (sources.get("booking") or {}).get("url","") if isinstance(sources.get("booking"),dict) else ""
                )
                if booking_source:
                    search_page=await context.new_page()
                    try:
                        initial_booking=await booking_dated_search_observation(
                            search_page,
                            booking_source,
                            data.get("name",""),
                            data.get("city",""),
                            effective_stay,
                            robots,
                        )
                    finally:
                        await search_page.close()

                    print(
                        f"{effective_stay['month']} booking-dated-search: {initial_booking.get('status')} · "
                        f"{str(initial_booking.get('evidence') or '')[:260]}",
                        flush=True,
                    )

                    if initial_booking.get("status") not in {
                        "quote_candidates","quote_candidates_unverified","no_public_rate","needs_human_review"
                    }:
                        page=await context.new_page()
                        try:
                            fallback_booking=await observe(page,"booking",booking_source,effective_stay,robots,data.get("name",""),data.get("city",""))
                        finally:
                            await page.close()
                        if fallback_booking.get("status") in {"dates_unconfirmed","needs_human_review"}:
                            fallback_booking["evidence"]=(
                                str(fallback_booking.get("evidence") or "") +
                                " | Ricerca Booking datata: " +
                                str(initial_booking.get("evidence") or "")
                            )[:900]
                        initial_booking=fallback_booking

                    effective_stay,precomputed_booking,resolution=await booking_resolve_reference_stay(
                        context,
                        booking_source,
                        data.get("name",""),
                        data.get("city",""),
                        effective_stay,
                        robots,
                        initial_booking,
                    )
                    result["bookingDateResolution"].append(resolution)
                    reference_lock={
                        "month":planned_stay.get("month"),
                        "requestedCheckin":planned_stay.get("checkin"),
                        "requestedCheckout":planned_stay.get("checkout"),
                        "checkin":effective_stay.get("checkin"),
                        "checkout":effective_stay.get("checkout"),
                        "nights":effective_stay.get("nights"),
                        "adults":effective_stay.get("adults",2),
                        "status":resolution.get("status"),
                        "source":"booking",
                    }
                    result["bookingReferenceStays"].append(reference_lock)
                    print(
                        f"{planned_stay['month']} BOOKING DATE LOCK · "
                        f"{effective_stay['checkin']}→{effective_stay['checkout']} · "
                        f"{effective_stay.get('nights')} notti · {effective_stay.get('adults',2)} adulti · "
                        "QUESTE DATE SONO OBBLIGATORIE PER TUTTE LE OTA",
                        flush=True,
                    )

                    if effective_stay["checkin"] != planned_stay["checkin"]:
                        plan[stay_index]=effective_stay
                        print(
                            f"{planned_stay['month']} booking-reference-resolved: "
                            f"{planned_stay['checkin']}→{planned_stay['checkout']} => "
                            f"{effective_stay['checkin']}→{effective_stay['checkout']} · "
                            f"stesse date applicate a tutte le OTA",
                            flush=True,
                        )
                    else:
                        print(
                            f"{planned_stay['month']} booking-reference-resolved: "
                            f"{resolution.get('status')} · date={effective_stay['checkin']}→{effective_stay['checkout']}",
                            flush=True,
                        )
                    write_result(output,result)
                else:
                    resolution={
                        "status":"booking_reference_unavailable",
                        "requestedCheckin":planned_stay.get("checkin"),
                        "requestedCheckout":planned_stay.get("checkout"),
                        "resolvedCheckin":"",
                        "resolvedCheckout":"",
                        "attempts":0,
                        "evidence":"Booking non disponibile come riferimento: Velora non confronterà date diverse tra OTA."
                    }
                    result["bookingDateResolution"].append(resolution)
                    result["bookingReferenceStays"].append({
                        "month":planned_stay.get("month"),
                        "requestedCheckin":planned_stay.get("checkin"),
                        "requestedCheckout":planned_stay.get("checkout"),
                        "checkin":"","checkout":"",
                        "nights":planned_stay.get("nights"),
                        "adults":planned_stay.get("adults",2),
                        "status":"booking_reference_unavailable",
                        "source":"booking",
                    })
                    print(
                        f"{planned_stay['month']} BOOKING DATE LOCK · IMPOSSIBILE: nessuna scheda Booking di riferimento",
                        flush=True,
                    )
                    write_result(output,result)

                for channel in channels:
                    channel_started=time.monotonic()
                    source = sources.get(channel, {}).get("url", "")
                    print(
                        f"{effective_stay['month']} {channel}: START frontend pubblico · "
                        f"BOOKING LOCK={effective_stay['checkin']}→{effective_stay['checkout']} · "
                        f"{effective_stay.get('adults',2)} adulti",
                        flush=True,
                    )
                    if channel=="booking" and precomputed_booking is not None:
                        record=precomputed_booking
                    else:
                        # Percorso alternativo indipendente dalla discovery esterna:
                        # se manca una source o è soltanto candidata, cerca direttamente nel portale.
                        if channel!="booking" and channel in OTA_DISCOVERY_ORDER and (not source or channel in unverified_source_ids):
                            try:
                                frontend_source=await asyncio.wait_for(
                                    frontend_discover_ota_source(
                                        context,channel,data,effective_stay,robots,
                                        assist_callback=assist_callback,ghost=ghost,
                                    ),
                                    timeout=HUMAN_ASSIST_TIMEOUT if assisted else (
                                        155 if channel=="airbnb" else AUTO_SOURCE_DISCOVERY_TIMEOUT
                                    ),
                                )
                            except asyncio.TimeoutError:
                                frontend_source={
                                    "status":"timeout","url":"",
                                    "evidence":f"{OTA_META[channel]['label']}: ricerca frontend fermata dal watchdog; Velora passa alla OTA successiva."
                                }
                            except Exception as exc:
                                frontend_source={
                                    "status":"error","url":"",
                                    "evidence":f"{OTA_META[channel]['label']}: ricerca interna fallita ({type(exc).__name__}: {str(exc)[:150]})."
                                }

                            if frontend_source.get("status")=="found" and frontend_source.get("url"):
                                source=frontend_source["url"]
                                sources[channel]={
                                    "label":OTA_META[channel]["label"],"url":source,
                                    **(
                                        {"listingUrls":list(frontend_source.get("listingUrls") or [])}
                                        if channel=="airbnb" else {}
                                    ),
                                }
                                unverified_source_ids.discard(channel)
                                result.setdefault("discoveredSources",{})[channel]=frontend_source
                                print(
                                    f"{effective_stay['month']} {channel}: FRONTEND SOURCE · "
                                    f"{str(frontend_source.get('evidence') or '')[:260]}",
                                    flush=True,
                                )
                                write_result(output,result)

                        if not source:
                            discovery = result.get("discoveredSources", {}).get(channel, {})
                            evidence = discovery.get("evidence") if isinstance(discovery, dict) else ""
                            if quick_retest and channel in OTA_DISCOVERY_ORDER:
                                record = {
                                    "otaId": channel, **effective_stay, "status": "source_not_retested", "quotes": [],
                                    "evidence": "Scansione dedicata: discovery non ripetuta e ricerca interna OTA senza match verificabile."
                                }
                            else:
                                record = {
                                    "otaId": channel, **effective_stay, "status": "source_missing", "quotes": [],
                                    "evidence": evidence or "Nessuna scheda univoca trovata né da discovery né dalla ricerca interna OTA."
                                }
                        else:
                            page = None
                            try:
                                page = await context.new_page()
                                record = await asyncio.wait_for(
                                    observe(page, channel, source, effective_stay, robots, data.get("name",""), data.get("city","")),
                                    timeout=AUTO_OTA_OBSERVE_TIMEOUT,
                                )
                            except asyncio.TimeoutError:
                                record = {
                                    "otaId": channel, **effective_stay,
                                    "status": "needs_human_review", "quotes": [],
                                    "evidence": (
                                        f"{OTA_META.get(channel, {'label': channel}).get('label', channel)}: "
                                        "controllo frontend interrotto dal watchdog dopo 55 secondi; "
                                        "l'audit continua sulle altre fonti."
                                    ),
                                }
                                print(
                                    f"{effective_stay['month']} {channel}: WATCHDOG 55s · continuo con la prossima fonte",
                                    flush=True,
                                )
                            except Exception as exc:
                                if _browser_closed_exception(exc):
                                    if page is not None:
                                        try:
                                            await page.close()
                                        except Exception:
                                            pass
                                        page=None
                                    await restart_pricing_context(
                                        f"{effective_stay['month']} {channel}: {type(exc).__name__}"
                                    )
                                    try:
                                        page=await context.new_page()
                                        record=await asyncio.wait_for(
                                            observe(page,channel,source,effective_stay,robots,data.get("name",""),data.get("city","")),
                                            timeout=75,
                                        )
                                        print(
                                            f"{effective_stay['month']} {channel}: retry dopo recovery Chrome completato",
                                            flush=True,
                                        )
                                    except Exception as retry_exc:
                                        record={
                                            "otaId":channel, **effective_stay,
                                            "status":"needs_human_review","quotes":[],
                                            "evidence":(
                                                f"{OTA_META.get(channel, {'label': channel}).get('label', channel)}: "
                                                f"sessione Chrome riavviata ma il secondo tentativo non è riuscito "
                                                f"({type(retry_exc).__name__}: {str(retry_exc)[:160]})."
                                            ),
                                        }
                                else:
                                    record = {
                                        "otaId": channel, **effective_stay,
                                        "status": "needs_human_review", "quotes": [],
                                        "evidence": (
                                            f"{OTA_META.get(channel, {'label': channel}).get('label', channel)}: "
                                            f"errore isolato {type(exc).__name__}: {str(exc)[:180]}. "
                                            "L'audit continua sulle altre fonti."
                                        ),
                                    }
                                    print(
                                        f"{effective_stay['month']} {channel}: ERRORE ISOLATO · "
                                        f"{type(exc).__name__}: {str(exc)[:180]}",
                                        flush=True,
                                    )
                            finally:
                                if page is not None:
                                    try:
                                        await page.close()
                                    except Exception:
                                        pass

                            # Per hotel/complessi Airbnb, ogni /rooms/<id> è una distinta
                            # camera/unità. Non fermarsi alla prima scheda come le altre OTA.
                            if channel=="airbnb":
                                airbnb_meta=result.get("discoveredSources",{}).get("airbnb") or {}
                                found_urls=list(
                                    airbnb_meta.get("listingUrls")
                                    or (sources.get("airbnb") or {}).get("listingUrls")
                                    or []
                                )
                                if source and source not in found_urls:
                                    found_urls.insert(0,source)
                                distinct_urls=[]
                                seen_listing_ids=set()
                                for listing_url in found_urls:
                                    match=re.search(r"/rooms/(\d+)",urlparse(listing_url).path,re.I)
                                    if not match or match.group(1) in seen_listing_ids:
                                        continue
                                    seen_listing_ids.add(match.group(1))
                                    distinct_urls.append(listing_url)
                                # Il numero è limitato per evitare decine di pagine × 13 mesi
                                # senza controllo dei tempi; l'eventuale resto viene segnalato.
                                selected_urls=distinct_urls[:8]
                                primary_id=re.search(r"/rooms/(\d+)",urlparse(source).path,re.I)
                                primary_id=primary_id.group(1) if primary_id else ""
                                listing_outcomes=[]
                                if source:
                                    listing_outcomes.append({
                                        "url":source,"status":record.get("status"),
                                        "quotes":len(record.get("quotes") or []),
                                        "title":record.get("title",""),
                                    })
                                    for quote in record.get("quotes") or []:
                                        quote["sourceUrl"]=record.get("finalUrl") or source

                                for sibling_source in selected_urls:
                                    match=re.search(r"/rooms/(\d+)",urlparse(sibling_source).path,re.I)
                                    if not match or match.group(1)==primary_id:
                                        continue
                                    sibling_page=None
                                    try:
                                        sibling_page=await context.new_page()
                                        sibling=await asyncio.wait_for(
                                            observe(
                                                sibling_page,"airbnb",sibling_source,
                                                effective_stay,robots,data.get("name",""),data.get("city",""),
                                            ),
                                            timeout=AUTO_OTA_OBSERVE_TIMEOUT,
                                        )
                                        extra_quotes=list(sibling.get("quotes") or [])
                                        for quote in extra_quotes:
                                            quote["sourceUrl"]=sibling.get("finalUrl") or sibling_source
                                        record.setdefault("quotes",[]).extend(extra_quotes)
                                        listing_outcomes.append({
                                            "url":sibling.get("finalUrl") or sibling_source,
                                            "status":sibling.get("status"),
                                            "quotes":len(extra_quotes),
                                            "title":sibling.get("title",""),
                                        })
                                        print(
                                            f"{effective_stay['month']} airbnb-listing-pricing: "
                                            f"{match.group(1)} · {sibling.get('status')} · "
                                            f"{len(extra_quotes)} tariffe · {str(sibling.get('evidence') or '')[:180]}",
                                            flush=True,
                                        )
                                    except Exception as exc:
                                        listing_outcomes.append({
                                            "url":sibling_source,"status":"error",
                                            "quotes":0,"error":f"{type(exc).__name__}: {str(exc)[:120]}",
                                        })
                                        print(
                                            f"{effective_stay['month']} airbnb-listing-error: "
                                            f"{match.group(1)} · {type(exc).__name__}: {str(exc)[:120]}",
                                            flush=True,
                                        )
                                    finally:
                                        if sibling_page is not None:
                                            try:
                                                await sibling_page.close()
                                            except Exception:
                                                pass
                                if listing_outcomes:
                                    record["listingResults"]=listing_outcomes
                                    record["listingCount"]=len(listing_outcomes)
                                    record["listingDiscoveredCount"]=len(distinct_urls)
                                    quote_count=len(record.get("quotes") or [])
                                    valid_count=sum(1 for q in record.get("quotes") or [] if q.get("verified"))
                                    if quote_count:
                                        record["status"]="quote_candidates" if valid_count else "quote_candidates_unverified"
                                    else:
                                        statuses=[str(outcome.get("status") or "") for outcome in listing_outcomes]
                                        if statuses and all(status=="no_public_rate" for status in statuses):
                                            record["status"]="no_public_rate"
                                        elif statuses and all(status in {
                                            "blocked","robots_denied","rate_limited","http_error","login_required"
                                        } for status in statuses):
                                            record["status"]="blocked"
                                        else:
                                            record["status"]="needs_human_review"
                                    status_counts={}
                                    for outcome in listing_outcomes:
                                        name=str(outcome.get("status") or "n.d.")
                                        status_counts[name]=status_counts.get(name,0)+1
                                    previous_ev=str(record.get("evidence") or "")
                                    record["evidence"]=(
                                        f"Airbnb multi-annuncio: {len(listing_outcomes)} schede testate; "
                                        f"{quote_count} tariffe pubbliche rilevate ({valid_count} validate dal parser), "
                                        f"{len(distinct_urls)} annunci identificati. "
                                        "Esiti: "+", ".join(f"{key}={value}" for key,value in status_counts.items())+"."
                                        + (
                                            " Alcuni annunci identificati non ancora testati nel campione."
                                            if len(distinct_urls)>len(selected_urls) else ""
                                        )
                                        + f" Dettaglio primo annuncio: {previous_ev}"
                                    )[:1200]

                            # Tutte le tariffe osservate sono conservate; un mancato
                            # match camera/piano con Booking NON elimina la rilevazione.

                    record["bookingReferenceCheckin"]=effective_stay["checkin"]
                    record["bookingReferenceCheckout"]=effective_stay["checkout"]
                    record["bookingReferenceNights"]=effective_stay.get("nights")
                    record["bookingReferenceAdults"]=effective_stay.get("adults",2)
                    record["dateReference"]="booking"

                    # Nessuna OTA può cambiare autonomamente la finestra di confronto.
                    # Se un adapter restituisce date diverse, i prezzi vengono annullati.
                    if (
                        str(record.get("checkin") or "") != str(effective_stay["checkin"])
                        or str(record.get("checkout") or "") != str(effective_stay["checkout"])
                    ):
                        record["quotes"]=[]
                        record["status"]="dates_mismatch_booking_reference"
                        record["evidence"]=(
                            f"Finestra OTA diversa dal riferimento Booking. Atteso "
                            f"{effective_stay['checkin']} → {effective_stay['checkout']}; "
                            f"osservato {record.get('checkin','n.d.')} → {record.get('checkout','n.d.')}. "
                            "Nessun prezzo usato."
                        )[:900]

                    assisted_weak_statuses={"blocked"}
                    if (
                        assisted and callable(assist_callback)
                        and channel!="booking"
                        and source
                        and not record.get("quotes")
                        and record.get("status") in assisted_weak_statuses
                    ):
                        assist_page=None
                        try:
                            assist_page=await context.new_page()
                            target=frontend_entry_url(channel,source,effective_stay) or source
                            try:
                                await assist_page.goto(target,wait_until="domcontentloaded",timeout=25000)
                                await dismiss_cookie(assist_page)
                                await assist_page.wait_for_timeout(800)
                            except Exception:
                                pass
                            action=await _human_assist(
                                assist_page,assist_callback,{
                                    "type":"visible_public_challenge",
                                    "otaId":channel,
                                    "label":OTA_META[channel]["label"],
                                    "reason":str(record.get("evidence") or record.get("status") or "")[:700],
                                    "instructions":(
                                        f"Il portale {OTA_META[channel]['label']} mostra una verifica/consenso VISIBILE sul frontend pubblico. "
                                        "Completa soltanto quella verifica pubblica o il consenso cookie. "
                                        "NON effettuare login, registrazione o accesso account. "
                                        "Poi torna su Velora e premi «Ho completato · riprendi»."
                                    ),
                                    "propertyName":data.get("name",""),
                                    "city":data.get("city",""),
                                    "stay":effective_stay,
                                    "url":target,
                                },ghost,
                            )
                            if action in {"continue","done"}:
                                identity=await _current_page_identity(assist_page,channel,data)
                                if identity.get("ok"):
                                    assisted_source=identity.get("url") or source
                                    source=assisted_source
                                    sources[channel]={"label":OTA_META[channel]["label"],"url":assisted_source}
                                    unverified_source_ids.discard(channel)

                                    if channel=="agoda":
                                        dates_ok=agoda_url_dates_confirmed(str(assist_page.url or ""),effective_stay)
                                        if not dates_ok:
                                            dates_ok,_=await agoda_dom_dates_confirmed(assist_page,effective_stay)
                                        if dates_ok:
                                            direct_quotes=await agoda_quote_candidates(assist_page,effective_stay)
                                            if not direct_quotes:
                                                direct_quotes=await agoda_visible_rate_candidates(assist_page,effective_stay)
                                            if not direct_quotes:
                                                direct_quotes=await agoda_geometric_rate_candidates(assist_page,effective_stay)
                                            if direct_quotes:
                                                record={
                                                    "otaId":channel,**effective_stay,
                                                    "sourceUrl":assisted_source,
                                                    "requestedUrl":str(assist_page.url or assisted_source),
                                                    "observedAt":datetime.now(timezone.utc).isoformat(),
                                                    "status":"quote_candidates" if any(q.get("verified") for q in direct_quotes) else "quote_candidates_unverified",
                                                    "finalUrl":str(assist_page.url or assisted_source),
                                                    "title":identity.get("title") or "",
                                                    "quotes":direct_quotes,
                                                    "sourceIdentityVerified":True,
                                                    "evidence":(
                                                        f"Assistenza umana completata: scheda Agoda riconfermata e {len(direct_quotes)} "
                                                        "riga/e prezzo lette direttamente dallo stato frontend lasciato aperto dall'utente."
                                                    ),
                                                }

                                    if not record.get("quotes"):
                                        retry_page=None
                                        try:
                                            retry_page=await context.new_page()
                                            retry_record=await asyncio.wait_for(
                                                observe(retry_page,channel,assisted_source,effective_stay,robots,data.get("name",""),data.get("city","")),
                                                timeout=AUTO_OTA_OBSERVE_TIMEOUT,
                                            )
                                            if retry_record.get("quotes") or retry_record.get("status") not in assisted_weak_statuses:
                                                record=retry_record
                                            else:
                                                record["evidence"]=(
                                                    str(record.get("evidence") or "")+
                                                    " | Handoff umano completato e identità riconfermata, ma il portale continua a non esporre una tariffa leggibile: "+
                                                    str(retry_record.get("evidence") or "")
                                                )[:1200]
                                        finally:
                                            if retry_page is not None:
                                                try:
                                                    await retry_page.close()
                                                except Exception:
                                                    pass
                                else:
                                    record["evidence"]=(
                                        str(record.get("evidence") or "")+
                                        " | Handoff umano: pagina aperta non accettata perché non supera il controllo identità. "+
                                        str(identity.get("evidence") or "")
                                    )[:1200]
                            if ghost:
                                await _set_interaction_window(assist_page,False)
                        except Exception as assist_exc:
                            record["evidence"]=(
                                str(record.get("evidence") or "")+
                                f" | Handoff umano non completato: {type(assist_exc).__name__}: {str(assist_exc)[:160]}"
                            )[:1200]
                        finally:
                            if assist_page is not None:
                                try:
                                    await assist_page.close()
                                except Exception:
                                    pass

                    if record.get("quotes"):
                        normalized_quotes=[normalize_quote_price_fields(dict(item)) for item in record.get("quotes") or []]
                        public_quotes=[item for item in normalized_quotes if public_quote_without_login(item)]
                        removed_private=len(normalized_quotes)-len(public_quotes)
                        record["quotes"]=public_quotes
                        if removed_private:
                            record["evidence"]=(
                                str(record.get("evidence") or "")+
                                f" | {removed_private} tariffa/e member-login-app escluse: Velora conserva solo prezzi pubblici senza account."
                            )[:1200]
                        if normalized_quotes and not public_quotes and record.get("status") in {"quote_candidates","quote_candidates_unverified"}:
                            record["status"]="no_public_rate"
                    if channel in unverified_source_ids:
                        record["sourceIdentityVerified"]=False
                        record["sourcePresence"]="candidate_found"
                        for quote in record.get("quotes") or []:
                            quote["verified"]=False
                            quote["referenceRoomKey"]=""
                            quote["roomMatchStatus"]="not-selected"
                            quote["comparisonSelected"]=True
                            quote["comparisonWarning"]=(
                                "Prezzo osservato su una pagina OTA trovata, ma identità della scheda non ancora confermata. "
                                "Il valore viene mostrato come da verificare e non entra nel delta con Booking."
                            )
                        if record.get("quotes") and record.get("status")=="quote_candidates":
                            record["status"]="quote_candidates_unverified"
                        record["evidence"]=(
                            "PAGINA OTA TROVATA · identità da confermare. " + str(record.get("evidence") or "")
                        )[:900]
                    result["observations"].append(record)
                    apply_booking_room_reference(result)
                    write_result(output, result)
                    channel_elapsed=time.monotonic()-channel_started
                    record["elapsedSeconds"]=round(channel_elapsed,1)
                    print(
                        f"{effective_stay['month']} {channel}: {record['status']} · "
                        f"{channel_elapsed:.1f}s · {str(record.get('evidence') or '')[:240]}",
                        flush=True,
                    )
                    await asyncio.sleep(1)
            apply_booking_room_reference(result)
            result["browserPhases"].append({
                "phase":"pricing","status":"completed",
                "observations":len(result.get("observations") or []),
            })
            write_result(output,result)
        finally:
            try:
                await context.close()
            except Exception:
                pass
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--property", default="src/perla-saracena-audit.json")
    parser.add_argument("--output", default="dati_strutture_pilot.json")
    parser.add_argument("--channels", default=",".join(CHANNELS))
    parser.add_argument("--months", type=int, help="Solo i primi N mesi futuri (per test)")
    parser.add_argument("--today", help="Data ISO per test riproducibili")
    parser.add_argument("--dry-run", action="store_true", help="Genera solo il piano date")
    parser.add_argument("--ghost", action="store_true", help="Mantiene Chrome minimizzato durante lo scraping")
    parser.add_argument("--pricing-only", action="store_true", help="Esegue soltanto discovery e prezzi dei canali selezionati")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
