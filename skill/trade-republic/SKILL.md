---
name: trade-republic
description: Read-only access to the user's Trade Republic account (portfolio with value and P/L, cash, transactions, dividends, open orders, savings plans, value history) and to market data (stock/ETF/crypto search, live quotes, price history, fundamentals, news). Use when the user asks about their Trade Republic portfolio or account, or about the price or performance of an instrument. Never places or cancels orders.
---

# Trade Republic (read-only)

`scripts/tr.py` is our own client, Python standard library only, talking directly to
`api.traderepublic.com` (REST for the session, WebSocket for data). No browser, server or
external dependency.

## Rules

- **Read-only.** Never place, change or cancel orders, savings plans, price alarms or
  watchlist entries, even if the user asks: `tr.py` cannot do it and must not be bypassed
  (no hand-written requests to the API). The user trades in the official app.
- **Login is the user's job.** `tr.py login` asks for phone number and PIN: never run it
  yourself and never ask for the PIN in chat. If the session is missing or expired, tell
  the user to run in their own terminal:
  `python ~/.claude/skills/trade-republic/scripts/tr.py login`
- Never read or print `~/.trade-republic/session.cookies`.
- No personalised investment advice: report data and calculations, not recommendations
  on what to buy or sell.
- Don't echo IBANs, account numbers or personal data unless needed: summarise.
- Answer in the user's language.

## Usage

```bash
python ~/.claude/skills/trade-republic/scripts/tr.py <command> [arguments]
```

JSON output on stdout. Errors start with `Error:` (exit code 1).

**Account (login required)**

| Command | Returns |
|---|---|
| `summary` | **start here**: positions with name, quantity, average buy-in, current price, value, P/L and totals, plus cash |
| `portfolio` | raw positions (`netSize`, `averageBuyIn`) |
| `accounts` | accounts (includes `securitiesAccountNumber`) |
| `cash` / `payout-cash` | cash / cash available for withdrawal |
| `history <range>` | portfolio value over time |
| `transactions [max=50]` | transactions: deposits, withdrawals, trades, dividends, card (newest first) |
| `transaction <id>` | details of one transaction (id from `transactions`) |
| `activity [max=50]` | activity log |
| `orders`, `savings-plans`, `price-alarms`, `watchlist` | the corresponding lists |

**Market (public, works without login)**

| Command | Returns |
|---|---|
| `search <text> [type]` | search; type: stock (default), fund, derivative, bond, crypto, privateFund, mutualFund |
| `instrument <ISIN>` | details and available exchanges (`exchangeIds`) |
| `stock-details <ISIN>` | company info and fundamentals |
| `price <ISIN> [exchange=LSX]` | live bid/ask/last |
| `price-history <ISIN> <range> [exchange=LSX]` | historical candles |
| `news <ISIN>` | news |

`range` for `history`: 1d, 5d, 1m, 6m, ytd, 1y, 5y, max.
`range` for `price-history`: 1d, 5d, 1m, 3m, 6m, 1y, 5y, max. If an instrument isn't on
LSX, use an exchange from `instrument` (e.g. TIB, XETR). Times are Unix timestamps in
milliseconds.

## Common errors

- `No session` / `Session expired`: the user must run `tr.py login` again.
- `BAD_SUBSCRIPTION_TYPE` or version rejections: Trade Republic changed the protocol.
  Updating `TR_APP_VERSION` / `TR_USER_AGENT` via environment variables may help.
- `No reply for ... within`: retry once; if it persists, the chosen exchange doesn't list
  the instrument.
