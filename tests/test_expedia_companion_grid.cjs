// Runtime regression fixture: reproduces Expedia's room grid with no "Book" buttons.
// Uses only built-in Node.js modules and a minimal visible-DOM model.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"..","chrome-companion-expedia","background.js"),"utf8");

class MockElement {
  constructor(tag, text, children=[]) {
    this.tag=tag; this.innerText=text; this.children=children;
    for (const child of children) child.parentElement=this;
  }
  getClientRects(){return [1];}
  querySelectorAll(selector) {
    const headings=[];
    const search=node=>{
      for (const child of node.children) {
        if (/h2,h3,h4,h5/.test(selector) && child.tag==="h3") headings.push(child);
        search(child);
      }
    };
    search(this);
    return headings;
  }
}

function runCapture(cards, options={}) {
  const roomHeadings=cards.map(card=>new MockElement("h3",card.title));
  const roomCards=cards.map((card,index)=>new MockElement("article",
    [card.title,card.description||"1 letto matrimoniale, bagno privato, colazione inclusa",
      card.prices].join("\n"),[roomHeadings[index]]));
  const docRoot=new MockElement("main",roomCards.map(card=>card.innerText).join("\n"),roomCards);
  const heading=new MockElement("h1","Scegli la tua camera");
  const sandbox={
    location:{
      hostname:"www.expedia.it",
      href:options.url||"https://www.expedia.it/Hotel-Search?startDate=2027-06-07&endDate=2027-06-09&adults=2"
    },
    document:{
      body:{innerText:"Scegli la tua camera\n7 giu\n9 giu\n2 persone, 1 camera\n"+docRoot.innerText},
      title:"Masseria Tenuta Specolizzi | Expedia",
      querySelectorAll(selector){
        if (/button,\[role=button\]/.test(selector)) return [];
        return docRoot.querySelectorAll(selector);
      },
      querySelector(selector){return selector==="h1"?heading:null;}
    },
    Element:MockElement,
    getComputedStyle:()=>({display:"block",visibility:"visible"}),
    chrome:{runtime:{onMessage:{addListener:()=>{}}}},
    URL
  };
  vm.createContext(sandbox);
  vm.runInContext(source+"\nthis.capture=visibleExpediaCapture;",sandbox);
  return sandbox.capture();
}

const result=runCapture([
  {title:"Doppia Classic, 1 camera da letto, bagno privato, vista giardino",prices:"€ 320 per 2 notti"},
  {title:"Camera, edificio separato (Trullo)",prices:"€ 410 per 2 notti"},
  {title:"Camera Superior, 1 letto king, bagno privato, vista giardino",prices:"€ 530 per 2 notti"}
]);
assert.equal(result.rooms.length,3,"Three unique Expedia rooms should be read with no booking buttons");
assert.deepEqual(Array.from(result.rooms,r=>r.total),[320,410,530]);
assert.equal(result.checkin,"2027-06-07");
assert.equal(result.checkout,"2027-06-09");
assert.equal(result.nights,2);
assert.equal(result.guests,2);
assert.equal(result.rooms[0].roomType,"Doppia Classic, 1 camera da letto, bagno privato, vista giardino");
assert.ok(result.rooms.every(room=>room.confidence==="total-for-stay"));

const noTotal=runCapture([
  {title:"Doppia Classic, bagno privato",prices:"€ 160 a notte"},
  {title:"Camera Superior, bagno privato",prices:"Prezzi non disponibili"}
]);
assert.equal(noTotal.rooms.length,0,"Do not infer a stay total from nightly pricing");
assert.match(noTotal.warning,/2 titoli di camera visibili/);
assert.match(noTotal.warning,/Scorri fino alle tariffe/);

const mixedTotals=runCapture([
  {title:"Doppia Classic, bagno privato",prices:"€ 330 per 2 notti\n€ 420 per 2 notti"},
  {title:"Camera Superior, bagno privato",prices:"€ 470 per 2 notti"}
]);
assert.equal(mixedTotals.rooms.length,1,"Ambiguous totals on one card must not be guessed");
assert.equal(mixedTotals.rooms[0].roomType,"Camera Superior, bagno privato");
const discounted=runCapture([
  {title:"Doppia Classic, 1 camera da letto, bagno privato, vista giardino",
    prices:"45 € di sconto\n461 €\n416 €\nper 3 notti, 1 camera\n139 € a notte\ntasse e oneri inclusi"},
  {title:"Camera, edificio separato (Trullo)",
    prices:"51 € di sconto\n521 €\n470 €\nper 3 notti, 1 camera\n157 € a notte"},
  {title:"Camera Superior, 1 letto king, bagno privato, vista giardino",
    prices:"54 € di sconto\n554 €\n500 €\nper 3 notti, 1 camera\n167 € a notte"},
  {title:"Camera Deluxe, 1 letto king, vista giardino, sul cortile",
    prices:"56 € di sconto\n573 €\n517 €\nper 3 notti, 1 camera\n172 € a notte"},
  {title:"Suite Junior (Prestige)",
    prices:"60 € di sconto\n610 €\n550 €\nper 3 notti, 1 camera\n183 € a notte"},
  {title:"Camera familiare, 2 camere da letto, vista giardino",
    prices:"79 € di sconto\n797 €\n718 €\nper 3 notti, 1 camera\n239 € a notte"}
],{url:"https://www.expedia.it/Hotel-Search?startDate=2027-06-01&endDate=2027-06-04&adults=2"});
assert.equal(discounted.rooms.length,6,"Discount, crossed-out and nightly figures must not hide six current room totals");
assert.deepEqual(Array.from(discounted.rooms,r=>r.total),[416,470,500,517,550,718]);
assert.equal(discounted.nights,3);
assert.equal(discounted.guests,2);
assert.ok(discounted.rooms.every(r=>r.confidence==="total-for-stay"));

const onlyDiscount=runCapture([
  {title:"Camera Deluxe, bagno privato",prices:"45 € di sconto\n400 € a notte"}
]);
assert.equal(onlyDiscount.rooms.length,0,"A discount and a nightly figure do not establish a stay total");

console.log("Expedia Chrome Companion: card-grid fixture passed (3 rooms, no-nightly-inference, ambiguous total protection).");
