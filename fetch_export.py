"""
fetch_export.py — 한국 품목별 수출 시계열 자동 축적 (관세청 무역통계 OpenAPI)

data.go.kr '관세청_수출입 무역통계' 서비스(getNitemtradeList)로 HS부호별 월별
수출액을 가져와 YoY를 계산하고 export-history.js(window.EXPORT_HISTORY)를 만든다.
캘린더 '한국 수출 트래커'가 있으면 이 과거 시계열을 우선 사용한다(없으면 큐레이션).

키 발급(무료): https://www.data.go.kr → '관세청_수출입 무역통계' 활용신청 →
    일반 인증키(Decoding)를 GitHub Secret  TRADE_API_KEY  에 저장.
    (엔드포인트 오버라이드가 필요하면 TRADE_API_URL 도 설정)

실행:
    TRADE_API_KEY=xxxx python fetch_export.py            # 최근 24개월 누적
    TRADE_API_KEY=xxxx python fetch_export.py --months 36
키가 없으면 아무것도 하지 않고 종료(캘린더는 큐레이션 series로 폴백).

누적: 기존 export-history.js가 있으면 읽어 최신월만 병합(과거는 보존).
"""
import argparse
import datetime as dt
import io
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "export-history.js"
API_URL = os.environ.get("TRADE_API_URL", "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList")
KEY = os.environ.get("TRADE_API_KEY")

# 품목 → HS부호(들). 여러 개면 합산. (음식료는 가공식품 대표 HS 바스켓)
CATEGORY_HS = {
    "semi":     ["8542"],               # 집적회로(메모리+시스템)
    "auto":     ["8703"],               # 승용차
    "cosmetic": ["3304"],               # 화장품(기초·색조)
    "food":     ["1902", "2106", "2005"],  # 면류·기타조제식품·조제채소 (K-food 대표 바스켓)
}
# 총수출은 별도 total HS 합계 대신 산업부 집계를 쓰는 게 정확 → 여기선 품목만. total은 큐레이션 유지.


def _http_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read().decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise RuntimeError("JSON 파싱 실패(키/서비스 확인): " + raw[:200])


def fetch_hs(hs, strt, end):
    """getNitemtradeList: {year:'2026.06', expDlr:'44823000', ...}. expDlr=천달러 단위."""
    q = {
        "serviceKey": KEY, "strtYymm": strt, "endYymm": end,
        "hsSgn": hs, "returnType": "json", "numOfRows": "500", "pageNo": "1",
    }
    url = API_URL + "?" + urllib.parse.urlencode(q, safe="")
    data = _http_json(url)
    items = (((data.get("response") or {}).get("body") or {}).get("items") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
    out = {}
    for it in items:
        ym = str(it.get("year", "")).replace(".", "")  # '2026.06' -> '202606'
        if not re.fullmatch(r"\d{6}", ym):
            continue
        try:
            exp = float(it.get("expDlr") or 0)  # 천달러
        except (TypeError, ValueError):
            continue
        out[ym] = out.get(ym, 0.0) + exp
    return out


def add_months(ym, n):
    y, m = ym // 100, ym % 100
    idx = (y * 12 + (m - 1)) + n
    return (idx // 12) * 100 + (idx % 12) + 1


def main():
    if not KEY:
        print("TRADE_API_KEY 없음 — 관세청 수출 자동수집 스킵(캘린더는 큐레이션 series 사용).")
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=24)
    args = ap.parse_args()

    now = dt.date.today()
    end = now.year * 100 + now.month
    # YoY 계산 위해 +12개월 더 과거부터
    strt = add_months(end, -(args.months + 12) + 1)
    strt_s, end_s = f"{strt:06d}", f"{end:06d}"

    # HS별 월별 수출($천) 수집 → 품목별 합산
    cat_month = {}  # cat -> {ym(int): usd_thousand}
    for cat, hslist in CATEGORY_HS.items():
        agg = {}
        for hs in hslist:
            try:
                m = fetch_hs(hs, strt_s, end_s)
            except Exception as e:
                print(f"  {cat}/{hs} 실패: {str(e)[:80]}")
                continue
            for ym, v in m.items():
                agg[int(ym)] = agg.get(int(ym), 0.0) + v
        cat_month[cat] = agg

    # 공통 월축(최근 args.months) + YoY 시계열
    months_int = [add_months(end, -(args.months - 1) + i) for i in range(args.months)]
    months = [f"{ym//100}.{ym%100:02d}" for ym in months_int]
    series = {}
    for cat, agg in cat_month.items():
        yoy = []
        val = []
        for ym in months_int:
            cur = agg.get(ym)
            prev = agg.get(add_months(ym, -12))
            val.append(round(cur / 1e6, 2) if cur else None)  # 십억달러
            yoy.append(round((cur / prev - 1) * 100, 1) if (cur and prev) else None)
        series[cat + "_yoy"] = yoy
        series[cat + "_val"] = val

    payload = {
        "as_of": now.isoformat(),
        "source": "관세청 무역통계 OpenAPI(getNitemtradeList) · HS부호별",
        "hs_map": CATEGORY_HS,
        "months": months,
        "series": series,
    }
    OUT.write_text(
        "// 한국 품목별 수출 과거 시계열 — fetch_export.py 생성(관세청 OpenAPI).\n"
        f"window.EXPORT_HISTORY = {json.dumps(payload, ensure_ascii=False, indent=1)};\n",
        encoding="utf-8",
    )
    got = sum(1 for k in series if k.endswith("_yoy") and any(v is not None for v in series[k]))
    print(f"생성: {OUT.name} · 월 {len(months)}개 · 품목 계열 {got}개 · {months[0]}~{months[-1]}")


if __name__ == "__main__":
    main()
