"""보유 해외 ETF 분배금 감지 (yfinance) + 지급일 정보(Nasdaq/추정).

배당락(ex-date)이 확정되는 즉시 이메일. 지급일은 Nasdaq 정확값이 있으면 사용,
없으면 ex + 추정 offset(대부분 미제공이라 추정 표기).
해외 = 포트폴리오 보유 중 US/DE(GY)/MI(IM) 상장. LX(룩셈부르크 뮤추얼펀드)는 야후 미수록 → 제외.
"""

import datetime as dt
import re

import requests

from sync_watchlist import _decrypt_holdings

_SUFFIX = {"US": "", "GY": ".DE", "IM": ".MI"}
_PAY_ESTIMATE_DAYS = 5           # 지급일 미제공 시 ex + N일(추정)
_NASDAQ_H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


def held_overseas() -> list[tuple[str, str, str]]:
    """(야후심볼, 종목명, 통화기호) 리스트. 실패 시 []."""
    try:
        data = _decrypt_holdings()
    except Exception as e:
        print(f"⚠️ 해외ETF: 보유 복호화 실패: {e}")
        return []
    out = []
    for h in data.get("holdings", []):
        m = re.match(r"^(\S+)\s+(US|GY|IM)$", h.get("ticker", ""))
        if not m:
            continue
        sym = m.group(1) + _SUFFIX[m.group(2)]
        ccy = "$" if m.group(2) == "US" else "€"
        out.append((sym, h.get("name", "").strip(), ccy))
    return out


def _nasdaq_paydate(sym: str, ex_iso: str) -> str | None:
    """Nasdaq에서 해당 ex-date의 지급일(ISO). 없으면 None."""
    t = sym.split(".")[0]
    try:
        r = requests.get(f"https://api.nasdaq.com/api/quote/{t}/dividends",
                         params={"assetclass": "etf"}, headers=_NASDAQ_H, timeout=12)
        rows = ((r.json().get("data") or {}).get("dividends", {}) or {}).get("rows") or []
    except Exception:
        return None
    for row in rows:
        ex = _us_date(row.get("exOrEffDate"))
        if ex == ex_iso and row.get("paymentDate") and row["paymentDate"] != "N/A":
            return _us_date(row["paymentDate"])
    return None


def _us_date(s: str | None) -> str | None:
    """'06/26/2026' → '2026-06-26'."""
    if not s:
        return None
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None


def recent_distributions(days_back: int = 7) -> list[dict]:
    """최근 `days_back`일 내 배당락된 보유 해외 ETF 분배 이벤트."""
    import yfinance as yf
    today = dt.date.today()
    lo = today - dt.timedelta(days=days_back)
    events = []
    for sym, name, ccy in held_overseas():
        try:
            s = yf.Ticker(sym).dividends
        except Exception:
            continue
        if s is None or len(s) == 0:
            continue
        for idx, val in s.items():
            ex = idx.date()
            if lo <= ex <= today:
                ex_iso = ex.isoformat()
                pay = _nasdaq_paydate(sym, ex_iso)
                estimated = pay is None
                if estimated:
                    pay = (ex + dt.timedelta(days=_PAY_ESTIMATE_DAYS)).isoformat()
                events.append({
                    "id": f"ov:{sym}:{ex_iso}",
                    "sym": sym, "name": name, "ccy": ccy,
                    "ex_date": ex_iso, "amount": f"{ccy}{float(val):,.4f}".rstrip("0").rstrip("."),
                    "pay_date": pay, "pay_estimated": estimated,
                })
    return events
