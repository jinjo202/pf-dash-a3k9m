"""벤치마크 지수의 historical PE/PB 시계열 수집 (장기 valuation 분석용).

데이터 소스:
- multpl.com: S&P 500 (PE 1871~, PB 1999~)
- 향후 추가 예정: KOSPI, NASDAQ, MSCI 등

저장 위치: portfolio-data.plain.js → data["historical_valuations"]
구조:
  {
    "S&P 500": {
      "pe": {"dates": [...], "values": [...]},   # monthly
      "pb": {"dates": [...], "values": [...]},   # annual (multpl 제약)
      "source": "multpl.com"
    },
    ...
  }

UI에서 ±1σ/±2σ 밴드와 함께 차트로 표시 (1년 rolling stats).
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

    data["historical_valuations"] = hv
    save_data(text, data)
    print(f"\n저장: {len(hv)}개 지수의 historical valuation")


if __name__ == "__main__":
    main()
