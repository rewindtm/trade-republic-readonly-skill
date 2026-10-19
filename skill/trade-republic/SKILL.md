---
name: trade-republic
description: Consulta in sola lettura il conto Trade Republic dell'utente (portafoglio con valore e P/L, liquidità, movimenti, dividendi, ordini aperti, piani di accumulo, storico valore) e i dati di mercato (ricerca titoli/ETF/crypto, quotazioni, storico prezzi, fondamentali, notizie). Usa quando l'utente chiede del suo portafoglio o conto Trade Republic o del prezzo/andamento di uno strumento. Non piazza né cancella ordini.
---

# Trade Republic (sola lettura)

`scripts/tr.py` è un client nostro, solo libreria standard di Python, che parla direttamente
con `api.traderepublic.com` (REST per la sessione, WebSocket per i dati). Nessun browser,
server o dipendenza esterna.

## Regole

- **Sola lettura.** Mai piazzare, modificare o cancellare ordini, piani di accumulo, allarmi
  o watchlist, nemmeno se l'utente lo chiede: `tr.py` non lo permette e non va aggirato
  (niente richieste scritte a mano verso l'API). Per operare l'utente usa l'app.
- **Login solo dall'utente.** `tr.py login` chiede telefono e PIN: non eseguirlo tu, non
  chiedere il PIN in chat. Se la sessione manca o è scaduta, di' all'utente di lanciare in
  un suo terminale: `python ~/.claude/skills/trade-republic/scripts/tr.py login`
- Non leggere né stampare `~/.trade-republic/session.cookies`.
- Niente consigli di investimento personalizzati: riporta dati e calcoli, non indicazioni
  su cosa comprare o vendere.
- Non riversare in chat IBAN, numeri di conto o dati personali se non servono: riassumi.

## Uso

```bash
python ~/.claude/skills/trade-republic/scripts/tr.py <comando> [argomenti]
```

Output JSON su stdout. Gli errori iniziano con `Errore:` (codice di uscita 1).

**Conto (serve login)**

| Comando | Restituisce |
|---|---|
| `summary` | **parti da qui**: posizioni con nome, quantità, prezzo medio, prezzo attuale, valore, P/L e totali, più liquidità |
| `portfolio` | posizioni grezze (`netSize`, `averageBuyIn`) |
| `accounts` | conti (contiene `securitiesAccountNumber`) |
| `cash` / `payout-cash` | liquidità / liquidità prelevabile |
| `history <range>` | valore storico del portafoglio |
| `transactions [max=50]` | movimenti: depositi, prelievi, trade, dividendi, carta (più recenti prima) |
| `transaction <id>` | dettaglio di un movimento (id preso da `transactions`) |
| `activity [max=50]` | log attività |
| `orders`, `savings-plans`, `price-alarms`, `watchlist` | liste corrispondenti |

**Mercato (pubblico, funziona anche senza login)**

| Comando | Restituisce |
|---|---|
| `search <testo> [tipo]` | ricerca; tipo: stock (default), fund, derivative, bond, crypto, privateFund, mutualFund |
| `instrument <ISIN>` | dettagli e borse disponibili (`exchangeIds`) |
| `stock-details <ISIN>` | società e fondamentali |
| `price <ISIN> [borsa=LSX]` | bid/ask/last live |
| `price-history <ISIN> <range> [borsa=LSX]` | candele storiche |
| `news <ISIN>` | notizie |

`range` per `history`: 1d, 5d, 1m, 6m, ytd, 1y, 5y, max.
`range` per `price-history`: 1d, 5d, 1m, 3m, 6m, 1y, 5y, max. Se uno strumento non è su LSX usa una borsa
presa da `instrument` (es. TIB, XETR). Gli orari sono timestamp Unix in millisecondi.

## Errori comuni

- `Nessuna sessione` / `Sessione scaduta`: l'utente deve rifare `tr.py login`.
- `BAD_SUBSCRIPTION_TYPE` o rifiuti di versione: Trade Republic ha cambiato il protocollo.
  Si può provare ad aggiornare `TR_APP_VERSION` / `TR_USER_AGENT` da variabile d'ambiente.
- `Nessuna risposta ... entro`: ritenta una volta; se persiste, la borsa scelta non quota
  lo strumento.
