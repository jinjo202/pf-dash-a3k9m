# -*- coding: utf-8 -*-
"""
국가배분 모델 백테스트 + 현재 모델 스냅샷 → country-model.js (대시보드 매크로 탭용).

백테스트 (월 1회 리밸런싱):
  가격만으로 재구성 가능한 코어 2팩터 — Asness·Moskowitz·Pedersen(2013) 방식.
    · Momentum = 최근 12-1개월 수익률 (최근 1개월 skip)
    · Value    = 과거 5년(60-12개월) 수익률의 음(-) → 장기 평균회귀(저평가 프록시)
  각 월말 5개국 횡단면 z-score, 합성(50/50) → 상위 2개국 동일비중 롱(월 리밸런싱).
  벤치마크 = 5개국 동일비중(EW).
  (전체 5팩터 모델은 시점 데이터가 필요해 forward 적용; 백테스트는 코어 팩터로 검증)

출력: window.COUNTRY_MODEL = {current, backtest, weights, rebalance, asof}
"""
import sys, os, io, json
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

MARKETS = [("미국", "^GSPC"), ("한국", "^KS11"), ("유럽", "^STOXX"),
           ("일본", "^N225"), ("이머징", "EEM")]
NAMES = [m[0] for m in MARKETS]
TICKERS = [m[1] for m in MARKETS]


def _zscore(vals):
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return [0.0 for _ in vals]
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
    return [((v - m) / sd if v is not None else 0.0) for v in vals]


def fetch_monthly():
    """5개 지수 월말 종가 시계열. {ticker: [(date, close)]}."""
    import yfinance as yf
    raw = yf.download(TICKERS, period="11y", interval="1mo",
                      auto_adjust=True, progress=False)
    close = raw["Close"] if "Close" in raw else raw
    series = {}
    for tk in TICKERS:
        try:
            s = close[tk].dropna()
        except Exception:
            continue
        series[tk] = [(idx.strftime("%Y-%m"), float(v)) for idx, v in s.items()]
    return series


def backtest():
    series = fetch_monthly()
    # 공통 월 인덱스
    common = None
    for tk in TICKERS:
        ds = set(d for d, _ in series.get(tk, []))
        common = ds if common is None else (common & ds)
    months = sorted(common or [])
    px = {tk: dict(series.get(tk, [])) for tk in TICKERS}

    dates, strat, bench = [], [], []
    sv = bv = 1.0
    wins = 0
    rebals = 0
    # t: 리밸런싱 시점 인덱스 (60개월 이상 과거 필요), t+1 수익 실현
    for i in range(60, len(months) - 1):
        t, t1 = months[i], months[i + 1]
        t_12 = months[i - 12]
        t_60 = months[i - 60]
        mom, val, fwd = [], [], []
        ok = True
        for tk in TICKERS:
            p_t, p_12, p_60, p_t1 = px[tk].get(t), px[tk].get(t_12), px[tk].get(t_60), px[tk].get(t1)
            if not all([p_t, p_12, p_60, p_t1]):
                ok = False; break
            mom.append(p_t / p_12 - 1)          # 12-1 모멘텀(최근월 t는 직전월 종가라 근사)
            val.append(-(p_t / p_60 - 1))       # 5년 반전 → 저평가 프록시
            fwd.append(p_t1 / p_t - 1)          # 다음달 실현수익
        if not ok:
            continue
        zc = [0.5 * z_v + 0.5 * z_m for z_v, z_m in zip(_zscore(val), _zscore(mom))]
        order = sorted(range(len(TICKERS)), key=lambda k: zc[k], reverse=True)
        top2 = order[:2]
        s_ret = sum(fwd[k] for k in top2) / len(top2)   # 상위2 EW
        b_ret = sum(fwd) / len(fwd)                      # EW 벤치
        sv *= (1 + s_ret); bv *= (1 + b_ret)
        if s_ret > b_ret:
            wins += 1
        rebals += 1
        dates.append(t1); strat.append(round(sv, 4)); bench.append(round(bv, 4))

    def stats(vseries, rets_pairs):
        if len(vseries) < 2:
            return {}
        n = len(vseries)
        yrs = n / 12.0
        cagr = (vseries[-1]) ** (1 / yrs) - 1 if yrs > 0 else 0
        rets = [vseries[k] / vseries[k - 1] - 1 for k in range(1, n)]
        mean = sum(rets) / len(rets)
        sd = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5 or 1e-9
        sharpe = (mean * 12) / (sd * (12 ** 0.5))
        peak = vseries[0]; mdd = 0
        for v in vseries:
            peak = max(peak, v); mdd = min(mdd, v / peak - 1)
        return {"cagr": round(cagr * 100, 1), "vol": round(sd * (12 ** 0.5) * 100, 1),
                "sharpe": round(sharpe, 2), "mdd": round(mdd * 100, 1),
                "total": round((vseries[-1] - 1) * 100, 1)}

    return {
        "dates": dates, "strategy": strat, "benchmark": bench,
        "stats_strategy": stats(strat, None),
        "stats_benchmark": stats(bench, None),
        "hit_rate": round(100 * wins / rebals, 0) if rebals else None,
        "rebalances": rebals,
        "period": (dates[0] + " ~ " + dates[-1]) if dates else "",
    }


def main():
    sys.path.insert(0, HERE)
    import country_model as cm
    current = cm.compute()
    bt = backtest()
    out = {
        "asof": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "rebalance": "월 1회 (매월 말)",
        "weights": cm.WEIGHTS,
        "current": [{"name": r["name"], "pref": r["pref"], "score": r["score"],
                     "factors": r["z"], "rationale": cm.rationale(r)} for r in current],
        "backtest": bt,
    }
    dest = os.path.join(REPO, "country-model.js")
    with open(dest, "w", encoding="utf-8") as f:
        f.write("// 국가배분 멀티팩터 모델 + 백테스트 (country_backtest.py 생성)\n")
        f.write("window.COUNTRY_MODEL = " + json.dumps(out, ensure_ascii=False) + ";\n")
    log = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    bs, bb = bt["stats_strategy"], bt["stats_benchmark"]
    log.write("백테스트 %s (%d회 리밸런싱)\n" % (bt["period"], bt["rebalances"]))
    log.write("  전략(상위2 모멘텀+밸류): CAGR %s%% · Sharpe %s · MDD %s%% · 누적 %s%%\n" % (
        bs.get("cagr"), bs.get("sharpe"), bs.get("mdd"), bs.get("total")))
    log.write("  벤치(EW 5개국):          CAGR %s%% · Sharpe %s · MDD %s%% · 누적 %s%%\n" % (
        bb.get("cagr"), bb.get("sharpe"), bb.get("mdd"), bb.get("total")))
    log.write("  적중률(벤치 상회) %s%% → country-model.js 저장\n" % bt.get("hit_rate"))
    log.flush()


if __name__ == "__main__":
    main()
