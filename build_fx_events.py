"""
build_fx_events.py — FX 포워드 만기 캘린더 이벤트 생성 (보유 헤지 포지션, 암호화 레이어)

FX_FORWARDS 리스트(계약ID·기초자산·통화·명목USD·만기)를 캘린더 이벤트로 변환해
calendar-holdings.plain.js(평문, gitignored)에 병합한다. 실제 헤지 포지션 크기가
드러나므로 반드시 암호화(encrypt_calendar.py encrypt)해서 커밋한다 — 평문 커밋 금지.

만기일 자체를 이벤트로 넣고, 캘린더 UI가 T-2(만기 2일 전)부터 페이지 상단
알림 배너로 노출한다(fxAlertDays=2, calendar.html 쪽 로직).

갱신 방법: FX 포지션이 바뀌면 아래 FX_FORWARDS 리스트를 교체하고 재실행.
    python build_fx_events.py
    python encrypt_calendar.py encrypt
    git add calendar-holdings.js && git commit ... && git push
(평문 calendar-holdings.plain.js는 절대 커밋하지 않는다 — .gitignore 확인됨)
"""
import io
import json
import re
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = Path(__file__).parent
PLAIN = HERE / "calendar-holdings.plain.js"

# ID, 기초자산(ETF/펀드), 통화, 명목금액(원통화 표시 단위 그대로), 만기일
FX_FORWARDS = [
    ("420001211", "STATE STREET TECHNOLOGY SELECT ETF",           "USD", 10_454_037.46, "2026-08-10"),
    ("420001215", "iShares Core MSCI Emerging Markets ETF",       "USD", 13_699_461.55, "2026-07-13"),
    ("420000261", "DB X-TRACKERS DAX UCITS ETF",                  "EUR",  6_487_600.00, "2026-08-11"),
    ("420001217", "T Rowe Price International Equity ETF",        "USD", 11_074_320.61, "2026-09-14"),
    ("420001220", "iShares FTSE MIB ETF",                         "EUR",  2_992_358.89, "2026-09-30"),
    ("420000830", "THREADNEEDLE EUROPEAN SELECT FUND",            "EUR",  2_397_214.35, "2026-10-08"),
    ("420001145", "SS Industrial Select SPDR ETF",                "USD", 14_913_720.00, "2026-10-15"),
    ("420001220", "iShares FTSE MIB ETF",                         "EUR",  3_115_800.00, "2026-10-16"),
    ("420001235", "Fidelity Fundamental Small-Mid Cap ETF",       "USD",  6_731_744.22, "2026-10-30"),
    ("420001241", "Invesco Nasdaq 100 ETF (QQQM)",                "USD",  7_985_296.55, "2026-11-23"),
    ("420000998", "Fidelity European Dividend Fund",              "EUR",  5_156_962.09, "2026-11-25"),
    ("420000085", "iShares MSCI Emerging Markets ETF",             "USD", 17_160_000.00, "2026-11-25"),
    ("420001164", "Dimensional International Markets Core ETF",   "USD",  7_555_000.00, "2026-12-03"),
    ("420001243", "Invesco RAFI Strategic US ETF",                "USD",  8_019_171.62, "2026-12-07"),
    ("420000776", "Vanguard S&P 500 ETF",                         "USD",  9_814_481.21, "2026-12-16"),
    ("420001207", "Dimensional International Value ETF",         "USD", 13_712_854.24, "2027-01-13"),
]

FX_ALERT_DAYS = 2   # T-2부터 페이지 상단 배너 노출(calendar.html에서 사용)


def make_events():
    out = []
    for cid, name, ccy, amt, maturity in FX_FORWARDS:
        out.append({
            "date": maturity,
            "type": "fx",
            "region": "GL",
            "ticker": cid,
            "name": name,
            "ccy": ccy,
            "notional": round(amt, 2),
            "importance": 3,
            "held": True,
            "released": False,
            "verified": True,
            "note": f"FX 포워드 만기(계약 {cid}) — 헤지 롤오버 여부 결정 필요. T-{FX_ALERT_DAYS}일부터 알림.",
        })
    return out


def main():
    if not PLAIN.exists():
        sys.exit(f"평문 없음: {PLAIN.name} (encrypt_calendar.py decrypt 먼저 실행)")
    text = PLAIN.read_text(encoding="utf-8")
    m = re.search(r"window\.CALENDAR_HOLDINGS\s*=\s*(\{.*\});", text, re.DOTALL)
    if not m:
        sys.exit("CALENDAR_HOLDINGS 블록 못 찾음")
    data = json.loads(m.group(1))

    # 기존 fx 이벤트 전부 제거 후 재생성(전량 교체 — 리스트가 최신 포지션 스냅샷이므로)
    kept = [e for e in data.get("events", []) if e.get("type") != "fx"]
    fx_events = make_events()
    data["events"] = kept + fx_events
    data["fx_alert_days"] = FX_ALERT_DAYS

    out = (
        "// 보유 분배금 + FX 포워드 만기 평문 (gitignored) — encrypt_calendar.py encrypt 로 calendar-holdings.js 갱신\n"
        f"window.CALENDAR_HOLDINGS = {json.dumps(data, ensure_ascii=False, indent=2)};\n"
    )
    PLAIN.write_text(out, encoding="utf-8")
    print(f"병합 완료: fx 이벤트 {len(fx_events)}건 (기존 {len(kept)}건 유지) · 총 {len(data['events'])}건")
    print("다음: python encrypt_calendar.py encrypt")


if __name__ == "__main__":
    main()
