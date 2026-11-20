/**
 * Report consulenziale frontend — by BarbarHouse.
 * Four shareable A4 pages. Read-only: never infers reservations, availability,
 * verified prices, identity, attribution or review ratings from missing data.
 */
type PriceQuote = {
  roomType?:string;total?:number;nightlyRate?:number;currency?:string;
  nights?:number;verified?:boolean;guests?:number;
};
type Observation = {
  otaId:string;checkin?:string;checkout?:string;status?:string;
  title?:string;identityQuarantined?:boolean;identityUnverified?:boolean;quotes?:PriceQuote[];
};
type StoredQuote = {
  otaId:string;stayDate?:string;roomType?:string;total:number;nights:number;
  currency?:string;pilotVerified?:boolean;manualIdentityConfirmed?:boolean;
  origin?:string;
};
type Source = {status?:string;identityVerified?:boolean;presenceDetected?:boolean;candidateUrl?:string;url?:string};
type Pilot = {
  observations?:Observation[];
  discoveredSources?:Record<string,Source>;
  otaProfiles?:Record<string,{status?:string;rating?:number|null;ratingScale?:number|null;reviewCount?:number|null;url?:string}>;
  bookingEngine?:{status?:string;provider?:string;mode?:string;url?:string;evidence?:string;
    otaName?:string;otaUrl?:string;otaSourcePage?:string;clickVerified?:boolean};
  directBookingVerification?:{status?:string;navigation?:string;bookingFlow?:string;availability?:string;evidence?:string[]};
  siteTraffic?:{provider?:string;status?:string;domain?:string;scope?:string;estimateType?:string;visitsMonthlyEstimate?:number|null;wholeSiteVisits?:number|null;month?:string;confidence?:string;momChangePct?:number|null;note?:string;monthlyVisits?:Array<{month:string;visits:number}>;annualSummaries?:Array<{year:number;sumAvailableMonths:number;monthsAvailable:number;completeYear:boolean}>;sourcesPct?:Record<string,number>;bounceRatePct?:number|null;pagesPerVisit?:number|null;timeOnSiteSeconds?:number|null};
  directCommercialAudit?:{status?:string;searchedTotal?:number;plannedTotal?:number;
    verifiedQuotes?:unknown[];samples?:Array<{status?:string;searchSubmitted?:boolean;checkin?:string;checkout?:string}>};
  navigationAudit?:{status?:string;pagesVisited?:number;internalLinksSeen?:number;failedPages?:unknown[];evidence?:string};
  photoAudit?:{status?:string;score?:number;imageCount?:number;highResolutionCount?:number;
    strengths?:string[];gaps?:string[];actions?:string[]};
  reputation?:{status?:string;rating?:number|null;reviewCount?:number|null;sampleSize?:number;
    strengths?:Array<{theme:string;count?:number}>;weaknesses?:Array<{theme:string;count?:number}>};
  plan?:Array<{checkin?:string;checkout?:string}>;
};
type Distribution = {
  checkin:string;checkout:string;otaId:string;otaLabel:string;
  unitCount:number;maxUnitCount:number;finding:string;
};
type Area = {name:string;score:number;finding:string;action:string};
export type FrontendReportInput = {
  propertyName:string;city?:string;website?:string;consultant:string;
  generatedDate:string;generatedTime?:string;pilot?:Pilot|null;
  eligibleObservations:Observation[];wrongListingChannels:string[];
  rateQuotes:StoredQuote[];asymmetries:Distribution[];manualAbsentIds?:string[];
  bookingStatus:string;bookingProvider:string;bookingMode:string;
  opportunityScore?:number|null;assessedItemCount?:number;
  areas?:Area[];
};

const OTAS:[string,string][]=[
  ["booking","Booking.com"],["airbnb","Airbnb"],["agoda","Agoda"],
  ["expedia","Expedia"],["vrbo","Vrbo"],["holidu","Holidu"],
  ["hotels","Hotels.com"],["travelocity","Travelocity"],
  ["trip","Trip.com"],["priceline","Priceline"],
  ["tripadvisor","Tripadvisor"],["trivago","Trivago"],
  ["googlehotels","Google Hotels"],["holidaycheck","HolidayCheck"]
];

function clean(value:unknown):string {
  return String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;")
    .replaceAll(">","&gt;").replaceAll('"',"&quot;")
    .replaceAll("'","&#39;");
}
function text(value:unknown,fallback="Non verificato"):string {
  const val=String(value??"").trim();
  return val?clean(val):fallback;
}
function num(value:unknown):number|null {
  const n=Number(value);
  return value===null||value===undefined||value===""||!Number.isFinite(n)?null:n;
}
function euro(value:number):string {
  return new Intl.NumberFormat("it-IT",{minimumFractionDigits:0,maximumFractionDigits:2}).format(value);
}
function formatRange(values:number[],currency="EUR"):string {
  if(!values.length)return "—";
  const a=Math.min(...values),b=Math.max(...values);
  const symbol=currency==="EUR"?"€":"USD ";
  return symbol+euro(a)+(Math.abs(b-a)>0.009?" – "+symbol+euro(b):"");
}
type QuoteMark={nightly:number;currency:string;verified:boolean;key:string};
function collectRows(input:FrontendReportInput) {
  const pilot=input.pilot;
  const eligible=input.eligibleObservations||[];
  // Mostra le OTA effettivamente esaminate o con evidenze raccolte.
  // Non riempire il report del cliente con portali mai analizzati; ciò
  // lascia spazio a tariffe leggibili anche quando la scansione è parziale.
  const labels=new Map(OTAS);
  const ids=[...new Set([
    ...eligible.map(o=>o.otaId),
    ...Object.keys(pilot?.discoveredSources||{}),
    ...Object.keys(pilot?.otaProfiles||{}),
    ...(input.rateQuotes||[]).map(q=>q.otaId),
    ...(input.manualAbsentIds||[]),
    ...(input.wrongListingChannels||[]),
  ])].filter(id=>id && id!=="sito" && id!=="official_site" && id!=="google" && id!=="reviews")
    .sort((a,b)=>{
      const ai=OTAS.findIndex(([id])=>id===a),bi=OTAS.findIndex(([id])=>id===b);
      return (ai<0?100:ai)-(bi<0?100:bi);
    });
  return ids.map(id=>{
    const observations=eligible.filter(x=>x.otaId===id);
    const source=pilot?.discoveredSources?.[id];
    const profile=pilot?.otaProfiles?.[id];
    const marks:QuoteMark[]=[];
    // Separate observed from validated prices. Always compare nightly rate,
    // never a whole-stay quote against a price per night.
    for(const o of observations) {
      if(o.identityQuarantined)continue;
      for(const q of o.quotes||[]) {
        const nights=num(q.nights);
        const given=num(q.nightlyRate);
        const total=num(q.total);
        const nightly=given!==null&&given>0?given:
          total!==null&&total>0&&nights!==null&&nights>0?total/nights:null;
        if(nightly===null||nightly<=0||nightly>100000)continue;
        const currency=String(q.currency||"EUR").toUpperCase();
        marks.push({nightly,currency,verified:q.verified===true && o.identityUnverified!==true,
          key:[id,o.checkin,q.roomType,currency,Math.round(nightly*100)].join("|")});
      }
    }
    for(const q of input.rateQuotes||[]) {
      if(q.otaId!==id)continue;
      const total=num(q.total),nights=num(q.nights);
      if(total===null||total<=0||nights===null||nights<=0)continue;
      const nightly=total/nights;
      if(nightly<=0||nightly>100000)continue;
      const currency=String(q.currency||"EUR").toUpperCase();
      marks.push({nightly,currency,
        verified:q.pilotVerified===true && q.manualIdentityConfirmed!==false,
        key:[id,q.stayDate,q.roomType,currency,Math.round(nightly*100)].join("|")});
    }
    // Deduplicate a price acquired through the pilot and subsequently imported
    // into the rate log; keep verification if either observation was validated.
    const distinct=new Map<string,QuoteMark>();
    for(const mark of marks) {
      const prior=distinct.get(mark.key);
      distinct.set(mark.key,prior?{...mark,verified:prior.verified||mark.verified}:mark);
    }
    const unique=[...distinct.values()];
    const eur=unique.filter(q=>q.currency==="EUR");
    const verified=eur.filter(q=>q.verified).map(q=>q.nightly);
    const observed=eur.map(q=>q.nightly);
    const usd=unique.filter(q=>q.currency==="USD").map(q=>q.nightly);
    const blocked=observations.some(x=>/blocked|rate_limited|429|403|robots_denied|login_required/i.test(x.status||""));
    const wrong=(input.wrongListingChannels||[]).includes(id);
    const manualAbsent=(input.manualAbsentIds||[]).includes(id);
    const confirmed=unique.some(q=>q.verified) || source?.identityVerified===true ||
      (profile?.status==="sampled" && observations.length>0);
    const candidate=observations.length>0||Boolean(source?.candidateUrl||source?.presenceDetected||profile?.url);
    const missing=observations.some(o=>o.status==="source_missing"||o.status==="not_found");
    const presence=confirmed?"Rilevata":
      blocked?"Accesso limitato":
      manualAbsent?"Non rilevata dall'operatore":
      wrong?"Scheda estranea scartata":
      candidate?"Candidata: identità da verificare":
      missing?"Non individuata nel test":"Non verificata";
    const tariffStatus=verified.length?"Validata nel campione":
      observed.length?"Osservata, da verificare":
      usd.length?"Solo USD, non convertiti":"Nessun prezzo verificato";
    return {id,name:labels.get(id)||id,presence,tariffStatus,
      count:unique.length,verifiedCount:unique.filter(q=>q.verified).length,
      verifiedEuro:verified.length,observedEuro:observed.length,
      minVerified:verified.length?Math.min(...verified):null,
      maxVerified:verified.length?Math.max(...verified):null,
      euroRange:formatRange(verified.length?verified:observed),
      usdRange:usd.length?formatRange(usd,"USD"):"",
      observedOnly:!verified.length&&observed.length>0,
      asymmetry:(input.asymmetries||[]).filter(a=>a.otaId===id),
    };
  });
}
function rating(input:FrontendReportInput) {
  const profile=input.pilot?.otaProfiles?.booking;
  const b=num(profile?.rating),scale=num(profile?.ratingScale);
  if(profile?.status==="sampled"&&b!==null&&scale!==null&&scale>0&&b>0&&b<=scale) {
    return {number:b.toLocaleString("it-IT",{maximumFractionDigits:1}),
      max:scale.toLocaleString("it-IT"),source:"Booking.com",count:profile.reviewCount};
  }
  const g=input.pilot?.reputation;
  const v=num(g?.rating);
  if(g?.status==="sampled"&&v!==null&&v>0&&v<=5) {
    return {number:v.toLocaleString("it-IT",{maximumFractionDigits:1}),
      max:"5",source:"Google",count:g.reviewCount};
  }
  return {number:"n.d.",max:"",source:"Rating pubblico non verificato",count:null};
}
function cells(...columns:string[]) {return "<tr>"+columns.map(x=>"<td>"+x+"</td>").join("")+"</tr>";}
function table(headers:string[],rows:string[][],empty:string) {
  return "<table><thead><tr>"+headers.map(h=>"<th>"+clean(h)+"</th>").join("")+
    "</tr></thead><tbody>"+(rows.length?rows.map(r=>cells(...r)).join(""):
      '<tr><td colspan="'+headers.length+'">'+clean(empty)+"</td></tr>")+"</tbody></table>";
}

export function buildFrontendConsultingReportHtml(input:FrontendReportInput):string {
  const pilot=input.pilot;
  const rows=collectRows(input);
  const reviews=pilot?.reputation,photos=pilot?.photoAudit;
  const rateRows=rows.map(r=>[
    "<b>"+clean(r.name)+"</b>",
    r.euroRange==="—"?"—":(r.observedOnly?"<span class='muted'>"+clean(r.euroRange)+"*</span>":clean(r.euroRange)),
    String(r.count),String(r.verifiedCount),
    text(r.tariffStatus),
  ]);
  const presenceRows=rows.map(r=>[
    "<b>"+clean(r.name)+"</b>",clean(r.presence),
    String(r.count)+" ("+r.verifiedCount+" valid.)",
    r.asymmetry.length?clean(r.asymmetry[0].unitCount+" vs "+
      r.asymmetry[0].maxUnitCount+" unità con tariffa validata")+
      "<small>Date: "+clean(r.asymmetry[0].checkin+" → "+r.asymmetry[0].checkout)+"</small>":
      r.verifiedCount===0?"Confronto non determinabile":"Nessuna asimmetria dimostrata",
  ]);
  const asymmetries=(input.asymmetries||[]).slice(0,5).map(a=>[
    clean(a.otaLabel),clean(a.checkin+" → "+a.checkout),
    clean(a.unitCount+" su "+a.maxUnitCount),clean(a.finding).slice(0,500),
  ]);
  const channelsWithValid=rows.filter(r=>r.verifiedCount>0).length;
  const totalValidated=rows.reduce((n,r)=>n+r.verifiedCount,0);
  const withPresence=rows.filter(r=>r.presence==="Rilevata").length;
  const ratingBox=rating(input);
  const searched=pilot?.directCommercialAudit?.searchedTotal||0;
  const directStatus=pilot?.bookingEngine?.status||"non_verificato";
  const bookingToOta=directStatus==="ota_redirect";
  const otaDestination=pilot?.bookingEngine?.otaName||"OTA non identificata";
  const engineDetected=/^(?:found|present|detected|available|linked|verified|provider_identified)$/i.test(directStatus) ||
    Boolean(pilot?.bookingEngine?.url) ||
    input.bookingStatus==="present";
  const engineExplicitMissing=/not_found_in_page|request_only|missing/i.test(directStatus) ||
    input.bookingStatus==="missing";
  const engineText=bookingToOta
    ?"Nessun booking engine diretto · Prenota rimanda a "+otaDestination
    : engineDetected?"Percorso di prenotazione individuato":
    engineExplicitMissing?"Booking engine non rilevato nel percorso esaminato":
    "Presenza del booking engine da verificare";
  const siteStatus=searched>0?
    "Ricerche sulle date eseguite: "+searched+". Preventivi completi verificati: "+
    (pilot?.directCommercialAudit?.verifiedQuotes?.length||0)+".":
    bookingToOta?"Le prenotazioni vengono indirizzate a "+otaDestination+
      "; nessuna ricerca di tariffa diretta eseguita.":
    engineDetected?"Percorso aperto, ma ricerca date/ospiti non confermata.":
    "Percorso di prenotazione non verificato.";
  const traffic=pilot?.siteTraffic;
  const trafficVerified=traffic?.status==="estimated" && traffic.estimateType==="site" &&
    Number.isFinite(traffic.wholeSiteVisits) && Number(traffic.wholeSiteVisits)>0;
  const trafficLine=trafficVerified
    ? Number(traffic?.wholeSiteVisits).toLocaleString("it-IT")+" visite mensili stimate per il dominio "+
      (traffic?.domain||"")+(traffic?.month?" · mese di riferimento "+traffic.month:"")+
      (traffic?.confidence?" · confidenza dichiarata "+traffic.confidence:"")+". "+
      (traffic?.scope==="domain_not_property"
        ?"Dominio condiviso: il dato NON è attribuibile alla singola struttura."
        :"Stima esterna Vaneform, NON dato misurato da Google Analytics.")
    : traffic?.status==="not_configured"
      ?"Stima traffico non eseguita: collegamento gratuito Vaneform non configurato."
      : traffic?.status==="limit_reached"
        ?"Stima traffico non disponibile: limite del piano gratuito raggiunto."
        : "Nessuna stima affidabile delle visite mensili disponibile per questa struttura.";
  const trafficMonths=(trafficVerified?(traffic?.monthlyVisits||[]):[])
    .filter(entry=>/^20[0-9]{2}-(0[1-9]|1[0-2])$/.test(entry.month) &&
      Number.isFinite(entry.visits) && entry.visits>=0)
    .sort((a,b)=>a.month.localeCompare(b.month));
  const channelLabels:Record<string,string>={
    search:"Ricerca organica",direct:"Diretto",referrals:"Siti referenti",
    search_paid:"Ricerca a pagamento",display_ads:"Display",
    social:"Social",affiliate:"Affiliazioni",mail:"Email",gen_ai:"AI generativa",other:"Altri",
  };
  const trafficSources=(trafficVerified?Object.entries(traffic?.sourcesPct||{}):[])
    .filter(([,value])=>Number.isFinite(value)&&value>=0&&value<=100)
    .sort((a,b)=>b[1]-a[1]);
  const trafficMonthlyHtml=trafficMonths.length
    ?'<h3>Visite stimate mese per mese</h3><div class="traffic-mini-grid">'+
      trafficMonths.map(row=>'<div><span>'+clean(row.month)+'</span><b>'+row.visits.toLocaleString("it-IT")+'</b></div>').join("")+
      '</div>':"<p class='muted'>Storico mensile non disponibile dal provider.</p>";
  const annualTrafficHtml=(traffic?.annualSummaries||[]).map(year=>
    '<p><b>'+(year.completeYear?"Totale annuo":"Somma dei soli mesi disponibili")+
    ' '+clean(String(year.year))+': '+
    Number(year.sumAvailableMonths).toLocaleString("it-IT")+
    ' visite</b> · '+Number(year.monthsAvailable)+'/12 mesi'+
    (year.completeYear?"":". NON è un totale annuale completo")+'.</p>').join("");
  const trafficSourcesHtml=trafficSources.length
    ?'<h3>Origine stimata del traffico · '+clean(traffic?.month||"mese non dichiarato")+'</h3>'+
      '<div class="traffic-mini-grid">'+trafficSources.map(([name,share])=>
        '<div><span>'+clean(channelLabels[name]||name)+'</span><b>'+
        Number(share).toLocaleString("it-IT")+"%</b></div>").join("")+'</div>'
    :"<p class='muted'>Suddivisione per canale non disponibile.</p>";
  const trafficEngagement=[
    traffic?.timeOnSiteSeconds!=null?
      "Durata media "+Math.floor(traffic.timeOnSiteSeconds/60)+"m "+Math.round(traffic.timeOnSiteSeconds%60)+"s":"",
    traffic?.pagesPerVisit!=null?"Pagine/visita "+traffic.pagesPerVisit.toLocaleString("it-IT"):"",
    traffic?.bounceRatePct!=null?"Rimbalzo "+traffic.bounceRatePct.toLocaleString("it-IT")+"%":"",
  ].filter(Boolean).join(" · ");
  const nav=pilot?.navigationAudit;
  const failedPages=nav?.failedPages?.length||0;
  const siteUsability=nav?.pagesVisited?
    nav.pagesVisited+" pagine consultate. "+(failedPages?failedPages+" pagine con errori osservati.":
      "Nessuna pagina con errore rilevata nel campione."):
    "Non sono disponibili prove sufficienti per valutare la navigazione completa del sito.";
  const observationsCount=(pilot?.observations||[]).length;
  const dates=[...new Set((pilot?.observations||[]).map(o=>o.checkin).filter(Boolean))].sort();
  const dateScope=dates.length?dates[0]+(dates.length>1?" – "+dates[dates.length-1]:""):"Date non documentate";
  const photoStrengths=(photos?.strengths||[]).slice(0,2).join("; ");
  const photoGaps=(photos?.gaps||[]).slice(0,3).join("; ");
  const strengths=(reviews?.strengths||[]).slice(0,2).map(x=>x.theme).join("; ");
  const weaknesses=(reviews?.weaknesses||[]).slice(0,2).map(x=>x.theme).join("; ");
  const photoText=photos?[
    photos.imageCount!==undefined?photos.imageCount+" immagini rilevate":"Quantità di fotografie non misurata",
    photos.score!==undefined?"indice tecnico "+photos.score+"/10":"indice tecnico non disponibile",
    photoStrengths?"Aspetti positivi: "+photoStrengths+".":"",
    photoGaps?"Da migliorare: "+photoGaps+".":"",
  ].filter(Boolean).join(" · "):"Audit fotografico non disponibile.";
  const reviewText=reviews?.status==="sampled"?
    "Campione: "+(reviews.sampleSize||0)+" recensioni. "+
    (strengths?"Aspetti apprezzati: "+strengths+". ":"")+
    (weaknesses?"Temi critici ricorrenti: "+weaknesses+".":"Nessuna criticità ricorrente verificabile nel campione.") :
    "Analisi testuale delle recensioni non disponibile o insufficiente.";
  const summary=channelsWithValid?
    "Le rilevazioni documentano prezzi verificati su "+channelsWithValid+
    " OTA nel campione analizzato. "+(input.asymmetries.length?
      "Sono emerse differenze di tipologie visibili da approfondire. ":
      "Non sono dimostrate differenze di inventario con le evidenze disponibili. "):
    "Il campione attuale non contiene un numero sufficiente di tariffe OTA validate per formulare conclusioni sui prezzi. ";
  const actions:{title:string;finding:string;action:string}[]=[];
  if(engineDetected && searched===0)actions.push({
    title:"Verificare la ricerca sul sito diretto",
    finding:"Percorso di prenotazione individuato, ma date e ospiti non verificati.",
    action:"Eseguire una ricerca reale su una finestra disponibile, verificare camere, tariffa e riepilogo; registrare il primo preventivo valido."
  });
  if(engineExplicitMissing)actions.push({
    title:"Rendere verificabile il canale diretto",
    finding:"Booking engine non rilevato nel percorso pubblico consultato.",
    action:"Controllare la presenza e la visibilità della CTA Prenota, il collegamento al motore e l'accessibilità da desktop/mobile."
  });
  if(input.asymmetries.length)actions.push({
    title:"Verificare distribuzione e mapping OTA",
    finding:"Differenze nel numero di tipologie con tariffa confermata sulle stesse date.",
    action:"Confrontare disponibilità, mapping camere, minimum stay, chiusure e regole tariffarie nel channel manager."
  });
  if(rows.some(r=>r.presence==="Candidata: identità da verificare"||r.presence==="Scheda estranea scartata"))
    actions.push({title:"Confermare l'identità delle schede",
      finding:"Alcune OTA presentano annunci candidati o schede non pertinenti.",
      action:"Confrontare denominazione, indirizzo e foto prima di attribuire prezzi o segnalare un'assenza."});
  if(totalValidated===0)actions.push({title:"Consolidare i campioni tariffari",
    finding:"Non sono disponibili tariffe EUR validate per un confronto commerciale.",
    action:"Ripetere la ricerca su date e ospiti omogenei, confermare unità, condizioni, valuta e totale prima di calcolare delta."});
  if(photoGaps)actions.push({title:"Ottimizzare le fotografie",
    finding:photoGaps,
    action:"Verificare immagini di copertina, camere, bagni, esterni e servizi sul sito e sulle OTA; sostituire soltanto quelle insufficienti."});
  if(failedPages)actions.push({title:"Controllare la navigazione",
    finding:failedPages+" pagina/e con errori durante la scansione.",
    action:"Aprire i collegamenti interessati, verificare pagine e CTA e ripetere il controllo dopo le correzioni."});
  for(const a of input.areas||[]) {
    if(actions.length>=6)break;
    actions.push({title:a.name,finding:a.finding,action:a.action});
  }
  if(!actions.length)actions.push({title:"Completare la verifica comparabile",
    finding:"Non emergono criticità dimostrate dal campione attuale.",
    action:"Estendere le date campionate, confermare i preventivi e confrontare canali, fotografia e sito diretto con la struttura."});
  const priority=actions.slice(0,5);
  const priorityHtml=priority.map((a,i)=>
    '<div class="action"><span class="actionno">'+(i+1)+'</span><div><b>'+
    clean(a.title)+'</b><p>'+clean(a.finding)+'</p><small><strong>Intervento:</strong> '+
    clean(a.action)+'</small></div></div>').join("");
  const ratings=ratingBox.number==="n.d."?"<span class='no-rating'>Non rilevato</span>":
    '<span class="ratingvalue">'+clean(ratingBox.number)+'</span><span class="ratingscale">/'+clean(ratingBox.max)+'</span>';
  const page=(i:number,title:string,inner:string)=>
    '<section class="report-page"><div class="masthead"><div><span class="brand">BarbarHouse</span><small>CONSULENZA E DISTRIBUZIONE TURISTICA</small></div><div class="brandright">REPORT FRONTEND <b>Sezione '+i+' / 4</b></div></div>'+
    '<div class="page-title"><div class="eyebrow">SCRAPING FRONTEND · '+clean(input.propertyName)+'</div><h1>'+title+'</h1></div>'+
    '<div class="page-content">'+inner+'</div><footer><span>Scraping frontend · '+text(input.generatedDate)+' · by BarbarHouse</span><span>Sezione '+i+' / 4</span></footer></section>';
  const p1=
    '<div class="cover"><div><p class="lead">Analisi consulenziale delle evidenze pubbliche di sito diretto, OTA e reputazione.</p>'+
    '<div class="identity"><div><label>Struttura</label><b>'+text(input.propertyName)+'</b></div>'+
    '<div><label>Località</label><b>'+text(input.city,"Non indicata")+'</b></div>'+
    '<div><label>Consulente · account di esecuzione</label><b>'+text(input.consultant,"Non registrato per questa scansione")+'</b></div>'+
    '<div><label>Data di emissione del report</label><b>'+text(input.generatedDate)+' · '+text(input.generatedTime,"")+'</b></div></div></div>'+
    '<div class="ratingbox"><label>RATING PUBBLICO</label><div class="ratingchip">'+ratings+'</div><span>'+clean(ratingBox.source)+'</span>'+
    (num(ratingBox.count)!==null?'<small>'+ratingBox.count+' recensioni pubblicate</small>':'<small>Fonte e punteggio non verificabili nel campione</small>')+'</div></div>'+
    '<div class="stats"><div><label>OTA con tariffe validate</label><strong>'+channelsWithValid+'</strong></div>'+
    '<div><label>Tariffe validate</label><strong>'+totalValidated+'</strong></div>'+
    '<div><label>Campioni OTA osservati</label><strong>'+observationsCount+'</strong></div></div>'+
    '<h2>Valutazione generale</h2><div class="conclusion"><p>'+clean(summary)+
    (searched?" Sul sito diretto risultano "+searched+" ricerche effettivamente inviate.":" La ricerca commerciale sul sito diretto non è ancora confermata.")+
    '</p>'+(num(input.opportunityScore)!==null && (input.assessedItemCount||0)>0
      ? '<p><b>Indice di opportunità consulenziale:</b> '+input.opportunityScore+'/100 su '+
        input.assessedItemCount+' voci valutate. È una priorità di intervento interna, non un rating degli ospiti né un indice di qualità assoluta.</p>'
      : '<p>Indice di opportunità: non calcolabile senza voci valutate.</p>')+
    '<p>Questa è una lettura preliminare del frontend: non equivale a un audit gestionale o a una certificazione delle tariffe.</p></div>'+
    '<h2>Quadro immediato</h2><div class="two">'+
    '<div class="card"><label>Presenza sulle OTA</label><b>'+withPresence+' portali con riscontro confermato</b><p>Un annuncio non rilevato automaticamente non dimostra assenza definitiva.</p></div>'+
    '<div class="card"><label>Canale diretto</label><b>'+clean(engineText)+'</b><p>'+clean(siteStatus)+'</p></div>'+
    '<div class="card"><label>Copertura temporale</label><b>'+clean(dateScope)+'</b><p>Finestre campionate, non intera stagione.</p></div>'+
    '<div class="card"><label>Prossimo passo</label><b>'+clean(priority[0].title)+'</b><p>'+clean(priority[0].action)+'</p></div></div>'+ 
    ((input.areas||[]).length
      ? '<div class="minor"><b>Spunti dalle aree già valutate:</b> '+
        (input.areas||[]).slice(0,3).map(a=>clean(a.name)).join(' · ')+
        '. Da confermare con la direzione sulla base delle evidenze raccolte.</div>'
      : '');
  const p2=
    '<p class="lead">Range delle tariffe pubbliche effettivamente lette, normalizzate per notte. Il numero di osservazioni non indica tutte le disponibilità del portale.</p>'+
    '<h2>Tariffe minime e massime per OTA</h2>'+
    table(["Portale","Range EUR / notte","Tariffe lette","Validate","Attendibilità"],rateRows,
      "Nessun prezzo associabile con certezza alla struttura.")+
    '<div class="note"><b>Come leggere gli importi</b><p>Gli importi indicano prezzi pubblici osservati nel campione, non ADR venduto. Quando presenti tariffe validate, il range EUR usa soltanto quelle. <b>*</b> In assenza di tariffe validate, il range mostra dati osservati e non confrontabili. Le tariffe USD non sono convertite automaticamente in EUR. Date, ospiti, camera, condizioni, cancellazione e tasse possono differire.</p></div>'+
    (rows.some(r=>r.usdRange)?'<div class="minor"><b>Prezzi USD mantenuti nella valuta originale:</b> '+
      rows.filter(r=>r.usdRange).map(r=>clean(r.name)+": "+clean(r.usdRange)).join(" · ")+'</div>':"")+
    '<h2>Presenza OTA e asimmetrie</h2>'+
    table(["Portale","Presenza rilevata","Tariffe lette","Confronto visibile"],presenceRows,
      "Nessun riscontro OTA disponibile.")+
    '<p class="caveat">Per attestare un’asimmetria serve almeno un riferimento con stessa data, stesso numero di ospiti e tipologia effettivamente comparabile. «Non verificato» e «non rilevato» non significano «assente».</p>';
  const p3=
    '<div class="two"><div class="card"><label>BOOKING ENGINE</label><h3>'+clean(engineText)+'</h3>'+
    '<dl><dt>Fornitore</dt><dd>'+text(bookingToOta?"Nessun booking engine diretto rilevato":input.bookingProvider||pilot?.bookingEngine?.provider,"Da identificare")+'</dd>'+
    '<dt>Percorso</dt><dd>'+text(bookingToOta?"Pulsante Prenota → "+otaDestination:input.bookingMode||pilot?.bookingEngine?.mode,"Non verificato")+'</dd></dl>'+
    (bookingToOta?'<p>La destinazione OTA è distinta dai fornitori di booking engine come Kross Booking ed ErmesHotels. '+
      (pilot?.bookingEngine?.clickVerified?'Clic confermato.':'Link osservato nella pagina; clic non verificato.')+
      '</p><p class="muted">Origine: '+clean(pilot?.bookingEngine?.otaSourcePage||"non rilevata")+
      ' · Destinazione: '+clean(pilot?.bookingEngine?.otaUrl||"non rilevata")+'</p>':'')+
    '</div>'+
    '<div class="card"><label>FUNZIONAMENTO DELLA RICERCA</label><h3>'+clean(siteStatus)+'</h3>'+
    '<p>Un dominio raggiungibile o una CTA cliccabile non provano disponibilità, checkout o pagamento funzionanti.</p></div></div>'+
    '<h2>Traffico stimato del sito diretto</h2><div class="note"><p>'+clean(trafficLine)+'</p>'+
    (trafficVerified?trafficMonthlyHtml+annualTrafficHtml+trafficSourcesHtml+
      (trafficEngagement?'<p>'+clean(trafficEngagement)+'</p>':''):'')+
    '<p class="muted">Fonte: Vaneform. Stima del dominio, non visita certificata. Un mese assente non equivale a zero; il totale annuo si dichiara soltanto quando sono presenti 12 mesi.</p></div>'+
    '<h2>Usabilità del sito diretto</h2><div class="note">'+clean(siteUsability)+
    '<p>Verifiche consigliate: navigazione mobile, chiarezza della CTA «Prenota», selezione date, ospiti, preventivo finale e condizioni. Il checkout non è certificato dal solo scraping.</p></div>'+
    '<h2>Fotografie</h2><div class="card wide"><p>'+text(photoText)+'</p>'+
    '<p class="muted">L’indice fotografico è tecnico: non costituisce una valutazione estetica certificata.</p></div>'+
    '<h2>Reputazione online</h2><div class="card wide"><p>'+text(reviewText)+'</p>'+
    '<p class="muted">Solo recensioni pubbliche campionate. I temi non equivalgono a statistiche complete degli ospiti.</p></div>'+
    '<h2>Osservazioni operative</h2><p class="muted">Il confronto definitivo delle performance commerciali richiede accesso a PMS, channel manager, booking engine e dati storici della struttura: non è ricostruibile con certezza dal solo frontend.</p>';
  const p4=
    '<p class="lead">Sintesi delle differenze dimostrate e delle azioni verificabili più rapide. Le priorità sono circoscritte alle evidenze pubbliche disponibili.</p>'+
    '<h2>Asimmetrie realmente rilevate</h2>'+
    (asymmetries.length?
      table(["Portale","Date identiche","Tipologie visibili","Riscontro"],asymmetries,""):
      '<div class="note"><b>CONFRONTO NON DETERMINABILE oppure nessuna differenza dimostrata</b><p>I campioni disponibili non attestano un’asimmetria di inventario. Non significa automaticamente che tutti i canali abbiano identici prezzi e disponibilità.</p></div>')+
    '<h2>Interventi prioritari</h2><div class="actions">'+priorityHtml+'</div>'+
    '<div class="conclusion"><h3>Considerazione finale</h3><p>Il primo obiettivo è distinguere le reali opportunità commerciali da problemi di rilevazione. Le azioni proposte vanno validate con proprietà o direzione, confrontando le condizioni delle OTA e la reale operatività del canale diretto.</p></div>'+
    '<div class="note"><b>Proposta di approfondimento</b><p>Confronto operativo con la struttura: scelta di 2–3 priorità, verifica dei dati interni e definizione degli indicatori con cui misurare il miglioramento.</p></div>';
  const css=`
    @page{size:A4;margin:0}
    *{box-sizing:border-box}
    html,body{margin:0;background:#fff;color:#25364c;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.44}
    .report-page{min-height:297mm;height:auto;width:210mm;padding:13mm 14mm 12mm;display:flex;flex-direction:column;page-break-after:always;break-after:page;overflow:visible}
    .traffic-mini-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:4px 10px;margin:5px 0 9px}
    .traffic-mini-grid>div{display:flex;justify-content:space-between;gap:6px;padding:3px 0;border-bottom:1px solid #e7e7ed;font-size:10px}
    .traffic-mini-grid b{white-space:nowrap}
    .report-page:last-child{page-break-after:auto;break-after:auto}
    .masthead{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #152e4d;padding-bottom:10px}
    .brand{display:block;font-size:18px;letter-spacing:-.45px;color:#163456;font-weight:700}
    .masthead small{display:block;font-size:7px;letter-spacing:1px;color:#65758a}
    .brandright{font-size:8px;letter-spacing:1.1px;color:#3c526b;text-align:right}
    .brandright b{display:block;font-size:11px;color:#173858}
    .page-title{margin:15px 0 14px}.eyebrow{font-size:8.5px;letter-spacing:1.35px;color:#6b7890}
    h1{font-size:22px;color:#163456;line-height:1.17;margin:5px 0 0}
    h2{color:#173754;font-size:13px;margin:13px 0 7px;padding-bottom:5px;border-bottom:1px solid #ccdae7}
    h3{font-size:11px;line-height:1.3;color:#193550;margin:3px 0 8px}
    p{margin:5px 0 8px}.lead{font-size:12px;color:#51647a;margin:0 0 10px}.muted,small{font-size:9px;color:#5e6f82}
    .page-content{min-height:0;flex:1}
    .cover{display:grid;grid-template-columns:1fr 152px;gap:16px;align-items:start}
    .identity{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:9px 0}
    .identity div{border-bottom:1px solid #d5e0eb;padding-bottom:7px;min-height:34px}
    label,.card label,.ratingbox label,.stats label{font-size:8.3px;letter-spacing:.35px;color:#526c84;display:block;margin-bottom:3px}
    .identity b{color:#142e4d;font-size:10.5px}
    .ratingbox{border-radius:11px;background:#eaf1f7;border:1px solid #c1d3e2;text-align:center;padding:12px 10px}
    .ratingchip{display:inline-flex;align-items:baseline;justify-content:center;gap:4px;background:#073b77;color:#fff;border-radius:10px 10px 10px 2px;min-width:83px;min-height:67px;padding:11px;margin:5px 0}
    .ratingvalue{font-size:29px;font-weight:700;color:#fff}.ratingscale{font-size:13px;color:#edf5ff}
    .no-rating{font-size:13px;align-self:center;color:#fff}
    .ratingbox>span{display:block;font-size:10px;color:#173858}
    .ratingbox small{display:block;margin-top:4px}
    .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:12px 0 14px}
    .stats>div{border-radius:9px;background:#edf3f7;border:1px solid #d0deea;padding:10px}
    .stats strong{font-size:20px;color:#16426c}
    .two{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:10px 0}
    .card{border:1px solid #cbd9e6;border-radius:10px;padding:11px;background:#f8fafc;min-height:66px}
    .card b{color:#173754}.card p{margin:5px 0}.card.wide{min-height:auto;margin:7px 0}
    .conclusion{background:#eef4f8;border-left:4px solid #245478;padding:12px;border-radius:3px 8px 8px 3px}
    .conclusion p{margin:4px 0}
    .note{background:#f7f9fb;border-left:3px solid #7799b5;padding:10px 12px;margin:9px 0;border-radius:3px 7px 7px 3px}
    .note p{margin:4px 0}.minor{padding:5px 8px;font-size:9px;color:#52647a}
    .caveat{font-size:9px;color:#5c7086;margin-top:10px}
    table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:10px;margin:6px 0 8px}
    thead{display:table-header-group}tbody tr{break-inside:avoid;page-break-inside:avoid}
    th{background:#153957;color:#fff;text-align:left;font-size:9px;letter-spacing:.1px;padding:6px 7px}
    td{border-bottom:1px solid #d5e0e9;padding:6px 7px;vertical-align:top;overflow-wrap:anywhere}
    tbody tr:nth-child(even){background:#f1f5f9}
    td small{display:block;font-size:8px;margin-top:2px}td .muted{color:#596f84}
    dl{display:grid;grid-template-columns:70px 1fr;gap:5px;margin:8px 0}dt{color:#5b7185}dd{margin:0;color:#18364f;overflow-wrap:anywhere}
    .actions{display:grid;grid-template-columns:1fr 1fr;gap:9px;margin:8px 0}
    .action{border:1px solid #cbdbe8;border-radius:10px;padding:9px 10px;display:grid;grid-template-columns:22px 1fr;gap:8px;break-inside:avoid}
    .actionno{display:grid;place-items:center;border-radius:50%;width:22px;height:22px;background:#183b5b;color:#fff;font-size:10px}
    .action b{display:block;color:#1c3c5a;font-size:10.5px}.action p{font-size:10.5px;margin:4px 0}.action small{font-size:9.5px;line-height:1.4}
    footer{margin-top:auto;border-top:1px solid #cbd7e4;padding-top:9px;display:flex;justify-content:space-between;color:#65778a;font-size:8.5px;gap:10px}
    @media print{body{-webkit-print-color-adjust:exact;print-color-adjust:exact}.report-page{page-break-after:always;break-after:page}}
  `;
  return "<!doctype html><html lang='it'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"+
    "<title>Scraping frontend · "+clean(input.propertyName)+" · by BarbarHouse</title><style>"+css+"</style></head><body>"+
    page(1,"Quadro generale e rating",p1)+page(2,"Tariffe e distribuzione OTA",p2)+
    page(3,"Sito diretto, immagini e recensioni",p3)+page(4,"Asimmetrie e priorità consulenziali",p4)+
    "</body></html>";
}
