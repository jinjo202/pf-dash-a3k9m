"""
fetch_etf_holdings.py — 각 ETF의 상위 N 구성종목 수집

yfinance `Ticker.funds_data.top_holdings`를 시도.
미국 ETF(SPDR, iShares, Vanguard 등)는 잘 받히고
한국 ETF(KODEX, KoAct 등)는 데이터 없을 가능성 큼 — 그 경우 N/A 처리.
"""
import json
import re
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

try:
    import yfinance as yf
except ImportError:
    sys.exit("필요: pip install yfinance")

HERE = Path(__file__).parent
PLAIN = HERE / "portfolio-data.plain.js"

# yfinance에 fund holdings가 없는 ETF/펀드용 수동 fallback
# (한국 ETF + KODEX S&P500(H) + FFSM + XDAX 등) — 운용사 fact sheet 기반 큐레이션
MANUAL_HOLDINGS = {
    "삼성 ESG 착한 책임투자": [
        {"name": "삼성전자", "weight": 0.225},
        {"name": "SK하이닉스", "weight": 0.075},
        {"name": "LG에너지솔루션", "weight": 0.034},
        {"name": "삼성바이오로직스", "weight": 0.030},
        {"name": "현대차", "weight": 0.026},
    ],
    "마이다스 책임투자": [
        {"name": "삼성전자", "weight": 0.240},
        {"name": "SK하이닉스", "weight": 0.080},
        {"name": "LG에너지솔루션", "weight": 0.035},
        {"name": "삼성바이오로직스", "weight": 0.028},
        {"name": "현대차", "weight": 0.025},
    ],
    "KODEX 200 ETF": [
        {"name": "삼성전자", "weight": 0.282},
        {"name": "SK하이닉스", "weight": 0.071},
        {"name": "LG에너지솔루션", "weight": 0.035},
        {"name": "삼성바이오로직스", "weight": 0.030},
        {"name": "현대차", "weight": 0.025},
    ],
    "KODEX 코스닥150 ETF": [
        {"name": "HLB", "weight": 0.048},
        {"name": "알테오젠", "weight": 0.045},
        {"name": "에코프로비엠", "weight": 0.040},
        {"name": "에코프로", "weight": 0.037},
        {"name": "리노공업", "weight": 0.027},
    ],
    "KODEX AI전력핵심설비 ETF": [
        {"name": "HD현대일렉트릭", "weight": 0.115},
        {"name": "LS ELECTRIC", "weight": 0.095},
        {"name": "효성중공업", "weight": 0.080},
        {"name": "한국전력기술", "weight": 0.070},
        {"name": "두산에너빌리티", "weight": 0.062},
    ],
    "KODEX 자동차": [
        {"name": "현대차", "weight": 0.247},
        {"name": "기아", "weight": 0.165},
        {"name": "현대모비스", "weight": 0.118},
        {"name": "한온시스템", "weight": 0.048},
        {"name": "한국타이어앤테크놀로지", "weight": 0.045},
    ],
    "KoAct 바이오헬스케어액티브": [
        {"name": "삼성바이오로직스", "weight": 0.098},
        {"name": "알테오젠", "weight": 0.080},
        {"name": "HLB", "weight": 0.060},
        {"name": "셀트리온", "weight": 0.058},
        {"name": "에이비엘바이오", "weight": 0.042},
    ],
    "Hanaro 원자력 iSelect": [
        {"name": "두산에너빌리티", "weight": 0.150},
        {"name": "한국전력", "weight": 0.105},
        {"name": "한국전력기술", "weight": 0.082},
        {"name": "한전KPS", "weight": 0.062},
        {"name": "우리기술", "weight": 0.052},
    ],
    "Plus K-방산 ETF": [
        {"name": "한화에어로스페이스", "weight": 0.222},
        {"name": "한국항공우주", "weight": 0.140},
        {"name": "현대로템", "weight": 0.128},
        {"name": "LIG넥스원", "weight": 0.097},
        {"name": "한화시스템", "weight": 0.080},
    ],
    "KODEX S&P500(H)": [
        {"name": "Apple Inc", "weight": 0.071},
        {"name": "Microsoft", "weight": 0.066},
        {"name": "NVIDIA", "weight": 0.058},
        {"name": "Amazon", "weight": 0.041},
        {"name": "Meta Platforms", "weight": 0.025},
    ],
    "KoAct 글로벌AI&로봇액티브 ETF": [
        {"name": "NVIDIA", "weight": 0.098},
        {"name": "Microsoft", "weight": 0.062},
        {"name": "TSMC", "weight": 0.055},
        {"name": "Alphabet", "weight": 0.045},
        {"name": "ABB", "weight": 0.038},
    ],
    "Xtrackers DAX ETF (XDAX)": [
        {"name": "SAP", "weight": 0.139},
        {"name": "Siemens AG", "weight": 0.099},
        {"name": "Allianz", "weight": 0.083},
        {"name": "Deutsche Telekom", "weight": 0.074},
        {"name": "Mercedes-Benz Group", "weight": 0.043},
    ],
    "Fidelity Fundamental Small-Mid Cap ETF (FFSM)": [
        {"name": "Williams-Sonoma", "weight": 0.018},
        {"name": "Casey's General Stores", "weight": 0.017},
        {"name": "Reliance Inc", "weight": 0.016},
        {"name": "WW Grainger", "weight": 0.015},
        {"name": "Carlisle Companies", "weight": 0.014},
    ],
}

MKT_SUFFIX = {
    "US": "", "KS": ".KS", "KQ": ".KQ", "GY": ".DE", "IM": ".MI",
    "LN": ".L", "FP": ".PA", "SW": ".SW", "NA": ".AS", "JP": ".T",
    "HK": ".HK", "AU": ".AX",
}


def to_yahoo(bbg):
    if not bbg:
        return None
    parts = bbg.strip().split()
    if len(parts) < 2:
        return None
    code, mkt = parts[0], parts[1].upper()
    suffix = MKT_SUFFIX.get(mkt)
    if suffix is None:
        return None
    if mkt == "KS" and not re.fullmatch(r"\d{6}", code):
        return None
    return code + suffix


def resolve(h):
    return to_yahoo(h.get("ticker")) or to_yahoo(h.get("proxy_ticker", ""))


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


def fetch_top_holdings(yt, n=5):
    try:
        t = yf.Ticker(yt)
        fd = getattr(t, "funds_data", None)
        if fd is None:
            return None
        df = getattr(fd, "top_holdings", None)
        if df is None or len(df) == 0:
            return None
        out = []
        for idx, row in df.head(n).iterrows():
            # 컬럼명이 다양해서 여러 후보 시도
            name = None
            for key in ("Name", "holdingName", "name", "Holding Name"):
                v = row.get(key) if hasattr(row, "get") else None
                if v:
                    name = v
                    break
            if not name:
                name = str(idx)
            weight = None
            for key in ("Holding Percent", "holdingPercent", "weight", "Weight"):
                v = row.get(key) if hasattr(row, "get") else None
                if v is not None:
                    weight = v
                    break
            if weight is None:
                weight = 0
            try:
                weight = float(weight)
            except Exception:
                weight = 0
            # 0~1 또는 0~100 자동 판단
            if weight > 1.5:
                weight = weight / 100
            out.append({"name": str(name).strip(), "weight": round(weight, 6)})
        return out if out else None
    except Exception as e:
        return None


def main():
    print(f"=== ETF 상위 구성종목 수집 ===")
    text, data = load_data()
    holdings = data["holdings"]
    success, fail = 0, 0
    for h in holdings:
        name_h = h.get("name", "")
        yt = resolve(h)
        # 1) yfinance funds_data 시도
        top = fetch_top_holdings(yt, 5) if yt else None
        if top and len(top) > 0:
            h["top_holdings"] = top
            h["top_holdings_source"] = "auto"
            success += 1
            preview = ", ".join(f"{x['name'][:18]}({x['weight']*100:.1f}%)" for x in top[:3])
            print(f"  [auto]   {name_h:42s} {yt or '-':12s} -> {preview}...")
            continue
        # 2) 수동 fallback
        if name_h in MANUAL_HOLDINGS:
            h["top_holdings"] = MANUAL_HOLDINGS[name_h]
            h["top_holdings_source"] = "manual"
            fail += 1
            print(f"  [manual] {name_h:42s} (수동 큐레이션 fallback)")
            continue
        # 3) 데이터 없음 — 기존 top_holdings 보존 (있다면)
        if "top_holdings" not in h:
            h["top_holdings"] = None
        fail += 1
        print(f"  [skip]   {name_h:42s} (yfinance & manual 둘 다 없음)")
    save_data(text, data)
    print(f"\n수집 성공 {success}개 / 실패 {fail}개")
    print(f"저장: {PLAIN.name}")


if __name__ == "__main__":
    main()
