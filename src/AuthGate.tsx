import React, { FormEvent, useEffect, useMemo, useState } from "react";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./supabase";

type View = "login" | "request" | "register" | "forgot" | "reset";

type FunctionResult = {
  ok?: boolean;
  message?: string;
  error?: string;
};

const inputClass =
  "h-12 w-full rounded-2xl border border-[#E0D7EC] bg-white px-4 text-sm font-semibold text-[#23124A] outline-none transition focus:border-[#C8A96B] focus:ring-4 focus:ring-[#C8A96B]/15";

const buttonClass =
  "h-12 w-full rounded-2xl bg-[#23124A] px-5 text-sm font-black text-white shadow-sm transition hover:bg-[#2F1A63] disabled:cursor-not-allowed disabled:opacity-50";

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

function ApprovalPanel({ token }: { token: string }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function approve() {
    setBusy(true);
    setError("");
    try {
      const result = await invokePublicFunction("approve-access", { token });
      setMessage(result.message || "Accesso approvato. Il codice è stato inviato all’utente.");
      window.history.replaceState({}, document.title, window.location.pathname);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Link non valido o scaduto.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AccessShell>
      <div className="mx-auto max-w-md">
        <p className="text-xs font-black uppercase tracking-[0.22em] text-[#C8A96B]">Autorizzazione amministratore</p>
        <h2 className="mt-3 text-3xl font-black tracking-tight text-[#23124A]">Conferma la richiesta di accesso</h2>
        <p className="mt-4 text-sm font-medium leading-7 text-[#50627F]">
          Confermando, l’utente riceverà via email un codice temporaneo composto da cinque numeri e un carattere speciale.
        </p>
        <div className="mt-6 space-y-4">
          {message && <Notice kind="success">{message}</Notice>}
          {error && <Notice kind="error">{error}</Notice>}
          {!message && (
            <button type="button" onClick={approve} disabled={busy} className={buttonClass}>
              {busy ? "Approvazione in corso…" : "Approva e invia il codice"}
            </button>
          )}
        </div>
      </div>
    </AccessShell>
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
      <p className="mt-3 text-sm font-medium leading-6 text-[#50627F]">L’amministratore riceverà una notifica e potrà autorizzarti con un solo passaggio.</p>
      {done ? (
        <div className="mt-7 space-y-5">
          <Notice kind="success">Richiesta registrata. Se approvata, riceverai il codice all’indirizzo indicato.</Notice>
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
          <Notice kind="info">Il codice viene inviato via email. L’invio tramite SMS potrà essere attivato successivamente.</Notice>
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
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const passwordValid = useMemo(
    () => password.length >= 12 && /[a-z]/.test(password) && /[A-Z]/.test(password) && /\d/.test(password) && /[^A-Za-z0-9]/.test(password),
    [password]
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (!/^\d{5}[!@#$%&*]$/.test(code)) {
      setError("Il codice deve contenere cinque numeri e un carattere speciale finale.");
      return;
    }
    if (!passwordValid) {
      setError("La password non rispetta i requisiti indicati.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Le due password non coincidono.");
      return;
    }

    setBusy(true);
    try {
      await invokePublicFunction("complete-registration", {
        fullName: fullName.trim(),
        email: email.trim(),
        code,
        password,
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
      <h2 className="mt-3 text-3xl font-black tracking-tight text-[#23124A]">Completa la registrazione</h2>
      {done ? (
        <div className="mt-7 space-y-5">
          <Notice kind="success">Account creato. Da questo momento puoi accedere direttamente con email e password.</Notice>
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
          <Field label="Crea una password">
            <input required type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} className={inputClass} />
          </Field>
          <p className="text-xs font-semibold leading-5 text-[#718096]">Almeno 12 caratteri, con maiuscola, minuscola, numero e simbolo.</p>
          <Field label="Ripeti la password">
            <input required type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className={inputClass} />
          </Field>
          {error && <Notice kind="error">{error}</Notice>}
          <button disabled={busy} className={buttonClass}>{busy ? "Creazione account…" : "Crea account autorizzato"}</button>
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
    if (password.length < 12 || !/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/\d/.test(password) || !/[^A-Za-z0-9]/.test(password)) {
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
        <Field label="Ripeti la password"><input required type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} className={inputClass} /></Field>
        {error && <Notice kind="error">{error}</Notice>}
        <button disabled={busy} className={buttonClass}>{busy ? "Aggiornamento…" : "Aggiorna password"}</button>
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

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const approvalToken = new URLSearchParams(window.location.search).get("approve");
  const [view, setView] = useState<View>("login");
  const [session, setSession] = useState<Session | null>(null);
  const [authorized, setAuthorized] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    supabase.auth.getSession().then(({ data }) => {
      if (!active) return;
      setSession(data.session);
      if (!data.session) setLoading(false);
    });

    const { data: listener } = supabase.auth.onAuthStateChange((event, nextSession) => {
      setSession(nextSession);
      setAuthorized(null);
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
      .select("authorized")
      .eq("user_id", session.user.id)
      .maybeSingle()
      .then(({ data, error }) => {
        setAuthorized(!error && data?.authorized === true);
        setLoading(false);
      });
  }, [session]);

  if (approvalToken) return <ApprovalPanel token={approvalToken} />;

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

  if (session && authorized === false) return <UnauthorizedPanel email={session.user.email} />;

  if (session && authorized) {
    return (
      <>
        <div className="sticky top-0 z-50 flex items-center justify-between gap-4 border-b border-[#E5DDF1] bg-white/95 px-5 py-3 backdrop-blur md:px-8">
          <Brand />
          <div className="flex items-center gap-3">
            <span className="hidden text-xs font-bold text-[#50627F] sm:inline">{session.user.email}</span>
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

