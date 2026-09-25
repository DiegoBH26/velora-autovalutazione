import React, { FormEvent, useEffect, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";

type View = "login" | "request" | "register" | "forgot" | "reset";

type FunctionResult = {
  ok?: boolean;
  message?: string;
  error?: string;
  code?: string;
  email?: string;
  fullName?: string;
  expiresAt?: string;
  requests?: AccessRequest[];
};

type AccessRequest = {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  status: "pending" | "approved" | "registered";
  requested_at: string;
  approved_at: string | null;
  invited_at: string | null;
  registration_code_expires_at: string | null;
  registered_at: string | null;
};

type Profile = {
  authorized: boolean;
  is_admin: boolean;
  full_name: string;
  onboarding_required: boolean;
};

const inputClass =
  "h-12 w-full rounded-2xl border border-[#E0D7EC] bg-white px-4 text-sm font-semibold text-[#23124A] outline-none transition focus:border-[#C8A96B] focus:ring-4 focus:ring-[#C8A96B]/15";

const buttonClass =
  "h-12 w-full rounded-2xl bg-[#23124A] px-5 text-sm font-black text-white shadow-sm transition hover:bg-[#2F1A63] disabled:cursor-not-allowed disabled:opacity-50";

function passwordIsValid(password: string) {
  return password.length >= 12 && password.length <= 128 && /[a-z]/.test(password) && /[A-Z]/.test(password) && /\d/.test(password) && /[^A-Za-z0-9]/.test(password);
}

function PasswordChecklist({ password }: { password: string }) {
  const checks = [
    [password.length >= 12, "almeno 12 caratteri"],
    [/[A-Z]/.test(password), "una maiuscola"],
    [/[a-z]/.test(password), "una minuscola"],
    [/\d/.test(password), "un numero"],
    [/[^A-Za-z0-9]/.test(password), "un simbolo"],
  ] as const;

  return (
    <div className="grid grid-cols-2 gap-2 text-xs font-bold text-[#718096]" aria-live="polite">
      {checks.map(([passed, label]) => (
        <span key={label} className={passed ? "text-emerald-700" : "text-[#718096]"}>
          {passed ? "✓" : "○"} {label}
        </span>
      ))}
    </div>
  );
}

function cleanMessage(value: unknown, fallback: string) {
  if (typeof value !== "string") return fallback;
  return value.length > 240 ? fallback : value;
}

async function invokePublicFunction(name: string, body: Record<string, unknown>) {
  const { data, error } = await supabase.functions.invoke<FunctionResult>(name, { body });

  if (error) {
    throw new Error(cleanMessage(data?.error || data?.message || error.message, "Operazione non riuscita. Riprova."));
  }

  if (!data?.ok) {
    throw new Error(cleanMessage(data?.error || data?.message, "Operazione non riuscita. Riprova."));
  }

  return data;
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="grid h-11 w-11 place-items-center rounded-2xl bg-[#23124A] text-lg font-black text-[#C8A96B] shadow-lg shadow-[#23124A]/15">
        V
      </div>
      <div>
        <p className="text-lg font-black leading-none text-[#23124A]">Velora</p>
        <p className="mt-1 text-[10px] font-black uppercase tracking-[0.22em] text-[#C8A96B]">
          Autovalutazione
        </p>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-2 text-sm font-black text-[#23124A]">
      {label}
      {children}
    </label>
  );
}

function Notice({ kind, children }: { kind: "success" | "error" | "info"; children: React.ReactNode }) {
  const classes = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-800",
    error: "border-red-200 bg-red-50 text-red-800",
    info: "border-[#DDD2EA] bg-[#FBF9FF] text-[#50627F]",
  }[kind];

  return <div className={`rounded-2xl border px-4 py-3 text-sm font-semibold leading-6 ${classes}`}>{children}</div>;
}

function AccessShell({ children }: { children: React.ReactNode }) {
  return (
    <main className="min-h-screen bg-[#F7F4FB] px-5 py-8 text-[#23124A] md:px-8 md:py-12">
      <div className="mx-auto grid min-h-[calc(100vh-6rem)] max-w-6xl overflow-hidden rounded-[2.25rem] border border-[#E5DDF1] bg-white shadow-[0_30px_90px_rgba(35,18,74,0.12)] lg:grid-cols-[1.05fr_0.95fr]">
        <section className="relative hidden overflow-hidden bg-[#23124A] p-12 text-white lg:flex lg:flex-col lg:justify-between">
          <div className="absolute -right-32 -top-32 h-96 w-96 rounded-full border border-white/10 bg-white/5" />
          <div className="absolute -bottom-36 -left-28 h-96 w-96 rounded-full border border-[#C8A96B]/20 bg-[#C8A96B]/10" />
          <div className="relative z-10">
            <p className="text-xs font-black uppercase tracking-[0.3em] text-[#C8A96B]">Accesso riservato</p>
            <h1 className="mt-6 max-w-xl text-5xl font-black leading-[1.05]">
              Analisi della struttura, priorità chiare, decisioni migliori.
            </h1>
            <p className="mt-6 max-w-lg text-base font-medium leading-8 text-white/70">
              L’area Velora è disponibile esclusivamente agli utenti autorizzati. I dati della valutazione restano associati alla sessione di lavoro dell’utente.
            </p>
          </div>
          <div className="relative z-10 grid grid-cols-3 gap-3">
            {["Analisi completa", "Hotel / B&B 30+20", "Report PDF e CSV"].map((item) => (
              <div key={item} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-xs font-black leading-5 text-white/80">
                {item}
              </div>
            ))}
          </div>
        </section>

        <section className="flex flex-col p-6 sm:p-10 lg:p-12">
          <Brand />
          <div className="my-auto py-10">{children}</div>
          <p className="text-xs font-semibold leading-5 text-[#718096]">
            L’accesso è personale. Non condividere password, codici o link di approvazione.
          </p>
        </section>
      </div>
    </main>
  );
}

function LoginPanel({ onView }: { onView: (view: View) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const { error: loginError } = await supabase.auth.signInWithPassword({ email: email.trim(), password });
    if (loginError) setError("Email o password non corretti.");
    setBusy(false);
  }

  return (
    <div className="mx-auto max-w-md">
      <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Bentornato</p>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-[#23124A]">Accedi a Velora</h2>
      <p className="mt-3 text-sm font-medium leading-6 text-[#50627F]">Inserisci le credenziali create dopo l’approvazione.</p>
      <form onSubmit={submit} className="mt-7 space-y-4">
        <Field label="Email">
          <input type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} className={inputClass} />
        </Field>
        <Field label="Password">
          <input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} className={inputClass} />
        </Field>
        {error && <Notice kind="error">{error}</Notice>}
        <button disabled={busy} className={buttonClass}>{busy ? "Accesso…" : "Accedi"}</button>
      </form>
      <div className="mt-6 grid gap-3 text-center text-sm font-black sm:grid-cols-2">
        <button type="button" onClick={() => onView("request")} className="rounded-2xl border border-[#C8A96B]/50 bg-[#FFF8E8] px-4 py-3 text-[#23124A] hover:bg-[#F7EBC9]">Richiedi accesso</button>
        <button type="button" onClick={() => onView("register")} className="rounded-2xl border border-[#E5DDF1] bg-[#FBF9FF] px-4 py-3 text-[#23124A] hover:bg-[#F3EEF9]">Ho ricevuto il codice</button>
      </div>
      <button type="button" onClick={() => onView("forgot")} className="mt-5 w-full text-center text-sm font-bold text-[#50627F] underline decoration-[#C8A96B] underline-offset-4">Password dimenticata?</button>
    </div>
  );
}

function RequestPanel({ onView }: { onView: (view: View) => void }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [website, setWebsite] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await invokePublicFunction("request-access", {
        fullName: fullName.trim(),
        email: email.trim(),
        phone: phone.trim(),
        preferredChannel: "email",
        website,
      });
      setDone(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Richiesta non inviata.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Nuovo utente</p>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-[#23124A]">Richiedi l’accesso</h2>
      <p className="mt-3 text-sm font-medium leading-6 text-[#50627F]">La richiesta comparirà nel pannello privato dell’amministratore.</p>
      {done ? (
        <div className="mt-7 space-y-5">
          <Notice kind="success">Richiesta registrata. Contatta l’amministratore Velora: dopo l’approvazione ti comunicherà personalmente il codice.</Notice>
          <button type="button" onClick={() => onView("login")} className={buttonClass}>Torna all’accesso</button>
        </div>
      ) : (
        <form onSubmit={submit} className="mt-7 space-y-4">
          <Field label="Nome e cognome">
            <input required minLength={2} maxLength={100} autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} className={inputClass} />
          </Field>
          <Field label="Email">
            <input required type="email" maxLength={254} autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className={inputClass} />
          </Field>
          <Field label="Telefono (facoltativo)">
            <input type="tel" maxLength={30} autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} className={inputClass} placeholder="Es. +39 333 1234567" />
          </Field>
          <div className="hidden" aria-hidden="true">
            <label>Lascia vuoto<input tabIndex={-1} autoComplete="off" value={website} onChange={(event) => setWebsite(event.target.value)} /></label>
          </div>
          <Notice kind="info">Per ora il codice viene comunicato personalmente dall’amministratore tramite il canale concordato.</Notice>
          {error && <Notice kind="error">{error}</Notice>}
          <button disabled={busy} className={buttonClass}>{busy ? "Invio…" : "Invia richiesta"}</button>
        </form>
      )}
      {!done && <button type="button" onClick={() => onView("login")} className="mt-5 w-full text-center text-sm font-black text-[#50627F]">← Torna al login</button>}
    </div>
  );
}

function RegisterPanel({ onView }: { onView: (view: View) => void }) {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!/^\d{5}[!@#$%&*]$/.test(code)) {
      setError("Il codice deve contenere cinque numeri e un carattere speciale finale.");
      return;
    }

    setBusy(true);
    try {
      await invokePublicFunction("complete-registration", {
        fullName: fullName.trim(),
        email: email.trim(),
        code,
      });
      setDone(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Registrazione non riuscita.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Utente autorizzato</p>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-[#23124A]">Verifica il codice</h2>
      {done ? (
        <div className="mt-7 space-y-5">
          <Notice kind="success">Email di verifica inviata. Aprila, clicca il collegamento personale e crea la tua password definitiva. Solo dopo potrai entrare nel software.</Notice>
          <Notice kind="info">Se non la trovi entro pochi minuti, controlla anche Spam o Promozioni. Il collegamento non deve essere condiviso.</Notice>
          <button type="button" onClick={() => onView("login")} className={buttonClass}>Vai al login</button>
        </div>
      ) : (
        <form onSubmit={submit} className="mt-7 space-y-4">
          <Field label="Nome e cognome">
            <input required minLength={2} maxLength={100} autoComplete="name" value={fullName} onChange={(event) => setFullName(event.target.value)} className={inputClass} />
          </Field>
          <Field label="Email autorizzata">
            <input required type="email" maxLength={254} autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className={inputClass} />
          </Field>
          <Field label="Codice ricevuto">
            <input required inputMode="text" maxLength={6} autoComplete="one-time-code" value={code} onChange={(event) => setCode(event.target.value.replace(/\s/g, ""))} className={`${inputClass} text-center font-mono text-xl tracking-[0.25em]`} placeholder="12345!" />
          </Field>
          <Notice kind="info">Dopo la verifica del codice riceverai un’email personale. Dal collegamento contenuto nell’email sceglierai la password definitiva.</Notice>
          {error && <Notice kind="error">{error}</Notice>}
          <button disabled={busy} className={buttonClass}>{busy ? "Invio email…" : "Verifica codice e invia email"}</button>
        </form>
      )}
      {!done && <button type="button" onClick={() => onView("login")} className="mt-5 w-full text-center text-sm font-black text-[#50627F]">← Torna al login</button>}
    </div>
  );
}

function ForgotPanel({ onView }: { onView: (view: View) => void }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const redirectTo = `${window.location.origin}${import.meta.env.BASE_URL}`;
    const { error: resetError } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo });
    if (resetError) setError("Non è stato possibile inviare il messaggio. Riprova più tardi.");
    else setDone(true);
    setBusy(false);
  }

  return (
    <div className="mx-auto max-w-md">
      <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Recupero credenziali</p>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-[#23124A]">Reimposta la password</h2>
      {done ? (
        <Notice kind="success">Se l’indirizzo appartiene a un account autorizzato, riceverai le istruzioni via email.</Notice>
      ) : (
        <form onSubmit={submit} className="mt-7 space-y-4">
          <Field label="Email">
            <input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} className={inputClass} />
          </Field>
          {error && <Notice kind="error">{error}</Notice>}
          <button disabled={busy} className={buttonClass}>{busy ? "Invio…" : "Invia istruzioni"}</button>
        </form>
      )}
      <button type="button" onClick={() => onView("login")} className="mt-5 w-full text-center text-sm font-black text-[#50627F]">← Torna al login</button>
    </div>
  );
}

function ResetPanel({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!passwordIsValid(password)) {
      setError("Usa almeno 12 caratteri con maiuscola, minuscola, numero e simbolo.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Le due password non coincidono.");
      return;
    }
    setBusy(true);
    const { error: updateError } = await supabase.auth.updateUser({ password });
    if (updateError) setError("Il collegamento è scaduto. Richiedi nuovamente il recupero.");
    else {
      await supabase.auth.signOut();
      onDone();
    }
    setBusy(false);
  }

  return (
    <div className="mx-auto max-w-md">
      <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Sicurezza account</p>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-[#23124A]">Scegli la nuova password</h2>
      <form onSubmit={submit} className="mt-7 space-y-4">
        <Field label="Nuova password"><input required type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} className={inputClass} /></Field>
        <PasswordChecklist password={password} />
        <Field label="Ripeti la password"><input required type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className={inputClass} /></Field>
        {error && <Notice kind="error">{error}</Notice>}
        <button disabled={busy} className={buttonClass}>{busy ? "Aggiornamento…" : "Aggiorna password"}</button>
      </form>
    </div>
  );
}

function OnboardingPasswordPanel({ email, onDone }: { email?: string; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!passwordIsValid(password)) {
      setError("La password non rispetta ancora tutti i requisiti indicati.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Le due password non coincidono.");
      return;
    }

    setBusy(true);
    try {
      await invokePublicFunction("complete-onboarding", { password });
      await supabase.auth.signOut();
      const cleanUrl = `${window.location.origin}${import.meta.env.BASE_URL}`;
      window.history.replaceState({}, document.title, cleanUrl);
      onDone();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Registrazione non riuscita.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Email verificata</p>
      <h2 className="mt-3 text-3xl font-black tracking-tight text-[#23124A]">Crea la tua password</h2>
      <p className="mt-3 text-sm font-medium leading-6 text-[#50627F]">
        {email ? `L’indirizzo ${email} è stato verificato.` : "Il tuo indirizzo email è stato verificato."} Scegli ora la password personale definitiva.
      </p>
      <form onSubmit={submit} className="mt-7 space-y-4">
        <Field label="Nuova password">
          <input required type="password" minLength={12} maxLength={128} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} className={inputClass} />
        </Field>
        <PasswordChecklist password={password} />
        <Field label="Ripeti la password">
          <input required type="password" minLength={12} maxLength={128} autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className={inputClass} />
        </Field>
        {error && <Notice kind="error">{error}</Notice>}
        <button disabled={busy} className={buttonClass}>{busy ? "Salvataggio…" : "Conferma password e completa"}</button>
      </form>
    </div>
  );
}

function UnauthorizedPanel({ email }: { email?: string }) {
  return (
    <AccessShell>
      <div className="mx-auto max-w-md space-y-5">
        <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Accesso non abilitato</p>
        <h2 className="text-3xl font-black tracking-tight text-[#23124A]">Questo account non è autorizzato</h2>
        <Notice kind="info">{email ? `L’account ${email} non risulta ancora autorizzato.` : "L’account non risulta ancora autorizzato."}</Notice>
        <button type="button" onClick={() => supabase.auth.signOut()} className={buttonClass}>Esci e usa un altro account</button>
      </div>
    </AccessShell>
  );
}

function AdminPanel({ onClose }: { onClose: () => void }) {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [generated, setGenerated] = useState<{ code: string; email: string; fullName: string; expiresAt: string } | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordMessage, setPasswordMessage] = useState("");

  async function loadRequests() {
    setLoading(true);
    setError("");
    try {
      const result = await invokePublicFunction("list-access-requests", {});
      setRequests(result.requests || []);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Richieste non disponibili.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadRequests();
  }, []);

  async function approve(request: AccessRequest) {
    setBusyId(request.id);
    setError("");
    try {
      const result = await invokePublicFunction("approve-access", { requestId: request.id });
      if (!result.code || !result.email || !result.fullName || !result.expiresAt) {
        throw new Error("Il codice non è stato generato.");
      }
      setGenerated({
        code: result.code,
        email: result.email,
        fullName: result.fullName,
        expiresAt: result.expiresAt,
      });
      await loadRequests();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Approvazione non riuscita.");
    } finally {
      setBusyId("");
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    setPasswordMessage("");
    if (!passwordIsValid(password)) {
      setPasswordMessage("Usa almeno 12 caratteri con maiuscola, minuscola, numero e simbolo.");
      return;
    }
    if (password !== confirmPassword) {
      setPasswordMessage("Le due password non coincidono.");
      return;
    }
    const { error: updateError } = await supabase.auth.updateUser({ password });
    if (updateError) {
      setPasswordMessage("Aggiornamento non riuscito. Riprova.");
      return;
    }
    setPassword("");
    setConfirmPassword("");
    setPasswordMessage("Password aggiornata correttamente.");
  }

  const pending = requests.filter((request) => request.status === "pending");
  const history = requests.filter((request) => request.status !== "pending");

  return (
    <main className="min-h-screen bg-[#F7F4FB] px-5 py-8 text-[#23124A] md:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Amministrazione</p>
            <h1 className="mt-2 text-3xl font-black">Richieste di accesso</h1>
            <p className="mt-2 text-sm font-semibold text-[#50627F]">Approva l’utente, copia il codice e invialo personalmente.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => void loadRequests()} className="rounded-xl border border-[#E5DDF1] bg-white px-4 py-2 text-xs font-black">Aggiorna</button>
            <button type="button" onClick={() => setShowPassword((value) => !value)} className="rounded-xl border border-[#E5DDF1] bg-white px-4 py-2 text-xs font-black">Cambia password</button>
            <button type="button" onClick={onClose} className="rounded-xl bg-[#23124A] px-4 py-2 text-xs font-black text-white">Apri software</button>
          </div>
        </div>

        {showPassword && (
          <form onSubmit={changePassword} className="mt-6 grid gap-4 rounded-3xl border border-[#E5DDF1] bg-white p-5 md:grid-cols-[1fr_1fr_auto] md:items-end">
            <Field label="Nuova password"><input required type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} className={inputClass} /></Field>
            <Field label="Ripeti password"><input required type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className={inputClass} /></Field>
            <button className="h-12 rounded-2xl bg-[#23124A] px-5 text-sm font-black text-white">Salva password</button>
            {passwordMessage && <div className="md:col-span-3"><Notice kind={passwordMessage.includes("correttamente") ? "success" : "error"}>{passwordMessage}</Notice></div>}
          </form>
        )}

        {generated && (
          <section className="mt-6 rounded-3xl border border-emerald-200 bg-emerald-50 p-6">
            <p className="text-xs font-black uppercase tracking-[0.2em] text-emerald-700">Codice pronto</p>
            <h2 className="mt-2 text-2xl font-black">{generated.fullName}</h2>
            <p className="mt-1 text-sm font-semibold text-emerald-900">{generated.email}</p>
            <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center">
              <code className="rounded-2xl bg-white px-6 py-4 text-center text-3xl font-black tracking-[0.25em] text-[#23124A]">{generated.code}</code>
              <button type="button" onClick={() => navigator.clipboard.writeText(generated.code)} className="rounded-2xl bg-[#23124A] px-5 py-4 text-sm font-black text-white">Copia codice</button>
            </div>
            <p className="mt-4 text-xs font-bold text-emerald-800">Valido per 24 ore e utilizzabile una sola volta. Un nuovo codice sostituisce quello precedente.</p>
          </section>
        )}

        {error && <div className="mt-6"><Notice kind="error">{error}</Notice></div>}

        <section className="mt-7 rounded-3xl border border-[#E5DDF1] bg-white p-5 md:p-7">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-black">Da approvare</h2>
            <span className="rounded-full bg-[#FFF8E8] px-3 py-1 text-xs font-black text-[#80621F]">{pending.length}</span>
          </div>
          {loading ? (
            <p className="mt-6 text-sm font-bold text-[#718096]">Caricamento…</p>
          ) : pending.length === 0 ? (
            <Notice kind="info">Non ci sono nuove richieste.</Notice>
          ) : (
            <div className="mt-5 grid gap-4">
              {pending.map((request) => (
                <article key={request.id} className="grid gap-4 rounded-2xl border border-[#E5DDF1] p-5 md:grid-cols-[1fr_auto] md:items-center">
                  <div>
                    <h3 className="font-black">{request.full_name}</h3>
                    <p className="mt-1 text-sm font-semibold text-[#50627F]">{request.email}</p>
                    {request.phone && <p className="mt-1 text-sm font-semibold text-[#50627F]">{request.phone}</p>}
                    <p className="mt-2 text-xs font-bold text-[#8A94A6]">Richiesta: {new Date(request.requested_at).toLocaleString("it-IT")}</p>
                  </div>
                  <button type="button" disabled={busyId === request.id} onClick={() => void approve(request)} className="rounded-2xl bg-[#23124A] px-5 py-3 text-sm font-black text-white disabled:opacity-50">
                    {busyId === request.id ? "Approvazione…" : "Approva e genera codice"}
                  </button>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="mt-7 rounded-3xl border border-[#E5DDF1] bg-white p-5 md:p-7">
          <h2 className="text-xl font-black">Storico recente</h2>
          <div className="mt-5 grid gap-3">
            {history.length === 0 ? (
              <p className="text-sm font-semibold text-[#718096]">Nessuna richiesta approvata.</p>
            ) : history.map((request) => (
              <div key={request.id} className="flex flex-col gap-3 rounded-2xl border border-[#EEE8F5] p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="font-black">{request.full_name} · {request.email}</p>
                  <p className="mt-1 text-xs font-bold text-[#718096]">
                    {request.status === "registered"
                      ? "Registrato"
                      : request.invited_at
                        ? "Email di verifica inviata — in attesa della password"
                        : "Approvato — puoi generare un nuovo codice"}
                  </p>
                </div>
                {request.status === "approved" && !request.invited_at && (
                  <button type="button" disabled={busyId === request.id} onClick={() => void approve(request)} className="rounded-xl border border-[#C8A96B]/60 bg-[#FFF8E8] px-4 py-2 text-xs font-black">Nuovo codice</button>
                )}
              </div>
            ))}
          </div>
        </section>
      </div>
    </main>
  );
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const [view, setView] = useState<View>("login");
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [showAdmin, setShowAdmin] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      if (!data.session) setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((event, nextSession) => {
      if (nextSession) setLoading(true);
      setSession(nextSession);
      setProfile(null);
      if (event === "PASSWORD_RECOVERY") setView("reset");
      if (!nextSession) setLoading(false);
    });

    return () => {
      active = false;
      listener.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!session) return;
    setLoading(true);
    supabase
      .from("profiles")
      .select("authorized,is_admin,full_name,onboarding_required")
      .eq("user_id", session.user.id)
      .maybeSingle()
      .then(({ data, error }) => {
        setProfile(!error && data ? data as Profile : null);
        setLoading(false);
      });
  }, [session]);

  if (loading) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#F7F4FB] px-6">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-[#E5DDF1] border-t-[#23124A]" />
          <p className="mt-4 text-sm font-black text-[#50627F]">Verifica accesso…</p>
        </div>
      </main>
    );
  }

  if (session && profile?.authorized !== true) return <UnauthorizedPanel email={session.user.email} />;

  if (session && profile?.authorized && profile.onboarding_required) {
    return (
      <AccessShell>
        <OnboardingPasswordPanel email={session.user.email} onDone={() => setView("login")} />
      </AccessShell>
    );
  }

  if (session && profile?.authorized && !profile.onboarding_required) {
    if (profile.is_admin && showAdmin) return <AdminPanel onClose={() => setShowAdmin(false)} />;
    return (
      <>
        <div className="sticky top-0 z-50 flex items-center justify-between gap-4 border-b border-[#E5DDF1] bg-white/95 px-5 py-3 backdrop-blur md:px-8">
          <Brand />
          <div className="flex items-center gap-3">
            <span className="hidden text-xs font-bold text-[#50627F] sm:inline">{session.user.email}</span>
            {profile.is_admin && <button type="button" onClick={() => setShowAdmin(true)} className="rounded-xl border border-[#C8A96B]/60 bg-[#FFF8E8] px-4 py-2 text-xs font-black text-[#23124A]">Richieste</button>}
            <button type="button" onClick={() => supabase.auth.signOut()} className="rounded-xl border border-[#E5DDF1] bg-[#FBF9FF] px-4 py-2 text-xs font-black text-[#23124A] hover:bg-[#F3EEF9]">Esci</button>
          </div>
        </div>
        {children}
      </>
    );
  }

  return (
    <AccessShell>
      {view === "login" && <LoginPanel onView={setView} />}
      {view === "request" && <RequestPanel onView={setView} />}
      {view === "register" && <RegisterPanel onView={setView} />}
      {view === "forgot" && <ForgotPanel onView={setView} />}
      {view === "reset" && <ResetPanel onDone={() => setView("login")} />}
    </AccessShell>
  );
}
