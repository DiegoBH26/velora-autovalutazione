// Visible-page bridge. The extension does not store credentials or booking data.
// Velora must be open in another Chrome tab while the user views one of five assisted OTAs.
"use strict";
const ORIGIN = "https://diegobh26.github.io";
if (location.origin === ORIGIN &&
    location.pathname.startsWith("/velora-autovalutazione/")) {
  const emit = (type, payload) => window.postMessage({
    source: "velora-expedia-companion-v1", type, payload
  }, ORIGIN);
  emit("READY", { installed: true,vrbo:true,holidu:true,hotels:true,travelocity:true,tabsLauncher:true,version:"0.4.5" });
  window.addEventListener("message", (event) => {
    if (event.source !== window || event.origin !== ORIGIN ||
        event.data?.source !== "velora-online-v1") return;
    if(event.data?.type === "COMPANION_PING") {
      emit("READY", {installed: true,vrbo:true,holidu:true,hotels:true,travelocity:true,tabsLauncher:true,version:"0.4.5"});
      return;
    }
    if(["OPEN_THREE_OTA_TABS","OPEN_FIVE_OTA_TABS"].includes(event.data?.type)) {
      chrome.runtime.sendMessage({type:event.data.type},(reply)=>{
        const error=chrome.runtime.lastError;
        if(error||!reply?.ok)
          emit("PORTALS_ERROR",{message:error?.message||reply?.error||"Apertura non riuscita",count:reply?.count||0});
        else emit("PORTALS_OPENED",{count:reply.count});
      });
      return;
    }
    if(!["CAPTURE_EXPEDIA","CAPTURE_VRBO","CAPTURE_HOLIDU","CAPTURE_HOTELS","CAPTURE_TRAVELOCITY"].includes(event.data?.type)) return;
    const requestType=event.data.type==="CAPTURE_VRBO"?"CAPTURE_VISIBLE_VRBO"
      :event.data.type==="CAPTURE_HOLIDU"?"CAPTURE_VISIBLE_HOLIDU"
      :event.data.type==="CAPTURE_HOTELS"?"CAPTURE_VISIBLE_HOTELS"
      :event.data.type==="CAPTURE_TRAVELOCITY"?"CAPTURE_VISIBLE_TRAVELOCITY"
      :"CAPTURE_VISIBLE_EXPEDIA";
    chrome.runtime.sendMessage({type: requestType}, (reply) => {
      const error = chrome.runtime.lastError;
      if (error || !reply?.ok) {
        emit("ERROR", {otaId:requestType==="CAPTURE_VISIBLE_VRBO"?"vrbo"
          :requestType==="CAPTURE_VISIBLE_HOLIDU"?"holidu"
          :requestType==="CAPTURE_VISIBLE_HOTELS"?"hotels"
          :requestType==="CAPTURE_VISIBLE_TRAVELOCITY"?"travelocity":"expedia",
          message: error?.message || reply?.error || "Acquisizione non riuscita"});
      } else {
        emit("RESULT", reply.payload);
      }
    });
  });
}
