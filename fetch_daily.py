"""
일간 시장 동향 데이터 파이프라인.

미국/유럽/중국/일본/한국 지역별 지수, GICS 섹터 움직임,
시총 상위 종목 일간 등락, 특징주 + 관련 뉴스를 수집해
daily-data.js (window.DAILY = {...}) 로 저장한다.

데이터 소스: yfinance (API 키 불필요)
"""
import json
import sys
import io
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import yfinance as yf
    import pandas as pd
except ImportError:
    sys.exit("필요: pip install yfinance pandas")

HERE = Path(__file__).parent
OUT = HERE / "daily-data.js"

# ─────────────────────────────────────────────────────────────────────────────
# 지역별 대표 지수
# ─────────────────────────────────────────────────────────────────────────────
REGION_INDICES = {
    "us": [
        ("^GSPC",  "S&P 500",    "USD"),
        ("^IXIC",  "NASDAQ",     "USD"),
        ("^DJI",   "다우",       "USD"),
        ("^RUT",   "Russell 2000","USD"),
        ("^VIX",   "VIX",        ""),
    ],
    "europe": [
        ("^STOXX50E", "Euro Stoxx 50", "EUR"),
        ("^GDAXI",    "DAX",          "EUR"),
        ("^FTSE",     "FTSE 100",     "GBP"),
        ("^FCHI",     "CAC 40",       "EUR"),
    ],
    "china": [
        ("000001.SS", "상해 종합",  "CNY"),
        ("^HSI",      "항셍",       "HKD"),
        ("399001.SZ", "선전 성분",  "CNY"),
        ("^HSCE",     "H주 지수",  "HKD"),
    ],
    "japan": [
        ("^N225",  "닛케이 225",  "JPY"),
        ("1306.T", "TOPIX ETF",  "JPY"),
    ],
    "korea": [
        ("^KS11",  "KOSPI",      "KRW"),
        ("^KQ11",  "KOSDAQ",     "KRW"),
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# 미국 GICS 섹터 ETF (SPDR 시리즈 — 정식 GICS 기준)
# ─────────────────────────────────────────────────────────────────────────────
US_SECTORS = [
    ("XLK",  "정보기술",          "Information Technology"),
    ("XLF",  "금융",              "Financials"),
    ("XLV",  "헬스케어",          "Health Care"),
    ("XLC",  "커뮤니케이션",      "Communication Services"),
    ("XLY",  "경기소비재",        "Consumer Discretionary"),
    ("XLI",  "산업재",            "Industrials"),
    ("XLE",  "에너지",            "Energy"),
    ("XLP",  "필수소비재",        "Consumer Staples"),
    ("XLB",  "소재",              "Materials"),
    ("XLU",  "유틸리티",          "Utilities"),
    ("XLRE", "부동산",            "Real Estate"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 지역별 시총 상위 종목 (내림차순 시총 기준, ticker / 한글명 / GICS 섹터 / 국가)
# ─────────────────────────────────────────────────────────────────────────────
UNIVERSE = {
    "us": [
        ("AAPL",  "애플",           "정보기술"),
        ("MSFT",  "마이크로소프트",  "정보기술"),
        ("NVDA",  "엔비디아",        "정보기술"),
        ("GOOGL", "알파벳",          "커뮤니케이션"),
        ("AMZN",  "아마존",          "경기소비재"),
        ("META",  "메타",            "커뮤니케이션"),
        ("AVGO",  "브로드컴",        "정보기술"),
        ("TSLA",  "테슬라",          "경기소비재"),
        ("BRK-B", "버크셔",          "금융"),
        ("LLY",   "일라이릴리",      "헬스케어"),
        ("JPM",   "JP모건",          "금융"),
        ("V",     "비자",            "금융"),
        ("XOM",   "엑슨모빌",        "에너지"),
        ("UNH",   "유나이티드헬스",  "헬스케어"),
        ("COST",  "코스트코",        "필수소비재"),
        ("MA",    "마스터카드",      "금융"),
        ("NFLX",  "넷플릭스",        "커뮤니케이션"),
        ("AMD",   "AMD",             "정보기술"),
        ("CRM",   "세일즈포스",      "정보기술"),
        ("WMT",   "월마트",          "필수소비재"),
        ("PG",    "P&G",             "필수소비재"),
        ("JNJ",   "존슨앤존슨",      "헬스케어"),
        ("HD",    "홈디포",          "경기소비재"),
        ("CVX",   "쉐브론",          "에너지"),
        ("ORCL",  "오라클",          "정보기술"),
    ],
    "europe": [
        ("ASML.AS",  "ASML",         "정보기술"),
        ("SAP.DE",   "SAP",          "정보기술"),
        ("NOVO-B.CO","노보 노디스크", "헬스케어"),
        ("MC.PA",    "LVMH",         "경기소비재"),
        ("NESN.SW",  "네슬레",       "필수소비재"),
        ("RO.SW",    "로슈",         "헬스케어"),
        ("AZN.L",    "아스트라제네카","헬스케어"),
        ("SHEL.L",   "쉘",           "에너지"),
        ("NOVN.SW",  "노바티스",     "헬스케어"),
        ("TTE.PA",   "토탈에너지",   "에너지"),
        ("SIE.DE",   "지멘스",       "산업재"),
        ("HSBA.L",   "HSBC",         "금융"),
        ("RMS.PA",   "에르메스",     "경기소비재"),
        ("OR.PA",    "로레알",       "필수소비재"),
        ("ALV.DE",   "알리안츠",     "금융"),
        ("SU.PA",    "슈나이더",     "산업재"),
        ("ULVR.L",   "유니레버",     "필수소비재"),
        ("ABI.BR",   "AB인베브",     "필수소비재"),
    ],
    "china": [
        ("0700.HK",   "텐센트",         "커뮤니케이션"),
        ("9988.HK",   "알리바바",       "경기소비재"),
        ("600519.SS", "구이저우 마오타이","필수소비재"),
        ("3690.HK",   "메이투안",       "경기소비재"),
        ("300750.SZ", "CATL",           "경기소비재"),
        ("1398.HK",   "중국공상은행",   "금융"),
        ("601857.SS", "페트로차이나",   "에너지"),
        ("1211.HK",   "BYD",            "경기소비재"),
        ("0939.HK",   "중국건설은행",   "금융"),
        ("2318.HK",   "핑안보험",       "금융"),
        ("0941.HK",   "차이나모바일",   "커뮤니케이션"),
        ("1810.HK",   "샤오미",         "정보기술"),
        ("9618.HK",   "JD닷컴",         "경기소비재"),
        ("9999.HK",   "넷이즈",         "커뮤니케이션"),
        ("3988.HK",   "중국은행",       "금융"),
    ],
    "japan": [
        ("7203.T",  "토요타",       "경기소비재"),
        ("6758.T",  "소니",         "경기소비재"),
        ("8306.T",  "미쓰비시UFJ", "금융"),
        ("6861.T",  "키엔스",       "산업재"),
        ("6501.T",  "히타치",       "산업재"),
        ("8035.T",  "도쿄일렉트론","정보기술"),
        ("9984.T",  "소프트뱅크G", "커뮤니케이션"),
        ("6098.T",  "리크루트",     "산업재"),
        ("4063.T",  "신에쓰화학",   "소재"),
        ("8316.T",  "SMFG",        "금융"),
        ("9983.T",  "패스트리테일링","경기소비재"),
        ("7974.T",  "닌텐도",       "커뮤니케이션"),
        ("8058.T",  "미쓰비시상사", "산업재"),
        ("4568.T",  "다이이치산쿄", "헬스케어"),
        ("6857.T",  "어드밴테스트", "정보기술"),
    ],
    "korea": [
        ("005930.KS", "삼성전자",      "정보기술"),
        ("000660.KS", "SK하이닉스",   "정보기술"),
        ("373220.KS", "LG에너지솔루션","경기소비재"),
        ("207940.KS", "삼성바이오로직스","헬스케어"),
        ("005380.KS", "현대차",        "경기소비재"),
        ("000270.KS", "기아",          "경기소비재"),
        ("068270.KS", "셀트리온",      "헬스케어"),
        ("105560.KS", "KB금융",        "금융"),
        ("035420.KS", "NAVER",         "커뮤니케이션"),
        ("006400.KS", "삼성SDI",       "경기소비재"),
        ("005490.KS", "POSCO홀딩스",  "소재"),
        ("035720.KS", "카카오",        "커뮤니케이션"),
        ("055550.KS", "신한지주",      "금융"),
        ("012450.KS", "한화에어로스페이스","산업재"),
        ("329180.KS", "HD현대중공업",  "산업재"),
    ],
}

REGION_META = {
    "us":     {"name": "미국",   "flag": "🇺🇸", "currency": "USD"},
    "europe": {"name": "유럽",   "flag": "🇪🇺", "currency": "EUR"},
    "china":  {"name": "중국",   "flag": "🇨🇳", "currency": "HKD"},
    "japan":  {"name": "일본",   "flag": "🇯🇵", "currency": "JPY"},
    "korea":  {"name": "한국",   "flag": "🇰🇷", "currency": "KRW"},
}

# ─────────────────────────────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────────────────────────────

def safe_float(v, decimals=2):
    try:
        f = float(v)
        if not (f == f):   # NaN
            return None
        return round(f, decimals)
    except Exception:
        return None


def pct_chg(cur, prev):
    try:
        if prev and prev != 0:
            return round((cur - prev) / abs(prev) * 100, 2)
    except Exception:
        pass
    return None


def last_two_closes(df_or_series):
    """DataFrame 또는 Series에서 마지막 두 유효 종가 반환 (cur, prev)."""
    try:
        s = df_or_series.dropna()
        if len(s) < 2:
            return None, None
        return float(s.iloc[-1]), float(s.iloc[-2])
    except Exception:
        return None, None


def batch_daily(tickers: list[str]) -> dict:
    """tickers 리스트를 한 번에 다운로드 → {ticker: {price, chg, chgPct, spark}} dict."""
    if not tickers:
        return {}
    try:
        # group_by 지정 없이 (default="column") → raw["Close"] 로 접근
        raw = yf.download(
            tickers, period="30d", interval="1d",
            auto_adjust=True, progress=False,
        )
    except Exception as e:
        print(f"  [warn] batch_daily 실패: {e}", file=sys.stderr)
        return {}

    # Close 슬라이스 추출
    try:
        if len(tickers) == 1:
            # 단일 티커: columns = ['Close','High',…] (flat)
            close_all = raw[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            # 다수 티커: columns MultiIndex, top-level = price field
            close_all = raw["Close"]
    except Exception as e:
        print(f"  [warn] Close 슬라이스 실패: {e}", file=sys.stderr)
        return {}

    result = {}
    for t in tickers:
        try:
            if t not in close_all.columns:
                continue
            close = close_all[t].dropna()

            if close.empty:
                continue
            cur, prev = float(close.iloc[-1]), float(close.iloc[-2]) if len(close) >= 2 else (float(close.iloc[-1]), None)
            chg_pct = pct_chg(cur, prev) if prev else None
            chg = round(cur - prev, 4) if prev else None
            # sparkline: 마지막 20일 종가
            spark = [safe_float(v, 4) for v in close.iloc[-20:].tolist()]
            result[t] = {
                "price":  safe_float(cur, 4),
                "chg":    safe_float(chg, 4),
                "chgPct": chg_pct,
                "spark":  spark,
            }
        except Exception as e:
            print(f"  [warn] {t} 파싱 실패: {e}", file=sys.stderr)
    return result


def fetch_news(ticker: str, max_items: int = 4) -> list:
    """yfinance Ticker.news → [{title, publisher, link, time}]"""
    try:
        tk = yf.Ticker(ticker)
        raw_news = tk.news or []
        items = []
        for n in raw_news[:max_items * 2]:
            # yfinance ≥ 0.2.55 uses nested 'content' key
            if isinstance(n.get("content"), dict):
                c = n["content"]
                title = c.get("title", "")
                pub   = c.get("provider", {}).get("displayName", "")
                link  = (c.get("canonicalUrl") or {}).get("url", "") or c.get("clickThroughUrl", {}).get("url", "")
                ts    = c.get("pubDate", "")
            else:
                title = n.get("title", "")
                pub   = n.get("publisher", "")
                link  = n.get("link", "")
                ts_raw = n.get("providerPublishTime", 0)
                ts    = datetime.fromtimestamp(ts_raw, tz=timezone.utc).isoformat() if ts_raw else ""
            if title:
                items.append({"title": title, "publisher": pub, "link": link, "time": ts})
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"  [warn] {ticker} 뉴스 실패: {e}", file=sys.stderr)
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 메인 빌드
# ─────────────────────────────────────────────────────────────────────────────

def build():
    now_utc = datetime.now(timezone.utc)
    today_str = now_utc.strftime("%Y-%m-%d")

    # 1. 전체 티커 수집 (한번에 다운로드)
    all_index_tickers  = [t for region in REGION_INDICES.values() for t, _, _ in region]
    sector_tickers     = [etf for etf, _, _ in US_SECTORS]
    universe_tickers   = [t for stocks in UNIVERSE.values() for t, _, _ in stocks]
    all_tickers = list(dict.fromkeys(all_index_tickers + sector_tickers + universe_tickers))

    print(f"[fetch_daily] 티커 {len(all_tickers)}개 다운로드 중…")
    price_map = batch_daily(all_tickers)
    print(f"[fetch_daily] 수신: {len(price_map)}개")

    regions_out = []

    for rkey, rmeta in REGION_META.items():
        # ── 1. 지수 ──────────────────────────────────────────────────────────
        indices_out = []
        for ticker, name, currency in REGION_INDICES[rkey]:
            d = price_map.get(ticker)
            if d is None:
                continue
            indices_out.append({
                "ticker":  ticker,
                "name":    name,
                "price":   d["price"],
                "chg":     d["chg"],
                "chgPct":  d["chgPct"],
                "currency": currency,
                "spark":   d["spark"],
            })

        # ── 2. GICS 섹터 ─────────────────────────────────────────────────────
        if rkey == "us":
            # 미국: SPDR ETF 직접 사용
            sectors_out = []
            for etf, name_ko, name_en in US_SECTORS:
                d = price_map.get(etf)
                if d is None:
                    continue
                sectors_out.append({
                    "name":    name_ko,
                    "nameEn":  name_en,
                    "etf":     etf,
                    "chgPct":  d["chgPct"],
                    "price":   d["price"],
                })
        else:
            # 다른 지역: 종목 구성 GICS 평균
            sector_buckets: dict[str, list] = {}
            for ticker, _, sector in UNIVERSE[rkey]:
                d = price_map.get(ticker)
                if d and d["chgPct"] is not None:
                    sector_buckets.setdefault(sector, []).append(d["chgPct"])
            sectors_out = []
            for sector, vals in sorted(sector_buckets.items()):
                avg = round(sum(vals) / len(vals), 2)
                sectors_out.append({
                    "name":   sector,
                    "chgPct": avg,
                })
            sectors_out.sort(key=lambda x: x["chgPct"] if x["chgPct"] is not None else 0, reverse=True)

        # ── 3. 종목 등락 테이블 ───────────────────────────────────────────────
        stocks_out = []
        for rank, (ticker, name_ko, sector) in enumerate(UNIVERSE[rkey], 1):
            d = price_map.get(ticker)
            if d is None:
                continue
            stocks_out.append({
                "rank":    rank,
                "ticker":  ticker,
                "name":    name_ko,
                "sector":  sector,
                "price":   d["price"],
                "chg":     d["chg"],
                "chgPct":  d["chgPct"],
            })

        # ── 4. 특징주 (당일 절대 변동 상위) ──────────────────────────────────
        valid = [s for s in stocks_out if s["chgPct"] is not None]
        sorted_by_abs = sorted(valid, key=lambda x: abs(x["chgPct"]), reverse=True)
        featured_tickers = []

        top_gainer = max(valid, key=lambda x: x["chgPct"], default=None)
        top_loser  = min(valid, key=lambda x: x["chgPct"], default=None)
        top_mover  = sorted_by_abs[0] if sorted_by_abs else None

        featured_raw = []
        seen = set()
        for item in [top_mover, top_gainer, top_loser]:
            if item and item["ticker"] not in seen:
                seen.add(item["ticker"])
                featured_raw.append(item)
                featured_tickers.append(item["ticker"])

        featured_out = []
        for item in featured_raw:
            news = fetch_news(item["ticker"])
            spark = price_map.get(item["ticker"], {}).get("spark", [])
            featured_out.append({
                **item,
                "spark": spark,
                "news":  news,
            })

        regions_out.append({
            "key":      rkey,
            "name":     rmeta["name"],
            "flag":     rmeta["flag"],
            "indices":  indices_out,
            "sectors":  sectors_out,
            "stocks":   stocks_out,
            "featured": featured_out,
        })

    payload = {
        "as_of":         today_str,
        "generated_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regions":       regions_out,
    }

    js = "// 일간 시장 동향 데이터 (공개 데이터, 평문). fetch_daily.py로 갱신.\n"
    js += "window.DAILY = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT.write_text(js, encoding="utf-8")
    print(f"[fetch_daily] → {OUT.name} 저장 완료 ({len(js):,} bytes)")


if __name__ == "__main__":
    build()
