// Visible-page bridge. The extension does not store credentials or booking data.
// Velora must be open in another Chrome tab while the user views Expedia or Vrbo.
"use strict";
const ORIGIN = "https://diegobh26.github.io";
if (location.origin === ORIGIN &&
    location.pathname.startsWith("/velora-autovalutazione/")) {
  const emit = (type, payload) => window.postMessage({
    source: "velora-expedia-companion-v1", type, payload
  }, ORIGIN);
  emit("READY", { installed: true });
  window.addEventListener("message", (event) => {
    if (event.source !== window || event.origin !== ORIGIN ||
        event.data?.source !== "velora-online-v1") return;
    if(event.data?.type === "COMPANION_PING") {
      emit("READY", {installed: true});
      return;
    }
    if(!["CAPTURE_EXPEDIA","CAPTURE_VRBO"].includes(event.data?.type)) return;
    const requestType=event.data.type==="CAPTURE_VRBO"?"CAPTURE_VISIBLE_VRBO":"CAPTURE_VISIBLE_EXPEDIA";
    chrome.runtime.sendMessage({type: requestType}, (reply) => {
      const error = chrome.runtime.lastError;
      if (error || !reply?.ok) {
        emit("ERROR", {otaId:requestType==="CAPTURE_VISIBLE_VRBO"?"vrbo":"expedia",
          message: error?.message || reply?.error || "Acquisizione non riuscita"});
      } else {
        emit("RESULT", reply.payload);
      }
    });
  });
}
