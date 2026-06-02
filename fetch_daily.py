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
from datetime import datetime, timezone, timedelta
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
# 11개 GICS 섹터 표준 순서 (US_SECTORS와 동일한 키 이름 사용)
# ─────────────────────────────────────────────────────────────────────────────
GICS_ORDER = [
    "정보기술", "금융", "헬스케어", "커뮤니케이션",
    "경기소비재", "산업재", "에너지", "필수소비재",
    "소재", "유틸리티", "부동산",
]

# ─────────────────────────────────────────────────────────────────────────────
# 지역별 시총 상위 종목 (내림차순 시총 기준, ticker / 한글명 / GICS 섹터)
# 전 지역에서 11개 GICS 섹터가 최소 1개 이상 커버되도록 종목 선정
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
        ("NEE",   "넥스트에라",      "유틸리티"),   # 유틸리티
        ("AMT",   "아메리칸타워",    "부동산"),      # 부동산(REIT)
        ("LIN",   "린데",            "소재"),        # 소재
    ],
    "europe": [
        ("ASML.AS",  "ASML",          "정보기술"),
        ("SAP.DE",   "SAP",           "정보기술"),
        ("NOVO-B.CO","노보 노디스크",  "헬스케어"),
        ("MC.PA",    "LVMH",          "경기소비재"),
        ("NESN.SW",  "네슬레",        "필수소비재"),
        ("RO.SW",    "로슈",          "헬스케어"),
        ("AZN.L",    "아스트라제네카","헬스케어"),
        ("SHEL.L",   "쉘",            "에너지"),
        ("NOVN.SW",  "노바티스",      "헬스케어"),
        ("TTE.PA",   "토탈에너지",    "에너지"),
        ("SIE.DE",   "지멘스",        "산업재"),
        ("HSBA.L",   "HSBC",          "금융"),
        ("RMS.PA",   "에르메스",      "경기소비재"),
        ("OR.PA",    "로레알",        "필수소비재"),
        ("ALV.DE",   "알리안츠",      "금융"),
        ("SU.PA",    "슈나이더",      "산업재"),
        ("ULVR.L",   "유니레버",      "필수소비재"),
        ("ABI.BR",   "AB인베브",      "필수소비재"),
        ("DTE.DE",   "도이체텔레콤",  "커뮤니케이션"),  # 커뮤니케이션
        ("BAS.DE",   "BASF",          "소재"),           # 소재
        ("IBE.MC",   "이베르드롤라",  "유틸리티"),       # 유틸리티
        ("AI.PA",    "에어리키드",    "소재"),
        ("VNA.DE",   "보노비아",      "부동산"),         # 부동산
    ],
    "china": [
        ("0700.HK",   "텐센트",           "커뮤니케이션"),
        ("9988.HK",   "알리바바",         "경기소비재"),
        ("600519.SS", "구이저우 마오타이", "필수소비재"),
        ("3690.HK",   "메이투안",         "경기소비재"),
        ("300750.SZ", "CATL",             "경기소비재"),
        ("1398.HK",   "중국공상은행",     "금융"),
        ("601857.SS", "페트로차이나",     "에너지"),
        ("1211.HK",   "BYD",              "경기소비재"),
        ("0939.HK",   "중국건설은행",     "금융"),
        ("2318.HK",   "핑안보험",         "금융"),
        ("0941.HK",   "차이나모바일",     "커뮤니케이션"),
        ("1810.HK",   "샤오미",           "정보기술"),
        ("9618.HK",   "JD닷컴",           "경기소비재"),
        ("9999.HK",   "넷이즈",           "커뮤니케이션"),
        ("3988.HK",   "중국은행",         "금융"),
        ("1093.HK",   "CSPC제약",         "헬스케어"),   # 헬스케어
        ("1177.HK",   "중국생물제약",     "헬스케어"),
        ("1766.HK",   "CRRC",             "산업재"),     # 산업재
        ("2899.HK",   "자진광업",         "소재"),       # 소재
        ("0836.HK",   "화런전력",         "유틸리티"),   # 유틸리티
        ("0960.HK",   "롱포그룹",         "부동산"),     # 부동산
    ],
    "japan": [
        ("7203.T",  "토요타",         "경기소비재"),
        ("6758.T",  "소니",           "경기소비재"),
        ("8306.T",  "미쓰비시UFJ",   "금융"),
        ("6861.T",  "키엔스",         "산업재"),
        ("6501.T",  "히타치",         "산업재"),
        ("8035.T",  "도쿄일렉트론",  "정보기술"),
        ("9984.T",  "소프트뱅크G",   "커뮤니케이션"),
        ("6098.T",  "리크루트",       "산업재"),
        ("4063.T",  "신에쓰화학",     "소재"),
        ("8316.T",  "SMFG",          "금융"),
        ("9983.T",  "패스트리테일링","경기소비재"),
        ("7974.T",  "닌텐도",         "커뮤니케이션"),
        ("8058.T",  "미쓰비시상사",   "산업재"),
        ("4568.T",  "다이이치산쿄",   "헬스케어"),
        ("6857.T",  "어드밴테스트",   "정보기술"),
        ("1605.T",  "INPEX",         "에너지"),         # 에너지
        ("2503.T",  "기린HD",        "필수소비재"),     # 필수소비재
        ("9432.T",  "NTT",           "커뮤니케이션"),
        ("9501.T",  "도쿄전력HD",    "유틸리티"),       # 유틸리티
        ("8801.T",  "미쓰이부동산",  "부동산"),         # 부동산
        ("4502.T",  "다케다제약",    "헬스케어"),
    ],
    "korea": [
        ("005930.KS", "삼성전자",          "정보기술"),
        ("000660.KS", "SK하이닉스",        "정보기술"),
        ("373220.KS", "LG에너지솔루션",    "경기소비재"),
        ("207940.KS", "삼성바이오로직스",  "헬스케어"),
        ("005380.KS", "현대차",            "경기소비재"),
        ("000270.KS", "기아",              "경기소비재"),
        ("068270.KS", "셀트리온",          "헬스케어"),
        ("105560.KS", "KB금융",            "금융"),
        ("035420.KS", "NAVER",             "커뮤니케이션"),
        ("006400.KS", "삼성SDI",           "경기소비재"),
        ("005490.KS", "POSCO홀딩스",       "소재"),
        ("035720.KS", "카카오",            "커뮤니케이션"),
        ("055550.KS", "신한지주",          "금융"),
        ("012450.KS", "한화에어로스페이스","산업재"),
        ("329180.KS", "HD현대중공업",      "산업재"),
        ("096770.KS", "SK이노베이션",      "에너지"),    # 에너지
        ("033780.KS", "KT&G",             "필수소비재"), # 필수소비재
        ("015760.KS", "한국전력",          "유틸리티"),  # 유틸리티
        ("051900.KS", "LG생활건강",        "필수소비재"),
        ("011200.KS", "HMM",              "산업재"),
        ("402340.KS", "SK스퀘어",         "정보기술"),
        ("330590.KS", "롯데리츠",         "부동산"),    # 부동산(REIT)
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
# 거래소별 정규장 마감 시각 (UTC, 서머타임 기준 근사). yfinance가 진행 중인
# 장중 일봉을 마지막 종가처럼 반환하므로, 마감 전 봉은 "미체결"로 보고 제외한다.
# 티커 suffix → (hour, minute) UTC. 데이터 지연 대비 10분 버퍼를 추가로 적용.
# ─────────────────────────────────────────────────────────────────────────────
MARKET_CLOSE_UTC_BY_SUFFIX = {
    ".L":   (15, 30),   # London
    ".PA":  (15, 30),   # Euronext Paris
    ".AS":  (15, 30),   # Euronext Amsterdam
    ".BR":  (15, 30),   # Euronext Brussels
    ".DE":  (15, 30),   # Xetra Frankfurt
    ".MC":  (15, 30),   # Madrid
    ".MI":  (15, 30),   # Milan
    ".SW":  (15, 20),   # SIX Swiss
    ".CO":  (15, 0),    # Copenhagen
    ".T":   (6, 0),     # Tokyo (15:00 JST)
    ".HK":  (8, 0),     # Hong Kong (16:00 HKT)
    ".SS":  (7, 0),     # Shanghai (15:00 CST)
    ".SZ":  (7, 0),     # Shenzhen
    ".KS":  (6, 30),    # KRX (15:30 KST)
    ".KQ":  (6, 30),    # KOSDAQ
}
# 지수 티커는 suffix가 없으므로 개별 매핑
MARKET_CLOSE_UTC_BY_TICKER = {
    "^GSPC": (20, 0), "^IXIC": (20, 0), "^DJI": (20, 0), "^RUT": (20, 0), "^VIX": (21, 15),
    "^STOXX50E": (15, 30), "^GDAXI": (15, 30), "^FTSE": (15, 30), "^FCHI": (15, 30),
    "000001.SS": (7, 0), "399001.SZ": (7, 0), "^HSI": (8, 0), "^HSCE": (8, 0),
    "^N225": (6, 0), "^TPX": (6, 0),
    "^KS11": (6, 30), "^KQ11": (6, 30),
}


def market_close_utc(ticker: str):
    """티커의 정규장 마감 시각 (UTC hour, minute). 기본값 = 미국(20:00)."""
    if ticker in MARKET_CLOSE_UTC_BY_TICKER:
        return MARKET_CLOSE_UTC_BY_TICKER[ticker]
    for suf, hm in MARKET_CLOSE_UTC_BY_SUFFIX.items():
        if ticker.endswith(suf):
            return hm
    return (20, 0)   # 미국(suffix 없음)

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


def is_settled(bar_date, ticker, now_utc) -> bool:
    """해당 일봉이 정규장 마감 후 확정된 종가인지 판정 (장중 진행봉 제외)."""
    h, m = market_close_utc(ticker)
    close_dt = datetime(bar_date.year, bar_date.month, bar_date.day, h, m, tzinfo=timezone.utc)
    # 데이터 지연 대비 10분 버퍼
    return now_utc >= close_dt + timedelta(minutes=10)


def batch_daily(tickers: list[str], now_utc: datetime) -> dict:
    """tickers 리스트를 한 번에 다운로드 → {ticker: {price, chg, chgPct, spark}} dict.
    장중 진행 중인 미체결 일봉은 제외하고, 마지막으로 '확정된 종가'를 기준으로 한다."""
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
            # 장중 진행 중인 미체결 일봉 제외: 뒤에서부터 첫 '확정 종가' 위치를 찾는다.
            cur_i = None
            for i in range(len(close) - 1, -1, -1):
                if is_settled(close.index[i].date(), t, now_utc):
                    cur_i = i
                    break
            if cur_i is None:
                continue
            prev_i = cur_i - 1 if cur_i >= 1 else None
            cur = float(close.iloc[cur_i])
            prev = float(close.iloc[prev_i]) if prev_i is not None else None
            last_date = str(close.index[cur_i].date())
            prev_date = str(close.index[prev_i].date()) if prev_i is not None else None
            chg_pct = pct_chg(cur, prev) if prev is not None else None
            chg = round(cur - prev, 4) if prev is not None else None
            # sparkline: 확정 종가까지의 마지막 20일
            spark = [safe_float(v, 4) for v in close.iloc[:cur_i + 1].iloc[-20:].tolist()]
            result[t] = {
                "price":  safe_float(cur, 4),
                "chg":    safe_float(chg, 4),
                "chgPct": chg_pct,
                "spark":  spark,
                "date":     last_date,
                "prevDate": prev_date,
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


def build_commentary(rmeta, indices_out, sectors_out, featured_out) -> list:
    """지수·섹터·특징주 수치로부터 그날의 시황 코멘트를 문장으로 생성한다.
    LLM 없이 계산된 숫자에 기반한 룰 기반 요약 (데이터 갱신 시 자동 갱신)."""
    lines = []

    # 1) 대표 지수 방향
    idx_valid = [i for i in indices_out if i.get("chgPct") is not None]
    if idx_valid:
        up   = [i for i in idx_valid if i["chgPct"] > 0]
        down = [i for i in idx_valid if i["chgPct"] < 0]
        lead = idx_valid[0]
        dir_word = "상승" if (lead["chgPct"] or 0) > 0 else ("하락" if (lead["chgPct"] or 0) < 0 else "보합")
        breadth = f"지수 {len(up)}개 상승·{len(down)}개 하락"
        lines.append(
            f"{rmeta['name']} 증시는 {lead['name']}이(가) {lead['chgPct']:+.2f}% {dir_word}하며 "
            f"{breadth}로 마감했다."
        )

    # 2) 섹터 주도 / 부진
    sec_valid = [s for s in sectors_out if s.get("chgPct") is not None]
    if sec_valid:
        best  = max(sec_valid, key=lambda s: s["chgPct"])
        worst = min(sec_valid, key=lambda s: s["chgPct"])
        if best["name"] != worst["name"]:
            lines.append(
                f"섹터별로는 {best['name']}({best['chgPct']:+.2f}%)이(가) 강세를 주도한 반면 "
                f"{worst['name']}({worst['chgPct']:+.2f}%)은(는) 가장 부진했다."
            )

    # 3) 특징주 (최대 상승 / 최대 하락)
    feat_valid = [f for f in featured_out if f.get("chgPct") is not None]
    if feat_valid:
        g = max(feat_valid, key=lambda f: f["chgPct"])
        l = min(feat_valid, key=lambda f: f["chgPct"])
        parts = []
        if g["chgPct"] > 0:
            parts.append(f"{g['name']}이(가) {g['chgPct']:+.2f}%로 가장 크게 올랐고")
        if l["chgPct"] < 0 and l["ticker"] != g["ticker"]:
            parts.append(f"{l['name']}은(는) {l['chgPct']:+.2f}%로 낙폭이 컸다")
        if parts:
            lines.append("종목별로는 " + ", ".join(parts) + ".")

    return lines


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
    price_map = batch_daily(all_tickers, now_utc)
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
                "date":    d.get("date"),
            })

        # ── 지역 기준일: 대표 지수들의 마지막 종가 날짜 중 최빈/최신값 ──────
        region_dates = [
            price_map[t]["date"]
            for t, _, _ in REGION_INDICES[rkey]
            if price_map.get(t) and price_map[t].get("date")
        ]
        # 종목 기준일도 보강 (지수가 없을 때 대비)
        if not region_dates:
            region_dates = [
                price_map[t]["date"]
                for t, _, _ in UNIVERSE[rkey]
                if price_map.get(t) and price_map[t].get("date")
            ]
        region_as_of = max(region_dates) if region_dates else today_str
        # 전일 대비 기준 (직전 거래일)
        region_prev = None
        for t, _, _ in REGION_INDICES[rkey]:
            d = price_map.get(t)
            if d and d.get("date") == region_as_of and d.get("prevDate"):
                region_prev = d["prevDate"]
                break

        # ── 2. GICS 섹터 (11개 전부 표시, 데이터 없으면 chgPct=null) ─────────
        if rkey == "us":
            # 미국: SPDR ETF 직접 사용 — ETF별 name_ko → GICS_ORDER 정렬
            etf_map = {name_ko: (etf, name_en, price_map.get(etf)) for etf, name_ko, name_en in US_SECTORS}
            sectors_out = []
            for sector_name in GICS_ORDER:
                if sector_name in etf_map:
                    etf, name_en, d = etf_map[sector_name]
                    sectors_out.append({
                        "name":    sector_name,
                        "nameEn":  name_en,
                        "etf":     etf,
                        "chgPct":  d["chgPct"] if d else None,
                        "price":   d["price"]   if d else None,
                    })
                else:
                    sectors_out.append({"name": sector_name, "chgPct": None})
        else:
            # 다른 지역: 종목 구성 GICS 평균 — 데이터 없는 섹터도 null로 포함
            sector_buckets: dict[str, list] = {}
            for ticker, _, sector in UNIVERSE[rkey]:
                d = price_map.get(ticker)
                if d and d["chgPct"] is not None:
                    sector_buckets.setdefault(sector, []).append(d["chgPct"])
            sectors_out = []
            for sector_name in GICS_ORDER:
                vals = sector_buckets.get(sector_name)
                avg = round(sum(vals) / len(vals), 2) if vals else None
                sectors_out.append({
                    "name":   sector_name,
                    "chgPct": avg,
                    "count":  len(vals) if vals else 0,
                })

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

        # ── 4. 특징주 (당일 절대 변동 상위 5종목) ────────────────────────────
        valid = [s for s in stocks_out if s["chgPct"] is not None]
        sorted_by_abs = sorted(valid, key=lambda x: abs(x["chgPct"]), reverse=True)
        # 등락 양방향이 고르게 보이도록 상위 5개를 절대 변동 기준으로 선정
        featured_raw = sorted_by_abs[:5]

        featured_out = []
        for item in featured_raw:
            news = fetch_news(item["ticker"])
            spark = price_map.get(item["ticker"], {}).get("spark", [])
            featured_out.append({
                **item,
                "spark": spark,
                "news":  news,
            })

        commentary = build_commentary(rmeta, indices_out, sectors_out, featured_out)

        regions_out.append({
            "key":        rkey,
            "name":       rmeta["name"],
            "flag":       rmeta["flag"],
            "as_of":      region_as_of,   # 이 지역 데이터의 실제 마지막 거래일
            "prev_date":  region_prev,    # 전일 대비 기준 거래일
            "indices":    indices_out,
            "sectors":    sectors_out,
            "stocks":     stocks_out,
            "featured":   featured_out,
            "commentary": commentary,     # 시황 코멘트 (룰 기반 자동 생성)
        })

    # 전역 as_of = 모든 지역 중 가장 최신 거래일
    all_region_dates = [r["as_of"] for r in regions_out if r.get("as_of")]
    global_as_of = max(all_region_dates) if all_region_dates else today_str

    payload = {
        "as_of":         global_as_of,
        "generated_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regions":       regions_out,
    }

    js = "// 일간 시장 동향 데이터 (공개 데이터, 평문). fetch_daily.py로 갱신.\n"
    js += "window.DAILY = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT.write_text(js, encoding="utf-8")
    print(f"[fetch_daily] → {OUT.name} 저장 완료 ({len(js):,} bytes)")


if __name__ == "__main__":
    build()
