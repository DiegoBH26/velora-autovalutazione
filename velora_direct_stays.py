"""Campioni commerciali diretti in sola lettura.

Solo finestre identiche a Booking, nessuna invenzione di prezzi. I campioni
non verificati restano osservazioni e non entrano in delta o disponibilità.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date
from urllib.parse import urlparse

_DATE_PATTERN=re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PRICE_PATTERN=re.compile(r"(?:€\s*([0-9][0-9.,]*)|([0-9][0-9.,]*)\s*€)")

def eligible_stays(rows, *, limit=4):
    """Accetta soltanto date richieste sul diretto o effettivamente confermate da Booking."""
    selected=[]
    for item in rows or []:
        if not isinstance(item,dict): continue
        arrival=str(item.get("checkin") or "")
        departure=str(item.get("checkout") or "")
        if not (_DATE_PATTERN.fullmatch(arrival) and _DATE_PATTERN.fullmatch(departure)):
            continue
        # Booking e' la fonte delle date di ricerca per TUTTI i canali.
        # Le date inizialmente richieste possono essere state sostituite da
        # Booking con un'altra finestra realmente confermata. In tal caso
        # manteniamo la finestra confermata, senza ripristinare la richiesta.
        status=str(item.get("status") or "")
        if status not in {"initial_dates_available","shifted_to_available_booking_dates",
                          "reused_minerva_lock","direct_master_requested"}:
            continue
        try:
            nights=(date.fromisoformat(departure)-date.fromisoformat(arrival)).days
        except ValueError: continue
        if item.get("adults") is None:
            continue
        try: adults=int(item.get("adults"))
        except (ValueError,TypeError): continue
        if not (1<=nights<=60 and 1<=adults<=12 and date.fromisoformat(arrival)>=date.today()):
            continue
        key=(arrival,departure,adults)
        if any((x["checkin"],x["checkout"],x["guests"])==key for x in selected): continue
        selected.append({"checkin":arrival,"checkout":departure,"guests":adults,"nights":nights,
                         "bookingConfirmation":status,
                         "requestedCheckin":str(item.get("requestedCheckin") or ""),
                         "requestedCheckout":str(item.get("requestedCheckout") or "")})
        if len(selected)>=limit:break
    return selected

def planned_direct_stays(plan, *, limit=4):
    """Crea il campione iniziale del sito diretto SENZA dati Booking inventati.

    Booking eseguirà poi il controllo delle medesime richieste e potrà
    confermare o spostare la finestra. Le differenze restano esplicite.
    """
    if not isinstance(plan,list):
        return []
    rows=[]
    for stay in plan[:max(limit*3,12)]:
        if not isinstance(stay,dict):
            continue
        rows.append({
            "checkin":str(stay.get("checkin") or ""),
            "checkout":str(stay.get("checkout") or ""),
            "requestedCheckin":str(stay.get("checkin") or ""),
            "requestedCheckout":str(stay.get("checkout") or ""),
            "adults":stay.get("adults"),
            "status":"direct_master_requested",
            "source":"direct_initial_plan"
        })
    return rows[:limit]

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

async def _form_diagnostic(page):
    """Visibile nell'audit: diagnostica del modulo SENZA credenziali o valori."""
    try:
        return await page.evaluate("""() => {
          const visible=e=>Boolean(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
          const fields=[...document.querySelectorAll('input,select')].filter(visible).slice(0,35)
            .map(e=>({type:(e.type||'').slice(0,24),
              label:((e.getAttribute('aria-label')||'')+' '+(e.placeholder||'')+' '+(e.name||''))
                .trim().slice(0,100),readOnly:Boolean(e.readOnly)}));
          const actions=[...document.querySelectorAll('button,[role=button]')].filter(visible).slice(0,40)
            .map(e=>(e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,90))
            .filter(Boolean);
          return {fieldSamples:fields,searchActions:actions,
                  dateWidgets:document.querySelectorAll('[role=grid],[role=datepicker],[data-date]').length};
        }""")
    except Exception:
        return {"fieldSamples":[],"searchActions":[],"dateWidgets":0}

async def _select_explicit_calendar_date(page, field, iso):
    """Solo giorno con attributo ISO esplicito; mai click su date presunte."""
    y,m,d=iso.split("-")
    candidates=[
        f'[data-date="{iso}"]',f'[data-day="{iso}"]',
        f'[data-value="{iso}"]',f'[datetime="{iso}"]',
        f'[aria-label="{iso}"]',f'[title="{iso}"]',
        f'[aria-label="{d}/{m}/{y}"]',
    ]
    try:
        await field.click(timeout=1800)
        await page.wait_for_timeout(200)
        for selector in candidates:
            nodes=page.locator(selector)
            if await nodes.count()==1 and await nodes.first.is_visible():
                await nodes.first.click(timeout=2200)
                return True
    except Exception:
        pass
    return False

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
    # Testo data esplicitamente etichettato, se il booking engine non usa input date.
    modes={"checkin":"date","checkout":"date"}
    if len(targets)!=2:
        targets={}
        for i,row in enumerate(controls):
            label=" ".join([row["name"],row["id"],row["placeholder"]])
            if row["type"] not in ("text","search","tel"):continue
            if re.search(r"check.?in|arriv|data di ingresso|start.date",label):
                targets["checkin"]=i;modes["checkin"]="text"
            elif re.search(r"check.?out|partenz|data di uscita|end.date",label):
                targets["checkout"]=i;modes["checkout"]="text"
    if len(targets)!=2:return {"applied":False,"reason":"Selettore date personalizzato o campi non riconosciuti"}
    inputs=page.locator("input:visible")
    # Only explicitly identified date controls: never submit checkout/payment.
    for name,index in targets.items():
        value=stay[name]
        if modes[name]=="text":
            year,month,day=value.split("-")
            value=f"{day}/{month}/{year}"
        field=inputs.nth(index)
        if await field.get_attribute("readonly") is not None:
            selected=await _select_explicit_calendar_date(page,field,stay[name])
            if not selected:
                return {"applied":False,"reason":"Calendario personalizzato: giorno richiesto non identificabile con certezza"}
        else:
            await field.fill(value,timeout=4500)
            await field.press("Tab",timeout=2500)
    await page.wait_for_timeout(250)
    actual=await page.evaluate("""() => [...document.querySelectorAll('input')].filter(e=>e.offsetWidth||e.offsetHeight||e.getClientRects().length).map(e=>e.value)""")
    def has_date(key):
        y,m,d=stay[key].split("-")
        return any(v in actual for v in (stay[key],f"{d}/{m}/{y}"))
    valid=has_date("checkin") and has_date("checkout")
    return {"applied":valid,"reason":"Date inserite e confermate" if valid else "Le date sono state modificate o rifiutate dal booking engine"}

async def _apply_guests(page, adults):
    """Prova soltanto controlli nativi esplicitamente etichettati adulti/ospiti."""
    try:
        inputs=page.locator("input:visible,select:visible")
        count=min(await inputs.count(),100)
        for i in range(count):
            el=inputs.nth(i)
            label=await el.evaluate("""e=>[
                e.name||'',e.id||'',e.getAttribute('aria-label')||'',
                e.placeholder||'',e.closest('label')?.innerText||''
            ].join(' ').toLowerCase()""")
            if not re.search(r"adulti|adults|ospiti|guests",label):
                continue
            tag=await el.evaluate("e=>e.tagName.toLowerCase()")
            if tag=="select":
                try:await el.select_option(str(adults),timeout=2500)
                except Exception:continue
            elif await el.get_attribute("type") in ("number","text","tel"):
                try:await el.fill(str(adults),timeout=2500)
                except Exception:continue
            else:
                continue
            value=await el.input_value()
            if value==str(adults):
                return {"confirmed":True,"evidence":"Occupazione impostata nel campo pubblico"}
    except Exception:
        pass
    return {"confirmed":False,"evidence":"Occupazione non confermata nel motore di prenotazione"}

def _explicit_conditions(text):
    low=str(text or "").lower()
    board=("Colazione inclusa" if re.search(r"colazione inclusa|breakfast included",low)
           else "Solo pernottamento" if re.search(r"solo pernottamento|room only",low)
           else "")
    refund=("Non rimborsabile" if re.search(r"non rimborsabile|non refundable",low)
            else "Cancellazione gratuita" if re.search(r"cancellazione gratuita|free cancellation",low)
            else "")
    taxes=("Incluse" if re.search(r"tasse incluse|imposte incluse|taxes included",low)
           else "Escluse" if re.search(r"tasse escluse|imposte escluse|taxes excluded",low)
           else "")
    return {"board":board,"refund":refund,"taxes":taxes}

async def _visible_offer_candidates(page):
    """Raccoglie prezzi e nomi camera nello stesso contenitore visibile;
    non presume che l'importo sia il totale confrontabile."""
    try:
        cards=await page.evaluate("""() => {
          const visible=e=>Boolean(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
          const nodes=[...document.querySelectorAll(
            'article,[data-testid*=room],[data-testid*=rate],[class*=room-card],[class*=roomCard],[class*=rate-card],[class*=room-type],[class*=roomType]')];
          return nodes.filter(visible).slice(0,80).map(el=>{
            const text=(el.innerText||'').replace(/\\s+/g,' ').trim().slice(0,1400);
            const head=el.querySelector('h2,h3,h4,[class*=room-name],[class*=roomName]')?.textContent||'';
            return {roomType:String(head).replace(/\\s+/g,' ').trim().slice(0,140),
                    text,hasBookingAction:/\\b(prenota|book now|seleziona|select room)\\b/i.test(text)};
          }).filter(x=>x.roomType&&x.text&&/[€]/.test(x.text)).slice(0,30);
        }""")
    except Exception:
        return []
    offers=[]
    seen=set()
    for card in cards:
        text=card.get("text") or ""
        matches=list(_PRICE_PATTERN.finditer(text))[:6]
        for match in matches:
            amount=_money(match.group(0))
            if amount is None:continue
            near=text[max(0,match.start()-75):min(len(text),match.end()+75)]
            basis="stay_total_claimed" if re.search(
                r"totale|prezzo complessivo|total price|total for stay|intero soggiorno",near,re.I) else "unknown"
            room=str(card.get("roomType") or "")[:140]
            key=(room.lower(),amount,basis)
            if key in seen:continue
            seen.add(key)
            terms=_explicit_conditions(text)
            offers.append({
                "roomType":room,"displayedAmount":amount,"currency":"EUR",
                "displayedBasis":basis,"bookingActionVisible":bool(card.get("hasBookingAction")),
                "conditions":text[-220:],"board":terms["board"],
                "refund":terms["refund"],"taxes":terms["taxes"],
                "verified":False,
                "evidence":"Importo e intestazione camera nella stessa scheda: "
                    +"totale soggiorno indicato" if basis=="stay_total_claimed"
                    else "Importo osservato, natura del prezzo non confermata",
            })
            if len(offers)>=20:return offers
    return offers

async def probe_direct_stays(url, rows, *, limit=4, ghost=False):
    # Keep date validation unit-testable without launching or importing a browser.
    from playwright.async_api import async_playwright
    from site_audit_builder import public_url, robots_allowed
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
        # Modalità normale: browser Chrome visibile, come per la ricerca OTA.
        # Ghost mantiene l'esecuzione senza finestra; nessun bypass di blocchi.
        browser=await pw.chromium.launch(channel="chrome",headless=bool(ghost))
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
                        await page.wait_for_timeout(1100)
                        sample["formDiagnostic"]=await _form_diagnostic(page)
                        applied=await _apply_dates(page,stay)
                        sample["controls"]=applied
                        if not applied["applied"]:
                            sample["status"]="dates_not_selectable"
                            sample["evidence"].append(applied["reason"])
                        else:
                            occupancy=await _apply_guests(page,stay["guests"])
                            sample["occupancyControl"]=occupancy
                            # Avoid submitting forms with unknown side effects.
                            # Search CTA is allowed only when explicitly a search, never checkout.
                            buttons=page.get_by_role("button",name=re.compile(r"^(?:cerca(?: disponibilit[aà])?|search(?: availability)?|verifica disponibilit[aà]|check availability|mostra disponibilit[aà]|verifica prezzi|trova camere|cerca camere)$",re.I))
                            if await buttons.count()==1:
                                await buttons.first.click(timeout=4500)
                                await page.wait_for_timeout(1300)
                            current=await page.evaluate("""() => ({
                              fields:[...document.querySelectorAll('input')].filter(e=>e.offsetWidth||e.offsetHeight||e.getClientRects().length).map(x=>x.value).slice(0,100),
                              url:location.href,
                              text:(document.body?.innerText||'').slice(0,22000)
                            })""")
                            page_text=current["text"]
                            actual_dates=set(current["fields"])
                            def contains_date(key):
                                year,month,day=stay[key].split("-")
                                return stay[key] in actual_dates or f"{day}/{month}/{year}" in actual_dates
                            date_confirmed=contains_date("checkin") and contains_date("checkout")
                            sample["status"]="date_context_observed" if date_confirmed else "dates_unconfirmed"
                            sample["sourceUrl"]=page.url.split("?")[0].split("#")[0]
                            prices=[{"amount":_money(m.group(0)),"text":m.group(0)}
                                    for m in list(_PRICE_PATTERN.finditer(page_text))[:20]]
                            sample["visiblePrices"]=[p for p in prices if p["amount"] is not None][:12]
                            sample["quotes"]=await _visible_offer_candidates(page)
                            # Conferma soltanto prezzi con camera, totale soggiorno,
                            # date/ospiti, disponibilita' e condizioni esplicite.
                            if date_confirmed and occupancy.get("confirmed"):
                                if not sample["quotes"] and re.search(
                                    r"nessuna disponibilit[aà]|non ci sono camere disponibili|no availability|no rooms available",
                                    page_text,re.I):
                                    sample["availability"]="unavailable_reported"
                                    sample["evidence"].append(
                                        "Il booking engine dichiara indisponibilità per le date/ospiti confermati.")
                                for offer in sample["quotes"]:
                                    complete=(offer.get("displayedBasis")=="stay_total_claimed"
                                        and offer.get("bookingActionVisible")
                                        and all(offer.get(k) for k in ("board","refund","taxes"))
                                        and offer.get("roomType"))
                                    if not complete:continue
                                    offer["verified"]=True
                                    result["verifiedQuotes"].append({
                                        **stay,"roomType":offer["roomType"],
                                        "total":offer["displayedAmount"],
                                        "board":offer["board"],"refund":offer["refund"],
                                        "taxes":offer["taxes"],"audience":"public",
                                        "sourceUrl":sample["sourceUrl"],
                                        "verified":True,
                                        "evidence":"Stesse date/ospiti, camera, prezzo totale e condizioni esplicite",
                                    })
                                if any(q.get("verified") for q in sample["quotes"]):
                                    sample["availability"]="price_and_booking_action_observed"
                            sample["evidence"].append(
                                f"{len(sample['quotes'])} prezzi-candidati associati a intestazioni camera; "
                                "nessuna parità tariffaria senza conferma completa di soggiorno e condizioni.")
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
    result["status"]="verified_rates" if result["verifiedQuotes"] else "samples_observed"
    result["evidence"].append("Solo le quotazioni che riportano tutte le condizioni richieste sono candidate al confronto con la medesima tipologia OTA.")
    return result
