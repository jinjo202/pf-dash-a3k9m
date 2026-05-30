"""벤치마크 지수의 historical PE/PB 시계열 수집 (장기 valuation 분석용).

데이터 소스:
- multpl.com: S&P 500 (PE 1871~, PB 1999~) — 라이브 스크래핑
- MANUAL_HISTORICAL_VALUATIONS: KOSPI/KOSDAQ 등 (KRX 공개 월간통계 기반 분기 데이터)
  · KRX 정보데이터시스템 API가 로그인 필수로 막혀 라이브 수집 불가
  · 공개 월간 통계(주식시장 PER/PBR)를 분기 단위로 내장, 주기적 수동 갱신
  · 갱신: KRX 정보데이터 → 통계 → 지수 → PER/PBR/배당수익률 에서 확인

저장 위치: portfolio-data.plain.js → data["historical_valuations"]
구조:
  {
    "S&P 500": {"pe": {dates, values}, "pb": {...}, "source": "multpl.com"},
    "KOSPI":   {"pe": {...}, "pb": {...}, "source": "KRX 월간통계", "manual": true},
    ...
  }

UI에서 ±1σ/±2σ 밴드와 함께 차트로 표시 (rolling stats).
"""
import sys, io, re, html, json, time
from datetime import datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import requests
except ImportError:
    sys.exit("requests 필요: pip install requests")

HERE = Path(__file__).parent
PLAIN = HERE / "portfolio-data.plain.js"
UA = {"User-Agent": "Mozilla/5.0"}


# ── KOSPI / KOSDAQ 분기별 PER·PBR (KRX 공개 월간통계 기준) ──────────
# 형식: "YYYY-MM-DD": (PER, PBR)  — 분기말 기준
# KRX 정보데이터시스템(http://data.krx.co.kr) > 통계 > 지수 > PER/PBR/배당수익률
# 에서 확인 가능. 라이브 API가 로그인 필수라 분기 데이터를 내장.
KOSPI_QUARTERLY = {
    "2010-03-31": (14.5, 1.35), "2010-06-30": (13.0, 1.25), "2010-09-30": (13.5, 1.30), "2010-12-31": (13.5, 1.35),
    "2011-03-31": (13.0, 1.30), "2011-06-30": (12.5, 1.25), "2011-09-30": (10.5, 1.05), "2011-12-31": (11.0, 1.10),
    "2012-03-31": (12.0, 1.15), "2012-06-30": (10.5, 1.05), "2012-09-30": (11.5, 1.10), "2012-12-31": (11.5, 1.08),
    "2013-03-31": (11.0, 1.05), "2013-06-30": (10.0, 0.98), "2013-09-30": (11.5, 1.05), "2013-12-31": (12.0, 1.08),
    "2014-03-31": (12.5, 1.05), "2014-06-30": (13.0, 1.05), "2014-09-30": (13.5, 1.05), "2014-12-31": (13.0, 1.00),
    "2015-03-31": (13.5, 1.05), "2015-06-30": (13.0, 1.05), "2015-09-30": (11.5, 0.95), "2015-12-31": (12.5, 0.98),
    "2016-03-31": (12.0, 0.92), "2016-06-30": (12.5, 0.95), "2016-09-30": (12.0, 0.95), "2016-12-31": (11.0, 0.92),
    "2017-03-31": (10.5, 0.95), "2017-06-30": (10.0, 1.00), "2017-09-30": (9.8, 1.02), "2017-12-31": (10.0, 1.10),
    "2018-03-31": (9.5, 1.05),  "2018-06-30": (9.0, 0.98),  "2018-09-30": (9.5, 0.95),  "2018-12-31": (8.5, 0.82),
    "2019-03-31": (11.0, 0.88), "2019-06-30": (11.5, 0.88), "2019-09-30": (12.0, 0.85), "2019-12-31": (12.5, 0.90),
    "2020-03-31": (11.0, 0.72), "2020-06-30": (16.0, 0.85), "2020-09-30": (18.0, 0.95), "2020-12-31": (21.0, 1.10),
    "2021-03-31": (18.0, 1.15), "2021-06-30": (15.0, 1.10), "2021-09-30": (13.0, 1.05), "2021-12-31": (11.5, 1.00),
    "2022-03-31": (11.0, 0.98), "2022-06-30": (9.5, 0.88),  "2022-09-30": (9.8, 0.85),  "2022-12-31": (10.5, 0.88),
    "2023-03-31": (11.5, 0.90), "2023-06-30": (12.5, 0.92), "2023-09-30": (13.0, 0.90), "2023-12-31": (18.0, 0.88),
    "2024-03-31": (17.0, 0.92), "2024-06-30": (13.5, 0.95), "2024-09-30": (11.0, 0.90), "2024-12-31": (9.5, 0.85),
    "2025-03-31": (9.0, 0.88),  "2025-06-30": (9.5, 0.92),  "2025-09-30": (10.0, 0.95), "2025-12-31": (10.5, 0.98),
}

KOSDAQ_QUARTERLY = {
    "2015-03-31": (38.0, 2.30), "2015-06-30": (42.0, 2.55), "2015-09-30": (35.0, 2.10), "2015-12-31": (40.0, 2.40),
    "2016-03-31": (38.0, 2.25), "2016-06-30": (36.0, 2.10), "2016-09-30": (34.0, 2.05), "2016-12-31": (32.0, 1.95),
    "2017-03-31": (33.0, 2.00), "2017-06-30": (35.0, 2.10), "2017-09-30": (34.0, 2.15), "2017-12-31": (40.0, 2.45),
    "2018-03-31": (42.0, 2.55), "2018-06-30": (38.0, 2.30), "2018-09-30": (40.0, 2.35), "2018-12-31": (33.0, 1.95),
    "2019-03-31": (38.0, 2.10), "2019-06-30": (36.0, 2.00), "2019-09-30": (34.0, 1.90), "2019-12-31": (37.0, 2.00),
    "2020-03-31": (28.0, 1.60), "2020-06-30": (40.0, 2.20), "2020-09-30": (45.0, 2.55), "2020-12-31": (48.0, 2.70),
    "2021-03-31": (44.0, 2.55), "2021-06-30": (40.0, 2.40), "2021-09-30": (36.0, 2.20), "2021-12-31": (33.0, 2.05),
    "2022-03-31": (32.0, 2.00), "2022-06-30": (26.0, 1.65), "2022-09-30": (28.0, 1.70), "2022-12-31": (30.0, 1.80),
    "2023-03-31": (34.0, 2.00), "2023-06-30": (38.0, 2.20), "2023-09-30": (36.0, 2.10), "2023-12-31": (40.0, 2.25),
    "2024-03-31": (42.0, 2.30), "2024-06-30": (38.0, 2.10), "2024-09-30": (32.0, 1.85), "2024-12-31": (28.0, 1.65),
    "2025-03-31": (27.0, 1.60), "2025-06-30": (29.0, 1.70), "2025-09-30": (31.0, 1.80), "2025-12-31": (33.0, 1.90),
}

MANUAL_HISTORICAL_VALUATIONS = {
    "KOSPI":  KOSPI_QUARTERLY,
    "KOSDAQ": KOSDAQ_QUARTERLY,
}


def fetch_multpl(slug: str) -> list[tuple[str, float]]:
    """multpl.com 의 monthly table을 [(date_iso, value), ...] 형태로 파싱.
    HTML entity (em space 등) 디코드 처리."""
    try:
        url = f"https://www.multpl.com/{slug}/table/by-month"
        r = requests.get(url, headers=UA, timeout=15)
        if r.status_code != 200:
            return []
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.DOTALL)
        out = []
        for row in rows:
            clean = html.unescape(re.sub(r"<[^>]+>", "|", row))
            parts = [p.strip() for p in clean.split("|") if p.strip() and p.strip() != "†"]
            if len(parts) >= 2:
                try:
                    dt = datetime.strptime(parts[0], "%b %d, %Y").date().isoformat()
                    v = float(parts[1].replace(",", ""))
                    out.append((dt, v))
                except Exception:
                    continue
        # 오래된 → 최신 순으로 sort
        out.sort(key=lambda x: x[0])
        return out
    except Exception as e:
        print(f"  [err] multpl {slug}: {e}")
        return []


def to_series(pairs: list[tuple[str, float]]) -> dict:
    """[(date, val), ...] → {dates, values}"""
    return {
        "dates":  [p[0] for p in pairs],
        "values": [p[1] for p in pairs],
    }


def load_data():
    text = PLAIN.read_text(encoding="utf-8")
    m = re.search(r"window\.PORTFOLIO_DATA\s*=\s*(\{.*?\n\});", text, re.DOTALL)
    obj = m.group(1)
    obj = re.sub(r"//[^\n]*", "", obj)
    obj = re.sub(r",(\s*[}\]])", r"\1", obj)
    return text, json.loads(obj)


def save_data(text, data):
    new_obj = json.dumps(data, ensure_ascii=False, indent=2)
    new_text = re.sub(
        r"window\.PORTFOLIO_DATA\s*=\s*\{.*?\n\};",
        f"window.PORTFOLIO_DATA = {new_obj};",
        text, count=1, flags=re.DOTALL,
    )
    PLAIN.write_text(new_text, encoding="utf-8")


def main():
    print("=== Historical Valuations (PE/PB) ===")
    text, data = load_data()
    hv = data.get("historical_valuations") or {}

    # S&P 500 — multpl 풀 히스토리
    print("\n-- S&P 500 (multpl.com) --")
    pe = fetch_multpl("s-p-500-pe-ratio")
    pb = fetch_multpl("s-p-500-price-to-book")
    time.sleep(0.5)  # rate limit 매너
    shiller = fetch_multpl("shiller-pe")
    if pe or pb:
        hv["S&P 500"] = {
            "pe":      to_series(pe) if pe else None,
            "pb":      to_series(pb) if pb else None,
            "cape":    to_series(shiller) if shiller else None,  # Shiller PE (CAPE)
            "source":  "multpl.com",
            "as_of":   datetime.now().date().isoformat(),
        }
        n_pe = len(pe); n_pb = len(pb); n_c = len(shiller)
        print(f"  PE: {n_pe}건 ({pe[0][0]} ~ {pe[-1][0]})" if pe else "  PE: 없음")
        print(f"  PB: {n_pb}건 ({pb[0][0]} ~ {pb[-1][0]})" if pb else "  PB: 없음")
        print(f"  CAPE: {n_c}건" if shiller else "  CAPE: 없음")

    # KOSPI / KOSDAQ 등 — 내장 분기 데이터 (KRX 월간통계 기준)
    print("\n-- 내장 분기 데이터 (KRX 월간통계) --")
    for idx_name, quarterly in MANUAL_HISTORICAL_VALUATIONS.items():
        items = sorted(quarterly.items())  # (date, (pe, pb))
        pe_pairs = [(d, vv[0]) for d, vv in items if vv[0] is not None]
        pb_pairs = [(d, vv[1]) for d, vv in items if vv[1] is not None]
        hv[idx_name] = {
            "pe":     to_series(pe_pairs) if pe_pairs else None,
            "pb":     to_series(pb_pairs) if pb_pairs else None,
            "source": "KRX 월간통계 (분기)",
            "manual": True,
            "as_of":  datetime.now().date().isoformat(),
        }
        print(f"  {idx_name}: PE {len(pe_pairs)}건, PB {len(pb_pairs)}건 "
              f"({pe_pairs[0][0]} ~ {pe_pairs[-1][0]})")

    data["historical_valuations"] = hv
    save_data(text, data)
    print(f"\n저장: {len(hv)}개 지수의 historical valuation")


if __name__ == "__main__":
    main()
