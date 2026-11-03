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
    const hits=[...cardText.matchAll(pricePattern)];
    const stayRe=/\bper\s+\d{1,2}\s+nott[ei]\b|\bfor\s+\d{1,2}\s+nights?\b/i;
    const results=[];
    for (const match of hits) {
      const amount=parseMoney(match[1]||match[2]);
      if (amount===null) continue;
      const before=cardText.slice(Math.max(0,match.index-35),match.index);
      const after=cardText.slice(match.index+match[0].length,match.index+match[0].length+85);
      const stay=stayRe.test(after)||stayRe.test(before);
      const nightly=/^(?:\s|[,;:])*a\s+notte|\bper\s+night\b/i.test(after);
      const crossed=/prezzo\s+(?:originale|barrato)/i.test(before);
      if (stay && !nightly && !crossed) results.push({amount,confidence:"total-for-stay",idx:match.index});
    }
    // Never guess a total from a single nightly figure or a crossed-out rate.
    if (results.length===0) return null;
    return results[0];
  }
  const invalidTitles=/^(?:prenota|book|scegli la tua camera|effettua un upgrade|il nostro prezzo più basso|questo è un prezzo standard|colazione inclusa|vista giardino|parcheggio incluso|scopri di più|wifi gratuito|paga più tardi)$/i;
  function roomTitle(node) {
    const nodes=[...node.querySelectorAll(
      '[data-stid*="room-name" i],[data-testid*="room-name" i],h2,h3,h4,h5,[role="heading"]'
    )].filter(isVisible);
    for (const element of nodes) {
      const value=(element.innerText||"").trim().replace(/\s+/g," ");
      if (value.length>=8&&value.length<=170&&!invalidTitles.test(value)&&!/\bprezzo|per \d+ nott|€/.test(value.toLowerCase())) return value;
    }
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
  const candidates=bookingButtons.map(cardFromButton).filter(Boolean);
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
    rooms,capturedAt:new Date().toISOString(),
    warning:rooms.length
      ? "Camere lette dal contenuto visibile. Identità e condizioni devono essere confermate prima di un confronto tariffario."
      : "Nessuna tariffa totale affidabile per camera: "+bookingButtons.length+
        " pulsanti camera riconosciuti, "+candidates.length+" schede con titolo e totale. "+
        "Verifica che la pagina mostri le camere e il totale per soggiorno. Nessun prezzo inventato."
  };
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if(request?.type !== "CAPTURE_VISIBLE_EXPEDIA") return false;
  if(!sender.tab?.url?.startsWith("https://diegobh26.github.io/velora-autovalutazione/")) {
    sendResponse({ok:false,error:"Richiesta consentita solo da Velora online."});
    return false;
  }
  (async()=>{
    const tabs=await chrome.tabs.query({url:[
      "https://*.expedia.it/*","https://*.expedia.com/*",
      "https://*.expedia.de/*","https://*.expedia.fr/*",
      "https://*.expedia.es/*","https://*.expedia.co.uk/*"
    ]});
    const targets=tabs.filter(tab=>tab.id&&tab.url?.startsWith("https://"))
      .sort((a,b)=>(b.lastAccessed||0)-(a.lastAccessed||0));
    if(!targets.length) throw Error("Apri prima la pagina delle camere Expedia nel tuo Chrome normale.");
    const executed=await chrome.scripting.executeScript({
      target:{tabId:targets[0].id},
      func:visibleExpediaCapture
    });
    const payload=executed?.[0]?.result;
    if(!payload||payload.error) throw Error(payload?.error||"Impossibile leggere le camere visibili.");
    sendResponse({ok:true,payload});
  })().catch(error=>sendResponse({
    ok:false,error: String(error?.message||error).slice(0,280)
  }));
  return true;
});
