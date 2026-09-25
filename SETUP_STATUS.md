# Stato configurazione

## Completato

- Copia web separata dall'app Windows originale.
- Login, richiesta di accesso, approvazione e codice monouso.
- Flusso a doppia verifica implementato localmente: controllo del codice, verifica email e password definitiva.
- Database, regole RLS ed Edge Functions pubblicati su Supabase.
- Pannello amministratore privato con elenco richieste e generazione manuale del codice.
- Account amministratore creato e canale di configurazione iniziale disattivato.
- Nessuna modifica ai DNS o al sito ufficiale Barbarhouse.
- Verifica desktop e mobile completata.
- Build di produzione e controllo TypeScript riusciti.
- Audit dipendenze: 0 vulnerabilità note.
- Repository Git inizializzato localmente sul branch `main`.

## Da completare prima della pubblicazione del nuovo flusso

1. Configurare in Supabase l’SMTP per l’invio delle email agli utenti esterni.
2. Aggiungere alla lista degli URL di reindirizzamento `https://diegobh26.github.io/velora-autovalutazione/`.
3. Applicare la migrazione, pubblicare le Edge Functions e poi il frontend.
4. Eseguire dal sito pubblico una richiesta reale end-to-end con un nuovo codice.
5. Cambiare la password amministratore temporanea al primo accesso.

Le chiavi segrete non devono mai essere salvate nel repository.
