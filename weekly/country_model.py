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
import sys, os, re, json
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

WEIGHTS = {"value": 0.25, "momentum": 0.25, "earnings": 0.20, "macro": 0.20, "currency": 0.10}

# 정책금리(%) — 캐리(KRW 대비) 근사. (BOK 2.50 기준)
POLICY_RATE = {"US": 3.625, "KR": 2.50, "EU": 2.25, "JP": 0.50, "CN": 3.00}


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

    raw = {c: {} for c, _, _ in MARKETS}
    for c, ko, tk in MARKETS:
        p = cp.get(c) or {}
        e = earn.get(c) or {}
        # Value: (fair_pe - pe)/fair_pe — 싸면 +
        pe, fpe = p.get("pe"), p.get("fair_pe")
        raw[c]["value"] = ((fpe - pe) / fpe) if (pe and fpe) else None
        # Momentum: 12-1
        raw[c]["momentum"] = mom_12_1(by_t.get(tk))
        # Earnings: ERR(0.7) + 1M수정(0.3)
        err, rev30 = e.get("err"), e.get("rev30")
        raw[c]["earnings"] = (0.7 * err + 0.3 * (rev30 or 0)) if err is not None else None
        # Macro: CLI 성장(cli-100)·0.6 + 통화정책(mon component/100)·0.4
        comp = p.get("components") or {}
        cli = p.get("cli")
        growth = (cli - 100.0) if cli is not None else None
        mon = (comp.get("mon") or 0) / 100.0
        if growth is not None:
            raw[c]["macro"] = 0.6 * growth + 0.4 * (mon * 2.0)  # mon 스케일 맞춤
        else:
            raw[c]["macro"] = mon * 2.0
        # Currency 3요소 (KR=home이라 전부 0 → FX 노출 없음)
        if c == "KR":
            raw[c]["carry"] = raw[c]["fxmom"] = raw[c]["fxval"] = 0.0
        else:
            raw[c]["carry"] = POLICY_RATE.get(c, 2.5) - POLICY_RATE["KR"]
            raw[c]["fxmom"] = p.get("fx12m")                    # 대KRW 12M 변화율(%)
            rd = (p.get("reer") or {}).get("dev_pct")
            raw[c]["fxval"] = (-rd) if rd is not None else None  # REER 고평가(−)/저평가(+)
        raw[c]["currency"] = None  # 아래서 서브팩터 z 평균으로 채움

    # 팩터별 z-score (currency는 3요소 z 등가중 평균)
    zf = {}
    for f in [k for k in WEIGHTS if k != "currency"]:
        zf[f] = zscores({c: raw[c][f] for c, _, _ in MARKETS})
    _subs = [zscores({c: raw[c][k] for c, _, _ in MARKETS}) for k in ("carry", "fxmom", "fxval")]
    zf["currency"] = {c: round(sum(s[c] for s in _subs) / 3.0, 4) for c, _, _ in MARKETS}
    for c, _, _ in MARKETS:
        raw[c]["currency"] = {k: raw[c][k] for k in ("carry", "fxmom", "fxval")}

    # 종합 z + 선호도
    out = []
    for c, ko, tk in MARKETS:
        contrib = {f: round(zf[f][c] * WEIGHTS[f], 3) for f in WEIGHTS}
        score = round(sum(contrib.values()), 3)
        out.append({"code": c, "name": ko, "score": score,
                    "z": {f: round(zf[f][c], 2) for f in WEIGHTS},
                    "contrib": contrib, "raw": {f: raw[c][f] for f in WEIGHTS}})
    out.sort(key=lambda x: x["score"], reverse=True)

    # 선호도: 종합 z 임계 (±0.3) — 횡단면 상대
    for r in out:
        s = r["score"]
        r["pref"] = "비중확대" if s >= 0.25 else ("축소" if s <= -0.25 else "중립")
    return out


_FAC_KO = {"value": "밸류", "momentum": "모멘텀", "earnings": "이익수정",
           "macro": "매크로", "currency": "통화(FX3요소)"}


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
