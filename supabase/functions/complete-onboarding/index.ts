import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import {
  corsHeaders,
  getAdminClient,
  json,
  originAllowed,
  readJson,
  validPassword,
} from "../_shared/common.ts";

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders(req) });
  if (req.method !== "POST") return json(req, 405, { ok: false, error: "Metodo non consentito." });
  if (!originAllowed(req)) return json(req, 403, { ok: false, error: "Origine non autorizzata." });

  try {
    const authorization = req.headers.get("authorization") || "";
    const token = authorization.startsWith("Bearer ") ? authorization.slice(7).trim() : "";
    if (!token) return json(req, 401, { ok: false, error: "Collegamento di verifica non valido o scaduto." });

    const body = await readJson(req);
    const password = typeof body.password === "string" ? body.password : "";
    if (!validPassword(password)) {
      return json(req, 400, {
        ok: false,
        error: "La password deve avere almeno 12 caratteri, maiuscola, minuscola, numero e simbolo.",
      });
    }

    const supabaseAdmin = getAdminClient();
    const { data: userResult, error: userError } = await supabaseAdmin.auth.getUser(token);
    const user = userResult.user;
    if (userError || !user) return json(req, 401, { ok: false, error: "Collegamento di verifica non valido o scaduto." });
    if (!user.email_confirmed_at) {
      return json(req, 403, { ok: false, error: "Prima conferma l’indirizzo email dal messaggio ricevuto." });
    }

    const { data: profile, error: profileError } = await supabaseAdmin
      .from("profiles")
      .select("authorized,onboarding_required,full_name")
      .eq("user_id", user.id)
      .maybeSingle();
    if (profileError) throw profileError;
    if (!profile || profile.authorized !== true) {
      return json(req, 403, { ok: false, error: "Questo account non è autorizzato." });
    }
    if (profile.onboarding_required !== true) {
      return json(req, 409, { ok: false, error: "La registrazione è già stata completata. Accedi dal login." });
    }

    const { error: passwordError } = await supabaseAdmin.auth.admin.updateUserById(user.id, {
      password,
      app_metadata: { authorized: true, created_via: "approved_access" },
      user_metadata: { full_name: profile.full_name },
    });
    if (passwordError) throw passwordError;

    const now = new Date().toISOString();
    const { error: updateProfileError } = await supabaseAdmin
      .from("profiles")
      .update({ onboarding_required: false, email_verified_at: now, updated_at: now })
      .eq("user_id", user.id)
      .eq("onboarding_required", true);
    if (updateProfileError) throw updateProfileError;

    const { error: requestError } = await supabaseAdmin
      .from("access_requests")
      .update({ status: "registered", registered_at: now, updated_at: now })
      .eq("user_id", user.id)
      .eq("status", "approved");
    if (requestError) console.error("complete-onboarding-request-history", requestError);

    return json(req, 200, { ok: true, message: "Email verificata e password creata correttamente." });
  } catch (error) {
    console.error("complete-onboarding", error);
    return json(req, 503, { ok: false, error: "Non è stato possibile completare la registrazione. Riprova." });
  }
});
