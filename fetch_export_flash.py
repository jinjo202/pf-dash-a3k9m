"""
fetch_export_flash.py — 한국 수출 '신속 잠정치' 자동 수집 (관세청 10일단위 API)

관세청 '수출 주요품목별 10일 단위 잠정치'(data.go.kr 15157908)로 최신월 잠정
수출금액(주요 10품목)을 받아 YoY를 계산하고 export-flash.js(window.EXPORT_FLASH)를
만든다. 캘린더 세부항목 모달의 ⚡신속 잠정치 배너가 이 파일을 우선 사용한다
(없으면 calendar-data.js의 수기 flash 폴백).

공표: 1~10일치=11일, 1~20일치=21일, 1~말일치=익월 1일. 상세 HS 확정(익월 15일)보다
최대 2주 빠름 — 수출데이터의 주식시장 신속성 요구를 메우는 레이어.

엔드포인트: https://apis.data.go.kr/1220000/prlstMmUtPrviExpAcrs/getPrlstMmUtPrviExpAcrs
응답: itemUsdAmt00(전체)~10(가전), priodDt/priodMon/priodYear. 단위 천달러.
요청 파라미터는 문서 미공개 → 후보 조합을 순차 시도(첫 성공 조합 로깅).

키: TRADE_API_KEY (기존 관세청 키 공유). 403(미승인/반영대기)·수집 0건이면
파일 미갱신 후 종료(수기 폴백 유지).
"""
import datetime as dt
import io
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
OUT = HERE / "export-flash.js"
API = "https://apis.data.go.kr/1220000/prlstMmUtPrviExpAcrs/getPrlstMmUtPrviExpAcrs"
KEY = os.environ.get("TRADE_API_KEY")

# 응답 필드 → 캘린더 SECTORS 키 매핑 (스키마 확정: itemUsdAmt00~10)
FIELD_MAP = {
    "itemUsdAmt00": ("total",     "전체"),
    "itemUsdAmt01": ("semi",      "반도체"),
    "itemUsdAmt02": ("steel",     "철강제품"),
    "itemUsdAmt03": ("auto",      "승용차"),
    "itemUsdAmt04": ("petroprod", "석유제품"),
    "itemUsdAmt05": ("wireless",  "무선통신기기"),
    "itemUsdAmt06": ("ship",      "선박"),
    "itemUsdAmt07": ("autoparts", "자동차부품"),
    "itemUsdAmt08": ("computer",  "컴퓨터주변기기"),
    "itemUsdAmt09": ("precision", "정밀기기"),
    "itemUsdAmt10": ("appliance", "가전제품"),
}


def _call(params):
    q = {"serviceKey": KEY, "numOfRows": "600", "pageNo": "1"}
    q.update(params)
    url = API + "?" + urllib.parse.urlencode(q, safe="")
    with urllib.request.urlopen(url, timeout=40) as r:
        return ET.fromstring(r.read().decode("utf-8", "replace"))


def _items(root):
    out = []
    for it in root.findall(".//item"):
        row = {ch.tag: (ch.text or "").strip() for ch in it}
        if row:
            out.append(row)
    return out


def fetch_rows():
    """파라미터 조합 후보를 순차 시도 → (rows, 사용한 조합)."""
    now = dt.date.today()
    y, ly = str(now.year), str(now.year - 1)
    candidates = [
        {},                                        # 무파라미터(전체 반환형 GW도 흔함)
        {"priodYear": y},
        {"priodYear": ly},                         # 전년(YoY용) — 성공 조합 확인용
        {"strtYymm": f"{now.year-1}01", "endYymm": f"{now.year}{now.month:02d}"},
        {"srchYear": y},
    ]
    rows, used = [], None
    for cand in candidates:
        try:
            root = _call(cand)
        except urllib.error.HTTPError as e:
            hint = {401: "키 미인식", 403: "미승인/반영대기"}.get(e.code, "")
            print(f"  {cand or '{bare}'} -> HTTP {e.code} {hint}")
            if e.code in (401, 403):
                return None, None      # 인증 문제 — 조합 바꿔도 소용없음
            continue
        except Exception as e:
            print(f"  {cand} -> {str(e)[:60]}")
            continue
        rc = root.findtext(".//resultCode")
        got = _items(root)
        print(f"  {cand or '{bare}'} -> resultCode={rc} rows={len(got)}")
        if got:
            rows, used = got, cand
            break
    return rows, used


def norm_mon(row):
    """priodMon/priodYear/priodDt → 'YYYY.MM'."""
    mon = row.get("priodMon", "")
    if mon:
        digits = mon.replace(".", "").replace("-", "")
        if len(digits) >= 6:
            return f"{digits[:4]}.{digits[4:6]}"
        yr = row.get("priodYear", "")
        if yr and len(digits) >= 1:
            return f"{yr}.{int(digits):02d}"
    dtv = row.get("priodDt", "").replace(".", "").replace("-", "")
    if len(dtv) >= 6:
        return f"{dtv[:4]}.{dtv[4:6]}"
    return None


def main():
    if not KEY:
        print("TRADE_API_KEY 없음 — 스킵.")
        return
    rows, used = fetch_rows()
    if not rows:
        print("수집 0건(미승인/반영대기 가능) — export-flash.js 미갱신(수기 flash 폴백 유지).")
        return

    # 월별로 '해당 월의 마지막 조회일자' 행 채택 (10일<20일<말일 누계 중 최신)
    bymon = {}
    for r in rows:
        mon = norm_mon(r)
        if not mon:
            continue
        key = r.get("priodDt", "") or mon
        if mon not in bymon or key > bymon[mon].get("priodDt", ""):
            bymon[mon] = r
    if not bymon:
        print("월 파싱 실패 — 필드 확인 필요:", list(rows[0].keys()))
        return

    mons = sorted(bymon.keys())
    latest = mons[-1]
    ly, lm = int(latest[:4]) - 1, latest[5:7]
    prior = f"{ly}.{lm}"

    def val(mon, field):
        r = bymon.get(mon)
        if not r:
            return None
        raw = (r.get(field) or "").replace(",", "").strip()
        if not raw:
            return None
        try:
            return float(raw) / 1e6   # 천달러(콤마 포함 문자열) → $10억
        except ValueError:
            return None

    items = {}
    for field, (k, nm) in FIELD_MAP.items():
        cur, prev = val(latest, field), val(prior, field)
        if cur is None or not cur:
            continue
        yoy = round((cur / prev - 1) * 100, 1) if prev else None
        items[k] = {"val": round(cur, 2), "yoy": yoy, "name": nm}

    if not items:
        print("품목 값 없음 — 미갱신. 첫 행 필드:", list(rows[0].keys()))
        return

    latest_dt = bymon[latest].get("priodDt", "")
    payload = {
        "as_of": dt.date.today().isoformat(),
        "month": latest,
        "period_end": latest_dt,
        "verified": True,
        "source": "관세청 수출 주요품목별 10일단위 잠정치(자동)",
        "note": f"관세청 10일단위 잠정({latest} 누계, ~{latest_dt}). 상세 HS 확정(익월 15일) 전 신속치 — YoY는 전년 동월 같은 집계 기준.",
        "items": items,
        "months_available": mons[-6:],
        "param_used": used,
    }
    OUT.write_text(
        "// 한국 수출 신속 잠정치(주요품목 10일단위) — fetch_export_flash.py 자동생성.\n"
        f"window.EXPORT_FLASH = {json.dumps(payload, ensure_ascii=False, indent=1)};\n",
        encoding="utf-8",
    )
    print(f"생성: {OUT.name} · {latest} 누계(~{latest_dt}) · 품목 {len(items)}개 · 조합 {used}")
    for k, v in items.items():
        print(f"  {v['name']:8} ${v['val']}B  YoY {v['yoy']}%")


if __name__ == "__main__":
    main()
