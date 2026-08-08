# -*- coding: utf-8 -*-
"""
fetch_pe_history.py — 국가별 장기 PER 히스토리 + 중앙값/z-score → pe-history.js

국가배분 모델의 COUNTRY_FAIR_PE(적정 PER)가 하드코딩이라 판단 기준선이 몇 년째
고정되는 문제의 해소용. 히스토리가 있는 나라는 장기 중앙값을 fair로 쓰고,
macro.html에 장기 PE 차트(중앙값 선 + z-score)를 그린다.

소스 (나라마다 다르다 — 전부 같은 정의가 아님을 sources에 명시):
  US: multpl.com S&P 500 trailing PE (월간, 실측 스크래핑. 최근 15년만 저장)
  KR: KRX 월간통계 기반 KOSPI 분기 PER (fetch_historical_valuations.py 내장 데이터)
      + bm-factors.js(EWY) 축적 tail — 분기 데이터가 2025-12에서 끝나므로
  EU/JP/CN: 장기 무료 소스 없음 → bm-factors.js(IEUR/EWJ/MCHI)에서 3일 주기 축적.
      span이 MIN_YEARS를 넘으면 중앙값이 자동으로 유효해진다(그 전엔 valid=false,
      모델은 시드 fair를 계속 쓴다). 데이터를 지어내지 않는 대가로 몇 년 걸린다.

중앙값 창: 최근 WINDOW_YEARS(10년). valid 조건: span >= MIN_YEARS(3년) & n >= 12.
z-score = (현재 - 창내 평균) / 창내 표준편차.
"""
# io: reconfigure 사용으로 불필요
import json
import re
import statistics
import sys
from datetime import date, datetime
from pathlib import Path

# TextIOWrapper 재래핑 금지 — import되는 fetch_historical_valuations도 stdout을 감싸는데,
# 이중 래핑되면 먼저 만든 래퍼가 GC되며 공유 버퍼를 닫아 'I/O on closed file'이 난다.
sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "pe-history.js"
BMF = HERE / "bm-factors.js"

WINDOW_YEARS = 10
MIN_YEARS = 3
US_KEEP_YEARS = 15   # multpl은 1871년까지 있어 파일 비대 방지용으로 자른다

# 국가코드 → (표기명, bm-factors 지수명[축적 소스], 축적 사용 여부)
# US는 multpl이 매월 라이브라 축적 tail을 섞지 않는다(정의 다른 점이 매달 끼면 꼬리가 오염됨).
COUNTRIES = {
    "US": ("미국", "S&P 500", False),
    "KR": ("한국", "KOSPI", True),
    "EU": ("유럽", "STOXX 600", True),
    "JP": ("일본", "니케이 225", True),
    "CN": ("이머징(중국)", "상해종합", True),
}


def load_prev_accum():
    """이전 pe-history.js의 축적 tail 보존 (CI는 매번 새로 clone하므로 파일이 유일한 상태)."""
    try:
        t = OUT.read_text(encoding="utf-8")
        d = json.loads(re.search(r"window\.PE_HISTORY\s*=\s*(\{.*\})\s*;", t, re.S).group(1))
        return {cc: (v.get("accum") or {"dates": [], "values": []})
                for cc, v in (d.get("countries") or {}).items()}
    except Exception:
        return {}


def load_bmf():
    """bm-factors.js → (as_of, {지수명: pe})."""
    try:
        t = BMF.read_text(encoding="utf-8")
        d = json.loads(re.search(r"window\.BM_FACTORS\s*=\s*(\{.*\})\s*;", t, re.S).group(1))
        return d.get("as_of"), {nm: v.get("pe") for nm, v in (d.get("indices") or {}).items()}
    except Exception as e:
        print(f"[warn] bm-factors.js 읽기 실패(축적 생략): {e}")
        return None, {}


def base_series(cc):
    """(dates, values, source_desc) — 나라별 기본(장기) 시리즈."""
    if cc == "US":
        sys.path.insert(0, str(HERE))
        from fetch_historical_valuations import fetch_multpl
        pairs = fetch_multpl("s-p-500-pe-ratio")
        cut = f"{date.today().year - US_KEEP_YEARS}-01-01"
        pairs = [p for p in pairs if p[0] >= cut]
        return ([p[0] for p in pairs], [p[1] for p in pairs],
                "multpl.com S&P500 trailing PE (월간)")
    if cc == "KR":
        from fetch_historical_valuations import KOSPI_QUARTERLY
        items = sorted(KOSPI_QUARTERLY.items())
        return ([d for d, _ in items], [v[0] for _, v in items],
                "KRX 월간통계 KOSPI PER (분기)")
    return [], [], None


def summarize(dates, values):
    """최근 WINDOW_YEARS 창의 median/mean/std/z. (summary dict, 창 시작 인덱스)."""
    if not dates:
        return None
    cut = (datetime.strptime(dates[-1], "%Y-%m-%d").date()
           .replace(year=datetime.strptime(dates[-1], "%Y-%m-%d").year - WINDOW_YEARS)
           .isoformat())
    i0 = next((i for i, d in enumerate(dates) if d >= cut), 0)
    w = values[i0:]
    wd = dates[i0:]
    span_years = round((datetime.strptime(wd[-1], "%Y-%m-%d")
                        - datetime.strptime(wd[0], "%Y-%m-%d")).days / 365.25, 1)
    out = {"n": len(w), "years": span_years,
           "median": round(statistics.median(w), 2),
           "mean": round(statistics.fmean(w), 2),
           "current": w[-1], "current_date": wd[-1],
           "valid": span_years >= MIN_YEARS and len(w) >= 12}
    sd = statistics.pstdev(w) if len(w) > 1 else 0.0
    out["z"] = round((w[-1] - out["mean"]) / sd, 2) if sd > 1e-9 else None
    return out


def main():
    prev = load_prev_accum()
    bmf_asof, bmf_pe = load_bmf()
    countries = {}
    for cc, (name, bmf_name, use_accum) in COUNTRIES.items():
        dates, values, src = base_series(cc)
        srcs = [s for s in [src] if s]
        accum = prev.get(cc) or {"dates": [], "values": []}
        if use_accum:
            pe_now = bmf_pe.get(bmf_name)
            if bmf_asof and pe_now and bmf_asof not in accum["dates"]:
                accum["dates"].append(bmf_asof)
                accum["values"].append(pe_now)
            if accum["dates"]:
                srcs.append(f"bm-factors({bmf_name} 프록시 ETF, Morningstar 집계) 축적 tail")
        # 병합: 기본 시리즈 뒤에 그보다 최신인 축적분만 붙인다
        last_base = dates[-1] if dates else ""
        for d, v in zip(accum["dates"], accum["values"]):
            if d > last_base:
                dates.append(d)
                values.append(v)
        s = summarize(dates, values)
        countries[cc] = {
            "name": name, "dates": dates, "values": values,
            "sources": srcs, "accum": accum, **(s or {}),
        }
        if s:
            print(f"  {cc}({name}): n={s['n']} span={s['years']}년 중앙값={s['median']} "
                  f"현재={s['current']}({s['current_date']}) z={s['z']} "
                  f"{'✓유효' if s['valid'] else '✗축적중(시드 유지)'}")
        else:
            print(f"  {cc}({name}): 데이터 없음 — 축적 시작 대기")

    payload = {
        "as_of": date.today().isoformat(),
        "window_years": WINDOW_YEARS, "min_years": MIN_YEARS,
        "note": ("중앙값은 최근 %d년 창. span %d년 미만이면 valid=false → 모델은 시드 "
                 "fair_pe를 유지하고 히스토리만 축적한다. 소스는 나라별로 다르며(정의 혼합) "
                 "sources에 명시.") % (WINDOW_YEARS, MIN_YEARS),
        "countries": countries,
    }
    OUT.write_text("// 국가별 장기 PER 히스토리 (자동생성: fetch_pe_history.py — 수동편집 금지)\n"
                   "window.PE_HISTORY = " + json.dumps(payload, ensure_ascii=False) + ";\n",
                   encoding="utf-8")
    print(f"완료: {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
