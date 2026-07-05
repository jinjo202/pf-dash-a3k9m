"""
fetch_memory_prices.py — 메모리(DRAM·NAND) 고정거래가 장기 시계열 생성

Meritz '장기 메모리 가격' 엑셀(DRAMeXchange 기반, 일별)을 읽어 월별 시계열로
집계하고 memory-prices.js(window.MEMORY_PRICES)를 만든다. 캘린더 '반도체 세부'
가 DRAM/NAND 단가 차트·MoM 트래킹에 사용한다.

엑셀은 로컬(OneDrive)에만 있으므로 이 스크립트는 로컬에서 실행(엑셀 갱신 시 재실행)한다:
    python fetch_memory_prices.py
    MEMORY_XLSX="D:/경로/파일.xlsx" python fetch_memory_prices.py

CI(GitHub)에는 엑셀이 없으니 산출물(memory-prices.js)만 commit한다.
"""
import datetime as dt
import io
import json
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import openpyxl
except ImportError:
    sys.exit("openpyxl 필요: pip install openpyxl")

HERE = Path(__file__).parent
OUT = HERE / "memory-prices.js"
DEFAULT_XLSX = r"C:\Users\ocarr\OneDrive\dev\research\반도체\[Meritz] 장기 메모리 가격(1) (1).xlsx"
XLSX = os.environ.get("MEMORY_XLSX", DEFAULT_XLSX)

START_YM = (2020, 1)   # 공통 월축 시작

# (라벨키, 시트, 값열 index)  — 고정거래가(contract) 중심
COLS = [
    ("dram_ddr5_16gb",   "디램가격", 10),  # DDR5 16Gb 고정가 (현세대 주력)
    ("dram_ddr4_8gb",    "디램가격", 9),   # DDR4 8Gb 고정가 (레거시 주력)
    ("dram_server_ddr5", "디램가격", 23),  # DDR5 4800 16GB RDIMM (서버/AI)
    ("nand_128g_mlc",    "낸드가격", 23),  # 128G MLC 고정가 (주력 NAND)
]
LABELS = {
    "dram_ddr5_16gb":   "DDR5 16Gb 고정가",
    "dram_ddr4_8gb":    "DDR4 8Gb 고정가",
    "dram_server_ddr5": "서버 DDR5 16GB RDIMM",
    "nand_128g_mlc":    "NAND 128Gb MLC 고정가",
}


def monthly_last(wb, sheet, valcol):
    """각 (년,월)의 마지막 유효값(고정거래가는 월중 몇 번만 갱신)."""
    ws = wb[sheet]
    m = {}
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i < 2:
            continue
        d = row[0] if row else None
        v = row[valcol] if valcol < len(row) else None
        if not isinstance(d, dt.datetime):
            continue
        if not isinstance(v, (int, float)):
            continue
        m[(d.year, d.month)] = float(v)
    return m


def ym_axis(start, end):
    out, y, mo = [], start[0], start[1]
    while (y, mo) <= end:
        out.append((y, mo))
        mo += 1
        if mo > 12:
            y += 1; mo = 1
    return out


def main():
    if not Path(XLSX).exists():
        sys.exit(f"엑셀 없음: {XLSX}\n  (로컬 OneDrive 경로. MEMORY_XLSX 로 지정 가능)")
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)

    raw = {key: monthly_last(wb, sheet, col) for key, sheet, col in COLS}
    # 공통 월축: START_YM ~ 데이터 최신월
    last = max(max(s.keys()) for s in raw.values() if s)
    axis = ym_axis(START_YM, last)
    months = [f"{y}.{mo:02d}" for (y, mo) in axis]

    series, latest = {}, {}
    for key in raw:
        vals = [raw[key].get(ym) for ym in axis]
        series[key] = vals
        # 최신 유효값 + MoM + YoY
        idx = len(vals) - 1
        while idx >= 0 and vals[idx] is None:
            idx -= 1
        if idx >= 0:
            cur = vals[idx]
            prev = vals[idx - 1] if idx >= 1 else None
            yoy_i = idx - 12
            yoy_v = vals[yoy_i] if yoy_i >= 0 else None
            latest[key] = {
                "month": months[idx],
                "val": round(cur, 3),
                "mom": round((cur / prev - 1) * 100, 1) if prev else None,
                "yoy": round((cur / yoy_v - 1) * 100, 1) if yoy_v else None,
            }

    payload = {
        "as_of": last[0] * 100 + last[1],
        "as_of_month": f"{last[0]}.{last[1]:02d}",
        "source": "Meritz 장기 메모리 가격 (DRAMeXchange 고정거래가 기반, 월말값)",
        "labels": LABELS,
        "months": months,
        "series": series,
        "latest": latest,
    }
    OUT.write_text(
        "// 메모리(DRAM·NAND) 고정거래가 월별 시계열 — fetch_memory_prices.py 생성(Meritz 엑셀).\n"
        f"window.MEMORY_PRICES = {json.dumps(payload, ensure_ascii=False, indent=1)};\n",
        encoding="utf-8",
    )
    print(f"생성: {OUT.name} · 월 {len(months)}개 · 최신 {payload['as_of_month']}")
    for k, v in latest.items():
        print(f"  {LABELS[k]}: {v['val']} (MoM {v['mom']}% / YoY {v['yoy']}%)")


if __name__ == "__main__":
    main()
