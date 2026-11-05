"""Campioni commerciali diretti in sola lettura.

Solo finestre identiche a Booking, nessuna invenzione di prezzi. I campioni
non verificati restano osservazioni e non entrano in delta o disponibilità.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from site_audit_builder import public_url, robots_allowed

_DATE_PATTERN=re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PRICE_PATTERN=re.compile(r"(?:€\s*([0-9][0-9.,]*)|([0-9][0-9.,]*)\s*€)")

def eligible_stays(rows, *, limit=4):
    """Non usare slittamenti automatici e non inventare date."""
    selected=[]
    for item in rows or []:
        if not isinstance(item,dict): continue
        arrival=str(item.get("checkin") or "")
        departure=str(item.get("checkout") or "")
        if not (_DATE_PATTERN.fullmatch(arrival) and _DATE_PATTERN.fullmatch(departure)):
            continue
        if arrival!=str(item.get("requestedCheckin") or "") or departure!=str(item.get("requestedCheckout") or ""):
            continue
        try:
            nights=(date.fromisoformat(departure)-date.fromisoformat(arrival)).days
        except ValueError: continue
        adults=int(item.get("adults") or 2)
        if not (1<=nights<=60 and 1<=adults<=12 and date.fromisoformat(arrival)>=date.today()):
            continue
        key=(arrival,departure,adults)
        if any((x["checkin"],x["checkout"],x["guests"])==key for x in selected): continue
        selected.append({"checkin":arrival,"checkout":departure,"guests":adults,"nights":nights})
        if len(selected)>=limit:break
    return selected

def _money(raw):
    s=re.sub(r"[^0-9.,]","",str(raw or ""))
    if not s:return None
    if "," in s and "." in s:
        s=s.replace(".","").replace(",",".") if s.rfind(",")>s.rfind(".") else s.replace(",","")
    elif "," in s:s=s.replace(",",".") if len(s.split(",")[-1])<=2 else s.replace(",","")
    elif "." in s and len(s.split(".")[-1])==3:s=s.replace(".","")
    try:
        v=float(s)
        return round(v,2) if 10<=v<=100000 else None
    except ValueError:return None

async def _apply_dates(page, stay):
    """Date input native: no guessing in datepicker widgets."""
    controls=await page.evaluate("""() => {
      const all=[...document.querySelectorAll('input')].filter(e=>e.offsetWidth||e.offsetHeight||e.getClientRects().length);
      return all.map(e=>({name:(e.name||'').toLowerCase(),id:(e.id||'').toLowerCase(),
        placeholder:(e.placeholder||'').toLowerCase(),type:e.type,value:e.value})).slice(0,100);
    }""")
    targets={}
    for i,row in enumerate(controls):
        label=" ".join([row["name"],row["id"],row["placeholder"]])
        if row["type"]=="date" and re.search(r"check.?in|arriv|start|from|entrata",label):targets["checkin"]=i
        elif row["type"]=="date" and re.search(r"check.?out|partenz|end|to|uscita",label):targets["checkout"]=i
    if len(targets)!=2:return {"applied":False,"reason":"Selettore date personalizzato o campi non riconosciuti"}
    inputs=page.locator("input:visible")
    # Only native dates; never click through unknown form/payment buttons.
    for name,index in targets.items():
        await inputs.nth(index).fill(stay[name],timeout=4500)
    actual=await page.evaluate("""() => [...document.querySelectorAll('input')].filter(e=>e.offsetWidth||e.offsetHeight||e.getClientRects().length).map(e=>e.value)""")
    valid=all(stay[key] in actual for key in ("checkin","checkout"))
    return {"applied":valid,"reason":"Date native impostate" if valid else "Le date sono state modificate dal booking engine"}

async def probe_direct_stays(url, rows, *, limit=4):
    stays=eligible_stays(rows,limit=limit)
    result={"status":"not_checked","samples":[],"verifiedQuotes":[],"evidence":[]}
    if not stays:
        result["status"]="missing_booking_reference"
        result["evidence"].append("Nessuna finestra futura esatta confermata da Booking; prezzi diretti non confrontabili.")
        return result
    try:
        url=public_url(url)
    except ValueError:
        result["status"]="missing_engine_url";return result
    if robots_allowed(url,{}) is not True:
        result["status"]="robots_unverified";result["evidence"].append("Navigazione non autorizzata o robots.txt non conclusivo.");return result
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel="chrome",headless=True)
        try:
            context=await browser.new_context(locale="it-IT",timezone_id="Europe/Rome",accept_downloads=False)
            for stay in stays:
                sample={**stay,"status":"not_verified","sourceUrl":url,"quotes":[],
                        "availability":"not_verified","evidence":[]}
                page=await context.new_page()
                try:
                    response=await page.goto(url,wait_until="domcontentloaded",timeout=18000)
                    if not response or response.status>=400:
                        sample["status"]="navigation_error";sample["evidence"].append("Pagina non accessibile")
                    else:
                        await page.wait_for_timeout(800)
                        applied=await _apply_dates(page,stay)
                        sample["controls"]=applied
                        if not applied["applied"]:
                            sample["status"]="dates_not_selectable"
                            sample["evidence"].append(applied["reason"])
                        else:
                            # Avoid submitting forms with unknown side effects.
                            # Search CTA is allowed only when explicitly a search, never checkout.
                            buttons=page.get_by_role("button",name=re.compile(r"^(cerca|search|verifica disponibilit[aà]|check availability|mostra disponibilit[aà])$",re.I))
                            if await buttons.count()==1:
                                await buttons.first.click(timeout=4500)
                                await page.wait_for_timeout(1300)
                            current=await page.evaluate("""() => ({
                              fields:[...document.querySelectorAll('input[type=date]')].map(x=>x.value),
                              url:location.href,
                              text:(document.body?.innerText||'').slice(0,22000)
                            })""")
                            page_text=current["text"]
                            actual_dates=set(current["fields"])
                            date_confirmed=stay["checkin"] in actual_dates and stay["checkout"] in actual_dates
                            sample["status"]="date_context_observed" if date_confirmed else "dates_unconfirmed"
                            sample["sourceUrl"]=page.url.split("?")[0].split("#")[0]
                            prices=[{"amount":_money(m.group(0)),"text":m.group(0)}
                                    for m in list(_PRICE_PATTERN.finditer(page_text))[:20]]
                            sample["visiblePrices"]=[p for p in prices if p["amount"] is not None][:12]
                            sample["evidence"].append("Contesto date presente; gli importi generici non indicano camera, totale, tasse o condizioni.")
                            # Never advertise dated quotes without confirmed room/type,
                            # total-stay basis, rate conditions and availability.
                except Exception as exc:
                    sample["status"]="navigation_error"
                    sample["evidence"].append("Navigazione incompleta: "+type(exc).__name__)
                finally:
                    await page.close()
                result["samples"].append(sample)
                await asyncio.sleep(0.25)
            await context.close()
        finally:
            await browser.close()
    result["status"]="samples_observed"
    result["evidence"].append("Nessun prezzo entra nel confronto senza conferma completa di soggiorno, tipologia e totale.")
    return result
