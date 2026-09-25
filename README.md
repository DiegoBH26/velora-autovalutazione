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
- Richiesta di accesso con pannello amministratore privato
- Codice di registrazione monouso composto da cinque numeri e un simbolo
- Approvazione manuale: l’amministratore copia il codice e lo invia con il canale concordato
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

Lo schema SQL e le Edge Functions sono nella cartella `supabase/`. Il flusso attuale non richiede un dominio email: le richieste compaiono nel pannello amministratore e il codice viene comunicato manualmente.

L’integrazione email automatica potrà essere riattivata in futuro utilizzando un dominio indipendente dedicato a Velora.
