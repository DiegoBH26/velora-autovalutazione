import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  cleanText,
  corsHeaders,
  emailFrame,
  escapeHtml,
  getAdminClient,
  json,
  normalizeEmail,
  originAllowed,
  randomToken,
  readJson,
  requestIp,
  sendTransactionalEmail,
  sha256,
  validEmail,
} from "../_shared/common.ts";

const GENERIC_SUCCESS = "Richiesta registrata. Se approvata, il codice verrà inviato all’indirizzo indicato.";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders(req) });
  if (req.method !== "POST") return json(req, 405, { ok: false, error: "Metodo non consentito." });
  if (!originAllowed(req)) return json(req, 403, { ok: false, error: "Origine non autorizzata." });

  try {
    const body = await readJson(req);
    if (cleanText(body.website, 100)) return json(req, 200, { ok: true, message: GENERIC_SUCCESS });

    const email = normalizeEmail(body.email);
    const fullName = cleanText(body.fullName, 100);
    const phone = cleanText(body.phone, 30);
    const preferredChannel = body.preferredChannel === "phone" ? "phone" : "email";

    if (!validEmail(email) || fullName.length < 2) {
      return json(req, 400, { ok: false, error: "Controlla nome ed email e riprova." });
    }

    if (preferredChannel === "phone") {
      return json(req, 400, { ok: false, error: "L’invio tramite telefono non è ancora disponibile. Seleziona l’email." });
    }

    const adminEmail = normalizeEmail(Deno.env.get("ADMIN_EMAIL"));
    const siteUrl = (Deno.env.get("SITE_URL") || "").replace(/\/$/, "");
    if (!validEmail(adminEmail) || !siteUrl.startsWith("https://")) {
      throw new Error("Configurazione amministratore incompleta.");
    }

    const supabaseAdmin = getAdminClient();
    const fingerprint = await sha256(`${requestIp(req)}:${Deno.env.get("CODE_PEPPER") || ""}`);
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const fifteenMinutesAgo = new Date(Date.now() - 15 * 60 * 1000).toISOString();

    const [{ count: emailCount }, { count: ipCount }, { data: existingProfile }] = await Promise.all([
      supabaseAdmin.from("access_requests").select("id", { count: "exact", head: true }).eq("email", email).gte("requested_at", oneHourAgo),
      supabaseAdmin.from("access_requests").select("id", { count: "exact", head: true }).eq("request_ip_hash", fingerprint).gte("requested_at", fifteenMinutesAgo),
      supabaseAdmin.from("profiles").select("user_id").eq("email", email).eq("authorized", true).maybeSingle(),
    ]);

    if (existingProfile) return json(req, 200, { ok: true, message: GENERIC_SUCCESS });
    if ((emailCount || 0) >= 3 || (ipCount || 0) >= 10) {
      return json(req, 429, { ok: false, error: "Troppe richieste ravvicinate. Riprova più tardi." });
    }

    const { data: activeRequest } = await supabaseAdmin
      .from("access_requests")
      .select("id,status,admin_email_id,notification_error,requested_at")
      .eq("email", email)
      .in("status", ["pending", "approved"])
      .order("requested_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (activeRequest?.status === "approved" || (activeRequest?.admin_email_id && !activeRequest.notification_error)) {
      return json(req, 200, { ok: true, message: GENERIC_SUCCESS });
    }

    const approvalToken = randomToken();
    const approvalTokenHash = await sha256(approvalToken);
    const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();
    let requestId = activeRequest?.id as string | undefined;

    if (requestId) {
      const { error } = await supabaseAdmin
        .from("access_requests")
        .update({
          full_name: fullName,
          phone: phone || null,
          preferred_channel: preferredChannel,
          approval_token_hash: approvalTokenHash,
          approval_token_expires_at: expiresAt,
          request_ip_hash: fingerprint,
          requested_at: new Date().toISOString(),
          notification_error: null,
          updated_at: new Date().toISOString(),
        })
        .eq("id", requestId)
        .eq("status", "pending");
      if (error) throw error;
    } else {
      const { data, error } = await supabaseAdmin
        .from("access_requests")
        .insert({
          email,
          full_name: fullName,
          phone: phone || null,
          preferred_channel: preferredChannel,
          approval_token_hash: approvalTokenHash,
          approval_token_expires_at: expiresAt,
          request_ip_hash: fingerprint,
        })
        .select("id")
        .single();
      if (error) throw error;
      requestId = data.id;
    }

    const approvalUrl = `${siteUrl}/?approve=${encodeURIComponent(approvalToken)}`;
    const safeName = escapeHtml(fullName);
    const safeEmail = escapeHtml(email);
    const safePhone = phone ? escapeHtml(phone) : "Non indicato";
    const html = emailFrame(
      "Nuova richiesta di accesso Velora",
      "Una nuova richiesta attende la tua approvazione.",
      `<h1 style="margin:0 0 16px;font-size:26px;line-height:34px;color:#23124a;">Nuova richiesta di accesso</h1>
       <p style="margin:0 0 20px;color:#50627f;font-size:16px;line-height:26px;">Un utente chiede di utilizzare Velora Autovalutazione.</p>
       <div style="margin:0 0 24px;padding:18px;border-radius:16px;background:#fbf9ff;color:#23124a;font-size:15px;line-height:25px;">
         <strong>Nome:</strong> ${safeName}<br>
         <strong>Email:</strong> ${safeEmail}<br>
         <strong>Telefono:</strong> ${safePhone}
       </div>
       <a href="${approvalUrl}" style="display:block;padding:15px 20px;border-radius:14px;background:#23124a;color:#ffffff;text-align:center;font-size:16px;font-weight:800;text-decoration:none;">Esamina e approva la richiesta</a>
       <p style="margin:20px 0 0;color:#667085;font-size:13px;line-height:21px;">Il link è personale, utilizzabile una sola volta e scade dopo sette giorni. Se non riconosci la richiesta, ignora questo messaggio.</p>`
    );
    const text = `Nuova richiesta di accesso Velora\n\nNome: ${fullName}\nEmail: ${email}\nTelefono: ${phone || "Non indicato"}\n\nApprova la richiesta: ${approvalUrl}\n\nIl link scade dopo sette giorni.`;

    try {
      const delivery = await sendTransactionalEmail({
        to: adminEmail,
        subject: `Richiesta accesso Velora — ${fullName}`,
        html,
        text,
        idempotencyKey: `access-request-${requestId}`,
      });
      await supabaseAdmin.from("access_requests").update({ admin_email_id: delivery.id, notification_error: null, updated_at: new Date().toISOString() }).eq("id", requestId);
    } catch (error) {
      const message = error instanceof Error ? error.message.slice(0, 500) : "Invio non riuscito";
      await supabaseAdmin.from("access_requests").update({ notification_error: message, updated_at: new Date().toISOString() }).eq("id", requestId);
      throw error;
    }

    return json(req, 200, { ok: true, message: GENERIC_SUCCESS });
  } catch (error) {
    console.error("request-access", error);
    return json(req, 503, { ok: false, error: "Il servizio di richiesta accesso non è momentaneamente disponibile." });
  }
});
