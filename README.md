# Trade Republic — read-only skill for Claude Code

A [skill](https://docs.claude.com/en/docs/claude-code/skills) for Claude Code that lets you ask,
in plain language, about your **Trade Republic** account (portfolio, value and profit/loss,
cash, transactions, dividends, open orders, savings plans, historical performance) and about
the markets (stock/ETF/crypto search, live quotes, price history, fundamentals, news).

- **Read-only by design**: it cannot buy, sell, cancel orders, or touch savings plans, price
  alarms or the watchlist.
- **Zero dependencies**: a single Python file using only the standard library. No `pip install`,
  no automated browsers, no local servers, no executables.
- **Your credentials stay yours**: you log in yourself in the terminal, the PIN is never stored,
  and the login is confirmed in the app on your phone.

> Unofficial project, not affiliated with Trade Republic Bank GmbH. It relies on a private,
> undocumented API that Trade Republic can change at any time. Use at your own risk.

---

## Contents

1. [Examples](#examples)
2. [How it works](#how-it-works)
3. [Security and privacy](#security-and-privacy)
4. [Installation](#installation)
5. [Login](#login)
6. [Command reference](#command-reference)
7. [Configuration](#configuration)
8. [Troubleshooting](#troubleshooting)
9. [Known limitations](#known-limitations)
10. [Repository layout](#repository-layout)

---

## Examples

Questions you can ask Claude Code once the skill is installed:

- "What is my Trade Republic portfolio worth and how much am I up or down?"
- "How much cash do I have, and how much can I withdraw?"
- "List the dividends and interest I received this year."
- "How has my portfolio performed over the last 6 months?"
- "Do I have any open orders or active savings plans?"
- "Find the Vanguard FTSE All-World ETF and show me its 1-year chart."
- "What is Apple trading at right now, and what does the company do?"

## How it works

```
Claude Code ──► SKILL.md (rules + commands) ──► scripts/tr.py ──┬─ HTTPS ─► api.traderepublic.com  (login, session, history)
                                                                └─ WSS ───► api.traderepublic.com  (portfolio, transactions, prices)
```

### `SKILL.md`
Tells Claude **when** to use the skill, **which commands** exist and **which rules** to follow:

- never trade or change the account, and never bypass `tr.py` with hand-written requests;
- never run the login on your behalf or ask for your PIN in chat;
- never read the session file;
- no personalised investment advice, only data and calculations;
- don't echo IBANs, account numbers or personal data unless needed.

### `scripts/tr.py`
A client written from scratch, ~600 lines, Python 3.10+ standard library only:

- **Login**: uses Trade Republic's "v2" web login flow (phone number + PIN, then confirmation
  in the app, plus an authenticator code if you have one enabled). This flow does not require
  the AWS WAF anti-bot token, so no browser is needed.
- **Session**: session cookies are saved to `~/.trade-republic/session.cookies` and refreshed
  automatically on every command (`GET /api/v1/auth/web/session`). When Trade Republic
  invalidates the session, you simply log in again.
- **WebSocket**: a minimal RFC 6455 implementation (handshake with `Sec-WebSocket-Accept`
  check, masked frames, fragmented messages, ping/pong) speaking Trade Republic's protocol:
  `connect` → `sub <id> {json}` → `A`/`D`/`E` reply → `unsub`.
- **Read-only**: every subscription is checked against an explicit allow-list
  (`READ_ONLY_TYPES`). Types such as `simpleCreateOrder`, `cancelOrder`, `createSavingsPlan`,
  `createPriceAlarm` and `addToWatchlist` are not on the list and are rejected before the server
  is even contacted. The only REST calls are login, session refresh and the portfolio history
  chart.
- **Summary**: `summary` combines positions, instrument name, current price, value, absolute and
  percentage P/L, totals and cash into a single JSON document.

Market commands (search, quotes, history, fundamentals, news) use public data and work
**without logging in**.

## Security and privacy

| Topic | Behaviour |
|---|---|
| PIN | Typed by you via `getpass` (hidden), sent only to `api.traderepublic.com`, never stored. |
| Session | Cookies in `~/.trade-republic/session.cookies` (mode `600` on macOS/Linux). Anyone holding this file can **read** your account while the session is valid: don't share or sync it. `tr.py logout` deletes it. |
| Network | Only `api.traderepublic.com` over HTTPS/WSS with system certificate verification. No telemetry, no third-party services. |
| Trading | Impossible from `tr.py`: there is no code for orders, savings plans, alarms or the watchlist. |
| Open ports | None: there is no local server. |

Note: the Trade Republic web session itself **would** allow trading (the official web app does
it). The restriction lives in this client and in the skill's rules. Treat the session file as
you would a browser with your account open.

## Installation

Requirements: Python ≥ 3.10 and Claude Code.

```bash
git clone https://github.com/rewindtm/trade-republic-readonly-skill.git
cp -r trade-republic-readonly-skill/skill/trade-republic ~/.claude/skills/
```

Windows (PowerShell):

```powershell
git clone https://github.com/rewindtm/trade-republic-readonly-skill.git
Copy-Item -Recurse trade-republic-readonly-skill\skill\trade-republic $HOME\.claude\skills\
```

Quick test without logging in (public data):

```bash
python ~/.claude/skills/trade-republic/scripts/tr.py price US0378331005
```

## Login

```bash
python ~/.claude/skills/trade-republic/scripts/tr.py login
```

1. Enter your phone number with the international prefix (e.g. `+49151...`).
2. Enter your Trade Republic PIN (it is not shown while typing).
3. If you use an authenticator app, enter the code.
4. Confirm the login in the Trade Republic app on your phone.
5. You will see `Accesso riuscito` ("login successful").

When the session expires, commands reply `Sessione scaduta` ("session expired"): log in again.
To log out: `tr.py logout`.

> The CLI messages are in Italian; the JSON output is in the language set by `TR_LOCALE`.

## Command reference

```bash
python tr.py help
python tr.py <command> [arguments]
```

Output is JSON on stdout. Errors start with `Errore:` and exit with code 1.

### Account (login required)

| Command | Description |
|---|---|
| `summary` | Positions with name, quantity, average buy-in, current price, value, P/L and totals, plus cash |
| `portfolio` | Raw positions (`netSize`, `averageBuyIn`, category) |
| `accounts` | Accounts, including `securitiesAccountNumber` and `cashAccountNumber` |
| `cash` | Cash balance |
| `payout-cash` | Cash available for withdrawal |
| `history <range>` | Portfolio value over time: `1d`, `5d`, `1m`, `6m`, `ytd`, `1y`, `5y`, `max` |
| `transactions [max=50]` | Transactions: deposits, withdrawals, buys/sells, dividends, interest, card |
| `transaction <id>` | Details of a single transaction (`id` from `transactions`) |
| `activity [max=50]` | Account activity log |
| `orders` | Open orders |
| `savings-plans` | Savings plans |
| `price-alarms` | Price alarms |
| `watchlist` | Watchlist |

### Market (public, no login needed)

| Command | Description |
|---|---|
| `search <text> [type]` | Search. `type`: `stock` (default), `fund`, `derivative`, `bond`, `crypto`, `privateFund`, `mutualFund` |
| `instrument <ISIN>` | Details and available exchanges (`exchangeIds`) |
| `stock-details <ISIN>` | Company description and fundamentals |
| `price <ISIN> [exchange=LSX]` | Live quote: bid, ask, last |
| `price-history <ISIN> <range> [exchange=LSX]` | Historical candles: `1d`, `5d`, `1m`, `3m`, `6m`, `1y`, `5y`, `max` |
| `news <ISIN>` | News |

Examples:

```bash
python tr.py summary
python tr.py history 1y
python tr.py transactions 200
python tr.py search "FTSE All-World" fund
python tr.py price IE00BK5BQT80
python tr.py price-history US0378331005 6m XETR
```

All times are Unix timestamps in milliseconds; amounts are decimal strings.

## Configuration

Optional environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `TR_STATE_DIR` | `~/.trade-republic` | Where the session is stored |
| `TR_LOCALE` | `it` | Language of responses (names, descriptions, news) |
| `TR_TIMEZONE` | `Europe/Rome` | Time zone declared at login |
| `TR_APP_VERSION` | current web frontend version | Bump if Trade Republic starts rejecting old versions |
| `TR_PLATFORM` | `web-pro` | Platform declared at login |
| `TR_USER_AGENT` | recent Chrome | HTTP user agent |

The last three exist because Trade Republic regularly updates its frontend: if login stops
working, updating one value often fixes it without touching the code.

## Troubleshooting

| Message | Cause and fix |
|---|---|
| `Nessuna sessione` (no session) | You haven't run `tr.py login` yet. |
| `Sessione scaduta o non valida` (session expired) | Trade Republic closed the session (timeout, another web login): log in again. |
| `Login rifiutato: ...` (login rejected) | Wrong number or PIN, too many attempts, or rejected version (see `TR_APP_VERSION`). |
| `Richiesta bloccata dal firewall AWS` (blocked by AWS WAF) | Trade Republic extended its anti-bot check to the v2 login: the client needs an update. |
| `BAD_SUBSCRIPTION_TYPE` | Trade Republic renamed a subscription: the client needs an update. |
| `Nessuna risposta per ticker` (no ticker reply) | The chosen exchange doesn't list the instrument: pick one from `instrument`. |
| `Intervallo non valido` (invalid range) | That range isn't supported by that command (see tables above). |

## Known limitations

- `summary` uses the latest price on LSX (or the first available exchange), which may differ
  slightly from the value shown in the app.
- Bonds are quoted as a percentage of par and divided by 100: double-check values if you hold any.
- Only the main securities account is handled; business or multiple accounts can't be selected.
- The API is undocumented: a change on Trade Republic's side can break individual commands.

## Repository layout

```
skill/trade-republic/
├── SKILL.md          instructions and rules for Claude Code
└── scripts/tr.py     read-only client (standard library only)
README.md
LICENSE               MIT
```

## Acknowledgements

Knowledge of the protocol comes from the open-source community, in particular
[pytr](https://github.com/pytr-org/pytr) and
[trade-republic-uapi](https://github.com/4strium/trade-republic-uapi) (both MIT). The code in
this repository is written from scratch.

## License

MIT
