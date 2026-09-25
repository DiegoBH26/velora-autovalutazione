import { createClient } from "npm:@supabase/supabase-js@2.117.1";

export type JsonRecord = Record<string, unknown>;

export function normalizeEmail(value: unknown) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

export function cleanText(value: unknown, maxLength: number) {
  if (typeof value !== "string") return "";
  return value.trim().replace(/[\u0000-\u001F\u007F]/g, " ").replace(/\s+/g, " ").slice(0, maxLength);
}

export function validEmail(email: string) {
  return email.length <= 254 && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function validPassword(password: string) {
  return (
    password.length >= 12 &&
    password.length <= 128 &&
    /[a-z]/.test(password) &&
    /[A-Z]/.test(password) &&
    /\d/.test(password) &&
    /[^A-Za-z0-9]/.test(password)
  );
}

export function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function getServerKey() {
  const modernKeys = Deno.env.get("SUPABASE_SECRET_KEYS");
  const legacyKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  let key = legacyKey || "";

  if (modernKeys) {
    try {
      key = JSON.parse(modernKeys).default || key;
    } catch {
      // The legacy key remains a safe server-side fallback.
    }
  }

  return key;
}

export function getAdminClient() {
  const url = Deno.env.get("SUPABASE_URL");
  const key = getServerKey();

  if (!url || !key) throw new Error("Configurazione Supabase server mancante.");

  return createClient(url, key, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
      detectSessionInUrl: false,
    },
  });
}

function configuredOrigins() {
  const defaults = "http://127.0.0.1:4173,http://localhost:4173,http://localhost:5173,https://diegobh26.github.io";
  const origins = `${defaults},${Deno.env.get("ALLOWED_ORIGINS") || ""},${Deno.env.get("SITE_URL") || ""}`
    .split(",")
    .map((value) => value.trim().replace(/\/$/, ""))
    .filter(Boolean);

  return new Set(origins);
}

export function originAllowed(req: Request) {
  const origin = req.headers.get("origin");
  if (!origin) return true;
  return configuredOrigins().has(origin.replace(/\/$/, ""));
}

export function corsHeaders(req: Request) {
  const origin = req.headers.get("origin")?.replace(/\/$/, "") || "";
  const allowed = configuredOrigins();

  return {
    "Access-Control-Allow-Origin": allowed.has(origin) ? origin : "null",
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    Vary: "Origin",
  };
}

export function json(req: Request, status: number, payload: JsonRecord) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...corsHeaders(req),
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

export async function readJson(req: Request) {
  const length = Number(req.headers.get("content-length") || "0");
  if (length > 12_000) throw new Error("Richiesta troppo grande.");
  return (await req.json()) as JsonRecord;
}

export function randomToken(bytes = 32) {
  const buffer = crypto.getRandomValues(new Uint8Array(bytes));
  return btoa(String.fromCharCode(...buffer)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export async function sha256(value: string) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function hashRegistrationCode(code: string, requestId: string) {
  const pepper = Deno.env.get("CODE_PEPPER") || getServerKey();
  if (!pepper || pepper.length < 24) throw new Error("Configurazione codice non valida.");
  return sha256(`${code}:${requestId}:${pepper}`);
}

export function randomRegistrationCode() {
  const values = crypto.getRandomValues(new Uint8Array(6));
  let digits = "";
  for (let index = 0; index < 5; index += 1) digits += String(values[index] % 10);
  const symbols = "!@#$%&*";
  return `${digits}${symbols[values[5] % symbols.length]}`;
}

export async function requireAdmin(req: Request) {
  const authorization = req.headers.get("authorization") || "";
  const token = authorization.startsWith("Bearer ") ? authorization.slice(7).trim() : "";
  if (!token) return null;

  const supabaseAdmin = getAdminClient();
  const { data, error } = await supabaseAdmin.auth.getUser(token);
  if (error || !data.user) return null;

  const { data: profile, error: profileError } = await supabaseAdmin
    .from("profiles")
    .select("authorized,is_admin")
    .eq("user_id", data.user.id)
    .maybeSingle();

  if (profileError || profile?.authorized !== true || profile?.is_admin !== true) return null;
  return data.user;
}

export function timingSafeEqual(left: string, right: string) {
  if (left.length !== right.length) return false;
  let mismatch = 0;
  for (let index = 0; index < left.length; index += 1) mismatch |= left.charCodeAt(index) ^ right.charCodeAt(index);
  return mismatch === 0;
}

export function requestIp(req: Request) {
  return (
    req.headers.get("cf-connecting-ip") ||
    req.headers.get("x-real-ip") ||
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
    "unknown"
  );
}

type EmailInput = {
  to: string;
  subject: string;
  html: string;
  text: string;
  idempotencyKey: string;
};

export async function sendTransactionalEmail(input: EmailInput) {
  const apiKey = Deno.env.get("RESEND_API_KEY");
  const from = Deno.env.get("EMAIL_FROM");
  const replyTo = Deno.env.get("REPLY_TO") || Deno.env.get("ADMIN_EMAIL");
  if (!apiKey || !from) throw new Error("Servizio email non configurato.");

  let lastError = "Invio email non riuscito.";

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const response = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
          "Idempotency-Key": input.idempotencyKey,
        },
        body: JSON.stringify({
          from,
          to: [input.to],
          reply_to: replyTo || undefined,
          subject: input.subject,
          html: input.html,
          text: input.text,
        }),
        signal: AbortSignal.timeout(10_000),
      });

      const result = await response.json().catch(() => ({}));
      if (response.ok) return { id: typeof result.id === "string" ? result.id : null };

      lastError = typeof result.message === "string" ? result.message : `Errore email ${response.status}`;
      if (response.status < 500 && response.status !== 429) break;
    } catch (error) {
      lastError = error instanceof Error ? error.message : lastError;
    }

    if (attempt < 2) await new Promise((resolve) => setTimeout(resolve, 1000 * 2 ** attempt + Math.random() * 500));
  }

  throw new Error(lastError);
}

export function emailFrame(title: string, preheader: string, content: string) {
  return `<!doctype html>
<html lang="it" dir="ltr">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>${escapeHtml(title)}</title>
  </head>
  <body style="margin:0;background:#f7f4fb;color:#23124a;font-family:Arial,sans-serif;">
    <div lang="it" dir="ltr" style="display:none;max-height:0;overflow:hidden;opacity:0;">${escapeHtml(preheader)}</div>
    <div lang="it" dir="ltr" style="max-width:620px;margin:0 auto;padding:32px 18px;">
      <div style="background:#ffffff;border:1px solid #e5ddf1;border-radius:24px;padding:32px;box-shadow:0 18px 50px rgba(35,18,74,.08);">
        <p style="margin:0 0 18px;color:#c8a96b;font-size:12px;font-weight:800;letter-spacing:.18em;text-transform:uppercase;">Velora Autovalutazione</p>
        ${content}
      </div>
      <p style="margin:18px 0 0;text-align:center;color:#667085;font-size:12px;line-height:20px;">Messaggio transazionale relativo all’accesso riservato Velora.</p>
    </div>
  </body>
</html>`;
}
