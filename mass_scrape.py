#!/usr/bin/env python3
"""Raccoglie schede pubbliche di strutture ricettive senza browser grafico.

Le cifre trovate senza date, camera e condizioni sono *indizi di prezzo*, non
preventivi comparabili né ADR. Non aggira login, CAPTCHA o blocchi del sito.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import ipaddress
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

try:
    from curl_cffi.requests import AsyncSession
    from selectolax.lexbor import LexborHTMLParser
except ImportError as exc:
    raise SystemExit(
        "Librerie mancanti. Esegui: python -m pip install curl_cffi selectolax"
    ) from exc


LOG = logging.getLogger("velora-scrape")
BOT_UA = "VeloraAuditBot/1.0 (raccolta di dati pubblici; contattare il gestore del progetto)"
OTA_HOSTS = {
    "booking": ("booking.com",),
    "airbnb": ("airbnb.com", "airbnb.it"),
    "expedia": ("expedia.com", "expedia.it"),
    "vrbo": ("vrbo.com", "vrbo.it"),
    "agoda": ("agoda.com",),
    "hotels": ("hotels.com",),
    "trip": ("trip.com",),
}
PROPERTY_PATH = re.compile(
    r"(?:/hotel/|/rooms/\d+|/stays/|/property/|/properties/|"
    r"hotel|albergo|resort|b-and-b|bed-and-breakfast|vacation-rental|"
    r"apartment|appartament|villa|luxury-suite)", re.I
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PRICE_RE = re.compile(r"(?:€\s*|EUR\s*)(\d{1,5}(?:[.,]\d{2})?)", re.I)
FIELDS = [
    "source_url", "final_url", "platform", "status", "http_status", "observed_at",
    "name", "address", "city", "description", "amenities_json", "prices_json",
    "email", "phone", "photo_urls_json", "error",
]


def clean(text: object, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def unique(values: list[str], limit: int = 50) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))[:limit]


def normalize_url(value: str) -> str:
    value = value.strip()
    if value and not re.match(r"^https?://", value, re.I):
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"URL non valido: {value}")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError(f"Host locale non consentito: {value}")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError(f"IP non pubblico: {value}")
    except ValueError as exc:
        if "IP non pubblico" in str(exc):
            raise
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path or "/", "", parsed.query, ""))


def same_site(left: str, right: str) -> bool:
    def host(url: str) -> str:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    return host(left) == host(right)


def platform_for(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    for name, suffixes in OTA_HOSTS.items():
        if any(host == suffix or host.endswith("." + suffix) for suffix in suffixes):
            return name
    return "sito_ufficiale_o_portale"


def property_candidate(url: str) -> bool:
    path = urlparse(url).path
    platform = platform_for(url)
    if platform == "booking":
        return bool(re.search(r"/hotel/[a-z]{2}/", path, re.I))
    if platform == "airbnb":
        return bool(re.search(r"/rooms/\d+", path))
    return bool(PROPERTY_PATH.search(path))


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: str
    http_status: int = 0
    body: bytes = b""
    content_type: str = ""
    error: str = ""


class FastFetcher:
    def __init__(self, session: AsyncSession, concurrency: int, per_host: int, delay: float):
        self.session = session
        self.global_limit = asyncio.Semaphore(concurrency)
        self.per_host_limit = per_host
        self.delay = delay
        self.host_limits: dict[str, asyncio.Semaphore] = {}
        self.next_start: dict[str, float] = {}
        self.throttle_lock = asyncio.Lock()
        self.robots: dict[str, RobotFileParser | None] = {}
        self.robots_locks: dict[str, asyncio.Lock] = {}

    async def _robots(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self.robots:
            return self.robots[origin]
        async with self.robots_locks.setdefault(origin, asyncio.Lock()):
            if origin in self.robots:
                return self.robots[origin]
            robots_url = origin + "/robots.txt"
            try:
                async with self.global_limit:
                    response = await self.session.get(robots_url, timeout=15, allow_redirects=False)
                if response.status_code == 404:
                    parser = RobotFileParser()
                    parser.parse([])
                elif response.status_code != 200:
                    LOG.warning("robots.txt non verificabile (%s): %s", response.status_code, origin)
                    self.robots[origin] = None  # fail closed
                    return None
                else:
                    parser = RobotFileParser()
                    parser.set_url(robots_url)
                    parser.parse(response.text.splitlines())
                self.robots[origin] = parser
                return parser
            except Exception as exc:
                LOG.warning("robots.txt non verificabile per %s: %s", origin, exc)
                self.robots[origin] = None
                return None

    async def get(self, url: str, redirects: int = 0) -> FetchResult:
        try:
            url = normalize_url(url)
        except ValueError as exc:
            return FetchResult(url, url, "invalid_url", error=str(exc))
        if redirects > 3:
            return FetchResult(url, url, "redirect_limit", error="Troppi redirect")
        parser = await self._robots(url)
        if parser is None or not parser.can_fetch(BOT_UA, url):
            return FetchResult(url, url, "robots_denied", error="robots.txt non consente o non è verificabile")
        host = urlparse(url).netloc.lower()
        host_limit = self.host_limits.setdefault(host, asyncio.Semaphore(self.per_host_limit))
        crawl_delay = parser.crawl_delay(BOT_UA) or parser.crawl_delay("*") or 0
        pause = max(self.delay, float(crawl_delay))
        async with self.global_limit, host_limit:
            for attempt in range(3):
                async with self.throttle_lock:
                    now = time.monotonic()
                    wait = max(0.0, self.next_start.get(host, 0.0) - now)
                    self.next_start[host] = max(now, self.next_start.get(host, 0.0)) + pause
                if wait:
                    await asyncio.sleep(wait)
                try:
                    response = await self.session.get(url, timeout=25, allow_redirects=False)
                    status = response.status_code
                    if status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("Location", "")
                        target = urljoin(url, location)
                        break
                    if status in {429, 500, 502, 503, 504} and attempt < 2:
                        retry_after = response.headers.get("Retry-After", "")
                        wait_for = min(float(retry_after), 30.0) if retry_after.isdigit() else 0.7 * (2**attempt) + random.uniform(0.1, 0.7)
                        await asyncio.sleep(wait_for)
                        continue
                    if status in {401, 403}:
                        return FetchResult(url, url, "access_denied", status, error="Accesso negato; nessun aggiramento tentato")
                    if status >= 400:
                        return FetchResult(url, url, "http_error", status, error=f"HTTP {status}")
                    body = response.content
                    if len(body) > 8_000_000:
                        return FetchResult(url, url, "too_large", status, error="Contenuto oltre 8 MB")
                    opening = body[:120_000].lower()
                    if status != 200 or any(marker in opening for marker in (
                        b"<title>javascript is disabled", b"<title>just a moment", b"captcha challenge",
                        b"enable javascript to continue", b"checking your browser before accessing",
                    )):
                        return FetchResult(url, url, "challenge_or_nonstandard", status,
                                           error="La risposta non e' una scheda HTML ordinaria; nessun dato estratto")
                    return FetchResult(url, url, "ok", status, body, response.headers.get("Content-Type", ""))
                except Exception as exc:
                    if attempt == 2:
                        return FetchResult(url, url, "network_error", error=clean(exc, 300))
                    await asyncio.sleep(0.7 * (2**attempt) + random.uniform(0.1, 0.7))
            else:
                return FetchResult(url, url, "network_error", error="Tre tentativi esauriti")
        # Il redirect si segue fuori dai semafori, verificando robots.txt del nuovo host.
        result = await self.get(target, redirects + 1)
        result.url = url
        return result


def sitemap_urls(payload: bytes, source: str) -> tuple[list[str], list[str]]:
    if source.lower().split("?")[0].endswith(".gz") or payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    root = ElementTree.fromstring(payload)
    tag = root.tag.rsplit("}", 1)[-1].lower()
    locs = [clean(node.text, 2000) for node in root.iter() if node.tag.rsplit("}", 1)[-1].lower() == "loc"]
    return (locs, []) if tag == "sitemapindex" else ([], locs)


async def discover(seed: str, fetcher: FastFetcher, max_links: int) -> list[str]:
    seed = normalize_url(seed)
    found = [seed]
    sitemap_queue = [urljoin(seed, "/sitemap.xml")]
    seen_sitemaps: set[str] = set()
    while sitemap_queue and len(seen_sitemaps) < 20 and len(found) < max_links:
        sitemap = sitemap_queue.pop(0)
        if sitemap in seen_sitemaps:
            continue
        seen_sitemaps.add(sitemap)
        result = await fetcher.get(sitemap)
        if result.status != "ok":
            continue
        try:
            nested, pages = sitemap_urls(result.body, sitemap)
        except (ElementTree.ParseError, OSError, EOFError) as exc:
            LOG.debug("Sitemap non leggibile %s: %s", sitemap, exc)
            continue
        sitemap_queue += [url for url in nested if same_site(seed, url)]
        for url in pages:
            if same_site(seed, url) and property_candidate(url):
                try:
                    found.append(normalize_url(url))
                except ValueError:
                    pass
            if len(found) >= max_links:
                break
    if len(found) == 1:
        result = await fetcher.get(seed)
        if result.status == "ok" and "html" in result.content_type.lower():
            tree = LexborHTMLParser(result.body)
            for anchor in tree.css("a[href]"):
                candidate = urljoin(seed, anchor.attributes.get("href") or "")
                if same_site(seed, candidate) and property_candidate(candidate):
                    try:
                        found.append(normalize_url(candidate))
                    except ValueError:
                        pass
                if len(found) >= max_links:
                    break
    return unique(found, max_links)


def ld_objects(tree: LexborHTMLParser) -> list[dict]:
    objects: list[dict] = []

    def walk(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            objects.append(value)
            if "@graph" in value:
                walk(value["@graph"])

    for node in tree.css('script[type="application/ld+json"]'):
        try:
            walk(json.loads(node.text()))
        except (TypeError, json.JSONDecodeError):
            continue
    return objects


def first_text(tree: LexborHTMLParser, selectors: list[str], limit: int = 4000) -> str:
    for selector in selectors:
        node = tree.css_first(selector)
        if node:
            text = clean(node.text(separator=" "), limit)
            if text:
                return text
    return ""


def meta(tree: LexborHTMLParser, key: str) -> str:
    for selector in (f'meta[property="{key}"]', f'meta[name="{key}"]'):
        node = tree.css_first(selector)
        if node:
            return clean(node.attributes.get("content"))
    return ""


def listify(value: object) -> list[object]:
    return value if isinstance(value, list) else ([] if value is None else [value])


def image_url(value: object) -> str:
    if isinstance(value, dict):
        return clean(value.get("url") or value.get("contentUrl"), 2000)
    return clean(value, 2000)


def extract(result: FetchResult) -> dict[str, str]:
    row = {field: "" for field in FIELDS}
    row.update(source_url=result.url, final_url=result.final_url, platform=platform_for(result.final_url),
               status=result.status, http_status=str(result.http_status or ""),
               observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), error=result.error)
    if result.status != "ok":
        return row
    if "html" not in result.content_type.lower():
        row.update(status="not_html", error=f"Content-Type: {result.content_type}")
        return row
    tree = LexborHTMLParser(result.body)
    ld = ld_objects(tree)
    lodging_types = {"hotel", "lodgingbusiness", "bedandbreakfast", "motel", "hostel", "resort", "vacationrental", "accommodation", "apartment", "house"}
    lodging = next((item for item in ld if any(str(part).lower().split("/")[-1] in lodging_types for part in listify(item.get("@type")))), {})
    selector_map = {
        "booking": ["[data-testid='title']", "[data-testid='property-title']", ".pp-header__title", "h1"],
        "airbnb": ["[data-section-id='TITLE_DEFAULT'] h1", "h1"],
        "expedia": ["[data-stid='content-hotel-title']", "h1"],
    }
    name = clean(lodging.get("name"))
    if not name and row["platform"] == "sito_ufficiale_o_portale":
        name = meta(tree, "og:title")
    name = name or first_text(tree, selector_map.get(row["platform"], ["h1"])) or meta(tree, "og:title")
    address = lodging.get("address") or {}
    if isinstance(address, dict):
        city = clean(address.get("addressLocality"))
        address_text = clean(", ".join(str(address.get(key, "")) for key in ("streetAddress", "postalCode", "addressLocality", "addressRegion", "addressCountry") if address.get(key)))
    else:
        city, address_text = "", clean(address)
    address_text = address_text or first_text(tree, ["[data-testid='address']", "[itemprop='address']", "address"])
    description = clean(lodging.get("description"), 20000) or first_text(tree, ["[data-testid='property-description']", "[data-testid='description']", "[data-section-id='DESCRIPTION_DEFAULT']"], 20000)
    if not description:
        description = clean(" ".join(clean(node.text(separator=" "), 1000) for node in tree.css("main p")[:80]), 20000)
    description = description or meta(tree, "og:description") or meta(tree, "description")
    amenities = []
    for value in listify(lodging.get("amenityFeature")):
        if isinstance(value, dict):
            if value.get("value") is not False:
                amenities.append(clean(value.get("name")))
        else:
            amenities.append(clean(value))
    for selector in ("[data-testid='facility-item']", "[data-testid*='amenity']", "[data-section-id='AMENITIES_DEFAULT']", "[itemprop='amenityFeature']", ".amenities li", ".facilities li"):
        amenities += [clean(node.text(separator=" "), 120) for node in tree.css(selector)[:30]]
    photos = [image_url(value) for value in listify(lodging.get("image"))]
    photos += [meta(tree, "og:image")]
    for node in tree.css("img[src], img[data-src]")[:80]:
        src = node.attributes.get("src") or node.attributes.get("data-src") or ""
        if src and not src.startswith("data:"):
            photos.append(urljoin(result.final_url, src))
    photos = unique(photos, 30)
    email = clean(lodging.get("email"))
    phone = clean(lodging.get("telephone"))
    for node in tree.css("a[href^='mailto:']")[:5]:
        email = email or clean((node.attributes.get("href") or "").split(":", 1)[-1].split("?", 1)[0])
    for node in tree.css("a[href^='tel:']")[:5]:
        phone = phone or clean((node.attributes.get("href") or "").split(":", 1)[-1])
    if not email and row["platform"] == "sito_ufficiale_o_portale":
        match = EMAIL_RE.search(tree.body.text(separator=" ") if tree.body else "")
        email = match.group(0) if match else ""
    prices: list[dict] = []
    for item in ld:
        for offer in listify(item.get("offers")):
            if not isinstance(offer, dict) or offer.get("price") is None:
                continue
            prices.append({"amount": str(offer["price"]), "currency": clean(offer.get("priceCurrency")),
                           "label": clean(offer.get("name"), 150), "context": "listino/Offer; date e condizioni non verificate"})
    if lodging.get("priceRange"):
        prices.append({"amount": clean(lodging["priceRange"], 120), "currency": "", "label": "priceRange",
                       "context": "fascia indicativa; date e condizioni non verificate"})
    if not prices:
        for selector in ("[data-testid='price-and-discounted-price']", "[data-testid='price-summary']", "[data-testid='price-breakdown']", "[itemprop='price']"):
            for node in tree.css(selector)[:10]:
                text = clean(node.text(separator=" "), 180)
                match = PRICE_RE.search(text)
                if match:
                    prices.append({"amount": match.group(1), "currency": "EUR", "label": text,
                                   "context": "prezzo HTML; date e condizioni non verificate"})
    row.update(name=name, address=address_text, city=city, description=description,
               amenities_json=json.dumps(unique(amenities, 60), ensure_ascii=False),
               prices_json=json.dumps(prices[:20], ensure_ascii=False), email=email, phone=phone,
               photo_urls_json=json.dumps(photos, ensure_ascii=False))
    if not name:
        row.update(status="unclassified", error="Nome struttura non identificabile nell'HTML pubblico")
    return row


def load_seeds(args: argparse.Namespace) -> list[str]:
    values = list(args.urls)
    if args.input:
        input_path = Path(args.input)
        if input_path.suffix.lower() == ".csv":
            with input_path.open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream)
                column = next((name for name in ("url", "source_url", "website", "sito") if name in (reader.fieldnames or [])), None)
                if not column:
                    raise SystemExit("Il CSV di input richiede una colonna url, source_url, website o sito.")
                values += [row[column].strip() for row in reader if row.get(column) and row[column].strip()]
        else:
            values += [line.strip() for line in input_path.read_text(encoding="utf-8-sig").splitlines()
                       if line.strip() and not line.lstrip().startswith("#")]
    if not values:
        raise SystemExit("Indica almeno un URL o --input con un URL per riga.")
    return unique([normalize_url(value) for value in values], 10000)


async def run(args: argparse.Namespace) -> None:
    seeds = load_seeds(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    if output.exists() and output.stat().st_size:
        with output.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != FIELDS:
                raise SystemExit("Il CSV esistente ha colonne diverse: usa un nuovo --output.")
            existing = {row["source_url"] for row in reader}
    async with AsyncSession(impersonate="chrome120", headers={"User-Agent": BOT_UA, "Accept-Language": "it-IT,it;q=0.9"}) as session:
        fetcher = FastFetcher(session, args.concurrency, args.per_host, args.delay)
        groups = await asyncio.gather(*(discover(seed, fetcher, args.max_links_per_seed) for seed in seeds), return_exceptions=True)
        urls: list[str] = []
        for seed, group in zip(seeds, groups):
            if isinstance(group, BaseException):
                LOG.warning("Discovery non riuscita per %s: %s", seed, group)
                urls.append(seed)
            else:
                urls.extend(group)
        targets = [url for url in unique(urls, len(urls)) if url not in existing][:args.max_pages]
        LOG.info("%s URL scoperti, %s nuovi da leggere", len(set(urls)), len(targets))

        async def job(url: str) -> dict[str, str]:
            try:
                return extract(await fetcher.get(url))
            except Exception as exc:
                return extract(FetchResult(url, url, "parse_error", error=clean(exc, 300)))

        with output.open("a", newline="", encoding="utf-8-sig" if not output.exists() or not output.stat().st_size else "utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            if not existing and stream.tell() == 0:
                writer.writeheader()
            tasks = [asyncio.create_task(job(url)) for url in targets]
            try:
                for index, task in enumerate(asyncio.as_completed(tasks), 1):
                    row = await task
                    writer.writerow(row)
                    stream.flush()  # ogni scheda rimane salvata anche se il processo si interrompe
                    if index % 25 == 0 or index == len(tasks):
                        LOG.info("Salvate %s/%s schede; ultima: %s", index, len(tasks), row["source_url"])
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()
    LOG.info("Completato: %s", output.resolve())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", help="Domini o pagine iniziali")
    parser.add_argument("--input", help="File TXT (un URL per riga) o CSV (colonna url/source_url/website/sito)")
    parser.add_argument("--output", default="dati_strutture.csv")
    parser.add_argument("--max-pages", type=int, default=500)
    parser.add_argument("--max-links-per-seed", type=int, default=300)
    parser.add_argument("--concurrency", type=int, default=15)
    parser.add_argument("--per-host", type=int, default=2)
    parser.add_argument("--delay", type=float, default=1.0, help="Secondi minimi tra avvii sullo stesso host")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if not (1 <= args.concurrency <= 15 and 1 <= args.per_host <= 3 and 0.5 <= args.delay <= 30 and args.max_pages > 0 and args.max_links_per_seed > 0):
        parser.error("Concorrenza 1-15, per-host 1-3, delay 0.5-30, limiti URL positivi.")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        LOG.warning("Interrotto: le righe già scritte restano nel CSV. Rilancia per riprendere.")
        sys.exit(130)


if __name__ == "__main__":
    main()
