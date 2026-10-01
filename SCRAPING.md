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
descrizione, servizi, contatti, URL delle foto e `prices_json`. I campi lista
sono JSON dentro la cella CSV. `prices_json` registra soltanto *indizi di
prezzo* esposti in HTML o JSON-LD, con provenienza e limiti: **non è ADR** e non
si usa automaticamente per il delta fra portali.

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
