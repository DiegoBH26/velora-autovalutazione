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

def _date_renderings(iso):
    """Formati espliciti ammessi per verificare giorno, mese e anno, mai date dedotte."""
    value=date.fromisoformat(iso)
    d,m,y=value.day,value.month,value.year
    months_it=("gennaio","febbraio","marzo","aprile","maggio","giugno",
               "luglio","agosto","settembre","ottobre","novembre","dicembre")
    months_en=("january","february","march","april","may","june",
               "july","august","september","october","november","december")
    return (iso,f"{d:02d}/{m:02d}/{y}",f"{d}/{m}/{y}",
            f"{d:02d}-{m:02d}-{y}",f"{d} {months_it[m-1]} {y}",
            f"{d} {months_en[m-1]} {y}",f"{months_en[m-1]} {d}, {y}")


def _date_is_present(values, iso):
    tokens=[str(v or "").strip().lower() for v in values]
    return any(form.lower() in tokens for form in _date_renderings(iso))


async def _select_explicit_calendar_date(scope, field, iso):
    """Seleziona un giorno con identificatore completo e avanza solo se il controllo
    'mese successivo' è univoco. Non clicca mai un semplice numero di giorno.
    """
    day=date.fromisoformat(iso)
    css=[
        f'[data-date="{iso}"]',f'[data-day="{iso}"]',
        f'[data-value="{iso}"]',f'[datetime="{iso}"]',
        f'[aria-label="{iso}"]',f'[title="{iso}"]',
        f'[aria-label="{day.day:02d}/{day.month:02d}/{day.year}"]',
        f'[aria-label="{day.day}/{day.month}/{day.year}"]',
    ]
    for text in _date_renderings(iso)[4:]:
        css.extend((f'[aria-label="{text}"]',f'[title="{text}"]'))
    try:
        await field.click(timeout=3000)
        await asyncio.sleep(0.2)
        for _ in range(15):
            for selector in css:
                nodes=scope.locator(selector)
                if await nodes.count()==1 and await nodes.first.is_visible():
                    await nodes.first.click(timeout=2800)
                    return True
            # Calendari lunghi (es. agosto 2027): avanti un mese per volta.
            # Mai avanzare se l'interfaccia presenta più frecce non distinguibili.
            next_buttons=scope.get_by_role("button",name=re.compile(
                r"^(?:mese successivo|next month|mese seguente|"
                r"successivo mese|next calendar month)$",re.I))
            if await next_buttons.count()!=1:
                break
            await next_buttons.first.click(timeout=2500)
            await asyncio.sleep(0.12)
    except Exception:
        pass
    return False


async def _apply_dates(scope, stay):
    """Identifica date etichettate anche con aria-label, label o data-testid.
    Funziona sul documento principale e sugli iframe pubblici del booking engine.
    """
    controls=await scope.evaluate("""() => {
      const visible=e=>Boolean(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
      return [...document.querySelectorAll('input')].filter(visible).slice(0,100).map(e=>({
        name:(e.name||'').toLowerCase(),id:(e.id||'').toLowerCase(),
        placeholder:(e.placeholder||'').toLowerCase(),type:(e.type||'').toLowerCase(),
        aria:(e.getAttribute('aria-label')||'').toLowerCase(),
        testid:(e.getAttribute('data-testid')||'').toLowerCase(),
        label:([...e.labels].map(l=>l.innerText||'').join(' ')||
          e.closest('label')?.innerText||'').toLowerCase().slice(0,120),
        value:e.value,readOnly:Boolean(e.readOnly)
      }));
    }""")
    patterns={
        "checkin":r"check[\s_-]?in|arriv|data[\s_-]?(?:dal|inizio|ingresso)|start[\s_-]?date|from[\s_-]?date|entry[\s_-]?date|ingresso",
        "checkout":r"check[\s_-]?out|partenz|data[\s_-]?(?:al|fine|uscita)|end[\s_-]?date|to[\s_-]?date|departure|uscita",
    }
    targets={}
    for name,pattern in patterns.items():
        candidates=[]
        for i,row in enumerate(controls):
            if row["type"] not in ("date","text","search","tel"):continue
            label=" ".join(str(row.get(k) or "") for k in ("name","id","placeholder","aria","testid","label"))
            if re.search(pattern,label):
                candidates.append((i,row))
        if len(candidates)!=1:
            return {"applied":False,"reason":(
                f"Campo {name} non identificabile con certezza "
                f"({len(candidates)} candidati): verificare il calendario del booking engine")}
        targets[name]=candidates[0]
    inputs=scope.locator("input:visible")
    methods=[]
    for name in ("checkin","checkout"):
        index,row=targets[name]
        field=inputs.nth(index)
        value=stay[name]
        try:
            if row["readOnly"]:
                if not await _select_explicit_calendar_date(scope,field,value):
                    return {"applied":False,"reason":(
                        f"Calendario {name}: giorno {value} non selezionabile "
                        "da attributi di data espliciti")}
                methods.append("calendar")
            else:
                if row["type"]!="date":
                    y,m,d=value.split("-")
                    value=f"{d}/{m}/{y}"
                await field.fill(value,timeout=4500)
                await field.press("Tab",timeout=2500)
                methods.append(row["type"])
        except Exception as exc:
            return {"applied":False,"reason":f"Campo {name} non compilato: {type(exc).__name__}"}
    await asyncio.sleep(0.2)
    current=await scope.evaluate("""() => [...document.querySelectorAll('input')]
      .filter(e=>e.offsetWidth||e.offsetHeight||e.getClientRects().length)
      .map(e=>e.value)""")
    valid=all(_date_is_present(current,stay[name]) for name in ("checkin","checkout"))
    return {"applied":valid,
            "method":"/".join(methods),
            "reason":("Date richieste inserite e lette nuovamente nei campi"
                      if valid else
                      "Il booking engine non conferma le date nei propri campi")}


async def _submit_availability_search(scope):
    """Nel caso di due CTA identiche preferisce il pulsante del form (non il menu).
    Interrompe il flusso se non riesce a distinguere il comando di ricerca.
    """
    controls=scope.locator(
        "button:visible,input[type=submit]:visible,[role=button]:visible,a[href]:visible")
    pattern=re.compile(
        r"^(?:cerca(?: (?:la )?disponibilit[aà]| camere| alloggi| prezzi| ora)?|"
        r"search(?: availability| rooms| rates)?|"
        r"verifica(?: (?:la )?disponibilit[aà]| prezzi| tariffe)?|"
        r"controlla disponibilit[aà]|vedi disponibilit[aà]|"
        r"check availability|show availability|"
        r"mostra (?:disponibilit[aà]|risultati|prezzi|camere|tariffe)|"
        r"visualizza (?:camere|prezzi|disponibilit[aà])|"
        r"show (?:results|rooms|prices|rates)|find (?:rooms|rates))"
        r"(?:\s*[›»→])?$",re.I)
    matched=[]
    for i in range(min(await controls.count(),120)):
        el=controls.nth(i)
        try:
            label=await el.evaluate("""e=>(e.innerText||
              e.getAttribute('aria-label')||e.value||e.title||'')
              .replace(/\s+/g,' ').trim()""")
            if not pattern.fullmatch(label) or not await el.is_enabled():continue
            hints=await el.evaluate("""e=>{
              const rect=e.getBoundingClientRect();
              const container=e.closest('form,[class*=booking],[class*=search],[class*=availability]');
              const txt=(container?.innerText||'').slice(0,2000);
              return {y:Math.round(rect.y),tag:e.tagName.toLowerCase(),
                form:!!e.closest('form'),
                inputs:container?.querySelectorAll('input,select')?.length||0,
                occupancy:/adulti|adults|ospiti|guests|camera 1/i.test(txt),
                dates:/check.?in|check.?out|arrivo|partenza/i.test(txt),
                header:!!e.closest('header,nav,[role=navigation]')};
            }""")
            score=(6 if hints.get("form") else 0)+(4 if hints.get("inputs",0)>=2 else 0)
            score+=(3 if hints.get("occupancy") else 0)+(3 if hints.get("dates") else 0)
            score+=(1 if hints.get("tag") in ("button","input") else 0)
            score-=10 if hints.get("header") else 0
            matched.append((el,label,score,hints.get("y",0)))
        except Exception:
            continue
    if len(matched)!=1:
        if not matched:
            return {"submitted":False,"reason":"Pulsante 'Verifica disponibilità' non trovato."}
        # Due voci con lo stesso nome (menu in alto + pulsante del modulo):
        # il pulsante con più indizi di form prevale; a parità non si clicca.
        ranked=sorted(matched,key=lambda x:(x[2],x[3]),reverse=True)
        if len(ranked)>1 and ranked[0][2]==ranked[1][2] and ranked[0][3]==ranked[1][3]:
            return {"submitted":False,"reason":"Più pulsanti di ricerca indistinguibili."}
        button,label=ranked[0][:2]
    else:
        button,label=matched[0][:2]
    try:
        await button.click(timeout=6500)
        return {"submitted":True,"action":label,"reason":"Clic sul pulsante di ricerca disponibilità"}
    except Exception as exc:
        return {"submitted":False,"reason":f"Ricerca non inviata: {type(exc).__name__}"}


async def _apply_guests(scope, adults):
    """Imposta adulti (e legge il valore di controllo) nel form pubblico.
    Non confonde il selettore bambini con quello adulti.
    """
    try:
        controls=scope.locator("input:visible,select:visible")
        count=min(await controls.count(),100)
        candidates=[]
        for i in range(count):
            el=controls.nth(i)
            info=await el.evaluate("""e=>{
              const own=[e.name,e.id,e.getAttribute('aria-label'),
                e.placeholder,e.closest('label')?.innerText,
                e.parentElement?.previousElementSibling?.innerText].filter(Boolean).join(' ');
              const nearby=(e.parentElement?.innerText||'').slice(0,90);
              return {own:own.toLowerCase(),nearby:nearby.toLowerCase(),
                tag:e.tagName.toLowerCase(),type:(e.type||'').toLowerCase()};
            }""")
            own=info["own"]
            nearby=info["nearby"]
            if re.search(r"bambin|child|infant|coupon",own):continue
            exact=bool(re.search(r"adult|adulti|ospiti|guests",own))
            fallback=bool(re.search(r"adulti|adults",nearby)) and not re.search(
                r"bambin|children",nearby)
            if exact or fallback:
                candidates.append((el,info,2 if exact else 1))
        if not candidates:
            return {"confirmed":False,"evidence":"Campo Adulti non identificato nel form."}
        candidates.sort(key=lambda t:t[2],reverse=True)
        if len(candidates)>1 and candidates[0][2]==candidates[1][2]:
            return {"confirmed":False,"evidence":"Più campi adulti indistinguibili."}
        el,info,_=candidates[0]
        if info["tag"]=="select":
            try:await el.select_option(str(adults),timeout=3000)
            except Exception:
                try:await el.select_option(label=str(adults),timeout=3000)
                except Exception:return {"confirmed":False,"evidence":"Selettore adulti non impostabile."}
        elif info["type"] in ("number","text","tel"):
            await el.fill(str(adults),timeout=3000)
            await el.press("Tab",timeout=2000)
        else:
            return {"confirmed":False,"evidence":"Controllo adulti non modificabile."}
        current=await el.input_value()
        return {"confirmed":current==str(adults),
                "evidence":("Adulti="+current+" confermati dal form" if current==str(adults)
                            else "Il booking engine ha modificato il numero di adulti")}
    except Exception as exc:
        return {"confirmed":False,"evidence":"Occupazione non confermata: "+type(exc).__name__}


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
    """Ricerca realmente date, occupazione e offerte nel booking engine pubblico.

    Un sito/engine trovato NON equivale a una ricerca completata. Il risultato
    distingue ricerca effettuata, prezzi osservati e preventivi verificati.
    """
    from playwright.async_api import async_playwright
    from site_audit_builder import public_url, robots_allowed
    stays=eligible_stays(rows,limit=limit)
    result={"status":"not_checked","samples":[],"verifiedQuotes":[],"evidence":[],
            "searchedTotal":0,"plannedTotal":len(stays)}
    if not stays:
        result["status"]="missing_direct_dates"
        result["evidence"].append("Nessuna data futura/occupazione valida selezionata per il sito diretto.")
        return result
    try:
        url=public_url(url)
    except ValueError:
        result["status"]="missing_engine_url"
        result["evidence"].append("URL del booking engine non valido.")
        return result
    if robots_allowed(url,{}) is not True:
        result["status"]="robots_unverified"
        result["evidence"].append(
            "Booking engine non analizzabile: accesso robots.txt negato o non verificabile.")
        return result
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel="chrome",headless=bool(ghost))
        try:
            context=await browser.new_context(
                locale="it-IT",timezone_id="Europe/Rome",accept_downloads=False)
            for stay in stays:
                sample={**stay,"status":"not_verified","sourceUrl":url,"quotes":[],
                        "availability":"not_verified","searchSubmitted":False,
                        "evidence":[]}
                page=await context.new_page()
                try:
                    response=await page.goto(url,wait_until="domcontentloaded",timeout=22000)
                    if not response or response.status>=400:
                        sample["status"]="navigation_error"
                        sample["evidence"].append("Booking engine non raggiungibile.")
                    else:
                        await page.wait_for_timeout(1200)
                        # I booking engine sono spesso in iframe cross-origin:
                        # Playwright vi accede con gli stessi controlli dell'utente.
                        scopes=[page.main_frame]+[frame for frame in page.frames
                            if frame!=page.main_frame and frame.url.startswith(("https://","http://"))]
                        attempts=[]
                        active=None
                        for scope in scopes:
                            try:
                                applied=await _apply_dates(scope,stay)
                                attempts.append({"frameUrl":scope.url.split("?")[0][:220],
                                                 "dates":applied})
                                if applied.get("applied"):
                                    active=scope
                                    sample["controls"]=applied
                                    break
                            except Exception as exc:
                                attempts.append({"frameUrl":scope.url.split("?")[0][:220],
                                                 "error":type(exc).__name__})
                        sample["dateAttempts"]=attempts[:12]
                        if active is None:
                            sample["status"]="dates_not_selectable"
                            sample["formDiagnostic"]=await _form_diagnostic(page.main_frame)
                            sample["evidence"].append(
                                "Le date non sono state selezionate. "
                                "Possibile calendario personalizzato, iframe non accessibile "
                                "o campi non identificati in modo univoco.")
                        else:
                            sample["formDiagnostic"]=await _form_diagnostic(active)
                            occupancy=await _apply_guests(active,stay["guests"])
                            sample["occupancyControl"]=occupancy
                            sample["searchSubmitted"]=False
                            submitted=await _submit_availability_search(active)
                            sample["searchAction"]=submitted
                            if submitted["submitted"]:
                                sample["searchSubmitted"]=True
                                result["searchedTotal"]+=1
                                await page.wait_for_timeout(1600)
                            else:
                                sample["evidence"].append(submitted["reason"])
                            # Leggere *dopo* l'invio: niente prezzi di un periodo precedente.
                            current=await active.evaluate("""() => ({
                              fields:[...document.querySelectorAll('input')]
                                .filter(e=>e.offsetWidth||e.offsetHeight||e.getClientRects().length)
                                .map(x=>x.value).slice(0,100),
                              url:location.href,
                              text:(document.body?.innerText||'').slice(0,22000)
                            })""")
                            page_text=current["text"]
                            current_values=current["fields"]
                            displayed=" ".join((page_text,current["url"]))
                            date_confirmed=all(
                                _date_is_present(current_values,stay[key]) or
                                any(token.lower() in displayed.lower()
                                    for token in _date_renderings(stay[key])[:4])
                                for key in ("checkin","checkout"))
                            sample["datesConfirmedAfterSearch"]=bool(date_confirmed)
                            # Mai usare query string e frammenti con possibili token sensibili.
                            sample["sourceUrl"]=active.url.split("?")[0].split("#")[0]
                            prices=[{"amount":_money(m.group(0)),"text":m.group(0)}
                                for m in list(_PRICE_PATTERN.finditer(page_text))[:25]]
                            sample["visiblePrices"]=[p for p in prices
                                if p["amount"] is not None][:14]
                            sample["quotes"]=await _visible_offer_candidates(active)
                            sample["status"]=(
                                "search_submitted_dates_confirmed"
                                if date_confirmed and sample["searchSubmitted"] else
                                "search_submitted_dates_unconfirmed"
                                if sample["searchSubmitted"] else
                                "date_inputs_observed_no_search")
                            if date_confirmed and occupancy.get("confirmed") and sample["searchSubmitted"]:
                                if not sample["quotes"] and re.search(
                                    r"nessuna disponibilit[aà]|non ci sono camere disponibili|"
                                    r"no availability|no rooms available",page_text,re.I):
                                    sample["availability"]="unavailable_reported"
                                    sample["evidence"].append(
                                        "Il booking engine segnala indisponibilità per date e occupazione confermate.")
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
                                        "evidence":"Ricerca confermata: date, occupazione, camera, totale e condizioni.",
                                    })
                                if any(q.get("verified") for q in sample["quotes"]):
                                    sample["availability"]="price_and_booking_action_observed"
                            sample["evidence"].append(
                                f"Ricerca inviata={sample['searchSubmitted']}; "
                                f"date presenti dopo ricerca={date_confirmed}; "
                                f"occupazione confermata={occupancy.get('confirmed')}; "
                                f"prezzi visibili={len(sample['visiblePrices'])}; "
                                f"offerte-candidato={len(sample['quotes'])}.")
                            if sample["quotes"] and not any(q.get("verified") for q in sample["quotes"]):
                                sample["evidence"].append(
                                    "Prezzi osservati ma non ancora confrontabili: "
                                    "verificare totale soggiorno e condizioni mancanti.")
                except Exception as exc:
                    sample["status"]="navigation_error"
                    sample["evidence"].append("Ricerca non completata: "+type(exc).__name__)
                finally:
                    await page.close()
                result["samples"].append(sample)
                await asyncio.sleep(0.25)
            await context.close()
        finally:
            await browser.close()
    if result["verifiedQuotes"]:
        result["status"]="verified_rates"
    elif result["searchedTotal"]==0:
        result["status"]="search_not_executed"
    elif any(s["status"]=="search_submitted_dates_confirmed"
             for s in result["samples"]):
        result["status"]="search_executed_rates_unverified"
    else:
        result["status"]="search_executed_dates_unconfirmed"
    result["evidence"].append(
        f"Ricerche disponibilità realmente inviate: {result['searchedTotal']}/{len(stays)}. "
        f"Preventivi completi verificati: {len(result['verifiedQuotes'])}. "
        "Le tariffe senza date, occupazione e condizioni confermate non entrano nel confronto OTA.")
    return result
