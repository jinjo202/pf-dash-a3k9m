"""
fetch_valuations.py — 각 holding + underlying 종목의 PER/PBR/ROE 수집

yfinance Ticker.info에서:
  - trailingPE → PER
  - priceToBook → PBR
  - returnOnEquity → ROE (소수, 0.18 = 18%)

저장:
  - 각 h["valuation"] = {pe, pb, roe}
  - data["underlying_valuations"] = {name: {pe, pb, roe}}
  - data["portfolio_valuation"] = {pe, pb, roe, coverage}  (시가 비중 가중 평균)
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


def fetch_one(yt):
    try:
        info = yf.Ticker(yt).info or {}
    except Exception:
        return {"pe": None, "pb": None, "roe": None, "pe_kind": None}
    # 12개월 Forward PER 우선 (forwardPE = 향후 12M EPS 컨센서스 기반)
    # 없으면 trailing (지난 12M 실적 EPS 기반)로 fallback
    forward_pe = info.get("forwardPE")
    trailing_pe = info.get("trailingPE")
    pe = forward_pe if forward_pe is not None else trailing_pe
    pe_kind = "fwd" if forward_pe is not None else ("ttm" if trailing_pe is not None else None)
    pb = info.get("priceToBook")
    roe = info.get("returnOnEquity")
    # sanity 필터: 비현실적 값 제거 (yfinance 데이터 오류 케이스)
    pe_v = float(pe) if pe is not None else None
    pb_v = float(pb) if pb is not None else None
    roe_v = float(roe) if roe is not None else None
    if pe_v is not None and (pe_v <= 0 or pe_v > 300):
        pe_v = None
        pe_kind = None
    if pb_v is not None and (pb_v <= 0 or pb_v > 100): pb_v = None
    if roe_v is not None and (roe_v > 3 or roe_v < -3): roe_v = None  # ±300%
    return {
        "pe": round(pe_v, 2) if pe_v else None,
        "pb": round(pb_v, 2) if pb_v else None,
        "roe": round(roe_v * 100, 2) if roe_v is not None else None,  # %
        "pe_kind": pe_kind,  # 'fwd' = 12M forward, 'ttm' = trailing 12M
    }


def main():
    print("=== Valuation 수집 ===")
    text, data = load_data()
    holdings = data["holdings"]

    # 1. holding별
    print("\n-- ETF/펀드 valuation --")
    for h in holdings:
        yt = resolve(h)
        if not yt:
            h["valuation"] = {"pe": None, "pb": None, "roe": None}
            continue
        v = fetch_one(yt)
        h["valuation"] = v
        pe_lbl = f"{v['pe']}({v.get('pe_kind') or '-'})" if v['pe'] else "-"
        print(f"  [{yt:12s}] {h['name'][:38]:38s}  PE={pe_lbl}, PB={v['pb']}, ROE={v['roe']}%")

    # 2. underlying별
    print("\n-- Underlying 종목 valuation --")
    underlying_ytd = data.get("underlying_ytd") or {}
    underlying_val = {}
    for name, info_u in underlying_ytd.items():
        yt = info_u.get("ticker")
        if not yt:
            continue
        v = fetch_one(yt)
        underlying_val[name] = v
        if v["pe"] or v["pb"] or v["roe"]:
            print(f"  [{yt:12s}] {name[:30]:30s}  PE={v['pe']}, PB={v['pb']}, ROE={v['roe']}%")
    data["underlying_valuations"] = underlying_val

    # 3. 직접 데이터가 없는 ETF는 top_holdings × underlying valuation 가중 평균으로 derive
    print("\n-- 부족한 ETF의 valuation을 top_holdings로 보완 --")
    for h in holdings:
        v = h.get("valuation") or {}
        tops = h.get("top_holdings") or []
        if not tops:
            continue
        # 부족한 항목만 채움
        need = {k: v.get(k) is None for k in ["pe", "pb", "roe"]}
        if not any(need.values()):
            continue
        pe_ys, pe_ws_l, pe_kinds_l = [], [], []
        pb_vs_l, pb_ws_l = [], []
        roe_vs_l, roe_ws_l = [], []
        for t in tops:
            uv = underlying_val.get(t.get("name"))
            if not uv:
                continue
            wt = t.get("weight", 0)
            if uv.get("pe") and uv["pe"] > 0:
                pe_ys.append(1.0 / uv["pe"]); pe_ws_l.append(wt)
                pe_kinds_l.append(uv.get("pe_kind"))
            if uv.get("pb") and uv["pb"] > 0:
                pb_vs_l.append(uv["pb"]); pb_ws_l.append(wt)
            if uv.get("roe") is not None:
                roe_vs_l.append(uv["roe"]); roe_ws_l.append(wt)
        derived = {}
        if need["pe"] and pe_ys:
            avg_y = sum(y*w for y,w in zip(pe_ys, pe_ws_l)) / sum(pe_ws_l)
            v["pe"] = round(1.0/avg_y, 2) if avg_y > 0 else None
            v["pe_src"] = "top5"
            # underlying의 pe_kind 다수결 (대부분 fwd면 fwd, 혼합이면 mixed)
            kinds_present = [k for k in pe_kinds_l if k]
            if kinds_present and all(k == "fwd" for k in kinds_present):
                v["pe_kind"] = "fwd"
            elif kinds_present and all(k == "ttm" for k in kinds_present):
                v["pe_kind"] = "ttm"
            elif kinds_present:
                v["pe_kind"] = "mixed"
            derived["pe"] = v["pe"]
        if need["pb"] and pb_vs_l:
            v["pb"] = round(sum(x*w for x,w in zip(pb_vs_l, pb_ws_l)) / sum(pb_ws_l), 2)
            v["pb_src"] = "top5"
            derived["pb"] = v["pb"]
        if need["roe"] and roe_vs_l:
            v["roe"] = round(sum(x*w for x,w in zip(roe_vs_l, roe_ws_l)) / sum(roe_ws_l), 2)
            v["roe_src"] = "top5"
            derived["roe"] = v["roe"]
        h["valuation"] = v
        if derived:
            print(f"  [top5] {h['name']:42s}  derived: {derived}")

    # 4. 포트폴리오 가중 평균
    pe_ys, pe_ws = [], []
    pb_vs, pb_ws = [], []
    roe_vs, roe_ws = [], []
    for h in holdings:
        v = h.get("valuation") or {}
        w = h.get("w") or 0
        if w <= 0:
            continue
        if v.get("pe") and v["pe"] > 0:
            pe_ys.append(1.0 / v["pe"])  # earnings yield
            pe_ws.append(w)
        if v.get("pb") and v["pb"] > 0:
            pb_vs.append(v["pb"])
            pb_ws.append(w)
        if v.get("roe") is not None:
            roe_vs.append(v["roe"])
            roe_ws.append(w)

    def wavg(vs, ws):
        s = sum(ws)
        return (sum(v * w for v, w in zip(vs, ws)) / s) if s > 0 else None

    pe_yield = wavg(pe_ys, pe_ws)
    pe_port = (1.0 / pe_yield) if pe_yield and pe_yield > 0 else None
    pb_port = wavg(pb_vs, pb_ws)
    roe_port = wavg(roe_vs, roe_ws)

    # 포트폴리오 PE의 종류 (대부분이 fwd면 fwd로 표시; 혼합이면 mixed)
    pe_kinds = [(h.get("valuation") or {}).get("pe_kind") for h in holdings if (h.get("valuation") or {}).get("pe")]
    if pe_kinds and all(k == "fwd" for k in pe_kinds):
        port_pe_kind = "fwd"
    elif pe_kinds and all(k == "ttm" for k in pe_kinds):
        port_pe_kind = "ttm"
    elif pe_kinds:
        port_pe_kind = "mixed"
    else:
        port_pe_kind = None

    data["portfolio_valuation"] = {
        "pe": round(pe_port, 2) if pe_port else None,
        "pb": round(pb_port, 2) if pb_port else None,
        "roe": round(roe_port, 2) if roe_port is not None else None,
        "pe_kind": port_pe_kind,  # 'fwd' | 'ttm' | 'mixed'
        "coverage_pe": round(sum(pe_ws) * 100, 1),
        "coverage_pb": round(sum(pb_ws) * 100, 1),
        "coverage_roe": round(sum(roe_ws) * 100, 1),
    }

    save_data(text, data)

    print("\n=== 포트폴리오 가중 평균 ===")
    print(f"  PER {pe_port:.2f} (커버리지 {sum(pe_ws)*100:.1f}%)" if pe_port else "  PER 데이터 부족")
    print(f"  PBR {pb_port:.2f} (커버리지 {sum(pb_ws)*100:.1f}%)" if pb_port else "  PBR 데이터 부족")
    print(f"  ROE {roe_port:.2f}% (커버리지 {sum(roe_ws)*100:.1f}%)" if roe_port is not None else "  ROE 데이터 부족")


if __name__ == "__main__":
    main()
