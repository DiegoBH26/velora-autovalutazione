// Prevent another property's listing from appearing as this structure's rate.
// Execute the REAL App.tsx guards through TypeScript transpilation in a VM.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const ts=require("typescript");
const app=fs.readFileSync(path.join(__dirname,"..","src/App.tsx"),"utf8");
const start=app.indexOf("const PILOT_GENERIC_PROPERTY_TOKENS");
const end=app.indexOf("function pilotComparisonEvidence(",start);
assert.ok(start>0&&end>start,"Identity helper block must exist");
const compiled=ts.transpileModule(app.slice(start,end),{compilerOptions:{
  target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.None
}}).outputText;
const sandbox={Set,Array,String,Boolean,Number};
vm.createContext(sandbox);
vm.runInContext(compiled+"\nthis.reject=pilotWrongListingReason;this.eligible=pilotEligiblePriceObservations;",sandbox);
const wrong={
  otaId:"airbnb",month:"2027-08",checkin:"2027-08-01",checkout:"2027-08-04",
  title:'Masseria TENUTA DESERTO "LA ROVERELLA"',
  status:"quote_candidates_unverified",
  quotes:[{roomType:'Masseria TENUTA DESERTO "LA ROVERELLA"',total:990,verified:false}]
};
const booking={
  otaId:"booking",month:"2027-09",checkin:"2027-09-26",checkout:"2027-09-29",
  title:"Masseria Tenuta Specolizzi",status:"quote_candidates",
  quotes:[{roomType:"Camera Classic",total:585,verified:true}]
};
const foundSame={
  otaId:"airbnb",month:"2027-08",checkin:"2027-08-01",checkout:"2027-08-04",
  title:"Tenuta Specolizzi - Intera casa",status:"quote_candidates",
  quotes:[{roomType:"Casa Tenuta Specolizzi",total:700,verified:false}]
};
const result={
  propertyId:"tenuta-speculizzi-salve",
  propertyName:"Masseria Tenuta Specolizzi",
  observations:[wrong,booking,foundSame]
};
assert.match(sandbox.reject(result,wrong),/Identità non coerente/);
assert.equal(sandbox.reject(result,booking),"");
assert.equal(sandbox.reject(result,foundSame),"");
const safe=sandbox.eligible(result);
assert.equal(safe.length,2);
assert.equal(safe.some(row=>row===wrong),false);
assert.equal(safe.some(row=>row===booking),true);
assert.equal(safe.some(row=>row===foundSame),true);
assert.equal(sandbox.eligible({...result,observations:[{...booking,status:"wrong_property_listing"}]}).length,0);
assert.equal(sandbox.eligible({...result,observations:[{...booking,identityQuarantined:true}]}).length,0);
assert.ok(app.includes('pilotEligiblePriceObservations(browserPilotResult).flatMap('));
assert.ok(app.includes('const pilotQuoteRows = pilotEligiblePriceObservations('));
assert.ok(app.includes('const observed = pilotEligiblePriceObservations('));
assert.ok(app.includes('ANNUNCIO ESTRANEO SCARTATO'));
assert.ok(app.includes('if(rejected.length&&!hasMatchingObservation)'));
console.log("Correct Booking rates retained; unrelated Masseria Tenuta Deserto €990 quarantined in all pricing views.");
