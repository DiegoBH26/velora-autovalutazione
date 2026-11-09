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
_PRICE_PATTERN=re.compile(r"(?:(?:€|EUR)\s*([0-9][0-9.,]*)|([0-9][0-9.,]*)\s*(?:€|EUR))",re.I)

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


async def _select_visual_calendar_date(scope, iso):
    """Fallback per calendari visuali (anche Bedzzle): mese/anno visibili,
    giorno selezionato SOLO nel mese corretto. Nessun giorno presunto.
    """
    month_names=("gennaio","febbraio","marzo","aprile","maggio","giugno",
                 "luglio","agosto","settembre","ottobre","novembre","dicembre")
    wanted=date.fromisoformat(iso)
    for _ in range(17):
        status=await scope.evaluate("""(target) => {
          const MONTHS=[
            ['gen','january','jan'],['feb','february'],['mar','march'],
            ['apr','april'],['mag','maggio','may'],['giu','giugno','jun','june'],
            ['lug','luglio','jul','july'],['ago','agosto','aug','august'],
            ['set','sett','settembre','sep','september'],['ott','ottobre','oct','october'],
            ['nov','november'],['dic','dicembre','dec','december']
          ];
          const visible=e=>{
            if (!e || !(e.offsetWidth||e.offsetHeight||e.getClientRects().length)) return false;
            const r=e.getBoundingClientRect();
            return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight;
          };
          const txt=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();
          const leafs=root=>[...root.querySelectorAll('span,a,button,td,div,[role=gridcell]')]
             .filter(e=>visible(e) && txt(e).length<35 && e.children.length<4);
          const guessMonth=s=>{
            s=(s||'').toLowerCase().trim();
            for(let i=0;i<12;i++) if(MONTHS[i].some(m=>s===m)) return i+1;
            return 0;
          };
          // Il mese e l'anno possono stare sopra la tabella del calendario:
          // considera anche il contenitore padre del widget, non solo il TABLE.
          const roots=[...document.querySelectorAll(
            '[class*="calendar"],[class*="datepicker"],[role=grid],table,[class*="month-view"]')]
             .filter(visible).slice(0,180);
          roots.push(...[...document.querySelectorAll('aside,section,div')]
             .filter(visible).slice(0,650));
          const options=[];
          for(const root of roots){
            const leaves=leafs(root);
            const days=leaves.filter(e=>/^\d{1,2}$/.test(txt(e)) &&
              Number(txt(e))>=1 && Number(txt(e))<=31);
            if(days.length<20) continue;
            const months=leaves.filter(e=>guessMonth(txt(e)));
            const years=leaves.filter(e=>/^20\d{2}$/.test(txt(e)));
            if (!months.length||!years.length) continue;
            const m=months[0], y=years[0];
            const month=guessMonth(txt(m)), year=Number(txt(y));
            options.push({root,leaves,days,m,y,month,year,area:root.getBoundingClientRect().width*
              root.getBoundingClientRect().height});
          }
          options.sort((a,b)=>a.area-b.area);
          const cal=options[0];
          if(!cal) return {action:'missing',reason:'Calendario mensile non riconosciuto'};
          const current=cal.year*12+cal.month;
          const wanted=target.year*12+target.month;
          const marker='data-velora-calendar-target';
          document.querySelectorAll('['+marker+']').forEach(e=>e.removeAttribute(marker));
          if(current===wanted){
            const disabled=e=>!!(e.closest('[disabled],[aria-disabled=true],.disabled,.off,.old,.new,.outside,.not-current-month'));
            const cells=cal.days.filter(e=>Number(txt(e))===target.day && !disabled(e));
            const tags=cells.filter(e=>['TD','BUTTON','A'].includes(e.tagName)||e.getAttribute('role')==='gridcell');
            const usable=tags.length?tags:cells.filter(e=>e.children.length===0);
            if(usable.length!==1) return {action:'missing',reason:'Giorno '+target.day+
              ' non univoco nel calendario '+cal.month+'/'+cal.year};
            usable[0].setAttribute(marker,'day');
            return {action:'day',month:cal.month,year:cal.year};
          }
          const isYear=cal.year!==target.year;
          const anchor=isYear?cal.y:cal.m;
          const right=wanted>current;
          const rect=anchor.getBoundingClientRect();
          const midX=(rect.left+rect.right)/2, midY=(rect.top+rect.bottom)/2;
          const nav=[...cal.root.querySelectorAll('button,a,[role=button],[class*=arrow],[class*=chevron],[class*=next],[class*=prev]')]
            .filter(e=>visible(e)&&!e.closest('[disabled],[aria-disabled=true],.disabled'))
            .map(e=>{
              const r=e.getBoundingClientRect();
              const x=(r.left+r.right)/2,y=(r.top+r.bottom)/2;
              const dx=x-midX;
              const distance=Math.abs(dx)+Math.abs(y-midY)*2;
              return {e,dx,distance,y};
            })
            .filter(v=>(right?v.dx>6:v.dx< -6) &&
              Math.abs(v.y-midY)<26 && Math.abs(v.dx)<110)
            .sort((a,b)=>a.distance-b.distance);
          if(!nav.length) return {action:'missing',reason:'Freccia calendario '+(isYear?'anno':'mese')+' assente'};
          nav[0].e.setAttribute(marker,'nav');
          return {action:'nav',month:cal.month,year:cal.year};
        }""",{"year":wanted.year,"month":wanted.month,"day":wanted.day})
        action=status.get("action")
        if action not in ("nav","day"):
            return False
        el=scope.locator('[data-velora-calendar-target="'+action+'"]')
        if await el.count()!=1:
            return False
        await el.first.click(timeout=3000)
        if action=="day":
            return True
        await asyncio.sleep(0.17)
    return False


async def _choose_visual_date_field(scope, name):
    """Se il booking engine usa DIV al posto di input, usa la voce visiva
    Check in/Check out. Non inventa le date con click generici.
    """
    pattern=(r"^\s*check[\s-]?in\s*$|^\s*arrivo\s*$|^\s*data d.arrivo\s*$"
             if name=="checkin" else
             r"^\s*check[\s-]?out\s*$|^\s*partenza\s*$|^\s*data di partenza\s*$")
    labels=scope.get_by_text(re.compile(pattern,re.I))
    if await labels.count()==1 and await labels.first.is_visible():
        await labels.first.click(timeout=2500)
        return True
    # È ammessa anche una etichetta che contenga la data già selezionata:
    # l'intero box è cliccabile e aggiorna il calendario a lato.
    broad=scope.get_by_text(re.compile(
        r"check[\s-]?in" if name=="checkin" else r"check[\s-]?out",re.I))
    if await broad.count()==1 and await broad.first.is_visible():
        await broad.first.click(timeout=2500)
        return True
    return False


async def _apply_dates(scope, stay):
    """Compila check-in/out per date native e calendar widget. Nell'engine
    visuale seleziona soltanto un giorno del mese/anno esatti.
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
        # In Bedzzle e simili i campi date sono box cliccabili, non input.
        # Non scegliere un input a caso: il fallback usa il calendario visivo.
        targets[name]=candidates[0] if len(candidates)==1 else (None,None)
    inputs=scope.locator("input:visible")
    methods=[]
    chosen_visual=set()
    for name in ("checkin","checkout"):
        index,row=targets[name]
        value=stay[name]
        try:
            if index is None:
                focused=await _choose_visual_date_field(scope,name)
                if not focused and name=="checkout":
                    return {"applied":False,"reason":"Box Check out non identificato: calendario non selezionato"}
                if not await _select_visual_calendar_date(scope,value):
                    return {"applied":False,"reason":f"Calendario visuale: {name} {value} non selezionato"}
                chosen_visual.add(name)
                methods.append("visual-calendar")
                continue
            field=inputs.nth(index)
            if row["readOnly"]:
                selected=await _select_explicit_calendar_date(scope,field,value)
                if not selected:
                    selected=await _select_visual_calendar_date(scope,value)
                if not selected:
                    return {"applied":False,"reason":(
                        f"Calendario {name}: giorno {value} non selezionabile in modo univoco")}
                chosen_visual.add(name)
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
    valid=all(name in chosen_visual or _date_is_present(current,stay[name])
              for name in ("checkin","checkout"))
    return {"applied":valid,"method":"/".join(methods),
            "reason":("Check-in/out selezionati e confermati dai controlli del booking engine"
                      if valid else "Il booking engine non conferma check-in/out")}


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
    """Legge la griglia delle camere visibili nella pagina risultati.
    Il prezzo esposto viene registrato anche se il piano o le imposte non
    sono indicati: solo la parità OTA necessita condizioni identiche.
    """
    try:
        cards=await page.evaluate("""() => {
          const visible=e=>Boolean(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
          const selectors=[
            'article','table tbody tr','[data-testid*=room]','[data-testid*=rate]',
            '[class*=room]','[class*=Room]','[class*=rate]','[class*=Rate]',
            '[class*=offer]','[class*=Offer]','[class*=product]','[class*=Product]',
            '[class*=accommodation]','[class*=Accommodation]'
          ].join(',');
          const nodes=[...document.querySelectorAll(selectors)].filter(visible).slice(0,650);
          const result=[];
          const seen=new Set();
          for(const el of nodes){
            const raw=(el.innerText||'').trim();
            if(!raw || raw.length>2500 || !/(€|EUR)\s*\d|\d[\d.,]*\s*(€|EUR)/i.test(raw))continue;
            const lines=raw.split(/\n+/).map(x=>x.replace(/\s+/g,' ').trim()).filter(Boolean);
            const all=lines.join(' ').slice(0,2000);
            const heading=[...el.querySelectorAll(
              'h2,h3,h4,h5,[class*=room-name],[class*=roomName],[class*=room-title],'+
              '[class*=roomTitle],[class*=name],[class*=Name],[class*=title],[class*=Title],strong,b')]
              .map(e=>(e.textContent||'').replace(/\s+/g,' ').trim())
              .find(t=>t.length>2&&t.length<130&&!/(€|EUR)/.test(t))||'';
            const likely=lines.find(t=>t.length>3&&t.length<120&&
              /\b(camera|camere|room|suite|deluxe|classic|superior|family|apartment|appartamento|trullo|pajara|matrimoniale|doppia|standard)\b/i.test(t) &&
              !/(€|EUR)/.test(t))||'';
            const name=heading||likely;
            if(!name)continue;
            const key=name.toLowerCase()+'|'+all.slice(0,180);
            if(seen.has(key))continue;
            seen.add(key);
            result.push({roomType:name.slice(0,140),text:all,
              hasBookingAction:/\b(prenota|book now|seleziona|select room|scegli)\b/i.test(all),
              textLength:all.length});
          }
          // Il contenitore minore evita di attribuire ad una camera i prezzi
          // delle camere vicine annidate nel medesimo elemento.
          return result.sort((a,b)=>a.textLength-b.textLength).slice(0,100);
        }""")
    except Exception:
        return []
    offers=[]
    seen=set()
    for card in cards:
        text=card.get("text") or ""
        room=str(card.get("roomType") or "").strip()[:140]
        if not room:continue
        for match in list(_PRICE_PATTERN.finditer(text))[:8]:
            amount=_money(match.group(0))
            if amount is None:continue
            near=text[max(0,match.start()-85):min(len(text),match.end()+85)]
            basis=("stay_total_claimed" if re.search(
                r"totale|prezzo complessivo|total price|total for stay|intero soggiorno",
                near,re.I) else "unknown")
            key=(room.casefold(),amount,basis)
            if key in seen:continue
            seen.add(key)
            terms=_explicit_conditions(text)
            offers.append({
                "roomType":room,"displayedAmount":amount,"currency":"EUR",
                "displayedBasis":basis,
                "bookingActionVisible":bool(card.get("hasBookingAction")),
                "conditions":text[-220:],"board":terms["board"],
                "refund":terms["refund"],"taxes":terms["taxes"],
                "verified":False,
                "evidence":("Prezzo mostrato accanto alla camera nella pagina risultati; "
                    +("totale soggiorno dichiarato" if basis=="stay_total_claimed"
                      else "base del prezzo non specificata")),
            })
            if len(offers)>=80:return offers
    return offers


async def probe_direct_stays(url, rows, *, limit=4, ghost=False):
    """Ricerca realmente date, occupazione e offerte nel booking engine pubblico.

    Un sito/engine trovato NON equivale a una ricerca completata. Il risultato
    distingue ricerca effettuata, prezzi osservati e preventivi verificati.
    """
    from playwright.async_api import async_playwright
    from site_audit_builder import public_url, robots_allowed
    stays=eligible_stays(rows,limit=limit)
    result={"status":"not_checked","samples":[],"verifiedQuotes":[],
            "observedRoomPrices":[],"evidence":[],
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
                            # Il compito primario di Leonardo è trascrivere i prezzi
                            # delle camere dopo la ricerca. Queste righe restano
                            # separate dai preventivi comparabili con le OTA.
                            if sample["searchSubmitted"]:
                                for offer in sample["quotes"]:
                                    result["observedRoomPrices"].append({
                                        "checkin":stay["checkin"],"checkout":stay["checkout"],
                                        "guests":stay["guests"],"nights":stay["nights"],
                                        "roomType":offer["roomType"],
                                        "displayedAmount":offer["displayedAmount"],
                                        "currency":offer["currency"],
                                        "priceBasis":offer["displayedBasis"],
                                        "dateContextConfirmed":bool(date_confirmed),
                                        "occupancyConfirmed":bool(occupancy.get("confirmed")),
                                        "sourceUrl":sample["sourceUrl"],
                                        "conditions":offer.get("conditions") or "",
                                        "source":"public_booking_engine_result",
                                    })
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
    elif result["observedRoomPrices"]:
        confirmed=all(x["dateContextConfirmed"] and x["occupancyConfirmed"]
                      for x in result["observedRoomPrices"])
        result["status"]=("room_prices_observed" if confirmed
                           else "room_prices_observed_context_unconfirmed")
    elif any(s.get("availability")=="unavailable_reported"
             for s in result["samples"]):
        result["status"]="unavailable_reported"
    elif any(s["status"]=="search_submitted_dates_confirmed"
             for s in result["samples"]):
        result["status"]="search_executed_rates_unverified"
    else:
        result["status"]="search_executed_dates_unconfirmed"
    result["evidence"].append(
        f"Ricerche disponibilità realmente inviate: {result['searchedTotal']}/{len(stays)}. "
        f"Prezzi di camere osservati: {len(result['observedRoomPrices'])}. "
        f"Preventivi completi verificati: {len(result['verifiedQuotes'])}. "
        "Le tariffe senza date, occupazione e condizioni confermate non entrano nel confronto OTA.")
    return result
