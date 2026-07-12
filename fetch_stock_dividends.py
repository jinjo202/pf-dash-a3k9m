"""
fetch_stock_dividends.py — 감시목록 개별주식의 DART 배당공시 → 캘린더 '보유 분배금' 반영

calendar.html '🔒 보유 분배금' 레이어(calendar-holdings)에, 보유(비공개) 개별주식의
실제 '현금ㆍ현물배당결정' 공시 데이터(1주당 배당금·배당기준일·지급예정일)를 추가한다.
ETF 분배금(fetch_calendar_dividends.py, yfinance) 이후에 실행 → 같은 파일에 병합.

파이프라인(calendar-update.yml):
    fetch_calendar_dividends.py  → calendar-holdings.plain.js (ETF, yfinance)
    fetch_stock_dividends.py     → calendar-holdings.plain.js 에 개별주식 배당 병합  ← 이 파일
    encrypt_calendar.py encrypt  → calendar-holdings.js (암호화, commit)

자급자족(kind_dividend_watch 의존 없음 — 러너에 없음). requests만 필요.
감시목록은 dividend-watch.plain.js(gitignored) 또는 dividend-watch.js(암호화, PORTFOLIO_PASSWORD).
DART 키는 env DART_API_KEY.
"""
import base64
import datetime as dt
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import requests

HERE = Path(__file__).parent
HOLD = HERE / "calendar-holdings.plain.js"
WATCH_PLAIN = HERE / "dividend-watch.plain.js"
WATCH_ENC = HERE / "dividend-watch.js"

TODAY = dt.date.today()
WIN_BACK, WIN_FWD = 60, 150
BASE = "https://opendart.fss.or.kr/api"
DIV_KW = ["현금ㆍ현물배당결정", "현금·현물배당결정"]
MQ_KW = "주주명부폐쇄기간또는기준일설정"   # 맥쿼리인프라(인프라펀드): 배당결정 대신 반기 기준일설정


def _clean(s: str) -> str:
    return s.lstrip("﻿").strip().lstrip("﻿")


def load_watch() -> dict:
    """감시목록 {code:name}. 평문 우선, 없으면 암호화본 복호화(PORTFOLIO_PASSWORD)."""
    if WATCH_PLAIN.exists():
        text = WATCH_PLAIN.read_text(encoding="utf-8")
    else:
        pw = os.environ.get("PORTFOLIO_PASSWORD") or (
            _clean((HERE / ".password").read_text(encoding="utf-8-sig")) if (HERE / ".password").exists() else None)
        if not pw or not WATCH_ENC.exists():
            sys.exit("감시목록 없음: dividend-watch.plain.js 또는 dividend-watch.js(+PORTFOLIO_PASSWORD)")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        from cryptography.hazmat.primitives import hashes
        blob = base64.b64decode(re.search(r'ENCRYPTED\s*=\s*"([^"]+)"', WATCH_ENC.read_text(encoding="utf-8")).group(1))
        salt, nonce, ct = blob[:16], blob[16:28], blob[28:]
        key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200_000).derive(pw.encode())
        text = AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
    m = re.search(r"window\.DIVIDEND_WATCH\s*=\s*(\{.*?\n\});", text, re.DOTALL)
    return json.loads(m.group(1))["stocks"]


def corp_map(key: str) -> dict:
    r = requests.get(f"{BASE}/corpCode.xml", params={"crtfc_key": key}, timeout=30)
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(zf.read([n for n in zf.namelist() if n.endswith(".xml")][0]))
    out = {}
    for e in root.iter("list"):
        sc = (e.findtext("stock_code") or "").strip()
        cc = (e.findtext("corp_code") or "").strip()
        if sc and cc:
            out[sc] = cc
    return out


def dart_list(key, cc, kw_list):
    r = requests.get(f"{BASE}/list.json", params={
        "crtfc_key": key, "corp_code": cc, "bgn_de": f"{TODAY.year}0101",
        "end_de": f"{TODAY.year}1231", "pblntf_ty": "I", "page_no": 1, "page_count": 100}, timeout=30).json()
    if r.get("status") != "000":
        return []
    return [d for d in r.get("list", []) if any(k in d["report_nm"] for k in kw_list)]


def doc_detail(key, rno) -> dict:
    r = requests.get(f"{BASE}/document.xml", params={"crtfc_key": key, "rcept_no": rno}, timeout=20)
    try:
        t = zipfile.ZipFile(io.BytesIO(r.content)).read(f"{rno}.xml").decode("utf-8", "replace")
    except Exception:
        return {}
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    g = lambda p: (re.search(p, t).group(1).strip() if re.search(p, t) else None)
    return {
        "per": g(r"1주당 배당금\(원\)\s*보통주식\s*([\d,]+)"),
        "ex": g(r"배당기준일\s*(\d{4}-\d{2}-\d{2})"),
        "pay": g(r"배당금지급 예정일자\s*(\d{4}-\d{2}-\d{2})"),
        "std": g(r"(?:^|[^배당])기준일\s*(\d{4}-\d{2}-\d{2})"),   # 맥쿼리 기준일설정용
    }


def in_win(d: str) -> bool:
    try:
        x = dt.date.fromisoformat(d)
    except (ValueError, TypeError):
        return False
    return (TODAY - dt.timedelta(days=WIN_BACK)) <= x <= (TODAY + dt.timedelta(days=WIN_FWD))


def _ev(name, code, date, kind, amount, note, disp_name=None):
    return {"date": date, "type": "dividend", "region": "KR", "ticker": f"{code}.KS",
            "name": disp_name or name, "kind": kind, "amount": amount, "freq": "",
            "held": True, "released": (dt.date.fromisoformat(date) <= TODAY),
            "verified": True, "src": "dart", "note": note}


def _with_t1(events, seen, name, code, ex_date, amount):
    """미래 배당기준일이면 T-1 리마인드 이벤트를 추가(중복 방지)."""
    ex = dt.date.fromisoformat(ex_date)
    if ex > TODAY:                          # 기준일이 미래일 때만 T-1 리마인드
        t1 = (ex - dt.timedelta(days=1)).isoformat()
        k = (name, t1, "t1")
        if in_win(t1) and k not in seen:
            seen.add(k)
            events.append(_ev(name, code, t1, "ex", amount,
                              f"D-1 · 내일({ex_date}) 배당기준일 · 1주당 {amount}",
                              disp_name=f"{name} 배당기준일 D-1"))


def build_events(key, watch) -> list:
    s2c = corp_map(key)
    events, seen = [], set()
    for code, name in watch.items():
        cc = s2c.get(code)
        if not cc:
            print(f"  skip {name}({code}): corp_code 없음"); continue
        # 맥쿼리인프라: 배당결정 없음 → 기준일설정을 분배 기준일(ex)로
        if code == "088980":
            for d in dart_list(key, cc, [MQ_KW]):
                det = doc_detail(key, d["rcept_no"])
                ex = det.get("std")
                if ex and in_win(ex):
                    k = (name, ex, "ex")
                    if k not in seen:
                        seen.add(k); events.append(_ev(name, code, ex, "ex", "분배(금액 미공시)", f"분배 기준일 · 공시 {d['rcept_dt']}"))
                    _with_t1(events, seen, name, code, ex, "분배(금액 미공시)")
            continue
        for d in dart_list(key, cc, DIV_KW):
            det = doc_detail(key, d["rcept_no"])
            per = det.get("per")
            amt = f"₩{per}" if per else "배당"
            if det.get("ex") and in_win(det["ex"]):
                k = (name, det["ex"], "ex")
                if k not in seen:
                    seen.add(k); events.append(_ev(name, code, det["ex"], "ex", amt, f"배당기준일 · 1주당 {amt} · 공시 {d['rcept_dt']}"))
                _with_t1(events, seen, name, code, det["ex"], amt)
            if det.get("pay") and in_win(det["pay"]):
                k = (name, det["pay"], "pay")
                if k not in seen:
                    seen.add(k); events.append(_ev(name, code, det["pay"], "pay", amt, f"배당금 지급 · 1주당 {amt}"))
    events.sort(key=lambda e: e["date"])
    return events


def merge_into_holdings(stock_events: list):
    """calendar-holdings.plain.js 에 병합(기존 src=dart 제거 후 재추가 → 멱등)."""
    if HOLD.exists():
        text = HOLD.read_text(encoding="utf-8")
        m = re.search(r"window\.CALENDAR_HOLDINGS\s*=\s*(\{.*\});", text, re.DOTALL)
        payload = json.loads(m.group(1)) if m else {}
    else:
        payload = {"as_of": TODAY.isoformat(), "note": "", "skipped": [], "events": []}
    evs = [e for e in payload.get("events", []) if e.get("src") != "dart"]  # 이전 주식배당 제거
    evs.extend(stock_events)
    evs.sort(key=lambda e: e["date"])
    payload["events"] = evs
    payload["as_of"] = TODAY.isoformat()
    out = ("// 보유 분배금 평문 (gitignored) — encrypt_calendar.py encrypt 로 calendar-holdings.js 갱신\n"
           "// fetch_calendar_dividends.py(ETF) + fetch_stock_dividends.py(개별주식 배당) 병합 생성\n"
           f"window.CALENDAR_HOLDINGS = {json.dumps(payload, ensure_ascii=False, indent=2)};\n")
    HOLD.write_text(out, encoding="utf-8")


def main():
    key = os.environ.get("DART_API_KEY")
    if not key:
        # 로컬 폴백: kind_dividend_watch/.env
        envf = HERE / "kind_dividend_watch" / ".env"
        if envf.exists():
            m = re.search(r"DART_API_KEY=(\S+)", envf.read_text(encoding="utf-8"))
            key = m.group(1) if m else None
    if not key:
        sys.exit("DART_API_KEY 없음 (env 또는 kind_dividend_watch/.env)")
    watch = load_watch()
    events = build_events(key, watch)
    merge_into_holdings(events)
    print(f"생성: 개별주식 배당 이벤트 {len(events)}건 → calendar-holdings.plain.js 병합")
    for e in events:
        print(f"  {e['date']} {e['name']} {e['kind']} {e['amount']}")


if __name__ == "__main__":
    main()
