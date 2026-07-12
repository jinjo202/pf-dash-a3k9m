# -*- coding: utf-8 -*-
"""
롱숏포트 리스크 룰 사후검증 엔진 v2 (pure stdlib)

v2 추가:
 - 로테이션 룰: 동일 페어 스톱(페어 -8% + 숏레그 +15%) 12개월(252거래일) 내 3회 누적 -> 영구 폐기.
   폐기 자본은 현금 대기(재배분 없음) -> Gross가 자연 감소. 신규 아이디어 유입은 시뮬레이션 불가.
 - 노출도 추적: 월초 리밸런스 후 가격 드리프트를 반영한 Gross/Net 시계열 산출.
 - 정책 상한 강제: |Net| > 50% -> 강제 리밸런스, Gross > 300% -> 강제 축소 (둘 다 이벤트 로그).

기존 룰:
 - 페어 스프레드 스톱 -8% -> 20거래일 플랫 후 재진입
 - 숏 레그 +15% 역행 -> 페어 50% 축소 20거래일
 - 월중 NAV -3% -> 잔여 월 그로스 50% / 월중 -5% -> 북 청산, 20거래일 후 50%로 재가동
 - 일간 NAV -1.5% -> 5거래일 재진입 동결
비용: 거래 그로스 10bps + 숏 그로스 연 1% 대차.
주의: 페어 방향은 2026년 시점 선정(사후 편향). 알파가 아니라 룰의 방어 거동을 검증한다.
"""
import json, math, ssl, sys, urllib.request, urllib.parse
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0"}
CTX = ssl.create_default_context()

def fetch(ticker, years=25):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?range={years}y&interval=1d"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        j = json.load(r)
    res = j["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]["close"]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose", q)
    out = {}
    for t, c in zip(ts, adj):
        if c is None or c <= 0:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d")
        out[d] = c
    return out

PAIRS = [
    {"id": "P1", "name": "삼성전자 L / SK하이닉스 S", "long": "005930.KS", "short": "000660.KS"},
    {"id": "P2", "name": "삼성전자우 L / 삼성전자 S",  "long": "005935.KS", "short": "005930.KS"},
    {"id": "P3", "name": "TSMC L / Intel S",           "long": "TSM",       "short": "INTC"},
    {"id": "P4", "name": "Walmart L / Target S",       "long": "WMT",       "short": "TGT"},
    {"id": "P5", "name": "LG엔솔 L / 삼성SDI S",       "long": "373220.KS", "short": "006400.KS"},
]
GROSS_TARGET = 190.0    # % of NAV (steady-state 목표)
GROSS_CAP = 300.0       # 정책 상한 (사용자 지정)
NET_CAP = 50.0          # 정책 상한 |Net| (사용자 지정)
PAIR_STOP = -8.0
SHORT_LEG_STOP = 15.0
FLAT_DAYS = 20
FREEZE_DAYS = 5
ROT_WINDOW = 252        # 로테이션 룰 룩백 (거래일)
ROT_MAX_STOPS = 3
COST_BPS = 10.0
BORROW_ANNUAL = 0.01

def run(prices, start, end, rules_on=True, reverse=False, rotation=False):
    pair_data = []
    for p in PAIRS:
        L, S = prices[p["long"]], prices[p["short"]]
        dates = sorted(set(L) & set(S))
        dates = [d for d in dates if start <= d <= end]
        if len(dates) < 60:
            continue
        pair_data.append({"cfg": p, "dates": dates, "L": L, "S": S,
                          "set": set(dates), "idx": {d: i for i, d in enumerate(dates)}})
    all_dates = sorted(set().union(*[pd_["set"] for pd_ in pair_data]))
    day_idx = {d: i for i, d in enumerate(all_dates)}

    nav = 100.0
    nav_series, events, expo_series = [], [], []
    st = {pd_["cfg"]["id"]: {"cum": 0.0, "flat": 0, "half": 0, "short_entry": None,
                             "entered": False, "retired": False, "stops": [],
                             "lm": 1.0, "sm": 1.0}
          for pd_ in pair_data}
    gross_mult = 1.0
    book_flat = 0
    freeze = 0
    month = None
    month_start_nav = nav
    month_had_cut = False
    restart_half = False

    def register_stop(s, pid, d):
        """스톱 발생 등록 + 로테이션 룰 판정. 폐기 시 True."""
        s["stops"].append(day_idx[d])
        if rotation and not s["retired"]:
            recent = [x for x in s["stops"] if day_idx[d] - x <= ROT_WINDOW]
            if len(recent) >= ROT_MAX_STOPS:
                s["retired"] = True
                events.append((d, "로테이션 룰: 12개월 스톱 3회 → 페어 영구 폐기", pid, ""))
                return True
        return False

    for d in all_dates:
        mkey = d[:7]
        if mkey != month:
            month = mkey
            month_start_nav = nav
            if month_had_cut and gross_mult < 1.0 and book_flat == 0:
                gross_mult = 1.0 if not restart_half else 0.5
                restart_half = False
            month_had_cut = False
            for s in st.values():   # 월초 리밸런스: 드리프트 리셋
                s["lm"], s["sm"] = 1.0, 1.0

        # 상장돼 있는(달력에 있는) 페어 수 — 폐기 페어도 분모에 포함 (자본은 현금 대기, 재배분 없음)
        n_listed = sum(1 for pd_ in pair_data if d in pd_["set"])
        if n_listed == 0:
            continue
        leg_w = GROSS_TARGET / 2.0 / n_listed   # % of NAV per leg

        day_pnl_pct, cost_pct = 0.0, 0.0
        gross_e, net_e = 0.0, 0.0
        for pd_ in pair_data:
            if d not in pd_["set"] or pd_["idx"][d] == 0:
                continue
            pid = pd_["cfg"]["id"]; s = st[pid]
            if s["retired"]:
                continue
            i = pd_["idx"][d]; d0 = pd_["dates"][i - 1]
            rl = pd_["L"][d] / pd_["L"][d0] - 1.0
            rs = pd_["S"][d] / pd_["S"][d0] - 1.0
            if reverse:
                rl, rs = rs, rl
            spread = rl - rs

            if not s["entered"]:
                s["entered"] = True
                s["short_entry"] = pd_["S"][d0] if not reverse else pd_["L"][d0]
                cost_pct += leg_w * 2 * COST_BPS / 1e4

            if rules_on and s["flat"] > 0:
                s["flat"] -= 1
                s["lm"], s["sm"] = 1.0, 1.0
                if s["flat"] == 0:
                    if freeze > 0 or book_flat > 0:
                        s["flat"] = 1
                    else:
                        s["cum"] = 0.0
                        s["short_entry"] = pd_["S"][d] if not reverse else pd_["L"][d]
                        cost_pct += leg_w * 2 * COST_BPS / 1e4
                        events.append((d, "재진입", pid, ""))
                continue

            size = gross_mult * (0.5 if (rules_on and s["half"] > 0) else 1.0)
            if rules_on and book_flat > 0:
                size = 0.0
            contrib = leg_w * spread * size  # leg_w(%) x spread(소수) = NAV %p
            day_pnl_pct += contrib
            s["cum"] += spread / 2.0 * 100.0 * (1.0 if size > 0 else 0.0)
            cost_pct += leg_w * size * BORROW_ANNUAL / 252.0

            # 드리프트 및 노출도
            if size > 0:
                s["lm"] *= (1.0 + rl)
                s["sm"] *= (1.0 + rs)
                gross_e += leg_w * size * (s["lm"] + s["sm"])
                net_e   += leg_w * size * (s["lm"] - s["sm"])
            else:
                s["lm"], s["sm"] = 1.0, 1.0

            if rules_on and s["half"] > 0:
                s["half"] -= 1
                if s["half"] == 0:
                    s["short_entry"] = pd_["S"][d] if not reverse else pd_["L"][d]

            if rules_on and size > 0:
                spx = pd_["S"][d] if not reverse else pd_["L"][d]
                if s["short_entry"] and spx / s["short_entry"] - 1.0 >= SHORT_LEG_STOP / 100.0 and s["half"] == 0:
                    s["half"] = FLAT_DAYS
                    cost_pct += leg_w * COST_BPS / 1e4
                    events.append((d, "숏레그 +15% → 50% 커버", pid, f"숏 {spx/s['short_entry']-1:+.1%}"))
                    register_stop(s, pid, d)
                if not s["retired"] and s["cum"] <= PAIR_STOP:
                    events.append((d, "페어 -8% 스톱 → 플랫", pid, f"cum {s['cum']:.1f}%"))
                    s["flat"] = FLAT_DAYS
                    s["cum"] = 0.0
                    cost_pct += leg_w * 2 * COST_BPS / 1e4
                    register_stop(s, pid, d)

        # 정책 상한 강제
        if abs(net_e) > NET_CAP:
            events.append((d, f"|Net| {net_e:+.1f}% > ±{NET_CAP:.0f}% → 강제 리밸런스", "PORT", ""))
            cost_pct += abs(net_e) * COST_BPS / 1e4
            for s in st.values():
                s["lm"], s["sm"] = 1.0, 1.0
            gross_e = sum(leg_w * gross_mult * 2 for pd_ in pair_data
                          if d in pd_["set"] and not st[pd_["cfg"]["id"]]["retired"]
                          and st[pd_["cfg"]["id"]]["flat"] == 0)
            net_e = 0.0
        if gross_e > GROSS_CAP:
            scale = GROSS_CAP / gross_e
            events.append((d, f"Gross {gross_e:.0f}% > {GROSS_CAP:.0f}% → {scale:.2f}x 축소", "PORT", ""))
            gross_e = GROSS_CAP
            net_e *= scale

        day_ret = (day_pnl_pct - cost_pct) / 100.0
        nav *= (1.0 + day_ret)
        nav_series.append((d, nav))
        expo_series.append((d, round(gross_e, 2), round(net_e, 3)))

        if rules_on:
            if freeze > 0: freeze -= 1
            if book_flat > 0:
                book_flat -= 1
                if book_flat == 0:
                    events.append((d, "북 재가동 (그로스 50%)", "PORT", ""))
            mtd = nav / month_start_nav - 1.0
            if day_ret <= -0.015 and freeze == 0:
                freeze = FREEZE_DAYS
                events.append((d, "일간 -1.5% → 신규 동결 5일", "PORT", f"{day_ret:+.2%}"))
            if mtd <= -0.05 and book_flat == 0 and not restart_half:
                book_flat = FLAT_DAYS
                gross_mult = 0.5
                restart_half = True
                month_had_cut = True
                events.append((d, "월중 -5% → 북 청산·재출발 심사", "PORT", f"MTD {mtd:+.2%}"))
            elif mtd <= -0.03 and gross_mult == 1.0:
                gross_mult = 0.5
                month_had_cut = True
                events.append((d, "월중 -3% → 그로스 반감", "PORT", f"MTD {mtd:+.2%}"))

    return nav_series, events, expo_series

def sma_series(price_map, window):
    dates = sorted(price_map)
    vals = [price_map[d] for d in dates]
    out, csum = {}, 0.0
    for i, d in enumerate(dates):
        csum += vals[i]
        if i >= window:
            csum -= vals[i - window]
        if i >= window - 1:
            out[d] = csum / window
    return out

def regime_signal(prices):
    """STRATEGY_DIRECTIONAL.md §1 레짐 매트릭스 -> 일별 목표 넷 N.
    강세 0.55 / 중립 0.35 / 경계 0.15 / 위기 0.0"""
    ks, sp, vix = prices["^KS11"], prices["^GSPC"], prices["^VIX"]
    ks50, ks200 = sma_series(ks, 50), sma_series(ks, 200)
    sp50, sp200 = sma_series(sp, 50), sma_series(sp, 200)
    sig = {}
    for d in sorted(set(ks200) & set(sp200) & set(vix)):
        v = vix[d]
        above200 = (ks[d] > ks200[d]) + (sp[d] > sp200[d])
        above50 = (ks[d] > ks50[d]) + (sp[d] > sp50[d])
        if v > 40 or above200 == 0:
            n = 0.0
        elif above200 == 1 or v >= 30:
            n = 0.15
        elif above50 < 2 or v >= 20:
            n = 0.35
        else:
            n = 0.55
        sig[d] = n
    return sig

def run_directional(prices, alpha_series):
    """전략 B: 알파 엔진(전략 A 로테이션 런의 일별 수익) + 레짐 넷 오버레이(지수 50:50).
    손실 사다리: 일간 -2% -> 넷 50% 5일 / 월중 -4% -> 잔여월 넷 50% / 월중 -6% -> 넷 0 (잔여월+20일).
    재위험 인수: 넷 증액은 일 +3%p(주 +15%p) 상한, 인하는 즉시."""
    sig = regime_signal(prices)
    sig_dates = sorted(sig)
    ks, sp = prices["^KS11"], prices["^GSPC"]
    ks_d, sp_d = sorted(ks), sorted(sp)
    ks_prev = {d: ks_d[i-1] for i, d in enumerate(ks_d) if i > 0}
    sp_prev = {d: sp_d[i-1] for i, d in enumerate(sp_d) if i > 0}

    nav = 100.0
    series, expo, events = [], [], []
    month, month_start = None, nav
    month_mult, net_zero, day_cut = 1.0, 0, 0
    sp_ptr, cur_sig, n_prev = 0, 0.0, 0.0

    for i in range(len(alpha_series)):
        d, v = alpha_series[i]
        alpha_ret = v / alpha_series[i-1][1] - 1.0 if i > 0 else 0.0
        mkey = d[:7]
        if mkey != month:
            month, month_start, month_mult = mkey, nav, 1.0
        # 전일까지의 신호만 사용 (룩어헤드 방지)
        while sp_ptr < len(sig_dates) and sig_dates[sp_ptr] < d:
            cur_sig = sig[sig_dates[sp_ptr]]
            sp_ptr += 1
        n_target = cur_sig * month_mult * (0.5 if day_cut > 0 else 1.0)
        if net_zero > 0:
            n_target = 0.0
        # 재위험 인수 램프: 증액은 일 +3%p 상한
        N = min(n_target, n_prev + 0.03) if n_target > n_prev else n_target
        n_prev = N

        r_ov = 0.0
        if d in ks_prev: r_ov += 0.5 * (ks[d] / ks[ks_prev[d]] - 1.0)
        if d in sp_prev: r_ov += 0.5 * (sp[d] / sp[sp_prev[d]] - 1.0)
        day_ret = alpha_ret + N * r_ov
        nav *= (1.0 + day_ret)
        series.append((d, nav))
        expo.append((d, round(N * 100, 1)))

        if day_cut > 0: day_cut -= 1
        if net_zero > 0: net_zero -= 1
        mtd = nav / month_start - 1.0
        if day_ret <= -0.02 and day_cut == 0:
            day_cut = 5
            events.append((d, "일간 -2% → 넷 50% 인하 5일", "DIR", f"{day_ret:+.2%}"))
        if mtd <= -0.06 and net_zero == 0 and month_mult > 0.0:
            net_zero, month_mult = 20, 0.0
            events.append((d, "월중 -6% → 넷 0 (뉴트럴 전환)", "DIR", f"MTD {mtd:+.2%}"))
        elif mtd <= -0.04 and month_mult == 1.0:
            month_mult = 0.5
            events.append((d, "월중 -4% → 잔여월 넷 50%", "DIR", f"MTD {mtd:+.2%}"))
    return series, events, expo

def stats(series, start=None, end=None):
    s = [(d, v) for d, v in series if (start is None or d >= start) and (end is None or d <= end)]
    if len(s) < 2:
        return None
    base = s[0][1]
    rets = [s[i][1] / s[i-1][1] - 1.0 for i in range(1, len(s))]
    tot = s[-1][1] / base - 1.0
    n = len(rets); yrs = n / 252.0
    cagr = (1.0 + tot) ** (1.0 / yrs) - 1.0 if yrs > 0.2 else tot
    mu = sum(rets) / n
    sd = math.sqrt(sum((r - mu) ** 2 for r in rets) / (n - 1)) if n > 1 else 0.0
    vol = sd * math.sqrt(252)
    sharpe = (mu * 252) / vol if vol > 0 else 0.0
    peak, mdd, mdd_date = s[0][1], 0.0, s[0][0]
    for d, v in s:
        peak = max(peak, v)
        dd = v / peak - 1.0
        if dd < mdd:
            mdd, mdd_date = dd, d
    worst = min(rets)
    wd = s[1 + rets.index(worst)][0]
    return {"start": s[0][0], "end": s[-1][0], "total": tot, "cagr": cagr, "vol": vol,
            "sharpe": sharpe, "mdd": mdd, "mdd_date": mdd_date, "worst_day": worst, "worst_date": wd}

def fmt_stats(name, st_):
    if not st_: return f"{name}: (데이터 부족)"
    return (f"{name:36s} | 누적 {st_['total']:+7.1%} | CAGR {st_['cagr']:+6.1%} | "
            f"변동성 {st_['vol']:5.1%} | Sharpe {st_['sharpe']:5.2f} | "
            f"MDD {st_['mdd']:+6.1%}({st_['mdd_date']}) | 최악일 {st_['worst_day']:+.2%}({st_['worst_date']})")

def downsample(series, step=5):
    out = series[::step]
    if series and (not out or out[-1][0] != series[-1][0]):
        out.append(series[-1])
    return out

def main():
    tickers = sorted({p["long"] for p in PAIRS} | {p["short"] for p in PAIRS} | {"^GSPC", "^KS11", "^VIX"})
    prices = {}
    for t in tickers:
        try:
            prices[t] = fetch(t)
            print(f"  fetched {t}: {len(prices[t])} rows", file=sys.stderr)
        except Exception as e:
            print(f"  FAILED {t}: {e}", file=sys.stderr)
            prices[t] = {}

    START, END = "2007-01-01", "2026-07-10"
    rot_series, rot_events, rot_expo = run(prices, START, END, rules_on=True, rotation=True)
    on_series, on_events, _ = run(prices, START, END, rules_on=True, rotation=False)
    off_series, _, _ = run(prices, START, END, rules_on=False)
    dir_series, dir_events, dir_expo = run_directional(prices, rot_series)

    windows = [
        ("전체 2007~2026", None, None),
        ("2008 금융위기 (07.07~09.06)", "2007-07-01", "2009-06-30"),
        ("2020 팬데믹 (20.01~20.12)", "2020-01-01", "2020-12-31"),
        ("2022 금리인상기 (22.01~22.12)", "2022-01-01", "2022-12-31"),
        ("2026 상반기", "2026-01-01", "2026-07-10"),
    ]
    print("\n=== 전략 B: 디렉셔널 L/S (알파엔진 + 레짐 넷 오버레이) ===")
    for name, a, b in windows:
        print(fmt_stats(name, stats(dir_series, a, b)))
    ne = [x[1] for x in dir_expo]
    print(f"넷 익스포저 실측: max {max(ne):.0f}% / min {min(ne):.0f}% / 평균 {sum(ne)/len(ne):.1f}%")
    print("디렉셔널 손실사다리 이벤트:", len(dir_events), "건")
    for e in dir_events[:15]:
        print("  ", e)

    print("\n=== 전략 A: 룰 ON + 로테이션 (마켓 뉴트럴 최종) ===")
    for name, a, b in windows:
        print(fmt_stats(name, stats(rot_series, a, b)))
    print("\n=== 룰 ON (로테이션 없음, v1) ===")
    for name, a, b in windows:
        print(fmt_stats(name, stats(on_series, a, b)))
    print("\n=== 룰 OFF ===")
    for name, a, b in windows:
        print(fmt_stats(name, stats(off_series, a, b)))

    print("\n=== 페어 폐기 이력 (로테이션 룰) ===")
    for d, typ, pid, detail in rot_events:
        if "폐기" in typ:
            print(f"{d} [{pid}] {typ}")
    print("\n=== 정책 상한 (Net ±50 / Gross 300) 발동 이력 ===")
    caps = [e for e in rot_events if "강제" in e[1] or "축소" in e[1]]
    print(f"{len(caps)}건" if caps else "0건 — 상한 미접촉 (운용 목표 Gross 190% / Net ~0가 상한 안쪽)")
    for e in caps[:20]:
        print(e)
    g = [x[1] for x in rot_expo]; nn = [x[2] for x in rot_expo]
    print(f"\n노출도 실측: Gross max {max(g):.1f}% / min {min(g):.1f}% / 평균 {sum(g)/len(g):.1f}%"
          f" | Net max {max(nn):+.2f}% / min {min(nn):+.2f}%")

    ev_total = {}
    for d, typ, pid, detail in rot_events:
        ev_total[typ.split("→")[0].strip()] = ev_total.get(typ.split("→")[0].strip(), 0) + 1
    print("\n로테이션 런 이벤트 합계:", json.dumps(ev_total, ensure_ascii=False))

    with open("backtest_results.json", "w", encoding="utf-8") as f:
        json.dump({"rules_rot": rot_series, "rules_on": on_series, "rules_off": off_series,
                   "expo": rot_expo, "events": rot_events,
                   "dir": dir_series, "dir_expo": dir_expo, "dir_events": dir_events}, f, ensure_ascii=False)

    # 대시보드용 데이터 (주 단위 다운샘플)
    bt = {
        "meta": {"period": f"{rot_series[0][0]} ~ {rot_series[-1][0]}",
                 "grossCap": GROSS_CAP, "netCap": NET_CAP, "grossTarget": GROSS_TARGET,
                 "generated": END},
        "navRot": [[d, round(v, 2)] for d, v in downsample(rot_series)],
        "navOn":  [[d, round(v, 2)] for d, v in downsample(on_series)],
        "navOff": [[d, round(v, 2)] for d, v in downsample(off_series)],
        "expo":   [[d, g_, n_] for d, g_, n_ in downsample(rot_expo)],
        "retired": [[d, pid] for d, typ, pid, _ in rot_events if "폐기" in typ],
        "navDir": [[d, round(v, 2)] for d, v in downsample(dir_series)],
        "expoDir": [[d, n_] for d, n_ in downsample(dir_expo)],
    }
    with open("backtest_data.js", "w", encoding="utf-8") as f:
        f.write("// 자동 생성: python backtest.py — 수동 편집 금지\nwindow.BACKTEST_DATA = ")
        json.dump(bt, f, ensure_ascii=False)
        f.write(";\n")
    print("\nsaved: backtest_results.json, backtest_data.js")

if __name__ == "__main__":
    main()
