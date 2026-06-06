"""
포트폴리오 가격 자동 업데이트 스크립트
- yfinance로 종목별 최신 종가를 받아 portfolio-data.js의 mkt(시가, 단위 억원) 갱신
- 첫 실행 또는 prices_log.json 부재 시: portfolio-data.js의 last_updated 날짜를
  yfinance 히스토리에서 조회해 베이스라인을 자동 백필
- 한국 액티브 펀드(공모펀드) 등 Yahoo에 없는 종목은 건너뜀

사용법:
    python update_prices.py
설치:
    pip install yfinance
"""

import json
import math
import re
import sys
import io
from datetime import datetime, timedelta, date
from pathlib import Path


def _num(x):
    """float 변환 + NaN/Inf 차단 → 유효 숫자면 float, 아니면 None.
    yfinance가 NaN 종가를 반환하면 mkt가 NaN 오염되어 브라우저 JSON.parse가
    깨지는 사고(2026-06-05) 방지. NaN은 None으로 취급해 carry-forward 시킴."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import yfinance as yf
except ImportError:
    print("yfinance가 필요합니다: pip install yfinance")
    sys.exit(1)


HERE = Path(__file__).parent
DATA_JS = HERE / "portfolio-data.plain.js"
PRICES_LOG = HERE / "prices_log.json"


MKT_SUFFIX = {
    "US": "",
    "KS": ".KS",
    "KQ": ".KQ",
    "GY": ".DE",
    "IM": ".MI",
    "LN": ".L",
    "FP": ".PA",
    "SW": ".SW",
    "NA": ".AS",
    "JP": ".T",
    "HK": ".HK",
    "AU": ".AX",
}


def to_yahoo_ticker(bbg: str) -> str | None:
    if not bbg:
        return None
    parts = bbg.strip().split()
    if len(parts) < 2:
        return None
    code, mkt = parts[0], parts[1].upper()
    suffix = MKT_SUFFIX.get(mkt)
    if suffix is None:
        return None
    # 한국 펀드형 코드(예: '9BU5577', '3455228')는 Yahoo에 없음
    if mkt == "KS" and not re.fullmatch(r"\d{6}", code):
        return None
    return code + suffix


def load_data() -> tuple[str, dict]:
    text = DATA_JS.read_text(encoding="utf-8")
    m = re.search(r"window\.PORTFOLIO_DATA\s*=\s*(\{.*?\n\});", text, re.DOTALL)
    if not m:
        raise RuntimeError("portfolio-data.js에서 PORTFOLIO_DATA 블록을 찾지 못함")
    obj_str = m.group(1)
    obj_str = re.sub(r"//[^\n]*", "", obj_str)
    obj_str = re.sub(r",(\s*[}\]])", r"\1", obj_str)
    return text, json.loads(obj_str)


def save_data(text: str, data: dict) -> None:
    new_obj = json.dumps(data, ensure_ascii=False, indent=2)
    new_text = re.sub(
        r"window\.PORTFOLIO_DATA\s*=\s*\{.*?\n\};",
        f"window.PORTFOLIO_DATA = {new_obj};",
        text,
        count=1,
        flags=re.DOTALL,
    )
    DATA_JS.write_text(new_text, encoding="utf-8")


def fetch_history(ticker: str, start: date, end: date):
    """start ~ end+1 사이의 일별 종가 (DataFrame)"""
    try:
        return yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
        )
    except Exception as e:
        print(f"  [warn] {ticker} history: {e}")
        return None


def close_on_or_before(hist, target: date) -> float | None:
    if hist is None or hist.empty:
        return None
    target_ts = str(target)
    try:
        sub = hist[hist.index.strftime("%Y-%m-%d") <= target_ts]
        if sub.empty:
            return None
        return _num(sub["Close"].iloc[-1])
    except Exception:
        return None


def last_close(hist) -> float | None:
    if hist is None or hist.empty:
        return None
    return _num(hist["Close"].iloc[-1])


def last_two_closes(hist) -> tuple[float | None, float | None]:
    """가장 최근 종가, 그 전 거래일 종가 (NaN 종가는 제외하고 유효값만)"""
    if hist is None or hist.empty:
        return None, None
    closes = [v for v in (_num(c) for c in hist["Close"].tolist()) if v is not None]
    latest = closes[-1] if len(closes) >= 1 else None
    prev = closes[-2] if len(closes) >= 2 else None
    return latest, prev


def main():
    today = date.today()
    print(f"[{datetime.now().isoformat(timespec='seconds')}] 가격 업데이트 시작 (today={today})")

    text, data = load_data()
    holdings = data.get("holdings", [])
    last_updated_str = data.get("last_updated") or today.isoformat()
    try:
        last_updated = date.fromisoformat(last_updated_str)
    except Exception:
        last_updated = today

    prev_log = {}
    if PRICES_LOG.exists():
        try:
            prev_log = json.loads(PRICES_LOG.read_text(encoding="utf-8"))
        except Exception:
            prev_log = {}
    prev_prices = prev_log.get("prices", {}) if isinstance(prev_log, dict) else {}

    updated_count = 0
    new_prices: dict[str, float] = {}

    for h in holdings:
        name = h.get("name")
        bbg = h.get("ticker")
        proxy_bbg = h.get("proxy_ticker")

        # proxy가 정의되어 있으면 그것을 우선 사용 (Yahoo에 없는 펀드 대응)
        use_proxy = bool(proxy_bbg)
        candidate = proxy_bbg if use_proxy else bbg
        yt = to_yahoo_ticker(candidate) if candidate else None

        # proxy 없고 direct ticker로 시도했는데 변환 실패 시 → skip
        if not yt:
            print(f"  [skip] {name}  (ticker={bbg}, proxy={proxy_bbg})")
            continue

        # 히스토리는 last_updated부터 today까지 한 번에 (최소 7일은 받아 직전 거래일도 확보)
        start = min(last_updated, today) - timedelta(days=10)
        hist = fetch_history(yt, start, today)
        today_close, prev_trading_close = last_two_closes(hist)
        last_close_dt = None
        if hist is not None and not hist.empty:
            try:
                last_close_dt = hist.index[-1].date()
            except Exception:
                last_close_dt = None

        # direct ticker로 시도했는데 데이터 없으면 proxy로 폴백
        if today_close is None and not use_proxy and proxy_bbg:
            yt_fallback = to_yahoo_ticker(proxy_bbg)
            if yt_fallback:
                hist = fetch_history(yt_fallback, start, today)
                today_close, prev_trading_close = last_two_closes(hist)
                if today_close is not None:
                    yt = yt_fallback
                    use_proxy = True
        if today_close is None:
            print(f"  [miss] {name}  (yahoo={yt})")
            continue

        tag = "proxy" if use_proxy else "ok   "

        # 베이스라인: 직전 로그가 있으면 그 값, 없으면 last_updated 날짜의 종가
        baseline = prev_prices.get(name)
        if baseline is None:
            baseline = close_on_or_before(hist, last_updated)
            if baseline is None:
                # 못 구하면 today 가격을 baseline으로 — 변화율 0
                baseline = today_close

        cur_mkt = _num(h.get("mkt")) or 0
        baseline = _num(baseline)
        if baseline and baseline > 0 and cur_mkt > 0:
            ratio = today_close / baseline
            new_mkt = cur_mkt * ratio
            # 최종 NaN 가드: 계산 결과가 NaN/Inf면 mkt를 건드리지 않고 직전값 유지
            if _num(new_mkt) is None:
                print(f"  [nan-guard] {name}  (today={today_close}, base={baseline}) → 직전 mkt 유지")
                h["daily_chg_pct"] = 0
                h["daily_pnl"] = 0
                continue
            h["mkt"] = round(new_mkt, 2)
            chg_pct = (ratio - 1) * 100

            # 금일(직전 거래일 대비) 변동: 가장 최근 2개 거래일 종가로 계산
            if prev_trading_close and prev_trading_close > 0 and today_close != prev_trading_close:
                daily_chg = (today_close / prev_trading_close - 1) * 100
                yesterday_mkt = new_mkt * prev_trading_close / today_close
                daily_pnl = new_mkt - yesterday_mkt
                h["daily_chg_pct"] = round(daily_chg, 4)
                h["daily_pnl"] = round(daily_pnl, 4)
                daily_str = f"  Δ {daily_chg:+.2f}% ({daily_pnl:+.2f}억)"
            else:
                h["daily_chg_pct"] = 0
                h["daily_pnl"] = 0
                daily_str = "  Δ 0.00%"
            h["daily_close_date"] = last_close_dt.isoformat() if last_close_dt else None
            if last_close_dt and last_close_dt < today:
                daily_str += f"  ⚠ 최근 종가 {last_close_dt}"

            print(
                f"  [{tag}] {name:42s}  {yt:14s}  base {baseline:>10,.2f} → {today_close:>10,.2f}  "
                f"mkt {cur_mkt:>7,.2f} → {h['mkt']:>7,.2f} ({chg_pct:+5.2f}%){daily_str}"
            )
            updated_count += 1
        else:
            print(f"  [zero] {name}  (mkt={cur_mkt}, base={baseline})")
            h["daily_chg_pct"] = 0
            h["daily_pnl"] = 0

        new_prices[name] = round(today_close, 6)

    # 비중 재계산
    total_mkt = sum((h.get("mkt") or 0) for h in holdings)
    if total_mkt > 0:
        for h in holdings:
            h["w"] = round((h.get("mkt") or 0) / total_mkt, 4)

    data["last_updated"] = today.isoformat()

    save_data(text, data)
    PRICES_LOG.write_text(
        json.dumps({"as_of_date": today.isoformat(), "prices": new_prices},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n갱신 종목: {updated_count} / 전체 {len(holdings)}")
    print(f"총 평가금액: {total_mkt:,.2f} 억원")
    print(f"저장: {DATA_JS.name}, {PRICES_LOG.name}")


if __name__ == "__main__":
    main()
