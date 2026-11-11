// Velora Chrome Companion: user-initiated reading of a visibly opened Expedia page.
// Does NOT perform navigation, bypass CAPTCHAs, send credentials or use a proxy.
"use strict";

function visibleExpediaCapture() {
  const hostname = location.hostname.toLowerCase();
  if (!/^(?:[a-z0-9-]+\.)?expedia\.(?:it|com|de|fr|es|co\.uk)$/.test(hostname)) {
    return {error: "La scheda aperta non appartiene a Expedia."};
  }
  const text = (document.body?.innerText || "").slice(0, 30000);
  if (/accesso è temporaneamente limitato|sei un robot\?|mostraci il tuo lato umano|your access (?:has been|is) temporarily limited/i.test(text)) {
    return {error: "Expedia mostra una verifica o un blocco. Nessuna tariffa verrà letta. Apri una pagina camere accessibile nel tuo Chrome normale."};
  }

  const url = new URL(location.href);
  const allowedParams = new Set([
    "chkin","chkout","checkin","checkout","check_in","check_out",
    "d1","d2","startDate","endDate","adults","rooms","rm1","children",
    "selected","sort","regionId","destination","destinationId"
  ]);
  const sanitized = new URL(url.origin + url.pathname);
  for (const [key,value] of url.searchParams) if (allowedParams.has(key) && value.length < 90) sanitized.searchParams.append(key,value);
  function iso(value) {
    const match = String(value || "").match(/\b(20\d\d)-(\d\d)-(\d\d)\b/);
    if (!match) return "";
    const result = match[0];
    const d = new Date(result + "T00:00:00Z");
    return !Number.isNaN(d.getTime()) && d.toISOString().slice(0,10)===result ? result : "";
  }
  function pickDate(keys) {
    for (const key of keys) {
      const found=iso(url.searchParams.get(key));
      if (found) return found;
    }
    return "";
  }
  const checkin = pickDate(["chkin","checkin","check_in","d1","startDate"]);
  const checkout = pickDate(["chkout","checkout","check_out","d2","endDate"]);
  let nights=0;
  if (checkin && checkout) nights=Math.round((Date.parse(checkout)-Date.parse(checkin))/86400000);
  if (nights<1 || nights>60) nights=0;
  let guests=0;
  for (const key of ["adults","rm1"]) {
    const value=url.searchParams.get(key)||"";
    if (/^\d{1,2}$/.test(value)) {guests=Number(value);break;}
    const rm=value.match(/(?:^|,)a(\d{1,2})(?:,|$)/);
    if (rm) {guests=Number(rm[1]);break;}
  }
  if (!guests) {
    const people = text.slice(0,2500).match(/\b(\d{1,2})\s*(?:persone|ospiti|adulti)\b/i);
    if (people) guests=Number(people[1]);
  }

  const isVisible = element => {
    if (!(element instanceof Element) || !element.getClientRects().length) return false;
    const styles=getComputedStyle(element);
    return styles.display!=="none" && styles.visibility!=="hidden";
  };
  function parseMoney(value) {
    const normalized=String(value).replace(/\s/g,"").replace(/[.,](?=\d{3}(?:[.,]|$))/g,"");
    const n=Number(normalized.replace(",","."));
    return Number.isFinite(n)&&n>=1&&n<=200000 ? n : null;
  }
  const pricePattern=/(\d{1,3}(?:[.\s]\d{3})+(?:,\d{2})?|\d{1,6}(?:[.,]\d{2})?)\s*€|€\s*(\d{1,3}(?:[.\s]\d{3})+(?:,\d{2})?|\d{1,6}(?:[.,]\d{2})?)/g;
  function quoteTotal(cardText) {
    // Expedia frequently shows: "45 € di sconto / 461 € (barrato) /
    // 416 € / per 3 notti, 1 camera / 139 € a notte".
    // A wide substring around "per 3 notti" incorrectly marks all four
    // figures as stay totals. Only the closest price tied to that label
    // is evidence of the actual total; never use crossed/discount/nightly.
    const hits=[...cardText.matchAll(pricePattern)].map(match=>{
      const amount=parseMoney(match[1]||match[2]);
      return {amount,start:match.index,end:match.index+match[0].length};
    }).filter(hit=>hit.amount!==null);
    if(!hits.length) return null;
    const markers=[...cardText.matchAll(/\b(?:per\s+(\d{1,2})\s+nott[ei]|for\s+(\d{1,2})\s+nights?)\b/gi)];
    const candidates=[];
    for(const marker of markers) {
      const count=Number(marker[1]||marker[2]);
      if(nights>0 && count!==nights)continue;
      const before=hits.filter(hit=>hit.end<=marker.index && marker.index-hit.end<=72)
        .sort((left,right)=>right.end-left.end);
      let selected=before[0];
      if(selected){
        const between=cardText.slice(selected.end,marker.index);
        if(/(?:\b(?:a|per)\s+notte\b|\bper\s+night\b|di\s+sconto|discount)/i.test(between))
          selected=null;
      }
      // Also support "per 3 notti: € 416" without guessing from other
      // prices farther away in the same card.
      if(!selected){
        const following=hits.filter(hit=>hit.start>=marker.index+marker[0].length &&
          hit.start-marker.index-marker[0].length<=35)
          .sort((left,right)=>left.start-right.start);
        const candidate=following[0];
        if(candidate && !/\b(?:a|per)\s+notte\b|\bper\s+night\b/i.test(
          cardText.slice(marker.index+marker[0].length,candidate.start)))
          selected=candidate;
      }
      if(selected)candidates.push({amount:selected.amount,confidence:"total-for-stay",idx:selected.start});
    }
    // Generic explicitly labeled totals (without an exact "per N notti")
    // are usable only if an unambiguous monetary amount immediately follows.
    if(!candidates.length){
      const totalMarkers=[...cardText.matchAll(
        /\b(?:prezzo\s+totale|totale\s+soggiorno|in\s+totale|total\s+price|total\s+for\s+(?:the\s+)?stay)\s*[:\-]?\s*/gi)];
      for(const marker of totalMarkers){
        const following=hits.filter(hit=>hit.start>=marker.index+marker[0].length &&
          hit.start-marker.index-marker[0].length<=20).sort((a,b)=>a.start-b.start);
        if(following[0])candidates.push({
          amount:following[0].amount,confidence:"total-for-stay",idx:following[0].start
        });
      }
    }
    // Several DIFFERENT real stay totals in the same room block mean
    // multiple rate plans: do not assign an arbitrary plan to the room.
    if(new Set(candidates.map(item=>item.amount)).size!==1)return null;
    return candidates[0]||null;
  }
  const invalidTitles=/^(?:prenota|book|scegli la tua camera|effettua un upgrade|il nostro prezzo più basso|questo è un prezzo standard|colazione inclusa|vista giardino|parcheggio incluso|scopri di più|wifi gratuito|paga più tardi|dettagli della camera|room details)$/i;
  const headingSelector='[data-stid*="room-name" i],[data-testid*="room-name" i],h2,h3,h4,h5,[role="heading"]';
  const roomHint=/(?:\bcamera\b|\bdoppia\b|\btripla\b|\bsuite\b|\btrullo\b|\bclassic\b|\bdeluxe\b|\bsuperior\b|\bjunior\b|\bfamiliare\b|\bking\b|\bapartment\b|\bdouble\b|\btwin\b|\broom\b|\bappartamento\b|\bstudio\b)/i;
  function headingText(node) {
    return (node.innerText||"").trim().replace(/\s+/g," ");
  }
  function looksLikeRoomHeading(node) {
    const value=headingText(node);
    return isVisible(node)&&value.length>=8&&value.length<=170&&roomHint.test(value)&&
      !invalidTitles.test(value)&&!/\bprezzo|\bprice|per \d+ nott|€|\b(?:scegli|choose|select|visualizza|show)\b/i.test(value);
  }
  function roomTitle(node) {
    const nodes=[...node.querySelectorAll(headingSelector)].filter(looksLikeRoomHeading);
    for (const element of nodes) return headingText(element);
    const lines=(node.innerText||"").split("\n").map(x=>x.trim());
    return lines.find(value=>value.length>=10&&value.length<=150 &&
      /(?:camera|doppia|tripla|suite|trullo|classic|deluxe|superior|junior|familiare|king|apartment|double|twin|room)/i.test(value) &&
      !/prezzo|€|colazione|prenota|nott[ei]/i.test(value)) || "";
  }
  function cardFromButton(button) {
    let current=button.parentElement;
    for(let level=0;level<12&&current;level++,current=current.parentElement) {
      if(!isVisible(current)) continue;
      const content=(current.innerText||"").trim();
      if(content.length<65||content.length>3500) continue;
      const actions=[...current.querySelectorAll("button,[role=button]")].filter(isVisible)
        .filter(x=>roomAction.test((x.innerText||"").trim().replace(/\s+/g," ")));
      if(actions.length>2) continue;
      const title=roomTitle(current);
      const price=quoteTotal(content);
      if(title&&price) return {node:current,title,price,text:content};
    }
    return null;
  }
  // Expedia localizes room CTAs and may append "ora"/"now" to the label.
  // Keep this restricted to explicit room/rate actions: do not click anything.
  const roomAction=/^(?:prenota(?: ora)?|book(?: now)?|reserve(?: now)?|seleziona(?: (?:camera|tariffa))?|choose(?: (?:room|rate))?|select(?: (?:a )?(?:room|rate))?)\s*[›»→]?$/i;
  const bookingButtons=[...document.querySelectorAll("button,[role=button]")].filter(isVisible)
    .filter(x=>roomAction.test((x.innerText||"").trim().replace(/\s+/g," ")));
  const buttonCandidates=bookingButtons.map(cardFromButton).filter(Boolean);
  // Expedia can display room cards without a "Book" button, or show a button
  // only after selecting a rate. Read room headings and explicit stay totals
  // from their own card instead of relying on one specific CTA.
  const roomHeadings=[...document.querySelectorAll(headingSelector)].filter(looksLikeRoomHeading);
  function cardFromHeading(heading) {
    let current=heading.parentElement;
    for(let level=0;level<12&&current;level++,current=current.parentElement) {
      if(!isVisible(current)) continue;
      const content=(current.innerText||"").trim();
      if(content.length<45) continue;
      if(content.length>3500) break;
      const titles=[...current.querySelectorAll(headingSelector)].filter(looksLikeRoomHeading)
        .map(headingText);
      // Do not borrow a price from a neighboring room card.
      if(new Set(titles).size>1) break;
      const price=quoteTotal(content);
      if(price) return {node:current,title:headingText(heading),price,text:content};
    }
    return null;
  }
  const headingCandidates=roomHeadings.map(cardFromHeading).filter(Boolean);
  // Expedia's three-column room grid can put the rate/footer in a sibling
  // subtree. In that layout, walking heading ancestors never reaches the
  // price without also reaching several other rooms. Match rendered price
  // panels to the heading directly above in the SAME visual column instead.
  // This is a read-only fallback, not browser navigation.
  const renderedHeadings=roomHeadings.map(node=>({
    node,title:headingText(node),rect:node.getBoundingClientRect?.()
  })).filter(item=>item.rect&&item.rect.width>0&&item.rect.height>0);
  const pricePanelSelector="div,span,p,strong,b,section,article";
  const possiblePricePanels=[...document.querySelectorAll(pricePanelSelector)].slice(0,7000);
  const pricePanels=possiblePricePanels.map(node=>{
    if(!isVisible(node)) return null;
    const content=(node.innerText||"").trim();
    if(content.length<10||content.length>260) return null;
    if(!/\b(?:per\s+\d{1,2}\s+nott[ei]|for\s+\d{1,2}\s+nights?)\b/i.test(content)) return null;
    const price=quoteTotal(content);
    if(!price||price.idx>65) return null;
    // The text must itself label the displayed price as a stay total,
    // and when known it must agree with the selected number of nights.
    const after=content.slice(price.idx+1,price.idx+145);
    if(nights>0&&!new RegExp("\\b(?:per|for)\\s+"+nights+"\\s+(?:nott[ei]|nights?)\\b","i").test(after)) return null;
    const rect=node.getBoundingClientRect?.();
    if(!rect||rect.width<20||rect.height<8) return null;
    return {node,rect,price,text:content};
  }).filter(Boolean);
  const spatialCandidates=[];
  const usedPricePositions=new Set();
  for (const panel of pricePanels) {
    const rect=panel.rect;
    const panelCenter=(rect.left+rect.right)/2;
    const matches=renderedHeadings.map(h=>{
      const hCenter=(h.rect.left+h.rect.right)/2;
      const columnDistance=Math.abs(hCenter-panelCenter);
      const verticalDistance=rect.top-h.rect.top;
      if(verticalDistance<35||verticalDistance>780||columnDistance>190) return null;
      return {heading:h,score:verticalDistance+columnDistance*.25,columnDistance};
    }).filter(Boolean).sort((a,b)=>a.score-b.score);
    if(!matches.length) continue;
    const winner=matches[0];
    // A price must be attributable to exactly one room in a column.
    if(matches.length>1&&Math.abs(matches[1].score-winner.score)<12&&
       matches[1].heading.title!==winner.heading.title) continue;
    const title=winner.heading.title;
    const locationKey=title.toLocaleLowerCase("it-IT")+"|"+panel.price.amount+"|"+
      Math.round(rect.top/10)+"|"+Math.round(panelCenter/15);
    if(usedPricePositions.has(locationKey)) continue;
    usedPricePositions.add(locationKey);
    spatialCandidates.push({node:panel.node,title,price:panel.price,text:panel.text});
  }
  const candidates=[...buttonCandidates,...headingCandidates,...spatialCandidates];
  const seen=new Set();
  const rooms=[];
  for (const candidate of candidates) {
    const title=candidate.title;
    const price=candidate.price.amount;
    const key=title.toLocaleLowerCase("it-IT")+"|"+price;
    if(seen.has(key)) continue;
    seen.add(key);
    if(rooms.length>=40) break;
    const text=candidate.text;
    const board=/colazione inclusa|breakfast included/i.test(text)
      ? "Colazione inclusa" : (/solo camera|room only/i.test(text)?"Solo camera":"Non chiaro");
    const refund=/completamente rimborsabile|fully refundable/i.test(text)
      ? "Rimborsabile" : (/non rimborsabile|non-refundable/i.test(text)?"Non rimborsabile":"Non chiaro");
    const taxes=/tasse e oneri inclusi|taxes and fees included/i.test(text)
      ? "Tutte le imposte incluse" : "Non chiaro";
    rooms.push({roomType:title,total:price,board,refund,taxes,confidence:candidate.price.confidence});
  }
  // Evidence for presentation asymmetries. This is a sample of visible,
  // loaded content, NOT an assertion about the entire OTA photo gallery.
  const imageNodes=[...document.querySelectorAll("img")].filter(isVisible);
  const photoKeys=new Set();
  const photoAlts=new Set();
  for(const img of imageNodes) {
    const url=String(img.currentSrc||img.src||"");
    if(!url||url.startsWith("data:")) continue;
    const w=Number(img.naturalWidth||img.width||0),h=Number(img.naturalHeight||img.height||0);
    if(w<180||h<120) continue;
    try {photoKeys.add(new URL(url,location.href).pathname);}catch{continue;}
    const alt=String(img.alt||"").trim();
    if(alt.length>=5&&alt.length<=140) photoAlts.add(alt);
  }
  const featureChecks=[
    ["Colazione",/\bcolazione inclusa\b|\bbreakfast included\b/i],
    ["Wi-Fi",/\bwi-?fi gratuito\b|\bfree wi-?fi\b/i],
    ["Parcheggio",/\bparcheggio incluso\b|\bfree parking\b/i],
    ["Vista giardino",/\bvista giardino\b|\bgarden view\b/i],
    ["Piscina",/\bpiscina\b|\bpool\b/i],
    ["Aria condizionata",/\baria condizionata\b|\bair conditioning\b/i],
    ["Spa",/\bspa\b|\bwellness\b/i]
  ];
  const features=featureChecks.filter(([,regex])=>regex.test(text)).map(([label])=>label);
  const metaDescription=String(document.querySelector('meta[name="description"]')?.getAttribute?.("content")||"")
    .trim().slice(0,450);
  const presentation={
    visibleImageCount:photoKeys.size,
    photoAltSamples:[...photoAlts].slice(0,15),
    visibleServices:features,
    descriptionExcerpt:metaDescription,
    roomCount:rooms.length,
    evidenceScope:"sample-of-visible-loaded-images-and-page-text"
  };
  const heading=(document.querySelector("h1")?.innerText||"").trim();
  const pageTitle=(document.title||heading||"").trim().slice(0,240);
  // On the rate grid, h1 can be "Scegli la tua camera": prefer the actual
  // accommodation name from the page title over this generic heading.
  const genericHeading=/scegli la tua camera|select your room|choose your room|rooms? and rates|le tue camere/i.test(heading);
  const propertyName=(genericHeading?document.title:heading||document.title||"")
    .trim().replace(/\s+[|–-]\s+Expedia.*$/i,"").slice(0,180);
  return {
    schema:"velora-expedia-visible-v1",
    pageTitle,propertyName,
    sourceUrl:sanitized.toString(),
    checkin,checkout,nights,guests,
    rooms,presentation,capturedAt:new Date().toISOString(),
    warning:rooms.length
      ? "Camere lette dal contenuto visibile. Identità e condizioni devono essere confermate prima di un confronto tariffario."
      : "Nessuna tariffa totale affidabile per camera: "+bookingButtons.length+
        " pulsanti camera riconosciuti, "+roomHeadings.length+" titoli di camera visibili, "+
        pricePanels.length+" pannelli prezzo, "+candidates.length+" schede con titolo e totale. "+
        (roomHeadings.length
          ? "Camere individuate, ma il prezzo totale per soggiorno non è leggibile o è ambiguo. "+
            "Scorri fino alle tariffe esposte sotto ciascuna camera e ripeti l'acquisizione. "
          : "La pagina potrebbe usare un layout diverso o non avere ancora caricato i nomi delle camere. ")+
        "Nessun prezzo inventato."
  };
}


/**
 * Vrbo is typically a whole-property listing, unlike Expedia's hotel room grid.
 * Capture at most one explicit, unambiguous stay total from the already opened page.
 * Never infer a total by multiplying a nightly amount.
 */
function visibleVrboCapture() {
  const host=location.hostname.toLowerCase();
  if(!/(^|\.)vrbo\.(com|co\.uk|de|fr|es|it)$/.test(host))
    return {error:"La scheda aperta non appartiene a Vrbo."};
  const pageText=String(document.body?.innerText||"").slice(0,50000);
  if(/accesso (?:temporaneamente )?limitato|access (?:temporarily )?limited|access denied|sei un robot|are you a robot|verify you are human|verifica che sei una persona|captcha/i.test(pageText.slice(0,3500)))
    return {error:"Vrbo mostra una limitazione o una verifica. Il Companion non può superarla. Apri prima una normale scheda struttura accessibile."};
  const url=new URL(location.href);
  const safeUrl=new URL(url.origin+url.pathname);
  const paramsAllowed=new Set(["chkin","chkout","checkin","checkout","startDate","endDate","d1","d2","adults","guests","rm1","arrival","departure"]);
  for(const [key,val] of url.searchParams)if(paramsAllowed.has(key)&&val.length<70)safeUrl.searchParams.set(key,val);
  function iso(v) {
    const match=String(v||"").match(/20\d{2}-\d{2}-\d{2}/);
    if(!match)return "";
    const d=new Date(match[0]+"T00:00:00Z");
    return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===match[0]?match[0]:"";
  }
  const pickDate=keys=>{for(const key of keys){const value=iso(url.searchParams.get(key));if(value)return value;}return "";};
  const checkin=pickDate(["chkin","checkin","d1","startDate","arrival"]);
  const checkout=pickDate(["chkout","checkout","d2","endDate","departure"]);
  const nightDiff=checkin&&checkout?Math.round((Date.parse(checkout)-Date.parse(checkin))/86400000):0;
  const nights=nightDiff>=1&&nightDiff<=60?nightDiff:0;
  let guests=0;
  for(const key of ["adults","guests","rm1"]){
    const value=url.searchParams.get(key)||"";
    if(/^\d{1,2}$/.test(value)){guests=Number(value);break;}
    const match=value.match(/(?:^|,)a(\d{1,2})(?:,|$)/);
    if(match){guests=Number(match[1]);break;}
  }
  if(!guests){
    const match=pageText.slice(0,3500).match(/\b(\d{1,2})\s*(?:ospiti|viaggiatori|adulti|guests|travelers|adults)\b/i);
    if(match)guests=Number(match[1]);
  }
  const visible=e=>e instanceof Element&&e.getClientRects().length>0&&
    getComputedStyle(e).display!=="none"&&getComputedStyle(e).visibility!=="hidden";
  const title=(document.querySelector("h1")?.innerText||"").trim().replace(/\s+/g," ").slice(0,180);
  const pageTitle=String(document.title||"").trim().slice(0,240);
  const propertyName=/^(?:vrbo|alloggi|sistemazioni|find your|results?)/i.test(title)||!title
    ? pageTitle.replace(/\s+[|–-]\s+Vrbo.*$/i,"").slice(0,180)
    : title;
  const currencyPattern=/(?:€\s*(\d[\d.,\s]*\d|\d)|(\d[\d.,\s]*\d|\d)\s*€)/g;
  const parseEur=raw=>{
    let v=String(raw||"").replace(/\s/g,"");
    if(/[.,]/.test(v)){
      if(v.includes(".")&&v.includes(",")){
        const decimal=v.lastIndexOf(",")>v.lastIndexOf(".")?",":".";
        const thousands=decimal===","?".":",";
        v=v.split(thousands).join("").replace(decimal,".");
      } else if(/^[\d]+[.,]\d{3}$/.test(v))v=v.replace(/[.,]/g,"");
      else v=v.replace(",",".");
    }
    const amount=Number(v);
    return Number.isFinite(amount)&&amount>=1&&amount<=200000?amount:null;
  };
  const candidates=[];
  const priceNodes=[...document.querySelectorAll("div,span,p,strong,b,section")].slice(0,7000);
  for(const node of priceNodes) {
    if(!visible(node))continue;
    const txt=String(node.innerText||"").trim().slice(0,310);
    if(!txt||txt.length>300)continue;
    if(!/€/.test(txt))continue;
    const matches=[...txt.matchAll(currencyPattern)];
    for(const match of matches){
      const value=parseEur(match[1]||match[2]);
      if(value===null)continue;
      const before=txt.slice(Math.max(0,match.index-90),match.index);
      const after=txt.slice(match.index+match[0].length,match.index+match[0].length+110);
      const context=(before+" "+after).toLowerCase();
      const isStay=/\b(?:totale(?:\s+(?:soggiorno|prezzo))?|prezzo\s+totale|total(?:\s+price)?|for\s+\d+\s+nights?|per\s+\d+\s+nott[ei])\b/i.test(context);
      const isNightly=/\b(?:a|per)\s+notte\b|\bper\s+night\b|\bnightly\b|\bprezzo\s+a\s+notte\b/i.test(after.slice(0,45))||
        /\b(?:a|per)\s+notte\s*$/i.test(before);
      const isOld=/\b(?:prezzo originale|prezzo barrato|original price|was)\b/i.test(before.slice(-45));
      const explicitNights=context.match(/\b(?:per|for)\s+(\d{1,2})\s+(?:nott[ei]|nights?)\b/i);
      if(!isStay||isNightly||isOld||(explicitNights&&nights&&Number(explicitNights[1])!==nights))continue;
      candidates.push({amount:value});
    }
  }
  const distinct=[...new Set(candidates.map(item=>item.amount))];
  const rooms=[];
  if(nights>0&&guests>0&&distinct.length===1){
    rooms.push({
      roomType:"Intero alloggio · "+(propertyName||"Vrbo").slice(0,115),
      total:distinct[0],board:"Non chiaro",refund:"Non chiaro",
      taxes:"Non chiaro",confidence:"total-for-stay"
    });
  }
  const imgUrls=new Set(),photoAlts=new Set();
  for(const img of [...document.querySelectorAll("img")].filter(visible).slice(0,300)){
    const w=Number(img.naturalWidth||img.width||0),h=Number(img.naturalHeight||img.height||0);
    if(w<180||h<120)continue;
    try{
      const source=String(img.currentSrc||img.src||"");
      if(!source||source.startsWith("data:"))continue;
      imgUrls.add(new URL(source,location.href).pathname);
    }catch{continue;}
    const alt=String(img.alt||"").trim();
    if(alt.length>4&&alt.length<140)photoAlts.add(alt);
  }
  const features=[
    ["Piscina",/\bpiscina\b|\bpool\b/i],["Wi-Fi",/\bwi-?fi\b/i],
    ["Parcheggio",/\bparcheggio\b|\bparking\b/i],
    ["Colazione",/\bcolazione\b|\bbreakfast\b/i],
    ["Aria condizionata",/\baria condizionata\b|\bair conditioning\b/i],
    ["Cucina",/\bcucina\b|\bkitchen\b/i]
  ].filter(([,r])=>r.test(pageText)).map(([name])=>name);
  const description=String(document.querySelector('meta[name="description"]')?.getAttribute?.("content")||"").trim().slice(0,450);
  const warning=rooms.length
    ?"Un totale soggiorno visibile acquisito. L'unità fisica, l'identità e le condizioni Booking vanno verificate."
    : !nights||!guests
      ?"Date oppure ospiti non verificabili nell'URL/pagina: nessun prezzo importabile."
      : distinct.length>1
        ?"Più importi di soggiorno differenti individuati: impossibile scegliere il totale senza ambiguità."
        :"Nessun totale soggiorno esplicito e attribuibile all'alloggio trovato. Non moltiplico il prezzo a notte.";
  return {
    schema:"velora-vrbo-visible-v1",pageTitle,propertyName,sourceUrl:safeUrl.toString(),
    checkin,checkout,nights,guests,rooms,
    presentation:{
      visibleImageCount:imgUrls.size,photoAltSamples:[...photoAlts].slice(0,15),
      visibleServices:features,descriptionExcerpt:description,roomCount:rooms.length,
      evidenceScope:"sample-of-visible-loaded-images-and-page-text"
    },
    capturedAt:new Date().toISOString(),warning
  };
}

function visibleHoliduCapture() {
  const host=location.hostname.toLowerCase();
  if(!/(^|\.)holidu\.(com|it|de|fr|es)$/.test(host))
    return {error:"La scheda aperta non appartiene a Holidu."};
  const pageText=String(document.body?.innerText||"").slice(0,50000);
  if(/accesso (?:temporaneamente )?limitato|access (?:temporarily )?limited|access denied|sei un robot|are you a robot|verify you are human|verifica che sei una persona|captcha/i.test(pageText.slice(0,3500)))
    return {error:"Holidu mostra una limitazione o una verifica. Il Companion non può superarla. Apri prima una normale scheda struttura accessibile."};
  const url=new URL(location.href);
  // Holidu partner links may redirect to another OTA. Never treat partner prices as Holidu.
  if(!/\/d\/\d+/.test(url.pathname))
    return {error:"Non è aperta una scheda alloggio Holidu verificabile (/d/...). Apri l'annuncio corretto, non i risultati di ricerca o un sito partner."};
  const safeUrl=new URL(url.origin+url.pathname);
  const paramsAllowed=new Set(["chkin","chkout","checkin","checkout","startDate","endDate","d1","d2","adults","guests","rm1","arrival","departure"]);
  for(const [key,val] of url.searchParams)if(paramsAllowed.has(key)&&val.length<70)safeUrl.searchParams.set(key,val);
  function iso(v) {
    const match=String(v||"").match(/20\d{2}-\d{2}-\d{2}/);
    if(!match)return "";
    const d=new Date(match[0]+"T00:00:00Z");
    return !Number.isNaN(d.getTime())&&d.toISOString().slice(0,10)===match[0]?match[0]:"";
  }
  const pickDate=keys=>{for(const key of keys){const value=iso(url.searchParams.get(key));if(value)return value;}return "";};
  const checkin=pickDate(["chkin","checkin","d1","startDate","arrival"]);
  const checkout=pickDate(["chkout","checkout","d2","endDate","departure"]);
  const nightDiff=checkin&&checkout?Math.round((Date.parse(checkout)-Date.parse(checkin))/86400000):0;
  const nights=nightDiff>=1&&nightDiff<=60?nightDiff:0;
  let guests=0;
  for(const key of ["adults","guests","rm1"]){
    const value=url.searchParams.get(key)||"";
    if(/^\d{1,2}$/.test(value)){guests=Number(value);break;}
    const match=value.match(/(?:^|,)a(\d{1,2})(?:,|$)/);
    if(match){guests=Number(match[1]);break;}
  }
  if(!guests){
    const match=pageText.slice(0,3500).match(/\b(\d{1,2})\s*(?:ospiti|viaggiatori|adulti|guests|travelers|adults)\b/i);
    if(match)guests=Number(match[1]);
  }
  const visible=e=>e instanceof Element&&e.getClientRects().length>0&&
    getComputedStyle(e).display!=="none"&&getComputedStyle(e).visibility!=="hidden";
  const title=(document.querySelector("h1")?.innerText||"").trim().replace(/\s+/g," ").slice(0,180);
  const pageTitle=String(document.title||"").trim().slice(0,240);
  const propertyName=/^(?:holidu|alloggi|sistemazioni|find your|results?)/i.test(title)||!title
    ? pageTitle.replace(/\s+[|–-]\s+Holidu.*$/i,"").slice(0,180)
    : title;
  const currencyPattern=/(?:€\s*(\d[\d.,\s]*\d|\d)|(\d[\d.,\s]*\d|\d)\s*€)/g;
  const parseEur=raw=>{
    let v=String(raw||"").replace(/\s/g,"");
    if(/[.,]/.test(v)){
      if(v.includes(".")&&v.includes(",")){
        const decimal=v.lastIndexOf(",")>v.lastIndexOf(".")?",":".";
        const thousands=decimal===","?".":",";
        v=v.split(thousands).join("").replace(decimal,".");
      } else if(/^[\d]+[.,]\d{3}$/.test(v))v=v.replace(/[.,]/g,"");
      else v=v.replace(",",".");
    }
    const amount=Number(v);
    return Number.isFinite(amount)&&amount>=1&&amount<=200000?amount:null;
  };
  const candidates=[];
  const priceNodes=[...document.querySelectorAll("div,span,p,strong,b,section")].slice(0,7000);
  for(const node of priceNodes) {
    if(!visible(node))continue;
    const txt=String(node.innerText||"").trim().slice(0,310);
    if(!txt||txt.length>300)continue;
    if(!/€/.test(txt))continue;
    const matches=[...txt.matchAll(currencyPattern)];
    for(const match of matches){
      const value=parseEur(match[1]||match[2]);
      if(value===null)continue;
      const before=txt.slice(Math.max(0,match.index-90),match.index);
      const after=txt.slice(match.index+match[0].length,match.index+match[0].length+110);
      const context=(before+" "+after).toLowerCase();
      const isStay=/\b(?:totale(?:\s+(?:soggiorno|prezzo))?|prezzo\s+totale|total(?:\s+price)?|for\s+\d+\s+nights?|per\s+\d+\s+nott[ei])\b/i.test(context);
      const isNightly=/\b(?:a|per)\s+notte\b|\bper\s+night\b|\bnightly\b|\bprezzo\s+a\s+notte\b/i.test(after.slice(0,45))||
        /\b(?:a|per)\s+notte\s*$/i.test(before);
      const isOld=/\b(?:prezzo originale|prezzo barrato|original price|was)\b/i.test(before.slice(-45));
      const explicitNights=context.match(/\b(?:per|for)\s+(\d{1,2})\s+(?:nott[ei]|nights?)\b/i);
      if(!isStay||isNightly||isOld||(explicitNights&&nights&&Number(explicitNights[1])!==nights))continue;
      candidates.push({amount:value});
    }
  }
  const distinct=[...new Set(candidates.map(item=>item.amount))];
  if(/(?:prenota su|continua su|book on|continue on)\s+(?:booking|expedia|vrbo|airbnb)/i.test(pageText.slice(0,8000)))
    return {error:"Holidu rimanda a un'altra OTA. Nessuna tariffa attribuita a Holidu."};
  const rooms=[];
  if(nights>0&&guests>0&&distinct.length===1){
    rooms.push({
      roomType:"Intero alloggio · "+(propertyName||"Holidu").slice(0,115),
      total:distinct[0],board:"Non chiaro",refund:"Non chiaro",
      taxes:"Non chiaro",confidence:"total-for-stay"
    });
  }
  const imgUrls=new Set(),photoAlts=new Set();
  for(const img of [...document.querySelectorAll("img")].filter(visible).slice(0,300)){
    const w=Number(img.naturalWidth||img.width||0),h=Number(img.naturalHeight||img.height||0);
    if(w<180||h<120)continue;
    try{
      const source=String(img.currentSrc||img.src||"");
      if(!source||source.startsWith("data:"))continue;
      imgUrls.add(new URL(source,location.href).pathname);
    }catch{continue;}
    const alt=String(img.alt||"").trim();
    if(alt.length>4&&alt.length<140)photoAlts.add(alt);
  }
  const features=[
    ["Piscina",/\bpiscina\b|\bpool\b/i],["Wi-Fi",/\bwi-?fi\b/i],
    ["Parcheggio",/\bparcheggio\b|\bparking\b/i],
    ["Colazione",/\bcolazione\b|\bbreakfast\b/i],
    ["Aria condizionata",/\baria condizionata\b|\bair conditioning\b/i],
    ["Cucina",/\bcucina\b|\bkitchen\b/i]
  ].filter(([,r])=>r.test(pageText)).map(([name])=>name);
  const description=String(document.querySelector('meta[name="description"]')?.getAttribute?.("content")||"").trim().slice(0,450);
  const warning=rooms.length
    ?"Un totale soggiorno visibile acquisito. L'unità fisica, l'identità e le condizioni Booking vanno verificate."
    : !nights||!guests
      ?"Date oppure ospiti non verificabili nell'URL/pagina: nessun prezzo importabile."
      : distinct.length>1
        ?"Più importi di soggiorno differenti individuati: impossibile scegliere il totale senza ambiguità."
        :"Nessun totale soggiorno esplicito e attribuibile all'alloggio trovato. Non moltiplico il prezzo a notte.";
  return {
    schema:"velora-holidu-visible-v1",pageTitle,propertyName,sourceUrl:safeUrl.toString(),
    checkin,checkout,nights,guests,rooms,
    presentation:{
      visibleImageCount:imgUrls.size,photoAltSamples:[...photoAlts].slice(0,15),
      visibleServices:features,descriptionExcerpt:description,roomCount:rooms.length,
      evidenceScope:"sample-of-visible-loaded-images-and-page-text"
    },
    capturedAt:new Date().toISOString(),warning
  };
}


chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if(!["CAPTURE_VISIBLE_EXPEDIA","CAPTURE_VISIBLE_VRBO","CAPTURE_VISIBLE_HOLIDU","OPEN_THREE_OTA_TABS"].includes(request?.type)) return false;
  if(!sender.tab?.url?.startsWith("https://diegobh26.github.io/velora-autovalutazione/")) {
    sendResponse({ok:false,error:"Richiesta consentita solo da Velora online."});
    return false;
  }
  if(request.type==="OPEN_THREE_OTA_TABS") {
    // Fixed, trusted homepages only. No caller-supplied URL, credentials or
    // automated browsing. chrome.tabs.create is not subject to popup blocking.
    (async()=>{
      const urls=["https://www.expedia.it/","https://www.vrbo.com/it-it/","https://www.holidu.it/"];
      let count=0;
      for(const url of urls){
        const options={url,active:false};
        if(Number.isInteger(sender.tab?.windowId))options.windowId=sender.tab.windowId;
        const tab=await chrome.tabs.create(options);
        if(!tab?.id)throw Error("Chrome non ha confermato l'apertura della scheda.");
        count+=1;
      }
      sendResponse({ok:true,count});
    })().catch(error=>sendResponse({ok:false,error:String(error?.message||error).slice(0,240)}));
    return true;
  }
  (async()=>{
    const vrbo=request.type==="CAPTURE_VISIBLE_VRBO";
    const holidu=request.type==="CAPTURE_VISIBLE_HOLIDU";
    const tabUrls=holidu
      ? ["https://*.holidu.it/*","https://*.holidu.com/*","https://*.holidu.de/*","https://*.holidu.fr/*","https://*.holidu.es/*"]
      : vrbo
      ? ["https://*.vrbo.com/*","https://*.vrbo.co.uk/*","https://*.vrbo.de/*","https://*.vrbo.fr/*","https://*.vrbo.es/*","https://*.vrbo.it/*"]
      : ["https://*.expedia.it/*","https://*.expedia.com/*",
         "https://*.expedia.de/*","https://*.expedia.fr/*",
         "https://*.expedia.es/*","https://*.expedia.co.uk/*"];
    const tabs=await chrome.tabs.query({url:tabUrls});
    const targets=tabs.filter(tab=>tab.id&&tab.url?.startsWith("https://")&&
      (holidu ? /\/d\/\d+/.test(new URL(tab.url).pathname)
        : vrbo ? /\/pdp\/|\/\d+(?:ha|vb|vr)?\/?$|\/vacation-rental\/|\/holiday-rental\//i.test(new URL(tab.url).pathname)
        : !/\/(?:hotel-search|search)\b/i.test(new URL(tab.url).pathname)))
      .sort((a,b)=>(b.lastAccessed||0)-(a.lastAccessed||0));
    if(!targets.length) throw Error(holidu
      ? "Nessuna scheda alloggio Holidu (/d/...) aperta. Apri l'annuncio corretto, non la pagina di ricerca."
      : vrbo ? "Nessuna scheda alloggio Vrbo aperta. Apri l'annuncio corretto, non la pagina di ricerca."
      : "Apri prima la pagina delle camere Expedia nel tuo Chrome normale.");
    const executed=await chrome.scripting.executeScript({
      target:{tabId:targets[0].id},
      func:holidu?visibleHoliduCapture:vrbo?visibleVrboCapture:visibleExpediaCapture
    });
    const payload=executed?.[0]?.result;
    if(!payload||payload.error) throw Error(payload?.error||"Impossibile leggere le camere visibili.");
    sendResponse({ok:true,payload});
  })().catch(error=>sendResponse({
    ok:false,error: String(error?.message||error).slice(0,280)
  }));
  return true;
});
