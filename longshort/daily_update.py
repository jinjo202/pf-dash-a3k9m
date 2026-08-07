# -*- coding: utf-8 -*-
"""
롱숏포트 기계적 일일 업데이트 (GitHub Actions용, 순수 stdlib, 멱등)

하는 일: 야후 종가 수집 -> data.js의 레그 last 갱신 -> 공백 거래일 NAV 백필(navHistory 추가)
        -> meta.asOfPrice/lastUpdated/usdkrw 갱신. 변경 없으면 파일을 건드리지 않고 exit 0.
안 하는 일(Claude 스케줄 작업 몫): 아이디어 작성, 레짐 서사/포지션 변경, 스톱 집행 판단.

전제: data.js의 레그는 한 줄 객체(side/ticker/weightPct/last 포함), navHistory 항목도 한 줄.
주의: 야후 chart API는 장중 미확정 바를 내려줄 수 있어 오늘(KST) 날짜 바는 버린다.
"""
import json, re, ssl, sys, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

UA = {"User-Agent": "Mozilla/5.0"}
CTX = ssl.create_default_context()
KST = timezone(timedelta(hours=9))
DATA = "data.js"

def fetch_series(ticker, rng="3mo"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}"
           f"?range={rng}&interval=1d")
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30, context=CTX) as r:
        j = json.load(r)
    res = j["chart"]["result"][0]
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")
    out = {}
    for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        if c is None or c <= 0:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        if d >= today_kst:  # 장중 미확정 바 방지 (07:15 KST 실행 기준 안전)
            continue
        out[d] = c
    return out

def fmt_px(v):
    return str(int(round(v))) if abs(v - round(v)) < 1e-9 or abs(v) >= 1000 else f"{v:.2f}"

def main():
    src = open(DATA, encoding="utf-8").read()
    lines = src.split("\n")

    # ---- 파스: 북/페어 상태/레그/navHistory 블록 ----
    leg_re = re.compile(r'side:\s*"(LONG|SHORT)".*?ticker:\s*"([^"]+)".*?weightPct:\s*([\d.]+).*?last:\s*([\d.]+)')
    books = {}          # id -> {"legs": [(idx, side, ticker, w, last, open)], "nav_end": idx, "last_nav": float, "nav_dates": set, "asof": str}
    book = None
    pair_open = True
    in_nav = False
    for i, ln in enumerate(lines):
        m = re.search(r'id:\s*"(neutral|directional)"', ln)
        if m:
            book = m.group(1)
            books[book] = {"legs": [], "nav_end": None, "last_nav": None, "nav_dates": set(),
                           "asof": None, "nav_last_idx": None}
            continue
        if book is None:
            continue
        b = books[book]
        ma = re.search(r'asOfPrice:\s*"([\d-]+)"', ln)
        if ma:
            b["asof"] = ma.group(1)
        if re.search(r'status:\s*"', ln):
            pair_open = 'status: "OPEN"' in ln
        if "navHistory: [" in ln:
            in_nav = True
            continue
        if in_nav:
            me = re.search(r'\{\s*date:\s*"([\d-]+)",\s*nav:\s*([\d.]+)', ln)
            if me:
                b["nav_dates"].add(me.group(1))
                b["last_nav"] = float(me.group(2))
                b["nav_last_idx"] = i
            if re.match(r'\s*\]', ln):
                b["nav_end"] = i
                in_nav = False
            continue
        ml = leg_re.search(ln)
        if ml:
            b["legs"].append({"idx": i, "side": ml.group(1), "ticker": ml.group(2),
                              "w": float(ml.group(3)), "last": float(ml.group(4)), "open": pair_open})

    for bid in ("neutral", "directional"):
        if bid not in books or not books[bid]["legs"] or books[bid]["nav_end"] is None:
            sys.exit(f"파스 실패: {bid} 북 구조를 찾지 못함 — data.js 형식 확인 필요")

    tickers = sorted({l["ticker"] for b in books.values() for l in b["legs"]} | {"KRW=X"})
    px = {}
    for t in tickers:
        try:
            px[t] = fetch_series(t)
        except Exception as e:
            sys.exit(f"시세 수집 실패 {t}: {e} — 갱신 중단(파일 미변경)")
        if not px[t]:
            sys.exit(f"시세 없음 {t} — 갱신 중단")

    # ---- 북별 NAV 백필 ----
    new_navs = {}   # bid -> [(date, nav)]
    latest_close = {t: px[t][max(px[t])] for t in px}
    for bid, b in books.items():
        asof = b["asof"]
        cal = sorted({d for l in b["legs"] if l["open"] for d in px[l["ticker"]] if d > asof})
        prev_date = {l["ticker"]: max((d for d in px[l["ticker"]] if d <= asof), default=None)
                     for l in b["legs"]}
        nav = b["last_nav"]
        rows = []
        for d in cal:
            day_pnl = 0.0  # %p of NAV
            for l in b["legs"]:
                if not l["open"]:
                    continue
                s = px[l["ticker"]]
                if d not in s or prev_date[l["ticker"]] is None:
                    continue
                r = s[d] / s[prev_date[l["ticker"]]] - 1.0
                day_pnl += (1 if l["side"] == "LONG" else -1) * l["w"] * r
                prev_date[l["ticker"]] = d
            nav *= (1.0 + day_pnl / 100.0)
            if d not in b["nav_dates"]:
                rows.append((d, round(nav, 2)))
        new_navs[bid] = rows

    if not any(new_navs.values()):
        print("신규 거래일 없음 — 변경 없이 종료 (휴장 또는 이미 최신)")
        return

    # ---- 라인 수정 (아래에서 위로: 인덱스 보존) ----
    max_date = max(d for rows in new_navs.values() for d, _ in rows) if any(new_navs.values()) else None
    usdkrw = latest_close.get("KRW=X")
    edits = []  # (idx, new_line) / navHistory 삽입은 별도
    for bid, b in books.items():
        for l in b["legs"]:
            t = l["ticker"]
            edits.append((l["idx"], re.sub(r'last:\s*[\d.]+', f'last: {fmt_px(latest_close[t])}', lines[l["idx"]])))
    for i, ln in enumerate(lines):
        if re.search(r'asOfPrice:\s*"', ln) and max_date:
            edits.append((i, re.sub(r'asOfPrice:\s*"[\d-]+"', f'asOfPrice: "{max_date}"', ln)))
        if re.search(r'lastUpdated:\s*"', ln):
            today = datetime.now(KST).strftime("%Y-%m-%d")
            edits.append((i, re.sub(r'lastUpdated:\s*"[\d-]+"', f'lastUpdated: "{today}"', ln)))
        if re.search(r'usdkrw:\s*[\d.]+', ln) and usdkrw:
            edits.append((i, re.sub(r'usdkrw:\s*[\d.]+', f'usdkrw: {usdkrw:.2f}', ln)))
    for idx, new in edits:
        lines[idx] = new

    # navHistory 삽입 (뒤쪽 북부터 — 인덱스 시프트 방지)
    for bid in sorted(books, key=lambda k: books[k]["nav_end"], reverse=True):
        rows = new_navs[bid]
        if not rows:
            continue
        b = books[bid]
        last_idx = b["nav_last_idx"]
        if last_idx is not None and not lines[last_idx].rstrip().endswith(","):
            lines[last_idx] = lines[last_idx].rstrip() + ","
        indent = re.match(r'\s*', lines[last_idx]).group(0) if last_idx else "      "
        ins = [f'{indent}{{ date: "{d}", nav: {n:.2f} }},' for d, n in rows]
        ins[-1] = ins[-1].rstrip(",")
        lines[b["nav_end"]:b["nav_end"]] = ins

    open(DATA, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    for bid, rows in new_navs.items():
        if rows:
            print(f"{bid}: {len(rows)}거래일 추가 ({rows[0][0]} ~ {rows[-1][0]}), NAV {rows[-1][1]}")
    print(f"asOfPrice={max_date}, USDKRW={usdkrw:.2f}")

if __name__ == "__main__":
    main()
