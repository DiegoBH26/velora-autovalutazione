# Velora – rete di agenti specialisti (prima integrazione v125)

## Obiettivo
Ridurre errori tra OTA senza perdere il patrimonio dei parser esistenti.
L'implementazione è **incrementale**: il percorso «Avvia analisi selezionata»
rimane disponibile come fallback. La rete non è un insieme di nuovi modelli AI:
è una serie di worker Playwright indipendenti, con adattatori e confini dati
specifici, coordinati dallo stesso agente locale.

## Agenti
| ID | Compito | Know-how riusato |
|---|---|---|
| booking | Scoperta scheda Booking, camere, prezzi e date | adapter Booking in browser_audit_pilot.py |
| agoda | Identità hotel, date e quote Agoda | estrattori DOM e geometrici Agoda |
| airbnb | Multi-annuncio, identità, date e quote | discovery e quotazioni Airbnb |
| official_site | Navigazione sito ufficiale e audit fotografico | site_audit_builder.py + frontend_photo_audit |
| reviews | Google Maps, temi ricorrenti e rating pubblici OTA | google_reputation_observation + observe_ota_profile |
| validator | Check in sola lettura sugli esiti già prodotti | evaluate() di velora_agent_network.py |

Booking rimane **riferimento obbligatorio delle date** anche per gli altri
due agenti. Per questo Agoda e Airbnb possono consultare Booking come
*dipendenza di calendario*, senza eseguire gli altri parser OTA.

## Nomi degli agenti (v125)
- **Minerva (Booking.com)** – attivo
- **Galileo (Agoda)** – attivo
- **Apollo (Airbnb)** – attivo
- **Leonardo (Sito diretto)** – attivo
- **Ipazia (Recensioni)** – attivo
- **Giove (Revisore/Validatore)** – esclusivamente manuale
- **Ercole (Expedia)**, **Atlante (Vrbo)**, **Mercurio (Holidu)** – nomi riservati, non ancora attivi
- **Tesla (Hotels.com)**, **Turing (Trip.com)**, **Pitagora (Priceline)**, **Newton (Travelocity)**,
  **Socrate (Tripadvisor)**, **Keplero (Trivago)**, **Euclide (Google Hotels)**,
  **Archimede (HolidayCheck)** – nomi riservati, non ancora attivi

### CMD: esempio illustrativo, non una scansione reale
```text
AGENTE (OTA)                 | FASE                 | ESITO        | DETTAGLIO
Minerva (Booking.com)        | Browser / scraping   | IN CORSO     | perla-saracena
Minerva (Booking.com)        | Esecuzione           | COMPLETATO   | Esito salvato, da validare

GIOVE (VALIDATORE) - CHECK MANUALE
AGENTE (OTA)                 | CONTROLLO             | ESITO        | DETTAGLIO
Minerva (Booking.com)        | Date Booking           | VALIDATO     | Date confermate
Apollo (Airbnb)              | Tariffe verificate     | ERRORE       | Nessuna tariffa verificata
```
La fine di un'esecuzione **non è** una validazione. Solo Giove, avviato manualmente,
può segnalare VALIDATO (verde quando il terminale supporta ANSI) o ERRORE (rosso).
Le righe non eseguite non ricevono un falso verde.

## Registrazioni Expedia / Vrbo / Holidu
La prima registrazione deve essere effettuata manualmente dal titolare
dell'account, che accetta termini, eventuali verifiche di identità, OTP e
consensi. Expedia e Vrbo condividono l'accesso One Key per i clienti,
quindi verificare se una sola iscrizione sia sufficiente. Holidu distingue
i flussi per ospiti e per proprietari: non iscrivere una proprietà soltanto
per osservare i prezzi.

La futura automazione potrà riutilizzare soltanto sessioni autorizzate,
nel browser locale, se compatibile con le condizioni dei singoli servizi.
Non inserire account/password/OTP nel codice, nelle impostazioni condivise,
in GitHub o nei messaggi di chat; non utilizzare login per aggirare blocchi
anti-bot, quote o condizioni di utilizzo.

## Isolamento reale
- Cartella input/output: `AppData/Local/Velora/specialist-agents/<struttura>/<agente>/`.
- Profili Chrome `velora-browser-profile-discovery-<OTA>` e
  `velora-browser-profile-pricing-<OTA>` dentro la cartella dell'agente.
- Non condividere cookie e sessioni fra OTA.
- Due worker Chrome al massimo contemporaneamente per limitare blocchi di RAM.
  Le altre richieste sono in coda, non perdute.
- Nessuno specialista scrive sul file JSON della struttura originale.
  Ogni risultato viene salvato separatamente.
- I risultati passano al revisore **solo su comando esplicito** «Esegui check».
  Verde solo con evidenze riscontrate; mancanza dati non significa «nessuna tariffa».

## API locali (loopback)
- `GET /api/agents/config` – elenco degli specialisti
- `POST /api/agents/start` – avvia un singolo agente per ID struttura e OTA
- `GET /api/agents/status?propertyId=...` – stato/coda/errore dei worker
- `GET /api/agents/result?propertyId=...&agentId=...` – JSON separato
- `POST /api/agents/validate` – genera check manuale senza avviare nuovi scraper
- `GET /api/agents/validation?propertyId=...` – ultimo report di verifica

Le chiamate POST richiedono token locale, origini autorizzate e JSON.
I vecchi endpoint `/api/pilot/*` e `/api/audit/*` restano disponibili.

## Controlli d'accettazione prima del rilascio operativo
1. Aggiornare `AGGIORNA_VELORA_COMPLETO.bat` e quindi i file locali;
   verificare v125 e la presenza di `velora_agent_network.py`.
2. Aprire la microsezione rete specialisti nel frontend.
3. Con una struttura **test**, avviare Booking. Verificare che sia la sola OTA
   richiesta, che le date siano confermate e che il JSON resti nella propria cartella.
4. Avviare Agoda e Airbnb separatamente; verificare isolamento Chrome,
   nessuna sovrascrittura e stessa finestra data/ospiti di riferimento Booking.
5. Avviare il sito diretto e il worker recensioni: i due output devono avere
   finalità diverse, senza modificare l'intervista consulenziale.
6. Prima del click «Esegui check», nessun check verde. Dopo, i fallimenti
   (HTTP 429, robots, identità da confermare, date incoerenti, prezzo non validato)
   devono comparire come «Da verificare».
7. Riprovare in seguito un solo canale, verificando che non cancelli i dati degli altri.
8. Verificare le 31 domande personalizzate e lo storico delle strutture.
9. Verificare build React/Vite + py_compile nella GitHub Action.
10. Testare in modo assistito su Windows prima di rendere predefinita la nuova rete.

## Accessi registrati – fase successiva, non inclusa
Per Expedia, Vrbo, Holidu e altre OTA, gli account possono essere creati
**manualmente dall'utente**, quando l'accesso e l'automazione siano consentiti
dalle condizioni del portale. Occorrerà isolare i profili e proteggere
sessioni e credenziali. Nessuna password nel codice o in GitHub.

**Un login valido non autorizza ad aggirare CAPTCHA, anti-bot, rate limit o
limitazioni contrattuali.** Per i portali che bloccano la navigazione si
registrano HTTP 429/verifiche e si considerano API, partner o integrazioni
ufficiali se disponibili. Niente retry aggressivi o false tariffe.

## Limiti dichiarati
- La specializzazione usa ancora gli adapter collaudati del pilot; la
  migrazione di ciascun parser in package fisici separati è una seconda fase.
- Il revisore è una funzione deterministica a check, non un nuovo modello AI.
- In questa prima versione la raccolta testuale delle recensioni è principalmente
  Google; sugli altri portali si raccolgono solo metriche pubbliche quando verificabili.
- È indispensabile testare sul PC Windows dell'utente, dove Chrome e
  i portali reali possono avere comportamenti differenti.
