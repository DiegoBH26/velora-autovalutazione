# Velora Autovalutazione Online

Versione web protetta del questionario di autovalutazione Velora. È una copia separata: il programma Windows originale non viene modificato.

## Cosa contiene
- App React/Vite standalone
- Branding Velora
- Salvataggio locale nel browser/app tramite localStorage
- Esportazione JSON
- Esportazione CSV
- Generazione report PDF tramite stampa/salva come PDF
- Modalità **Analisi rapida Hotel / B&B** con 30 domande principali mostrate in un unico percorso, senza sidebar
- Secondo livello opzionale con 20 domande di approfondimento
- Esportazione del modello 30+20 dell'analisi rapida in PDF e CSV
- Login personale con Supabase Auth
- Richiesta di accesso con approvazione amministratore
- Codice di registrazione monouso composto da cinque numeri e un simbolo
- Notifiche transazionali tramite Resend
- Pubblicazione automatica tramite GitHub Pages

## Uso in Velora
Il codice originale può restare anche dentro Velora come pagina del gestionale.

## Avvio locale

### Modalità sviluppo
```bash
npm install
npm run dev
```

Aprire l'indirizzo mostrato da Vite.

La configurazione pubblica Supabase è in `.env.development` e `.env.production`; non inserire mai chiavi segrete nel progetto o nel repository.

## Pubblicazione

Il workflow `.github/workflows/deploy-pages.yml` compila il progetto a ogni push su `main` e pubblica la cartella `dist` su GitHub Pages.

## Backend

Lo schema SQL e le Edge Functions sono nella cartella `supabase/`. Le funzioni richiedono i segreti `RESEND_API_KEY`, `ADMIN_EMAIL`, `SITE_URL`, `ALLOWED_ORIGINS`, `EMAIL_FROM` e `CODE_PEPPER` configurati nel pannello Supabase.
