"""Fetch market + fund data and build the dashboard into site/index.html.

Env vars:
  DASHBOARD_PASSWORD  encrypt the page data with this password (recommended when published)
  PORTFOLIO_JSON      portfolio as a JSON string (used on GitHub Actions instead of portfolio.json)
"""
import base64
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130 Safari/537.36"}
BKK = dt.timezone(dt.timedelta(hours=7))
SPARK_DAYS = 92
session = requests.Session()
session.headers.update(UA)


def get_json(url, tries=4):
    last = None
    for i in range(tries):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:120]!r}"
            if r.status_code == 404:
                break
        except (requests.RequestException, ValueError) as e:
            last = repr(e)[:200]
        time.sleep(2 * (i + 1))
    print(f"  ! request failed {url[:90]} -> {last}", file=sys.stderr)
    return None


# ---------- series helpers ----------

def value_on_or_before(series, day):
    """series: list of (date, value) ascending."""
    best = None
    for d, v in series:
        if d <= day:
            best = v
        else:
            break
    return best


def pct(a, b):
    if a is None or b in (None, 0):
        return None
    return (a / b - 1) * 100


def metrics(series):
    """Return change metrics for a list of (date, value) ascending."""
    if not series:
        return None
    last_d, last = series[-1]
    prev = series[-2][1] if len(series) > 1 else None
    year_start = value_on_or_before(series, dt.date(last_d.year - 1, 12, 31))
    return {
        "last": last,
        "date": last_d.isoformat(),
        "d1": pct(last, prev),
        "m1": pct(last, value_on_or_before(series, last_d - dt.timedelta(days=30))),
        "ytd": pct(last, year_start),
        "y1": pct(last, value_on_or_before(series, last_d - dt.timedelta(days=365))),
    }


def spark(series, days=SPARK_DAYS):
    if not series:
        return []
    cutoff = series[-1][0] - dt.timedelta(days=days)
    return [[d.isoformat(), round(v, 6)] for d, v in series if d >= cutoff]


# ---------- Yahoo Finance ----------

def yahoo_series(symbol):
    for host in ("query1", "query2"):
        url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol)}?range=2y&interval=1d"
        data = get_json(url)
        try:
            res = data["chart"]["result"][0]
        except (TypeError, KeyError, IndexError):
            continue
        tz = dt.timezone(dt.timedelta(seconds=res["meta"].get("gmtoffset", 0)))
        closes = res["indicators"]["quote"][0]["close"]
        out = {}
        for ts, c in zip(res.get("timestamp", []), closes):
            if c is not None:
                out[dt.datetime.fromtimestamp(ts, tz).date()] = c
        series = sorted(out.items())
        # Make the latest point the live market price when Yahoo has a newer one
        meta = res["meta"]
        price, mtime = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
        if price and mtime:
            mday = dt.datetime.fromtimestamp(mtime, tz).date()
            if not series or mday >= series[-1][0]:
                series = [p for p in series if p[0] < mday] + [(mday, price)]
        # Some indices (e.g. SET, CSI 300) come back without history: keep the reported
        # previous close so at least the 1-day change works.
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        if len(series) == 1 and prev:
            series = [(series[0][0] - dt.timedelta(days=1), prev)] + series
        return series
    return []


# ---------- snapshot history for symbols Yahoo has no history for ----------

SNAP_FILE = ROOT / "data" / "snapshots.json"


def load_snapshots():
    try:
        return json.loads(SNAP_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def merge_snapshots(symbol, series, snaps):
    """Record today's close and fill in history from earlier runs when Yahoo's is thin."""
    if not series:
        return series
    rec = snaps.setdefault(symbol, {})
    d, v = series[-1]
    rec[d.isoformat()] = v
    if len(series) >= 30:
        return series
    merged = {dt.date.fromisoformat(k): val for k, val in rec.items()}
    merged.update(dict(series))
    return sorted(merged.items())


# ---------- Thai data: fund NAVs (Finnomena) + gold (Gold Traders Association) ----------
# Both sites block GitHub's servers, so a scheduled task on a home PC fetches them
# (fetch_thai.py) and pushes an encrypted copy to data/thai.enc.json for Actions to use.

FN = "https://www.finnomena.com/fn3/api/fund"
GTA = "https://www.goldtraders.or.th/api/GoldPrices"
THAI_FILE = ROOT / "data" / "thai.enc.json"
KEY_FILE = ROOT / ".thai_key"


def fund_series(fund_id):
    data = get_json(f"{FN}/v2/public/funds/{fund_id}/nav/q?range=1Y")
    try:
        navs = data["data"]["navs"]
    except (TypeError, KeyError):
        return []
    out = {}
    for n in navs:
        if n.get("value"):
            out[n["date"][:10]] = n["value"]
    return sorted(out.items())


def gold_series_live():
    """Returns (latest, daily) for the Thai 96.5% gold bar price in THB per baht-weight."""
    latest = get_json(f"{GTA}/Latest?readjson=false")
    ohlc = get_json(f"{GTA}/ohlc?readjson=true") or []
    cutoff = (dt.date.today() - dt.timedelta(days=800)).isoformat()
    daily = {}
    for row in ohlc:  # hourly rows, ascending: the last one of each day is its close
        d = row["hour"][:10]
        if d >= cutoff:
            daily[d] = row["close"]
    if latest:
        daily[latest["asTime"][:10]] = latest["bL_SellPrice"]
    return latest, sorted(daily.items())


def fetch_thai_live(portfolio):
    idx = {f["short_code"].upper(): f for f in (get_json(f"{FN}/public/list") or [])}
    funds = {}
    for f in portfolio.get("funds", []):
        info = idx.get(f["code"].upper())
        if info:
            funds[f["code"]] = {"name": info["name_th"], "navs": fund_series(info["id"])}
            time.sleep(0.3)
    latest, gold = gold_series_live()
    return {"fetched": dt.datetime.now(BKK).isoformat(timespec="minutes"),
            "funds": funds, "gold_latest": latest, "gold": gold}


def _key():
    k = os.environ.get("THAI_DATA_KEY") or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else None)
    return base64.b64decode(k) if k else None


def save_thai_cache(thai):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = os.urandom(12)
    ct = AESGCM(_key()).encrypt(iv, json.dumps(thai, ensure_ascii=False).encode(), None)
    THAI_FILE.parent.mkdir(exist_ok=True)
    THAI_FILE.write_text(json.dumps({"iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(ct).decode()}))


def load_thai_cache():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    blob = json.loads(THAI_FILE.read_text())
    pt = AESGCM(_key()).decrypt(base64.b64decode(blob["iv"]), base64.b64decode(blob["ct"]), None)
    return json.loads(pt)


def thai_data(portfolio):
    """Live on a home PC; the encrypted cache on GitHub Actions (THAI_DATA_KEY is set there)."""
    if os.environ.get("THAI_DATA_KEY"):
        try:
            thai = load_thai_cache()
            print(f"  using cached Thai data from {thai['fetched']}")
            return thai
        except (OSError, ValueError, KeyError) as e:
            print(f"  ! cannot read {THAI_FILE.name}: {e!r}", file=sys.stderr)
            return {"funds": {}, "gold_latest": None, "gold": []}
    return fetch_thai_live(portfolio)


def to_series(pairs):
    return [(dt.date.fromisoformat(d), v) for d, v in pairs]


# ---------- build ----------

def build_watchlists(config):
    sections, snaps = [], load_snapshots()
    for sec in config["sections"]:
        rows = []
        for symbol, name, sub in sec["items"]:
            s = yahoo_series(symbol)
            if len(s) < 30:
                s = merge_snapshots(symbol, s, snaps)
            if not s:
                print(f"  ! no data for {symbol}", file=sys.stderr)
            rows.append({"symbol": symbol, "name": name, "sub": sub, "m": metrics(s), "spark": spark(s)})
            time.sleep(0.3)
        sections.append({"id": sec["id"], "title": sec["title"], "rows": rows})
        print(f"  {sec['id']}: {sum(1 for r in rows if r['m'])}/{len(rows)}")
    if snaps:
        SNAP_FILE.parent.mkdir(exist_ok=True)
        SNAP_FILE.write_text(json.dumps(snaps, indent=1, sort_keys=True), encoding="utf-8")
    return sections


def add_thai_gold_row(sections, latest, series):
    if not series:
        return
    sub = f"สมาคมค้าทองคำ · รับซื้อ {latest['bL_BuyPrice']:,.0f}" if latest else "สมาคมค้าทองคำ"
    for s in sections:
        if s["id"] == "macro":
            s["rows"].insert(1, {"symbol": "GTA", "name": "ทองคำแท่ง 96.5% ขายออก (บาท/บาททองคำ)",
                                 "sub": sub, "m": metrics(series), "spark": spark(series)})


def build_portfolio(portfolio, thai):
    gold_latest, gold_series = thai["gold_latest"], to_series(thai["gold"])
    holdings, history = [], {}
    for g in portfolio.get("gold", []):
        # Value at the association's bar buy-back price, i.e. what it would sell for today
        nav = gold_latest["bL_BuyPrice"] if gold_latest else (gold_series[-1][1] if gold_series else None)
        m = metrics(gold_series)
        holdings.append({
            "code": g.get("code", "ทองคำแท่ง"), "name": g.get("name", "ทองคำแท่ง 96.5% (ราคารับซื้อ สมาคมค้าทองคำ)"),
            "units": g["baht_weight"], "cost": g["cost"], "nav": nav,
            "nav_date": gold_latest["asTime"][:10] if gold_latest else (m["date"] if m else None),
            "m": m, "spark": spark(gold_series), "found": nav is not None,
        })
        for d, v in gold_series:
            history.setdefault(d, {})[holdings[-1]["code"]] = v * g["baht_weight"]
    for f in portfolio.get("funds", []):
        info = thai["funds"].get(f["code"])
        s = to_series(info["navs"]) if info else []
        if not s:
            print(f"  ! fund not found / no NAV: {f['code']}", file=sys.stderr)
        m = metrics(s)
        nav = m["last"] if m else None
        h = {
            "code": f["code"],
            "name": info["name"] if info else "ไม่พบกองทุนนี้ – ตรวจสอบรหัส",
            "units": f["units"], "cost": f["cost"], "nav": nav,
            "nav_date": m["date"] if m else None, "m": m, "spark": spark(s),
            "found": bool(s),
        }
        holdings.append(h)
        for d, v in s:
            history.setdefault(d, {})[f["code"]] = v * f["units"]
    for f in portfolio.get("manual", []):
        holdings.append({
            "code": f["code"], "name": f.get("name", f["code"]), "units": f["units"],
            "cost": f.get("cost"), "cost_total": f.get("cost_total"), "nav": f["nav"], "nav_date": f.get("nav_date"),
            "m": None, "spark": [], "found": True, "manual": True,
        })

    # Value history of market-priced funds at today's units (forward-filled NAVs)
    codes = [h["code"] for h in holdings if not h.get("manual") and h["found"]]
    last, hist = {}, []
    for d in sorted(history):
        last.update(history[d])
        if all(c in last for c in codes):
            hist.append([d.isoformat(), round(sum(last[c] for c in codes), 2)])
    return {"holdings": holdings, "history": hist}


def encrypt(payload: bytes, password: str) -> dict:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt, iv, iters = os.urandom(16), os.urandom(12), 250_000
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iters).derive(password.encode())
    ct = AESGCM(key).encrypt(iv, payload, None)
    b64 = lambda b: base64.b64encode(b).decode()
    return {"salt": b64(salt), "iv": b64(iv), "iter": iters, "ct": b64(ct)}


def main():
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if os.environ.get("PORTFOLIO_JSON"):
        portfolio = json.loads(os.environ["PORTFOLIO_JSON"])
    elif (ROOT / "portfolio.json").exists():
        portfolio = json.loads((ROOT / "portfolio.json").read_text(encoding="utf-8"))
    else:
        portfolio = {}

    print("Fetching watchlists…")
    sections = build_watchlists(config)
    print("Fetching Thai funds and gold…")
    thai = thai_data(portfolio)
    if not thai["gold"]:
        print("  ! no Thai gold price", file=sys.stderr)
    add_thai_gold_row(sections, thai["gold_latest"], to_series(thai["gold"]))
    port = build_portfolio(portfolio, thai)

    data = {
        "generated": dt.datetime.now(BKK).strftime("%Y-%m-%d %H:%M"),
        "portfolio": port,
        "sections": sections,
    }
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    password = os.environ.get("DASHBOARD_PASSWORD")
    blob = {"enc": encrypt(payload, password)} if password else {"plain": data}

    html = (ROOT / "template.html").read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/null", json.dumps(blob, ensure_ascii=False))
    out = ROOT / "site"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"Wrote {out / 'index.html'} ({'encrypted' if password else 'NOT encrypted'})")


if __name__ == "__main__":
    main()
