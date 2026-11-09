"""Campioni commerciali diretti in sola lettura.

Solo finestre identiche a Booking, nessuna invenzione di prezzi. I campioni
non verificati restano osservazioni e non entrano in delta o disponibilità.
"""
from __future__ import annotations

LEONARDO_BUILD = "direct-engine-cta-httpdiag-20261109-r1"

import asyncio
import re
from datetime import date
from urllib.parse import urlparse, urljoin, parse_qsl

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


async def _select_visual_calendar_date(scope, iso, trace=None):
    """Seleziona anno, mese e giorno nel calendario visibile, senza deduzioni.

    Bedzzle ha frecce DIVERSE per anno e mese. Individuiamo i due titoli
    vicino alla griglia e clicchiamo solo la freccia adiacente corretta;
    dopo OGNI click verifichiamo che il titolo sia effettivamente cambiato.
    """
    wanted=date.fromisoformat(iso)
    trace=trace if trace is not None else []
    last_navigation=None
    for attempt in range(24):
        try:
            state=await scope.evaluate(r"""target => {
              const MON=[
                ['gen','gennaio','jan','january'],
                ['feb','febbraio','february'],['mar','marzo','march'],
                ['apr','aprile','april'],['mag','maggio','may'],
                ['giu','giugno','jun','june'],['lug','luglio','jul','july'],
                ['ago','agosto','aug','august'],['set','sett','settembre','sep','september'],
                ['ott','ottobre','oct','october'],['nov','novembre','november'],
                ['dic','dicembre','dec','december']];
              const visible=e=>{
                if(!e || !(e.offsetWidth||e.offsetHeight||e.getClientRects().length))return false;
                const r=e.getBoundingClientRect();
                return r.width>0&&r.height>0&&r.bottom>0&&r.top<innerHeight;
              };
              const text=e=>(e?.innerText||e?.textContent||'').replace(/\s+/g,' ').trim().toLowerCase();
              const monthOf=s=>{
                const normalized=(s||'').replace(/\s+20\d{2}$/,'').trim();
                for(let i=0;i<12;i++)if(MON[i].includes(normalized))return i+1;
                return 0;
              };
              const marker='data-velora-calendar-target';
              document.querySelectorAll('['+marker+']').forEach(e=>e.removeAttribute(marker));
              const roots=[...document.querySelectorAll(
                '[class*="calendar"],[class*="datepicker"],[role=grid],table,[class*="month"],section,aside,div'
              )].filter(visible).slice(0,1100);
              const options=[];
              for(const root of roots){
                const leaves=[...root.querySelectorAll('button,a,span,td,div,th,[role=gridcell]')]
                  .filter(e=>visible(e) && text(e).length<32 && e.children.length<4);
                const dates=leaves.filter(e=>/^\d{1,2}$/.test(text(e))&&
                   Number(text(e))>=1&&Number(text(e))<=31);
                if(dates.length<20)continue;
                const months=leaves.filter(e=>monthOf(text(e))>0);
                const years=leaves.filter(e=>/^20\d{2}$/.test(text(e)));
                const combined=leaves.filter(e=>monthOf(text(e)) && /\b20\d{2}$/.test(text(e)));
                const m=months[0]||combined[0],y=years[0]||combined[0];
                if(!m||!y)continue;
                const month=monthOf(text(m));
                const year=Number((text(y).match(/\b20\d{2}\b/)||[])[0]||0);
                if(year<2020||year>2045||!month)continue;
                const rect=root.getBoundingClientRect();
                options.push({root,dates,m,y,month,year,area:rect.width*rect.height});
              }
              options.sort((a,b)=>a.area-b.area);
              const cal=options[0];
              if(!cal)return {action:'fail',reason:'Nessun calendario con mese, anno e giorni visibili'};
              const now=cal.year*12+cal.month,goal=target.year*12+target.month;
              if(now===goal){
                const disabled=e=>Boolean(e.closest(
                  '[disabled],[aria-disabled="true"],.disabled,.off,.old,.new,.outside,.not-current-month'));
                const matches=cal.dates.filter(e=>Number(text(e))===target.day&&!disabled(e));
                const clickables=matches.map(e=>
                  e.closest('button,a,[role=gridcell],[data-date],td')||e
                ).filter(e=>visible(e)&&!disabled(e));
                const unique=[...new Set(clickables)];
                // Se è il giorno duplicato del mese adiacente NON fare clic a caso.
                if(unique.length!==1)return {
                  action:'fail',reason:'Giorno '+target.day+
                    ' ambiguo/indisponibile in '+cal.month+'/'+cal.year,
                  currentMonth:cal.month,currentYear:cal.year};
                unique[0].setAttribute(marker,'day');
                return {action:'day',currentMonth:cal.month,currentYear:cal.year};
              }
              const yearStep=cal.year!==target.year;
              const anchor=yearStep?cal.y:cal.m;
              const targetIsLater=goal>now;
              const r=anchor.getBoundingClientRect();
              const cx=(r.left+r.right)/2,cy=(r.top+r.bottom)/2;
              const candidates=[...cal.root.querySelectorAll(
                'button,a,[role=button],[onclick],[ng-click],[data-ng-click],'+
                '[class*="arrow"],[class*="chevron"],[class*="next"],'+
                '[class*="prev"],[class*="glyphicon"],svg,i,span'
              )].filter(visible).map(e=>{
                const clickable=e.closest('button,a,[role=button],[onclick],[ng-click],[data-ng-click]')
                  ||e.closest('[class*="arrow"],[class*="chevron"],[class*="next"],'+
                       '[class*="prev"],[class*="glyphicon"]')
                  ||(getComputedStyle(e).cursor==='pointer'?e:null);
                return clickable;
              }).filter(Boolean);
              const nav=[...new Set(candidates)].map(e=>{
                const r=e.getBoundingClientRect();
                const x=(r.left+r.right)/2,y=(r.top+r.bottom)/2;
                return {e,x,y,distance:Math.abs(x-cx)+2*Math.abs(y-cy),width:r.width};
              }).filter(v=>visible(v.e)&&v.width<100&&
                 Math.abs(v.y-cy)<32&&Math.abs(v.x-cx)<125&&
                 (targetIsLater?v.x>cx+8:v.x<cx-8))
                .sort((a,b)=>a.distance-b.distance);
              if(!nav.length)return {action:'fail',
                reason:'Freccia '+(yearStep?'anno':'mese')+
                 ' '+(targetIsLater?'successivo':'precedente')+' non trovata',
                currentMonth:cal.month,currentYear:cal.year};
              nav[0].e.setAttribute(marker,'nav');
              return {action:'nav',kind:yearStep?'year':'month',
                currentMonth:cal.month,currentYear:cal.year,
                direction:targetIsLater?'forward':'backward'};
            }""",{"year":wanted.year,"month":wanted.month,"day":wanted.day})
            action=state.get("action")
            if last_navigation and (
                state.get("currentMonth"),state.get("currentYear"))==last_navigation:
                trace.append("La freccia è stata cliccata ma il calendario è rimasto su "+
                    f"{state.get('currentMonth')}/{state.get('currentYear')}")
                return False
            if action=="fail":
                trace.append(str(state.get("reason") or "Calendario non utilizzabile"))
                return False
            if action not in ("nav","day"):
                trace.append("Calendario: comando inatteso")
                return False
            locator=scope.locator('[data-velora-calendar-target="'+action+'"]')
            if await locator.count()!=1:
                trace.append("Calendario: pulsante/giorno non identificato in modo univoco")
                return False
            await locator.first.click(timeout=3500)
            if action=="day":
                trace.append("Giorno selezionato nel calendario "+
                    f"{state.get('currentMonth')}/{state.get('currentYear')}")
                return True
            last_navigation=(state.get("currentMonth"),state.get("currentYear"))
            trace.append("Navigazione "+str(state.get("kind"))+" "+
                f"{state.get('currentMonth')}/{state.get('currentYear')} "+
                str(state.get("direction")))
            await asyncio.sleep(0.28)
        except Exception as exc:
            trace.append("Errore calendario: "+type(exc).__name__)
            return False
    trace.append("Calendario: raggiunto limite di 24 passaggi senza trovare "+iso)
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


async def _visual_date_values(scope):
    """Legge i valori realmente visualizzati nei box Check in / Check out.

    Non deduce il successo dal clic su un giorno: il box deve mostrare
    esattamente le nuove date, non quelle iniziali del portale.
    """
    try:
        return await scope.evaluate(r"""() => {
          const visible=e=>Boolean(e.offsetWidth||e.offsetHeight||e.getClientRects().length);
          const text=e=>(e.innerText||e.textContent||'').replace(/\s+/g,' ').trim();
          const regex=/\b\d{1,2}[\/.-]\d{1,2}[\/.-]20\d{2}\b/;
          const fields={checkin:'',checkout:''};
          const labels=[...document.querySelectorAll('label,span,div,strong,p,button')]
              .filter(visible).filter(e=>text(e).length<36);
          for(const [key,pattern] of [
            ['checkin',/^(check[\s-]?in|arrivo|data d.arrivo)$/i],
            ['checkout',/^(check[\s-]?out|partenza|data di partenza)$/i]]){
            const matches=labels.filter(e=>pattern.test(text(e)));
            const candidates=[];
            for(const label of matches){
              let parent=label;
              for(let hops=0;parent&&hops<4;hops++,parent=parent.parentElement){
                const t=text(parent);
                if(t.length>170)break;
                const dates=t.match(new RegExp(regex.source,'g'))||[];
                if(dates.length===1)candidates.push({value:dates[0],size:t.length});
              }
            }
            candidates.sort((a,b)=>a.size-b.size);
            if(candidates.length)fields[key]=candidates[0].value;
          }
          return fields;
        }""")
    except Exception:
        return {"checkin":"","checkout":""}


async def _apply_dates(scope, stay):
    """Imposta check-in e check-out SOLO per il periodo richiesto in Velora."""
    controls=await scope.evaluate(r"""() => {
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
    inputs=scope.locator("input:visible")
    targets={}
    for name,pattern in patterns.items():
        matches=[]
        for i,row in enumerate(controls):
            if row["type"] not in ("date","text","search","tel"):continue
            label=" ".join(str(row.get(k) or "") for k in ("name","id","placeholder","aria","testid","label"))
            if re.search(pattern,label):matches.append((i,row))
        targets[name]=matches[0] if len(matches)==1 else (None,None)
    methods=[]
    traces=[]
    for name in ("checkin","checkout"):
        index,row=targets[name]
        requested=stay[name]
        try:
            if index is None:
                await _choose_visual_date_field(scope,name)
                path=[]
                if not await _select_visual_calendar_date(scope,requested,path):
                    traces.extend(path[-5:])
                    return {"applied":False,"reason":(
                        "Calendario "+name+" "+requested+" non selezionato: "+
                        " | ".join(path[-3:]))[:600],"trace":traces}
                methods.append("visual-calendar")
                traces.extend(path[-5:])
                continue
            field=inputs.nth(index)
            if row["readOnly"]:
                explicit=await _select_explicit_calendar_date(scope,field,requested)
                if not explicit:
                    path=[]
                    explicit=await _select_visual_calendar_date(scope,requested,path)
                    traces.extend(path[-5:])
                if not explicit:
                    return {"applied":False,"reason":(
                        "Calendario "+name+" "+requested+
                        " non selezionabile; "+" | ".join(traces[-3:]))[:600],
                        "trace":traces}
                methods.append("calendar")
            else:
                formatted=requested
                if row["type"]!="date":
                    y,m,d=requested.split("-")
                    formatted=f"{d}/{m}/{y}"
                await field.fill(formatted,timeout=4500)
                await field.press("Tab",timeout=2500)
                if not _date_is_present([await field.input_value()],requested):
                    # Il campo è controllato da JavaScript: riapri il
                    # calendario e usa i pulsanti reali, non una falsa fill.
                    await field.click(timeout=2500)
                    path=[]
                    if not await _select_visual_calendar_date(scope,requested,path):
                        traces.extend(path[-5:])
                        return {"applied":False,"reason":(
                            "Il campo "+name+" non accetta la data e il calendario "+
                            "non la seleziona: "+" | ".join(path[-3:]))[:600],
                            "trace":traces}
                    methods.append("calendar-fallback")
                    traces.extend(path[-5:])
                else:
                    methods.append(row["type"])
        except Exception as exc:
            return {"applied":False,"reason":(
                "Data "+name+" non impostata: "+type(exc).__name__), "trace":traces}
    await asyncio.sleep(0.3)
    current=await scope.evaluate(r"""() => [...document.querySelectorAll('input')]
      .filter(e=>e.offsetWidth||e.offsetHeight||e.getClientRects().length)
      .map(e=>e.value)""")
    visual=await _visual_date_values(scope)
    # Un click su un numero NON è prova che le date siano corrette.
    valid=all(_date_is_present([*current,visual.get(name)],stay[name])
              for name in ("checkin","checkout"))
    return {"applied":valid,"method":"/".join(methods),"trace":traces[-12:],
            "displayedDates":visual,
            "reason":("Check-in e check-out 2027 letti nuovamente dai box del motore"
                      if valid else
                      "Il motore mostra ancora date diverse: "+
                      str(visual.get("checkin") or "check-in non visibile")+" / "+
                      str(visual.get("checkout") or "check-out non visibile"))}


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
            const lines=raw.split(/\\n+/).map(x=>x.replace(/\s+/g,' ').trim()).filter(Boolean);
            const all=lines.join(' ').slice(0,2000);
            const heading=[...el.querySelectorAll(
              'h2,h3,h4,h5,[class*=room-name],[class*=roomName],[class*=room-title],'+
              '[class*=roomTitle],[class*=name],[class*=Name],[class*=title],[class*=Title],strong,b')]
              .map(e=>(e.textContent||'').replace(/\s+/g,' ').trim())
              .find(t=>t.length>2&&t.length<130&&!/(€|EUR)/.test(t))||'';
            const likely=lines.find(t=>t.length>3&&t.length<120&&
              /\\b(camera|camere|room|suite|deluxe|classic|superior|family|apartment|appartamento|trullo|pajara|matrimoniale|doppia|standard)\\b/i.test(t) &&
              !/(€|EUR)/.test(t))||'';
            const name=heading||likely;
            if(!name)continue;
            const key=name.toLowerCase()+'|'+all.slice(0,180);
            if(seen.has(key))continue;
            seen.add(key);
            result.push({roomType:name.slice(0,140),text:all,
              hasBookingAction:/\\b(prenota|book now|seleziona|select room|scegli)\\b/i.test(all),
              textLength:all.length});
          }
          // Fallback neutrale per booking engine con contenitori <div>
          // senza nomi CSS "room"/"rate", ma con prezzo vicino al nome camera.
          if(!result.length){
            const txtPrice=e=>(e.innerText||'').replace(/\s+/g,' ').trim();
            const words=/\\b(camera|camere|room|suite|deluxe|classic|superior|family|apartment|appartamento|trullo|pajara|matrimoniale|doppia|standard)\\b/i;
            const prices=[...document.querySelectorAll('span,strong,b,p,div')]
              .filter(visible).filter(e=>{
                const t=txtPrice(e);
                return t.length>1&&t.length<75&&
                  /(?:€|EUR)\s*\d|\d[\d.,]*\s*(?:€|EUR)/i.test(t);
              }).slice(0,200);
            for(const price of prices){
              let parent=price.parentElement;
              for(let hops=0;parent && hops<5;hops++,parent=parent.parentElement){
                const raw=(parent.innerText||'').trim();
                if(!raw||raw.length>1800)break;
                const lines=raw.split(/\\n+/).map(x=>x.replace(/\s+/g,' ').trim()).filter(Boolean);
                const title=lines.find(x=>words.test(x)&&x.length<130&&!/(€|EUR)/.test(x))||'';
                if(!title)continue;
                const key=title.toLowerCase()+'|'+raw.slice(0,180);
                if(!seen.has(key)){
                  seen.add(key);
                  result.push({roomType:title,text:lines.join(' ').slice(0,1800),
                    hasBookingAction:/\\b(prenota|book now|seleziona|scegli)\\b/i.test(raw),
                    textLength:raw.length});
                }
                break;
              }
            }
          }
          // Il contenitore più piccolo con nome e prezzo evita attribuzioni
          // errate a camere vicine nella stessa pagina.
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


def _engine_destination_matches(candidate, engine_url):
    """Check both provider and structure identity (Bedzzle public apikey)."""
    expected=urlparse(engine_url)
    observed=urlparse(candidate)
    if observed.scheme not in ("http","https") or not observed.hostname:
        return False
    if (expected.hostname or "").lower()!=(observed.hostname or "").lower():
        return False
    expected_q={k.lower():v for k,v in parse_qsl(expected.query)}
    observed_q={k.lower():v for k,v in parse_qsl(observed.query)}
    if expected_q.get("apikey"):
        return observed_q.get("apikey")==expected_q["apikey"]
    if expected.path not in ("","/") and not observed.path.startswith(expected.path.rstrip("/")):
        return False
    return True


async def _navigate_booking_engine(page, context, engine_url, site_url=None):
    """Enter via official website as a guest, or try one direct navigation.
    Never treat an HTTP failure as evidence the hotel has no availability.
    """
    from site_audit_builder import public_url, robots_allowed, dismiss_cookie
    diagnostic={"openingMethod":"not_attempted","httpStatus":None,
                "pageReached":False,"reason":"","fallbackUsed":False}
    if site_url:
        try:
            website=public_url(site_url)
            if robots_allowed(website,{}) is True:
                site_response=await page.goto(
                    website,wait_until="domcontentloaded",timeout=20000)
                diagnostic["siteHttpStatus"]=site_response.status if site_response else None
                if site_response and site_response.status<400:
                    await page.wait_for_timeout(500)
                    await dismiss_cookie(page)
                    links=page.locator("a[href]:visible")
                    candidates=[]
                    for i in range(min(await links.count(),180)):
                        anchor=links.nth(i)
                        href=await anchor.get_attribute("href") or ""
                        dest=urljoin(page.url,href)
                        if not _engine_destination_matches(dest,engine_url):
                            continue
                        try:label=(await anchor.inner_text(timeout=1200)).strip()
                        except Exception:label=""
                        score=2 if re.search(r"prenot|book|disponibilit|availability",label,re.I) else 0
                        candidates.append((score,anchor))
                    if candidates:
                        candidates.sort(key=lambda item:item[0],reverse=True)
                        before=set(context.pages)
                        try:
                            await candidates[0][1].click(timeout=6500)
                            await page.wait_for_timeout(1400)
                            new_pages=[item for item in context.pages if item not in before]
                            destination=new_pages[-1] if new_pages else page
                            try:await destination.wait_for_load_state(
                                "domcontentloaded",timeout=7000)
                            except Exception:pass
                            if _engine_destination_matches(destination.url,engine_url):
                                try:
                                    body=(await destination.locator("body").inner_text(
                                        timeout=3500)).lower()[:9000]
                                except Exception:
                                    body=""
                                if re.search(
                                    r"access denied|accesso negato|forbidden|captcha|"
                                    r"too many requests|temporarily blocked|blocked by",
                                    body,re.I):
                                    diagnostic["reason"]=(
                                        "Il portale mostra una limitazione d'accesso "
                                        "dopo il clic dal sito ufficiale.")
                                else:
                                    diagnostic.update(openingMethod="official_site_cta",
                                                      pageReached=True,
                                                      reason="Link Prenota del sito ufficiale seguito.")
                                    return destination,diagnostic
                            diagnostic["reason"]="Il link Prenota non ha raggiunto il motore previsto."
                        except Exception as exc:
                            diagnostic["reason"]="Clic Prenota non riuscito: "+type(exc).__name__
                    else:
                        diagnostic["reason"]="Link Prenota verso il motore configurato non individuato."
                else:
                    diagnostic["reason"]="Sito ufficiale: HTTP "+str(
                        diagnostic.get("siteHttpStatus") or "nessuna risposta")
            else:
                diagnostic["reason"]="Navigazione del sito ufficiale non autorizzata o verificabile."
        except Exception as exc:
            diagnostic["reason"]="Visita sito ufficiale: "+type(exc).__name__
    # Only one direct fallback, never aggressive retries on a blocked page.
    diagnostic["fallbackUsed"]=bool(site_url)
    try:
        response=await page.goto(engine_url,wait_until="domcontentloaded",timeout=22000)
        status=response.status if response else None
        diagnostic.update(openingMethod="direct_url",httpStatus=status,
                          pageReached=bool(response and status<400))
        diagnostic["reason"]=("Motore raggiunto tramite URL diretto." if response and status<400
                              else "Motore: HTTP "+str(status) if status is not None
                              else "Motore: nessuna risposta HTTP.")
    except Exception as exc:
        diagnostic.update(openingMethod="direct_url",pageReached=False,
                          reason="Motore: "+type(exc).__name__)
    return page,diagnostic


async def probe_direct_stays(url, rows, *, limit=4, ghost=False, site_url=None):
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
            blocked_status=None
            systemic_calendar_failure=""
            for stay in stays:
                sample={**stay,"status":"not_verified","sourceUrl":url.split("?")[0],"quotes":[],
                        "availability":"not_verified","searchSubmitted":False,
                        "evidence":[]}
                if blocked_status is not None or systemic_calendar_failure:
                    sample["status"]="access_blocked" if blocked_status is not None else "calendar_not_navigable"
                    sample["evidence"].append(
                        ("Ricerca sospesa dopo HTTP "+str(blocked_status) if blocked_status is not None
                         else "Calendario non navigabile: "+systemic_calendar_failure)+
                        ". Evito di riaprire inutilmente le settimane successive.")
                    result["samples"].append(sample)
                    continue
                page=await context.new_page()
                try:
                    engine_page,navigation=await _navigate_booking_engine(
                        page,context,url,site_url=site_url)
                    sample["navigation"]=navigation
                    if not navigation["pageReached"]:
                        sample["status"]="navigation_error"
                        sample["evidence"].append("Motore non raggiunto: "+(
                            navigation.get("reason") or "errore sconosciuto"))
                        if navigation.get("httpStatus") is not None:
                            sample["evidence"].append(
                                "Codice HTTP: "+str(navigation["httpStatus"]))
                            if navigation["httpStatus"] in (401,403,429):
                                blocked_status=navigation["httpStatus"]
                    else:
                        sample["evidence"].append(
                            "Apertura booking engine: "+navigation["openingMethod"]+".")
                        await engine_page.wait_for_timeout(1200)
                        # I booking engine sono spesso in iframe cross-origin:
                        # Playwright vi accede con gli stessi controlli dell'utente.
                        scopes=[engine_page.main_frame]+[frame for frame in engine_page.frames
                            if frame!=engine_page.main_frame and frame.url.startswith(("https://","http://"))]
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
                            sample["formDiagnostic"]=await _form_diagnostic(engine_page.main_frame)
                            reasons=[(entry.get("dates") or {}).get("reason") or entry.get("error") or ""
                                     for entry in attempts]
                            sample["evidence"].append(
                                "Ricerca NON eseguita: non è stato possibile selezionare check-in e check-out.")
                            sample["evidence"].extend(
                                "Calendario: "+reason for reason in reasons if reason)
                            for reason in reasons:
                                if any(fragment in reason.lower() for fragment in (
                                    "freccia", "è rimasto su", "nessun calendario",
                                    "calendario non utilizzabile","limite di 24 passaggi")):
                                    systemic_calendar_failure=reason[:220]
                                    break
                        else:
                            sample["formDiagnostic"]=await _form_diagnostic(active)
                            occupancy=await _apply_guests(active,stay["guests"])
                            sample["occupancyControl"]=occupancy
                            sample["searchSubmitted"]=False
                            before_pages=set(context.pages)
                            submitted=await _submit_availability_search(active)
                            sample["searchAction"]=submitted
                            if submitted["submitted"]:
                                sample["searchSubmitted"]=True
                                result["searchedTotal"]+=1
                                await page.wait_for_timeout(1600)
                                # Alcuni motori mostrano i risultati in una nuova
                                # scheda. La lettura deve seguire la pagina aperta.
                                new_pages=[p for p in context.pages if p not in before_pages]
                                if new_pages:
                                    result_page=new_pages[-1]
                                    try:await result_page.wait_for_load_state("domcontentloaded",timeout=5000)
                                    except Exception:pass
                                    active=result_page.main_frame
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
                            sample["quotes"]=(await _visible_offer_candidates(active)
                                if sample["searchSubmitted"] else [])
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
                    for additional in list(context.pages):
                        if additional != page:
                            try:await additional.close()
                            except Exception:pass
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
