import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  cleanText,
  corsHeaders,
  getAdminClient,
  hashRegistrationCode,
  json,
  normalizeEmail,
  originAllowed,
  readJson,
  timingSafeEqual,
  validEmail,
  validPassword,
} from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders(req) });
  if (req.method !== "POST") return json(req, 405, { ok: false, error: "Metodo non consentito." });
  if (!originAllowed(req)) return json(req, 403, { ok: false, error: "Origine non autorizzata." });

  try {
    const body = await readJson(req);
    const email = normalizeEmail(body.email);
    const fullName = cleanText(body.fullName, 100);
    const code = cleanText(body.code, 6);
    const password = typeof body.password === "string" ? body.password : "";

    if (!validEmail(email) || fullName.length < 2 || !/^\d{5}[!@#$%&*]$/.test(code)) {
      return json(req, 400, { ok: false, error: "Controlla i dati e il formato del codice." });
    }
    if (!validPassword(password)) {
      return json(req, 400, { ok: false, error: "La password deve avere almeno 12 caratteri, maiuscola, minuscola, numero e simbolo." });
    }

    const supabaseAdmin = getAdminClient();
    const { data: existingProfile } = await supabaseAdmin.from("profiles").select("user_id").eq("email", email).maybeSingle();
    if (existingProfile) return json(req, 409, { ok: false, error: "Esiste già un account autorizzato. Usa la pagina di login." });

    const { data: request, error } = await supabaseAdmin
      .from("access_requests")
      .select("id,registration_code_hash,registration_code_expires_at,code_attempts,status")
      .eq("email", email)
      .eq("status", "approved")
      .order("approved_at", { ascending: false })
      .limit(1)
      .maybeSingle();
    if (error) throw error;

    if (!request || !request.registration_code_hash || !request.registration_code_expires_at) {
      return json(req, 400, { ok: false, error: "Codice non valido oppure richiesta non approvata." });
    }
    if (request.code_attempts >= 5) {
      return json(req, 429, { ok: false, error: "Troppi tentativi. Richiedi un nuovo codice all’amministratore." });
    }
    if (new Date(request.registration_code_expires_at).getTime() < Date.now()) {
      await supabaseAdmin.from("access_requests").update({ status: "expired", updated_at: new Date().toISOString() }).eq("id", request.id);
      return json(req, 410, { ok: false, error: "Il codice è scaduto. Richiedi nuovamente l’accesso." });
    }

    const submittedHash = await hashRegistrationCode(code, request.id);
    if (!timingSafeEqual(submittedHash, request.registration_code_hash)) {
      await supabaseAdmin.from("access_requests").update({ code_attempts: request.code_attempts + 1, updated_at: new Date().toISOString() }).eq("id", request.id);
      return json(req, 400, { ok: false, error: "Codice non corretto." });
    }

    const { data: created, error: createError } = await supabaseAdmin.auth.admin.createUser({
      email,
      password,
      email_confirm: true,
      app_metadata: { authorized: true, created_via: "approved_access" },
      user_metadata: { full_name: fullName },
    });
    if (createError || !created.user) {
      if (createError?.message?.toLowerCase().includes("already")) {
        return json(req, 409, { ok: false, error: "Esiste già un account con questa email. Usa il login o il recupero password." });
      }
      throw createError || new Error("Creazione utente non riuscita.");
    }

    const now = new Date().toISOString();
    const { error: profileError } = await supabaseAdmin.from("profiles").insert({
      user_id: created.user.id,
      email,
      full_name: fullName,
      authorized: true,
      authorized_at: now,
    });
    if (profileError) {
      await supabaseAdmin.auth.admin.deleteUser(created.user.id);
      throw profileError;
    }

    const { error: requestError } = await supabaseAdmin
      .from("access_requests")
      .update({
        status: "registered",
        user_id: created.user.id,
        registered_at: now,
        registration_code_hash: null,
        updated_at: now,
      })
      .eq("id", request.id)
      .eq("status", "approved");
    if (requestError) throw requestError;

    return json(req, 200, { ok: true, message: "Account creato correttamente." });
  } catch (error) {
    console.error("complete-registration", error);
    return json(req, 503, { ok: false, error: "Non è stato possibile completare la registrazione. Riprova." });
  }
});
