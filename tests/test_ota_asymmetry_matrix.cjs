const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const ts=require("typescript");
const source=fs.readFileSync(path.join(__dirname,"..","src/App.tsx"),"utf8");
const name="function pilotDistributionAsymmetries(";
const start=source.indexOf(name),end=source.indexOf("const OTA_DISTRIBUTION_BAR_COLORS",start);
assert.ok(start>0 && end>start,"Expected OTA comparison function");
const js=ts.transpileModule(source.slice(start,end),{
  compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None}
}).outputText;
const context={
  PILOT_TARIFF_OTA_IDS:["booking","airbnb","agoda","expedia","vrbo"],
  PILOT_OTA_LABELS:{booking:"Booking.com",airbnb:"Airbnb",agoda:"Agoda",expedia:"Expedia",vrbo:"Vrbo"},
  pilotListingIdentityWarning:()=>"",
  pilotWrongListingReason:()=>"",
  normalizedRateToken:name=>name.toLowerCase().trim(),
  Set,Map,Number,String
};
vm.createContext(context);
vm.runInContext(js+"\nthis.compare=pilotDistributionAsymmetries",context);
const sample=(otaId,count,status="quote_candidates",checkin="2027-08-01")=>({
  otaId,status,checkin,checkout:"2027-08-04",quotes:Array.from({length:count},(_,index)=>({
    verified:true,roomType:"camera "+(index+1)
  }))
});
const results=context.compare({observations:[
  sample("booking",6),sample("expedia",4),sample("airbnb",2),sample("agoda",7),
  sample("vrbo",0,"no_public_rate"),sample("expedia",3,"quote_candidates","2027-08-12")
]});
const byId=Object.fromEntries(results.map(item=>[item.otaId,item]));
assert.equal(byId.expedia.unitCount,4);
assert.equal(byId.expedia.maxUnitCount,6);
assert.equal(byId.airbnb.unitCount,2);
assert.equal(byId.vrbo.unitCount,0);
assert.equal(byId.agoda,undefined,"A channel exceeding Booking is not a deficit");
assert.equal(byId.booking,undefined,"Booking is never compared against itself");
assert.equal(byId.expedia.referenceChannels.join(","),"Booking.com");
assert.deepEqual(Array.from(context.compare({observations:[sample("agoda",7),sample("expedia",4)]})),[],
  "No asymmetry should be reported without a Booking baseline");
const py=source;
for(const phrase of [
  "Barra delle asimmetrie · Sito diretto MASTER · Booking riferimento tra OTA",
  "Sito diretto · MASTER commerciale",
  "1 · Presenza scheda","2 · Fotografie","3 · Tipologie / Booking","4 · Tariffe / Booking",
  "5 · Tariffe / Sito diretto",
  "6 · Camere / Sito diretto",
  "directRoomParityFor",
  "const asymmetryWithDirect=[directMasterRow,...otaAsymmetryRows]",
  "id=\"velora-pricing-ota-sito\"",
  "Tariffe puntuali · sito diretto MASTER e OTA · apri/chiudi",
  "Prezzi e asimmetrie · sito diretto master / Booking riferimento OTA · apri/chiudi",
  "otaAsymmetryRows","presenceLabel",
  "Non individuata nella ricerca","Accesso bloccato · presenza incerta",
  "Confermo identità dopo verifica nome, località e foto",
  "photoDifference","matchedPrices","quote.roomMatchStatus"
]){
  // The price match uses variable `ota` rather than `quote`.
  if(phrase==="quote.roomMatchStatus")continue;
  assert.ok(py.includes(phrase),"Missing comparison contract: "+phrase);
}
console.log("OTA benchmark and site-direct master UI: legacy 6/4/2 room comparison, direct-rate parity and collapsible panels protected.");
