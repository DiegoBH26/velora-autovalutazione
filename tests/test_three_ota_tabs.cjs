// Verify that Velora opens all three approved OTA homepages through Chrome
// extension tabs, not popup windows, and never accepts arbitrary URLs.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");
const root=path.resolve(__dirname,"..");
const worker=fs.readFileSync(path.join(root,"chrome-companion-expedia","background.js"),"utf8");
const bridge=fs.readFileSync(path.join(root,"chrome-companion-expedia","bridge.js"),"utf8");
const app=fs.readFileSync(path.join(root,"src/App.tsx"),"utf8");
const manifest=JSON.parse(fs.readFileSync(path.join(root,"chrome-companion-expedia","manifest.json"),"utf8"));
assert.equal(manifest.version,"0.4.5");
assert.ok(manifest.permissions.includes("tabs"));
assert.match(bridge,/OPEN_THREE_OTA_TABS/);
assert.match(bridge,/PORTALS_OPENED/);
assert.match(bridge,/tabsLauncher:true/);
const openFunction=app.split("  function openThreeOtaPortals() {",2)[1].split("\n  function captureHoliduFromChrome()",1)[0];
assert.match(openFunction,/OPEN_THREE_OTA_TABS/);
assert.doesNotMatch(openFunction,/window\.open\(/);

let listener=null,opened=[];
const chrome={
  runtime:{onMessage:{addListener:callback=>{listener=callback;}}},
  tabs:{create:async options=>{
    opened.push(options);
    return {id:100+opened.length};
  }}
};
vm.runInNewContext(worker,{chrome,URL,Date,Number,Set,Error,console});
assert.equal(typeof listener,"function");

function request(type,sender){
  return new Promise((resolve,reject)=>{
    const keepAlive=listener({type},sender,resolve);
    if(!keepAlive)reject(new Error("Unexpected request type"));
  });
}
async function main(){
  const sender={tab:{url:"https://diegobh26.github.io/velora-autovalutazione/",windowId:7}};
  const success=await request("OPEN_THREE_OTA_TABS",sender);
  assert.equal(success.ok,true);
  assert.equal(success.count,3);
  assert.deepEqual(opened.map(x=>x.url),[
    "https://www.expedia.it/","https://www.vrbo.com/it-it/","https://www.holidu.it/"
  ]);
  assert.ok(opened.every(x=>x.active===false&&x.windowId===7));
  const saved=opened.length;
  const rejected=await new Promise(resolve=>listener({type:"OPEN_THREE_OTA_TABS"},
    {tab:{url:"https://evil.example/",windowId:7}},resolve));
  assert.equal(rejected.ok,false);
  assert.equal(opened.length,saved);
  console.log("Chrome Companion v0.4.3: all three OTA tabs opened, no popups, denied untrusted sender.");
}
main().catch(err=>{console.error(err);process.exitCode=1;});
