# Leonardo · Visite mensili stimate del sito diretto

Fonte: Vaneform Free API (https://vaneform.com/docs/api).

## Cosa acquisisce

* Stima delle visite mensili del dominio e mese di riferimento, quando disponibili;
* Variazione sul mese precedente, mix delle sorgenti e confidenza dichiarata, quando forniti;
* Stato affidabile `not_available` se il dominio non ha una stima;
* Nessun dato inventato, nessuna stima della singola struttura quando il sito è una pagina di un dominio condiviso.

Queste NON sono visite effettive misurate su GA4. Vaneform usa dati di terze parti (Similarweb) e offre 100 crediti al mese nel piano gratuito; una lettura utile di dominio costa 1 credito. I limiti possono cambiare secondo il fornitore.

## Configurazione una sola volta sul PC Windows dell'agente

1. Apri https://vaneform.com/ e crea un account gratuito.
2. Dopo l'accesso, apri https://vaneform.com/account/api e genera una chiave API privata (`vf_live_...`).
3. **Non inviare la chiave su ChatGPT, GitHub o email.** Sul PC Windows, apri **PowerShell** e inserisci:

   ```powershell
   setx VANEFORM_API_KEY "INCOLLA_QUI_LA_TUA_CHIAVE_VANEFORM"
   ```

4. Chiudi **tutte le finestre** dell'agente Velora, esegui **AGGIORNA_VELORA_COMPLETO.bat**, poi riapri **AVVIA_AGENTE_VELORA.bat**. La nuova variabile è visibile ai nuovi processi Windows.
5. In Velora seleziona soltanto **Leonardo (Sito diretto)**, avvia il controllo ed entra nella sezione **Leonardo · Visite mensili stimate del sito diretto**.

## Limiti

* 100 crediti/mese non significa scansioni illimitate. Velora salva un risultato valido per dominio e mese, per non ripetere l'acquisizione ogni volta.
* Alcuni piccoli domini non hanno dati sufficienti. Se la fonte non restituisce una stima, il valore rimane **non disponibile**, mai **0 visite**.
* Se una struttura è una sottopagina di un dominio condiviso, il traffico del dominio **non** va attribuito alla singola struttura.
* Se la chiave è assente, non valida, esaurita o l'API non è disponibile, lo scraping commerciale del booking engine continua indipendentemente.

La chiave resta sul PC e viene letta **solo dall'agente Windows**, non dal frontend pubblico di Velora.
