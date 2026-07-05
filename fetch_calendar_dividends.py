"""
fetch_calendar_dividends.py — 보유 ETF/펀드 분배금 캘린더 생성 (yfinance)

캘린더 탭(calendar.html)의 '🔒 보유 분배금' 레이어 데이터를 만든다.
실보유 리스트는 public repo에 노출하지 않기 위해 결과를 암호화한다:

    python fetch_calendar_dividends.py       # → calendar-holdings.plain.js (gitignored)
    python encrypt_calendar.py encrypt       # → calendar-holdings.js (암호화, commit)

동작
  1) portfolio-data.plain.js(평문, gitignored)에서 보유 종목/티커를 읽는다.
  2) 야후 심볼로 매핑해 yfinance 분배금 이력을 가져온다.
  3) 최근 실지급(actual) + 주기 추정으로 향후 예상 ex-date(estimate)를 투영한다.
  4) [today-60d, today+150d] 창의 이벤트만 emit.

주의: 이 PC에서 yfinance(야후)는 정상. FRED만 IP throttle. GitHub Actions에서도 동일.
"""
import datetime as dt
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance 필요: pip install yfinance")

HERE = Path(__file__).parent
PLAIN_HOLDINGS = HERE / "portfolio-data.plain.js"
OUT = HERE / "calendar-holdings.plain.js"

TODAY = dt.date.today()
WIN_BACK = 60
WIN_FWD = 150

# 거래소 접미사 → 야후 심볼 접미사. LX(룩셈부르크 뮤추얼펀드)·KS 사모펀드코드는 야후 미수록 → 스킵.
SUFFIX = {"US": "", "KS": ".KS", "GY": ".DE", "IM": ".MI"}
SKIP_SUFFIX = {"LX"}  # 룩셈부르크 펀드(FIEDIAE, THEAAIE 등) — 야후 없음


def to_yahoo(ticker: str):
    """'069500 KS' → '069500.KS', 'XLK US' → 'XLK'. 매핑 불가 시 None."""
    ticker = ticker.strip()
    m = re.match(r"^(\S+)\s+([A-Z]{2})$", ticker)
    if not m:
        return None
    code, suf = m.group(1), m.group(2)
    if suf in SKIP_SUFFIX:
        return None
    # 순수 숫자 사모펀드 코드(예: 9BU5577, 3455228)는 ETF가 아니라 스킵
    if suf == "KS" and not re.fullmatch(r"\d{6}", code):
        return None
    if suf not in SUFFIX:
        return None
    return code + SUFFIX[suf]


def load_holdings():
    if not PLAIN_HOLDINGS.exists():
        sys.exit(f"평문 보유파일 없음: {PLAIN_HOLDINGS.name} (encrypt_data.py decrypt 먼저)")
    text = PLAIN_HOLDINGS.read_text(encoding="utf-8")
    m = re.search(r"window\.PORTFOLIO_DATA\s*=\s*(\{.*?\n\});", text, re.DOTALL)
    if not m:
        sys.exit("PORTFOLIO_DATA 블록 못 찾음")
    return json.loads(m.group(1))["holdings"]


def infer_freq(dates):
    """지급일 간격(중앙값)으로 주기 라벨·투영 간격(월) 추정."""
    if len(dates) < 2:
        return "분기", 3
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    gaps.sort()
    med = gaps[len(gaps) // 2]
    if med <= 45:
        return "월", 1
    if med <= 100:
        return "분기", 3
    if med <= 200:
        return "반기", 6
    return "연", 12


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return dt.date(y, m, day)


def main():
    holdings = load_holdings()
    lo, hi = TODAY - dt.timedelta(days=WIN_BACK), TODAY + dt.timedelta(days=WIN_FWD)
    events, skipped = [], []

    for h in holdings:
        name, tkr = h.get("name", ""), h.get("ticker", "")
        ysym = to_yahoo(tkr)
        if not ysym:
            skipped.append(f"{name} ({tkr})")
            continue
        try:
            s = yf.Ticker(ysym).dividends
        except Exception as e:
            skipped.append(f"{name} ({ysym}) ERR {str(e)[:40]}")
            continue
        if s is None or len(s) == 0:
            skipped.append(f"{name} ({ysym}) 무분배(accumulating 가능)")
            continue

        pays = [(i.date(), float(v)) for i, v in s.items()]
        pays.sort()
        dates = [d for d, _ in pays]
        freq_lbl, step = infer_freq(dates[-6:] if len(dates) >= 6 else dates)
        last_date, last_amt = pays[-1]
        ccy = "₩" if ysym.endswith(".KS") else ("€" if (ysym.endswith(".DE") or ysym.endswith(".MI")) else "$")

        # 실지급(actual): 창 안의 과거 지급
        for d, amt in pays:
            if lo <= d <= hi:
                events.append(_ev(name, ysym, d, amt, ccy, freq_lbl, actual=True))

        # 예상(estimate): 마지막 지급 이후 주기로 투영, 창 안까지
        proj, guard = last_date, 0
        while guard < 12:
            proj = add_months(proj, step)
            guard += 1
            if proj > hi:
                break
            if proj <= TODAY:
                continue
            events.append(_ev(name, ysym, proj, last_amt, ccy, freq_lbl, actual=False))

    events.sort(key=lambda e: e["date"])
    payload = {
        "as_of": TODAY.isoformat(),
        "note": "보유 ETF/펀드 분배금(yfinance). 과거=실지급, 미래=주기추정(estimate). ex-date 기준. 룩셈부르크 뮤추얼펀드·사모펀드는 야후 미수록으로 제외.",
        "skipped": skipped,
        "events": events,
    }
    out = (
        "// 보유 분배금 평문 (gitignored) — encrypt_calendar.py encrypt 로 calendar-holdings.js 갱신\n"
        "// fetch_calendar_dividends.py 자동생성\n"
        f"window.CALENDAR_HOLDINGS = {json.dumps(payload, ensure_ascii=False, indent=2)};\n"
    )
    OUT.write_text(out, encoding="utf-8")
    print(f"생성: {OUT.name} · 이벤트 {len(events)}건 · 스킵 {len(skipped)}건")
    for s in skipped:
        print("  skip:", s)


def _ev(name, ysym, d, amt, ccy, freq, actual):
    return {
        "date": d.isoformat(),
        "type": "dividend",
        "region": "KR" if ysym.endswith(".KS") else ("EU" if (ysym.endswith(".DE") or ysym.endswith(".MI")) else "US"),
        "ticker": ysym,
        "name": name,
        "kind": "ex",
        "amount": f"{ccy}{amt:,.4f}".rstrip("0").rstrip(".") if ccy != "₩" else f"₩{amt:,.0f}",
        "freq": freq,
        "held": True,
        "released": actual,
        "verified": actual,
        "note": ("실지급(ex-date)" if actual else "예상 지급일(직전 분배금·주기 추정)") + f" · {ysym}",
    }


if __name__ == "__main__":
    main()
