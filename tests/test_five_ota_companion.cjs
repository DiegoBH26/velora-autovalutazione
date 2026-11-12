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
  const roomTitle=new MockElement("h3","Camera Deluxe matrimoniale con bagno e vista giardino");
  const card=new MockElement("article","Camera Deluxe matrimoniale con bagno e vista giardino\n€ 420 per 3 notti",[roomTitle]);
  const root=new MockElement("main",card.innerText,[card]);
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
console.log("Companion 0.4.4: Hotels/Travelocity date+guest and source-safe visible totals; blockers/redirects/search rejected.");
