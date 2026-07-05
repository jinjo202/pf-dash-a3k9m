"""
fetch_export.py — 한국 품목별 수출 시계열 자동 축적 (관세청 무역통계 OpenAPI)

data.go.kr '관세청_품목별 수출입실적'(getNitemtradeList, XML)로 HS부호별 월별
수출액(expDlr, USD)·중량(expWgt, kg)을 받아 품목별로 월 합산하고,
수출금액($10억)·수출단가($/kg)·각 YoY/MoM를 계산해 export-history.js를 만든다.
반도체는 디램(모듈포함/제외)·낸드·MCP(HBM)·SSD·시스템으로 세분한다.

키(무료): data.go.kr '관세청_품목별 수출입실적' 활용신청 → 일반 인증키(Decoding)를
    GitHub Secret TRADE_API_KEY 에. 키 없으면 스킵(캘린더는 큐레이션 폴백).

실행:  TRADE_API_KEY=xxx python fetch_export.py [--months 18]
주의:  상세 HS는 최신월이 1~2개월 지연(예: 오늘 7월이면 5월까지). 금액=USD.
"""
import argparse
import datetime as dt
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "export-history.js"
API_URL = os.environ.get("TRADE_API_URL", "https://apis.data.go.kr/1220000/nitemtrade/getNitemtradeList")
KEY = os.environ.get("TRADE_API_KEY")

# key: (표시명, 그룹, [HS부호들])  — 여러 코드는 합산
CATS = {
    # 품목 (주력/유망)
    "semi":       ("반도체(전체)",       "반도체", ["8542"]),
    "computer":   ("컴퓨터(SSD포함)",     "IT",     ["8471", "852351"]),  # 한국 컴퓨터 수출은 SSD 주도
    "appliance":  ("가전제품",           "IT",     ["8418", "8450", "8516", "8508", "8415", "8528"]),
    "mlcc":       ("전자제품(MLCC)",      "IT",     ["853224"]),
    "semi_equip": ("반도체 제조장비",      "장비",   ["8486"]),
    # 전력기기 (변압기 용량별 + 전선) — AI/전력망 투자 테마
    "tf_xl":      ("변압기(특대형)",       "전력",   ["850423"]),                 # >10,000kVA
    "tf_ml":      ("변압기(중대형)",       "전력",   ["850422"]),                 # 650~10,000kVA
    "tf_sm":      ("변압기(소형)",         "전력",   ["850421", "850431", "850432", "850433", "850434"]),
    "cable":      ("전선·케이블",          "전력",   ["8544"]),
    "wireless":   ("무선통신기기",         "IT",     ["8517"]),
    "display":    ("디스플레이",           "IT",     ["8524"]),
    "auto":       ("자동차",             "운송",   ["8703"]),
    "autoparts":  ("자동차부품",           "운송",   ["8708"]),
    "ship":       ("선박",               "운송",   ["8901", "8904", "8905", "8906"]),
    "battery":    ("2차전지",            "소재",   ["8507"]),
    "petrochem":  ("석유화학",            "소재",   ["3901", "3902", "3903", "3904"]),
    "steel":      ("철강판",             "소재",   ["7208", "7210"]),
    "cosmetic":   ("화장품",             "소비재", ["3304"]),
    "botox":      ("보톡스(보툴리눔)",      "소비재", ["300249"]),
    "food":       ("농수산식품",           "소비재", ["1902", "2106", "2005"]),
    "ramen":      ("라면",               "소비재", ["190230"]),
    # 반도체 세부 (금액·단가 모두 의미있음)
    "semi_mem":   ("반도체:메모리",        "반도체세부", ["854232"]),
    "semi_sys":   ("반도체:시스템",        "반도체세부", ["854231"]),
    "dram_excl":  ("디램(모듈제외)",       "반도체세부", ["8542321010"]),
    "dram_incl":  ("디램(모듈포함)",       "반도체세부", ["8542321010", "8542323000"]),
    "nand":       ("플래시메모리(낸드)",    "반도체세부", ["8542321030"]),
    "mcp":        ("MCP(HBM)",          "반도체세부", ["8542323000"]),
    "ssd":        ("SSD",               "반도체세부", ["852351"]),
}


def add_months(ym, n):
    idx = (ym // 100) * 12 + (ym % 100 - 1) + n
    return (idx // 12) * 100 + (idx % 12) + 1


def _fetch_window(hs, s, e):
    """단일 요청(≤1년). XML 반환. 월별 (expDlr, expWgt) 합산해서 {ym:(dlr,wgt)}."""
    q = {"serviceKey": KEY, "strtYymm": f"{s:06d}", "endYymm": f"{e:06d}",
         "hsSgn": hs, "numOfRows": "900", "pageNo": "1"}
    url = API_URL + "?" + urllib.parse.urlencode(q, safe="")
    with urllib.request.urlopen(url, timeout=50) as r:
        xml = r.read().decode("utf-8", "replace")
    root = ET.fromstring(xml)
    rc = root.findtext(".//resultCode")
    if rc not in (None, "00", "0"):
        raise RuntimeError(f"resultCode={rc}")
    out = defaultdict(lambda: [0.0, 0.0])
    for it in root.findall(".//item"):
        y = (it.findtext("year") or "").strip()
        if "." not in y:            # '한계'(총계) 등 스킵, 월행만
            continue
        ym = int(y.replace(".", ""))
        try:
            out[ym][0] += float(it.findtext("expDlr") or 0)
            out[ym][1] += float(it.findtext("expWgt") or 0)
        except (TypeError, ValueError):
            continue
    return out


def fetch_hs(hs, strt, end):
    out, ws = defaultdict(lambda: [0.0, 0.0]), strt
    while ws <= end:
        we = min(add_months(ws, 11), end)
        try:
            for ym, (d, w) in _fetch_window(hs, ws, we).items():
                out[ym][0] += d
                out[ym][1] += w
        except urllib.error.HTTPError as e:
            hint = {401: "키 미인식/미활성", 403: "서비스 미승인"}.get(e.code, "")
            print(f"  {hs} {ws}-{we} HTTP {e.code} {hint}")
        except Exception as e:
            print(f"  {hs} {ws}-{we} 실패: {str(e)[:60]}")
        ws = add_months(we, 1)
    return out


def yoy(series, i):
    if i < 12 or series[i] is None or series[i - 12] in (None, 0):
        return None
    return round((series[i] / series[i - 12] - 1) * 100, 1)


def mom(series, i):
    if i < 1 or series[i] is None or series[i - 1] in (None, 0):
        return None
    return round((series[i] / series[i - 1] - 1) * 100, 1)


def main():
    if not KEY:
        print("TRADE_API_KEY 없음 — 관세청 자동수집 스킵(큐레이션 폴백).")
        return
    ap = argparse.ArgumentParser()
    ap.add_argument("--months", type=int, default=18)   # 표시 개월수
    ap.add_argument("--only", default="")                 # 쉼표구분 key만(테스트용)
    args = ap.parse_args()

    now = dt.date.today()
    end = now.year * 100 + now.month
    strt = add_months(end, -(args.months + 12) + 1)       # YoY용 +12개월
    nmonths = (end // 100 - strt // 100) * 12 + (end % 100 - strt % 100) + 1
    axis = [add_months(strt, i) for i in range(nmonths)]
    months_all = [f"{ym // 100}.{ym % 100:02d}" for ym in axis]
    disp_from = len(axis) - args.months                    # 표시 시작 인덱스

    keys = [k for k in CATS if (not args.only or k in args.only.split(","))]
    cat_out, latest_ym = {}, 0
    for key in keys:
        name, group, hslist = CATS[key]
        agg = defaultdict(lambda: [0.0, 0.0])
        for hs in hslist:
            for ym, (d, w) in fetch_hs(hs, strt, end).items():
                agg[ym][0] += d
                agg[ym][1] += w
        val = [round(agg[ym][0] / 1e9, 3) if agg.get(ym) and agg[ym][0] else None for ym in axis]   # $10억
        price = [round(agg[ym][0] / agg[ym][1], 1) if agg.get(ym) and agg[ym][1] else None for ym in axis]  # $/kg
        for i, ym in enumerate(axis):
            if val[i]:
                latest_ym = max(latest_ym, ym)
        cat_out[key] = {
            "name": name, "group": group,
            "months": months_all[disp_from:],
            "val": val[disp_from:],
            "price": price[disp_from:],
            "val_yoy": [yoy(val, i) for i in range(disp_from, len(axis))],
            "val_mom": [mom(val, i) for i in range(disp_from, len(axis))],
            "price_yoy": [yoy(price, i) for i in range(disp_from, len(axis))],
            "price_mom": [mom(price, i) for i in range(disp_from, len(axis))],
        }
        v = cat_out[key]["val"]
        got = next((x for x in reversed(v) if x is not None), None)
        print(f"  {key:11}{name:16} 최신값 {got}")

    have = sum(1 for k in cat_out if any(x is not None for x in cat_out[k]["val"]))
    if have == 0:
        print("수집 0건 — export-history.js 미갱신(큐레이션 유지).")
        return

    payload = {
        "as_of": now.isoformat(),
        "latest_month": f"{latest_ym // 100}.{latest_ym % 100:02d}" if latest_ym else None,
        "source": "관세청 품목별 수출입실적 OpenAPI · 금액=USD, 단가=$/kg(금액/중량)",
        "cat": cat_out,
    }
    OUT.write_text(
        "// 한국 품목별 수출 과거 시계열 — fetch_export.py 생성(관세청 OpenAPI). 금액·단가 + YoY/MoM.\n"
        f"window.EXPORT_HISTORY = {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))};\n",
        encoding="utf-8",
    )
    print(f"생성: {OUT.name} · 품목 {have}개 · 최신 {payload['latest_month']} · 표시 {args.months}개월")


if __name__ == "__main__":
    main()
