import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  corsHeaders,
  getAdminClient,
  json,
  originAllowed,
  requireAdmin,
} from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders(req) });
  if (req.method !== "POST") return json(req, 405, { ok: false, error: "Metodo non consentito." });
  if (!originAllowed(req)) return json(req, 403, { ok: false, error: "Origine non autorizzata." });

  try {
    const adminUser = await requireAdmin(req);
    if (!adminUser) return json(req, 403, { ok: false, error: "Accesso amministratore richiesto." });

    const supabaseAdmin = getAdminClient();
    const { data, error } = await supabaseAdmin
      .from("access_requests")
      .select("id,email,full_name,phone,status,requested_at,approved_at,invited_at,registration_code_expires_at,registered_at")
      .in("status", ["pending", "approved", "registered"])
      .order("requested_at", { ascending: false })
      .limit(100);

    if (error) throw error;
    return json(req, 200, { ok: true, requests: data || [] });
  } catch (error) {
    console.error("list-access-requests", error);
    return json(req, 503, { ok: false, error: "Non è stato possibile caricare le richieste." });
  }
});
