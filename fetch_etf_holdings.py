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
        yt = resolve(h)
        if not yt:
            h["top_holdings"] = None
            fail += 1
            print(f"  [skip] {h['name']:42s} (no ticker)")
            continue
        top = fetch_top_holdings(yt, 5)
        if top and len(top) > 0:
            h["top_holdings"] = top
            success += 1
            preview = ", ".join(f"{x['name'][:18]}({x['weight']*100:.1f}%)" for x in top[:3])
            print(f"  [ok]   {h['name']:42s} {yt:12s} -> {preview}...")
        else:
            h["top_holdings"] = None
            fail += 1
            print(f"  [miss] {h['name']:42s} {yt:12s}")
    save_data(text, data)
    print(f"\n수집 성공 {success}개 / 실패 {fail}개")
    print(f"저장: {PLAIN.name}")


if __name__ == "__main__":
    main()
