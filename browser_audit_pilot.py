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
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
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


def visible_dates_confirmed(text: str, stay: dict) -> bool:
    """Conservativo: le date richieste devono apparire nella pagina renderizzata."""
    start, end = date.fromisoformat(stay["checkin"]), date.fromisoformat(stay["checkout"])
    lowered = text.lower()
    # Le lingue e i formati variano. Un URL con date non basta come prova.
    forms = lambda day: (day.isoformat(), f"{day.day:02d}/{day.month:02d}/{day.year}",
                         f"{day.day}/{day.month}/{day.year}")
    return any(value in lowered for value in forms(start)) and any(value in lowered for value in forms(end))


def write_result(path: Path, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


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
        # Il contenuto OTA spesso compare dopo il primo DOM; il limite resta breve.
        try:
            await page.locator("body").wait_for(state="visible", timeout=5000)
            await page.wait_for_timeout(1500)
        except PlaywrightTimeout:
            pass
        record["finalUrl"] = page.url
        record["title"] = (await page.title())[:200]
        body = (await page.locator("body").inner_text(timeout=7000))[:12000]
        text = (record["title"] + " " + body).lower()
        if response and response.status >= 400:
            record.update(status="http_error", evidence=f"HTTP {response.status}")
        elif any(word in text for word in BLOCK_WORDS):
            record.update(status="blocked", evidence="Il portale ha mostrato una pagina di verifica/blocco; nessun prezzo acquisito.")
        elif not body.strip():
            record.update(status="empty_page", evidence="Pagina senza contenuto leggibile nel campione.")
        elif not visible_dates_confirmed(body, stay):
            record.update(status="dates_unconfirmed", evidence="Le date richieste non sono confermate nel contenuto visibile: prezzi non utilizzabili.")
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
                                                  "evidence": "Non ancora esaminato."}, "observations": []}
    output = Path(args.output)
    if args.dry_run:
        write_result(output, result)
        return result
    robots: dict[str, RobotFileParser | bool | None] = {}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(locale="it-IT", timezone_id="Europe/Rome")
        try:
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
                        record = {"otaId": channel, **stay, "status": "source_missing", "quotes": [],
                                  "evidence": "Nessuna scheda univoca conosciuta per questo portale."}
                    else:
                        page = await context.new_page()
                        try:
                            record = await observe(page, channel, source, stay, robots)
                        finally:
                            await page.close()
                    result["observations"].append(record)
                    write_result(output, result)
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
