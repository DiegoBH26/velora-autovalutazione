"""Individua indizi pubblici sul booking engine senza inventare il fornitore.

La presenza di un link non conferma disponibilità, tariffe o checkout riuscito.
Il dominio/URL viene usato come prova del fornitore soltanto per host noti.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

from selectolax.lexbor import LexborHTMLParser


OTA_HOSTS = (
    "booking.com", "airbnb.com", "airbnb.it", "expedia.com", "expedia.it",
    "vrbo.com", "vrbo.it", "hotels.com", "agoda.com", "trip.com",
    "google.com", "google.it", "holidaycheck.de",
)
BOOKING_WORDS = re.compile(r"\b(prenota|prenotazioni|book(?:ing)?|reserv(?:ation|a)|disponibilit[aà]|availability)\b", re.I)
CONTACT_WORDS = re.compile(r"/(?:contatt[io]|contact|richiedi[-_/]?info|inquiry|request)(?:[/?#-]|$)", re.I)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _public_url(value: str, base: str) -> str:
    resolved = urljoin(base, value.strip())
    parsed = urlparse(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return ""
    # Le query di prenotazione possono contenere token o dati del soggiorno.
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", "", ""))


def _provider(host: str) -> str:
    if host.endswith(".kross.travel") or host == "book.krossbooking.com":
        return "Kross Booking"
    if host == "book.ermeshotels.com" or host.endswith(".book.ermeshotels.com"):
        return "ErmesHotels"
    return ""


def _is_ota(host: str) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in OTA_HOSTS)


def detect_booking_engine(page_url: str, html: str, final_url: str | None = None) -> dict[str, str]:
    """Return provider, URL, mode and evidence; uncertainty is explicit."""
    final = final_url or page_url
    host = _host(final)
    known = _provider(host)
    if known:
        return {"status": "provider_identified", "provider": known, "url": _public_url(final, final),
                "mode": "pagina ospitata dal fornitore", "evidence": "Dominio della pagina di prenotazione"}
    if _is_ota(host):
        return {"status": "not_applicable", "provider": "", "url": "", "mode": "OTA",
                "evidence": "Una scheda OTA non identifica il booking engine diretto della struttura."}

    tree = LexborHTMLParser(html)
    candidates: list[tuple[int, str, str, str, str]] = []
    for selector, attr, mode in (("a[href]", "href", "link dal sito"),
                                 ("iframe[src]", "src", "widget incorporato"),
                                 ("form[action]", "action", "modulo di prenotazione")):
        for node in tree.css(selector)[:300]:
            raw = node.attributes.get(attr) or ""
            url = _public_url(raw, final)
            if not url:
                continue
            target_host = _host(url)
            if _is_ota(target_host):
                continue
            text = " ".join((node.text(separator=" "), node.attributes.get("aria-label", ""),
                             node.attributes.get("title", "")))[:180]
            if CONTACT_WORDS.search(url):
                continue
            vendor = _provider(target_host)
            booking_path = BOOKING_WORDS.search(urlparse(url).path.replace("-", " "))
            booking_text = BOOKING_WORDS.search(text)
            if vendor:
                # Un link al sito marketing del software non basterebbe; qui
                # si riconoscono solo gli host del suo percorso di acquisto.
                candidates.append((0 if mode != "link dal sito" else 1, vendor, url, mode, text))
            elif booking_path or booking_text:
                score = 2 if target_host != host else 3
                candidates.append((score, "", url, mode, text))

    if candidates:
        _, vendor, url, mode, text = sorted(candidates, key=lambda row: row[0])[0]
        evidence = f"{mode}: {text.strip() or urlparse(url).path}"[:250]
        return {"status": "provider_identified" if vendor else "provider_unknown",
                "provider": vendor, "url": url, "mode": mode, "evidence": evidence}
    return {"status": "not_found_in_page", "provider": "", "url": "", "mode": "non rilevato",
            "evidence": "Nessun percorso di prenotazione identificabile nell'HTML esaminato; non prova l'assenza di un booking engine."}
