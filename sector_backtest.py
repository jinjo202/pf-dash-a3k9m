# -*- coding: utf-8 -*-
"""
섹터 로테이션 모델 백테스트 → sector-backtest.js (매크로 탭 섹터 패널용).

가격만으로 재구성 가능한 코어 2팩터(라이브 모델 4팩터 중 이익·국면적합은 시점 데이터
부재로 제외 — country_backtest와 동일한 관행):
  · Momentum 55% = 6-1개월 수익률 (최근 1개월 skip)
  · Risk     45% = 12개월 고점대비 낙폭 + 12개월 실현변동성 (둘 다 낮을수록 +)
  (라이브 가중 momentum .30 / risk .25 의 상대비율을 유지한 55/45)

월 1회 리밸런싱, 상위 3개 섹터 동일비중 롱 vs 가용 섹터 동일비중(EW) 벤치.
섹터별 상장 시점이 달라 매월 '데이터 있는 섹터'만 횡단면에 포함(최소 6개).

로테이션 빈도 통계도 산출 — "얼마나 자주 바뀌나"가 실사용 관점 핵심 질문:
  · 상위3 교체율: 리밸런싱당 평균 교체 종목 수
  · 무교체 비율: 상위3이 그대로인 달의 비율
  · 평균 보유기간: 한 섹터가 상위3에 머무는 평균 개월

사용법: python sector_backtest.py
갱신 주기: 월 1회면 충분(월간 데이터라 일중 변화 없음). 수동 실행 후 commit.
"""
import io
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import yfinance as yf

from fetch_daily import US_SECTORS
from sector_history import KR_SECTOR_ETFS

HERE = Path(__file__).parent
OUT = HERE / "sector-backtest.js"

MOM_W, RISK_W = 0.55, 0.45
TOP_N = 3
MIN_CROSS = 6      # 횡단면 최소 섹터 수 (미달 월은 스킵)


def _z(vals):
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return [0.0 for _ in vals]
    m = sum(xs) / len(xs)
    sd = (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
    return [((v - m) / sd if v is not None else None) for v in vals]


def fetch_monthly(tickers):
    df = yf.download(tickers, period="max", interval="1mo",
                     auto_adjust=True, progress=False)
    close = df["Close"] if "Close" in df else df
    out = {}
    for tk in tickers:
        try:
            s = close[tk].dropna()
        except Exception:
            continue
        out[tk] = {idx.strftime("%Y-%m"): float(v) for idx, v in s.items()}
    return out


def backtest(universe):
    """universe: [(ticker, 섹터명)]. 반환: 성과 + 로테이션 통계."""
    px = fetch_monthly([t for t, _ in universe])
    names = {t: n for t, n in universe}
    months = sorted(set(m for d in px.values() for m in d))

    dates, strat, bench = [], [], []
    sv = bv = 1.0
    wins = rebals = 0
    prev_top = None
    total_changes = 0
    unchanged_months = 0
    tenure = {}          # 섹터별 상위3 연속 체류 기록
    tenures_done = []

    for i in range(13, len(months) - 1):
        t, t1 = months[i], months[i + 1]
        rows = []
        for tk in px:
            p = px[tk]
            win = [p.get(months[j]) for j in range(i - 12, i + 1)]
            if any(v is None for v in win) or p.get(t1) is None:
                continue
            mom = win[-2] / win[-7] - 1                    # 6-1M (최근 1개월 skip)
            dd = win[-1] / max(win) - 1
            rets = [win[k] / win[k - 1] - 1 for k in range(1, len(win))]
            vol = statistics.pstdev(rets)
            rows.append({"tk": tk, "mom": mom, "dd": dd, "vol": -vol,
                         "fwd": p[t1] / p[t] - 1})
        if len(rows) < MIN_CROSS:
            continue
        zm = _z([r["mom"] for r in rows])
        zd = _z([r["dd"] for r in rows])
        zv = _z([r["vol"] for r in rows])
        for r, a, b, c in zip(rows, zm, zd, zv):
            r["score"] = MOM_W * (a or 0) + RISK_W * (((b or 0) + (c or 0)) / 2)
        rows.sort(key=lambda r: r["score"], reverse=True)
        top = [r["tk"] for r in rows[:TOP_N]]

        s_ret = sum(r["fwd"] for r in rows[:TOP_N]) / TOP_N
        b_ret = sum(r["fwd"] for r in rows) / len(rows)
        sv *= (1 + s_ret); bv *= (1 + b_ret)
        wins += int(s_ret > b_ret)
        rebals += 1
        dates.append(t1); strat.append(round(sv, 4)); bench.append(round(bv, 4))

        # 로테이션 통계
        if prev_top is not None:
            changed = len(set(top) - set(prev_top))
            total_changes += changed
            unchanged_months += int(changed == 0)
        for tk in top:
            tenure[tk] = tenure.get(tk, 0) + 1
        for tk in list(tenure):
            if tk not in top:
                tenures_done.append(tenure.pop(tk))
        prev_top = top
    tenures_done.extend(tenure.values())

    def stats(vs):
        if len(vs) < 2:
            return {}
        yrs = len(vs) / 12.0
        rets = [vs[k] / vs[k - 1] - 1 for k in range(1, len(vs))]
        mean = sum(rets) / len(rets)
        sd = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5 or 1e-9
        peak, mdd = vs[0], 0.0
        for v in vs:
            peak = max(peak, v); mdd = min(mdd, v / peak - 1)
        return {"cagr": round((vs[-1] ** (1 / yrs) - 1) * 100, 1),
                "sharpe": round(mean * 12 / (sd * 12 ** 0.5), 2),
                "mdd": round(mdd * 100, 1), "total": round((vs[-1] - 1) * 100, 1)}

    n_reb = max(rebals - 1, 1)
    return {
        "period": f"{dates[0]} ~ {dates[-1]}" if dates else "",
        "rebalances": rebals,
        "stats_strategy": stats(strat), "stats_benchmark": stats(bench),
        "hit_rate": round(100 * wins / rebals) if rebals else None,
        "rotation": {
            "avg_changes": round(total_changes / n_reb, 2),      # 월평균 교체 수(0~3)
            "unchanged_pct": round(100 * unchanged_months / n_reb),
            "avg_tenure_m": round(sum(tenures_done) / len(tenures_done), 1) if tenures_done else None,
        },
        "dates": dates, "strategy": strat, "benchmark": bench,
    }


def main():
    # stdout 재래핑 금지 — fetch_daily가 import 시 이미 UTF-8 래핑함.
    # 이중 래핑하면 기존 래퍼가 GC되며 버퍼가 닫혀 'I/O operation on closed file'.
    us_uni = [(etf, nm) for etf, nm, _ in US_SECTORS]
    kr_uni = [(tk, nm) for tk, nm, _ in KR_SECTOR_ETFS]
    print(f"백테스트: US {len(us_uni)}섹터(SPDR), KR {len(kr_uni)}섹터(ETF)")
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
           "method": (f"가격 코어 2팩터(모멘텀 6-1M {MOM_W:.0%} + 리스크(12M낙폭·변동성) {RISK_W:.0%}) "
                      f"횡단면 z, 월 1회 상위 {TOP_N}개 동일비중 vs 가용 섹터 EW. "
                      "이익·국면적합 팩터는 과거 시점 데이터가 없어 백테스트에서 제외 — "
                      "라이브 모델 성과가 아니라 코어 팩터의 검증."),
           "regions": {}}
    for cc, uni in (("US", us_uni), ("KR", kr_uni)):
        r = backtest(uni)
        out["regions"][cc] = r
        s, b, ro = r["stats_strategy"], r["stats_benchmark"], r["rotation"]
        print(f"[{cc}] {r['period']} ({r['rebalances']}회)")
        print(f"    전략 CAGR {s.get('cagr')}% Sharpe {s.get('sharpe')} MDD {s.get('mdd')}% "
              f"| 벤치 CAGR {b.get('cagr')}% Sharpe {b.get('sharpe')} MDD {b.get('mdd')}%")
        print(f"    적중률 {r['hit_rate']}% | 로테이션: 월평균 {ro['avg_changes']}개 교체, "
              f"무교체 {ro['unchanged_pct']}%, 평균 보유 {ro['avg_tenure_m']}개월")
    body = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    OUT.write_text("// 섹터 로테이션 백테스트 (sector_backtest.py, 월 1회 수동 갱신)\n"
                   "window.SECTOR_BACKTEST = " + body + ";\n", encoding="utf-8")
    print(f"저장: {OUT.name}")


if __name__ == "__main__":
    main()
