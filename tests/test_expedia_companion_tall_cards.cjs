// Expedia 2027 room grid: tall cards, two rows, discounted rates,
// explicit "Prenota" links, and price footers separated from titles.
// This replicates DOM geometry that a 780px title-price cutoff misses.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const source=fs.readFileSync(path.join(__dirname,"..","chrome-companion-expedia","background.js"),"utf8");
class Node {
  constructor(tag,text,rect,children=[]) {
    this.tag=tag;this.innerText=text;this.rect=rect;this.children=children;
    for(const child of children)child.parentElement=this;
  }
  getClientRects(){return [this.rect];}
  getBoundingClientRect(){return this.rect;}
  querySelectorAll(selector){
    const matches=selector.includes("h2,h3,h4,h5")?(n=>n.tag==="h3"):
      selector.includes("button,[role=button],a[href]")?(n=>n.tag==="a"):
      selector.includes("div,span,p,strong,b")?(n=>["div","span","p","strong","b","section","article"].includes(n.tag)):
      (()=>false);
    const out=[];
    const walk=n=>{for(const child of n.children){if(matches(child))out.push(child);walk(child);}};
    walk(this);return out;
  }
}
const rect=(x,y,w,h)=>({left:x,top:y,right:x+w,bottom:y+h,width:w,height:h});
function capture(root){
  const heading=new Node("h1","Scegli la tua camera",rect(20,20,140,35));
  const sandbox={
    location:{hostname:"www.expedia.it",
      href:"https://www.expedia.it/Hotel-Search?startDate=2027-06-01&endDate=2027-06-04&adults=2"},
    document:{
      body:{innerText:"Scegli la tua camera\n2 persone\n"+root.innerText},
      title:"Masseria Tenuta Specolizzi | Expedia",
      querySelectorAll:selector=>root.querySelectorAll(selector),
      querySelector:selector=>selector==="h1"?heading:null
    },
    Element:Node,getComputedStyle:()=>({display:"block",visibility:"visible"}),
    chrome:{runtime:{onMessage:{addListener:()=>{}}}},URL
  };
  vm.createContext(sandbox);
  vm.runInContext(source+"\nthis.capture=visibleExpediaCapture;",sandbox);
  return sandbox.capture();
}
const entries=[
  ["Doppia Classic, 1 camera da letto, bagno privato",416,461,45,139],
  ["Camera, edificio separato (Trullo)",470,521,51,157],
  ["Camera Superior, 1 letto king, bagno privato",500,554,54,167],
  ["Camera Deluxe, 1 letto king, vista giardino",517,573,56,172],
  ["Suite Junior (Prestige)",550,610,60,183],
  ["Camera familiare, 2 camere da letto",718,797,79,239]
];
function priceText([,amount,old,discount,nightly]){
  return [discount+" € di sconto",old+" €",amount+" €",
    "per 3 notti, 1 camera",nightly+" € a notte","tasse e oneri inclusi"].join("\n");
}
// Real-life grid where heading and rate are sibling subtrees.
// Price row sits 900px below heading; the old code's threshold was 780.
const headings=[],footers=[];
entries.forEach((entry,i)=>{
  const col=i%3,row=Math.floor(i/3),x=70+col*300,y=150+row*1300;
  headings.push(new Node("h3",entry[0],rect(x,y,240,45)));
  footers.push(new Node("span",priceText(entry),rect(x+150,y+890,90,120)));
});
const titles=new Node("div","",rect(60,120,880,1500),headings);
const rates=new Node("div","",rect(60,1000,880,1600),footers);
const separated=new Node("main",entries.map(e=>e[0]+"\n"+priceText(e)).join("\n"),
  rect(50,100,900,2700),[titles,rates]);
const result=capture(separated);
assert.equal(result.rooms.length,6,"Tall grid must link all six current prices to individual room headings");
assert.deepEqual(Array.from(result.rooms,r=>r.total),entries.map(e=>e[1]));
assert.ok(result.rooms.every(r=>r.confidence==="total-for-stay"));

// Other layouts put "Prenota" in an anchor rather than a <button>.
// The book link is only an identifying signal; the reader must NOT click it.
const linked=entries.slice(0,3).map((entry,i)=>{
  const x=75+i*300,y=140;
  const head=new Node("h3",entry[0],rect(x,y,225,45));
  const rate=new Node("span",priceText(entry),rect(x+140,y+720,80,100));
  const anchor=new Node("a","Prenota",rect(x+130,y+850,90,36));
  return new Node("article",entry[0]+"\n"+priceText(entry)+"\nPrenota",
    rect(x,y,250,920),[head,rate,anchor]);
});
const linkedRoot=new Node("main",linked.map(n=>n.innerText).join("\n"),
  rect(50,120,950,1000),linked);
const linkedResult=capture(linkedRoot);
assert.equal(linkedResult.rooms.length,3,"Anchor-style Prenota links must be supported");
assert.deepEqual(Array.from(linkedResult.rooms,r=>r.total),entries.slice(0,3).map(e=>e[1]));

console.log("Expedia tall grid: six 3-night current totals linked; anchor CTA read without clicking.");
