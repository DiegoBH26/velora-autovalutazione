# DNS email Velora

Il dominio transazionale creato in Resend è `velora.barbarhouse.com`, nella regione europea. Il tracciamento di apertura e dei clic è disattivato.

Aggiungere questi record nella gestione DNS di `barbarhouse.com`:

| Tipo | Nome/Host | Valore/Destinazione | Priorità |
|---|---|---|---:|
| TXT | `resend._domainkey.velora` | `p=MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDYh4fV41c+luGnB/eHdWb+8TS0qLXPhTneEBmsOZDOf0fG6tKoSOaDMyUVWqHqSJ7gF4qAZZNNTNNrQpJIMieGJBNgbsBre9C43jjUgLN50bDLIAfcirj/9R5gIVrSgCUbTb5kYlYw9YQoCEhjy1gpfUfg/xlfVTm4WIvnvExfgQIDAQAB` | — |
| MX | `send.velora` | `feedback-smtp.eu-west-1.amazonses.com` | 10 |
| TXT | `send.velora` | `v=spf1 include:amazonses.com ~all` | — |
| CNAME | `rsend.velora` | `send.forge.rmta.net` | — |

Usare il TTL automatico o quello predefinito del provider DNS. Dopo la propagazione, avviare la verifica del dominio in Resend.

Mittente applicativo previsto: `Velora <accesso@velora.barbarhouse.com>`.

