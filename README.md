# Trade Republic — skill in sola lettura per Claude Code

Una [skill](https://docs.claude.com/en/docs/claude-code/skills) per Claude Code che permette
di chiedere in linguaggio naturale informazioni sul proprio conto **Trade Republic**
(portafoglio, valore e guadagno/perdita, liquidità, movimenti, dividendi, ordini aperti, piani
di accumulo, andamento storico) e sui mercati (ricerca titoli/ETF/crypto, quotazioni live,
storico prezzi, fondamentali, notizie).

- **Sola lettura per costruzione**: non può comprare, vendere, cancellare ordini, toccare
  piani di accumulo, allarmi o watchlist.
- **Zero dipendenze**: un unico file Python che usa solo la libreria standard. Niente `pip install`,
  niente browser automatizzati, niente server locali, niente eseguibili.
- **Le credenziali restano tue**: il login lo fai tu nel terminale, il PIN non viene salvato
  e la conferma avviene nell'app sul telefono.

> Progetto non ufficiale, non affiliato a Trade Republic Bank GmbH. Usa un'API privata e non
> documentata che Trade Republic può cambiare in qualsiasi momento. Usalo a tuo rischio.

---

## Indice

1. [Esempi](#esempi)
2. [Come funziona](#come-funziona)
3. [Sicurezza e privacy](#sicurezza-e-privacy)
4. [Installazione](#installazione)
5. [Login](#login)
6. [Riferimento comandi](#riferimento-comandi)
7. [Configurazione](#configurazione)
8. [Risoluzione problemi](#risoluzione-problemi)
9. [Limiti noti](#limiti-noti)
10. [Struttura della repo](#struttura-della-repo)

---

## Esempi

Domande che puoi fare a Claude Code una volta installata la skill:

- «Quanto vale il mio portafoglio Trade Republic e quanto sto guadagnando o perdendo?»
- «Quanta liquidità ho disponibile e quanta posso prelevare?»
- «Elencami i dividendi e gli interessi ricevuti quest'anno.»
- «Com'è andato il portafoglio negli ultimi 6 mesi?»
- «Ho ordini aperti o piani di accumulo attivi?»
- «Cerca l'ETF Vanguard FTSE All-World e mostrami l'andamento a 1 anno.»
- «Quanto quota adesso Apple e cosa fa l'azienda?»

## Come funziona

```
Claude Code ──► SKILL.md (regole + comandi) ──► scripts/tr.py ──┬─ HTTPS ─► api.traderepublic.com  (login, sessione, storico)
                                                                └─ WSS ───► api.traderepublic.com  (portafoglio, movimenti, prezzi)
```

### `SKILL.md`
Dice a Claude **quando** usare la skill, **quali comandi** esistono e **quali regole** rispettare:

- mai operare sul conto, né aggirare `tr.py` con richieste scritte a mano;
- mai eseguire il login al posto tuo o chiederti il PIN in chat;
- mai leggere il file di sessione;
- niente consigli di investimento personalizzati, solo dati e calcoli;
- non riportare IBAN, numeri di conto o dati personali se non servono.

### `scripts/tr.py`
Client scritto da zero, ~600 righe, solo libreria standard di Python 3.10+:

- **Login** — usa il flusso web "v2" di Trade Republic: numero + PIN, poi conferma nell'app
  (più l'eventuale codice dell'app di autenticazione). Questo flusso non richiede il token
  anti-bot AWS WAF, quindi non serve nessun browser.
- **Sessione** — i cookie di sessione vengono salvati in `~/.trade-republic/session.cookies`
  e rinnovati automaticamente a ogni comando (`GET /api/v1/auth/web/session`). Quando
  Trade Republic la invalida, si rifà il login.
- **WebSocket** — implementazione minimale di RFC 6455 (handshake con verifica di
  `Sec-WebSocket-Accept`, frame mascherati, messaggi frammentati, ping/pong) usata con il
  protocollo di Trade Republic: `connect` → `sub <id> {json}` → risposta `A`/`D`/`E` → `unsub`.
- **Sola lettura** — ogni sottoscrizione passa da un controllo su una lista esplicita di tipi
  ammessi (`READ_ONLY_TYPES`). Tipi come `simpleCreateOrder`, `cancelOrder`,
  `createSavingsPlan`, `createPriceAlarm`, `addToWatchlist` non sono in lista e vengono
  rifiutati prima ancora di contattare il server. Le uniche chiamate REST sono login,
  rinnovo sessione e grafico storico del portafoglio.
- **Riepilogo** — `summary` unisce posizioni, nome dello strumento, prezzo attuale, valore,
  P/L assoluto e percentuale, totali e liquidità in un unico JSON.

I comandi di mercato (ricerca, prezzi, storico, fondamentali, notizie) usano dati pubblici
e funzionano anche **senza login**.

## Sicurezza e privacy

| Aspetto | Comportamento |
|---|---|
| PIN | Digitato da te con `getpass` (non visibile), inviato solo a `api.traderepublic.com`, mai salvato. |
| Sessione | Cookie in `~/.trade-republic/session.cookies` (permessi `600` su macOS/Linux). Chi ha questo file può **leggere** il tuo conto finché la sessione è valida: non condividerlo e non sincronizzarlo. `tr.py logout` lo elimina. |
| Rete | Solo `api.traderepublic.com` su HTTPS/WSS con verifica dei certificati di sistema. Nessuna telemetria, nessun servizio di terze parti. |
| Operatività | Impossibile da `tr.py`: nessun codice per ordini, piani, allarmi o watchlist. |
| Porte aperte | Nessuna: non c'è un server locale. |

Nota: la sessione web di Trade Republic in sé **permetterebbe** di operare (lo fa il sito web
ufficiale). Il limite è nel nostro client e nelle regole della skill. Tratta il file di
sessione come tratteresti un browser con il conto aperto.

## Installazione

Requisiti: Python ≥ 3.10 e Claude Code.

```bash
git clone https://github.com/rewindtm/trade-republic-readonly-skill.git
cp -r trade-republic-readonly-skill/skill/trade-republic ~/.claude/skills/
```

Windows (PowerShell):

```powershell
git clone https://github.com/rewindtm/trade-republic-readonly-skill.git
Copy-Item -Recurse trade-republic-readonly-skill\skill\trade-republic $HOME\.claude\skills\
```

Prova senza login (dati pubblici):

```bash
python ~/.claude/skills/trade-republic/scripts/tr.py price US0378331005
```

## Login

```bash
python ~/.claude/skills/trade-republic/scripts/tr.py login
```

1. Inserisci il numero con prefisso internazionale (es. `+39333...`).
2. Inserisci il PIN di Trade Republic (non viene mostrato mentre lo digiti).
3. Se usi un'app di autenticazione, inserisci il codice.
4. Conferma l'accesso nell'app Trade Republic sul telefono.
5. Compare `Accesso riuscito`.

Quando la sessione scade, i comandi rispondono `Sessione scaduta`: ripeti il login.
Per disconnetterti: `tr.py logout`.

## Riferimento comandi

```bash
python tr.py help
python tr.py <comando> [argomenti]
```

Output in JSON su stdout. Gli errori iniziano con `Errore:` e restituiscono codice di uscita 1.

### Conto (serve il login)

| Comando | Descrizione |
|---|---|
| `summary` | Posizioni con nome, quantità, prezzo medio di carico, prezzo attuale, valore, P/L e totali, più liquidità |
| `portfolio` | Posizioni grezze (`netSize`, `averageBuyIn`, categoria) |
| `accounts` | Conti, con `securitiesAccountNumber` e `cashAccountNumber` |
| `cash` | Liquidità |
| `payout-cash` | Liquidità prelevabile |
| `history <range>` | Valore storico del portafoglio — `1d`, `5d`, `1m`, `6m`, `ytd`, `1y`, `5y`, `max` |
| `transactions [max=50]` | Movimenti: depositi, prelievi, acquisti/vendite, dividendi, interessi, carta |
| `transaction <id>` | Dettaglio di un movimento (`id` preso da `transactions`) |
| `activity [max=50]` | Log attività del conto |
| `orders` | Ordini aperti |
| `savings-plans` | Piani di accumulo |
| `price-alarms` | Allarmi di prezzo |
| `watchlist` | Watchlist |

### Mercato (pubblico, anche senza login)

| Comando | Descrizione |
|---|---|
| `search <testo> [tipo]` | Ricerca. `tipo`: `stock` (default), `fund`, `derivative`, `bond`, `crypto`, `privateFund`, `mutualFund` |
| `instrument <ISIN>` | Dettagli e borse disponibili (`exchangeIds`) |
| `stock-details <ISIN>` | Descrizione della società e fondamentali |
| `price <ISIN> [borsa=LSX]` | Quotazione live: bid, ask, last |
| `price-history <ISIN> <range> [borsa=LSX]` | Candele storiche — `1d`, `5d`, `1m`, `3m`, `6m`, `1y`, `5y`, `max` |
| `news <ISIN>` | Notizie |

Esempi:

```bash
python tr.py summary
python tr.py history 1y
python tr.py transactions 200
python tr.py search "FTSE All-World" fund
python tr.py price IE00BK5BQT80
python tr.py price-history US0378331005 6m XETR
```

Tutti gli orari sono timestamp Unix in millisecondi; gli importi sono stringhe decimali.

## Configurazione

Variabili d'ambiente opzionali:

| Variabile | Default | A cosa serve |
|---|---|---|
| `TR_STATE_DIR` | `~/.trade-republic` | Dove salvare la sessione |
| `TR_LOCALE` | `it` | Lingua delle risposte (nomi, descrizioni, notizie) |
| `TR_TIMEZONE` | `Europe/Rome` | Fuso orario dichiarato al login |
| `TR_APP_VERSION` | versione del frontend web | Da aggiornare se Trade Republic rifiuta versioni vecchie |
| `TR_PLATFORM` | `web-pro` | Piattaforma dichiarata al login |
| `TR_USER_AGENT` | Chrome recente | User agent HTTP |

Le ultime tre esistono perché Trade Republic cambia periodicamente il frontend: se il login
smette di funzionare, spesso basta aggiornare un valore senza toccare il codice.

## Risoluzione problemi

| Messaggio | Causa e rimedio |
|---|---|
| `Nessuna sessione` | Non hai ancora fatto `tr.py login`. |
| `Sessione scaduta o non valida` | Trade Republic ha chiuso la sessione (tempo, altro login web): rifai il login. |
| `Login rifiutato: ...` | Numero o PIN errati, troppi tentativi o versione rifiutata (vedi `TR_APP_VERSION`). |
| `Richiesta bloccata dal firewall AWS` | Trade Republic ha esteso il controllo anti-bot al login v2: serve un aggiornamento del client. |
| `BAD_SUBSCRIPTION_TYPE` | Trade Republic ha rinominato una sottoscrizione: serve un aggiornamento del client. |
| `Nessuna risposta per ticker` | La borsa scelta non quota lo strumento: usa una borsa da `instrument`. |
| `Intervallo non valido` | L'intervallo non è supportato da quel comando (vedi tabelle sopra). |

## Limiti noti

- `summary` usa l'ultimo prezzo su LSX (o sulla prima borsa disponibile); può differire
  leggermente dal valore mostrato dall'app.
- Le obbligazioni vengono riportate in percentuale del nominale e divise per 100: verifica i
  valori se ne possiedi.
- È gestito il conto titoli principale; conti aziendali o multipli non sono selezionabili.
- L'API non è documentata: un cambio lato Trade Republic può rompere singoli comandi.

## Struttura della repo

```
skill/trade-republic/
├── SKILL.md          istruzioni e regole per Claude Code
└── scripts/tr.py     client in sola lettura (solo libreria standard)
README.md
LICENSE               MIT
```

## Ringraziamenti

La conoscenza del protocollo deriva dal lavoro della community open source, in particolare
[pytr](https://github.com/pytr-org/pytr) e
[trade-republic-uapi](https://github.com/4strium/trade-republic-uapi) (entrambi MIT). Il codice
di questa repo è scritto da zero.

## Licenza

MIT
