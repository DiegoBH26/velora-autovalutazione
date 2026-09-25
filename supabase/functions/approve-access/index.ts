import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  cleanText,
  corsHeaders,
  getAdminClient,
  hashRegistrationCode,
  json,
  originAllowed,
  randomRegistrationCode,
  readJson,
  requireAdmin,
} from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders(req) });
  if (req.method !== "POST") return json(req, 405, { ok: false, error: "Metodo non consentito." });
  if (!originAllowed(req)) return json(req, 403, { ok: false, error: "Origine non autorizzata." });

  try {
    const adminUser = await requireAdmin(req);
    if (!adminUser) return json(req, 403, { ok: false, error: "Accesso amministratore richiesto." });

    const body = await readJson(req);
    const requestId = cleanText(body.requestId, 36);
    if (!/^[0-9a-f-]{36}$/i.test(requestId)) {
      return json(req, 400, { ok: false, error: "Richiesta non valida." });
    }

    const supabaseAdmin = getAdminClient();
    const { data: request, error } = await supabaseAdmin
      .from("access_requests")
      .select("id,email,full_name,status")
      .eq("id", requestId)
      .in("status", ["pending", "approved"])
      .maybeSingle();

    if (error) throw error;
    if (!request) return json(req, 404, { ok: false, error: "La richiesta non esiste o è già stata utilizzata." });

    const code = randomRegistrationCode();
    const codeHash = await hashRegistrationCode(code, request.id);
    const now = new Date().toISOString();
    const codeExpiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

    const { error: updateError } = await supabaseAdmin
      .from("access_requests")
      .update({
        status: "approved",
        approved_at: now,
        approval_used_at: now,
        registration_code_hash: codeHash,
        registration_code_expires_at: codeExpiresAt,
        code_attempts: 0,
        notification_error: null,
        updated_at: now,
      })
      .eq("id", request.id)
      .in("status", ["pending", "approved"]);

    if (updateError) throw updateError;

    return json(req, 200, {
      ok: true,
      message: "Richiesta approvata. Copia il codice e invialo personalmente all’utente.",
      code,
      email: request.email,
      fullName: request.full_name,
      expiresAt: codeExpiresAt,
    });
  } catch (error) {
    console.error("approve-access", error);
    return json(req, 503, { ok: false, error: "Non è stato possibile completare l’approvazione. Riprova." });
  }
});
