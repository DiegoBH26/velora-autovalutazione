# Raccolta massiva di schede pubbliche

`mass_scrape.py` legge una lista di URL o domini, cerca una sitemap (o i link
interni della pagina iniziale), scarica le schede con richieste asincrone e
salva progressivamente i risultati in `dati_strutture.csv`. Non serve usare F12,
copiarne le richieste cURL o aprire un browser per ogni pagina.

## Avvio su Windows

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-scraping.txt
.\.venv\Scripts\python.exe mass_scrape.py --input input_strutture.txt --output dati_strutture.csv
```

In alternativa: `python -m pip install curl_cffi selectolax pandas`. Pandas è
facoltativo: lo script usa il modulo CSV di Python e non ne ha bisogno.

Mettere un URL per riga in `input_strutture.txt`, ad esempio un sito ufficiale,
un elenco pubblico o la pagina di una singola struttura. Si possono passare
anche URL direttamente. È accettato pure un CSV con colonna `url`, `source_url`,
`website` o `sito`:

```powershell
.\.venv\Scripts\python.exe mass_scrape.py https://esempio.it/ --max-pages 300 --concurrency 15
```

La concorrenza massima è 15; per ogni dominio sono attive al massimo 2 richieste
e almeno 1 secondo tra gli avvii (più a lungo se `robots.txt` prescrive un
`Crawl-delay`). `--per-host`, `--delay`, `--max-pages` e
`--max-links-per-seed` sono configurabili entro limiti prudenti. Rilanciando
lo stesso comando il CSV esistente viene ripreso: gli URL già salvati non sono
scaricati di nuovo. Ogni riga è scaricata su disco subito.

## Colonne e affidabilità

Il CSV contiene URL, piattaforma, esito, timestamp, nome, indirizzo/città,
descrizione, servizi, contatti, URL delle foto, `prices_json` e le colonne
`booking_engine_*` (fornitore, URL, tipo di collegamento, esito, prova). I campi lista
sono JSON dentro la cella CSV. `prices_json` registra soltanto *indizi di
prezzo* esposti in HTML o JSON-LD, con provenienza e limiti: **non è ADR** e non
si usa automaticamente per il delta fra portali.

Il booking engine è cercato sul sito pubblico, anche se la pagina è ospitata
direttamente dal fornitore e non esiste un sito indipendente. Domini noti come
`book.ermeshotels.com`, `book.krossbooking.com` e `*.kross.travel` possono
identificare il fornitore; un dominio personalizzato o un link generico resta
“fornitore non identificato”. Si escludono le schede OTA e i pulsanti che
portano soltanto ai contatti. Un link non prova che il checkout sia operativo.
La nuova versione del CSV ha colonne aggiuntive: se hai già un file prodotto
con la vecchia intestazione, usa un nuovo nome di output per non alterarlo.

Il confronto numerico nel report Velora richiede preventivi datati con:
stessa unità fisica verificata, check-in, notti, ospiti, piano, trattamento,
cancellazione, pubblico e imposte. Nella sezione Audit Web si inseriscono i
preventivi completi; la nuova tabella mostra prezzi per notte e il delta verso
Booking solo se il confronto è omogeneo. La tabella descrittiva di piani e
promozioni resta nel report.

`curl_cffi` con `impersonate="chrome120"` fornisce un client HTTP leggero; non
garantisce accesso a pagine OTA rese via JavaScript o protette. Lo script si
identifica come bot, rispetta `robots.txt`, non supera login/CAPTCHA/403 e non
simula disponibilità o tariffe assenti. La velocità effettiva dipende dai siti,
dalla rete e dalle restrizioni: 15 richieste concorrenti **non** significano
15-20 pagine completate ogni secondo.

## Pilota locale delle date future, senza servizi a pagamento

`browser_audit_pilot.py` usa il Chrome già installato su questo PC tramite
Playwright. Sceglie automaticamente un soggiorno campione per ogni mese fino a
dicembre dell'anno successivo: 15-18 del mese, 12-17 agosto (5 notti), due
adulti. Se la data del mese è passata, usa una data ancora futura oppure salta
il mese. Non usa l'account personale Chrome e non effettua login.

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-scraping.txt
.\.venv\Scripts\python.exe browser_audit_pilot.py --dry-run
.\.venv\Scripts\python.exe browser_audit_pilot.py --months 1 --channels booking,airbnb --output dati_strutture_pilot.json
```

### Uso dal software sullo stesso PC

Questa funzione non richiede un server a pagamento. Dalla cartella del
progetto, con Node e Python già installati:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-scraping.txt
npm run build
.\.venv\Scripts\python.exe local_audit_server.py
```

Apri `http://127.0.0.1:8768/` nel browser e accedi a Velora con il tuo
account già autorizzato. Nella scheda **Audit Web** di Perla Saracena o
Sant'Antonio, sotto “Prezzi osservati per mese”, trovi **Prova un mese** e
**Verifica mesi futuri fino a fine anno prossimo**. Il risultato è salvato
progressivamente in un file `dati_strutture_pilot_<id>.json` nella cartella
del progetto e incluso nel report. In questa versione locale, il pulsante
**Genera report PDF** scarica direttamente il file; sul sito GitHub Pages
continua ad aprire la stampa del browser, da cui puoi scegliere “Salva come
PDF”. Interrompi il servizio locale con `Ctrl+C` nella finestra PowerShell.

Il servizio è disponibile **solo su questo PC** (`127.0.0.1`): non espone il
pilota ai colleghi attraverso il link pubblico. L'autenticazione di Velora
resta attiva anche in locale. Per gli altri utenti il PDF esistente e la
compilazione manuale continuano a funzionare online.

Per ora gli adattatori che **tentano** di applicare le date sono Booking e
Airbnb. Lo script visita solo URL consentiti da `robots.txt`, si ferma davanti
a blocchi o CAPTCHA e salva progressivamente esiti e fonti nel JSON. Una URL
con date non prova che la pagina abbia applicato quelle date: se non compaiono
nel contenuto reso, l'esito è `dates_unconfirmed`. Gli altri canali sono
esplicitamente `date_adapter_missing`, non "nessun prezzo". Il pilota non
inserisce automaticamente cifre nel report: prezzo finale, camera, piano,
imposte e pubblico vanno ancora verificati come un singolo preventivo prima
del confronto. È una base gratuita e onesta per sviluppare gli adattatori
canale per canale, non una promessa di scraping integrale delle OTA.

Prova del 1° ottobre 2026 su Perla Saracena (15–18 ottobre, due adulti): il
sito diretto e sei OTA non hanno ancora un adattatore date; Booking non ha
confermato le date nel contenuto reso; Airbnb mostra date ma non un
preventivo completo attribuibile con sicurezza a camera, piano e imposte.
Di conseguenza **zero prezzi sono stati acquisiti automaticamente** in questa
prova. Le tariffe e i delta già presenti nel report storico restano separati
da questi nuovi esiti. Per ottenere una tabella numerica futura affidabile,
servono adattatori e prove per ciascun portale, o un'integrazione ufficiale
con il channel manager/fornitore delle tariffe.


## Uso dall'app online con agente locale

Velora online puo' usare il browser Playwright del PC senza spostare lo scraping
su un servizio a pagamento.

1. esegui una sola volta `INSTALLA_AGENTE_VELORA.bat`;
2. quando devi fare un audit, avvia `AVVIA_AGENTE_VELORA.bat` e lascia aperta la finestra;
3. apri `https://diegobh26.github.io/velora-autovalutazione/`;
4. in **Strutture analizzate** usa **Nuovo audit automatico**, inserisci il sito
   ufficiale e premi **Analizza struttura**.

Il frontend online comunica con `http://127.0.0.1:8768` sullo stesso PC.
L'agente accetta richieste soltanto dalle origini Velora autorizzate e usa un
token casuale rigenerato a ogni avvio.

L'audit automatico iniziale riguarda il sito ufficiale: pagine, contatti,
privacy/cookie, CIN visibili, servizi, fotografie, segnali mobile e booking
engine quando rilevabile. I dati non dimostrabili restano **Non verificati**.
Prezzi OTA, recensioni e parita' tariffaria richiedono gli adattatori dedicati
e non vengono inventati.
