import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  cleanText,
  corsHeaders,
  deriveRegistrationCode,
  emailFrame,
  escapeHtml,
  getAdminClient,
  hashRegistrationCode,
  json,
  originAllowed,
  readJson,
  sendTransactionalEmail,
  sha256,
} from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders(req) });
  if (req.method !== "POST") return json(req, 405, { ok: false, error: "Metodo non consentito." });
  if (!originAllowed(req)) return json(req, 403, { ok: false, error: "Origine non autorizzata." });

  try {
    const body = await readJson(req);
    const token = cleanText(body.token, 200);
    if (token.length < 32) return json(req, 400, { ok: false, error: "Link di approvazione non valido." });

    const tokenHash = await sha256(token);
    const supabaseAdmin = getAdminClient();
    const { data: request, error } = await supabaseAdmin
      .from("access_requests")
      .select("id,email,full_name,status,approval_token_expires_at")
      .eq("approval_token_hash", tokenHash)
      .in("status", ["pending", "approved"])
      .maybeSingle();

    if (error) throw error;
    if (!request) return json(req, 404, { ok: false, error: "La richiesta non esiste oppure è già stata utilizzata." });

    if (new Date(request.approval_token_expires_at).getTime() < Date.now()) {
      await supabaseAdmin.from("access_requests").update({ status: "expired", updated_at: new Date().toISOString() }).eq("id", request.id);
      return json(req, 410, { ok: false, error: "Il link di approvazione è scaduto." });
    }

    const code = await deriveRegistrationCode(token);
    const codeHash = await hashRegistrationCode(code, request.id);
    const codeExpiresAt = new Date(Date.now() + 30 * 60 * 1000).toISOString();
    const now = new Date().toISOString();

    const { error: updateError } = await supabaseAdmin
      .from("access_requests")
      .update({
        status: "approved",
        approved_at: request.status === "pending" ? now : undefined,
        approval_used_at: request.status === "pending" ? now : undefined,
        registration_code_hash: codeHash,
        registration_code_expires_at: codeExpiresAt,
        code_attempts: 0,
        notification_error: null,
        updated_at: now,
      })
      .eq("id", request.id)
      .in("status", ["pending", "approved"]);
    if (updateError) throw updateError;

    const safeName = escapeHtml(request.full_name);
    const safeCode = escapeHtml(code);
    const html = emailFrame(
      "Accesso Velora approvato",
      "Il tuo codice temporaneo di registrazione scade tra 30 minuti.",
      `<h1 style="margin:0 0 16px;font-size:26px;line-height:34px;color:#23124a;">Accesso approvato</h1>
       <p style="margin:0 0 18px;color:#50627f;font-size:16px;line-height:26px;">Ciao ${safeName}, la tua richiesta di accesso a Velora Autovalutazione è stata approvata.</p>
       <p style="margin:0 0 10px;color:#50627f;font-size:14px;line-height:22px;">Inserisci questo codice nella pagina “Ho ricevuto il codice”:</p>
       <div style="margin:0 0 18px;padding:18px;border-radius:16px;background:#fbf9ff;border:1px solid #e5ddf1;color:#23124a;text-align:center;font-family:monospace;font-size:30px;font-weight:800;letter-spacing:.25em;">${safeCode}</div>
       <p style="margin:0;color:#667085;font-size:13px;line-height:21px;"><strong>Il codice scade tra 30 minuti</strong> e può essere utilizzato una sola volta. Non condividerlo. Se non hai richiesto l’accesso, ignora questa email.</p>`
    );
    const text = `Accesso Velora approvato\n\nCiao ${request.full_name},\n\nil tuo codice di registrazione è: ${code}\n\nScade tra 30 minuti e può essere usato una sola volta. Non condividerlo.`;

    try {
      const delivery = await sendTransactionalEmail({
        to: request.email,
        subject: "Il tuo codice di accesso a Velora",
        html,
        text,
        idempotencyKey: `access-approved-${request.id}`,
      });
      await supabaseAdmin.from("access_requests").update({ user_email_id: delivery.id, notification_error: null, updated_at: new Date().toISOString() }).eq("id", request.id);
    } catch (sendError) {
      const message = sendError instanceof Error ? sendError.message.slice(0, 500) : "Invio non riuscito";
      await supabaseAdmin.from("access_requests").update({ notification_error: message, updated_at: new Date().toISOString() }).eq("id", request.id);
      throw sendError;
    }

    return json(req, 200, { ok: true, message: "Accesso approvato. Il codice è stato inviato all’utente e scade tra 30 minuti." });
  } catch (error) {
    console.error("approve-access", error);
    return json(req, 503, { ok: false, error: "Non è stato possibile completare l’approvazione. Riprova." });
  }
});
