# Stato configurazione

## Completato

- Copia web separata dall'app Windows originale.
- Login, richiesta di accesso, approvazione, codice monouso e registrazione.
- Database, regole RLS ed Edge Functions pubblicati su Supabase.
- Dominio email `velora.barbarhouse.com` creato in Resend (regione UE).
- Verifica desktop e mobile completata.
- Build di produzione e controllo TypeScript riusciti.
- Audit dipendenze: 0 vulnerabilità note.
- Repository Git inizializzato localmente sul branch `main`.

## Da completare prima della pubblicazione

1. Aggiungere al DNS i record presenti in `DNS_SETUP.md` e verificare il dominio in Resend.
2. Creare una chiave Resend con solo permesso di invio e salvarla nei segreti Supabase.
3. Pubblicare il repository e ottenere l'URL definitivo.
4. Impostare `SITE_URL` e `ALLOWED_ORIGINS` con l'URL definitivo.
5. Eseguire una richiesta di accesso reale end-to-end.

Le chiavi segrete non devono mai essere salvate nel repository.
