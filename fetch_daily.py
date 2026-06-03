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
import re
import urllib.request
import xml.etree.ElementTree as ET
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


def fetch_period_returns(tickers: list, now_utc: datetime) -> dict:
    """티커별 연초대비(YTD)·월초대비(MTD) 수익률(%) 동시 산출.
    기준일(마지막 확정 종가)의 연·월을 기준으로, 직전 연도/직전 월의 마지막
    종가 대비 변동률을 계산한다. 반환: {ticker: {"ytd": x, "mtd": y}}.
    데이터 부족 시 해당 티커/항목은 생략(None)."""
    out = {}
    if not tickers:
        return out
    try:
        raw = yf.download(tickers, period="1y", interval="1d",
                          auto_adjust=True, progress=False)
        if len(tickers) == 1:
            close_all = raw[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            close_all = raw["Close"]
    except Exception as e:
        print(f"  [warn] 기간수익률 다운로드 실패: {e}", file=sys.stderr)
        return out
    for t in tickers:
        try:
            if t not in close_all.columns:
                continue
            close = close_all[t].dropna()
            if close.empty:
                continue
            # 현재 = 마지막 확정 종가 (장중 진행봉 제외)
            cur_i = None
            for i in range(len(close) - 1, -1, -1):
                if is_settled(close.index[i].date(), t, now_utc):
                    cur_i = i
                    break
            if cur_i is None:
                continue
            cur = float(close.iloc[cur_i])
            cur_date = close.index[cur_i].date()
            dates = [d.date() if hasattr(d, "date") else d for d in close.index]
            vals = [float(v) for v in close.values]
            # YTD 기준: 직전 연도 마지막 종가 (없으면 올해 첫 종가)
            ytd_prev = [vals[i] for i in range(len(dates))
                        if dates[i].year < cur_date.year]
            ytd_base = ytd_prev[-1] if ytd_prev else vals[0]
            # MTD 기준: 직전 월 마지막 종가 (없으면 이번 달 첫 종가)
            mtd_prev = [vals[i] for i in range(len(dates))
                        if (dates[i].year, dates[i].month) < (cur_date.year, cur_date.month)]
            mtd_base = mtd_prev[-1] if mtd_prev else vals[0]
            out[t] = {
                "ytd": pct_chg(cur, ytd_base),
                "mtd": pct_chg(cur, mtd_base),
            }
        except Exception as e:
            print(f"  [warn] {t} 기간수익률 실패: {e}", file=sys.stderr)
    return out


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
# RSS 뉴스 수집 (investing.com 시장 뉴스 + Yahoo Finance 종목별 헤드라인)
# yfinance.news 보다 관련성·설명(snippet)이 풍부해 시황 코멘트를 보강한다.
# 각 소스를 try/except 로 감싸 cron 안정성(차단·타임아웃)을 확보한다.
# ─────────────────────────────────────────────────────────────────────────────
RSS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/121.0 Safari/537.36")

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean_text(s: str, limit: int = 220) -> str:
    """HTML 태그 제거 + 공백 정리 + 길이 제한."""
    if not s:
        return ""
    s = _TAG_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    if len(s) > limit:
        s = s[:limit].rstrip() + "…"
    return s


def _http_get(url: str, timeout: int = 12) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": RSS_UA,
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _parse_rss(xml_bytes: bytes, max_items: int) -> list:
    """RSS 2.0 → [{title, desc, link, time, publisher}]"""
    items = []
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return items
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        link = (item.findtext("link") or "").strip()
        desc = _clean_text(item.findtext("description") or "")
        pub = (item.findtext("pubDate") or "").strip()
        src_el = item.find("source")
        src = src_el.text.strip() if (src_el is not None and src_el.text) else ""
        items.append({"title": title, "desc": desc, "link": link,
                      "time": pub, "publisher": src})
        if len(items) >= max_items:
            break
    return items


def fetch_rss(url: str, max_items: int = 6) -> list:
    try:
        return _parse_rss(_http_get(url), max_items)
    except Exception as e:
        print(f"  [warn] RSS 실패 {url}: {e}", file=sys.stderr)
        return []


def fetch_yahoo_ticker_news(ticker: str, max_items: int = 4) -> list:
    """Yahoo Finance 종목별 RSS — 헤드라인 + 설명 snippet 포함."""
    url = (f"https://feeds.finance.yahoo.com/rss/2.0/headline?"
           f"s={ticker}&region=US&lang=en-US")
    items = fetch_rss(url, max_items)
    for it in items:
        if not it.get("publisher"):
            it["publisher"] = "Yahoo Finance"
    return items


# investing.com 시장/매크로 뉴스 피드 (글로벌 주요 이벤트)
INVESTING_FEEDS = [
    "https://www.investing.com/rss/news_25.rss",   # 주요 시장 뉴스
    "https://www.investing.com/rss/news_301.rss",  # 시장·경제
]


def fetch_investing_news(max_items: int = 5) -> list:
    """investing.com 글로벌 시장 뉴스 → 시장을 움직인 주요 이벤트."""
    out, seen = [], set()
    for url in INVESTING_FEEDS:
        for it in fetch_rss(url, max_items + 2):
            key = it["title"].lower()
            if key in seen:
                continue
            seen.add(key)
            if not it.get("publisher"):
                it["publisher"] = "Investing.com"
            out.append(it)
            if len(out) >= max_items:
                return out
    return out


def fetch_featured_news(ticker: str, max_items: int = 4) -> list:
    """특징주 뉴스: Yahoo 종목 RSS 우선, 비면 yfinance.news 로 폴백."""
    news = fetch_yahoo_ticker_news(ticker, max_items=max_items)
    if news:
        return news
    return fetch_news(ticker, max_items=max_items)


def load_macro_snapshot():
    """benchmarks.js에서 VIX·금리·유가·환율 등 매크로 스냅샷을 읽어온다."""
    try:
        s = (HERE / "benchmarks.js").read_text(encoding="utf-8")
        j = json.loads(s[s.find("{"):s.rfind("}") + 1])
    except Exception as e:
        print(f"  [warn] benchmarks.js 로드 실패: {e}", file=sys.stderr)
        return {}
    return {it.get("ticker"): it for it in j.get("indices", []) if it.get("ticker")}


def build_macro_line(macro: dict) -> str:
    """글로벌 매크로 한 줄 요약 (변동성·금리·유가·환율)."""
    if not macro:
        return ""
    parts = []
    vix = macro.get("^VIX")
    if vix and vix.get("current") is not None:
        lvl = vix["current"]; dp = vix.get("daily_pct") or 0
        senti = "위험선호 우위" if lvl < 17 else ("경계감이 상존하는" if lvl < 22 else "위험회피 심리가 강한")
        parts.append(f"변동성지수(VIX) {lvl:.1f}({dp:+.1f}%)로 {senti} 국면")
    tnx = macro.get("^TNX")
    if tnx and tnx.get("current") is not None:
        parts.append(f"미 10년물 국채금리 {tnx['current']:.2f}%")
    wti = macro.get("CL=F")
    if wti and wti.get("current") is not None:
        parts.append(f"WTI 유가 {wti['current']:.1f}달러({(wti.get('daily_pct') or 0):+.1f}%)")
    krw = macro.get("KRW=X")
    if krw and krw.get("current") is not None:
        parts.append(f"원/달러 환율 {krw['current']:,.0f}원({(krw.get('daily_pct') or 0):+.1f}%)")
    if not parts:
        return ""
    return "글로벌 매크로 환경은 " + ", ".join(parts) + " 흐름을 나타냈다."


# GICS 성장(경기민감) vs 방어 섹터 분류 — 로테이션 해석용
GROWTH_SECTORS    = {"정보기술", "커뮤니케이션", "경기소비재"}
DEFENSIVE_SECTORS = {"필수소비재", "유틸리티", "헬스케어"}


def build_commentary(rmeta, indices_out, sectors_out, featured_out,
                     macro_line="", events=None) -> dict:
    """지수·섹터·특징주·뉴스로부터 풍부한 시황 코멘트(구조화 객체)를 생성한다.
    종목 등락 사유는 실제 수집된 뉴스 헤드라인을 근거로 제시한다."""

    # ── 1) 시장 총평 (방향·강도·breadth) ─────────────────────────────────
    summary = ""
    idx_valid = [i for i in indices_out if i.get("chgPct") is not None]
    if idx_valid:
        up   = [i for i in idx_valid if i["chgPct"] > 0]
        down = [i for i in idx_valid if i["chgPct"] < 0]
        lead = idx_valid[0]
        cp = lead["chgPct"] or 0
        mag = abs(cp)
        if   mag >= 1.5: mword = "큰 폭으로"
        elif mag >= 0.7: mword = "뚜렷하게"
        elif mag >  0.2: mword = "완만하게"
        else:            mword = "강보합권에서" if cp >= 0 else "약보합권에서"
        dir_word = "상승" if cp > 0 else ("하락" if cp < 0 else "보합")
        if   len(up) > len(down): breadth = "상승 종목이 우위를 보인"
        elif len(down) > len(up): breadth = "하락 종목이 우위를 보인"
        else:                     breadth = "등락이 엇갈린 혼조세의"
        others = idx_valid[1:4]
        others_txt = ", ".join(f"{o['name']} {o['chgPct']:+.2f}%" for o in others)
        summary = (
            f"{rmeta['name']} 증시는 대표지수인 {lead['name']}이 {cp:+.2f}% {mword} {dir_word} 마감했다. "
            f"주요 지수 {len(up)}개가 오르고 {len(down)}개가 내리는 등 {breadth} 장세였으며, "
            f"{others_txt} 등의 흐름을 보였다."
        )

    # ── 2) 섹터 로테이션 해석 ────────────────────────────────────────────
    sectors_txt = ""
    sec_valid = [s for s in sectors_out if s.get("chgPct") is not None]
    if sec_valid:
        ups   = sorted(sec_valid, key=lambda s: s["chgPct"], reverse=True)[:3]
        downs = sorted(sec_valid, key=lambda s: s["chgPct"])[:2]
        g_vals = [s["chgPct"] for s in sec_valid if s["name"] in GROWTH_SECTORS]
        d_vals = [s["chgPct"] for s in sec_valid if s["name"] in DEFENSIVE_SECTORS]
        rot = ""
        if g_vals and d_vals:
            g_avg = sum(g_vals) / len(g_vals)
            d_avg = sum(d_vals) / len(d_vals)
            if   g_avg - d_avg > 0.3: rot = " 성장·경기민감 섹터가 방어주를 앞서며 위험선호(risk-on) 색채가 두드러졌다."
            elif d_avg - g_avg > 0.3: rot = " 방어 섹터가 성장주 대비 선전하며 위험회피(risk-off) 심리가 우위였다."
            else:                     rot = " 성장주와 방어주 간 뚜렷한 우열 없이 종목별 차별화 장세가 나타났다."
        sectors_txt = (
            "섹터별로는 "
            + ", ".join(f"{s['name']}({s['chgPct']:+.2f}%)" for s in ups)
            + "이(가) 강세를 주도했고, "
            + ", ".join(f"{s['name']}({s['chgPct']:+.2f}%)" for s in downs)
            + "은(는) 부진했다." + rot
        )

    # ── 3) 종목별 등락 사유 (실제 뉴스 헤드라인 근거) ────────────────────
    movers = []
    feat_valid = [f for f in featured_out if f.get("chgPct") is not None]
    feat_sorted = sorted(feat_valid, key=lambda f: abs(f["chgPct"]), reverse=True)[:5]
    for f in feat_sorted:
        news = f.get("news") or []
        detail = ""
        if news:
            reason = news[0].get("title", "")
            detail = news[0].get("desc", "") or ""
            source = news[0].get("publisher", "")
            link   = news[0].get("link", "")
        else:
            ud = "강세" if f["chgPct"] >= 0 else "약세"
            reason = (f"개별 호재·악재 뉴스는 확인되지 않았으며, {f.get('sector','해당')} "
                      f"섹터 전반의 {ud} 흐름에 연동된 것으로 보인다.")
            source = ""; link = ""
        movers.append({
            "name":   f["name"],
            "ticker": f["ticker"],
            "sector": f.get("sector", ""),
            "chgPct": f["chgPct"],
            "dir":    "up" if f["chgPct"] >= 0 else "down",
            "reason": reason,
            "detail": detail,
            "source": source,
            "link":   link,
        })

    return {
        "summary":  summary,
        "macro":    macro_line,
        "sectors":  sectors_txt,
        "events":   events or [],
        "movers":   movers,
    }


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

    # 연초대비(YTD)·월초대비(MTD) 수익률 (지수·섹터ETF·종목 전체, 별도 1년치 다운로드)
    pr_map = fetch_period_returns(all_tickers, now_utc)
    print(f"[fetch_daily] YTD·MTD {len(pr_map)}개 계산")

    # 매크로 스냅샷 (benchmarks.js) → 글로벌 매크로 코멘트
    macro = load_macro_snapshot()
    macro_line = build_macro_line(macro)

    # 글로벌 시장 뉴스 (investing.com) — 모든 지역의 "주요 이벤트"에 공통 반영
    global_events = fetch_investing_news(max_items=5)
    print(f"[fetch_daily] investing.com 글로벌 뉴스 {len(global_events)}건")

    regions_out = []

    for rkey, rmeta in REGION_META.items():
        # ── 1. 지수 ──────────────────────────────────────────────────────────
        indices_out = []
        for ticker, name, currency in REGION_INDICES[rkey]:
            d = price_map.get(ticker)
            if d is None:
                continue
            pr = pr_map.get(ticker) or {}
            indices_out.append({
                "ticker":  ticker,
                "name":    name,
                "price":   d["price"],
                "chg":     d["chg"],
                "chgPct":  d["chgPct"],
                "ytdPct":  pr.get("ytd"),
                "mtdPct":  pr.get("mtd"),
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
                    epr = pr_map.get(etf) or {}
                    sectors_out.append({
                        "name":    sector_name,
                        "nameEn":  name_en,
                        "etf":     etf,
                        "chgPct":  d["chgPct"] if d else None,
                        "price":   d["price"]   if d else None,
                        "ytdPct":  epr.get("ytd"),
                        "mtdPct":  epr.get("mtd"),
                    })
                else:
                    sectors_out.append({"name": sector_name, "chgPct": None,
                                        "ytdPct": None, "mtdPct": None})
        else:
            # 다른 지역: 종목 구성 GICS 평균 — 데이터 없는 섹터도 null로 포함
            sector_buckets: dict[str, list] = {}
            sector_pr_buckets: dict[str, dict] = {}   # name → {"ytd": [...], "mtd": [...]}
            for ticker, _, sector in UNIVERSE[rkey]:
                d = price_map.get(ticker)
                if d and d["chgPct"] is not None:
                    sector_buckets.setdefault(sector, []).append(d["chgPct"])
                pr = pr_map.get(ticker)
                if pr:
                    b = sector_pr_buckets.setdefault(sector, {"ytd": [], "mtd": []})
                    if pr.get("ytd") is not None:
                        b["ytd"].append(pr["ytd"])
                    if pr.get("mtd") is not None:
                        b["mtd"].append(pr["mtd"])

            def _avg(arr):
                return round(sum(arr) / len(arr), 2) if arr else None

            sectors_out = []
            for sector_name in GICS_ORDER:
                vals = sector_buckets.get(sector_name)
                prb = sector_pr_buckets.get(sector_name, {})
                sectors_out.append({
                    "name":   sector_name,
                    "chgPct": _avg(vals) if vals else None,
                    "count":  len(vals) if vals else 0,
                    "ytdPct": _avg(prb.get("ytd", [])),
                    "mtdPct": _avg(prb.get("mtd", [])),
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
                "spark":   d.get("spark", []),
            })

        # ── 4. 특징주 (당일 절대 변동 상위 5종목) ────────────────────────────
        valid = [s for s in stocks_out if s["chgPct"] is not None]
        sorted_by_abs = sorted(valid, key=lambda x: abs(x["chgPct"]), reverse=True)
        # 등락 양방향이 고르게 보이도록 상위 5개를 절대 변동 기준으로 선정
        featured_raw = sorted_by_abs[:5]

        featured_out = []
        for item in featured_raw:
            news = fetch_featured_news(item["ticker"])
            spark = price_map.get(item["ticker"], {}).get("spark", [])
            featured_out.append({
                **item,
                "spark": spark,
                "news":  news,
            })

        # 주요 이벤트: 지역 지수 레벨 뉴스 + investing.com 글로벌 시장 뉴스
        events = []
        seen_titles = set()

        def _add_event(title, source, link, desc="", scope="region"):
            t = (title or "").strip()
            if not t or t.lower() in seen_titles:
                return
            seen_titles.add(t.lower())
            events.append({"title": t, "source": source or "",
                           "link": link or "", "desc": desc or "", "scope": scope})

        # (a) 지역 대표 지수 관련 뉴스 (지역 고유 헤드라인 우선 노출)
        if REGION_INDICES[rkey]:
            lead_idx_ticker = REGION_INDICES[rkey][0][0]
            for n in fetch_news(lead_idx_ticker, max_items=2):
                _add_event(n.get("title"), n.get("publisher"), n.get("link"),
                           n.get("desc", ""), scope="region")
        # (b) investing.com 글로벌 시장 뉴스 (매크로·이벤트 컨텍스트)
        for n in global_events[:3]:
            _add_event(n.get("title"), n.get("publisher"), n.get("link"),
                       n.get("desc", ""), scope="global")

        commentary = build_commentary(rmeta, indices_out, sectors_out, featured_out,
                                      macro_line=macro_line, events=events)

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
