#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
모닝 노트 생성기 → morning-note.js (window.MORNING = {...})

이미 생성된 데이터를 조합만 한다(추가 LLM/API 호출 없음):
  - briefings-archive.js / briefings-archive-asia.js : 미국장·아시아장 브리핑
    (report.sections·outlook 은 generate_briefing.py 가 LLM으로 생성한 오피니언)
  - daily-data.js  : 지역 지수·통합 등락 종목
  - macro-data.js  : VIX·10Y·WTI·USD/KRW·공포탐욕·VKOSPI 지표

daily.html '🌅 모닝 노트' 탭이 이 파일을 소비한다. cron(daily-update.yml)에서 매일 갱신.
데이터가 없거나 파싱 실패해도 죽지 않고 가능한 만큼 채운다(fail-safe).
"""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "morning-note.js"
KST = timezone(timedelta(hours=9))


def load_js(name):
    """window.X = {...}; 형태의 js 데이터파일을 파싱해 파이썬 객체로."""
    p = HERE / name
    if not p.exists():
        return None
    try:
        txt = p.read_text(encoding="utf-8")
        m = re.search(r"=\s*(\{.*\}|\[.*\])\s*;?\s*$", txt, re.S)
        if not m:
            return None
        return json.loads(m.group(1))
    except Exception as e:
        print(f"  [warn] {name} 파싱 실패: {e}")
        return None


def latest(archive):
    if isinstance(archive, list) and archive:
        return sorted(archive, key=lambda b: b.get("as_of", ""), reverse=True)[0]
    return None


def build():
    us_arc = load_js("briefings-archive.js")
    asia_arc = load_js("briefings-archive-asia.js")
    D = load_js("daily-data.js") or {}
    M = load_js("macro-data.js") or {}

    us = latest(us_arc) or load_js("briefing-data.js") or {}
    asia = latest(asia_arc) or load_js("briefing-data.js") or {}
    us_rep = (us.get("report") or {})
    asia_rep = (asia.get("report") or {})

    # ── 헤드라인·리드 ──
    us_secs = us_rep.get("sections") or []
    headline = us_rep.get("headline") or (us_secs[0]["head"] if us_secs else us.get("title", ""))
    lead = ""
    for p in (us.get("paragraphs") or []):
        t = str(p or "").strip()
        if t.startswith("_"):
            lead = t.lstrip("_ ").strip()
            break

    # ── 지역 지수 ──
    indices = []
    for r in (D.get("regions") or []):
        idx = (r.get("indices") or [None])[0]
        if idx:
            indices.append({"flag": r.get("flag", ""), "name": idx.get("name", ""),
                            "chg": idx.get("chgPct")})

    # ── 미국 간밤 (브리핑 섹션 상위) ──
    us_items = []
    for s in us_secs[:5]:
        det = []
        for pt in (s.get("points") or []):
            if pt.get("text"):
                det.append(pt["text"])
            for u in (pt.get("subs") or []):
                det.append(u)
        us_items.append({"head": s.get("head", ""), "detail": " · ".join(det[:2])})

    # ── 아시아 (브리핑 섹션 상위) ──
    asia_items = [s.get("head", "") for s in (asia_rep.get("sections") or [])[:4] if s.get("head")]

    # ── 통합 등락 종목 (daily commentary.movers) ──
    movers = []
    for r in (D.get("regions") or []):
        c = r.get("commentary")
        if not isinstance(c, dict):
            continue
        for m in (c.get("movers") or []):
            if m.get("chgPct") is None:
                continue
            movers.append({"flag": r.get("flag", ""), "name": m.get("name", ""),
                           "ticker": m.get("ticker", ""), "pct": m["chgPct"]})
    ups = sorted([m for m in movers if m["pct"] > 0], key=lambda x: -x["pct"])[:5]
    downs = sorted([m for m in movers if m["pct"] < 0], key=lambda x: x["pct"])[:5]

    # ── 오늘 관전 포인트 (미국 브리핑 outlook) ──
    outlook = [str(o).strip() for o in (us.get("outlook") or []) if str(o).strip()][:4]

    # ── 매크로 스냅샷 ──
    ind = M.get("indicators") or {}
    macro = []
    for key in ["vix", "us10y", "oil_yoy", "usdkrw", "cnn_fng", "vkospi"]:
        d = ind.get(key)
        if not d or d.get("current") is None:
            continue
        v = d["current"]
        unit = d.get("unit", "")
        if key == "usdkrw":
            val = f"{round(v):,}원"
        elif key == "oil_yoy":
            val = f"{'+' if v > 0 else ''}{v:.1f}%"
        elif unit == "%":
            val = f"{v:.2f}%"
        else:
            val = f"{v:g}"
        macro.append({"name": d.get("name", key), "value": val,
                      "signal": d.get("signal", ""), "cls": d.get("signal_cls", "neu"),
                      "as_of": d.get("as_of", "")})

    # ── 리스크 톤(룰 기반 요약) ──
    up_idx = sum(1 for x in indices if (x.get("chg") or 0) > 0)
    vix = (ind.get("vix") or {}).get("current")
    if vix is not None and vix < 18 and up_idx >= 3:
        tone = "위험선호(risk-on)"
    elif vix is not None and vix >= 25:
        tone = "위험회피(risk-off)"
    else:
        tone = "혼조·중립"

    as_of = D.get("as_of") or us.get("as_of") or ""
    now = datetime.now(timezone.utc)
    payload = {
        "as_of": as_of,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date_kst": now.astimezone(KST).strftime("%Y-%m-%d %H:%M"),
        "tone": tone,
        "headline": headline,
        "lead": lead,
        "indices": indices,
        "us": us_items,
        "us_as_of": us.get("as_of", ""),
        "asia": asia_items,
        "asia_as_of": asia.get("as_of", ""),
        "movers_up": ups,
        "movers_down": downs,
        "outlook": outlook,
        "macro": macro,
    }
    return payload


def main():
    payload = build()
    js = "// 모닝 노트 데이터 (공개 데이터, 평문). morning_note.py로 갱신 — 기존 브리핑·매크로·시황 조합.\n"
    js += "window.MORNING = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    OUT.write_text(js, encoding="utf-8")
    print(f"[morning_note] → {OUT.name} 저장 완료 "
          f"(as_of {payload['as_of']}, 미국 {len(payload['us'])}섹션, "
          f"등락 {len(payload['movers_up'])}+{len(payload['movers_down'])}, "
          f"매크로 {len(payload['macro'])}, {len(js):,} bytes)")


if __name__ == "__main__":
    main()
