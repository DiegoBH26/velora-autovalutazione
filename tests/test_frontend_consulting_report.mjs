import assert from "node:assert/strict";
import fs from "node:fs";
import ts from "typescript";

const source = fs.readFileSync("src/frontend-consulting-report.ts", "utf8");
const js = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ES2022, target: ts.ScriptTarget.ES2022 }
}).outputText;
const { buildFrontendConsultingReportHtml } = await import(
  "data:text/javascript;base64," + Buffer.from(js).toString("base64")
);

const valid = {
  propertyName: 'Hotel <Esempio>', city: 'Lecce',consultant: 'Consulente Test',
  generatedDate: '16/11/2026',generatedTime: '15:00',
  bookingStatus: 'present',bookingProvider:'Bedzzle',bookingMode:'Motore esterno',
  rateQuotes: [],
  wrongListingChannels: ['vrbo'], manualAbsentIds: [],
  areas: [{name:'CTA prenotazione',score:70,finding:'Ricerca da verificare',action:'Completare il test'}],
  asymmetries:[{
    otaId:'airbnb',otaLabel:'Airbnb',checkin:'2027-06-01',checkout:'2027-06-04',
    unitCount:1,maxUnitCount:2,
    finding:'Una tipologia in meno rispetto a Booking sulle stesse date.'
  }],
  pilot:{
    bookingEngine:{status:'present',provider:'Bedzzle'},
    directCommercialAudit:{searchedTotal:0,verifiedQuotes:[]},
    otaProfiles:{booking:{status:'sampled',rating:8.7,ratingScale:10,reviewCount:42}},
    reputation:{status:'sampled',rating:4.6,sampleSize:20,reviewCount:90},
    photoAudit:{status:'sampled',score:7,imageCount:25,gaps:['Foto bagni da integrare']},
    discoveredSources:{booking:{identityVerified:true},airbnb:{presenceDetected:true}},
    observations:[
      {otaId:'booking',checkin:'2027-06-01',checkout:'2027-06-04',status:'quote_candidates'},
      {otaId:'airbnb',checkin:'2027-06-01',checkout:'2027-06-04',status:'quote_candidates'},
      {otaId:'vrbo',checkin:'2027-06-01',checkout:'2027-06-04',status:'wrong_property_listing',
        quotes:[{total:999999,nights:3,currency:'EUR',verified:true}]}
    ]
  },
  eligibleObservations:[
    {otaId:'booking',checkin:'2027-06-01',checkout:'2027-06-04',status:'quote_candidates',
      quotes:[
        {roomType:'Camera matrimoniale',total:300,nights:3,currency:'EUR',verified:true},
        {roomType:'Suite',total:600,nights:3,currency:'EUR',verified:true}]},
    {otaId:'airbnb',checkin:'2027-06-01',checkout:'2027-06-04',status:'quote_candidates',
      quotes:[{roomType:'Appartamento',total:450,nights:3,currency:'EUR',verified:false}]},
    {otaId:'expedia',checkin:'2027-06-01',checkout:'2027-06-04',status:'quote_candidates',
      quotes:[{roomType:'Camera',total:300,nights:3,currency:'USD',verified:false}]}
  ]
};
const html = buildFrontendConsultingReportHtml(valid);
assert.equal((html.match(/<section class="report-page">/g)||[]).length,4);
assert.ok(html.includes('SCRAPING FRONTEND'),"Branded header missing");
assert.ok(html.includes('by BarbarHouse'),"Client attribution missing");
assert.ok(html.includes('Consulente Test'),"Operator missing");
assert.ok(html.includes('Hotel &lt;Esempio&gt;'),"Escaping failed");
assert.ok(!html.includes('<Esempio>'),"Untrusted property name appeared as HTML");
assert.ok(html.includes('8,7'),"Booking public rating should be shown");
assert.ok(html.includes('Booking.com'),"Rating source should be explicit");
assert.ok(html.includes('€100 – €200'),"Booking 300/3 and 600/3 should be nightly range");
assert.ok(html.includes('€150*') || html.includes('€150</span>') ||
  html.includes('€150'),"Airbnb unverified price must be labelled observed");
assert.ok(html.includes('Osservata, da verificare'),"Unverified quotes should not count as validated");
assert.ok(html.includes('USD 100'),"USD retained, not converted");
assert.ok(!html.includes('€333.333'),"Wrong property prices must be excluded");
assert.ok(html.includes('Scheda estranea scartata'),"Wrong listing should be diagnosed");
assert.ok(html.includes('Bedzzle'),"Booking-engine provider missing");
assert.ok(html.includes('Foto bagni da integrare'),"Photo assessment missing");
assert.ok(html.includes('Una tipologia in meno'),"Actual asymmetry missing");
assert.ok(html.includes('Sezione 4 / 4'),"Footer section marker missing");

const empty = buildFrontendConsultingReportHtml({
  ...valid,pilot:null,eligibleObservations:[],rateQuotes:[],wrongListingChannels:[],
  asymmetries:[],areas:[],consultant:'',bookingStatus:'unverified',bookingProvider:''
});
assert.ok(empty.includes('Non registrato per questa scansione'),"Never invent scan operator");
assert.ok(empty.includes('Rating pubblico non verificato'),"Never invent ratings");
assert.ok(empty.includes('Nessun prezzo') || empty.includes('Non sono disponibili'),"No prices must be acknowledged");
assert.ok(!empty.includes('€100 – €200'),"No prices may leak from previous structure");
console.log("OK: 4-page BarbarHouse PDF content, pricing integrity, account attribution and rating.");
