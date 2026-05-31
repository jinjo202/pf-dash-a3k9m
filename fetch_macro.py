"""
매크로·시장 레짐 모니터 데이터 파이프라인.

장기(약 25년) 시계열을 수집해 4개 축으로 점수화하고, 과거 유사 국면을
최근접 이웃으로 찾아 이후 수익률(base rate)을 계산한 뒤, 자동 코멘터리와
함께 macro-data.js (평문, 공개 데이터)로 저장한다.

데이터 소스 (API 키 불필요):
  - FRED CSV 엔드포인트  https://fred.stlouisfed.org/graph/fredgraph.csv?id=...
  - yfinance            (S&P 500 / KOSPI 장기 지수)
  - benchmarks.js       (fetch_benchmarks.py가 만든 현재 Forward PER 등 재사용)

매크로 데이터(FRED)는 월간 갱신이 많지만, cron이 매일 돌려도 무해하다
(변경 없으면 git diff 없음 → commit 안 됨).
"""
import json
import sys
import io
import math
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "macro-data.js"
BENCH = HERE / "benchmarks.js"

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"
START = "2000-01-01"

# ── 수동 입력 (무료 장기 시계열이 없는 항목) ──────────────────────────────
# ISM 제조업 PMI: FRED에서 라이선스 문제로 중단됨. 최신값만 수동 유지.
# 갱신: ISM 발표(매월 첫 영업일) 후 current/prev/as_of 수정.
MANUAL = {
    "ism_pmi": {
        "name": "ISM 제조업 PMI",
        "pillar": "macro",
        "current": 52.7,     # 발표치 (S&P Global flash는 55.3이나 ISM 공식 기준)
        "prev": 52.0,
        "as_of": "2026-04-30",
        "unit": "",
        "note": "ISM 공식 발표치. 50 위 = 확장. FRED 무료 장기시계열 없어 수동 유지.",
    },
    "cnn_fng": {
        "name": "CNN 공포·탐욕 지수",
        "pillar": "sentiment",
        "current": 60,
        "prev": 55,
        "as_of": "2026-05-29",
        "unit": "",
        "note": "0=극단적 공포, 100=극단적 탐욕. 무료 API 없어 수동 유지.",
    },
    "aaii_spread": {
        "name": "AAII 불-베어 스프레드",
        "pillar": "sentiment",
        "current": -6.3,     # 강세% − 약세%
        "prev": -11.9,
        "as_of": "2026-05-28",
        "unit": "%p",
        "note": "AAII 개인투자자 설문: 강세 35.6%·중립 22.6%·약세 41.9%(역사평균 강세 37.5%). "
                "역발상 지표 — 비관(음수)일수록 바닥 신호. aaii.com/sentimentsurvey 주간 갱신.",
    },
    "put_call": {
        "name": "CBOE 풋/콜 비율(총)",
        "pillar": "sentiment",
        "current": 0.74,
        "prev": 0.85,
        "as_of": "2026-05-28",
        "unit": "",
        "note": "옵션 시장 심리(주식 P/C 0.39·SPX 0.88 동반). 역발상 — 높을수록(공포) 강세, "
                "0.7 아래는 낙관·과열. ※요청의 '풋콜 패리티'는 심리지표인 풋/콜 비율로 해석. cboe.com 일간.",
    },
}

# 수급(flows) 수동 지표 — 무료 자동 API 없음(KOFIA/KRX/노무라 추정 등). 별도 dict.
MANUAL_FLOWS = {
    "cta_pos": {
        "name": "미국 CTA 주식 노출(백분위)",
        "pillar": "flows",
        "current": 43,      # %ile (노무라/DB 추정)
        "prev": 48,
        "as_of": "2026-05-29",
        "unit": "%ile",
        "note": "시스템(추세추종) 펀드 주식 노출 백분위. 노무라: 역사평균 약 5% 하회·여전히 롱. "
                "낮을수록 추가 매수 여력(되돌림 위험 작음). 주간 갱신.",
    },
    "retail_alloc": {
        "name": "미국 리테일 주식비중",
        "pillar": "flows",
        "current": 70,      # 가계/개인 주식 배분 % (추정)
        "prev": 69,
        "as_of": "2026-05-29",
        "unit": "%",
        "note": "리테일 주문비중 36%(사상최고)·가계 주식배분 고점권. 역발상 — 높을수록 후기·과열. "
                "AAII 자산배분 설문/Vanda 참조, 월간 갱신.",
    },
    "kr_deposit": {
        "name": "한국 투자자예탁금",
        "pillar": "flows",
        "current": 95,      # 조원 (추정 — KOFIA freesis 확정치로 갱신 필요)
        "prev": 88,
        "as_of": "2026-05-29",
        "unit": "조원",
        "note": "증시 대기자금. 개인 순매수 지속으로 증가 추세(추정치 — KOFIA freesis 증시자금추이에서 확정). "
                "증가=매수 여력 확대.",
    },
    "kr_flows": {
        "name": "한국 투자자별 수급(외국인, 월)",
        "pillar": "flows",
        "current": -44.7,   # 외국인 KOSPI 월 순매수(조원)
        "prev": -30.0,
        "as_of": "2026-05-29",
        "unit": "조원",
        "note": "5월 KOSPI: 외국인 -44.7조(역대 최대 월 순매도, 차익실현)·개인 대규모 순매수로 흡수·"
                "기관 +2.4조. 구조적으로 외인 의존도↓(연기금·ETF 흡수). KRX data.krx.co.kr 갱신.",
    },
}


# ── HTTP / 파싱 헬퍼 ──────────────────────────────────────────────────────
def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 macro-monitor"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def fred_csv(series_id, start=START):
    """FRED CSV → (dates[ISO], values[float]). 결측('.')은 건너뜀."""
    url = FRED_CSV.format(id=series_id, start=start)
    txt = http_get(url)
    dates, vals = [], []
    for line in txt.splitlines()[1:]:  # 헤더 스킵
        parts = line.split(",")
        if len(parts) < 2:
            continue
        d, v = parts[0].strip(), parts[1].strip()
        if not d or v in (".", "", "NA"):
            continue
        try:
            vals.append(float(v))
            dates.append(d)
        except ValueError:
            continue
    return dates, vals


def yf_monthly(ticker, start=START):
    """yfinance 월말 종가 → (dates[ISO], values[float])."""
    import yfinance as yf
    import pandas as pd
    hist = yf.Ticker(ticker).history(start=start, auto_adjust=False, interval="1mo")
    if hist.empty:
        return [], []
    dates, vals = [], []
    for ts, v in hist["Close"].items():
        if pd.isna(v):
            continue
        dates.append(ts.strftime("%Y-%m-%d"))
        vals.append(float(v))
    return dates, vals


def to_month_end(dates, vals):
    """일별 시계열 → 월말 마지막값으로 다운샘플. {YYYY-MM: value} dict."""
    out = {}
    for d, v in zip(dates, vals):
        ym = d[:7]
        out[ym] = v  # 같은 달이면 뒤쪽(최신)이 덮어씀 = 월말값
    return out


def yoy(dates, vals):
    """월간 레벨 시계열 → 전년동월비(%) 시계열. 12개월 전 값과 비교."""
    by_month = {d[:7]: v for d, v in zip(dates, vals)}
    keys = sorted(by_month)
    out_d, out_v = [], []
    for k in keys:
        y, m = int(k[:4]), int(k[5:7])
        prev_key = f"{y-1:04d}-{m:02d}"
        if prev_key in by_month and by_month[prev_key] != 0:
            out_d.append(k + "-01")
            out_v.append((by_month[k] / by_month[prev_key] - 1) * 100)
    return out_d, out_v


def mom_change(dates, vals):
    """월간 레벨 → 전월대비 변화량(절대). payrolls(천명) 용."""
    by_month = {d[:7]: v for d, v in zip(dates, vals)}
    keys = sorted(by_month)
    out_d, out_v = [], []
    for i in range(1, len(keys)):
        out_d.append(keys[i] + "-01")
        out_v.append(by_month[keys[i]] - by_month[keys[i - 1]])
    return out_d, out_v


def zscore(vals, lookback=None):
    """최신값의 z-score + 백분위(%). lookback=최근 N개만 사용(None=전체)."""
    arr = vals[-lookback:] if lookback else vals
    if len(arr) < 8:
        return None, None
    mean = sum(arr) / len(arr)
    var = sum((x - mean) ** 2 for x in arr) / len(arr)
    sd = math.sqrt(var)
    cur = vals[-1]
    z = (cur - mean) / sd if sd > 0 else 0.0
    pct = 100.0 * sum(1 for x in arr if x <= cur) / len(arr)
    return round(z, 2), round(pct, 1)


def downsample_monthly(dates, vals, max_points=320):
    """차트용: 월말로 줄이고 최대 길이 제한."""
    me = to_month_end(dates, vals)
    keys = sorted(me)
    if len(keys) > max_points:
        keys = keys[-max_points:]
    return [k + "-01" for k in keys], [round(me[k], 4) for k in keys]


# ── 시그널 점수화 (+1 = 주식 강세, -1 = 약세) ────────────────────────────
def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))


def score_indicator(key, cur, hist_vals, ctx):
    """지표별 강세/약세 점수 [-1,+1]. ctx=파생값 dict."""
    # 최근 추세 (3개월 변화)
    chg3 = (hist_vals[-1] - hist_vals[-4]) if len(hist_vals) >= 4 else 0.0

    if key == "ism_pmi":
        return clamp((cur - 50) / 5.0)                      # 50 기준, ±5pt = ±1
    if key == "cpi_yoy":
        # 2% 목표 근처 호재, 4%+ 악재, 추세 하락이면 가산
        lvl = clamp((2.5 - cur) / 2.0)
        trd = clamp(-chg3 / 1.5) * 0.5
        return clamp(lvl + trd)
    if key == "core_cpi_yoy":
        lvl = clamp((2.5 - cur) / 1.5)
        trd = clamp(-chg3 / 1.0) * 0.5
        return clamp(lvl + trd)
    if key == "unemployment":
        # 절대수준보다 *상승*이 위험 (Sahm). 3개월 상승폭 가중
        return clamp(-chg3 / 0.5)
    if key == "payrolls":
        # 월 +15만 이상 견조, 0 이하 위험
        return clamp((cur - 100) / 150.0)
    if key == "fed_funds":
        # 실질금리(명목-코어CPI) 높으면 긴축적=악재
        real = ctx.get("real_rate")
        if real is None:
            return 0.0
        return clamp((1.0 - real) / 2.0)                    # 실질 1% 중립, 3%=악재
    if key == "consumer_sent":
        z = ctx.get("z", 0) or 0
        return clamp(z / 1.5)
    if key == "yield_curve":
        # 역전(<0) 경고. 가파른 정상화는 호재
        if cur < 0:
            return clamp(cur / 0.5)                          # -0.5%면 -1
        return clamp(cur / 1.5)
    if key == "m2_yoy":
        # 유동성 증가 호재. 0% 중립, 6%+ 강세, 마이너스 악재
        return clamp(cur / 5.0)
    if key == "baa_spread":
        # 신용스프레드(Baa-10Y) 낮으면 위험선호 호재, 4%+ 스트레스
        return clamp((2.2 - cur) / 1.3)
    if key == "usdkrw":
        # 원화 약세(상승) = 위험회피/한국 악재. 3개월 변화 가중
        return clamp(-chg3 / 40.0)
    if key == "vix":
        # 낮으면 안정(호재), 25+ 악재, 35+ 패닉(역발상 일부 상쇄)
        if cur >= 32:
            return clamp(-1.0 + (cur - 32) / 30.0 * 0.4)     # 극단 패닉은 바닥 시그널 일부
        return clamp((18 - cur) / 10.0)
    if key == "oil_yoy":
        # 유가 급등(인플레/비용) 악재
        return clamp(-cur / 40.0)
    if key == "spx_mom":
        # 12개월 모멘텀 + 200일선 위/아래
        m = clamp(cur / 15.0)
        above = ctx.get("above_200d")
        if above is not None:
            m = clamp(m + (0.3 if above else -0.4))
        return clamp(m)
    if key == "erp":
        # 주식위험프리미엄(어닝일드-10Y). 높으면 주식 매력(호재)
        return clamp((cur - 1.0) / 3.0)
    if key == "spx_fwd_pe":
        # Forward PER 높으면 비쌈(장기 악재). 17 적정, 22+ 부담
        return clamp((18.0 - cur) / 4.0)
    if key == "kospi_fwd_pe":
        return clamp((11.0 - cur) / 4.0)
    # ── 수동 지표 (센티먼트/수급) ──
    if key == "cnn_fng":
        return clamp((cur - 50) / 30.0)
    if key == "aaii_spread":
        # 역발상: 비관(음수)→강세, 과열(고+)→약세
        return clamp(-cur / 25.0)
    if key == "put_call":
        # 역발상: 높을수록(공포)→강세, 낮을수록(낙관)→약세
        return clamp((cur - 0.95) / 0.35)
    if key == "cta_pos":
        # 포지셔닝 낮을수록 매수여력(호재), 높을수록 되돌림 위험
        return clamp((50 - cur) / 40.0)
    if key == "retail_alloc":
        # 역발상: 리테일 비중 높을수록 후기·과열(약세)
        return clamp((62 - cur) / 25.0)
    if key == "kr_deposit":
        # 예탁금 증가(대기자금)→호재. hist_vals=[prev,cur]
        chg = hist_vals[-1] - hist_vals[0] if len(hist_vals) >= 2 else 0.0
        return clamp(chg / 12.0)
    if key == "kr_flows":
        # 외국인 순매수(조원). 음수=유출(약세)·국내 흡수로 완화
        return clamp(cur / 80.0)
    return 0.0


SIGNAL_WORDS = [
    (0.5, "강한 호재", "pos"), (0.2, "호재", "pos"),
    (-0.2, "중립", "neu"), (-0.5, "악재", "neg"), (-99, "강한 악재", "neg"),
]


def signal_label(score):
    for thr, label, cls in SIGNAL_WORDS:
        if score >= thr:
            return label, cls
    return "강한 악재", "neg"


# ── 지표 정의 ─────────────────────────────────────────────────────────────
# (key, name, pillar, source, transform, decimals, unit, invert_chart, desc)
INDICATORS = [
    # 매크로
    ("cpi_yoy",      "미국 CPI (YoY)",       "macro", "CPIAUCSL",  "yoy",   1, "%",  "물가. 낮고 하락할수록 멀티플 우호"),
    ("core_cpi_yoy", "미국 근원 CPI (YoY)",  "macro", "CPILFESL",  "yoy",   1, "%",  "에너지·식품 제외 기조 물가"),
    ("unemployment", "미국 실업률",          "macro", "UNRATE",    "level", 1, "%",  "절대수준보다 *상승 전환*이 침체 신호"),
    ("payrolls",     "비농업 고용 (전월비)", "macro", "PAYEMS",    "mom",   0, "천명","월 +15만 이상 견조"),
    ("fed_funds",    "연방기금금리",         "macro", "FEDFUNDS",  "level", 2, "%",  "실질금리가 높을수록 긴축적"),
    ("consumer_sent","소비자심리(미시간)",   "macro", "UMCSENT",   "level", 1, "",   "소비 모멘텀 선행"),
    ("yield_curve",  "장단기 금리차(10Y-2Y)","macro", "T10Y2Y",    "daily", 2, "%p", "역전은 침체 경고, 정상화는 회복 신호"),
    ("oil_yoy",      "WTI 유가 (YoY)",       "macro", "DCOILWTICO","oilyoy",1, "%",  "급등 시 인플레·비용 압력"),
    # 밸류에이션
    ("spx_fwd_pe",   "S&P500 12M Fwd PER",   "valuation", "bench", "bench", 1, "배", "이익 대비 가격. 높을수록 기대수익 낮음"),
    ("kospi_fwd_pe", "KOSPI 12M Fwd PER",    "valuation", "bench", "bench", 1, "배", "한국 밸류에이션"),
    ("erp",          "주식위험프리미엄(ERP)","valuation", "derived","derived",2,"%p","S&P 어닝일드 − 미 10Y. 높을수록 주식 매력"),
    ("us10y",        "미국 10Y 금리",        "valuation", "DGS10", "daily", 2, "%",  "할인율. 급등 시 밸류 부담"),
    # 수급·유동성
    ("m2_yoy",       "M2 통화량 (YoY)",      "flows", "M2SL",          "yoy",   1, "%", "유동성. 증가할수록 위험자산 우호"),
    ("baa_spread",   "신용 스프레드(Baa-10Y)","flows", "BAA10Y",       "daily", 2, "%p","위험선호 게이지. 낮을수록 강세, 4%+ 스트레스"),
    ("usdkrw",       "USD/KRW",              "flows", "DEXKOUS",       "daily", 1, "원","원화 약세는 위험회피·외인 유출"),
    # 센티먼트
    ("vix",          "VIX 변동성",           "sentiment", "VIXCLS", "daily", 1, "",  "공포 게이지. 낮을수록 안정"),
    ("spx_mom",      "S&P500 12M 모멘텀",    "sentiment", "spxmom", "spxmom",1, "%",  "추세. 200일선 상회 여부 포함"),
]

PILLARS = {
    "macro":     {"name": "매크로", "weight": 0.25},
    "valuation": {"name": "밸류에이션", "weight": 0.18},
    "flows":     {"name": "수급·유동성", "weight": 0.17},
    "sentiment": {"name": "센티먼트", "weight": 0.15},
    "earnings":  {"name": "기업이익", "weight": 0.25},
}

# 과거 유사국면 매칭에 쓸 deep-history 지표 (월간 정렬)
ANALOG_FEATURES = ["cpi_yoy", "core_cpi_yoy", "unemployment", "fed_funds",
                   "yield_curve", "m2_yoy", "baa_spread", "vix", "oil_yoy", "spx_mom"]


# ── 기업이익(Forward EPS / ERR) 바스켓 ────────────────────────────────────
# 국가·섹터별 대표 대형주. yfinance 애널리스트 추정치(eps_revisions/eps_trend/
# earnings_estimate)를 종목별로 받아 집계한다. 종목 가감은 여기만 수정.
US_SECTORS = {
    "반도체·AI HW": ["NVDA", "AVGO", "AMD", "MU", "TSM", "ASML"],
    "소프트웨어·IT": ["MSFT", "AAPL", "ORCL", "CRM", "ADBE", "PLTR"],
    "커뮤니케이션": ["GOOGL", "META", "NFLX", "DIS"],
    "금융": ["JPM", "BAC", "GS", "WFC", "MS"],
    "헬스케어": ["LLY", "UNH", "JNJ", "ABBV", "MRK"],
    "임의소비재": ["AMZN", "TSLA", "HD", "MCD", "NKE"],
    "에너지": ["XOM", "CVX", "COP", "SLB"],
    "산업재": ["GE", "CAT", "BA", "HON", "UNP"],
}
KR_SECTORS = {
    "반도체": ["005930.KS", "000660.KS"],
    "2차전지·소재": ["373220.KS", "006400.KS", "051910.KS"],
    "자동차": ["005380.KS", "000270.KS"],
    "금융": ["105560.KS", "055550.KS", "086790.KS"],
    "인터넷·IT": ["035420.KS", "035720.KS"],
    "바이오": ["207940.KS", "068270.KS"],
    "방산·조선": ["012450.KS", "042660.KS", "009540.KS"],
    "엔터·미디어": ["352820.KS", "035900.KQ", "041510.KQ"],
    "철강·소재": ["005490.KS", "004020.KS", "010130.KS"],
    "통신": ["017670.KS", "030200.KS", "032640.KS"],
    "유통·필수소비재": ["097950.KS", "090430.KS", "271560.KS"],
}
# 국가 레벨 요약만 내는 추가 국가 (섹터 분해 없음)
COUNTRY_EXTRA = {
    "EU": ("유럽", ["ASML", "SAP", "NVO", "MC.PA", "SHEL", "SIE.DE"]),
    "JP": ("일본", ["TM", "SONY", "8035.T", "6861.T", "6501.T"]),
    "CN": ("중국", ["BABA", "PDD", "JD", "BIDU", "TCEHY"]),
}

# 국가별 연도 EPS (2020~2027E). 클릭 시 막대그래프·YoY용.
#  US = S&P500 Bottom-Up EPS 실값(FactSet). 나머지 = 지수(2020=100) 근사치(편집 가능).
#  actual_through 이후 연도는 추정(E)으로 표시.
COUNTRY_EPS_ANNUAL = {
    "US": {"unit": "$ (S&P500 Bottom-Up, FactSet)", "actual_through": 2025, "source": "FactSet",
           "eps": {"2020": 140.23, "2021": 208.01, "2022": 219.17, "2023": 220.21,
                   "2024": 243.02, "2025": 271.23, "2026": 337.47, "2027": 389.45}},
    "KR": {"unit": "지수(2020=100, 근사)", "actual_through": 2025, "source": "추정·편집 가능",
           "eps": {"2020": 100, "2021": 130, "2022": 96, "2023": 80,
                   "2024": 128, "2025": 175, "2026": 300, "2027": 345}},
    "EU": {"unit": "지수(2020=100, 근사)", "actual_through": 2025, "source": "추정·편집 가능",
           "eps": {"2020": 100, "2021": 142, "2022": 156, "2023": 150,
                   "2024": 156, "2025": 166, "2026": 181, "2027": 196}},
    "JP": {"unit": "지수(2020=100, 근사)", "actual_through": 2025, "source": "추정·편집 가능",
           "eps": {"2020": 100, "2021": 128, "2022": 145, "2023": 160,
                   "2024": 176, "2025": 188, "2026": 203, "2027": 218}},
    "CN": {"unit": "지수(2020=100, 근사)", "actual_through": 2025, "source": "추정·편집 가능",
           "eps": {"2020": 100, "2021": 112, "2022": 100, "2023": 106,
                   "2024": 112, "2025": 117, "2026": 124, "2027": 133}},
}


# 섹터별 주요 이슈/지표 — 정성 코멘트. 발표·뉴스 흐름에 맞춰 주기적으로 갱신.
# (자동 산출 불가 항목. as_of로 신선도 표시)
ISSUES_AS_OF = "2026-05-31"
US_SECTOR_ISSUES = {
    "반도체·AI HW": {"issue": "AI 인프라 capex 지속 상향, HBM·가속기 공급부족. 하이퍼스케일러 capex 가이던스 추가 상향이 EPS 견인.",
                    "indicators": "하이퍼스케일러 capex, HBM 가격, 데이터센터 매출, 파운드리 가동률"},
    "소프트웨어·IT": {"issue": "AI 수익화(코파일럿·에이전트) 본격화 vs 클라우드 마진. 기업 IT예산 견조.",
                    "indicators": "클라우드 성장률, RPO, AI ARR, Net Revenue Retention"},
    "커뮤니케이션": {"issue": "광고 회복 + AI 검색·추천. 콘텐츠 비용 통제. 규제 리스크 잔존.",
                  "indicators": "광고단가(CPM), MAU/DAU, 광고주 지출, AI 검색 점유"},
    "금융": {"issue": "금리 동결·가파른 커브로 NIM 우호. 신용비용 정상화. IB 수수료 회복.",
            "indicators": "순이자마진(NIM), 대손충당금, 예대율, IB 수수료"},
    "헬스케어": {"issue": "GLP-1(비만) 수요 강세, 약가 정책 리스크. 파이프라인 모멘텀.",
              "indicators": "GLP-1 처방량, 약가규제, 임상 성공률, 특허 만료"},
    "임의소비재": {"issue": "고유가·고물가가 실질소비 압박. 전기차 수요 둔화 vs AI 광고.",
                "indicators": "실질 소매판매, 휘발유가격, 소비자신뢰, 전기차 인도량"},
    "에너지": {"issue": "이란 전쟁發 유가 $100+ 고착. EPS 상향이지만 지정학 변동성 큼.",
            "indicators": "WTI/Brent, 정제마진, 호르무즈 리스크, 리그수"},
    "산업재": {"issue": "리쇼어링·전력인프라·방산 수요. 자본재 수주 견조.",
            "indicators": "ISM 신규주문, 자본재 수주, 전력 capex, 방산 예산"},
}
KR_SECTOR_ISSUES = {
    "반도체": {"issue": "메모리 슈퍼사이클 — HBM·DDR5 가격 급등으로 삼성·하이닉스 EPS 컨센서스 급상향. KOSPI 시총 절반 차지, 쏠림 위험.",
              "indicators": "DRAM·NAND 고정가, HBM capa, 미국 대중 수출규제, 재고"},
    "2차전지·소재": {"issue": "전기차 수요 둔화·중국 과잉공급 부담. AMPC 보조금·ESS 수요가 변수.",
                  "indicators": "전기차 판매, 리튬가격, AMPC, 가동률, 수주잔고"},
    "자동차": {"issue": "원화 약세(1,500+)로 수출채산성 개선 vs 미국 관세·전기차 둔화. 밸류업 배당 기대.",
            "indicators": "미국 판매·인센티브, 원/달러, 관세, 하이브리드 믹스"},
    "금융": {"issue": "밸류업(주주환원) 정책 수혜 핵심. 금리 동결로 NIM 안정, 충당금 정상화.",
            "indicators": "NIM, CET1, 주주환원율(배당+자사주), 연체율, 밸류업 공시"},
    "인터넷·IT": {"issue": "광고·커머스 회복 + AI 투자비용. 일본·글로벌 확장.",
                "indicators": "광고매출, 커머스 GMV, AI capex, MAU"},
    "바이오": {"issue": "바이오시밀러·CDMO 수주 확대. 환율 수혜. 미국 약가·생물보안법 변수.",
            "indicators": "CDMO 수주, 시밀러 점유, FDA 승인, 환율"},
    "방산·조선": {"issue": "유럽 재무장·중동 분쟁으로 수출 호황. 조선 슈퍼사이클(LNG선·친환경).",
               "indicators": "수출 수주잔고, 신조선가지수, 방산 수출계약, 후판가격"},
    "엔터·미디어": {"issue": "K팝 글로벌 확장·앨범/투어 회복, 신인 IP 모멘텀. 중국 한한령 완화 기대 vs 아티스트 리스크.",
                "indicators": "앨범 판매, 콘서트 동원, 일본·미국 매출, 신인 데뷔"},
    "철강·소재": {"issue": "중국 감산·인프라 수요가 가격 변수. 2차전지 소재(리튬·니켈) 다각화. 전력·조선향 후판 견조.",
              "indicators": "중국 철강가·재고, 후판가격, 원료탄, 전기차·ESS 소재 수요"},
    "통신": {"issue": "5G 성숙·요금 규제 속 배당 매력(밸류업). AI·데이터센터·B2B 신사업이 성장축.",
            "indicators": "ARPU, 가입자, 배당성향, AI/IDC 매출, 마케팅비"},
    "유통·필수소비재": {"issue": "내수 회복 더딤·고물가 부담 vs 중국 리오프닝·화장품 수출. 환율 수혜 일부.",
                    "indicators": "내수 소비, 중국·미국 화장품 수출, 원가(곡물·환율), 면세 회복"},
}


def _cell(df, row, col):
    try:
        import pandas as pd
        if df is None or row not in df.index or col not in df.columns:
            return None
        v = df.loc[row, col]
        return None if pd.isna(v) else float(v)
    except Exception:
        return None


def ticker_earnings(tk):
    """종목 1개 → {up30, down30, rev90, growth_cy, growth_ny, trend5(정규화 5점), n}.
    데이터 없으면 None."""
    import yfinance as yf
    try:
        t = yf.Ticker(tk)
        er = t.eps_revisions
        tr = t.eps_trend
        ee = t.earnings_estimate
    except Exception:
        return None
    up30 = _cell(er, "0y", "upLast30days")
    down30 = _cell(er, "0y", "downLast30days")
    cur = _cell(tr, "0y", "current")
    d7 = _cell(tr, "0y", "7daysAgo")
    d30 = _cell(tr, "0y", "30daysAgo")
    d90 = _cell(tr, "0y", "90daysAgo")
    growth_cy = _cell(ee, "0y", "growth")
    growth_ny = _cell(ee, "+1y", "growth")
    n = _cell(ee, "0y", "numberOfAnalysts")
    if cur is None and up30 is None:
        return None
    rev7 = (cur / d7 - 1) * 100 if (cur and d7 and d7 > 0) else None
    rev30 = (cur / d30 - 1) * 100 if (cur and d30 and d30 > 0) else None
    rev90 = (cur / d90 - 1) * 100 if (cur and d90 and d90 > 0) else None
    # 내년(+1y) 추정치 수정률 (1개월/3개월 전 대비)
    cur1 = _cell(tr, "+1y", "current")
    d30_1 = _cell(tr, "+1y", "30daysAgo")
    d90_1 = _cell(tr, "+1y", "90daysAgo")
    rev30_ny = (cur1 / d30_1 - 1) * 100 if (cur1 and d30_1 and d30_1 > 0) else None
    rev90_ny = (cur1 / d90_1 - 1) * 100 if (cur1 and d90_1 and d90_1 > 0) else None
    # 90일 컨센서스 경로(자기 90d 기준 정규화) → [90d,60d,30d,7d,cur]
    trend5 = None
    if tr is not None and d90 and d90 > 0:
        pts = [_cell(tr, "0y", c) for c in ["90daysAgo", "60daysAgo", "30daysAgo", "7daysAgo", "current"]]
        if all(p is not None for p in pts):
            trend5 = [round(p / d90 * 100, 2) for p in pts]
    return {"up30": up30 or 0, "down30": down30 or 0, "rev7": rev7, "rev30": rev30, "rev90": rev90,
            "rev30_ny": rev30_ny, "rev90_ny": rev90_ny,
            "growth_cy": growth_cy, "growth_ny": growth_ny, "n": n, "trend5": trend5}


def _median(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs)
    return xs[m // 2] if m % 2 else (xs[m // 2 - 1] + xs[m // 2]) / 2


def aggregate_basket(tickers):
    """바스켓 집계 → ERR, rev90 중간값, EPS성장 중간값, 정규화 trend 경로."""
    rows = []
    for tk in tickers:
        r = ticker_earnings(tk)
        if r:
            rows.append(r)
    if not rows:
        return None
    up = sum(r["up30"] for r in rows)
    dn = sum(r["down30"] for r in rows)
    err = (up - dn) / (up + dn) if (up + dn) > 0 else None
    rev7 = _median([r["rev7"] for r in rows])
    rev30 = _median([r["rev30"] for r in rows])
    rev90 = _median([r["rev90"] for r in rows])
    rev30_ny = _median([r["rev30_ny"] for r in rows])
    rev90_ny = _median([r["rev90_ny"] for r in rows])
    g_cy = _median([r["growth_cy"] for r in rows])
    g_ny = _median([r["growth_ny"] for r in rows])
    # 단기 모멘텀: 최근 7일 페이스(30일 환산)와 실제 30일 수정 비교
    mom = None
    if rev30 is not None and rev7 is not None:
        accel = rev7 * (30.0 / 7.0)
        if rev7 > 0 and accel > rev30 + 0.5:
            mom = "가속"
        elif accel < rev30 - 0.5 or (rev30 > 0 and rev7 < -0.1):
            mom = "둔화"
        else:
            mom = "유지"
    # trend 경로: 각 종목 5점 경로의 시점별 중간값
    paths = [r["trend5"] for r in rows if r["trend5"]]
    trend = None
    if paths:
        trend = [round(_median([p[i] for p in paths]), 2) for i in range(5)]
    return {"err": round(err, 3) if err is not None else None,
            "rev7": round(rev7, 1) if rev7 is not None else None,
            "rev30": round(rev30, 1) if rev30 is not None else None,
            "rev90": round(rev90, 1) if rev90 is not None else None, "momentum": mom,
            "rev30_ny": round(rev30_ny, 1) if rev30_ny is not None else None,
            "rev90_ny": round(rev90_ny, 1) if rev90_ny is not None else None,
            "growth_cy": round(g_cy * 100, 1) if g_cy is not None else None,
            "growth_ny": round(g_ny * 100, 1) if g_ny is not None else None,
            "trend": trend, "n": len(rows), "up": up, "down": dn}


def err_label(err):
    if err is None:    return "데이터 없음", "neu"
    if err >= 0.3:     return "강한 상향", "pos"
    if err >= 0.1:     return "상향 우위", "pos"
    if err > -0.1:     return "중립", "neu"
    if err > -0.3:     return "하향 우위", "neg"
    return "강한 하향", "neg"


def earnings_score(agg):
    """기업이익 시그널 [-1,+1]: ERR + 수정모멘텀 결합."""
    if not agg:
        return 0.0
    s = 0.0
    if agg.get("err") is not None:
        s += clamp(agg["err"] * 1.4) * 0.6
    if agg.get("rev90") is not None:
        s += clamp(agg["rev90"] / 8.0) * 0.4
    return clamp(s)


def build_annual(cc):
    """국가 연도 EPS → [{y, eps, yoy, est}] + 메타. 없으면 None."""
    a = COUNTRY_EPS_ANNUAL.get(cc)
    if not a:
        return None
    years = sorted(a["eps"].keys())
    out = []
    for i, y in enumerate(years):
        eps = a["eps"][y]
        prev = a["eps"][years[i - 1]] if i > 0 else None
        yoy = round((eps / prev - 1) * 100, 1) if (prev and prev != 0) else None
        out.append({"y": int(y), "eps": eps, "yoy": yoy, "est": int(y) > a["actual_through"]})
    return {"unit": a["unit"], "source": a["source"], "actual_through": a["actual_through"], "years": out}


def build_earnings():
    """국가/섹터 기업이익 섹션 + 5번째 축 카드/점수."""
    print("=== 기업이익(Forward EPS/ERR) 수집 ===")
    countries, scores = {}, []

    # 미국·한국: 섹터 바스켓 합산으로 국가 집계
    sector_out = {"US": [], "KR": []}
    for cc, sectors, issues in [("US", US_SECTORS, US_SECTOR_ISSUES),
                                ("KR", KR_SECTORS, KR_SECTOR_ISSUES)]:
        all_tickers = []
        for sname, tks in sectors.items():
            agg = aggregate_basket(tks)
            all_tickers += tks
            lbl, cls = err_label(agg["err"] if agg else None)
            iss = issues.get(sname, {})
            sector_out[cc].append({
                "name": sname, "err": agg["err"] if agg else None, "err_label": lbl, "err_cls": cls,
                "rev7": agg["rev7"] if agg else None, "rev30": agg["rev30"] if agg else None,
                "rev90": agg["rev90"] if agg else None, "momentum": agg["momentum"] if agg else None,
                "growth_cy": agg["growth_cy"] if agg else None,
                "growth_ny": agg["growth_ny"] if agg else None, "trend": agg["trend"] if agg else None,
                "n": agg["n"] if agg else 0,
                "issue": iss.get("issue", ""), "indicators": iss.get("indicators", ""),
            })
            print(f"  [{cc}] {sname:14s} ERR {agg['err'] if agg else 'NA'}  rev90 {agg['rev90'] if agg else 'NA'}  n={agg['n'] if agg else 0}")
        cagg = aggregate_basket(all_tickers)
        lbl, cls = err_label(cagg["err"] if cagg else None)
        countries[cc] = {"name": "미국" if cc == "US" else "한국",
                         "err": cagg["err"] if cagg else None, "err_label": lbl, "err_cls": cls,
                         "rev7": cagg["rev7"] if cagg else None, "rev30": cagg["rev30"] if cagg else None,
                         "rev90": cagg["rev90"] if cagg else None, "momentum": cagg["momentum"] if cagg else None,
                         "rev30_ny": cagg["rev30_ny"] if cagg else None, "rev90_ny": cagg["rev90_ny"] if cagg else None,
                         "growth_cy": cagg["growth_cy"] if cagg else None,
                         "growth_ny": cagg["growth_ny"] if cagg else None,
                         "trend": cagg["trend"] if cagg else None, "n": cagg["n"] if cagg else 0,
                         "annual": build_annual(cc)}
        scores.append(earnings_score(cagg))

    # 추가 국가(섹터 분해 없음)
    for cc, (kname, tks) in COUNTRY_EXTRA.items():
        agg = aggregate_basket(tks)
        lbl, cls = err_label(agg["err"] if agg else None)
        countries[cc] = {"name": kname, "err": agg["err"] if agg else None,
                         "err_label": lbl, "err_cls": cls,
                         "rev7": agg["rev7"] if agg else None, "rev30": agg["rev30"] if agg else None,
                         "rev90": agg["rev90"] if agg else None, "momentum": agg["momentum"] if agg else None,
                         "rev30_ny": agg["rev30_ny"] if agg else None, "rev90_ny": agg["rev90_ny"] if agg else None,
                         "growth_cy": agg["growth_cy"] if agg else None,
                         "growth_ny": agg["growth_ny"] if agg else None,
                         "trend": agg["trend"] if agg else None, "n": agg["n"] if agg else 0,
                         "annual": build_annual(cc)}
        print(f"  [{cc}] {kname} ERR {agg['err'] if agg else 'NA'}  rev90 {agg['rev90'] if agg else 'NA'}")

    # 5번째 축 점수: 미국 0.55 + 한국 0.45 (가중)
    pillar = scores[0] * 0.55 + scores[1] * 0.45 if len(scores) >= 2 else (scores[0] if scores else 0)

    # 지표 카드 (indicators dict에 병합) — pillar='earnings'
    cards = {}
    for cc in ["US", "KR"]:
        c = countries.get(cc, {})
        nm = c.get("name", cc)
        lbl, cls = err_label(c.get("err"))
        cards[f"err_{cc.lower()}"] = {
            "name": f"{nm} ERR(이익수정비율)", "pillar": "earnings",
            "current": c.get("err"), "unit": "", "z": None, "pct": None,
            "score": round(earnings_score(c), 2), "signal": lbl, "signal_cls": cls,
            "desc": "최근 30일 상향-하향 추정 비율. +면 상향 우세(이익 모멘텀).",
            "as_of": date.today().isoformat(), "history": None,
        }
        tr = c.get("trend")
        rv = c.get("rev30")   # 1개월(30일) 수정률을 헤드라인으로
        mom = c.get("momentum")
        rcls = "pos" if (rv or 0) > 0.5 else ("neg" if (rv or 0) < -0.5 else "neu")
        cards[f"eps_rev_{cc.lower()}"] = {
            "name": f"{nm} Fwd EPS 수정(1개월)", "pillar": "earnings",
            "current": rv, "unit": "%", "z": None, "pct": None,
            "score": round(clamp((rv or 0) / 5.0), 2), "signal": (mom or err_label(c.get("err"))[0]),
            "signal_cls": rcls,
            "desc": f"올해 컨센서스 EPS의 최근 30일 변화율(단기 모멘텀 {mom or '-'}). 7일 {fmt_pct(c.get('rev7'))}·90일 {fmt_pct(c.get('rev90'))}. 그래프=90일 경로.",
            "as_of": date.today().isoformat(),
            "history": ({"dates": ["90일전", "60일전", "30일전", "7일전", "현재"], "values": tr} if tr else None),
        }

    data = {"as_of": date.today().isoformat(), "issues_as_of": ISSUES_AS_OF,
            "countries": countries, "sectors": sector_out}
    return {"data": data, "cards": cards, "pillar_score": pillar}


def load_kr_flows():
    """fetch_kr_flows.py가 만든 kr_flows.json → MANUAL_FLOWS 패치본 반환."""
    f = HERE / "kr_flows.json"
    flows = dict(MANUAL_FLOWS)
    if not f.exists():
        return flows
    try:
        kr = json.loads(f.read_text(encoding="utf-8"))
        m = kr["mtd"]; lt = kr["latest"]
        fo = m["foreign"]
        flows["kr_flows"] = {**MANUAL_FLOWS["kr_flows"], "current": fo, "as_of": kr["as_of"],
            "note": f"{kr['month']} KOSPI 누적(조원): 외국인 {fo:+.1f}·기관 {m['inst']:+.1f}·개인 {m['retail']:+.1f}"
                    f"({m['days']}일). 최근 {lt['date']}: 외국인 {lt['foreign']:+.2f}·기관 {lt['inst']:+.2f}·개인 {lt['retail']:+.2f}. "
                    f"외인 순매도를 개인·기관(연기금·ETF)이 흡수하는 구조. 자동수집(네이버 금융)."}
        if kr.get("deposit"):
            flows["kr_deposit"] = {**MANUAL_FLOWS["kr_deposit"], "current": kr["deposit"], "as_of": kr["as_of"]}
    except Exception as e:
        print(f"  [warn] kr_flows.json 로드 실패: {e}")
    return flows


def load_benchmarks():
    if not BENCH.exists():
        return {}
    txt = BENCH.read_text(encoding="utf-8")
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j < 0:
        return {}
    try:
        data = json.loads(txt[i:j + 1])
    except json.JSONDecodeError:
        return {}
    out = {}
    for idx in data.get("indices", []):
        out[idx.get("name")] = idx
    return out


def build():
    today = date.today()
    bench = load_benchmarks()

    raw = {}        # key -> (dates, transformed_vals)  월간 정렬 차트용
    indicators = {} # key -> 출력 dict
    monthly = {}    # key -> {YYYY-MM: value}  (analog 매트릭스용, transformed)

    # --- S&P / KOSPI 장기 지수 (모멘텀·차트용) ---
    spx_dates, spx_vals = [], []
    try:
        spx_dates, spx_vals = yf_monthly("^GSPC")
        print(f"  [ok] S&P500 월간 {len(spx_vals)}개")
    except Exception as e:
        print(f"  [err] S&P500: {e}")
    kospi_dates, kospi_vals = [], []
    try:
        kospi_dates, kospi_vals = yf_monthly("^KS11")
        print(f"  [ok] KOSPI 월간 {len(kospi_vals)}개")
    except Exception as e:
        print(f"  [err] KOSPI: {e}")

    # spx 200일(월) 모멘텀 파생
    spx_mom_d, spx_mom_v = [], []
    if len(spx_vals) >= 13:
        for i in range(12, len(spx_vals)):
            spx_mom_d.append(spx_dates[i])
            spx_mom_v.append((spx_vals[i] / spx_vals[i - 12] - 1) * 100)
    above_200d = None
    if len(spx_vals) >= 10:
        ma10 = sum(spx_vals[-10:]) / 10  # 월간 10개월 ≈ 200일선
        above_200d = spx_vals[-1] > ma10

    # ERP 계산용 fwd earnings yield (benchmarks fwd PE) + 10Y
    spx_fwd_pe = (bench.get("S&P 500", {}).get("valuation") or {}).get("pe")
    kospi_fwd_pe = (bench.get("KOSPI", {}).get("valuation") or {}).get("pe")

    # 코어 CPI 최신 (실질금리 계산용) — 먼저 당겨둠
    core_now = None
    try:
        d, v = fred_csv("CPILFESL")
        _, yv = yoy(d, v)
        core_now = yv[-1] if yv else None
    except Exception:
        pass

    us10y_now = None

    for key, name, pillar, src, transform, dec, unit, desc in INDICATORS:
        dates, vals = [], []
        try:
            if transform == "yoy":
                d, v = fred_csv(src); dates, vals = yoy(d, v)
            elif transform == "mom":
                d, v = fred_csv(src); dates, vals = mom_change(d, v)
            elif transform == "level":
                d, v = fred_csv(src); dates, vals = downsample_monthly(d, v)
            elif transform == "daily":
                d, v = fred_csv(src); dates, vals = downsample_monthly(d, v)
            elif transform == "oilyoy":
                d, v = fred_csv(src)
                me = to_month_end(d, v); keys = sorted(me)
                for k in keys:
                    y, m = int(k[:4]), int(k[5:7])
                    pk = f"{y-1:04d}-{m:02d}"
                    if pk in me and me[pk] > 0:
                        dates.append(k + "-01"); vals.append((me[k] / me[pk] - 1) * 100)
            elif transform == "spxmom":
                dates, vals = spx_mom_d, spx_mom_v
            elif transform == "bench":
                cur = spx_fwd_pe if key == "spx_fwd_pe" else kospi_fwd_pe
                if cur:
                    dates, vals = [today.isoformat()], [cur]
            elif transform == "derived":
                pass  # erp 아래서 처리
        except Exception as e:
            print(f"  [err] {key}: {e}")

        if key == "us10y" and vals:
            us10y_now = vals[-1]

        if not vals and key != "erp":
            print(f"  [miss] {key}")
            continue

        if vals:
            raw[key] = (dates, vals)
            monthly[key] = to_month_end(dates, vals)

    # ERP = S&P fwd earnings yield − 10Y
    if spx_fwd_pe and us10y_now:
        ey = 100.0 / spx_fwd_pe
        erp_now = ey - us10y_now
        raw["erp"] = ([today.isoformat()], [round(erp_now, 2)])

    real_rate = None
    if "fed_funds" in raw and core_now is not None:
        real_rate = raw["fed_funds"][1][-1] - core_now

    # --- 지표 dict 작성 + 점수화 ---
    pillar_scores = {p: [] for p in PILLARS}
    for key, name, pillar, src, transform, dec, unit, desc in INDICATORS:
        if key not in raw:
            continue
        dates, vals = raw[key]
        cur = vals[-1]
        z, pct = zscore(vals) if len(vals) >= 8 else (None, None)
        ctx = {"z": z, "real_rate": real_rate, "above_200d": above_200d}
        score = score_indicator(key, cur, vals, ctx)
        lbl, cls = signal_label(score)
        pillar_scores[pillar].append(score)
        # 차트 히스토리 (bench/derived/단일점은 sparkline 생략)
        hist = None
        if len(vals) >= 8:
            cd, cv = downsample_monthly(dates, vals) if transform not in ("yoy", "mom", "oilyoy", "spxmom") else (dates, [round(x, 4) for x in vals])
            hist = {"dates": cd, "values": cv}
        indicators[key] = {
            "name": name, "pillar": pillar, "current": round(cur, dec if dec > 0 else 0) if dec else round(cur, 2),
            "unit": unit, "z": z, "pct": pct, "score": round(score, 2),
            "signal": lbl, "signal_cls": cls, "desc": desc,
            "as_of": dates[-1][:10], "history": hist,
        }

    # --- 수동 지표 (센티먼트 MANUAL + 수급 MANUAL_FLOWS, 한국 수급은 자동 패치) ---
    flows_manual = load_kr_flows()
    for key, m in {**MANUAL, **flows_manual}.items():
        score = score_indicator(key, m["current"], [m.get("prev", m["current"]), m["current"]], {})
        lbl, cls = signal_label(score)
        pillar_scores[m["pillar"]].append(score)
        indicators[key] = {
            "name": m["name"], "pillar": m["pillar"], "current": m["current"],
            "unit": m.get("unit", ""), "z": None, "pct": None, "score": round(score, 2),
            "signal": lbl, "signal_cls": cls, "desc": m.get("note", ""),
            "as_of": m["as_of"], "history": None, "manual": True,
        }

    # --- 기업이익 축 (국가/섹터 Forward EPS·ERR) ---
    earn = build_earnings()
    indicators.update(earn["cards"])
    pillar_scores["earnings"] = [earn["pillar_score"]]

    # --- 축별/종합 레짐 점수 (-100 ~ +100) ---
    pillars_out = {}
    overall = 0.0
    for p, meta in PILLARS.items():
        scores = pillar_scores[p]
        avg = sum(scores) / len(scores) if scores else 0.0
        pillars_out[p] = {"name": meta["name"], "score": round(avg * 100), "n": len(scores)}
        overall += avg * meta["weight"]
    overall_score = round(overall * 100)
    regime_label, regime_cls = regime_band(overall_score)

    # --- 장기 지수 차트 ---
    indices = {}
    if spx_vals:
        cd, cv = downsample_monthly(spx_dates, spx_vals)
        indices["spx"] = {"name": "S&P 500", "dates": cd, "values": cv, "current": round(spx_vals[-1], 2)}
    if kospi_vals:
        cd, cv = downsample_monthly(kospi_dates, kospi_vals)
        indices["kospi"] = {"name": "KOSPI", "dates": cd, "values": cv, "current": round(kospi_vals[-1], 2)}

    # --- 과거 유사 국면 ---
    analogs = compute_analogs(monthly, spx_dates, spx_vals, kospi_dates, kospi_vals)

    # --- 자동 코멘터리 + 전망 ---
    commentary = build_commentary(indicators, pillars_out, overall_score)
    outlook = build_outlook(indicators, pillars_out, overall_score, analogs)

    out = {
        "as_of": today.isoformat(),
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "regime": {"score": overall_score, "label": regime_label, "cls": regime_cls,
                   "pillars": pillars_out},
        "indicators": indicators,
        "indices": indices,
        "analogs": analogs,
        "earnings": earn["data"],
        "commentary": commentary,
        "outlook": outlook,
        "real_rate": round(real_rate, 2) if real_rate is not None else None,
    }

    OUT.write_text(
        "// 매크로·시장 레짐 모니터 데이터 (공개 데이터, 평문). fetch_macro.py로 갱신.\n"
        "// 소스: FRED(키 불필요 CSV) + yfinance + benchmarks.js\n"
        f"window.MACRO = {json.dumps(out, ensure_ascii=False, indent=2)};\n",
        encoding="utf-8",
    )
    print(f"\n저장: {OUT.name}  레짐 {overall_score:+d} ({regime_label}), 지표 {len(indicators)}개, "
          f"유사국면 {len(analogs.get('neighbors', []))}개")


def regime_band(s):
    if s >= 35:  return "리스크온 (적극)", "strong-pos"
    if s >= 12:  return "비중확대 우위", "pos"
    if s >= -12: return "중립 (선별적)", "neu"
    if s >= -35: return "방어 우위", "neg"
    return "리스크오프 (축소)", "strong-neg"


def compute_analogs(monthly, spx_d, spx_v, kospi_d, kospi_v, k=6):
    """ANALOG_FEATURES 월간 매트릭스 표준화 → 현재와 최근접 과거 월 K개.
    각 analog 이후 S&P/KOSPI 1·3·6·12개월 수익률 산출."""
    feats = [f for f in ANALOG_FEATURES if f in monthly and len(monthly[f]) >= 60]
    if len(feats) < 5:
        return {"method": "insufficient", "neighbors": [], "features": feats}

    # 공통 월 인덱스
    common = None
    for f in feats:
        ks = set(monthly[f].keys())
        common = ks if common is None else (common & ks)
    months = sorted(common)
    if len(months) < 60:
        return {"method": "insufficient", "neighbors": [], "features": feats}

    # 표준화 (각 피처 전체기간 평균/표준편차)
    stats = {}
    for f in feats:
        col = [monthly[f][m] for m in months]
        mean = sum(col) / len(col)
        sd = math.sqrt(sum((x - mean) ** 2 for x in col) / len(col)) or 1.0
        stats[f] = (mean, sd)

    def vec(m):
        return [(monthly[f][m] - stats[f][0]) / stats[f][1] for f in feats]

    cur_m = months[-1]
    cur_vec = vec(cur_m)

    # S&P / KOSPI 월말 값 lookup
    spx_me = to_month_end(spx_d, spx_v)
    kospi_me = to_month_end(kospi_d, kospi_v)
    spx_keys = sorted(spx_me)

    def fwd_ret(me, ym, months_ahead):
        y, mo = int(ym[:4]), int(ym[5:7])
        tot = mo + months_ahead
        ty = y + (tot - 1) // 12
        tm = (tot - 1) % 12 + 1
        tkey = f"{ty:04d}-{tm:02d}"
        if ym in me and tkey in me and me[ym] > 0:
            return round((me[tkey] / me[ym] - 1) * 100, 1)
        return None

    # 후보: 마지막 12개월 제외(forward 수익률 확보) + 현재 ±2개월 제외
    cand = months[:-13]
    dist = []
    for m in cand:
        v = vec(m)
        d = math.sqrt(sum((a - b) ** 2 for a, b in zip(cur_vec, v)))
        dist.append((d, m))
    dist.sort()

    neighbors = []
    used_years = set()
    for d, m in dist:
        yr = m[:4]
        # 같은 해 중복 과다 방지 (다양성)
        if list(n["date"][:4] for n in neighbors).count(yr) >= 2:
            continue
        neighbors.append({
            "date": m + "-01",
            "distance": round(d, 2),
            "spx_fwd": {h: fwd_ret(spx_me, m, n) for h, n in [("m1", 1), ("m3", 3), ("m6", 6), ("m12", 12)]},
            "kospi_fwd": {h: fwd_ret(kospi_me, m, n) for h, n in [("m1", 1), ("m3", 3), ("m6", 6), ("m12", 12)]},
        })
        if len(neighbors) >= k:
            break

    def med(xs):
        xs = sorted(x for x in xs if x is not None)
        if not xs:
            return None
        n = len(xs)
        return round((xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2), 1)

    summary = {}
    for mkt, fld in [("spx", "spx_fwd"), ("kospi", "kospi_fwd")]:
        summary[mkt] = {h: med([nb[fld][h] for nb in neighbors]) for h in ["m1", "m3", "m6", "m12"]}

    return {"method": "knn-euclidean(z)", "features": feats, "n_months": len(months),
            "current_month": cur_m, "neighbors": neighbors, "summary": summary}


def build_commentary(ind, pillars, overall):
    """축별 자동 코멘터리 (지표 시그널 기반 한국어 템플릿)."""
    def g(k, field="current"):
        return ind.get(k, {}).get(field)

    def fmt(k):
        i = ind.get(k)
        if not i:
            return None
        u = i.get("unit", "")
        return f"{i['name']} {i['current']}{u}({i['signal']})"

    macro_bits = [fmt(k) for k in ["ism_pmi", "cpi_yoy", "core_cpi_yoy", "unemployment", "payrolls", "yield_curve", "oil_yoy"]]
    macro = "·".join(b for b in macro_bits if b)
    val_bits = [fmt(k) for k in ["spx_fwd_pe", "kospi_fwd_pe", "erp", "us10y"]]
    valuation = "·".join(b for b in val_bits if b)
    flow_bits = [fmt(k) for k in ["m2_yoy", "baa_spread", "usdkrw", "cta_pos", "retail_alloc", "kr_deposit", "kr_flows"]]
    flows = "·".join(b for b in flow_bits if b)
    sent_bits = [fmt(k) for k in ["vix", "spx_mom", "cnn_fng", "aaii_spread", "put_call"]]
    sentiment = "·".join(b for b in sent_bits if b)
    earn_bits = [fmt(k) for k in ["err_us", "eps_rev_us", "err_kr", "eps_rev_kr"]]
    earnings = "·".join(b for b in earn_bits if b)

    def verdict(p):
        s = pillars[p]["score"]
        if s >= 25:  return "전반적으로 우호적"
        if s >= 8:   return "완만한 호재 우위"
        if s >= -8:  return "혼조/중립"
        if s >= -25: return "부담 우위"
        return "뚜렷한 역풍"

    return {
        "macro": f"[{verdict('macro')}] {macro}",
        "valuation": f"[{verdict('valuation')}] {valuation}",
        "flows": f"[{verdict('flows')}] {flows}",
        "sentiment": f"[{verdict('sentiment')}] {sentiment}",
        "earnings": f"[{verdict('earnings')}] {earnings}",
        "overall": f"종합 레짐 점수 {overall:+d}. "
                   f"매크로 {pillars['macro']['score']:+d}, 밸류 {pillars['valuation']['score']:+d}, "
                   f"수급 {pillars['flows']['score']:+d}, 센티 {pillars['sentiment']['score']:+d}, "
                   f"기업이익 {pillars['earnings']['score']:+d}.",
    }


def build_outlook(ind, pillars, overall, analogs):
    """1개월/3개월/1년 방향성 자동 산출. 데이터 기반 + 정성 톤."""
    sm = analogs.get("summary", {}).get("spx", {})

    def bias(score):
        if score >= 20:  return "상승", "pos"
        if score >= 6:   return "완만한 상승", "pos"
        if score >= -6:  return "박스권", "neu"
        if score >= -20: return "하방 주의", "neg"
        return "조정 위험", "neg"

    ep = pillars.get("earnings", {}).get("score", 0)
    # 단기=센티+모멘텀, 중기=매크로+유동성+기업이익+유사국면, 장기=밸류+매크로+기업이익+유사국면
    short_s = round((pillars["sentiment"]["score"] + (ind.get("spx_mom", {}).get("score", 0) * 100)) / 2)
    mid_s = round((pillars["macro"]["score"] * 0.4 + pillars["flows"]["score"] * 0.3 + ep * 0.3)
                  + (sm.get("m3") or 0) * 2)
    long_s = round((pillars["valuation"]["score"] * 0.35 + pillars["macro"]["score"] * 0.35 + ep * 0.30)
                   + (sm.get("m12") or 0))

    sb, sc = bias(short_s); mb, mc = bias(mid_s); lb, lc = bias(long_s)
    m3 = sm.get("m3"); m12 = sm.get("m12")
    return {
        "short": {"bias": sb, "cls": sc,
                  "text": f"센티먼트·모멘텀 기반. VIX·추세가 핵심 변수. 단기 비대칭 리스크 점검."},
        "mid": {"bias": mb, "cls": mc,
                "text": f"매크로·유동성·기업이익 수정 + 과거 유사국면 이후 3개월 중간값 {fmt_pct(m3)}."},
        "long": {"bias": lb, "cls": lc,
                 "text": f"밸류에이션·매크로 추세·이익 모멘텀 + 유사국면 이후 12개월 중간값 {fmt_pct(m12)}."},
    }


def fmt_pct(x):
    return f"{x:+.1f}%" if isinstance(x, (int, float)) else "N/A"


if __name__ == "__main__":
    print(f"=== 매크로 레짐 모니터 ({date.today()}) ===")
    build()
