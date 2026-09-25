import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  cleanText,
  corsHeaders,
  getAdminClient,
  json,
  normalizeEmail,
  originAllowed,
  randomToken,
  readJson,
  requestIp,
  sha256,
  validEmail,
} from "../_shared/common.ts";

const GENERIC_SUCCESS =
  "Richiesta registrata. Contatta l’amministratore Velora per sapere quando è stata approvata e ricevere il codice.";

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

    if (!validEmail(email) || fullName.length < 2) {
      return json(req, 400, { ok: false, error: "Controlla nome ed email e riprova." });
    }

    const supabaseAdmin = getAdminClient();
    const fingerprint = await sha256(`velora:${requestIp(req)}`);
    const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const fifteenMinutesAgo = new Date(Date.now() - 15 * 60 * 1000).toISOString();

    const [emailRate, ipRate, profileResult] = await Promise.all([
      supabaseAdmin.from("access_requests").select("id", { count: "exact", head: true }).eq("email", email).gte("requested_at", oneHourAgo),
      supabaseAdmin.from("access_requests").select("id", { count: "exact", head: true }).eq("request_ip_hash", fingerprint).gte("requested_at", fifteenMinutesAgo),
      supabaseAdmin.from("profiles").select("user_id").eq("email", email).eq("authorized", true).maybeSingle(),
    ]);

    if (emailRate.error || ipRate.error || profileResult.error) throw emailRate.error || ipRate.error || profileResult.error;
    if (profileResult.data) return json(req, 200, { ok: true, message: GENERIC_SUCCESS });
    if ((emailRate.count || 0) >= 3 || (ipRate.count || 0) >= 10) {
      return json(req, 429, { ok: false, error: "Troppe richieste ravvicinate. Riprova più tardi." });
    }

    const { data: activeRequest, error: activeError } = await supabaseAdmin
      .from("access_requests")
      .select("id,status")
      .eq("email", email)
      .in("status", ["pending", "approved"])
      .order("requested_at", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (activeError) throw activeError;
    if (activeRequest) return json(req, 200, { ok: true, message: GENERIC_SUCCESS });

    const approvalTokenHash = await sha256(randomToken());
    const { error: insertError } = await supabaseAdmin.from("access_requests").insert({
      email,
      full_name: fullName,
      phone: phone || null,
      preferred_channel: "email",
      approval_token_hash: approvalTokenHash,
      approval_token_expires_at: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      request_ip_hash: fingerprint,
    });

    if (insertError) throw insertError;
    return json(req, 200, { ok: true, message: GENERIC_SUCCESS });
  } catch (error) {
    console.error("request-access", error);
    return json(req, 503, { ok: false, error: "Il servizio di richiesta accesso non è momentaneamente disponibile." });
  }
});
