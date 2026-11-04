// Reproduces a three-column Expedia room grid with titles and price footers separated.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"..","chrome-companion-expedia","background.js"),"utf8");
class Node {
  constructor(tag,body,rect,children=[]) {
    this.tag=tag;this.innerText=body;this.rect=rect;this.children=children;
    for(const c of children)c.parentElement=this;
  }
  getClientRects(){return [this.rect];}
  getBoundingClientRect(){return this.rect;}
  querySelectorAll(selector){
    const out=[];
    const matches=selector.includes("h2,h3,h4,h5")?(node=>node.tag==="h3"):
      selector.includes("div,span,p,strong,b")?(node=>["div","span","p","strong","b","section","article"].includes(node.tag)):
      (()=>false);
    const scan=node=>{for(const child of node.children){if(matches(child))out.push(child);scan(child);}};
    scan(this);return out;
  }
}
const rect=(x,y,w,h)=>({left:x,top:y,right:x+w,bottom:y+h,width:w,height:h});
const cards=[
  {title:"Doppia Classic, 1 camera da letto, bagno privato, vista giardino",amount:297,nightly:149},
  {title:"Camera, edificio separato (Trullo)",amount:335,nightly:168},
  {title:"Camera Superior, 1 letto king, bagno privato, vista giardino",amount:357,nightly:179}
];
const headings=[];
const prices=[];
for(let i=0;i<3;i++){
  const x=80+i*250,c=cards[i];
  headings.push(new Node("h3",c.title,rect(x,150,208,44)));
  prices.push(new Node("span",c.amount+" €\nper 2 notti, 1 camera\n"+c.nightly+" € a notte\ntasse e oneri inclusi",rect(x+110,415,96,75)));
}
// Nearest common ancestor contains three different headings: old extraction failed.
const titles=new Node("div","",rect(80,120,710,100),headings);
const footers=new Node("div","",rect(80,400,710,120),prices);
const grid=new Node("main","",rect(60,90,760,480),[titles,footers]);
const heading=new Node("h1","Scegli la tua camera",rect(80,30,200,30));
const sandbox={
  location:{hostname:"www.expedia.it",href:"https://www.expedia.it/Hotel-Search?startDate=2027-06-07&endDate=2027-06-09&adults=2"},
  document:{
    body:{innerText:"Scegli la tua camera\n7 giu\n9 giu\n2 persone, 1 camera\n"+headings.map(h=>h.innerText).join("\n")+prices.map(p=>p.innerText).join("\n")},
    title:"Masseria Tenuta Specolizzi | Expedia",
    querySelectorAll:selector=>grid.querySelectorAll(selector),
    querySelector:selector=>selector==="h1"?heading:null
  },
  Element:Node,getComputedStyle:()=>({display:"block",visibility:"visible"}),
  chrome:{runtime:{onMessage:{addListener:()=>{}}}},URL
};
vm.createContext(sandbox);
vm.runInContext(source+"\nthis.capture=visibleExpediaCapture;",sandbox);
const result=sandbox.capture();
assert.equal(result.rooms.length,3,"Each same-column room must get exactly one visible stay total");
assert.deepEqual(Array.from(result.rooms,r=>r.total),[297,335,357]);
assert.deepEqual(Array.from(result.rooms,r=>r.roomType),cards.map(c=>c.title));
assert.ok(result.rooms.every(r=>r.confidence==="total-for-stay"));
console.log("Expedia geometry fixture: 297/335/357 stay totals linked to correct rooms, nightly amounts excluded.");
