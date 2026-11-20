"""Evidenze commerciali del sito diretto, senza dedurre prezzi o disponibilità.
Nessun acquisto, login, elusione di controlli o navigazione aggressiva.
"""
from __future__ import annotations
import re
from urllib.parse import urlparse, urljoin
from site_audit_builder import public_url, robots_allowed
from booking_engine import detect_booking_engine
from playwright.async_api import async_playwright

def _safe(url):
    p=urlparse(str(url or ""))
    return p.scheme in ("https","http") and bool(p.hostname) and not (
        p.hostname in ("localhost","127.0.0.1") or p.hostname.endswith(".local"))

async def follow_booking_cta(site_url, engine, *, timeout_ms=18000):
    """Follow the actual booking CTA without treating OTA links as direct engines.

    A link on an inner Hotel/Rooms page counts even when the homepage has none.
    We keep the DOM observation if the click cannot be verified, and never
    open booking dates or payments here.
    """
    from booking_engine import _ota_name, _public_url
    evidence={"status":"not_verified","resolvedUrl":"","connectionType":"",
              "provider":"","otaName":"","evidence":[]}
    if not _safe(site_url) or robots_allowed(site_url,{}) is not True:
        evidence["evidence"].append("Visita CTA non autorizzata o sito non valido.")
        return evidence
    is_ota=engine.get("status")=="ota_redirect"
    source=engine.get("otaSourcePage") if is_ota else site_url
    source=source if (_safe(source) and
        (urlparse(source).hostname or "").lower().removeprefix("www.")==
        (urlparse(site_url).hostname or "").lower().removeprefix("www.")) else site_url
    if robots_allowed(source,{}) is False:
        evidence["evidence"].append("Pagina contenente il pulsante Prenota non accessibile secondo robots.txt.")
        return evidence
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel="chrome",headless=True)
        try:
            context=await browser.new_context(locale="it-IT",timezone_id="Europe/Rome")
            page=await context.new_page()
            try:
                response=await page.goto(source,wait_until="domcontentloaded",timeout=timeout_ms)
                if not response or response.status>=400:return evidence
                await page.wait_for_timeout(650)
                candidates=page.locator("a[href]:visible")
                target=engine.get("otaUrl") if is_ota else (engine.get("url") or "")
                chosen=None
                for i in range(min(await candidates.count(),220)):
                    a=candidates.nth(i)
                    href=await a.get_attribute("href") or ""
                    try:label=await a.inner_text(timeout=1200)
                    except Exception:label=""
                    if is_ota:
                        url=urljoin(page.url,href)
                        expected=urlparse(target)
                        observed=urlparse(url)
                        if (_ota_name((observed.hostname or "").lower().removeprefix("www."))
                            and observed.hostname==expected.hostname
                            and observed.path.rstrip("/")==expected.path.rstrip("/")
                            and re.search(r"prenot|book|reserve",label,re.I)):
                            chosen=a
                            break
                    elif "booking.bedzzle.com" in href or (
                        target and urlparse(target).hostname and
                        urlparse(target).hostname in href and
                        re.search(r"prenot|book",label,re.I)):
                        chosen=a
                        break
                if chosen is None:
                    evidence["evidence"].append(
                        "CTA osservata nell'audit DOM, ma non cliccabile con un collegamento univoco.")
                    return evidence
                original=page.url
                before=set(context.pages)
                await chosen.click(timeout=4500)
                await page.wait_for_timeout(1200)
                after=[p for p in context.pages if p not in before]
                destination=after[-1] if after else page
                try:await destination.wait_for_load_state("domcontentloaded",timeout=5500)
                except Exception:pass
                final=destination.url
                if not _safe(final) or final==original:
                    evidence["evidence"].append("La CTA non ha mostrato una navigazione verificabile.")
                    return evidence
                final_host=(urlparse(final).hostname or "").lower().removeprefix("www.")
                ota=_ota_name(final_host)
                if ota:
                    evidence.update(status="ota_redirect_verified",
                        resolvedUrl=_public_url(final,final),
                        connectionType=("nuova scheda" if after else "stessa scheda")
                            +" verso una OTA",
                        otaName=ota)
                    evidence["evidence"].append(
                        "Pulsante Prenota cliccato: la pagina di destinazione appartiene a "+
                        ota+". NON e' un booking engine diretto.")
                    return evidence
                detected=detect_booking_engine(final,"",final)
                if detected.get("status")!="provider_identified":
                    evidence["evidence"].append(
                        "CTA raggiunta, ma booking engine diretto non identificato.")
                    return evidence
                evidence.update(status="reached",
                    resolvedUrl=detected.get("url") or "",
                    connectionType=("nuova scheda" if after else "stessa scheda")
                        +(" verso dominio esterno"
                          if urlparse(final).hostname!=urlparse(original).hostname else ""),
                    provider=detected.get("provider") or "")
                evidence["evidence"].append(
                    "CTA Prenota cliccata; booking engine del fornitore identificato.")
            except Exception as exc:
                evidence["status"]="error"
                evidence["evidence"].append(
                    "Navigazione CTA non conclusa: "+type(exc).__name__)
            finally:
                await context.close()
        finally:
            await browser.close()
    return evidence

async def inspect_direct_booking(site_url, engine, *, timeout_ms=18000):
    """Esamina in sola lettura il percorso identificato dall'audit.
    I prezzi osservati senza date/occupazione NON sono preventivi validati.
    """
    url=(engine or {}).get("url") or ""
    base={"status":"not_verified","provider":(engine or {}).get("provider") or "",
          "engineUrl":url,"connectionType":(engine or {}).get("mode") or "",
          "website":site_url,"navigation":"not_tested","finalUrl":"",
          "bookingFlow":"not_verified","datedPrices":[],
          "availability":"not_verified","observedPriceTexts":[],
          "evidence":[]}
    if not _safe(url):
        base["evidence"].append("Nessun URL transazionale verificabile rilevato; non equivale ad assenza del booking engine.")
        return base
    try:
        url = public_url(url)
    except ValueError:
        base["status"]="invalid_url"
        base["evidence"].append("URL booking engine non pubblico o non sicuro.")
        return base
    if robots_allowed(url, {}) is False:
        base["status"]="robots_denied"
        base["evidence"].append("Verifica non eseguita: robots.txt non permette la navigazione automatica.")
        return base
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel="chrome", headless=True)
        try:
            context=await browser.new_context(locale="it-IT",timezone_id="Europe/Rome",accept_downloads=False)
            page=await context.new_page()
            try:
                response=await page.goto(url,wait_until="domcontentloaded",timeout=timeout_ms)
                await page.wait_for_timeout(700)
                base["finalUrl"]=page.url.split("?")[0].split("#")[0]
                base["navigation"]="reached" if response and response.status < 400 else "http_error"
                info=await page.evaluate("""() => {
                  const visible=e=>!!(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
                  const inputs=[...document.querySelectorAll('input,select')].filter(visible);
                  const fields=inputs.map(x=>((x.name||'')+' '+(x.placeholder||'')+' '+(x.type||'')+' '+(x.getAttribute('aria-label')||'')).toLowerCase());
                  const body=(document.body?.innerText||'').slice(0,14000);
                  const actions=[...document.querySelectorAll('button,a,[role=button]')].filter(visible).map(e=>(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,90)).filter(Boolean).slice(0,80);
                  return {title:document.title,fields,body,actions};
                }""")
                fields=" ".join(info["fields"]); body=info["body"].lower()
                has_dates=bool(re.search(r"check.?in|check.?out|arrival|departure|arrivo|partenza|date",fields))
                has_guests=bool(re.search(r"guest|adult|ospit|person|occup",fields))
                has_booking_action=any(re.search(r"prenot|book|continua|continue|cerca|search|verifica disponibilit",x,re.I) for x in info["actions"])
                base["controls"]={"dates":has_dates,"guests":has_guests,"bookingAction":has_booking_action}
                base["bookingFlow"]="form_observed_not_completed" if has_booking_action and (has_dates or has_guests) else "not_verified"
                base["evidence"].append("Pagina raggiunta; controlli visibili: date=%s, ospiti=%s, azione prenotazione=%s."%(has_dates,has_guests,has_booking_action))
                if re.search(r"access denied|captcha|robot|accesso negato",body):
                    base["status"]="blocked"
                    base["evidence"].append("Il sito mostra una possibile limitazione d'accesso.")
                else:
                    base["status"]="page_observed"
                price_re=re.compile(r"(?:€\s*\d[\d.,]*|\d[\d.,]*\s*€)")
                base["observedPriceTexts"]=price_re.findall(info["body"])[:10]
                if base["observedPriceTexts"]:
                    base["evidence"].append("Importi generici visibili: NON verificati per date, ospiti, camera e condizioni.")
            except Exception as exc:
                base["status"]="error"
                base["evidence"].append("Navigazione non conclusa: "+type(exc).__name__)
            finally:
                await context.close()
        finally:
            await browser.close()
    return base

def concise_engine_fields(audit, verification):
    """Campi normalizzati da collegare alla scheda Booking engine della UI."""
    be=audit.get("bookingEngine") or {}
    return {"verificationStatus":verification.get("status","not_verified"),
            "provider":be.get("provider") or "",
            "bookingUrl":be.get("url") or "",
            "connectionType":be.get("mode") or "",
            "evidence":" | ".join(x for x in [
                be.get("evidence",""),*verification.get("evidence",[])
            ] if x)[:1600],
            "providerIdentified":be.get("status")=="provider_identified",
            "bookingOperationalVerified":False,
            "pricingVerified":False,
            "availabilityVerified":False}
