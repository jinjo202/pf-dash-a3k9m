"""
한국 고객예탁금 + 신용잔고 자동 수집 → kr_deposit.json (평문, 공개 데이터).

소스: 네이버 금융 '증시자금추이'(sise_deposit.naver, 일별). 단위 억원 → 조원.
  컬럼: 날짜 | 고객예탁금 | (대비) | 신용잔고 | (대비) | ...
  → cells[1]=고객예탁금, cells[3]=신용잔고
KOFIA freesis는 websquare(JS 렌더) 포털이라 단순 HTTP로 수집 불가 → 네이버가 동일 데이터를 제공.

fetch_macro.py가 이 파일을 읽어 예탁금·신용잔고 지표·시계열을 갱신.
방어적: 유효 데이터 못 받으면 기존 kr_deposit.json 보존.
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
OUT = HERE / "kr_deposit.json"
URL = "https://finance.naver.com/sise/sise_deposit.naver?page={p}"
PAGES = 26  # 약 2년치(20행/페이지)


def fetch_page(p):
    req = urllib.request.Request(URL.format(p=p),
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                 "Referer": "https://finance.naver.com/sise/"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("euc-kr", errors="replace")


def parse_rows(html):
    """일별 행 → {date 'YY.MM.DD': (고객예탁금억, 신용잔고억)}."""
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub("<[^>]+>", "", c).strip().replace("\xa0", "")
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) >= 4 and re.match(r"\d{2}\.\d{2}\.\d{2}", cells[0]):
            try:
                dep = int(cells[1].replace(",", ""))
                cred = int(cells[3].replace(",", ""))
                out[cells[0]] = (dep, cred)
            except ValueError:
                continue
    return out


def main():
    rows = {}
    try:
        for p in range(1, PAGES + 1):
            page = parse_rows(fetch_page(p))
            if not page:
                break
            rows.update(page)
    except Exception as e:
        print(f"[err] 네이버 예탁금 수집 실패: {type(e).__name__} {e}")

    if not rows:
        print("유효 데이터 없음 — 기존 kr_deposit.json 보존")
        return

    keys = sorted(rows, key=lambda d: "20" + d.replace(".", ""))  # 시간순
    iso = lambda d: "20" + d.replace(".", "-")
    dep = {"dates": [], "values": []}
    cred = {"dates": [], "values": []}
    for d in keys:
        dv, cv = rows[d]
        dep["dates"].append(iso(d)); dep["values"].append(round(dv / 10000.0, 1))   # 억→조
        cred["dates"].append(iso(d)); cred["values"].append(round(cv / 10000.0, 1))
    last = keys[-1]
    out = {
        "as_of": date.today().isoformat(),
        "source": "naver-finance (증시자금추이)",
        "source_url": "https://finance.naver.com/sise/sise_deposit.naver",
        "unit": "조원",
        "current": {"deposit": dep["values"][-1], "credit": cred["values"][-1], "as_of": iso(last)},
        "deposit": dep,
        "credit": cred,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {OUT.name}  예탁금 {dep['values'][-1]}조 · 신용잔고 {cred['values'][-1]}조 "
          f"({len(keys)}일, {iso(keys[0])}~{iso(last)})")


if __name__ == "__main__":
    main()
