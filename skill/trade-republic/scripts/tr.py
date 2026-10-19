"""Read-only Trade Republic client, Python standard library only.

Talks directly to api.traderepublic.com (REST for login, WebSocket for data),
with no browser, local server or external dependencies.

It contains NO operation that changes the account: no orders, savings plans,
price alarms or watchlist edits. Allowed subscriptions are listed in
READ_ONLY_TYPES; anything else is rejected before a connection is opened.

Usage:
    python tr.py login              # interactive: phone, PIN, confirm in the app
    python tr.py <command> [...]    # see: python tr.py help
    python tr.py logout
"""

import base64
import getpass
import hashlib
import http.cookiejar
import json
import os
import platform
import socket
import ssl
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

HOST = "api.traderepublic.com"
API = f"https://{HOST}"
STATE_DIR = Path(os.getenv("TR_STATE_DIR") or Path.home() / ".trade-republic")
COOKIE_FILE = STATE_DIR / "session.cookies"
LOCALE = os.getenv("TR_LOCALE", "it")

# Values the web frontend sends. Trade Republic may start rejecting stale ones:
# they can then be updated via environment variables without touching the code.
APP_VERSION = os.getenv("TR_APP_VERSION", "2.2631.13")
PLATFORM = os.getenv("TR_PLATFORM", "web-pro")
USER_AGENT = os.getenv(
    "TR_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
)

READ_ONLY_TYPES = {
    "accountPairs",
    "aggregateHistoryLight",
    "availableCash",
    "availableCashForPayout",
    "cash",
    "compactPortfolioByType",
    "instrument",
    "neonNews",
    "neonSearch",
    "orders",
    "priceAlarms",
    "savingsPlans",
    "stockDetails",
    "ticker",
    "timelineActivityLog",
    "timelineDetailV2",
    "timelineTransactions",
    "watchlist",
}

HISTORY_RANGES = ("1d", "5d", "1m", "6m", "ytd", "1y", "5y", "max")
PRICE_RANGES = ("1d", "5d", "1m", "3m", "6m", "1y", "5y", "max")
ASSET_TYPES = ("stock", "fund", "derivative", "bond", "crypto", "privateFund", "mutualFund")


class TRError(Exception):
    pass


# --------------------------------------------------------------------------- REST


def _cookie_jar() -> http.cookiejar.LWPCookieJar:
    jar = http.cookiejar.LWPCookieJar(str(COOKIE_FILE))
    if COOKIE_FILE.exists():
        jar.load(ignore_discard=True, ignore_expires=True)
    return jar


def _save_cookies(jar: http.cookiejar.LWPCookieJar) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    jar.save(ignore_discard=True, ignore_expires=True)
    if os.name != "nt":
        COOKIE_FILE.chmod(0o600)


def _device_info() -> str:
    seed = "|".join([str(socket.gethostname()), platform.machine(), platform.system(), str(Path.home())])
    offset = datetime.now().astimezone().utcoffset()
    device = {
        "stableDeviceId": hashlib.sha512(seed.encode()).hexdigest(),
        "browser": "Chrome",
        "browserVersion": "146.0.0.0",
        "os": platform.system(),
        "osVersion": platform.release(),
        "timezone": os.getenv("TR_TIMEZONE", "Europe/Rome"),
        "timezoneOffset": -int(offset.total_seconds() // 60) if offset else 0,
        "screen": "1920x1080x24",
        "preferredLanguages": [LOCALE],
        "numberOfCores": os.cpu_count() or 1,
    }
    return base64.b64encode(json.dumps(device).encode()).decode()


class Rest:
    def __init__(self) -> None:
        self.jar = _cookie_jar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.login_headers = {
            "X-TR-Device-Info": _device_info(),
            "X-TR-App-Version": APP_VERSION,
            "X-Tr-Platform": PLATFORM,
        }

    def request(self, method: str, path: str, body: object = None, login: bool = False) -> tuple[int, object]:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": LOCALE,
            "Origin": "https://app.traderepublic.com",
            "Referer": "https://app.traderepublic.com/",
        }
        if login:
            headers.update(self.login_headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=30) as resp:
                status, raw = resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
            if status == 405 and "awselb" in (e.headers.get("server") or "").lower():
                raise TRError("Request blocked by Trade Republic's AWS firewall (WAF).") from None
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode("utf-8", "replace")
        return status, payload

    def cookie_header(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self.jar if c.domain.endswith("traderepublic.com"))

    def refresh(self) -> None:
        if not COOKIE_FILE.exists():
            raise TRError("No session: run `python tr.py login` first.")
        status, _ = self.request("GET", "/api/v1/auth/web/session")
        if status >= 400:
            raise TRError(f"Session expired or invalid (HTTP {status}): run `python tr.py login` again.")
        _save_cookies(self.jar)


def _login_error(payload: object, status: int) -> str:
    try:
        return payload["errors"][0]["errorCode"]  # type: ignore[index]
    except (TypeError, KeyError, IndexError):
        return f"HTTP {status}"


def login() -> None:
    if not sys.stdin.isatty():
        raise TRError("Login must be done by the user in an interactive terminal.")
    phone = input("Phone number (international format, e.g. +49...): ").strip()
    pin = getpass.getpass("Trade Republic PIN (hidden, never stored): ").strip()

    rest = Rest()
    rest.jar.clear()
    status, payload = rest.request("POST", "/api/v2/auth/web/login", {"phoneNumber": phone, "pin": pin}, login=True)
    pin = ""
    if status >= 400 or not isinstance(payload, dict) or "processId" not in payload:
        raise TRError(f"Login rejected: {_login_error(payload, status)}")
    process_id = payload["processId"]
    deadline = time.time() + int(payload.get("countdownInSeconds") or 120)
    process_path = f"/api/v2/auth/web/login/processes/{process_id}"

    status, process = rest.request("GET", process_path, login=True)
    if status < 400 and isinstance(process, dict) and process.get("requiredAction") == "AUTHENTICATOR_VERIFICATION":
        code = input("Authenticator app code: ").strip()
        status, payload = rest.request("POST", f"{process_path}/authenticator-verification", {"code": code}, login=True)
        if status >= 400:
            raise TRError(f"Code rejected: {_login_error(payload, status)}")

    print("Confirm the login in the Trade Republic app on your phone...")
    while True:
        status, process = rest.request("GET", process_path, login=True)
        if status >= 400 or not isinstance(process, dict):
            raise TRError(f"Login aborted: {_login_error(process, status)}")
        state = process.get("status")
        if state in ("CONFIRMED", "COMPLETED"):
            break
        if state != "PENDING":
            raise TRError(f"Unexpected login state: {state}")
        if time.time() > deadline:
            raise TRError("Timed out: the login was not confirmed in the app.")
        time.sleep(2)

    _save_cookies(rest.jar)
    rest.refresh()
    print(f"Login successful. Session saved to {COOKIE_FILE}")


def logout() -> None:
    if COOKIE_FILE.exists():
        COOKIE_FILE.unlink()
    print("Local session deleted.")


# ---------------------------------------------------------------------- WebSocket


class WebSocket:
    """Minimal WebSocket client (RFC 6455), only for api.traderepublic.com."""

    def __init__(self, cookie: str) -> None:
        raw = socket.create_connection((HOST, 443), timeout=30)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=HOST)
        key = base64.b64encode(os.urandom(16)).decode()
        handshake = (
            "GET / HTTP/1.1\r\n"
            f"Host: {HOST}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "Origin: https://app.traderepublic.com\r\n"
            f"User-Agent: {USER_AGENT}\r\n"
            f"Cookie: {cookie}\r\n\r\n"
        )
        self.sock.sendall(handshake.encode())
        response = b""
        while b"\r\n\r\n" not in response:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise TRError("WebSocket connection closed during the handshake.")
            response += chunk
        head, self.buffer = response.split(b"\r\n\r\n", 1)
        status_line = head.split(b"\r\n", 1)[0].decode(errors="replace")
        if " 101 " not in status_line + " ":
            raise TRError(f"WebSocket handshake rejected: {status_line}")
        expected = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()
        ).decode()
        if expected.encode() not in head:
            raise TRError("Invalid WebSocket handshake.")

    def _read(self, n: int) -> bytes:
        while len(self.buffer) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise TRError("WebSocket connection closed by the server.")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def _send_frame(self, opcode: int, payload: bytes) -> None:
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack("!Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + mask + masked)

    def send(self, text: str) -> None:
        self._send_frame(0x1, text.encode())

    def recv(self) -> str:
        message = b""
        while True:
            b1, b2 = self._read(2)
            fin, opcode = b1 & 0x80, b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", self._read(8))[0]
            mask = self._read(4) if b2 & 0x80 else None
            payload = self._read(n)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 0x9:
                self._send_frame(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            if opcode == 0x8:
                raise TRError("WebSocket connection closed by the server.")
            message += payload
            if fin:
                return message.decode("utf-8")

    def close(self) -> None:
        try:
            self._send_frame(0x8, b"")
            self.sock.close()
        except OSError:
            pass


class Client:
    def __init__(self, authenticated: bool = True) -> None:
        self.rest = rest = Rest()
        if authenticated:
            rest.refresh()
        self.ws = WebSocket(rest.cookie_header() if authenticated else "")
        hello = {
            "locale": LOCALE,
            "platformId": "webtrading",
            "platformVersion": "chrome - 146.0.0",
            "clientId": "app.traderepublic.com",
            "clientVersion": APP_VERSION,
        }
        self.ws.send(f"connect 31 {json.dumps(hello)}")
        reply = self.ws.recv()
        if reply != "connected":
            raise TRError(f"Connection rejected: {reply[:200]}")
        self.next_id = 1

    def get(self, payload: dict, timeout: float = 15.0) -> object:
        if payload.get("type") not in READ_ONLY_TYPES:
            raise TRError(f"Subscription not allowed: {payload.get('type')}")
        sub_id = str(self.next_id)
        self.next_id += 1
        self.ws.send(f"sub {sub_id} {json.dumps(payload)}")
        self.ws.sock.settimeout(timeout)
        try:
            while True:
                message = self.ws.recv()
                msg_id, _, rest = message.partition(" ")
                if msg_id != sub_id:
                    continue
                code, _, body = rest.partition(" ")
                if code in ("A", "D"):
                    # The first reply always carries the full state (A).
                    return json.loads(body) if body else {}
                if code == "E":
                    raise TRError(f"Trade Republic error for {payload['type']}: {body[:300]}")
        except socket.timeout:
            raise TRError(f"No reply for {payload['type']} within {timeout:.0f}s.") from None
        finally:
            self.ws.sock.settimeout(30)
            self.ws.send(f"unsub {sub_id}")

    def close(self) -> None:
        self.ws.close()

    # ------------------------------------------------------------------ helpers

    def accounts(self) -> list[dict]:
        data = self.get({"type": "accountPairs"})
        return data.get("accounts", []) if isinstance(data, dict) else []

    def sec_acc_no(self) -> str:
        accounts = [a for a in self.accounts() if a.get("securitiesAccountNumber")]
        accounts.sort(key=lambda a: a.get("productType") != "DEFAULT")
        if not accounts:
            raise TRError("No securities account found.")
        return accounts[0]["securitiesAccountNumber"]

    def positions(self) -> list[dict]:
        data = self.get({"type": "compactPortfolioByType", "secAccNo": self.sec_acc_no()})
        out = []
        for category in data.get("categories", []) if isinstance(data, dict) else []:
            for pos in category.get("positions", []):
                pos.setdefault("instrumentId", pos.get("isin"))
                pos["category"] = category.get("categoryType")
                out.append(pos)
        return out

    def history(self, range_: str) -> dict:
        result = {}
        for account in self.accounts():
            sec_acc_no = account.get("securitiesAccountNumber")
            if not sec_acc_no:
                continue
            query = urllib.parse.urlencode(
                {"secAccNo": sec_acc_no, "range": range_, "currency": account.get("currency", "EUR")}
            )
            path = f"/api-gateway/portfolio-chart/v2/chart?{query}"
            status, data = self.rest.request("GET", path, login=True)
            if status >= 400:
                # The chart service sometimes answers with a transient error.
                time.sleep(1.5)
                status, data = self.rest.request("GET", path, login=True)
            if status >= 400 or not isinstance(data, dict):
                raise TRError(f"History unavailable (HTTP {status}).")
            for point in data.get("points", []):
                cash, net = _dec(point.get("cashBalance")), _dec(point.get("netValue"))
                if cash is not None and net is not None:
                    point["totalValue"] = str(cash + net)
            result[sec_acc_no] = data
        return result

    def paged(self, kind: str, limit: int) -> list[dict]:
        items: list[dict] = []
        after = None
        while len(items) < limit:
            data = self.get({"type": kind, "after": after})
            if not isinstance(data, dict):
                break
            items.extend(data.get("items", []))
            after = (data.get("cursors") or {}).get("after")
            if not after:
                break
        return items[:limit]


def _dec(value: object) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def summary(client: Client) -> dict:
    positions = client.positions()
    total_value = total_cost = Decimal(0)
    rows = []
    for pos in positions:
        isin = pos["instrumentId"]
        info = client.get({"type": "instrument", "id": isin})
        name = info.get("shortName") or info.get("name") or isin if isinstance(info, dict) else isin
        exchanges = info.get("exchangeIds", []) if isinstance(info, dict) else []
        exchange = "LSX" if "LSX" in exchanges else (exchanges[0] if exchanges else "LSX")
        price = None
        try:
            ticker = client.get({"type": "ticker", "id": f"{isin}.{exchange}"}, timeout=8)
            if isinstance(ticker, dict):
                price = _dec((ticker.get("last") or ticker.get("bid") or {}).get("price"))
                if price is not None and info.get("typeId") == "bond":
                    price /= 100
        except TRError:
            pass
        size = _dec(pos.get("netSize")) or Decimal(0)
        avg = _dec(pos.get("averageBuyIn")) or Decimal(0)
        cost = (size * avg).quantize(Decimal("0.01"))
        value = (size * price).quantize(Decimal("0.01")) if price is not None else None
        total_cost += cost
        if value is not None:
            total_value += value
        rows.append({
            "name": name,
            "isin": isin,
            "category": pos.get("category"),
            "quantity": str(size),
            "averageBuyIn": str(avg),
            "price": str(price) if price is not None else None,
            "exchange": exchange,
            "cost": str(cost),
            "value": str(value) if value is not None else None,
            "pnl": str(value - cost) if value is not None else None,
            "pnlPct": f"{((value / cost) - 1) * 100:.2f}" if value is not None and cost else None,
        })
    rows.sort(key=lambda r: Decimal(r["value"] or r["cost"]), reverse=True)
    cash = client.get({"type": "cash"})
    return {
        "positions": rows,
        "totals": {
            "cost": str(total_cost),
            "value": str(total_value),
            "pnl": str(total_value - total_cost),
            "note": "Values at current prices on the listed exchange; positions without a price are excluded from the value.",
        },
        "cash": cash,
    }


# --------------------------------------------------------------------------- CLI


def _need(args: list[str], names: list[str]) -> list[str]:
    if len(args) < len(names):
        raise TRError(f"Missing arguments: {' '.join(f'<{n}>' for n in names)}")
    return args


def _range(value: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise TRError(f"Invalid range: {value}. Allowed: {', '.join(allowed)}")
    return value


COMMANDS = {
    "summary": ("", "positions with name, current price, value and P/L, plus cash"),
    "accounts": ("", "accounts (includes securitiesAccountNumber)"),
    "portfolio": ("", "raw positions (quantity, average buy-in)"),
    "cash": ("", "cash balance"),
    "payout-cash": ("", "cash available for withdrawal"),
    "history": ("<range>", f"portfolio value over time ({'/'.join(HISTORY_RANGES)})"),
    "transactions": ("[max=50]", "transactions (deposits, withdrawals, trades, dividends, card)"),
    "transaction": ("<id>", "details of one transaction"),
    "activity": ("[max=50]", "account activity log"),
    "orders": ("", "open orders"),
    "savings-plans": ("", "savings plans"),
    "price-alarms": ("", "price alarms"),
    "watchlist": ("", "watchlist"),
    "search": ("<text> [type=stock]", f"search instruments ({'/'.join(ASSET_TYPES)})"),
    "instrument": ("<ISIN>", "instrument details"),
    "stock-details": ("<ISIN>", "company info / fundamentals"),
    "price": ("<ISIN> [exchange=LSX]", "live quote bid/ask/last"),
    "price-history": ("<ISIN> <range> [exchange=LSX]", f"price history ({'/'.join(PRICE_RANGES)})"),
    "news": ("<ISIN>", "news about the instrument"),
}


PUBLIC_COMMANDS = {"search", "instrument", "stock-details", "price", "price-history", "news"}


def run(command: str, args: list[str]) -> object:
    if command == "login":
        login()
        return None
    if command == "logout":
        logout()
        return None
    if command not in COMMANDS:
        raise TRError(f"Unknown or not allowed command: {command}")

    # Market data is public: it works without logging in.
    client = Client(authenticated=command not in PUBLIC_COMMANDS)
    try:
        if command == "summary":
            return summary(client)
        if command == "accounts":
            return client.accounts()
        if command == "portfolio":
            return client.positions()
        if command == "cash":
            return client.get({"type": "cash"})
        if command == "payout-cash":
            return client.get({"type": "availableCashForPayout"})
        if command == "history":
            (r,) = _need(args, ["range"])[:1]
            return client.history(_range(r, HISTORY_RANGES))
        if command == "transactions":
            return client.paged("timelineTransactions", int(args[0]) if args else 50)
        if command == "transaction":
            (tid,) = _need(args, ["id"])[:1]
            return client.get({"type": "timelineDetailV2", "id": tid})
        if command == "activity":
            return client.paged("timelineActivityLog", int(args[0]) if args else 50)
        if command == "orders":
            return client.get({"type": "orders"})
        if command == "savings-plans":
            return client.get({"type": "savingsPlans"})
        if command == "price-alarms":
            return client.get({"type": "priceAlarms"})
        if command == "watchlist":
            return client.get({"type": "watchlist"})
        if command == "search":
            _need(args, ["text"])
            kind = args[1] if len(args) > 1 else "stock"
            if kind not in ASSET_TYPES:
                raise TRError(f"Invalid type: {kind}. Allowed: {', '.join(ASSET_TYPES)}")
            data = {"q": args[0], "filter": [{"key": "type", "value": kind}], "page": 1, "pageSize": 20}
            return client.get({"type": "neonSearch", "data": data})
        if command == "instrument":
            return client.get({"type": "instrument", "id": _need(args, ["ISIN"])[0]})
        if command == "stock-details":
            return client.get({"type": "stockDetails", "id": _need(args, ["ISIN"])[0]})
        if command == "price":
            isin = _need(args, ["ISIN"])[0]
            return client.get({"type": "ticker", "id": f"{isin}.{args[1] if len(args) > 1 else 'LSX'}"})
        if command == "price-history":
            isin, r = _need(args, ["ISIN", "range"])[:2]
            exchange = args[2] if len(args) > 2 else "LSX"
            return client.get({"type": "aggregateHistoryLight", "id": f"{isin}.{exchange}", "range": _range(r, PRICE_RANGES)})
        if command == "news":
            return client.get({"type": "neonNews", "isin": _need(args, ["ISIN"])[0]})
    finally:
        client.close()
    return None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2 or sys.argv[1] in ("help", "-h", "--help"):
        print("Commands (read-only):")
        print(f"  {'login':<46}interactive login (phone + PIN + confirm in the app)")
        print(f"  {'logout':<46}delete the local session")
        for name, (usage, text) in COMMANDS.items():
            print(f"  {(name + ' ' + usage).strip():<46}{text}")
        return
    try:
        result = run(sys.argv[1], sys.argv[2:])
    except TRError as e:
        sys.exit(f"Error: {e}")
    except (OSError, ValueError) as e:
        sys.exit(f"Error: {e}")
    if result is not None:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
