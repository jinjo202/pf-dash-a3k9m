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
FRED_API = "https://api.stlouisfed.org/fred/series/observations?series_id={id}&observation_start={start}&api_key={key}&file_type=json"
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
    "citi_surprise": {
        "name": "Citi 경제 서프라이즈(미)",
        "pillar": "macro",
        "current": -8.0,
        "prev": 5.0,
        "as_of": "2026-06-12",
        "unit": "",
        "kind": "forward",
        "note": "실제 발표가 컨센서스를 얼마나 상회/하회하는지(+면 호조). 데이터 모멘텀 선행 지표. "
                "무료 API 없어 수동 — macromicro.me(45866)/Bloomberg에서 갱신.",
    },
    "cnn_fng": {
        "name": "CNN 공포·탐욕 지수",
        "pillar": "sentiment",
        "current": 32,
        "prev": 60,
        "as_of": "2026-07-03",
        "unit": "",
        "note": "0=극단적 공포, 100=극단적 탐욕. production.dataviz.cnn.io/index/fearandgreed/graphdata "
                "(UA 헤더 필요)에서 자동 조회 — 실패 시 이 시드값 유지(fail-safe).",
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
    "vkospi": {
        "name": "VKOSPI (한국 변동성)",
        "pillar": "sentiment",
        "current": 21.0,
        "prev": 22.5,
        "as_of": "2026-06-03",
        "unit": "",
        "note": "코스피200 변동성지수(한국판 VIX). 낮을수록 안정. VIX 대비 한국 시장 공포 정도. "
                "무료 실시간 API 없어 수동 — KRX(data.krx.co.kr 변동성지수)/Investing.com에서 갱신.",
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
def http_get(url, timeout=22, retries=3):
    """GET + 재시도(GitHub Actions에서 FRED/multpl throttling 대응)."""
    import time
    last = None
    for a in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 macro-monitor"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(1.0 * (a + 1))
    raise last


def fetch_cnn_fng():
    """CNN 공포·탐욕 지수 자동 조회.

    production.dataviz.cnn.io graphdata 엔드포인트(브라우저 UA 필요)에서 최신
    score와 직전 종가를 가져온다. 실패 시 None → 호출부에서 기존 시드값 유지(fail-safe).
    반환: {"current": int, "prev": int, "as_of": "YYYY-MM-DD"} 또는 None.
    """
    import time, json as _json
    url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    last = None
    for a in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": ua,
                "Accept": "application/json, text/plain, */*",
                "Origin": "https://www.cnn.com",
                "Referer": "https://www.cnn.com/markets/fear-and-greed",
            })
            with urllib.request.urlopen(req, timeout=22) as r:
                data = _json.loads(r.read().decode("utf-8", errors="replace"))
            fng = data.get("fear_and_greed") or {}
            score = fng.get("score")
            if score is None:
                raise ValueError("응답에 score 없음")
            cur = int(round(float(score)))
            pc = fng.get("previous_close")
            prev = int(round(float(pc))) if pc is not None else cur
            as_of = date.today().isoformat()
            ts = fng.get("timestamp")
            if ts is not None:
                try:
                    if isinstance(ts, (int, float)) or str(ts).isdigit():
                        as_of = datetime.fromtimestamp(int(ts) / 1000, timezone.utc).date().isoformat()
                    else:
                        as_of = str(ts)[:10]
                except Exception:
                    pass
            return {"current": cur, "prev": prev, "as_of": as_of}
        except Exception as e:
            last = e
            time.sleep(1.0 * (a + 1))
    print(f"  [err] CNN F&G 자동조회 실패(시드값 유지): {last}")
    return None


def fetch_vkospi():
    """VKOSPI(코스피200 변동성지수) 자동 조회.

    investing.com 내부 API(instrumentId=956761, KSVKOSPI)에서 일별 종가를 가져온다.
    이 엔드포인트는 Cloudflare가 Python urllib/requests의 TLS 지문을 차단하지만
    curl은 통과시킨다(투자자·개발자 커뮤니티에 알려진 동작) — 그래서 curl subprocess로 호출.
    KRX 데이터포털은 이 정보를 로그인 계정 없이는 조회 불가(확인됨)라 대안으로 사용.
    실패 시 None → 호출부에서 기존 시드값 유지(fail-safe).
    반환: {"current": float, "prev": float, "as_of": "YYYY-MM-DD",
           "history": {"dates": [...], "values": [...]}} 또는 None.
    """
    import subprocess, json as _json
    url = ("https://api.investing.com/api/financialdata/956761/historical/chart/"
           "?interval=P1D&pointscount=70")
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "20", "-A", ua,
             "-H", "Accept: application/json",
             "-H", "Referer: https://kr.investing.com/indices/kospi-volatility",
             url],
            capture_output=True, timeout=25, check=True,
        )
        data = _json.loads(r.stdout.decode("utf-8", errors="replace"))
        rows = data.get("data") or []
        if len(rows) < 2:
            raise ValueError("데이터 부족")
        dates, vals = [], []
        for ts, o, h, l, c, *_ in rows:
            d = datetime.fromtimestamp(ts / 1000, timezone.utc).date().isoformat()
            dates.append(d)
            vals.append(round(float(c), 2))
        return {"current": vals[-1], "prev": vals[-2], "as_of": dates[-1],
                "history": {"dates": dates, "values": vals}}
    except Exception as e:
        print(f"  [err] VKOSPI 자동조회 실패(시드값 유지): {e}")
        return None


def fetch_ism_pmi():
    """ISM 제조업 PMI 자동 조회.

    investing.com 경제캘린더 페이지(event_id=173)에 내장된 __NEXT_DATA__ JSON에서
    최신 발표치(actual/previous/발표일)를 추출. FRED는 2016년 라이선스 문제로
    ISM PMI 배포를 중단해 대안으로 사용. investing.com도 Cloudflare가 Python
    TLS 지문을 막아 curl subprocess 필요(fetch_vkospi와 동일 이유).
    실패 시 None → 호출부에서 기존 시드값 유지(fail-safe).
    반환: {"current": float, "prev": float, "as_of": "YYYY-MM-DD"} 또는 None.
    """
    import subprocess, re as _re, json as _json
    url = "https://kr.investing.com/economic-calendar/ism-manufacturing-pmi-173"
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    try:
        r = subprocess.run(
            ["curl", "-s", "--compressed", "--max-time", "20", "-A", ua, url],
            capture_output=True, timeout=25, check=True,
        )
        html = r.stdout.decode("utf-8", errors="replace")
        m = _re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, _re.S)
        if not m:
            raise ValueError("__NEXT_DATA__ 없음")
        data = _json.loads(m.group(1))
        s = _json.dumps(data)
        idx = s.find('"closestOccurrences"')
        if idx < 0:
            raise ValueError("closestOccurrences 없음")
        window = s[idx:idx + 600]
        actual = float(_re.search(r'"actual":\s*([\d.]+)', window).group(1))
        prev = float(_re.search(r'"previous":\s*([\d.]+)', window).group(1))
        as_of = _re.search(r'"occurrence_time":\s*"([^"]{10})', window).group(1)
        return {"current": actual, "prev": prev, "as_of": as_of}
    except Exception as e:
        print(f"  [err] ISM PMI 자동조회 실패(시드값 유지): {e}")
        return None


def fetch_multpl(slug):
    """multpl.com 월별 테이블 → (dates[ISO], values[float]). 실패 시 ([],[])."""
    import re, html as _html
    from datetime import datetime as _dt
    try:
        txt = http_get(f"https://www.multpl.com/{slug}/table/by-month")
    except Exception as e:
        print(f"  [err] multpl {slug}: {e}")
        return [], []
    dates, vals = [], []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", txt, re.DOTALL):
        clean = _html.unescape(re.sub(r"<[^>]+>", "|", row))
        parts = [p.strip() for p in clean.split("|") if p.strip() and p.strip() != "†"]
        if len(parts) >= 2:
            try:
                d = _dt.strptime(parts[0], "%b %d, %Y").date().isoformat()
                v = float(parts[1].replace(",", ""))
                dates.append(d); vals.append(v)
            except Exception:
                continue
    pairs = sorted(zip(dates, vals))
    return [p[0] for p in pairs], [p[1] for p in pairs]


def fred_csv(series_id, start=START):
    """FRED 데이터 fetch. FRED_API_KEY 환경변수 있으면 API JSON, 없으면 CSV fallback."""
    import os, time, json as _json
    time.sleep(0.15)
    api_key = os.environ.get("FRED_API_KEY", "")
    if api_key:
        url = FRED_API.format(id=series_id, start=start, key=api_key)
        try:
            txt = http_get(url)
            data = _json.loads(txt)
            dates, vals = [], []
            for obs in data.get("observations", []):
                d, v = obs.get("date", ""), obs.get("value", ".")
                if not d or v in (".", "", "NA"):
                    continue
                try:
                    vals.append(float(v))
                    dates.append(d)
                except ValueError:
                    continue
            if dates:
                return dates, vals
        except Exception as e:
            print(f"  [fred-api] {series_id} 실패({e}), CSV fallback")
    # CSV fallback (FRED_API_KEY 없거나 API 실패 시)
    url = FRED_CSV.format(id=series_id, start=start)
    txt = http_get(url)
    dates, vals = [], []
    for line in txt.splitlines()[1:]:
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
    if key == "cli_us":
        # 100 기준 + 모멘텀. 위·상승=확장
        lvl = clamp((cur - 100) / 1.5)
        trd = clamp(chg3 / 0.4)
        return clamp(lvl * 0.6 + trd * 0.4)
    if key == "gdpnow":
        # GDP nowcast. 2% 추세 기준, 높을수록 호재
        return clamp((cur - 2.0) / 2.0)
    if key == "citi_surprise":
        # 경제지표 서프라이즈. +면 데이터 호조(호재)
        return clamp(cur / 40.0)
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
    if key == "t10y3m":
        # NY Fed probit 기준 스프레드. 역전 심화 = 침체 경고, 가파른 정상화 = 회복
        if cur < 0:
            return clamp(cur / 0.7)
        return clamp(cur / 1.5)
    if key == "cfnai":
        # CFNAI-MA3: 0=추세성장, -0.7=침체 임계(시카고연준 공식)
        return clamp((cur + 0.35) / 0.45)
    if key == "sahm":
        # Sahm(2019): 0.5%p 이상 = 침체 시작. 0 근처 = 노동시장 안정
        return clamp((0.25 - cur) / 0.25)
    if key == "copper_gold":
        # 레벨보다 추세 — 6개월 변화율(성장 기대 방향)
        if len(hist_vals) >= 7 and hist_vals[-7]:
            chg6 = (hist_vals[-1] / hist_vals[-7] - 1) * 100
            return clamp(chg6 / 15.0)
        return 0.0
    if key == "hy_oas":
        # HY OAS: ~4.2% 중립(장기 중앙값), 3% 미만 타이트(위험선호 강), 6%+ 스트레스
        return clamp((4.2 - cur) / 1.8)
    if key == "nfci":
        # 0=역사평균. 음수=완화적(호재), 양수=긴축적(악재)
        return clamp(-cur / 0.5)
    if key == "move":
        # 채권 변동성. ~95 중립, 낮을수록 금리 안정(호재), 130+ 스트레스
        return clamp((95 - cur) / 40.0)
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
    if key == "cape":
        # CAPE 높을수록 장기 고평가. 역사평균 ~17, 24 중립선
        return clamp((24.0 - cur) / 12.0)
    if key == "peg":
        # PEG = Fwd PER / EPS성장. 1 미만 저평가, 2+ 부담
        return clamp((1.6 - cur) / 1.0)
    if key == "spx_eps_yoy":
        # S&P 트레일링 EPS YoY. 성장 가속=호재 (과거 이익 모멘텀 프록시)
        return clamp(cur / 12.0)
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
    if key == "vkospi":
        # VKOSPI 낮으면 안정(호재), 30+ 악재 (한국 변동성, VIX보다 베이스 높음)
        if cur >= 35:
            return clamp(-1.0 + (cur - 35) / 30.0 * 0.4)
        return clamp((22 - cur) / 12.0)
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
    ("cli_us",       "OECD 경기선행지수(미)", "macro", "USALOLITOAASTSAM", "level", 1, "", "100=추세선. 위·상승=확장, 아래·하락=수축 (진폭조정)"),
    ("gdpnow",       "GDPNow (애틀랜타 연준)","macro", "GDPNOW", "level", 1, "%", "실시간 GDP 성장 추정(nowcast). 발표 전 선행 추정치"),
    ("oil_yoy",      "WTI 유가 (YoY)",       "macro", "DCOILWTICO","oilyoy",1, "%",  "급등 시 인플레·비용 압력"),
    ("t10y3m",       "장단기 금리차(10Y-3M)","macro", "T10Y3M",    "daily", 2, "%p", "NY Fed 침체모델(Estrella-Mishkin)의 기준 스프레드. 역전(<0)은 12개월 내 침체 경고 — 10Y-2Y보다 예측력 우수"),
    ("cfnai",        "시카고연준 활동지수(MA3)","macro","CFNAI",   "ma3",   2, "",   "85개 실물지표 합성(CFNAI) 3개월 평균. 0=추세성장, -0.7 이하=침체 임계(시카고연준 공식 기준)"),
    ("sahm",         "Sahm Rule 침체신호",   "macro", "SAHMREALTIME","level",2, "%p","실업률 3개월평균 − 직전 12개월 저점. 0.5%p 이상 = 침체 시작(1970년 이후 무오류 실시간 신호)"),
    ("copper_gold",  "구리/금 비율",         "macro", "HG=F/GC=F", "cugd",  2, "",  "실물수요(구리) vs 안전선호(금). 상승 추세 = 글로벌 성장 기대 개선 — 10Y 금리 선행 프록시"),
    # 밸류에이션
    ("spx_fwd_pe",   "S&P500 12M Fwd PER",   "valuation", "bench", "bench", 1, "배", "이익 대비 가격. 높을수록 기대수익 낮음"),
    ("cape",         "S&P500 CAPE(실러 PE)",  "valuation", "shiller-pe", "multpl", 1, "배", "경기조정 P/E(최근 10년 평균이익). 역사평균 ~17, 높을수록 장기 고평가"),
    ("kospi_fwd_pe", "KOSPI 12M Fwd PER",    "valuation", "bench", "bench", 1, "배", "한국 밸류에이션"),
    ("erp",          "주식위험프리미엄(ERP)","valuation", "derived","derived",2,"%p","S&P 어닝일드 − 미 10Y. 높을수록 주식 매력"),
    ("us10y",        "미국 10Y 금리",        "valuation", "DGS10", "daily", 2, "%",  "할인율. 급등 시 밸류 부담"),
    # 수급·유동성
    ("m2_yoy",       "M2 통화량 (YoY)",      "flows", "M2SL",          "yoy",   1, "%", "유동성. 증가할수록 위험자산 우호"),
    ("baa_spread",   "신용 스프레드(Baa-10Y)","flows", "BAA10Y",       "daily", 2, "%p","위험선호 게이지(투자등급). 낮을수록 강세, 4%+ 스트레스"),
    ("hy_oas",       "하이일드 스프레드(OAS)","flows", "BAMLH0A0HYM2", "daily", 2, "%p","정크본드 위험프리미엄(ICE BofA). 위험선호의 가장 민감한 게이지 — 3% 미만 타이트, 6%+ 스트레스"),
    ("nfci",         "금융환경지수(NFCI)",   "flows", "NFCI",          "daily", 2, "",  "시카고연준 105개 지표 합성 금융환경. 0=역사평균, 음수=완화적(위험자산 우호)"),
    ("usdkrw",       "USD/KRW",              "flows", "DEXKOUS",       "daily", 1, "원","원화 약세는 위험회피·외인 유출"),
    # 센티먼트
    ("vix",          "VIX 변동성",           "sentiment", "VIXCLS", "daily", 1, "",  "공포 게이지. 낮을수록 안정"),
    ("move",         "MOVE (채권 변동성)",   "sentiment", "^MOVE",  "yfmo",  1, "",  "미 국채 옵션 내재변동성(ICE BofA). 금리 불확실성 게이지 — 80 미만 안정, 120+ 스트레스"),
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
                   "yield_curve", "m2_yoy", "baa_spread", "vix", "oil_yoy", "spx_mom", "cli_us",
                   "t10y3m", "nfci", "cfnai", "sahm"]   # hy_oas는 FRED 3년 제한으로 제외
ANALOG_LABELS = {
    "cpi_yoy": "인플레", "core_cpi_yoy": "근원물가", "unemployment": "실업률",
    "fed_funds": "정책금리", "yield_curve": "장단기차", "m2_yoy": "유동성",
    "baa_spread": "신용스프레드", "vix": "변동성", "oil_yoy": "유가",
    "spx_mom": "주가모멘텀", "cli_us": "경기선행지수",
    "t10y3m": "10Y-3M", "hy_oas": "HY스프레드", "nfci": "금융환경",
    "cfnai": "실물활동", "sahm": "Sahm룰",
}


def analog_context(date_str):
    """유사 시점의 시대적 매크로 맥락(당시 무슨 일이었나)."""
    ym = date_str[:7]
    y = int(date_str[:4])
    table = [
        ("2008-08", "2009-06", "글로벌 금융위기 — 신용경색·증시 폭락·제로금리·QE 시작"),
        ("2007-06", "2008-07", "신용 정점·서브프라임 균열 직전 — 위험선호 극대, 곧 침체"),
        ("2011-05", "2012-06", "유럽 재정위기 — 그리스·남유럽 우려, 안전자산 선호"),
        ("2013-05", "2013-12", "테이퍼 텐트럼 — 연준 자산매입 축소 시사로 금리 급등"),
        ("2014-07", "2016-02", "강달러·유가 급락·중국 둔화 — 디스인플레 우려"),
        ("2016-03", "2016-12", "차이나 쇼크 후 회복 — 원자재 반등, 위험선호 복귀"),
        ("2017-01", "2018-01", "글로벌 동반성장 — 저변동성·강세장(synchronized growth)"),
        ("2018-02", "2018-12", "Fed 긴축·무역분쟁 — 변동성 확대, 4분기 급락"),
        ("2019-01", "2019-12", "Fed 보험성 인하·무역분쟁 완화 — 멀티플 확장"),
        ("2020-02", "2020-05", "COVID 충격 — 급락 후 대규모 부양·V자 반등"),
        ("2020-06", "2021-12", "리오프닝·유동성 과잉 — 성장주·밈주식 랠리"),
        ("2022-01", "2022-12", "인플레 급등·Fed 급속 긴축 — 약세장, 멀티플 압축"),
        ("2023-01", "2023-12", "디스인플레·AI 랠리 시작 — 빅테크 주도 반등"),
        ("2024-01", "2025-12", "AI 주도 강세·금리 고원 — 실적 견조, 밸류 부담"),
        ("2004-06", "2006-12", "금리 인상 사이클 중반 — 견조한 성장·완만한 인플레"),
        ("2000-01", "2002-12", "닷컴 버블 붕괴 — 고밸류 기술주 폭락"),
    ]
    for start, end, note in table:
        if start <= ym <= end:
            return note
    return f"{y}년대 — 특이 국면 라벨 없음(지표 패턴 매칭)"


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
    "US": {"unit": "$ (S&P500 Bottom-Up, FactSet)", "actual_through": 2025, "source": "FactSet Earnings Insight",
           "eps_as_of": "2026-06-12",
           "note": "FactSet Earnings Insight(6/12 발간) 기준 — CY2026 EPS 성장 +23.2%, CY2027 +16.2% 컨센서스. "
                   "S&P500 bottom-up EPS, forward 12M ≈ $361.5(forward P/E 20.1·지수 7,267). 매주 금요일 갱신.",
           "eps": {"2020": 140.23, "2021": 208.01, "2022": 219.17, "2023": 220.21,
                   "2024": 243.02, "2025": 275.24, "2026": 339.10, "2027": 394.04}},
    "KR": {"unit": "지수(2020=100, 컨센서스)", "actual_through": 2025, "source": "Goldman Sachs/MSCI",
           "eps_as_of": "2026-05-31",
           "note": "2026 컨센서스 EPS 성장 전체 +265%(반도체 제외 +42%) — 메모리 슈퍼사이클. "
                   "연초 +48% → 5월 +265%로 지속 상향(Goldman Sachs). 2026 급증은 삼성·하이닉스 cap-weight 효과. "
                   "※ DataGuide(FnGuide)·퀀티와이즈에서 최신 컨센서스로 갱신 필요(수동).",
           "eps": {"2020": 100, "2021": 170, "2022": 130, "2023": 55,
                   "2024": 100, "2025": 130, "2026": 475, "2027": 540}},
    "EU": {"unit": "지수(2020=100, 근사)", "actual_through": 2025, "source": "추정·편집 가능",
           "eps_as_of": "2026-05-31",
           "eps": {"2020": 100, "2021": 142, "2022": 156, "2023": 150,
                   "2024": 156, "2025": 166, "2026": 181, "2027": 196}},
    "JP": {"unit": "지수(2020=100, 근사)", "actual_through": 2025, "source": "추정·편집 가능",
           "eps_as_of": "2026-05-31",
           "eps": {"2020": 100, "2021": 128, "2022": 145, "2023": 160,
                   "2024": 176, "2025": 188, "2026": 203, "2027": 218}},
    "CN": {"unit": "지수(2020=100, 근사)", "actual_through": 2025, "source": "추정·편집 가능",
           "eps_as_of": "2026-05-31",
           "eps": {"2020": 100, "2021": 112, "2022": 100, "2023": 106,
                   "2024": 112, "2025": 117, "2026": 124, "2027": 133}},
}


# ── AI 섹션 (6번 항목) 데이터 — 대부분 시드(편집 가능). as_of로 신선도 표기 ──
AI_AS_OF = "2026-06-01"
# 하이퍼스케일러 연간 CAPEX($B). 2026=컨센서스(GS Exhibit 15), 2027=추정.
#  2026 컨센서스: GOOGL $186B·AMZN $218B·META $132B·MSFT $157B (총 $693B).
AI_CAPEX = {
    "Microsoft": {"2020": 15, "2021": 21, "2022": 24, "2023": 28, "2024": 44, "2025": 92, "2026": 157, "2027": 190},
    "Alphabet":  {"2020": 22, "2021": 24, "2022": 31, "2023": 32, "2024": 52, "2025": 88, "2026": 186, "2027": 225},
    "Amazon":    {"2020": 40, "2021": 55, "2022": 60, "2023": 53, "2024": 78, "2025": 115, "2026": 218, "2027": 260},
    "Meta":      {"2020": 15, "2021": 19, "2022": 32, "2023": 28, "2024": 39, "2025": 72, "2026": 132, "2027": 160},
}
AI_CAPEX_ACTUAL_THROUGH = 2025
AI_CAPEX_SOURCE = "https://ir.aboutamazon.com (각사 IR) · 2026 컨센서스 GS"
# 미국 명목 GDP 연간 fallback ($B, SAAR 연평균 근사). FRED throttle 시 사용.
# 출처: BEA (US Bureau of Economic Analysis), 2025는 Q4 SAAR 기준 근사.
GDP_ANNUAL_SEED = {
    "2020": 20893, "2021": 23200, "2022": 25463, "2023": 27357,
    "2024": 28620, "2025": 29900,
}
# 미국 R&D 투자 / GDP (%). 버블 점검용. (NSF/BEA 근사)
AI_RND_GDP = {"2015": 2.7, "2018": 3.0, "2020": 3.2, "2022": 3.4, "2023": 3.5, "2024": 3.6, "2025": 3.7}
# FCF 우려 코멘트 — AI capex 급증에 따른 잉여현금흐름 압박
AI_FCF_NOTE = (
    "FCF 급락 경보: AI capex 급증($367B→$693B, +89% YoY 추정)에 따라 2026E FCF가 "
    "Microsoft $60B(2025比 −17%), Alphabet $50B(−33%), Amazon −$20B(흑자→적자 역전), "
    "Meta $30B(−33%)로 일제히 급감 예상. 영업이익은 성장세이나 자본지출이 현금창출을 "
    "초과 — 배당·자사주보다 AI 투자에 현금을 소진하는 국면. 빅4 합산 FCF $227B→$120B(−47%)로 "
    "FCF 수익률 하락 + 고밸류가 맞물려 실망 시 멀티플 압축 확대. "
    "관전 포인트: Q2~Q3 AI 클라우드 ARR 성장이 capex 증가를 상쇄하는 속도."
)
# AI 랩 매출/수익성 추정 — 언론·업계 추정치. 변동 큼, 수시 갱신.
AI_LABS = {
    "OpenAI": {"rev": {"2023": 1.6, "2024": 3.7, "2025": 13, "2026": 30, "2027": 60},
               "profit_note": "추론 비용·학습 투자로 적자 지속. 흑자 전환 목표 ~2029~2030(연간 적자 2026~2027 정점 전망).",
               "source": "언론 추정(The Information/Reuters 등)"},
    "Anthropic": {"rev": {"2023": 0.1, "2024": 1.0, "2025": 5, "2026": 12, "2027": 25},
                  "profit_note": "엔터프라이즈·API 중심 고성장. 컴퓨트 투자로 단기 적자, 흑자 전환은 OpenAI보다 늦거나 비슷.",
                  "source": "언론 추정"},
}


# 빅4 연간 재무 ($B). 2026~2027 추정. mktcap 2025=현재 시총(GS Exhibit 15). (근사·편집 가능)
#  시총: GOOGL $4.7T·AMZN $2.9T·META $1.6T·MSFT $3.0T. FCF는 2026 CAPEX 급증분 반영.
AI_FINANCIALS = {
    "Microsoft": {
        "rev":    {"2020": 143, "2021": 168, "2022": 198, "2023": 212, "2024": 245, "2025": 282, "2026": 315, "2027": 350},
        "opinc":  {"2020": 53, "2021": 70, "2022": 83, "2023": 88, "2024": 109, "2025": 128, "2026": 142, "2027": 160},
        "fcf":    {"2020": 45, "2021": 56, "2022": 65, "2023": 59, "2024": 74, "2025": 72, "2026": 60, "2027": 80},
        "mktcap": {"2020": 1680, "2021": 2520, "2022": 1790, "2023": 2790, "2024": 3130, "2025": 3000}},
    "Alphabet": {
        "rev":    {"2020": 183, "2021": 257, "2022": 283, "2023": 307, "2024": 350, "2025": 390, "2026": 440, "2027": 490},
        "opinc":  {"2020": 41, "2021": 79, "2022": 75, "2023": 84, "2024": 112, "2025": 135, "2026": 160, "2027": 185},
        "fcf":    {"2020": 42, "2021": 67, "2022": 60, "2023": 69, "2024": 73, "2025": 75, "2026": 50, "2027": 80},
        "mktcap": {"2020": 1190, "2021": 1920, "2022": 1150, "2023": 1750, "2024": 2310, "2025": 4700}},
    "Amazon": {
        "rev":    {"2020": 386, "2021": 470, "2022": 514, "2023": 575, "2024": 638, "2025": 700, "2026": 770, "2027": 840},
        "opinc":  {"2020": 23, "2021": 25, "2022": 12, "2023": 37, "2024": 68, "2025": 88, "2026": 105, "2027": 125},
        "fcf":    {"2020": 31, "2021": -9, "2022": -17, "2023": 37, "2024": 38, "2025": 35, "2026": -20, "2027": 20},
        "mktcap": {"2020": 1630, "2021": 1690, "2022": 860, "2023": 1570, "2024": 2300, "2025": 2900}},
    "Meta": {
        "rev":    {"2020": 86, "2021": 118, "2022": 116, "2023": 135, "2024": 164, "2025": 190, "2026": 220, "2027": 250},
        "opinc":  {"2020": 33, "2021": 47, "2022": 29, "2023": 47, "2024": 69, "2025": 87, "2026": 98, "2027": 112},
        "fcf":    {"2020": 23, "2021": 39, "2022": 19, "2023": 44, "2024": 52, "2025": 45, "2026": 30, "2027": 50},
        "mktcap": {"2020": 780, "2021": 935, "2022": 320, "2023": 910, "2024": 1500, "2025": 1600}},
}
# 과거 클라우드 capex 사이클 참고 (빅4 capex/매출 강도, 근사)
CLOUD_CYCLE_NOTE = ("1차 클라우드 capex 사이클(2016~2018) 당시 빅4 capex/매출 강도는 ~9~12% 수준이었음. "
                    "현재 AI 사이클은 20%대로 약 2배 — 투자 강도가 역대 최고. 매출·FCF가 이를 따라오는지가 버블 판가름.")


# ── 이달의 정성 요인 & 캘린더 (월별 수동 시드, 편집 가능) ──────────────────
#  events: 일정·이벤트와 시장 영향  /  themes: 진행 중 이슈 전망
#  dir: pos(호재) neg(악재) neu(중립) watch(관전·변수)
MONTHLY_FACTORS = {
    "2026-06": {
        "headline": "Computex·FOMC·CPI 집중 + 이란 전쟁 종전 협상이 6월 최대 변수",
        "events": [
            {"date": "6/2~6", "title": "Computex 2026 (대만)", "dir": "pos", "sector": "반도체·AI",
             "impact": "AI 가속기·서버·쿨링·HBM 차세대 로드맵 공개. NVDA·AMD·TSMC·서버 ODM·국내 HBM(삼성·하이닉스)·냉각·기판 수혜. 단, 기대 선반영 시 'sell-the-news' 주의."},
            {"date": "6/5", "title": "미국 5월 고용", "dir": "watch",
             "impact": "냉각 속 견조 유지면 골디락스, 급랭이면 침체 우려. 임금·실업률이 Fed 경로 변수."},
            {"date": "6/11", "title": "미국 5월 CPI", "dir": "watch",
             "impact": "유가발 헤드라인 재가속 vs 코어 안정. 4%대 고착이면 멀티플(특히 고밸류 테크) 압박."},
            {"date": "6/16~17", "title": "FOMC", "dir": "neu",
             "impact": "유가 인플레로 동결 유력. 점도표·파월 톤이 인하 기대를 좌우 — 매파면 단기 조정."},
            {"date": "6/19", "title": "쿼드러플 위칭(만기)", "dir": "watch",
             "impact": "선물·옵션 동시만기. 수급 변동성·리밸런싱 확대 가능."},
            {"date": "6월 중", "title": "MSCI 반기 리뷰", "dir": "watch", "sector": "한국",
             "impact": "한국 선진지수 편입 관찰대상 여부·지수 리밸런싱 패시브 자금. 편입 진전 시 중장기 외인 유입 재료."},
        ],
        "themes": [
            {"title": "🇺🇸 나스닥 변동성 리포트 — AI 밸류 논쟁", "dir": "watch",
             "outlook": "VIX 15~17로 절대수준은 낮으나 빅테크 쏠림에 일중·종목 변동 확대. 변동요인 ①AI capex/매출 강도 40%대 정당성 논쟁(엔비디아·하이퍼스케일러 가이던스 민감) ②CAPE 42·PEG 1.5 고밸류로 실적·금리 실망 시 멀티플 압축 ③이란發 유가로 Fed 인하 지연. 지수 하방보다 그로스↔밸류 로테이션·종목 분산 변동성이 핵심."},
            {"title": "🇰🇷 코스피 변동성·수급 리포트 — 외인 매도 vs 개인 흡수", "dir": "watch",
             "outlook": "VKOSPI 21로 VIX보다 높음(한국 특유 변동성). 수급: 외국인 YTD 120조대 대규모 순매도(차익실현·환헤지)를 개인·기관이 흡수하는 구조(상세는 아래 한국 수급 패널). 변동요인 ①삼성·하이닉스 시총 절반 쏠림(메모리 사이클 레버리지) ②원화 1,500+ 약세로 외인 환손실 ③신용잔고 증가(레버리지 확대) ④MSCI 리뷰·밸류업 기대. 외인 순매도 진정·환율 안정이 변동성 축소의 키."},
            {"title": "이란 전쟁 · 종전 협상", "dir": "watch",
             "outlook": "휴전 진전 시 유가 급락 → 인플레 완화·위험선호 회복(에너지 비중 축소, 항공·소비재 반등). 교착·확전 시 유가 $100+ 고착으로 인플레·멀티플 압박 지속. 6월 협상 헤드라인이 방향타."},
            {"title": "AI capex 버블 논쟁", "dir": "watch",
             "outlook": "빅4 capex/매출 40%대(2026E)로 역대 최고. 하반기 클라우드·AI 매출이 투자를 정당화하는지가 관건. Computex 신제품·하이퍼스케일러 가이던스 재확인 필요(6번 AI 섹션 참조)."},
            {"title": "한국 메모리 슈퍼사이클 지속성", "dir": "pos",
             "outlook": "HBM·DDR5 가격 강세로 EPS 상향 지속이나, 최근 7일 수정 모멘텀은 둔화 신호. DRAM 고정가·HBM capa 증설·미·중 수출규제가 체크포인트."},
            {"title": "Fed 인하 시점 후퇴 · 고밸류 부담", "dir": "neg",
             "outlook": "유가 인플레로 2026 인하 지연 컨센서스. CAPE 42·PEG 1.5로 밸류 부담 → 금리·실적 실망 시 변동성. 퀄리티·현금흐름주 선호."},
        ],
    },
    "2026-07": {
        "headline": "Q2 어닝시즌 — 빅테크 AI capex 정당성 검증 + 7월 FOMC·CPI가 하반기 방향 결정",
        "events": [
            {"date": "7/1", "title": "한국 6월 수출(관세청)", "dir": "watch", "sector": "반도체·한국",
             "impact": "반도체·자동차 중심 수출 모멘텀 확인. HBM·메모리 단가 강세 지속 여부가 코스피 EPS 상향의 키. 6월 10일·20일 잠정치 대비 월간 확정."},
            {"date": "7/3", "title": "미국 6월 고용", "dir": "watch",
             "impact": "냉각 연착륙 vs 급랭. 실업률·임금이 7월 FOMC 인하 기대를 좌우. 견조하면 'higher for longer' 재확인."},
            {"date": "7/15", "title": "미국 6월 CPI", "dir": "watch",
             "impact": "이란發 유가가 헤드라인에 본격 반영되는 첫 지표. 코어 안정 vs 헤드라인 재가속 — 4%대 고착이면 고밸류 멀티플 압박."},
            {"date": "7/22~31", "title": "빅테크 Q2 실적 (MSFT·GOOGL·META·AMZN·AAPL)", "dir": "neu", "sector": "AI·테크",
             "impact": "하이퍼스케일러 capex 가이던스 상향 폭 + AI 매출 기여가 핵심. capex/매출 40%대 정당화 못 하면 'AI 버블' 논쟁 재점화 → 그로스 조정. (6번 AI 섹션 참조)"},
            {"date": "7/24", "title": "한국 2분기 GDP(속보)", "dir": "watch", "sector": "한국",
             "impact": "수출 회복의 성장 기여 확인. 내수 부진 지속 시 한은 인하 기대 — 원화·금리 변수."},
            {"date": "7/하순", "title": "삼성전자·SK하이닉스 Q2 실적", "dir": "pos", "sector": "반도체",
             "impact": "HBM·DDR5 가격 강세의 실적 반영. 가이던스·HBM capa 증설 코멘트가 메모리 슈퍼사이클 지속성 판단 근거."},
            {"date": "7/28~29", "title": "FOMC", "dir": "neu",
             "impact": "유가 인플레로 동결 유력하나, 6~7월 CPI·고용 둔화 시 9월 인하 시그널 가능. 파월 톤이 하반기 위험선호 방향타."},
        ],
        "themes": [
            {"title": "🇺🇸 Q2 어닝시즌 — AI capex 정당성의 분수령", "dir": "watch",
             "outlook": "빅4 capex/매출 40%대(역대 최고)가 클라우드·AI 매출로 정당화되는지 Q2 실적이 첫 본격 검증대. 가이던스 상향+AI ARR 가속이면 랠리 연장, 'capex만 늘고 매출 미온'이면 그로스→밸류 로테이션·멀티플 압축. 엔비디아 8월 실적 전 하이퍼스케일러 발주 톤이 선행 지표."},
            {"title": "🇰🇷 코스피 Q2 실적 — 메모리 슈퍼사이클 실적 확인", "dir": "pos",
             "outlook": "삼성·하이닉스 Q2 HBM·DRAM 강세의 실적 반영 + 가이던스. 외국인 순매도(YTD 120조대) 진정·환율(1,500+) 안정 시 수급 개선. 변수: ①메모리 고정가·HBM capa ②최근 EPS 수정 모멘텀 둔화 신호 ③밸류업·MSCI 후속."},
            {"title": "이란 종전 후속 · 유가 경로", "dir": "watch",
             "outlook": "휴전 정착 시 유가 하향 안정 → 인플레 완화·Fed 인하 여지 확대(위험선호). 재확전·호르무즈 리스크 재부각 시 $100+ 재고착으로 7월 CPI·멀티플 압박. 6월 협상 결과의 지속성이 7월 변수."},
            {"title": "Fed 9월 인하 기대 vs 유가 인플레", "dir": "neu",
             "outlook": "6~7월 CPI·고용 둔화가 확인되면 9월 인하 컨센서스 형성 → 듀레이션·그로스 우호. 유가발 인플레 재가속이면 인하 후퇴로 되돌림. 7월 FOMC 점도표·도트가 분기점."},
        ],
    },
    "2026-08": {
        "headline": "8월 FOMC 부재 — 잭슨홀(파월 연설)·엔비디아 Q2가 9월 인하 기대와 AI 사이클을 가를 마지막 주 분수령. 거래 비수기 계절적 변동성 유의",
        "events": [
            {"date": "8/1", "title": "한국 7월 수출(관세청)", "dir": "pos", "sector": "반도체·한국",
             "impact": "반도체·자동차 수출 모멘텀 확인. HBM·메모리 단가 강세가 7월에도 이어졌는지가 하반기 코스피 EPS 상향의 핵심. 10일·20일 잠정치 대비 월간 확정."},
            {"date": "8/7", "title": "미국 7월 고용", "dir": "watch",
             "impact": "8월 FOMC가 없어 9월 인하 기대의 1차 관문. 실업률·임금 둔화면 9월 인하 컨센서스 강화, 견조하면 'higher for longer' 되돌림."},
            {"date": "8/12", "title": "미국 7월 CPI", "dir": "watch",
             "impact": "유가·관세 물가 전가가 본격 반영되는 지표. 코어 안정이면 9월 인하 길 확보, 4%대 재가속이면 고밸류 멀티플 압박. 잭슨홀 직전 방향타."},
            {"date": "8/26", "title": "엔비디아 Q2(FY27) 실적", "dir": "neu", "sector": "AI·반도체",
             "impact": "장 마감 후 발표. 데이터센터·HBM 수요와 블랙웰 차세대 가이던스가 7월 빅테크 capex 상향을 정당화하는지의 최종 검증대. 어긋나면 그로스→밸류 로테이션·메모리 사이클 논쟁 재점화. (6번 AI 섹션 참조)"},
            {"date": "8/27", "title": "한은 금통위", "dir": "watch", "sector": "한국",
             "impact": "성장·환율(1,500+)·가계부채 사이에서 인하 시점 저울질. 원화 약세·외인 순매도 국면이라 인하 신호는 환율 변수. 도비시면 듀레이션·내수, 매파면 원화 지지."},
            {"date": "8/27~29", "title": "잭슨홀 경제정책 심포지엄", "dir": "neu",
             "impact": "8월 최대 이벤트. 주제 'Financial Innovation: Implications for Payments and Policy'이나, 파월 의장 연설의 9월 인하·QT/대차대조표 관련 톤이 하반기 위험선호 방향타. 6~7월 지표 둔화 확인 시 사전 인하 시그널 가능."},
            {"date": "8/하순", "title": "한국 7월 산업활동·국제수지", "dir": "watch", "sector": "한국",
             "impact": "수출 회복의 생산·투자 파급과 내수 점검. 경상흑자·반도체 생산이 코스피 이익 사이클 지속성의 보조 근거."},
        ],
        "themes": [
            {"title": "🇺🇸 잭슨홀·9월 인하 분수령 — 8월 FOMC 부재의 공백", "dir": "neu",
             "outlook": "8월엔 FOMC가 없어(다음 9/16~17) 잭슨홀 파월 연설이 사실상 유일한 통화정책 시그널. 6~7월 CPI·고용 둔화가 확인되면 9월 인하 사전 신호 → 듀레이션·그로스 우호. 유가·관세 인플레 재가속이면 'higher for longer' 재확인으로 멀티플 압박. QT 종료·대차대조표 코멘트도 주목."},
            {"title": "🇺🇸 엔비디아 Q2 — AI capex 정당성의 최종 검증", "dir": "watch",
             "outlook": "7월 빅테크가 올린 capex(매출 40%대)를 엔비디아 데이터센터 매출·가이던스가 뒷받침하는지 8/26 실적이 분기점. 블랙웰 후속·주권(소버린)AI 수요가 가속이면 랠리 연장, 'capex만 늘고 수요 미온'이면 그로스→밸류 로테이션·AI 버블 논쟁 재점화."},
            {"title": "🇰🇷 메모리 슈퍼사이클 — Q2 확인 후 하반기 단가가 관건", "dir": "pos",
             "outlook": "삼성·하이닉스 Q2 호실적 반영 후, HBM4·DDR5 고정가와 capa 증설이 하반기 EPS 상향 지속의 키. 다만 최근 EPS 수정 모멘텀 둔화 신호가 잔존 — DRAM 고정가 협상·미·중 수출규제가 체크포인트. 엔비디아 가이던스가 메모리 수요 선행 지표."},
            {"title": "🇰🇷 외인 수급·환율 — 한은 인하 경로와 맞물림", "dir": "watch",
             "outlook": "YTD 대규모 외인 순매도와 원화 1,500+ 약세 지속 여부가 코스피 수급의 키. 8/27 금통위가 도비시하면 원화 추가 약세→외인 환손실 우려, 매파면 원화 지지. 환율 안정·외인 순매도 진정 + 밸류업·MSCI 후속이 수급 개선 트리거."},
            {"title": "유가·관세 인플레 — 인하 경로의 상방 리스크", "dir": "neu",
             "outlook": "이란 종전 이후 유가 경로 + 관세 물가 전가가 7월 CPI에 반영되는 강도가 9월 인하 가능성의 핵심 변수. 유가 하향 안정·관세 전가 제한적이면 인하 여지 확대, 재가속이면 잭슨홀 톤 매파 전환."},
            {"title": "8월 계절적 변동성 — 비수기 얇은 유동성", "dir": "watch",
             "outlook": "8월은 휴가철 거래량 비수기로 유동성이 얇아 이벤트 변동성이 증폭되는 경향(역사적 8~9월 약세 계절성). 마지막 주 엔비디아·금통위·잭슨홀이 한 주에 몰려 변동성 집중 — 포지션·헤지 점검 구간."},
        ],
    },
}


def build_monthly(today):
    """이달(없으면 가장 최근 정의된 달)의 정성 요인."""
    ym = today.strftime("%Y-%m")
    if ym in MONTHLY_FACTORS:
        key = ym
    else:
        past = [k for k in sorted(MONTHLY_FACTORS) if k <= ym]
        key = past[-1] if past else None
    if not key:
        return None
    return {"month": key, "stale": key != ym, **MONTHLY_FACTORS[key]}


def build_monthly_all(today):
    """정의된 모든 달의 정성요인 (월 선택 드롭다운용, 최신월 먼저)."""
    ym = today.strftime("%Y-%m")
    return [{"month": k, "stale": k != ym, **MONTHLY_FACTORS[k]}
            for k in sorted(MONTHLY_FACTORS, reverse=True)]


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


# 종목 한줄 태그 (핵심 테마). 없으면 데이터 기반 자동 코멘트로 대체.
STOCK_TAGS = {
    # US
    "NVDA": "AI 가속기 사실상 독점·데이터센터 폭증", "AVGO": "맞춤형 AI칩(ASIC)·네트워킹",
    "AMD": "AI GPU 추격·MI 시리즈", "MU": "HBM·메모리 업사이클", "TSM": "AI칩 위탁생산 독점적",
    "ASML": "EUV 노광 독점", "MSFT": "Azure·코파일럿 AI 수익화", "AAPL": "온디바이스 AI·서비스",
    "ORCL": "OCI 클라우드 수주 급증", "CRM": "에이전트포스 AI", "ADBE": "생성형 AI 크리에이티브",
    "PLTR": "AIP 정부·기업 수요", "GOOGL": "검색·Gemini·클라우드", "META": "광고 회복·AI 추천",
    "NFLX": "광고요금제·콘텐츠", "DIS": "스트리밍 흑자 전환", "JPM": "NIM·IB 회복",
    "BAC": "예금·금리 레버리지", "GS": "IB·트레이딩", "WFC": "자산상한 해제 기대", "MS": "WM·IB",
    "LLY": "GLP-1 비만치료 선두", "UNH": "관리의료 마진", "JNJ": "제약·의료기기", "ABBV": "면역질환 후속",
    "MRK": "키트루다·종양", "AMZN": "AWS·리테일 마진", "TSLA": "FSD·로보택시 기대", "HD": "주택수리",
    "MCD": "가성비 메뉴", "NKE": "리브랜딩·중국", "XOM": "유가 레버리지·정제", "CVX": "배당·가이아나",
    "COP": "셰일 효율", "SLB": "유전서비스", "GE": "항공엔진 수주", "CAT": "인프라·전력장비",
    "BA": "생산정상화", "HON": "자동화·항공", "UNP": "물동량",
    # KR
    "005930.KS": "메모리·HBM·파운드리 턴", "000660.KS": "HBM 선두·실적 급증",
    "373220.KS": "전기차 둔화·ESS", "006400.KS": "각형 배터리", "051910.KS": "양극재·화학",
    "005380.KS": "하이브리드·환율수혜", "000270.KS": "수익성·밸류업", "105560.KS": "주주환원·밸류업",
    "055550.KS": "배당·NIM", "086790.KS": "자사주 소각", "035420.KS": "광고·AI·웹툰",
    "035720.KS": "톡비즈·AI", "207940.KS": "CDMO 증설", "068270.KS": "시밀러·합병효과",
    "012450.KS": "방산수출 호황", "042660.KS": "조선 슈퍼사이클", "009540.KS": "LNG선·친환경선",
    "352820.KS": "K팝 신인·투어", "035900.KQ": "아티스트 IP", "041510.KQ": "신인·일본",
    "005490.KS": "철강가·2차전지 소재", "004020.KS": "전기로·후판", "010130.KS": "비철·동제련",
    "017670.KS": "배당·AI/IDC", "030200.KS": "배당·B2B", "032640.KS": "배당·AI",
    "097950.KS": "원가·해외식품", "090430.KS": "중국 화장품 회복", "271560.KS": "제과·내수",
    # EU/JP/CN
    "SAP": "클라우드 ERP·AI", "NVO": "위고비 비만", "MC.PA": "명품 수요", "SHEL": "에너지·배당",
    "SIE.DE": "산업 자동화", "TM": "하이브리드 강세", "SONY": "게임·이미지센서",
    "8035.T": "반도체 장비", "6861.T": "FA 센서", "6501.T": "발전·AI인프라",
    "BABA": "클라우드·AI 회복", "PDD": "저가 커머스·테무", "JD": "리테일 마진", "BIDU": "검색·AI",
    "TCEHY": "게임·위챗·광고",
}


# 한국 투자자예탁금 월말 시계열(조원) — 무료 안정 소스 없어 수동 시드(KOFIA freesis 기준 근사).
#  갱신: freesis.kofia.or.kr 증시자금추이. 최근값은 MANUAL_FLOWS["kr_deposit"]와 일치시키기.
KR_DEPOSIT_SERIES = {
    "2024-01": 52, "2024-04": 55, "2024-07": 54, "2024-10": 53,
    "2025-01": 55, "2025-04": 58, "2025-07": 62, "2025-10": 70,
    "2026-01": 78, "2026-02": 82, "2026-03": 86, "2026-04": 90, "2026-05": 95,
}

# 한국 신용거래융자 잔고(조원) — KOSPI/KOSDAQ. 무료 안정 소스 없어 월별 수동 시드.
#  갱신: KOFIA freesis 증시자금추이 / KRX 신용거래. {YYYY-MM: (KOSPI, KOSDAQ)}
KR_CREDIT_SERIES = {
    "2024-03": (10.5, 8.3), "2024-06": (10.8, 8.5), "2024-09": (10.2, 7.9), "2024-12": (10.6, 8.4),
    "2025-03": (11.2, 8.8), "2025-06": (11.8, 9.2), "2025-09": (12.5, 9.8), "2025-12": (13.4, 10.3),
    "2026-03": (14.6, 11.0), "2026-04": (15.1, 11.3), "2026-05": (15.8, 11.7), "2026-06": (16.3, 12.0),
}


def _kospi_credit_share(m):
    """월 m 시점의 신용잔고 중 KOSPI 비중(0~1) — KR_CREDIT_SERIES 시드(코스피,코스닥)에서
    가장 가까운 시점 비율. 네이버 실측은 총액만 줘서 시장별 분해에 시드 비율을 사용."""
    seed = sorted(KR_CREDIT_SERIES)
    le = [s for s in seed if s <= m]
    key = le[-1] if le else seed[0]
    kc, qc = KR_CREDIT_SERIES[key]
    tot = kc + qc
    return (kc / tot) if tot else 0.57


def build_kr_credit(kospi_me, kosdaq_me):
    """신용잔고(총) + 같은 시점 KOSPI/KOSDAQ 지수 정렬 → 추이 차트용.
    네이버 증시자금추이 실측(총 신용잔고)을 시드 비율로 코스피/코스닥 신용잔고로 분해.
    실측 없으면 KOSPI/KOSDAQ 시드 합산."""
    kd = load_kr_deposit()
    if kd and kd.get("credit", {}).get("values"):
        cme = to_month_end(kd["credit"]["dates"], kd["credit"]["values"])
        months = sorted(cme)
        dates, total, kospi_i, kosdaq_i, kospi_c, kosdaq_c = [], [], [], [], [], []
        for m in months:
            tot = round(cme[m], 1); sh = _kospi_credit_share(m)
            dates.append(m + "-01"); total.append(tot)
            kospi_c.append(round(tot * sh, 1)); kosdaq_c.append(round(tot * (1 - sh), 1))
            kospi_i.append(round(kospi_me[m], 1) if m in kospi_me else None)
            kosdaq_i.append(round(kosdaq_me[m], 2) if m in kosdaq_me else None)
        cur = kd["current"]
        csh = _kospi_credit_share(months[-1]) if months else 0.57
        ct = cur.get("credit")
        return {"dates": dates, "total_credit": total, "kospi_credit": kospi_c, "kosdaq_credit": kosdaq_c,
                "kospi_idx": kospi_i, "kosdaq_idx": kosdaq_i,
                "unit": "조원", "realtime": True,
                "current": {"total": ct, "deposit": cur.get("deposit"), "as_of": cur.get("as_of"),
                            "kospi": round(ct * csh, 1) if ct else None,
                            "kosdaq": round(ct * (1 - csh), 1) if ct else None},
                "source": "네이버 증시자금추이(실측·시장별은 시드비율 분해)", "source_url": kd.get("source_url")}
    # fallback: KOSPI/KOSDAQ 시드 (시장별 직접)
    months = sorted(KR_CREDIT_SERIES)
    dates, total, kospi_i, kosdaq_i, kospi_c, kosdaq_c = [], [], [], [], [], []
    for m in months:
        kc, qc = KR_CREDIT_SERIES[m]
        dates.append(m + "-01"); total.append(round(kc + qc, 1))
        kospi_c.append(round(kc, 1)); kosdaq_c.append(round(qc, 1))
        kospi_i.append(round(kospi_me[m], 1) if m in kospi_me else None)
        kosdaq_i.append(round(kosdaq_me[m], 2) if m in kosdaq_me else None)
    last = months[-1]; lk, lq = KR_CREDIT_SERIES[last]
    return {"dates": dates, "total_credit": total, "kospi_credit": kospi_c, "kosdaq_credit": kosdaq_c,
            "kospi_idx": kospi_i, "kosdaq_idx": kosdaq_i,
            "unit": "조원", "current": {"total": round(lk + lq, 1), "as_of": last,
                                        "kospi": round(lk, 1), "kosdaq": round(lq, 1)},
            "source": "KRX 신용거래(시드)", "source_url": "https://freesis.kofia.or.kr/"}


def build_kr_credit_daily():
    """일별 신용잔고 + 지수 시계열 (최근 90 거래일).
    총 신용잔고(네이버 실측) × 월별 KOSPI/KOSDAQ 비율 → 시장별 분해.
    지수: yfinance ^KS11(KOSPI), ^KQ11(KOSDAQ)."""
    kd = load_kr_deposit()
    if not (kd and kd.get("credit", {}).get("dates")):
        return None
    try:
        import yfinance as yf
        import pandas as pd
        cred_dates = kd["credit"]["dates"][-90:]
        cred_vals = kd["credit"]["values"][-90:]
        start_dt = cred_dates[0]
        kospi_raw = yf.Ticker("^KS11").history(start=start_dt, auto_adjust=False, interval="1d")
        kosdaq_raw = yf.Ticker("^KQ11").history(start=start_dt, auto_adjust=False, interval="1d")
        if kospi_raw.empty or kosdaq_raw.empty:
            return None
        kospi_map = {ts.strftime("%Y-%m-%d"): round(float(v), 2)
                     for ts, v in kospi_raw["Close"].items() if not pd.isna(v)}
        kosdaq_map = {ts.strftime("%Y-%m-%d"): round(float(v), 2)
                      for ts, v in kosdaq_raw["Close"].items() if not pd.isna(v)}
        dates, kospi_c, kosdaq_c, kospi_i, kosdaq_i = [], [], [], [], []
        for d, tot in zip(cred_dates, cred_vals):
            ki = kospi_map.get(d)
            qi = kosdaq_map.get(d)
            if ki is None and qi is None:
                continue
            sh = _kospi_credit_share(d[:7])
            dates.append(d)
            kospi_c.append(round(tot * sh, 2))
            kosdaq_c.append(round(tot * (1 - sh), 2))
            kospi_i.append(ki)
            kosdaq_i.append(qi)
        if len(dates) < 5:
            return None
        return {"dates": dates, "kospi_credit": kospi_c, "kosdaq_credit": kosdaq_c,
                "kospi_idx": kospi_i, "kosdaq_idx": kosdaq_i, "unit": "조원"}
    except Exception as e:
        print(f"[build_kr_credit_daily] 실패: {e}")
        return None


# 수동 지표 원본 데이터 링크 (클릭 시 원천 확인)
MANUAL_URLS = {
    "ism_pmi": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/",
    "cnn_fng": "https://www.cnn.com/markets/fear-and-greed",
    "aaii_spread": "https://www.aaii.com/sentimentsurvey",
    "put_call": "https://www.cboe.com/us/options/market_statistics/daily/",
    "vkospi": "https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
    "cta_pos": "https://www.isabelnet.com/?s=CTA+equity+positioning",
    "retail_alloc": "https://www.aaii.com/assetallocationsurvey",
    "kr_deposit": "https://freesis.kofia.or.kr/",
    "kr_flows": "https://finance.naver.com/sise/investorDealTrendDay.naver?sosok=01",
}


def indicator_source(key, src, transform):
    """지표 원본 데이터 출처 {name, url}. 없으면 None."""
    if transform == "benchlvl":
        ytk = {"vix": "%5EVIX", "us10y": "%5ETNX", "usdkrw": "KRW=X"}.get(key, "")
        return {"name": "yfinance (benchmarks.js)", "url": f"https://finance.yahoo.com/quote/{ytk}"}
    if transform == "multpl":
        return {"name": "multpl.com", "url": f"https://www.multpl.com/{src}"}
    if transform in ("yoy", "mom", "level", "daily", "oilyoy", "ma3") and src and len(src) <= 14 and src.replace("_", "").isalnum() and any(ch.isupper() for ch in src):
        return {"name": f"FRED: {src}", "url": f"https://fred.stlouisfed.org/series/{src}"}
    if transform == "yfmo":
        return {"name": f"yfinance ({src})", "url": f"https://finance.yahoo.com/quote/{src.replace('^', '%5E')}"}
    if transform == "cugd":
        return {"name": "yfinance (HG=F/GC=F)", "url": "https://finance.yahoo.com/quote/HG%3DF"}
    if key in ("spx_mom",):
        return {"name": "Yahoo Finance (^GSPC)", "url": "https://finance.yahoo.com/quote/%5EGSPC/history"}
    if key in ("spx_fwd_pe", "erp"):
        return {"name": "FactSet/yfinance", "url": "https://insight.factset.com/topic/earnings"}
    if key == "kospi_fwd_pe":
        return {"name": "yfinance (EWY)", "url": "https://finance.yahoo.com/quote/EWY"}
    return None


def _cell(df, row, col):
    try:
        import pandas as pd
        if df is None or row not in df.index or col not in df.columns:
            return None
        v = df.loc[row, col]
        return None if pd.isna(v) else float(v)
    except Exception:
        return None


def _returns(t):
    """가격 수익률 {w1,m1,m3,ytd} (%). 실패 시 {}."""
    import pandas as pd
    try:
        h = t.history(period="1y")["Close"].dropna()
        if len(h) < 2:
            return {}
        cur = float(h.iloc[-1])
        def rr(days):
            return round((cur / float(h.iloc[-1 - days]) - 1) * 100, 1) if len(h) > days else None
        out = {"w1": rr(5), "m1": rr(21), "m3": rr(63)}
        yr = h.index[-1].year
        base = h[h.index < pd.Timestamp(yr, 1, 1, tz=h.index.tz)]
        out["ytd"] = round((cur / float(base.iloc[-1]) - 1) * 100, 1) if len(base) else None
        return out
    except Exception:
        return {}


def ticker_all(tk):
    """종목 1개 → 이익수정 지표 + 시총/Fwd PER/PBR/가격수익률. 데이터 없으면 None."""
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
    # 종목 상세 (시총/Fwd PER/PBR/이름/수익률)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass
    mktcap = info.get("marketCap")
    fwdpe = info.get("forwardPE")
    pbr = info.get("priceToBook")
    name = info.get("shortName") or info.get("longName") or tk
    if fwdpe is not None and (fwdpe <= 0 or fwdpe > 300):
        fwdpe = None
    if pbr is not None and (pbr <= 0 or pbr > 100):
        pbr = None
    rets = _returns(t)
    return {"ticker": tk, "name": name, "mktcap": mktcap, "fwdpe": fwdpe, "pbr": pbr, "rets": rets,
            "up30": up30 or 0, "down30": down30 or 0, "rev7": rev7, "rev30": rev30, "rev90": rev90,
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
        r = ticker_all(tk)
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
            "trend": trend, "n": len(rows), "up": up, "down": dn, "rows": rows}


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


def stock_note(r):
    """종목 한줄: 큐레이션 태그 우선, 없으면 데이터 기반."""
    tag = STOCK_TAGS.get(r["ticker"])
    if tag:
        return tag
    bits = []
    rv = r.get("rev30")
    if rv is not None:
        bits.append("EPS 상향" if rv > 0.5 else ("EPS 하향" if rv < -0.5 else "EPS 보합"))
    yt = (r.get("rets") or {}).get("ytd")
    if yt is not None:
        bits.append(f"YTD {yt:+.0f}%")
    return " · ".join(bits) if bits else "—"


def build_holdings(rows, top=5):
    """바스켓 rows → 시총 상위 N 종목 카드."""
    ranked = sorted(rows, key=lambda r: (r.get("mktcap") or 0), reverse=True)[:top]
    out = []
    for r in ranked:
        out.append({
            "ticker": r["ticker"], "name": r["name"], "mktcap": r.get("mktcap"),
            "fwdpe": round(r["fwdpe"], 1) if r.get("fwdpe") else None,
            "pbr": round(r["pbr"], 2) if r.get("pbr") else None,
            "rets": r.get("rets") or {}, "rev30": r.get("rev30"),
            "note": stock_note(r),
        })
    return out


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
    # EPS 시드 신선도 — cron이 매일 재빌드하므로 경과일·갱신필요 배지가 자동 갱신.
    # showCountryDetail이 source를 그대로 표시 → macro.html 수정 없이 신선도 노출.
    eps_as_of = a.get("eps_as_of")
    days_old, stale, src = None, False, a["source"]
    if eps_as_of:
        try:
            days_old = (date.today() - date.fromisoformat(eps_as_of)).days
        except Exception:
            days_old = None
        src = f"{a['source']} · EPS 기준 {eps_as_of[5:7]}/{eps_as_of[8:10]}"
        if days_old is not None:
            src += f" ({days_old}일 경과)"
            stale = days_old >= 14
        if stale:
            src = "⚠️ 갱신 필요 · " + src
    return {"unit": a["unit"], "source": src, "actual_through": a["actual_through"],
            "eps_as_of": eps_as_of, "days_old": days_old, "stale": stale,
            "note": a.get("note"), "years": out}


# 업데이트 알림 대상 — 경제지표 발표/수정 (일별 시장지표 제외, 노이즈 방지)
RELEASE_KEYS = {"cpi_yoy", "core_cpi_yoy", "unemployment", "payrolls", "fed_funds",
                "consumer_sent", "m2_yoy", "cli_us", "oil_yoy", "cape",
                "ism_pmi", "cnn_fng", "aaii_spread", "put_call", "cta_pos", "retail_alloc", "kr_deposit"}
# 미래 추정·nowcast 지표(실제 발표 데이터와 구분 표기)
FORWARD_KEYS = {"gdpnow", "citi_surprise"}


def load_prev():
    """직전 macro-data.js 로드(업데이트 diff용). 없으면 {}."""
    try:
        if OUT.exists():
            t = OUT.read_text(encoding="utf-8")
            i, j = t.find("{"), t.rfind("}")
            return json.loads(t[i:j + 1])
    except Exception:
        pass
    return {}


def build_updates(indicators, prev, cycle, regime_label, regime_score, kr_ts, today_iso):
    """직전 대비 변경분 → 업데이트 로그 누적 + 오늘 이벤트."""
    prev_ind = prev.get("indicators", {})
    log = list(prev.get("update_log", []))
    seed = not log  # 첫 실행이면 최신 발표치로 시드
    seen = set((e.get("date"), e.get("type"), e.get("key")) for e in log)
    events = []

    def add(ev):
        eid = (ev["date"], ev["type"], ev.get("key"))
        if eid in seen:
            return
        seen.add(eid); events.append(ev)

    for k, d in indicators.items():
        if k not in RELEASE_KEYS:
            continue
        u = d.get("unit", "")
        pd = prev_ind.get(k)
        if seed:
            add({"date": today_iso, "type": "release", "key": k, "title": d["name"],
                 "detail": f"최근 발표 {d['current']}{u} ({d.get('as_of')})", "as_of": d.get("as_of")})
        elif pd is None:
            add({"date": today_iso, "type": "release", "key": k, "title": d["name"],
                 "detail": f"신규 {d['current']}{u} ({d.get('as_of')})", "as_of": d.get("as_of")})
        elif pd.get("as_of") != d.get("as_of"):
            add({"date": today_iso, "type": "release", "key": k, "title": d["name"],
                 "detail": f"{pd.get('current')}{u} → {d['current']}{u} ({d.get('as_of')} 발표)", "as_of": d.get("as_of")})
        elif pd.get("current") != d.get("current"):
            add({"date": today_iso, "type": "revision", "key": k, "title": d["name"],
                 "detail": f"{pd.get('current')}{u} → {d['current']}{u} (수정)", "as_of": d.get("as_of")})

    pc = (prev.get("cycle") or {}).get("phase")
    if cycle and pc and pc != cycle.get("phase"):
        add({"date": today_iso, "type": "cycle", "key": "cycle", "title": "경기국면 변경",
             "detail": f"{pc} → {cycle['phase']}"})
    pl = (prev.get("regime") or {}).get("label")
    if pl and pl != regime_label:
        add({"date": today_iso, "type": "regime", "key": "regime", "title": "레짐 국면 변경",
             "detail": f"{pl} → {regime_label} ({regime_score:+d})"})
    if kr_ts and kr_ts.get("latest"):
        lt = kr_ts["latest"]; ld = lt.get("date")
        pkr = ((prev.get("kr_flows_ts") or {}).get("latest") or {}).get("date")
        if ld and ld != pkr:
            yt = kr_ts.get("ytd_total", {})
            add({"date": today_iso, "type": "flows", "key": "krflow_" + ld, "title": "한국 투자자 수급 갱신",
                 "detail": f"외국인 {ld} {lt['foreign']:+g}조 · YTD누적 {yt.get('foreign')}조"})

    log = (log + events)[-60:]
    return log, events


def build_ai():
    """AI 섹션(6): 하이퍼스케일러 CAPEX, capex/GDP·R&D/GDP 버블점검, AI 랩 매출추정."""
    years = sorted(next(iter(AI_CAPEX.values())).keys())
    companies, totals = [], {}
    for name, d in AI_CAPEX.items():
        ser = [{"y": int(y), "capex": d[y], "est": int(y) > AI_CAPEX_ACTUAL_THROUGH} for y in years]
        companies.append({"name": name, "years": ser})
        for y in years:
            totals[y] = totals.get(y, 0) + d[y]
    total_series = [{"y": int(y), "capex": totals[y], "est": int(y) > AI_CAPEX_ACTUAL_THROUGH} for y in years]
    # 미국 명목 GDP (FRED) → 연도별 capex/GDP 시계열 (버블 게이지)
    gdp_by_year, gdp = {}, None
    try:
        gd, gv = fred_csv("GDP")  # 분기 명목 $B SAAR
        by = {}
        for dd, vv in zip(gd, gv):
            by.setdefault(dd[:4], []).append(vv)
        gdp_by_year = {y: sum(a) / len(a) for y, a in by.items()}  # 연평균
        if gdp_by_year:
            gdp = gdp_by_year[max(gdp_by_year)]
    except Exception:
        pass
    if not gdp_by_year:  # FRED throttle 시 seed 사용
        gdp_by_year = GDP_ANNUAL_SEED.copy()
        gdp = gdp_by_year[max(gdp_by_year)]
    last = str(AI_CAPEX_ACTUAL_THROUGH)
    # 전망연도 GDP는 최신 실측에서 연 4% 명목성장 외삽
    def gdp_for(y):
        yi = int(y)
        if str(yi) in gdp_by_year:
            return gdp_by_year[str(yi)]
        if gdp_by_year:
            base_y = max(int(k) for k in gdp_by_year)
            return gdp_by_year[str(base_y)] * (1.04 ** (yi - base_y))
        return None
    capex_gdp_series = []
    for y in years:
        g = gdp_for(y)
        if g:
            capex_gdp_series.append({"y": int(y), "pct": round(totals[y] / g * 100, 2), "est": int(y) > AI_CAPEX_ACTUAL_THROUGH})
    capex_gdp = round(totals[last] / gdp * 100, 2) if gdp else None
    capex_gdp_e = round(totals[str(AI_CAPEX_ACTUAL_THROUGH + 1)] / gdp_for(AI_CAPEX_ACTUAL_THROUGH + 1) * 100, 2) if gdp else None
    rnd = [{"y": int(y), "pct": AI_RND_GDP[y]} for y in sorted(AI_RND_GDP)]
    labs = []
    for name, d in AI_LABS.items():
        rev = [{"y": int(y), "rev": d["rev"][y], "est": int(y) > 2025} for y in sorted(d["rev"])]
        labs.append({"name": name, "rev": rev, "profit_note": d["profit_note"], "source": d["source"]})
    # 빅4 재무 (매출/영업이익/FCF/시총)
    at = AI_CAPEX_ACTUAL_THROUGH
    def ser(d, metric):
        return [{"y": int(y), "v": d[metric][y], "est": int(y) > at} for y in sorted(d[metric])]
    fin = []
    for name in ["Microsoft", "Alphabet", "Amazon", "Meta"]:
        d = AI_FINANCIALS[name]
        fin.append({"name": name, "rev": ser(d, "rev"), "opinc": ser(d, "opinc"),
                    "fcf": ser(d, "fcf"), "mktcap": [{"y": int(y), "v": d["mktcap"][y]} for y in sorted(d["mktcap"])]})
    # capex/매출 강도 (클라우드 사이클 비교)
    intensity = []
    for y in years:
        tot_rev = sum(AI_FINANCIALS[c]["rev"].get(y, 0) for c in AI_FINANCIALS)
        if tot_rev > 0:
            intensity.append({"y": int(y), "pct": round(totals[y] / tot_rev * 100, 1), "est": int(y) > at})
    print(f"  [AI] CAPEX {last} 합계 ${totals[last]}B, capex/GDP {capex_gdp}% (GDP ${gdp}B), capex/매출 {intensity[-1]['pct'] if intensity else 'NA'}%")
    return {"as_of": AI_AS_OF, "capex": {"companies": companies, "total": total_series,
            "actual_through": AI_CAPEX_ACTUAL_THROUGH},
            "capex_gdp_pct": capex_gdp, "capex_gdp_pct_e": capex_gdp_e,
            "capex_gdp_series": capex_gdp_series,
            "total_capex_last": totals[last], "total_capex_e": totals[str(AI_CAPEX_ACTUAL_THROUGH + 1)],
            "last_actual_year": AI_CAPEX_ACTUAL_THROUGH, "gdp": round(gdp) if gdp else None,
            "rnd_gdp": rnd, "labs": labs, "financials": fin,
            "capex_intensity": intensity, "cloud_note": CLOUD_CYCLE_NOTE,
            "fcf_note": AI_FCF_NOTE,
            "capex_source": AI_CAPEX_SOURCE}


def cycle_phase(vals):
    """CLI 시계열 → 경기국면(4단계)."""
    if not vals or len(vals) < 7:
        return None
    cur = vals[-1]
    rising = (cur - vals[-7]) > 0
    above = cur >= 100
    if above and rising:
        return {"phase": "확장 (Expansion)", "cls": "strong-pos",
                "desc": "선행지수 추세 상회 + 상승. 위험자산·경기민감(시클리컬·반도체) 우호."}
    if above and not rising:
        return {"phase": "둔화·후기 (Late-cycle)", "cls": "neu",
                "desc": "추세 상회하나 모멘텀 둔화. 퀄리티·방어주 비중 점검, 후기 사이클."}
    if (not above) and (not rising):
        return {"phase": "수축 (Contraction)", "cls": "neg",
                "desc": "추세 하회 + 하락. 방어적 포지션·현금비중↑, 듀레이션(국채) 점검."}
    return {"phase": "회복 (Recovery)", "cls": "pos",
            "desc": "추세 하회하나 반등. 바닥 통과 가능성 — 선제적 리스크온 점검."}


# ── 국가 선호도 설정 ──────────────────────────────────────────────────────
COUNTRY_PREF_CFG = {
    "US": {"name": "미국", "cli": "USALOLITOAASTSAM", "fx": None, "fx_invert": False, "mon_note": "Fed 동결·인하 지연(제약적)"},
    "KR": {"name": "한국", "cli": "KORLOLITOAASTSAM", "fx": "DEXKOUS", "fx_invert": True, "mon_note": "BOK 동결·완화 여지"},
    "EU": {"name": "유럽", "cli": None, "fx": "DEXUSEU", "fx_invert": False, "mon_note": "ECB 완화 사이클(+)"},
    "JP": {"name": "일본", "cli": "JPNLOLITOAASTSAM", "fx": "DEXJPUS", "fx_invert": True, "mon_note": "BOJ 정상화(긴축, −)"},
    "CN": {"name": "중국", "cli": "CHNLOLITOAASTSAM", "fx": "DEXCHUS", "fx_invert": True, "mon_note": "인민은행 부양(+)"},
}
COUNTRY_FAIR_PE = {"US": 19.0, "KR": 11.0, "EU": 14.0, "JP": 15.0, "CN": 13.0}
COUNTRY_VAL_PE_SEED = {"EU": 14.5, "JP": 15.0, "CN": 11.0}  # US/KR은 라이브
MON_SEED = {"US": -0.1, "KR": 0.1, "EU": 0.3, "JP": -0.4, "CN": 0.3}
PREF_WEIGHTS = {
    "m1":  {"fx": 0.35, "earn": 0.30, "cycle": 0.20, "mon": 0.15, "val": 0.00},
    "m3":  {"earn": 0.25, "cycle": 0.25, "fx": 0.20, "val": 0.15, "mon": 0.15},
    "m12": {"val": 0.30, "earn": 0.25, "cycle": 0.20, "mon": 0.15, "fx": 0.10},
}


def _fred_chg(series_id, months):
    """(최신값, N개월 변화량). 실패 시 (None, None)."""
    try:
        d, v = fred_csv(series_id)
        me = to_month_end(d, v); ks = sorted(me)
        if len(ks) < months + 1:
            return (me[ks[-1]], None) if ks else (None, None)
        return me[ks[-1]], me[ks[-1]] - me[ks[-1 - months]]
    except Exception:
        return None, None


# 환율: yfinance 통화쌍 (FRED 차단 무관). sign: USD 기준쌍은 -1(통화약세→음), EURUSD는 +1.
FX_YF = {"KR": ("KRW=X", -1), "JP": ("JPY=X", -1), "EU": ("EURUSD=X", 1), "CN": ("CNY=X", -1)}


def _yf_fx_3m(ticker):
    """yfinance 통화쌍 3개월 변화율(%). (최신값, pct) 또는 (None, None)."""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="4mo")["Close"].dropna()
        if len(h) < 50:
            return None, None
        cur = float(h.iloc[-1])
        ago = float(h.iloc[-63]) if len(h) >= 63 else float(h.iloc[0])
        if ago <= 0:
            return None, None
        return round(cur, 2), round((cur / ago - 1) * 100, 1)
    except Exception:
        return None, None


# BIS 실질실효환율(REER, broad) — 통화 밸류에이션. 10년 평균 대비 괴리로 저평가/고평가 측정.
REER_FRED = {"US": "RBUSBIS", "KR": "RBKRBIS", "EU": "RBXMBIS", "JP": "RBJPBIS", "CN": "RBCNBIS"}
FX12_KRW = {"US": "KRW=X", "EU": "EURKRW=X", "JP": "JPYKRW=X"}  # 대KRW 12M 모멘텀. CN은 크로스


def _yf_12m_chg(ticker):
    """yfinance 12개월 변화율(%). 실패 시 None."""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period="13mo")["Close"].dropna()
        if len(h) < 150:
            return None
        return round((float(h.iloc[-1]) / float(h.iloc[0]) - 1) * 100, 1)
    except Exception:
        return None


def build_country_pref(earn, bench):
    """국가 선호도: 밸류·이익·환율·통화정책·경기 종합 → 1·3·12개월 점수."""
    print("=== 국가 선호도 ===")
    us_pe = (bench.get("S&P 500", {}).get("valuation") or {}).get("pe")
    kr_pe = (bench.get("KOSPI", {}).get("valuation") or {}).get("pe")
    out = {}
    for cc, cfg in COUNTRY_PREF_CFG.items():
        pe = us_pe if cc == "US" else kr_pe if cc == "KR" else COUNTRY_VAL_PE_SEED.get(cc)
        fair = COUNTRY_FAIR_PE[cc]
        val = clamp((fair - pe) / (fair * 0.3)) if pe else 0.0
        ec = earn.get("countries", {}).get(cc, {})
        err, rev = ec.get("err"), ec.get("rev30")
        earn_s = clamp((err or 0) * 1.3) * 0.6 + clamp((rev or 0) / 8.0) * 0.4
        # 환율 모멘텀 (통화 강세 = +) — yfinance (FRED 차단과 무관). 미국=USD 기준이라 0.
        fx_s, fx_chg, fx_val = 0.0, None, None
        yf_fx = FX_YF.get(cc)
        if yf_fx:
            last, pct3 = _yf_fx_3m(yf_fx[0])
            if pct3 is not None and last is not None:
                strength = yf_fx[1] * pct3   # sign 으로 통화강세(+)/약세(−) 처리
                fx_chg, fx_s, fx_val = round(strength, 1), clamp(strength / 5.0), round(last, 2)
        mon_s = MON_SEED.get(cc, 0.0)
        # 경기 — 1순위 FRED CLI, 실패/미설정 시 이익성장(growth_cy) 프록시(비-가격 펀더멘털)
        cyc_s, cli_now, phase = 0.0, None, None
        if cfg["cli"]:
            try:
                d, v = fred_csv(cfg["cli"]); me = to_month_end(d, v)
                ks = sorted(me); vals = [me[k] for k in ks]
                if vals:
                    cli_now = round(vals[-1], 1)
                    chg3 = vals[-1] - vals[-4] if len(vals) >= 4 else 0
                    cyc_s = clamp((vals[-1] - 100) / 1.5 * 0.6 + clamp(chg3 / 0.4) * 0.4)
                    cp = cycle_phase(vals); phase = cp["phase"] if cp else None
            except Exception:
                pass
        if cli_now is None:   # FRED CLI 실패/미설정 → 이익성장 프록시
            g = ec.get("growth_cy")
            if g is not None:
                cyc_s = clamp((g - 12.0) / 18.0)  # ~12% 추세 기준 정규화
                phase = ("확장 (Expansion)" if g >= 13 else
                         "수축 (Contraction)" if g <= 4 else "둔화 (Slowdown)") + "*"
        # ── Currency 3요소 소스 (weekly/country_model.py가 소비) ──
        # REER 밸류: BIS 실질실효환율의 10년 평균 대비 괴리(%). 음수=저평가.
        reer = None
        try:
            _, rv_ = fred_csv(REER_FRED[cc], start="2015-01-01")
            if rv_:
                m10 = sum(rv_) / len(rv_)
                reer = {"cur": round(rv_[-1], 1), "avg10y": round(m10, 1),
                        "dev_pct": round((rv_[-1] / m10 - 1) * 100, 1)}
        except Exception:
            pass
        # 대KRW 12개월 FX 모멘텀(%): KRW 투자자의 무헤지 환수익 방향. KR=0(home).
        fx12 = 0.0 if cc == "KR" else None
        if cc in FX12_KRW:
            fx12 = _yf_12m_chg(FX12_KRW[cc])
        elif cc == "CN":
            a, b = _yf_12m_chg("KRW=X"), _yf_12m_chg("CNY=X")
            if a is not None and b is not None:
                fx12 = round(a - b, 1)   # CNYKRW ≈ USDKRW / USDCNY
        comp = {"val": round(val * 100), "earn": round(earn_s * 100), "fx": round(fx_s * 100),
                "mon": round(mon_s * 100), "cycle": round(cyc_s * 100)}
        horizon = {h: round(sum(comp[k] * w for k, w in wts.items())) for h, wts in PREF_WEIGHTS.items()}
        out[cc] = {"name": cfg["name"], "pe": round(pe, 1) if pe else None, "fair_pe": fair,
                   "components": comp, "horizon": horizon, "fx_val": fx_val, "fx_chg": fx_chg,
                   "reer": reer, "fx12m": fx12,
                   "cli": cli_now, "phase": phase, "mon_note": cfg["mon_note"]}
        print(f"  {cfg['name']}: 1M {horizon['m1']:+d} 3M {horizon['m3']:+d} 12M {horizon['m12']:+d} "
              f"(val {comp['val']:+d} earn {comp['earn']:+d} fx {comp['fx']:+d} cyc {comp['cycle']:+d})")
    return out


HIST_PILLAR_KEYS = {
    "macro": ["cpi_yoy", "core_cpi_yoy", "unemployment", "payrolls", "fed_funds", "consumer_sent",
              "yield_curve", "cli_us", "oil_yoy", "t10y3m", "cfnai", "sahm", "copper_gold"],
    "valuation": ["cape", "us10y"],
    "flows": ["m2_yoy", "baa_spread", "usdkrw", "nfci"],   # hy_oas는 FRED가 최근 3년만 제공(ICE 라이선스) → 제외
    "sentiment": ["vix", "spx_mom"],   # move는 야후 히스토리 얕아 타임머신 제외
    "earnings": ["spx_eps_yoy"],
}
HIST_WEIGHTS = {"macro": 0.24, "valuation": 0.20, "flows": 0.18, "sentiment": 0.18, "earnings": 0.20}


def _fwd_ret(me, ym, n):
    """me(월말 dict) ym 시점 → n개월 후 수익률(%)."""
    y, mo = int(ym[:4]), int(ym[5:7])
    tot = mo + n
    tkey = f"{y + (tot - 1) // 12:04d}-{(tot - 1) % 12 + 1:02d}"
    if ym in me and tkey in me and me[ym] > 0:
        return round((me[tkey] / me[ym] - 1) * 100, 1)
    return None


def build_regime_history(monthly, spx_me, kospi_me, max_months=192):
    """과거 월별 레짐(5축, 이익은 S&P EPS YoY 프록시) + 경기국면 + 당시 주가·이후수익률."""
    core_me = monthly.get("core_cpi_yoy", {})
    # 교집합은 비-이익 축으로만(이익 프록시는 보고지연 → carry-forward로 처리)
    core_keys = [k for p, ks in HIST_PILLAR_KEYS.items() if p != "earnings"
                 for k in ks if k in monthly and len(monthly[k]) >= 24]
    if len(core_keys) < 8:
        return []
    sets = [set(monthly[k].keys()) for k in core_keys]
    inter = sorted(set.intersection(*sets))
    if not inter:
        return []
    # 시작월(전 지표 존재)~최신월(가장 최근 데이터)까지 월 시퀀스 — 늦게 발표되는
    # 지표(CLI·CPI 등)는 carry-forward(kk<=mo)로 채워 5·6월 등 최근월도 포함.
    latest = max(max(monthly[k]) for k in core_keys)
    if spx_me:
        latest = max(latest, max(spx_me))
    common, y, m = [], int(inter[0][:4]), int(inter[0][5:7])
    while f"{y:04d}-{m:02d}" <= latest:
        common.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1; y += 1
    common = common[-max_months:]
    out = []
    for mo in common:
        pil = {}
        for pillar, keys in HIST_PILLAR_KEYS.items():
            scores = []
            for k in keys:
                if k not in monthly:
                    continue
                ks = sorted(kk for kk in monthly[k] if kk <= mo)  # mo 이전 최신값까지 (carry-forward)
                if len(ks) < 4:
                    continue
                vals = [monthly[k][kk] for kk in ks]
                ctx = {}
                if k == "consumer_sent":
                    ctx["z"] = zscore(vals)[0]
                elif k == "fed_funds":
                    cc = core_me.get(mo)
                    ctx["real_rate"] = (vals[-1] - cc) if cc is not None else None
                elif k == "spx_mom":
                    sks = sorted(kk for kk in spx_me if kk <= mo)
                    if len(sks) >= 10:
                        ctx["above_200d"] = spx_me[sks[-1]] > sum(spx_me[kk] for kk in sks[-10:]) / 10
                scores.append(score_indicator(k, vals[-1], vals, ctx))
            pil[pillar] = round(sum(scores) / len(scores) * 100) if scores else 0
        comp = round(sum(pil[p] * HIST_WEIGHTS[p] for p in HIST_WEIGHTS))
        phase = None
        if "cli_us" in monthly:
            cks = sorted(kk for kk in monthly["cli_us"] if kk <= mo)
            cp = cycle_phase([monthly["cli_us"][kk] for kk in cks])
            phase = cp["phase"] if cp else None
        out.append({"date": mo + "-01", "score": comp, "phase": phase, "pillars": pil,
                    "spx": round(spx_me[mo], 1) if mo in spx_me else None,
                    "kospi": round(kospi_me[mo], 1) if mo in kospi_me else None,
                    "fwd": {"spx1": _fwd_ret(spx_me, mo, 1), "spx3": _fwd_ret(spx_me, mo, 3),
                            "spx12": _fwd_ret(spx_me, mo, 12), "kospi1": _fwd_ret(kospi_me, mo, 1),
                            "kospi3": _fwd_ret(kospi_me, mo, 3), "kospi12": _fwd_ret(kospi_me, mo, 12)}})
    return out


def _zseries(me):
    """월말 dict {ym: val} → 전 히스토리 z-score dict {ym: z}. 표본<24면 {}."""
    ks = sorted(me)
    vals = [me[k] for k in ks]
    if len(vals) < 24:
        return {}
    mean = sum(vals) / len(vals)
    sd = (sum((x - mean) ** 2 for x in vals) / len(vals)) ** 0.5 or 1.0
    return {k: (me[k] - mean) / sd for k in ks}


# Investment Clock 4국면 (Merrill Lynch "The Investment Clock", 2004)
QUADRANT_PHASES = {
    ("up", "down"):   {"name": "회복 (Recovery)", "cls": "strong-pos",
                       "assets": "주식(성장주) > 회사채 > 국채 > 원자재",
                       "desc": "성장 개선 + 인플레 하락 = 골디락스. 마진 확대·멀티플 상승 동시 진행 — 주식 최선호 국면."},
    ("up", "up"):     {"name": "과열 (Overheat)", "cls": "pos",
                       "assets": "원자재 > 주식(가치·시클리컬) > 현금 > 채권",
                       "desc": "성장·인플레 동반 상승. 원자재·시클리컬·가치주 우위, 금리 상승으로 장기채·성장주 부담."},
    ("down", "up"):   {"name": "스태그플레이션 (Stagflation)", "cls": "neg",
                       "assets": "현금 > 원자재 > 채권 > 주식",
                       "desc": "성장 둔화 + 인플레 상승 — 주식에 최악의 조합. 현금·방어주 중심, 정책 대응 여력 제한."},
    ("down", "down"): {"name": "디스인플레 둔화 (Reflation)", "cls": "neu",
                       "assets": "국채 > 회사채 > 주식(퀄리티·방어) > 원자재",
                       "desc": "성장·인플레 동반 하락. 금리 인하 사이클 — 듀레이션(국채) 최선호, 주식은 퀄리티·방어 중심."},
}


def build_quadrant(monthly):
    """성장×인플레 4국면 (Investment Clock, Merrill Lynch 2004 · Bridgewater 프레임워크).

    성장 컴포지트 = mean z(CFNAI-MA3, 고용 3MMA, OECD CLI, 구리/금)
    인플레 컴포지트 = mean z(근원CPI YoY, 헤드라인CPI YoY, 유가 YoY)
    축 = 각 컴포지트의 3개월 모멘텀(Δ) → 사분면 판정 + 최근 13개월 궤적.
    """
    # 고용은 변동 큰 mom 값 → 3개월 이동평균 전처리
    pay = monthly.get("payrolls", {})
    pay3 = {}
    ks = sorted(pay)
    for i in range(2, len(ks)):
        pay3[ks[i]] = (pay[ks[i]] + pay[ks[i - 1]] + pay[ks[i - 2]]) / 3
    growth_in = {"cfnai": monthly.get("cfnai", {}), "payrolls": pay3,
                 "cli_us": monthly.get("cli_us", {}), "copper_gold": monthly.get("copper_gold", {})}
    infl_in = {"core_cpi_yoy": monthly.get("core_cpi_yoy", {}), "cpi_yoy": monthly.get("cpi_yoy", {}),
               "oil_yoy": monthly.get("oil_yoy", {})}
    gz = {k: _zseries(v) for k, v in growth_in.items() if v}
    iz = {k: _zseries(v) for k, v in infl_in.items() if v}
    gz = {k: v for k, v in gz.items() if v}
    iz = {k: v for k, v in iz.items() if v}
    if len(gz) < 2 or len(iz) < 2:
        return None

    def composite(zs):
        months = sorted(set().union(*[set(z.keys()) for z in zs.values()]))
        comp = {}
        for mo in months:
            xs = []
            for z in zs.values():
                mk = [k for k in z if k <= mo]
                if mk:                      # carry-forward: 발표 지연 지표는 직전값
                    xs.append(z[max(mk)])
            if len(xs) >= 2:
                comp[mo] = sum(xs) / len(xs)
        return comp

    cg, ci = composite(gz), composite(iz)
    common = sorted(set(cg) & set(ci))
    if len(common) < 16:
        return None
    trail = []
    for mo in common[-13:]:
        idx = common.index(mo)
        if idx < 3:
            continue
        p3 = common[idx - 3]
        trail.append({"ym": mo, "g": round(cg[mo] - cg[p3], 2), "i": round(ci[mo] - ci[p3], 2)})
    if not trail:
        return None
    last = trail[-1]
    key = ("up" if last["g"] >= 0 else "down", "up" if last["i"] >= 0 else "down")
    phase = QUADRANT_PHASES[key]
    return {"axes": {"x": "성장 모멘텀 (컴포지트 3개월Δ)", "y": "인플레 모멘텀 (컴포지트 3개월Δ)"},
            "trail": trail,
            "level": {"g": round(cg[common[-1]], 2), "i": round(ci[common[-1]], 2)},
            "phase": phase,
            "inputs": {"growth": sorted(gz.keys()), "inflation": sorted(iz.keys())},
            "as_of": common[-1],
            "note": "Merrill Lynch Investment Clock(2004) 프레임워크. 성장=CFNAI·고용·CLI·구리/금, "
                    "인플레=근원/헤드라인CPI·유가. 각 축은 z-컴포지트의 3개월 변화."}


def build_recession(monthly):
    """침체확률 대시보드 — 독립 4신호 병렬.

    1) NY Fed probit (Estrella-Mishkin 1998): 10Y-3M 스프레드 → 12개월 내 침체확률
    2) Sahm Rule (Sahm 2019, FRED 실시간)
    3) Chauvet-Piger 마코프 스위칭 확률 (RECPROUSM156N)
    4) CFNAI-MA3 (시카고연준, -0.7 = 침체 임계)
    """
    sig = []

    def add(key, name, val, unit, status, thr, desc, src_id):
        lbl = {"safe": "안전", "watch": "주의", "alert": "경고"}[status]
        sig.append({"key": key, "name": name, "value": val, "unit": unit,
                    "status": status, "status_ko": lbl, "threshold": thr, "desc": desc,
                    "source": {"name": f"FRED: {src_id}" if src_id else "derived",
                               "url": f"https://fred.stlouisfed.org/series/{src_id}" if src_id else None}})

    t = monthly.get("t10y3m", {})
    if t:
        s = t[max(t)]
        p = round(0.5 * (1 + math.erf((-0.5333 - 0.6330 * s) / math.sqrt(2))) * 100, 1)
        st = "safe" if p < 15 else ("watch" if p < 30 else "alert")
        add("probit", "NY Fed 수익률곡선 모델", p, "%", st, "30% 이상 경고",
            f"10Y-3M 스프레드 {s:+.2f}%p 기반 12개월 내 침체확률(Estrella-Mishkin probit). "
            "역사상 30% 돌파 시 대부분 침체 선행.", "T10Y3M")

    sm = monthly.get("sahm", {})
    if sm:
        v = round(sm[max(sm)], 2)
        st = "safe" if v < 0.2 else ("watch" if v < 0.5 else "alert")
        add("sahm", "Sahm Rule", v, "%p", st, "0.50%p = 침체 트리거",
            "실업률 3개월평균이 12개월 저점 대비 얼마나 상승했는지. "
            "0.5%p 이상이면 침체가 이미 시작됐다는 실시간 신호(1970년 이후 무오류).", "SAHMREALTIME")

    try:
        d, v = fred_csv("RECPROUSM156N")
        if v:
            cp = round(v[-1], 1)
            st = "safe" if cp < 20 else ("watch" if cp < 80 else "alert")
            add("chauvet", "Chauvet-Piger 확률", cp, "%", st, "80% 이상 = 침체 판정",
                "마코프 스위칭 동적요인 모델의 현재 침체확률. 80% 이상 3개월 지속 시 "
                "침체로 판정하는 학계 표준(Chauvet & Piger 2008).", "RECPROUSM156N")
    except Exception as e:
        print(f"  [err] Chauvet-Piger: {e}")

    cf = monthly.get("cfnai", {})
    if cf:
        v = round(cf[max(cf)], 2)
        st = "safe" if v > -0.35 else ("watch" if v > -0.7 else "alert")
        add("cfnai", "CFNAI-MA3", v, "", st, "-0.70 이하 = 침체 임계",
            "85개 실물지표 합성(3개월 평균). 0=추세성장. -0.7 이하는 침체 국면 진입 신호"
            "(시카고연준 공식 기준).", "CFNAI")

    if not sig:
        return None
    n_alert = sum(1 for s in sig if s["status"] == "alert")
    n_watch = sum(1 for s in sig if s["status"] == "watch")
    if n_alert >= 2:
        verdict = {"label": "침체 경고", "cls": "neg",
                   "desc": f"4개 독립 신호 중 {n_alert}개 경고 — 방어 포지션 강화 필요."}
    elif n_alert == 1 or n_watch >= 2:
        verdict = {"label": "주의 관찰", "cls": "neu",
                   "desc": f"경고 {n_alert}·주의 {n_watch} — 단일 신호는 오탐 있음, 조합 악화 여부 추적."}
    else:
        d = ("독립 신호 모두 안전권" if n_watch == 0
             else f"경고 없음 · 주의 {n_watch}개 — 대체로 안전권")
        verdict = {"label": "침체 신호 없음", "cls": "pos",
                   "desc": d + ". 경기 연착륙/확장 시나리오 유지."}
    return {"signals": sig, "verdict": verdict,
            "note": "서로 다른 방법론(수익률곡선·노동시장·마코프모델·실물합성)의 독립 신호를 병렬 표시. "
                    "단일 모델 과신 방지 목적."}


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
                "holdings": build_holdings(agg["rows"]) if agg else [],
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


def load_kr_deposit():
    """kr_deposit.json(네이버 증시자금추이) → dict 또는 None."""
    f = HERE / "kr_deposit.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def _deposit_series():
    kd = load_kr_deposit()
    if kd and kd.get("deposit", {}).get("values"):
        return kd["deposit"]   # 실측(네이버 일별)
    ks = sorted(KR_DEPOSIT_SERIES)
    return {"dates": [k + "-01" for k in ks], "values": [KR_DEPOSIT_SERIES[k] for k in ks]}


def load_kr_flows():
    """kr_flows.json → (MANUAL_FLOWS 패치본, 시계열 dict)."""
    f = HERE / "kr_flows.json"
    flows = dict(MANUAL_FLOWS)
    kd = load_kr_deposit()
    dep_ser = _deposit_series()
    ts = {"deposit": dep_ser,
          "deposit_source": ("네이버 증시자금추이(실측)" if kd else "KOFIA freesis(근사·편집)")}
    # 예탁금 지표 현재값을 실측으로 갱신
    if kd and kd.get("current", {}).get("deposit") is not None:
        dme = to_month_end(dep_ser["dates"], dep_ser["values"]); mk = sorted(dme)
        dhist = {"dates": [k + "-01" for k in mk], "values": [round(dme[k], 1) for k in mk]}
        flows["kr_deposit"] = {**MANUAL_FLOWS["kr_deposit"], "current": kd["current"]["deposit"],
            "as_of": kd["current"].get("as_of", kd.get("as_of")), "history": dhist,
            "source": {"name": "네이버 증시자금추이", "url": kd.get("source_url")},
            "note": f"증시 대기자금(고객예탁금). 신용잔고 {kd['current'].get('credit')}조 동반. "
                    f"자동수집(네이버 증시자금추이). 예탁금 증가=매수 여력 확대. 카드 클릭→누적 추이."}
    if not f.exists():
        return flows, ts
    try:
        kr = json.loads(f.read_text(encoding="utf-8"))
        m = kr["mtd"]; lt = kr["latest"]; fo = m["foreign"]
        flows["kr_flows"] = {**MANUAL_FLOWS["kr_flows"], "current": fo, "as_of": kr["as_of"],
            "note": f"{kr['month']} KOSPI 누적(조원): 외국인 {fo:+.1f}·기관 {m['inst']:+.1f}·개인 {m['retail']:+.1f}"
                    f"({m['days']}일). 최근 {lt['date']}: 외국인 {lt['foreign']:+.2f}·기관 {lt['inst']:+.2f}·개인 {lt['retail']:+.2f}. "
                    f"외인 순매도를 개인·기관(연기금·ETF)이 흡수하는 구조. 자동수집(네이버 금융)."}
        if kr.get("deposit"):
            flows["kr_deposit"] = {**MANUAL_FLOWS["kr_deposit"], "current": kr["deposit"], "as_of": kr["as_of"]}
        ts.update({"as_of": kr["as_of"], "month": kr.get("month"), "unit": "조원",
                   "ytd_total": kr.get("ytd_total"), "mtd": m, "latest": lt,
                   "ytd_cum": kr.get("ytd_cum"), "month_daily": kr.get("month_daily"),
                   "source": "네이버 금융", "source_url": MANUAL_URLS.get("kr_flows")})
    except Exception as e:
        print(f"  [warn] kr_flows.json 로드 실패: {e}")
    return flows, ts


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
    kosdaq_dates, kosdaq_vals = [], []
    try:
        kosdaq_dates, kosdaq_vals = yf_monthly("^KQ11")
        print(f"  [ok] KOSDAQ 월간 {len(kosdaq_vals)}개")
    except Exception as e:
        print(f"  [err] KOSDAQ: {e}")

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
            elif transform == "benchlvl":
                # benchmarks.js(yfinance, cron 안정 갱신)에서 직접 — FRED 차단 무관 항상 최신
                bi = bench.get(src) or {}
                bh = bi.get("history") or {}
                bd, bv = bh.get("dates", []), list(bh.get("values", []))
                if bv:
                    dates, vals = downsample_monthly(bd, bv)
                    # 최신 current를 마지막 값으로, 날짜는 실제 최신일로 보정
                    if bi.get("current") is not None:
                        if dates:
                            vals[-1] = round(bi["current"], 4)
                            dates[-1] = bi.get("as_of", dates[-1])
                        else:
                            dates, vals = [bi.get("as_of", today.isoformat())], [round(bi["current"], 4)]
            elif transform == "oilyoy":
                d, v = fred_csv(src)
                me = to_month_end(d, v); keys = sorted(me)
                for k in keys:
                    y, m = int(k[:4]), int(k[5:7])
                    pk = f"{y-1:04d}-{m:02d}"
                    if pk in me and me[pk] > 0:
                        dates.append(k + "-01"); vals.append((me[k] / me[pk] - 1) * 100)
            elif transform == "ma3":
                # 월간 시계열 → 3개월 이동평균 (CFNAI-MA3 등 공식 지표 규격)
                d, v = fred_csv(src)
                me = to_month_end(d, v); ks = sorted(me)
                dates = [k + "-01" for k in ks[2:]]
                vals = [(me[ks[i]] + me[ks[i - 1]] + me[ks[i - 2]]) / 3 for i in range(2, len(ks))]
            elif transform == "yfmo":
                # yfinance 월간 종가. 월간 히스토리 미지원 티커(^MOVE 등)는 일별 2y 폴백
                dates, vals = yf_monthly(src)
                if len(vals) < 3:
                    import yfinance as yf
                    h = yf.Ticker(src).history(period="2y")["Close"].dropna()
                    if len(h):
                        dd = [ts.strftime("%Y-%m-%d") for ts in h.index]
                        dates, vals = downsample_monthly(dd, [float(x) for x in h.values])
            elif transform == "cugd":
                # 구리/금 비율 (×1000 스케일): 실물수요 vs 안전선호
                cd, cv = yf_monthly("HG=F"); gd, gv = yf_monthly("GC=F")
                cme, gme = to_month_end(cd, cv), to_month_end(gd, gv)
                ks = [k for k in sorted(set(cme) & set(gme)) if gme[k]]
                dates = [k + "-01" for k in ks]
                vals = [round(cme[k] / gme[k] * 1000, 3) for k in ks]
            elif transform == "multpl":
                dates, vals = fetch_multpl(src)
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
            "z_from": dates[0][:7] if z is not None else None,   # z-score 기준 시작월
            "z_n": len(vals) if z is not None else None,         # z-score 표본 수(월)
            "kind": "forward" if key in FORWARD_KEYS else "release",
            "source": indicator_source(key, src, transform),
        }

    # --- 수동 지표 (센티먼트 MANUAL + 수급 MANUAL_FLOWS, 한국 수급은 자동 패치) ---
    # CNN 공포·탐욕 지수는 CNN 엔드포인트에서 자동 조회, 실패 시 시드값 유지(fail-safe).
    sent_manual = dict(MANUAL)
    fng = fetch_cnn_fng()
    if fng:
        seed = MANUAL["cnn_fng"]
        sent_manual["cnn_fng"] = {**seed, "current": fng["current"],
                                  "prev": fng["prev"], "as_of": fng["as_of"]}
        print(f"  [ok] CNN F&G {fng['current']} (직전 {fng['prev']}, {fng['as_of']})")
    else:
        print("  [skip] CNN F&G 시드값 유지")
    vk = fetch_vkospi()
    if vk:
        seed = MANUAL["vkospi"]
        sent_manual["vkospi"] = {**seed, "current": vk["current"], "prev": vk["prev"],
                                  "as_of": vk["as_of"], "history": vk["history"],
                                  "source": {"name": "investing.com (KSVKOSPI)",
                                             "url": "https://kr.investing.com/indices/kospi-volatility"}}
        print(f"  [ok] VKOSPI {vk['current']} (직전 {vk['prev']}, {vk['as_of']})")
    else:
        print("  [skip] VKOSPI 시드값 유지")
    ism = fetch_ism_pmi()
    if ism:
        seed = MANUAL["ism_pmi"]
        sent_manual["ism_pmi"] = {**seed, "current": ism["current"], "prev": ism["prev"],
                                   "as_of": ism["as_of"],
                                   "source": {"name": "investing.com (ISM 제조업 PMI)",
                                              "url": "https://kr.investing.com/economic-calendar/ism-manufacturing-pmi-173"}}
        print(f"  [ok] ISM PMI {ism['current']} (직전 {ism['prev']}, {ism['as_of']})")
    else:
        print("  [skip] ISM PMI 시드값 유지")
    flows_manual, kr_flows_ts = load_kr_flows()
    for key, m in {**sent_manual, **flows_manual}.items():
        score = score_indicator(key, m["current"], [m.get("prev", m["current"]), m["current"]], {})
        lbl, cls = signal_label(score)
        pillar_scores[m["pillar"]].append(score)
        indicators[key] = {
            "name": m["name"], "pillar": m["pillar"], "current": m["current"],
            "unit": m.get("unit", ""), "z": None, "pct": None, "score": round(score, 2),
            "signal": lbl, "signal_cls": cls, "desc": m.get("note", ""),
            "as_of": m["as_of"], "history": m.get("history"), "manual": True,
            "kind": m.get("kind", "release"),
            "source": m.get("source") or ({"name": "원본 데이터", "url": MANUAL_URLS[key]} if key in MANUAL_URLS else None),
        }

    # --- 기업이익 축 (국가/섹터 Forward EPS·ERR) ---
    earn = build_earnings()
    indicators.update(earn["cards"])
    pillar_scores["earnings"] = [earn["pillar_score"]]

    # --- PEG (밸류에이션): Fwd PER / EPS성장 ---
    us_e = earn["data"].get("countries", {}).get("US", {})
    g_list = [x for x in [us_e.get("growth_cy"), us_e.get("growth_ny")] if x and x > 0]
    fwd_g = sum(g_list) / len(g_list) if g_list else None
    if spx_fwd_pe and fwd_g:
        peg = round(spx_fwd_pe / fwd_g, 2)
        ps = score_indicator("peg", peg, [peg], {})
        plbl, pcls = signal_label(ps)
        indicators["peg"] = {"name": "S&P500 PEG", "pillar": "valuation", "current": peg,
            "unit": "", "z": None, "pct": None, "score": round(ps, 2), "signal": plbl, "signal_cls": pcls,
            "desc": f"Fwd PER {spx_fwd_pe} / EPS성장 {fwd_g:.0f}%. 1 미만 저평가, 2+ 부담",
            "as_of": today.isoformat(), "history": None,
            "source": {"name": "yfinance/FactSet", "url": "https://insight.factset.com/topic/earnings"}}
        pillar_scores["valuation"].append(ps)

    # --- Carry-forward: 이번에 못 받은 지표는 직전 macro-data.js 값 사용 ---
    # (FRED/yfinance transient 실패로 지표가 누락돼도 출력이 항상 완전하게 유지)
    prev = load_prev()
    carried = 0
    for k, pdv in prev.get("indicators", {}).items():
        if k not in indicators and pdv.get("pillar") in pillar_scores:
            indicators[k] = {**pdv, "stale": True}
            sc = pdv.get("score")
            if sc is not None:
                pillar_scores[pdv["pillar"]].append(sc)
            carried += 1
    if carried:
        print(f"  [carry-forward] 직전값 사용 지표 {carried}개(이번 실패분)")

    # 현재값을 benchmarks.js(yfinance)로 보정 — FRED 차단/지연 시 헤드라인 stale 방지.
    # (히스토리·z·레짐은 FRED 장기시계열 유지, 카드 현재값만 최신으로)
    def bench_override(key, bname, dec, yoy=False):
        bi = bench.get(bname) or {}
        bcur = bi.get("current")
        if key not in indicators or bcur is None:
            return
        ind = indicators[key]
        if yoy:
            vv = (bi.get("history") or {}).get("values") or []
            if len(vv) < 2 or vv[0] <= 0:
                return
            newcur = round((bcur / vv[0] - 1) * 100, 1)
        else:
            newcur = round(bcur, dec)
        # 점수 재계산 (기존 히스토리 + 새 current로 chg3 등 반영)
        hist = (ind.get("history") or {}).get("values") or []
        hv = (hist[-12:] + [newcur]) if hist else [newcur]
        sc = score_indicator(key, newcur, hv, {})
        old = ind.get("score"); ps = pillar_scores.get(ind.get("pillar"), [])
        if old is not None and old in ps:
            ps.remove(old)
        ps.append(sc)
        lbl, cls = signal_label(sc)
        ind.update({"current": newcur, "as_of": bi.get("as_of", ind.get("as_of")),
                    "score": round(sc, 2), "signal": lbl, "signal_cls": cls, "stale": False})

    bench_override("vix", "VIX", 1)
    bench_override("us10y", "US 10Y", 2)
    bench_override("usdkrw", "USD/KRW", 1)
    bench_override("oil_yoy", "WTI 유가", 1, yoy=True)

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

    # --- 경기국면 (OECD CLI) ---
    cycle = None
    if "cli_us" in raw and raw["cli_us"][1]:
        cp = cycle_phase(raw["cli_us"][1])
        if cp:
            cv = raw["cli_us"][1]
            cycle = {**cp, "cli": round(cv[-1], 1), "chg6": round(cv[-1] - cv[-7], 2) if len(cv) >= 7 else None}

    # 과거 기업이익 모멘텀 프록시 (S&P 트레일링 EPS YoY) — 타임머신 earnings 축용
    try:
        ed, ev = fetch_multpl("s-p-500-earnings")
        eyd, eyv = yoy(ed, ev)
        if eyd:
            monthly["spx_eps_yoy"] = to_month_end(eyd, eyv)
    except Exception as e:
        print(f"  [warn] S&P earnings YoY: {e}")

    # --- 국가 선호도 + 과거 레짐 타임머신 ---
    spx_me = to_month_end(spx_dates, spx_vals)
    kospi_me = to_month_end(kospi_dates, kospi_vals)
    kosdaq_me = to_month_end(kosdaq_dates, kosdaq_vals)
    country_pref = build_country_pref(earn["data"], bench)
    regime_history = build_regime_history(monthly, spx_me, kospi_me)
    # FRED 일별(vix/환율 등)이 차단돼 장기 히스토리가 끊기면 레짐히스토리 품질 저하
    # → 직전 좋은 값 보존(cron의 정상 실행이 갱신). 길이 급감 또는 핵심 일별 누락 시.
    prev_rh = prev.get("regime_history", [])
    degraded = ("vix" not in monthly) or ("usdkrw" not in monthly) or ("baa_spread" not in monthly)
    if prev_rh and (degraded or len(regime_history) < len(prev_rh) - 2):
        # 장기 히스토리는 직전(정상 FRED 기반)을 신뢰. 단, 직전에 없는 '더 최근 월'
        # (예: 5·6월 — spx/kospi는 yfinance라 차단과 무관)은 이번 build(carry-forward)에서
        # 가져와 append → 타임머신에 최근월이 빠지지 않게 함.
        prev_last = prev_rh[-1]["date"] if prev_rh else "0000-00-00"
        tail = [r for r in regime_history if r["date"] > prev_last]
        print(f"  [regime_history] degraded={degraded}, fresh={len(regime_history)} "
              f"→ 직전({len(prev_rh)}) 보존 + 신규월 {len(tail)}개 append")
        regime_history = prev_rh + tail
    kr_credit = build_kr_credit(kospi_me, kosdaq_me)
    kr_credit_daily = build_kr_credit_daily()
    quadrant = build_quadrant(monthly)
    if quadrant:
        print(f"  [quadrant] {quadrant['phase']['name']} (성장Δ {quadrant['trail'][-1]['g']:+.2f}, "
              f"인플레Δ {quadrant['trail'][-1]['i']:+.2f})")
    recession = build_recession(monthly)
    if recession:
        print(f"  [recession] {recession['verdict']['label']} — " +
              ", ".join(f"{s['name']} {s['value']}{s['unit']}({s['status_ko']})" for s in recession["signals"]))

    # --- 업데이트 알림 (직전 대비 변경분) ---
    prev = load_prev()
    update_log, updates_today = build_updates(indicators, prev, cycle, regime_label, overall_score,
                                              kr_flows_ts, today.isoformat())

    # --- 자동 코멘터리 + 전망 ---
    commentary = build_commentary(indicators, pillars_out, overall_score)
    outlook = build_outlook(indicators, pillars_out, overall_score, analogs)

    out = {
        "as_of": today.isoformat(),
        "update_log": update_log,
        "updates_today": updates_today,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "regime": {"score": overall_score, "label": regime_label, "cls": regime_cls,
                   "pillars": pillars_out},
        "cycle": cycle,
        "quadrant": quadrant,
        "recession": recession,
        "monthly_factors": build_monthly(today),
        "monthly_all": build_monthly_all(today),
        "country_pref": country_pref,
        "regime_history": regime_history,
        "kr_flows_ts": kr_flows_ts,
        "kr_credit": kr_credit,
        "kr_credit_daily": kr_credit_daily,
        "indicators": indicators,
        "indices": indices,
        "analogs": analogs,
        "earnings": earn["data"],
        "ai": build_ai(),
        "commentary": commentary,
        "outlook": outlook,
        "real_rate": round(real_rate, 2) if real_rate is not None else None,
    }

    # 품질 게이트: 이번 수집이 빈약(일부 FRED/yfinance 실패)하면 직전 좋은 버전 보존.
    # cron이 하루 8회(백업 포함) 도므로, 한 번 실패해도 다음 정상 실행이 갱신.
    us_n = (earn["data"].get("countries", {}).get("US") or {}).get("n", 0)
    if OUT.exists() and (len(indicators) < 16 or not regime_history):
        # 심각한 실패(지표 절반 이상 누락 등)만 차단 — 일부 지표 누락은 그대로 발행해
        # KR 수급·시장 데이터 등 신선한 부분이 반영되게 함.
        print(f"\n[guard] 심각한 수집 실패(지표 {len(indicators)}/16, US이익 n={us_n}, "
              f"레짐히스토리 {len(regime_history)}) → macro-data.js 갱신 생략(직전 보존).")
        return

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

    def month_minus(ym, n):
        y, mo = int(ym[:4]), int(ym[5:7])
        tot = mo - n
        ty = y + (tot - 1) // 12
        tm = (tot - 1) % 12 + 1
        return f"{ty:04d}-{tm:02d}"

    neighbors = []
    for d, m in dist:
        yr = m[:4]
        if list(n["date"][:4] for n in neighbors).count(yr) >= 2:
            continue
        # 유사·상이 피처 (표준화 차이 기준)
        v = vec(m)
        diffs = sorted(((abs(cur_vec[i] - v[i]), feats[i]) for i in range(len(feats))), key=lambda x: x[0])
        similar = [ANALOG_LABELS.get(f, f) for _, f in diffs[:3]]
        divergent = [ANALOG_LABELS.get(f, f) for _, f in diffs[-1:]]
        # 당시 지표 값
        def gv(key):
            return round(monthly[key][m], 1) if (key in monthly and m in monthly[key]) else None
        u10 = monthly.get("us10y", {})
        u10_now = round(u10[m], 2) if m in u10 else None
        pm3 = month_minus(m, 3)
        u10_chg3 = round(u10[m] - u10[pm3], 2) if (m in u10 and pm3 in u10) else None
        vals = {"cpi": gv("cpi_yoy"), "vix": gv("vix"), "curve": gv("yield_curve"),
                "mom": gv("spx_mom"), "cli": gv("cli_us"), "us10y": u10_now, "us10y_chg3": u10_chg3}
        neighbors.append({
            "date": m + "-01",
            "distance": round(d, 2),
            "similar": similar, "divergent": divergent,
            "vals": vals, "context": analog_context(m + "-01"),
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
