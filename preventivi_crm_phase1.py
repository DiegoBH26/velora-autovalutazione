"""Velora Preventivi & CRM — fase 1, rilevamento e bozze NON inviabili.

Modulo indipendente dai parser OTA. Non invia email, non esegue submit dei form,
non accede a Gmail. Ogni eventuale invio richiederà un passaggio separato,
autenticato e approvato esplicitamente dall'operatore.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

CONTACT_TERMS = ("preventivo", "richiedi disponibilità", "richiesta disponibilità",
                 "contattaci", "richiedi informazioni", "request a quote",
                 "enquire", "inquiry", "contact us", "booking request")
PRICE_TERMS = ("prenota ora", "book now", "verifica disponibilità", "check availability")
FIELD_ALIASES = {
    "first_name": ("nome", "first name", "firstname", "given-name"),
    "last_name": ("cognome", "last name", "lastname", "surname", "family-name"),
    "email": ("email", "e-mail", "mail"),
    "checkin": ("checkin", "check-in", "arrivo", "arrival", "dal"),
    "checkout": ("checkout", "check-out", "partenza", "departure", "al"),
    "adults": ("adulti", "adults", "guests", "ospiti"),
    "message": ("messaggio", "message", "richiesta", "notes", "note"),
}
ADDRESS = "veloracon@gmail.com"

class _FormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.active = None
        self.links = []
        self._a = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.active = {"action": a.get("action", ""), "method":a.get("method","get").lower(), "fields": []}
        elif tag in ("input", "textarea", "select") and self.active is not None:
            self.active["fields"].append({
                "name":a.get("name", ""), "id":a.get("id",""),
                "type":a.get("type",tag), "placeholder":a.get("placeholder",""),
                "required":"required" in a,
            })
        elif tag == "a":
            self._a = {"href":a.get("href",""), "label":""}

    def handle_data(self, data):
        if self._a is not None:
            self._a["label"] += data

    def handle_endtag(self, tag):
        if tag == "form" and self.active is not None:
            self.forms.append(self.active)
            self.active = None
        if tag == "a" and self._a is not None:
            self.links.append(self._a)
            self._a = None

def _field_role(field):
    name = " ".join(str(field.get(k) or "") for k in ("name","id","placeholder")).lower()
    for role, patterns in FIELD_ALIASES.items():
        if any(p in name for p in patterns):
            return role
    return "other"

def discover_contact_channels(html: str, page_url: str) -> dict:
    """Analizza markup già acquisito lecitamente; non effettua navigazione."""
    p = _FormParser()
    p.feed(html)
    base = urlparse(page_url)
    findings=[]
    for form in p.forms:
        action=urljoin(page_url, form["action"])
        target=urlparse(action)
        if target.scheme not in ("http","https") or target.netloc != base.netloc:
            # A third-party widget is visible, but submit policy unknown.
            classification="external_form_review"
        else:
            classification="quote_or_contact_form" if any(
                _field_role(f) in ("email","checkin","checkout","message") for f in form["fields"]
            ) else "form_review"
        findings.append({
            "type":classification, "actionUrl":action, "method":form["method"],
            "fields":[{**f,"role":_field_role(f)} for f in form["fields"]],
            "submitAllowed":False
        })
    for link in p.links:
        label=re.sub(r"\s+"," ",link["label"]).strip()
        href=urljoin(page_url,link["href"])
        if href.startswith("mailto:"):
            findings.append({"type":"email_contact","url":href,"label":label,"submitAllowed":False})
        elif any(t in label.lower() for t in CONTACT_TERMS):
            findings.append({"type":"contact_link","url":href,"label":label,"submitAllowed":False})
        elif any(t in label.lower() for t in PRICE_TERMS):
            findings.append({"type":"booking_engine_candidate","url":href,"label":label,"submitAllowed":False})
    return {"pageUrl":page_url,"channels":findings,"automaticSubmission":False}

def prepare_quote_draft(property_name: str, contact_url: str, stay: dict,
                        first_name: str, last_name: str, *,
                        consent_to_use_identity: bool=False) -> dict:
    """Prepara una bozza locale senza eseguire invii o precompilazioni sul sito."""
    if not consent_to_use_identity or not first_name.strip() or not last_name.strip():
        raise ValueError("Serve un referente reale autorizzato, con nome e cognome.")
    for required in ("checkin","checkout","adults"):
        if not stay.get(required):
            raise ValueError(f"Campo soggiorno mancante: {required}")
    checkin=str(stay["checkin"]); checkout=str(stay["checkout"])
    if datetime.fromisoformat(checkin).date() >= datetime.fromisoformat(checkout).date():
        raise ValueError("La data di partenza deve essere successiva all'arrivo.")
    return {
        "propertyName":property_name, "contactUrl":contact_url,
        "requester":{"firstName":first_name.strip(),"lastName":last_name.strip(),"email":ADDRESS},
        "stay":{"checkin":checkin,"checkout":checkout,"adults":int(stay["adults"])},
        "status":"draft_pending_manual_approval","approved":False,
        "sentAt":None,"messageId":None,
        "createdAt":datetime.now(timezone.utc).isoformat(),
        "message":(
            f"Buongiorno, sono {first_name.strip()} {last_name.strip()}, referente Velora Consulting. "
            f"Vorrei richiedere un preventivo per {int(stay['adults'])} adulti "
            f"dal {checkin} al {checkout} presso {property_name}. "
            "Potete indicare tipologia, prezzo totale, servizi inclusi e condizioni di cancellazione? "
            f"Potete rispondere a {ADDRESS}. Grazie."
        ),
    }
