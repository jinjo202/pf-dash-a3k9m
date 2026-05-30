"""
시장 지수 YTD + 일일 수익률 수집 (KOSPI/KOSDAQ/S&P/NASDAQ/SOX/USDKRW)
- yfinance에서 작년 12월부터 오늘까지 종가 받아 YTD 계산
- 결과를 benchmarks.js로 저장 (평문 — 공개 시장 데이터)
"""
import json
import sys
import io
from datetime import date, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    sys.exit("필요: pip install yfinance pandas")

HERE = Path(__file__).parent
OUT = HERE / "benchmarks.js"

# 수동 입력 데이터 (Yahoo에 안정 티커가 없는 항목)
# 변경 시: 이 dict를 수정 → fetch_benchmarks.py 실행 → push.
# KR 10년 국고채 yield는 한국은행 ECOS API 키 받기 전엔 수동 갱신.
MANUAL_OVERRIDES = {
    "KR 10Y": {
        "category": "금리",
        "current": 3.30,         # 현재 yield (%) — 한국은행/금융투자협회 채권시세에서 확인 후 업데이트
        "baseline": 2.95,        # 연초(1/2) yield (%)
        "mtd_baseline": 3.18,    # 5/1 직전 거래일 yield (%) — MTD 계산용
        "prev_close": 3.27,      # 직전 거래일 yield (%) — 일일 변동 계산용
        "as_of": "2026-05-19",   # 마지막 수동 업데이트 날짜
        "decimals": 2,
        "ticker": "MANUAL",
        "manual": True,
    },
}


# 지수 → 대표 ETF (PER/PBR/ROE 가져올 때 사용). None = 해당 없음.
VAL_PROXY = {
    "ACWI":      "ACWI",
    "EEM":       "EEM",
    "^KS11":     "EWY",      # iShares MSCI Korea (US)
    "^KQ11":     None,        # KOSDAQ 직접 ETF 없음
    "^GSPC":     "SPY",       # SPDR S&P 500
    "^IXIC":     "QQQ",       # Invesco QQQ
    "^SOX":      "SOXX",      # iShares Semiconductor
    "^STOXX":    "IEUR",      # iShares Core MSCI Europe
    "^N225":     "EWJ",       # iShares MSCI Japan
    "000001.SS": "MCHI",      # iShares MSCI China
    "KRW=X":     None,
    "^VIX":      None,
    "^TNX":      None,        # US 10Y Treasury Yield (직접)
    "CL=F":      None,        # WTI Crude Oil
}


BENCHMARKS = [
    # (이름, yahoo 티커, 소수자리, 카테고리)
    # MSCI 글로벌 (최상단 우선)
    ("MSCI ACWI",        "ACWI",      2, "MSCI"),
    ("MSCI EM",          "EEM",       2, "MSCI"),
    # 한국
    ("KOSPI",            "^KS11",     0, "한국"),
    ("KOSDAQ",           "^KQ11",     2, "한국"),
    # 미국
    ("S&P 500",          "^GSPC",     2, "미국"),
    ("NASDAQ",           "^IXIC",     2, "미국"),
    ("필라델피아 반도체",  "^SOX",      2, "미국"),
    # 유럽
    ("STOXX 600",        "^STOXX",    2, "유럽"),
    # 아시아
    ("니케이 225",        "^N225",     0, "아시아"),
    ("상해종합",          "000001.SS", 2, "아시아"),
    # 환율
    ("USD/KRW",          "KRW=X",     2, "환율"),
    # 금리
    ("US 10Y",           "^TNX",      2, "금리"),
    # KR 10Y는 Yahoo에 없음 — 한국은행 OpenAPI 또는 KRX 데이터 필요 (별도)
    # 원자재
    ("WTI 유가",          "CL=F",      2, "원자재"),
    # 변동성·기타
    ("VIX",              "^VIX",      2, "변동성"),
    # VKOSPI는 Yahoo 안정 티커 없음 — Investing.com 스크래핑이나 KRX OpenAPI 필요 (별도)
]


def derive_forward_pe_from_etf(etf_ticker, max_holdings=15):
    """ETF top holdings의 individual forwardPE → 가중 earnings yield 방식으로 ETF의 forward PE 도출.
    개별 종목은 yfinance forwardPE를 잘 주므로, ETF의 forward PE도 충분히 정확하게 도출 가능.
    """
    try:
        fd = yf.Ticker(etf_ticker).funds_data
        if not fd:
            return None
        tops = fd.top_holdings
        if tops is None or tops.empty:
            return None
        ys, ws = [], []  # earnings yield (1/PE) + weight
        for sym in list(tops.index)[:max_holdings]:
            row = tops.loc[sym]
            w = row.get("Holding Percent")
            if w is None or w <= 0:
                continue
            try:
                info = yf.Ticker(sym).info or {}
            except Exception:
                continue
            fwd = info.get("forwardPE")
            if fwd is None or fwd <= 0 or fwd > 200:
                continue
            ys.append(1.0 / fwd)
            ws.append(float(w))
        if not ys:
            return None
        # 가중 earnings yield → invert → forward PE
        # (sum 정규화: top N만으로도 비례 보존)
        avg_y = sum(y * w for y, w in zip(ys, ws)) / sum(ws)
        if avg_y <= 0:
            return None
        derived = 1.0 / avg_y
        # sanity
        if derived <= 0 or derived > 300:
            return None
        return derived
    except Exception:
        return None


def main():
    today = date.today()
    start = today - timedelta(days=400)  # 1년치 차트 + YTD baseline 확보
    end = today + timedelta(days=1)

    out = {"as_of": today.isoformat(), "indices": []}
    print(f"=== 시장 지수 ({today}) ===")
    for name, ticker, decimals, category in BENCHMARKS:
        try:
            hist = yf.Ticker(ticker).history(
                start=start.isoformat(), end=end.isoformat(), auto_adjust=False
            )
            if hist.empty:
                print(f"  [miss] {name} ({ticker})")
                continue

            # YTD 기준: 올해 1월 1일 직전 마지막 거래일 종가
            this_year_start = None
            for i, ts in enumerate(hist.index):
                if ts.year >= today.year:
                    this_year_start = i
                    break
            # NaN-safe: 베이스라인 + 현재가 + 이전가를 NaN 건너뛰며 찾기
            closes = hist["Close"]
            # baseline: 올해 시작 직전 마지막 거래일 (NaN 아닌 첫 값 찾기 - 뒤에서 앞으로)
            baseline = None
            for j in range(max(0, (this_year_start or len(hist)) - 1), -1, -1):
                v = closes.iloc[j]
                if not pd.isna(v):
                    baseline = float(v)
                    break
            # MTD baseline: 이번 달 1일 직전 마지막 거래일
            this_month_start_idx = None
            for i, ts in enumerate(hist.index):
                if ts.year == today.year and ts.month == today.month:
                    this_month_start_idx = i
                    break
            mtd_baseline = None
            if this_month_start_idx is not None:
                for j in range(max(0, this_month_start_idx - 1), -1, -1):
                    v = closes.iloc[j]
                    if not pd.isna(v):
                        mtd_baseline = float(v)
                        break
            # current: 마지막 NaN 아닌 값
            current = None
            current_idx = None
            for j in range(len(closes) - 1, -1, -1):
                v = closes.iloc[j]
                if not pd.isna(v):
                    current = float(v)
                    current_idx = j
                    break
            if baseline is None or current is None:
                print(f"  [miss] {name} ({ticker}) — 유효 가격 없음")
                continue
            ytd_pct = (current / baseline - 1) * 100 if baseline > 0 else None
            mtd_pct = (current / mtd_baseline - 1) * 100 if (mtd_baseline and mtd_baseline > 0) else None

            # 직전 거래일 대비 (current 바로 앞 NaN 아닌 값)
            daily_pct = None
            if current_idx is not None and current_idx > 0:
                for j in range(current_idx - 1, -1, -1):
                    v = closes.iloc[j]
                    if not pd.isna(v):
                        prev = float(v)
                        if prev > 0:
                            daily_pct = (current / prev - 1) * 100
                        break

            asof = str(hist.index[current_idx].date()) if current_idx is not None else str(hist.index[-1].date())
            # 1년 히스토리 (차트용) — 일별 종가
            history = None
            try:
                closes_arr = hist["Close"]
                hist_dates, hist_values = [], []
                for ts in hist.index:
                    v = closes_arr.loc[ts] if ts in closes_arr.index else None
                    if v is not None and not pd.isna(v):
                        hist_dates.append(ts.strftime("%Y-%m-%d"))
                        hist_values.append(round(float(v), 4))
                if len(hist_dates) > 260:
                    hist_dates = hist_dates[-260:]
                    hist_values = hist_values[-260:]
                if hist_dates:
                    history = {"dates": hist_dates, "values": hist_values}
            except Exception:
                pass

            # 밸류에이션 (대응 ETF에서 수집, 가능한 것만)
            # 12M Forward PER 우선:
            #   1) yfinance.info.forwardPE 직접 시도 (개별 종목은 잘 옴, ETF는 보통 None)
            #   2) None이면 top holdings의 forwardPE 가중 earnings yield → 도출
            # PBR은 yfinance priceToBook 정의상 항상 trailing
            val = {"pe": None, "pb": None, "roe": None, "src": None,
                   "pe_kind": None, "pb_kind": None}
            proxy = VAL_PROXY.get(ticker)
            if proxy:
                try:
                    pinfo = yf.Ticker(proxy).info or {}
                    fwd_pe = pinfo.get("forwardPE")
                    ttm_pe = pinfo.get("trailingPE")
                    pe = fwd_pe if fwd_pe is not None else ttm_pe
                    pe_kind = "fwd" if fwd_pe is not None else ("ttm" if ttm_pe is not None else None)
                    pb = pinfo.get("priceToBook")
                    roe = pinfo.get("returnOnEquity")
                    if pe is not None and (pe <= 0 or pe > 300):
                        pe = None
                        pe_kind = None
                    if pb is not None and (pb <= 0 or pb > 100): pb = None
                    if roe is not None and (roe > 3 or roe < -3): roe = None
                    val["pe"]  = round(float(pe), 2) if pe else None
                    val["pb"]  = round(float(pb), 2) if pb else None
                    val["roe"] = round(float(roe) * 100, 2) if roe is not None else None
                    val["pe_kind"] = pe_kind
                    val["pb_kind"] = "ttm" if val["pb"] else None
                    val["src"] = proxy if any([val["pe"], val["pb"], val["roe"]]) else None

                    # forwardPE 직접 못 받았으면 ETF top holdings → derive
                    if val["pe_kind"] != "fwd":
                        derived = derive_forward_pe_from_etf(proxy)
                        if derived is not None:
                            val["pe"] = round(derived, 2)
                            val["pe_kind"] = "fwd"
                            val["src"] = f"{proxy} (top derived)"
                            print(f"    └ {name}: fwd derived from {proxy} top holdings = {derived:.2f}")
                except Exception:
                    pass

            out["indices"].append({
                "name": name,
                "ticker": ticker,
                "category": category,
                "current": round(current, 4),
                "baseline": round(baseline, 4),
                "mtd_baseline": round(mtd_baseline, 4) if mtd_baseline else None,
                "ytd_pct": round(ytd_pct, 4) if ytd_pct is not None else None,
                "mtd_pct": round(mtd_pct, 4) if mtd_pct is not None else None,
                "daily_pct": round(daily_pct, 4) if daily_pct is not None else None,
                "as_of": asof,
                "decimals": decimals,
                "valuation": val,
                "history": history,
            })
            print(f"  [ok]  {name:18s} {ticker:10s} {current:>10.2f}  "
                  f"YTD {ytd_pct:+6.2f}%  Δ {daily_pct:+5.2f}% ({asof})")
        except Exception as e:
            print(f"  [err] {name} ({ticker}): {e}")

    # 수동 override 적용 (Yahoo에 없는 KR 10Y 등)
    for name, m in MANUAL_OVERRIDES.items():
        ytd_pct = (m["current"] / m["baseline"] - 1) * 100 if m["baseline"] else None
        mtd_pct = (m["current"] / m["mtd_baseline"] - 1) * 100 if m.get("mtd_baseline") else None
        daily_pct = (m["current"] / m["prev_close"] - 1) * 100 if m.get("prev_close") else None
        out["indices"].append({
            "name": name,
            "ticker": m["ticker"],
            "category": m["category"],
            "current": m["current"],
            "baseline": m["baseline"],
            "mtd_baseline": m.get("mtd_baseline"),
            "ytd_pct": round(ytd_pct, 4) if ytd_pct is not None else None,
            "mtd_pct": round(mtd_pct, 4) if mtd_pct is not None else None,
            "daily_pct": round(daily_pct, 4) if daily_pct is not None else None,
            "as_of": m["as_of"],
            "decimals": m.get("decimals", 2),
            "valuation": {"pe": None, "pb": None, "roe": None, "src": None},
            "manual": True,
        })
        print(f"  [수동] {name:18s} {m['ticker']:10s} {m['current']:>8.2f}  "
              f"YTD {ytd_pct:+5.2f}%  MTD {mtd_pct:+5.2f}%  Δ {daily_pct:+5.2f}% (as of {m['as_of']})")

    OUT.write_text(
        "// 시장 지수 YTD/일일 수익률 (공개 데이터, 평문). fetch_benchmarks.py로 갱신.\n"
        "// KR 10Y는 수동 입력 (MANUAL_OVERRIDES) — 한국은행/금융투자협회에서 확인 후 갱신 필요.\n"
        f"window.BENCHMARKS = {json.dumps(out, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    print(f"\n저장: {OUT.name}  ({len(out['indices'])}개 지수)")


if __name__ == "__main__":
    main()
