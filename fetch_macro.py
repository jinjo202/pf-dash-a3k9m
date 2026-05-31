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
    "macro":     {"name": "매크로", "weight": 0.30},
    "valuation": {"name": "밸류에이션", "weight": 0.25},
    "flows":     {"name": "수급·유동성", "weight": 0.25},
    "sentiment": {"name": "센티먼트", "weight": 0.20},
}

# 과거 유사국면 매칭에 쓸 deep-history 지표 (월간 정렬)
ANALOG_FEATURES = ["cpi_yoy", "core_cpi_yoy", "unemployment", "fed_funds",
                   "yield_curve", "m2_yoy", "baa_spread", "vix", "oil_yoy", "spx_mom"]


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

    # --- 수동 지표 ---
    for key, m in MANUAL.items():
        score = score_indicator(key, m["current"], [m.get("prev", m["current"]), m["current"]], {})
        if key == "cnn_fng":
            score = clamp((m["current"] - 50) / 30.0)
        lbl, cls = signal_label(score)
        pillar_scores[m["pillar"]].append(score)
        indicators[key] = {
            "name": m["name"], "pillar": m["pillar"], "current": m["current"],
            "unit": m.get("unit", ""), "z": None, "pct": None, "score": round(score, 2),
            "signal": lbl, "signal_cls": cls, "desc": m.get("note", ""),
            "as_of": m["as_of"], "history": None, "manual": True,
        }

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
    flow_bits = [fmt(k) for k in ["m2_yoy", "baa_spread", "usdkrw"]]
    flows = "·".join(b for b in flow_bits if b)
    sent_bits = [fmt(k) for k in ["vix", "spx_mom", "cnn_fng"]]
    sentiment = "·".join(b for b in sent_bits if b)

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
        "overall": f"종합 레짐 점수 {overall:+d}. "
                   f"매크로 {pillars['macro']['score']:+d}, 밸류 {pillars['valuation']['score']:+d}, "
                   f"수급 {pillars['flows']['score']:+d}, 센티 {pillars['sentiment']['score']:+d}.",
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

    # 단기=센티+모멘텀, 중기=매크로+유사국면, 장기=밸류+매크로추세
    short_s = round((pillars["sentiment"]["score"] + (ind.get("spx_mom", {}).get("score", 0) * 100)) / 2)
    mid_s = round((pillars["macro"]["score"] * 0.6 + pillars["flows"]["score"] * 0.4)
                  + (sm.get("m3") or 0) * 2)
    long_s = round((pillars["valuation"]["score"] * 0.5 + pillars["macro"]["score"] * 0.5)
                   + (sm.get("m12") or 0))

    sb, sc = bias(short_s); mb, mc = bias(mid_s); lb, lc = bias(long_s)
    m3 = sm.get("m3"); m12 = sm.get("m12")
    return {
        "short": {"bias": sb, "cls": sc,
                  "text": f"센티먼트·모멘텀 기반. VIX·추세가 핵심 변수. 단기 비대칭 리스크 점검."},
        "mid": {"bias": mb, "cls": mc,
                "text": f"매크로·유동성 + 과거 유사국면 이후 3개월 중간값 {fmt_pct(m3)}."},
        "long": {"bias": lb, "cls": lc,
                 "text": f"밸류에이션·매크로 추세 + 유사국면 이후 12개월 중간값 {fmt_pct(m12)}."},
    }


def fmt_pct(x):
    return f"{x:+.1f}%" if isinstance(x, (int, float)) else "N/A"


if __name__ == "__main__":
    print(f"=== 매크로 레짐 모니터 ({date.today()}) ===")
    build()
