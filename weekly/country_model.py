# -*- coding: utf-8 -*-
"""
국가 선호도 멀티팩터 모델 (학술 문헌 기반).

기존 지역배분이 '가격 모멘텀(YTD)'에만 의존하던 문제를 보완해, 국가배분 학술 연구의
표준 팩터를 결합한다. 단일 신호가 아니라 5개 팩터의 횡단면 z-score 가중 합성.

팩터 & 가중 (근거):
  · Value 25%      — Keimling(StarCapital 2016) CAPE가 10~15년 국가수익률 R²≈0.48.
                     pe vs fair_pe(적정) 괴리. 싸면 +. (장기 평균회귀)
  · Momentum 25%   — Asness·Moskowitz·Pedersen(2013) "Value and Momentum Everywhere".
                     12-1개월 가격모멘텀(최근 1개월 skip). Value와 음의상관 → 결합효과.
  · Earnings 20%   — 이익수정비율(ERR)+1M 수정. Causeway/MSCI: revisions 강건한 예측력.
  · Macro 20%      — Zaremba 외(2022, J.Fin.Markets): OECD CLI 변화가 국가수익률 예측
                     (월 1.43%). + 통화정책 방향(완화 +/긴축 −). AQR Macro Momentum.
  · Currency 10%   — FX 3요소 등가중 (KRW 기준 무헤지 투자자 관점):
                     ① 캐리(상대 정책금리) — Menkhoff 외(2012) carry premium
                     ② 대KRW 12M 모멘텀 — Asness 외(2013) FX momentum
                     ③ REER 밸류 — BIS 실질실효환율 10년 평균 대비 괴리(고평가 −).
                       Asness 외(2013) FX value: REER 저평가 통화가 장기 초과수익.
                     소스: fetch_macro.py가 country_pref에 reer/fx12m 제공(FRED RB*BIS).

각 팩터를 5개국 횡단면 z-score 후 가중합 → 종합점수 → 선호도(비중확대/중립/축소).
출력: 종합점수·순위·팩터별 기여 + 한 줄 근거.
"""
import sys, os, re, json, math, statistics
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# 모델 대상 5개 시장 (한국 PM 관점) — 이머징=중국 중심
MARKETS = [
    ("US", "미국", "^GSPC"),
    ("KR", "한국", "^KS11"),
    ("EU", "유럽", "^STOXX"),
    ("JP", "일본", "^N225"),
    ("CN", "이머징", "EEM"),   # 이머징: 펀더멘털=중국(CN), 모멘텀=EM ETF
]

WEIGHTS = {"value": 0.20, "momentum": 0.20, "earnings": 0.175,
           "macro": 0.15, "currency": 0.075, "risk": 0.20}

# 정책금리(%)·통화정책 방향은 macro-data.js의 policy_rates(FRED 자동수집)에서 읽는다.
# 아래는 그 키가 없는 옛 macro-data.js를 만났을 때의 폴백일 뿐 — 손으로 갱신하지 말 것.
# (하드코딩 시절 KR이 2.50에 굳어 2026-07 금통위 인상을 몇 달간 놓친 사고가 있었다)
POLICY_RATE_FALLBACK = {"US": 3.63, "KR": 2.75, "EU": 2.25, "JP": 0.84, "CN": 1.51}
POLICY_BIAS_FALLBACK = {"US": 0, "KR": -1, "EU": 0, "JP": -1, "CN": 1}


def policy_from(macro):
    """(정책금리, 방향) — macro-data.js의 policy_rates 우선, 없으면 폴백.

    방향(bias)은 주식 관점 부호: 긴축 −1 / 중립 0 / 완화 +1.
    """
    pr = (macro or {}).get("policy_rates") or {}
    if not pr:
        return dict(POLICY_RATE_FALLBACK), dict(POLICY_BIAS_FALLBACK)
    rate = {c: ((pr.get(c) or {}).get("rate") or POLICY_RATE_FALLBACK.get(c))
            for c in POLICY_RATE_FALLBACK}
    bias = {c: (pr.get(c) or {}).get("bias", POLICY_BIAS_FALLBACK.get(c, 0))
            for c in POLICY_BIAS_FALLBACK}
    return rate, bias


def _load(path, var_re):
    t = open(path, encoding="utf-8").read()
    return json.loads(re.search(var_re, t, re.S).group(1))


def load_macro():
    return _load(os.path.join(REPO, "macro-data.js"), r"=\s*(\{.*\})\s*;?\s*\Z")


def load_benchmarks():
    return _load(os.path.join(REPO, "benchmarks.js"),
                 r"window\.BENCHMARKS\s*=\s*(\{.*\})\s*;?\s*\Z")


def mom_12_1(idx):
    """12-1개월 모멘텀(%) — ~252거래일 전 → ~21거래일 전(최근 1개월 skip)."""
    h = (idx or {}).get("history") or {}
    vals = [v for v in (h.get("values") or []) if v]
    if len(vals) < 240:
        return None
    p_start = vals[-252] if len(vals) >= 252 else vals[0]
    p_end = vals[-21]
    if not p_start:
        return None
    return (p_end / p_start - 1) * 100.0


def mom_1m(idx):
    """최근 1개월(~21거래일) 수익률(%). 12-1 모멘텀이 건너뛰는 구간을 메운다."""
    h = (idx or {}).get("history") or {}
    vals = [v for v in (h.get("values") or []) if v]
    if len(vals) < 22:
        return None
    return (vals[-1] / vals[-22] - 1) * 100.0


def drawdown_vol(idx):
    """(52주 고점대비 낙폭%, 실현변동성 20일 연율화%) — 둘 다 못 구하면 (None, None).

    모멘텀(12-1개월)은 최근 1개월을 설계상 건너뛰므로 **직전 한 달의 급락을 못 본다**.
    2026-07 KOSPI가 고점 대비 -31% 급락했는데도 모델이 한국 모멘텀 z를 +1.85(5개국
    최고)로 주고 '비중확대'를 낸 것이 그 때문이다. 낙폭·변동성은 그 사각지대를 메운다.
    """
    h = (idx or {}).get("history") or {}
    v = [x for x in (h.get("values") or []) if x]
    if len(v) < 60:
        return None, None
    win = v[-252:] if len(v) >= 252 else v
    dd = (v[-1] / max(win) - 1) * 100.0
    lr = [math.log(v[i] / v[i - 1]) for i in range(len(v) - 20, len(v)) if v[i - 1]]
    vol = (statistics.pstdev(lr) * math.sqrt(252) * 100.0) if len(lr) > 1 else None
    return dd, vol


# bm-factors.js(Morningstar 후행 집계) 지수명 → 국가코드. 후행 PER이 있는 나라만.
_BMF_TO_CODE = {"KOSPI": "KR", "S&P 500": "US", "STOXX 600": "EU",
                "니케이 225": "JP", "상해종합": "CN"}
CYC_RATIO_WARN = 0.60      # fwd/trailing 이 이보다 낮으면 이익 정점 의심
CYC_MAX_CUT = 0.70         # 밸류 플러스분 최대 차감 비율


def cyclical_pe_ratio():
    """{국가코드: forward PER ÷ trailing PER}. 데이터 없는 나라는 제외.

    경기민감주는 **사이클 정점에서 PER이 가장 낮게 보인다** — 이익이 최대이기 때문이다.
    2026-08 한국이 그 전형: forward PER 3.67(삼성 3.44·하이닉스 3.12가 EWY의 45%)
    대비 후행 19.98 → 비율 0.18. 값 자체는 정확하지만 '싸다'로 읽으면 오독이다.
    (미국은 22.07/26.87 = 0.82로 정상 범위)
    """
    out = {}
    try:
        t = open(os.path.join(REPO, "bm-factors.js"), encoding="utf-8").read()
        d = json.loads(re.search(r"window\.BM_FACTORS\s*=\s*(\{.*\})\s*;", t, re.S).group(1))
    except Exception:                              # noqa: BLE001 — 없으면 가드만 생략
        return out
    for nm, v in (d.get("indices") or {}).items():
        code = _BMF_TO_CODE.get(nm)
        ttm = v.get("pe")
        if code and ttm:
            out[code] = ttm
    return out


def kr_flow_overlay():
    """한국 전용 수급 오버레이 (점수 가산·감산, 범위 ±0.25).

    수급 데이터(외인 순매수·신용잔고)는 한국만 있어 5개국 횡단면 z를 만들 수 없다.
    그래서 팩터가 아니라 **홈마켓 오버레이**로 분리한다(방법론에 명시).
    · 외인 YTD 누적 순매도가 크면 감점
    · 신용잔고 1개월 감소(반대매매·디레버리징 진행)면 감점
    반환: (조정치, 설명문자열)
    """
    adj, notes = 0.0, []
    try:
        fl = json.load(open(os.path.join(REPO, "kr_flows.json"), encoding="utf-8"))
        ytd = ((fl.get("ytd_total") or {}).get("foreign"))
        if ytd is not None and ytd <= -50:        # 조원. 대규모 외인 이탈
            adj -= 0.15
            notes.append("외인 YTD %.0f조 순매도" % ytd)
    except Exception:                             # noqa: BLE001 — 없으면 오버레이만 생략
        pass
    try:
        sp = json.load(open(os.path.join(REPO, "kr_supply.json"), encoding="utf-8"))
        cr = (sp.get("credit") or {}).get("신용잔고_1개월변화_조")
        if cr is not None and cr <= -1.0:         # 신용잔고 급감 = 반대매매 진행
            adj -= 0.10
            notes.append("신용잔고 1M %+.1f조(디레버리징)" % cr)
    except Exception:                             # noqa: BLE001
        pass
    return max(-0.25, adj), ("수급: " + ", ".join(notes)) if notes else ""


def zscores(d):
    """{key: val} → {key: z}. None 은 0(중립) 처리."""
    vals = [v for v in d.values() if v is not None]
    if len(vals) < 2:
        return {k: 0.0 for k in d}
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    sd = var ** 0.5 or 1.0
    return {k: ((v - mean) / sd if v is not None else 0.0) for k, v in d.items()}


def compute():
    macro = load_macro()
    bench = load_benchmarks()
    cp = macro.get("country_pref") or {}
    earn = (macro.get("earnings") or {}).get("countries") or {}
    by_t = {x.get("ticker"): x for x in (bench.get("indices") or [])}
    POLICY_RATE, POLICY_BIAS = policy_from(macro)

    raw = {c: {} for c, _, _ in MARKETS}
    for c, ko, tk in MARKETS:
        p = cp.get(c) or {}
        e = earn.get(c) or {}
        # Value: (fair_pe - pe)/fair_pe — 싸면 +
        pe, fpe = p.get("pe"), p.get("fair_pe")
        # fair가 장기 중앙값(후행 히스토리)이면 비교 대상도 후행(pe_ttm)으로 맞춘다.
        # forward(pe)를 후행 중앙값과 비교하면 fwd<ttm 편향으로 전 국가가 싸 보인다.
        # fair가 시드(EU/JP/CN 축적 중)면 종전대로 forward 비교.
        cur_v = p.get("pe_ttm") if (str(p.get("fair_src") or "").startswith("후행PER")
                                    and p.get("pe_ttm")) else pe
        raw[c]["value"] = ((fpe - cur_v) / fpe) if (cur_v and fpe) else None
        raw[c]["pe_fwd"] = pe          # 사이클 정점 가드에서 후행 PER과 대조
        # Momentum: 12-1개월(장기 추세) + 최근 1개월(급변 반영) 등가중.
        # 12-1만 쓰면 최근 1개월이 설계상 제외돼 직전 달 급락을 전혀 못 본다.
        raw[c]["mom12"] = mom_12_1(by_t.get(tk))
        raw[c]["mom1"] = mom_1m(by_t.get(tk))
        raw[c]["momentum"] = None                  # 아래서 서브팩터 z 평균으로 채움
        # Earnings: ERR(0.7) + 1M수정(0.3)
        err, rev30 = e.get("err"), e.get("rev30")
        raw[c]["earnings"] = (0.7 * err + 0.3 * (rev30 or 0)) if err is not None else None
        # Macro: CLI 성장(cli-100)·0.6 + 통화정책(mon component/100)·0.4
        comp = p.get("components") or {}
        cli = p.get("cli")
        growth = (cli - 100.0) if cli is not None else None
        mon = (comp.get("mon") or 0) / 100.0
        # 정책 방향(POLICY_BIAS)을 명시적으로 더한다 — components.mon만으로는
        # BOK 인상 같은 긴축 전환이 반영되지 않았다(mon_note가 '동결·완화 여지'로 고정).
        bias = POLICY_BIAS.get(c, 0) * 0.5
        if growth is not None:
            raw[c]["macro"] = 0.6 * growth + 0.4 * (mon * 2.0) + bias
        else:
            raw[c]["macro"] = mon * 2.0 + bias
        # Risk: 52주 고점대비 낙폭 + 실현변동성(둘 다 낮을수록 좋음 → 아래서 z 평균)
        dd, vol = drawdown_vol(by_t.get(tk))
        raw[c]["ddown"] = dd                       # 음수일수록 나쁨 → 그대로 z
        raw[c]["vol"] = (-vol) if vol is not None else None   # 높을수록 나쁨 → 부호반전
        raw[c]["risk"] = None                      # 아래서 서브팩터 z 평균으로 채움
        # Currency 3요소 (KR=home이라 전부 0 → FX 노출 없음)
        if c == "KR":
            raw[c]["carry"] = raw[c]["fxmom"] = raw[c]["fxval"] = 0.0
        else:
            raw[c]["carry"] = POLICY_RATE.get(c, 2.5) - POLICY_RATE["KR"]
            raw[c]["fxmom"] = p.get("fx12m")                    # 대KRW 12M 변화율(%)
            rd = (p.get("reer") or {}).get("dev_pct")
            raw[c]["fxval"] = (-rd) if rd is not None else None  # REER 고평가(−)/저평가(+)
        raw[c]["currency"] = None  # 아래서 서브팩터 z 평균으로 채움

    # 팩터별 z-score (currency·risk는 서브팩터 z 등가중 평균)
    zf = {}
    for f in [k for k in WEIGHTS if k not in ("currency", "risk", "momentum")]:
        zf[f] = zscores({c: raw[c][f] for c, _, _ in MARKETS})
    _msub = [zscores({c: raw[c][k] for c, _, _ in MARKETS}) for k in ("mom12", "mom1")]
    zf["momentum"] = {c: round(sum(s[c] for s in _msub) / 2.0, 4) for c, _, _ in MARKETS}
    _subs = [zscores({c: raw[c][k] for c, _, _ in MARKETS}) for k in ("carry", "fxmom", "fxval")]
    zf["currency"] = {c: round(sum(s[c] for s in _subs) / 3.0, 4) for c, _, _ in MARKETS}
    _rsub = [zscores({c: raw[c][k] for c, _, _ in MARKETS}) for k in ("ddown", "vol")]
    zf["risk"] = {c: round(sum(s[c] for s in _rsub) / 2.0, 4) for c, _, _ in MARKETS}
    for c, _, _ in MARKETS:
        raw[c]["currency"] = {k: raw[c][k] for k in ("carry", "fxmom", "fxval")}
        raw[c]["risk"] = {"ddown": raw[c]["ddown"], "vol": raw[c]["vol"]}
        raw[c]["momentum"] = {"mom12": raw[c]["mom12"], "mom1": raw[c]["mom1"]}

    # 밸류 함정 가드: 급락으로 PER만 싸진 경우를 걸러낸다.
    # 이익수정(earnings)이 마이너스인데 밸류가 플러스면, 싼 게 아니라 이익이 깎이는
    # 중일 수 있다. 그런 조합에서 밸류 z의 플러스분을 최대 50%까지 깎는다.
    # (2026-08 한국: 밸류 z+1.87 · 이익수정 z−0.18 — 전형적 사례)
    trap = {}
    for c, _, _ in MARKETS:
        zv, ze = zf["value"][c], zf["earnings"][c]
        if zv > 0 and ze < 0:
            cut = min(0.5, abs(ze) / 2.0)
            trap[c] = round(zv * cut, 4)
            zf["value"][c] = zv - trap[c]

    # 사이클 정점 가드: forward PER이 후행 대비 극단적으로 낮으면 '싼 게 아니라
    # 이익이 정점'일 수 있다. 비율이 낮을수록 밸류 플러스분을 더 깎는다.
    cyc = {}
    ttm_pe = cyclical_pe_ratio()
    for c, _, _ in MARKETS:
        fwd, ttm = raw[c].get("pe_fwd"), ttm_pe.get(c)
        zv = zf["value"][c]
        if not (fwd and ttm and zv > 0):
            continue
        ratio = fwd / ttm
        if ratio < CYC_RATIO_WARN:
            frac = min(CYC_MAX_CUT, (CYC_RATIO_WARN - ratio) / CYC_RATIO_WARN)
            cyc[c] = {"ratio": round(ratio, 2), "cut": round(zv * frac, 4),
                      "fwd": fwd, "ttm": ttm}
            zf["value"][c] = zv - cyc[c]["cut"]

    # 종합 z + 선호도 (한국은 수급 오버레이 가산)
    kr_adj, kr_note = kr_flow_overlay()
    out = []
    for c, ko, tk in MARKETS:
        contrib = {f: round(zf[f][c] * WEIGHTS[f], 3) for f in WEIGHTS}
        score = sum(contrib.values())
        row = {"code": c, "name": ko,
               "z": {f: round(zf[f][c], 2) for f in WEIGHTS},
               "contrib": contrib, "raw": {f: raw[c][f] for f in WEIGHTS}}
        if c == "KR" and kr_adj:
            score += kr_adj
            row["overlay"] = {"adj": round(kr_adj, 3), "note": kr_note}
        if trap.get(c):
            row["value_trap_cut"] = trap[c]
        if cyc.get(c):
            row["cyclical_peak"] = cyc[c]
        row["score"] = round(score, 3)
        out.append(row)
    out.sort(key=lambda x: x["score"], reverse=True)

    # 선호도: 종합 z 임계 (±0.3) — 횡단면 상대
    for r in out:
        s = r["score"]
        r["pref"] = "비중확대" if s >= 0.25 else ("축소" if s <= -0.25 else "중립")
    return out


_FAC_KO = {"value": "밸류", "momentum": "모멘텀", "earnings": "이익수정",
           "macro": "매크로", "currency": "통화(FX3요소)", "risk": "리스크(낙폭·변동성)"}


def rationale(r):
    """모델 팩터 기반 plain 근거: 주도 팩터(+)·부담 팩터(−)."""
    z = r["z"]
    pos = sorted([(f, v) for f, v in z.items() if v >= 0.4], key=lambda x: -x[1])
    neg = sorted([(f, v) for f, v in z.items() if v <= -0.4], key=lambda x: x[1])
    parts = []
    if pos:
        parts.append("강점 " + "·".join(_FAC_KO[f] for f, _ in pos))
    if neg:
        parts.append("부담 " + "·".join(_FAC_KO[f] for f, _ in neg))
    if r.get("value_trap_cut"):
        parts.append("밸류함정 보정 −%.2f(이익수정 마이너스)" % r["value_trap_cut"])
    if r.get("cyclical_peak"):
        cp = r["cyclical_peak"]
        parts.append("사이클정점 보정 −%.2f(fwd PER %.1f vs 후행 %.1f, 비율 %.2f)"
                     % (cp["cut"], cp["fwd"], cp["ttm"], cp["ratio"]))
    if r.get("overlay"):
        parts.append("%s(%+.2f)" % (r["overlay"]["note"], r["overlay"]["adj"]))
    verdict = {"비중확대": "→ 비중확대", "축소": "→ 축소", "중립": "→ 중립"}.get(r["pref"], "")
    return (", ".join(parts) + " " + verdict).strip()


def main():
    res = compute()
    out = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    out.write("국가 선호도 멀티팩터 모델 결과 (Value25·Momentum25·Earnings20·Macro20·FX10)\n")
    out.write("=" * 78 + "\n")
    for i, r in enumerate(res, 1):
        out.write("%d. %-4s [%s] 종합 %+.3f\n" % (i, r["name"], r["pref"], r["score"]))
        out.write("    %s\n" % rationale(r))
        out.write("    기여: " + ", ".join("%s %+.3f" % (f, r["contrib"][f]) for f in WEIGHTS) + "\n")
    out.flush()


if __name__ == "__main__":
    import io
    main()
