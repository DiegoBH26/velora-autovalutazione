import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { corsHeaders, json } from "../_shared/common.ts";

// Bootstrap completed. This endpoint intentionally remains disabled.
Deno.serve((req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders(req) });
  return json(req, 410, { ok: false, error: "Configurazione amministratore già completata." });
});
