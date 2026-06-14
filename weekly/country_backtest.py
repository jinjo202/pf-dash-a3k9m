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


STATE = os.path.join(REPO, "country-model-state.json")
_FAC_KO = {"value": "밸류", "momentum": "모멘텀", "earnings": "이익수정",
           "macro": "매크로", "currency": "통화캐리"}
SCORE_THRESH = 0.40    # 종합점수 변화 임계 (이벤트 리밸런싱)
FACTOR_THRESH = 0.80   # 단일 팩터 z 변화 임계
MONTHLY_DAYS = 30


def _load_state():
    if os.path.exists(STATE):
        try:
            return json.load(open(STATE, encoding="utf-8"))
        except Exception:
            pass
    return {"last_rebalance": None, "snapshot": {}, "changes": []}


def _days_since(d, today):
    try:
        return (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days
    except Exception:
        return 999


def detect_changes(prev_snap, current, last_rebalance, today):
    """직전 리밸런싱 대비 변화 감지 → (리밸런싱 여부, trigger, 변화목록)."""
    changes, rebal_event = [], False
    for r in current:
        nm = r["name"]
        prev = prev_snap.get(nm)
        if not prev:
            continue
        pf, pz = prev.get("factors") or {}, None
        # 가장 크게 변한 팩터(드라이버)
        deltas = {f: r["z"].get(f, 0) - pf.get(f, 0) for f in _FAC_KO}
        drv = max(deltas, key=lambda f: abs(deltas[f]))
        drv_txt = "%s z%+.1f→%+.1f" % (_FAC_KO[drv], pf.get(drv, 0), r["z"].get(drv, 0))
        flipped = prev.get("pref") != r["pref"]
        d_score = r["score"] - prev.get("score", 0)
        if flipped or abs(d_score) >= SCORE_THRESH or abs(deltas[drv]) >= FACTOR_THRESH:
            rebal_event = True
            changes.append({
                "country": nm,
                "from_pref": prev.get("pref"), "to_pref": r["pref"],
                "flipped": flipped,
                "d_score": round(d_score, 2),
                "driver": drv_txt,
            })
    monthly_due = (last_rebalance is None) or (_days_since(last_rebalance, today) >= MONTHLY_DAYS)
    rebal = rebal_event or monthly_due
    trigger = ("이벤트(팩터 변화)" if rebal_event else
               ("정기(월 1회)" if monthly_due else "변화 없음"))
    return rebal, trigger, changes


def main():
    sys.path.insert(0, HERE)
    import country_model as cm
    current = cm.compute()
    bt = backtest()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # ── 상태 추적 · 이벤트 리밸런싱 ──
    state = _load_state()
    rebal, trigger, changes = detect_changes(
        state.get("snapshot") or {}, current, state.get("last_rebalance"), today)
    snap_now = {r["name"]: {"pref": r["pref"], "score": r["score"], "factors": r["z"]}
                for r in current}
    log = list(state.get("changes") or [])
    if rebal:
        entry = {"date": today, "trigger": trigger, "items": changes}
        if changes or trigger.startswith("정기"):
            log = [entry] + log
        log = log[:10]
        state = {"last_rebalance": today, "snapshot": snap_now, "changes": log}
        json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    methodology = (
        "방법론: 5개 팩터를 5개국 횡단면 z-score(평균0·표준편차1)로 표준화 후 가중합성. "
        "Value=12M Fwd PER 적정대비 괴리(쌀수록+), Momentum=12-1개월 가격(최근1M skip), "
        "Earnings=이익수정비율(ERR)+1M수정, Macro=OECD CLI 수준+통화정책 방향, "
        "Currency=KRW 대비 정책금리 캐리. 종합점수 ≥+0.25 비중확대, ≤−0.25 축소, 그 외 중립. "
        "리밸런싱: 월 1회 정기 + 선호변경·점수 ±0.4·단일팩터 z ±0.8 이상 변화 시 이벤트.")

    out = {
        "asof": today,
        "rebalance": "월 1회 + 팩터 변화 시 (이벤트)",
        "last_rebalance": state.get("last_rebalance"),
        "rebalance_trigger": trigger,
        "changes": log,
        "methodology": methodology,
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
