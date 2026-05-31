"""
한국 투자자별 수급(외국인/기관/개인) 자동 수집 → kr_flows.json (평문, 공개 데이터).

소스: 네이버 금융 투자자별 매매동향(일별, KOSPI). 단위 억원 → 조원 변환.
fetch_macro.py가 이 파일을 읽어 macro-data.js의 한국 수급 지표를 갱신한다.

방어적 설계: 유효 데이터를 못 받으면 기존 kr_flows.json을 보존(덮어쓰지 않음).
→ 네이버 접근 실패(예: 일부 클라우드 IP) 시에도 마지막 정상값 유지.
GitHub Actions(미국)에서 막히면 로컬 daily_run.ps1(한국)이 갱신·커밋.

투자자예탁금은 무료 안정 소스가 없어 fetch_macro.py의 수동 시드를 유지(별도).
"""
import json
import re
import sys
import io
import urllib.request
from datetime import date
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "kr_flows.json"
URL = "https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={d}&sosok=01&page={p}"


def fetch_page(bizdate, page):
    req = urllib.request.Request(
        URL.format(d=bizdate, p=page),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                 "Referer": "https://finance.naver.com/sise/"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("euc-kr", errors="replace")


def parse_rows(html):
    """일별 행 → {date: [개인, 외국인, 기관계]} (억원, int)."""
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub("<[^>]+>", "", c).strip().replace("\xa0", "")
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        cells = [c for c in cells if c != ""]
        if len(cells) >= 4 and re.match(r"\d{2}\.\d{2}\.\d{2}", cells[0]):
            try:
                out[cells[0]] = [int(cells[1].replace(",", "")),   # 개인
                                 int(cells[2].replace(",", "")),   # 외국인
                                 int(cells[3].replace(",", ""))]   # 기관계
            except ValueError:
                continue
    return out


def main():
    today = date.today()
    bizdate = today.strftime("%Y%m%d")
    rows = {}
    try:
        for p in (1, 2):
            rows.update(parse_rows(fetch_page(bizdate, p)))
    except Exception as e:
        print(f"[err] 네이버 수집 실패: {type(e).__name__} {e}")

    if not rows:
        print("유효 데이터 없음 — 기존 kr_flows.json 보존")
        return

    # 'YY.MM.DD' → 정렬 가능 키
    def keyf(d):
        return "20" + d.replace(".", "")
    dates = sorted(rows, key=keyf)
    latest = dates[-1]
    # 현재 달(YY.MM) 누적
    ym = latest[:5]  # 'YY.MM'
    month_rows = [rows[d] for d in dates if d.startswith(ym)]
    retail = sum(r[0] for r in month_rows) / 10000.0
    foreign = sum(r[1] for r in month_rows) / 10000.0
    inst = sum(r[2] for r in month_rows) / 10000.0
    lc = rows[latest]

    out = {
        "as_of": today.isoformat(),
        "source": "naver-finance",
        "month": "20" + ym,
        "unit": "조원",
        "mtd": {"retail": round(retail, 1), "foreign": round(foreign, 1),
                "inst": round(inst, 1), "days": len(month_rows)},
        "latest": {"date": latest, "retail": round(lc[0] / 10000.0, 2),
                   "foreign": round(lc[1] / 10000.0, 2), "inst": round(lc[2] / 10000.0, 2)},
        "deposit": None,   # KOFIA 자동 소스 없음 → fetch_macro 수동 시드 사용
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {OUT.name}  {out['month']} 누적(조원) 외국인 {foreign:+.1f}·기관 {inst:+.1f}·개인 {retail:+.1f} "
          f"({len(month_rows)}일), 최근 {latest}")


if __name__ == "__main__":
    main()
