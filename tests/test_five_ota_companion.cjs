// Five-OTA Companion regression: Hotels.com / Travelocity read-only page scope.
"use strict";
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"..","chrome-companion-expedia","background.js"),"utf8");

class MockElement {
  constructor(tag,text,children=[]) {
    this.tag=tag; this.innerText=text; this.children=children;
    for(const child of children)child.parentElement=this;
  }
  getClientRects(){return [1];}
  querySelectorAll(selector){
    const matches=[];
    const walk=node=>{
      for(const child of node.children){
        if(/h2,h3,h4,h5/.test(selector)&&child.tag==="h3")matches.push(child);
        walk(child);
      }
    };
    walk(this);
    return matches;
  }
}

function capture(portal,url,options={}){
  const hostname=new URL(url).hostname;
  const fixtures=options.rooms||[{
    title:"Camera Deluxe matrimoniale con bagno e vista giardino",
    prices:"€ 420 per 3 notti"
  }];
  const cards=fixtures.map(fixture=>{
    const heading=new MockElement("h3",fixture.title);
    return new MockElement("article",fixture.title+"\n"+fixture.prices,[heading]);
  });
  const root=new MockElement("main",cards.map(card=>card.innerText).join("\n"),cards);
  const h1=new MockElement("h1","Scegli la tua camera");
  const sandbox={
    location:{hostname,href:url,pathname:new URL(url).pathname},
    document:{
      body:{innerText:options.body||"Scegli la tua camera\n2 adulti\n"+root.innerText},
      title:options.title||"Masseria Tenuta Specolizzi | Hotels",
      querySelectorAll(selector){
        if(/button,\[role=button\]/.test(selector))return [];
        return root.querySelectorAll(selector);
      },
      querySelector(selector){return selector==="h1"?h1:null;}
    },
    Element:MockElement,
    getComputedStyle:()=>({display:"block",visibility:"visible"}),
    chrome:{runtime:{onMessage:{addListener:()=>{}}}},
    URL
  };
  vm.createContext(sandbox);
  vm.runInContext(source+"\nthis.reader=visibleExpediaCapture;",sandbox);
  return sandbox.reader(portal);
}

const hotels="https://it.hotels.com/ho563394/masseria-tenuta-specolizzi-salve-italia/?chkin=2027-06-01&chkout=2027-06-04&rm1=a2";
const travelocity="https://www.travelocity.com/Salve-Hotels-Masseria-Tenuta-Specolizzi.h13064344.Hotel-Information?chkin=2027-06-01&chkout=2027-06-04&rm1=a2";
for(const [portal,url] of [["hotels",hotels],["travelocity",travelocity]]) {
  const result=capture(portal,url);
  assert.equal(result.schema,"velora-"+portal+"-visible-v1");
  assert.equal(result.checkin,"2027-06-01");
  assert.equal(result.checkout,"2027-06-04");
  assert.equal(result.guests,2);
  assert.equal(result.nights,3);
  assert.equal(result.rooms.length,1);
  assert.equal(result.rooms[0].total,420);
  assert.equal(result.rooms[0].confidence,"total-for-stay");
  assert.equal(new URL(result.sourceUrl).hostname,new URL(url).hostname);
  const blocked=capture(portal,url,{body:"Sei un robot? Verifica di sicurezza."});
  assert.match(blocked.error||"",/blocco/i);
  const redirect=capture(portal,"https://www.expedia.it/Hotel-Search?chkin=2027-06-01");
  assert.match(redirect.error||"",/non appartiene/i);
}
assert.match(capture("hotels","https://it.hotels.com/Hotel-Search?chkin=2027-06-01").error||"",/pagina della struttura/i);
assert.match(capture("travelocity","https://www.travelocity.com/Hotel-Search?chkin=2027-06-01").error||"",/scheda dell'hotel/i);
// Realistic 1–4 Jun 2027 Travelocity room cards: the crossed-out value and
// nightly quote are NOT the stay total. Prices are visibly in USD.
const english=capture("travelocity",travelocity,{rooms:[
  {title:"Classic Double Room, 1 Bedroom, Private Bathroom, Garden View",
   prices:"10% off\n$136 nightly\n$514\n$461 total\nTotal with taxes and fees\nReserve"},
  {title:"Room, Annex Building (Trullo)",
   prices:"10% off\n$154 nightly\n$578\n$521 total\nTotal with taxes and fees\nReserve"},
  {title:"Superior Room, 1 King Bed, Private Bathroom, Garden View",
   prices:"10% off\n$164 nightly\n$614\n$554 total\nTotal with taxes and fees\nReserve"}
]});
assert.deepEqual(Array.from(english.rooms,room=>room.total),[461,521,554]);
assert.ok(english.rooms.every(room=>room.currency==="USD"));
assert.ok(english.rooms.every(room=>room.confidence==="total-for-stay"));
const nightlyOnly=capture("travelocity",travelocity,{rooms:[
  {title:"Classic Double Room",prices:"$136 nightly\n$514"}
]});
assert.equal(nightlyOnly.rooms.length,0,"Nightly and crossed-out without a stay total is not importable");
const ambiguous=capture("travelocity",travelocity,{rooms:[
  {title:"Classic Double Room",prices:"$461 total\n$471 total"}
]});
assert.equal(ambiguous.rooms.length,0,"Two different explicit totals must not be assigned arbitrarily");
console.log("Companion 0.4.5: Hotels/Travelocity currency-aware room totals, English 'total' after amount and false-price safeguards passed.");
