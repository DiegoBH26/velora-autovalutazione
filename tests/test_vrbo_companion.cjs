const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const code=fs.readFileSync(path.join(__dirname,"..","chrome-companion-expedia","background.js"),"utf8");
class Element {
  constructor(body,tag="div"){this.innerText=body;this.tag=tag;this.width=220;this.height=40;}
  getClientRects(){return [1];}
}
function capture(prices, href="https://www.vrbo.com/it-it/pdp/lo/42693330?chkin=2027-06-07&chkout=2027-06-10&adults=2") {
  const url=new URL(href);
  const panels=prices.map(price=>new Element(price));
  const h1=new Element("Casa vacanze con piscina nel Salento","h1");
  const body={innerText:"Casa vacanze con piscina nel Salento\n2 ospiti\n"+prices.join("\n")};
  const sandbox={
    location:{hostname:url.hostname,href:url.toString()},
    document:{
      body,title:"Casa vacanze con piscina nel Salento | Vrbo",
      querySelector:selector=>selector==="h1"?h1:selector.includes('meta[name="description"]')?null:null,
      querySelectorAll:selector=>selector==="img"?[]:panels
    },
    Element,getComputedStyle:()=>({display:"block",visibility:"visible"}),
    chrome:{runtime:{onMessage:{addListener:()=>{}}}},URL
  };
  vm.createContext(sandbox);
  vm.runInContext(code+"\nthis.capture=visibleVrboCapture;",sandbox);
  return sandbox.capture();
}
const valid=capture(["€ 450 per 3 notti, 1 alloggio","€ 150 a notte"]);
assert.equal(valid.schema,"velora-vrbo-visible-v1");
assert.equal(valid.checkin,"2027-06-07");
assert.equal(valid.checkout,"2027-06-10");
assert.equal(valid.guests,2);
assert.equal(valid.rooms.length,1);
assert.equal(valid.rooms[0].total,450);
const ambiguous=capture(["€ 450 per 3 notti","€ 600 per 3 notti"]);
assert.equal(ambiguous.rooms.length,0);
assert.match(ambiguous.warning,/differenti/);
const nightly=capture(["€ 150 a notte"]);
assert.equal(nightly.rooms.length,0);
assert.match(nightly.warning,/Nessun totale soggiorno/);
const undated=capture(["€ 450 per 3 notti"],"https://www.vrbo.com/it-it/pdp/lo/42693330?adults=2");
assert.equal(undated.rooms.length,0);
assert.match(undated.warning,/Date oppure ospiti/);
console.log("Vrbo Companion: explicit stay total 450, ambiguous quote, nightly-only and missing dates validated.");
