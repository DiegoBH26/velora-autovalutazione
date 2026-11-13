import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import AuthGate from "./AuthGate";
import "./styles.css";
import "./velora-readability.css";
import "./velora-inclusive-dark.css";

// Ripristina la scelta cromatica prima del rendering; non modifica dati o fotografie.
try {
  document.documentElement.classList.toggle(
    "velora-inclusive-dark",
    window.localStorage.getItem("velora-color-mode") === "dark-inclusive"
  );
} catch { /* Modalità originale se lo storage non è accessibile. */ }

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AuthGate>
      <App />
    </AuthGate>
  </React.StrictMode>
);
