const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const worker=fs.readFileSync(path.join(__dirname,"..","chrome-companion-expedia","background.js"),"utf8");
const bridge=fs.readFileSync(path.join(__dirname,"..","chrome-companion-expedia","bridge.js"),"utf8");
const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,"..","chrome-companion-expedia","manifest.json"),"utf8"));

class Element { constructor(text){this.innerText=text;} getClientRects(){return [1];} }
function capture(prices,locationHref="https://www.holidu.it/d/12345?checkin=2027-06-07&checkout=2027-06-10&adults=2"){
  const url=new URL(locationHref),nodes=prices.map(x=>new Element(x));
  const h1=new Element("Villa sul mare con piscina");
  const sandbox={
    location:{hostname:url.hostname,href:url.toString()},
    document:{
      body:{innerText:"Villa sul mare con piscina\n2 ospiti\n"+prices.join("\n")},
      title:"Villa sul mare con piscina | Holidu",
      querySelector:q=>q==="h1"?h1:null,
      querySelectorAll:q=>q==="img"?[]:nodes
    },
    Element,getComputedStyle:()=>({display:"block",visibility:"visible"}),
    chrome:{runtime:{onMessage:{addListener:()=>{}}}},URL
  };
  vm.createContext(sandbox);
  vm.runInContext(worker+"\nthis.capture=visibleHoliduCapture;",sandbox);
  return sandbox.capture();
}
assert.equal(manifest.version,"0.4.0");
assert.ok(manifest.host_permissions.includes("https://*.holidu.it/*"));
assert.match(bridge,/CAPTURE_VISIBLE_HOLIDU/);
const valid=capture(["€ 450 per 3 notti, 1 alloggio","€ 150 a notte"]);
assert.equal(valid.schema,"velora-holidu-visible-v1");
assert.equal(valid.rooms.length,1);
assert.equal(valid.rooms[0].total,450);
assert.equal(valid.nights,3);
assert.equal(valid.guests,2);
assert.equal(capture(["€ 120 a notte"]).rooms.length,0);
assert.equal(capture(["€ 450 per 3 notti","€ 600 per 3 notti"]).rooms.length,0);
assert.match(capture(["€ 450 per 3 notti"],"https://www.holidu.it/search?checkin=2027-06-07&checkout=2027-06-10&adults=2").error,/scheda alloggio/);
assert.match(capture(["€ 450 per 3 notti","Continua su Booking per prenotare"]).error,/un'altra OTA/);
console.log("Holidu Companion v0.4: explicit total and safeguards passed");
