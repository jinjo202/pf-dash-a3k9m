# -*- coding: utf-8 -*-
"""
서버사이드(GitHub Actions) '오늘의 CIO 데일리' 생성기 — fm.html CIO 패널용.

시황 브리핑(generate_briefing.py)과 동일한 인프라(구독 CLI 우선)를 재사용하되,
목적이 다르다: 시황 서술이 아니라 **CIO의 사고 흐름**을 매일 업데이트한다.
  - 최근 수 주 시장을 움직인 이슈들의 인과 체인(chain)을 전일 entry에서 이어받아 갱신
  - 각 이슈가 기술적(수급)인지 펀더멘털(이익 훼손)인지 판정
  - 종합 포지셔닝 결론(매크로/비중/국가/섹터/구체 매매)까지 도출
  - 최근 정성 요인(factors)도 뉴스 기반으로 자동 갱신 → fm.html renderRecentFactors가 사용

흐름:
  1. benchmarks.js + daily-data.js + macro-data.js(regime) + fm-data.js(시드) 로드
  2. 뉴스 수집: 연합인포맥스 섹션 RSS + Investing.com RSS + Seeking Alpha RSS
     + Bloomberg(Google News RSS 경유). 실패 시 소스별로 조용히 생략.
  3. 전일 CIO entry(fm-cio.js)를 프롬프트에 넣어 '판단의 연속성' 유지
  4. Claude 호출 → JSON → fm-cio.js(entries newest-first, 30개 유지) 게시

사용법:
  python briefing/generate_cio.py [--slot auto|us_close|asia_close] [--as-of YYYY-MM-DD]
                                  [--dry-run] [--skip-if-current] [--use-cli]

자격증명: CLAUDE_CODE_OAUTH_TOKEN(구독, 우선) 또는 ANTHROPIC_API_KEY.
--use-cli 는 로컬에서 토큰 env 없이 로그인된 Claude Code CLI(구독)로 실행할 때.

종료코드: 0 성공 / 2 인자·환경 / 3 데이터 / 4 API·파싱
"""
import sys, os, re, json, argparse, subprocess
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import generate_briefing as gb  # noqa: E402  (데이터 로더·RSS·Claude 호출 재사용)

FM_CIO_JS = os.path.join(REPO, "fm-cio.js")
FM_DATA_JS = os.path.join(REPO, "fm-data.js")
MACRO_JS = os.path.join(REPO, "macro-data.js")
KST = timezone(timedelta(hours=9))
MAX_KEEP = 30


# ----------------------------------------------------------------------------
# 데이터 로드
# ----------------------------------------------------------------------------
def load_js_var_node(path, varname):
    """주석·비따옴표 키가 섞인 JS(fm-data.js 등)를 node로 평가해 JSON으로 회수."""
    script = ("global.window={};eval(require('fs').readFileSync(%s,'utf8'));"
              "process.stdout.write(JSON.stringify(window.%s||null));"
              % (json.dumps(path), varname))
    try:
        proc = subprocess.run(["node", "-e", script], capture_output=True,
                              text=True, encoding="utf-8", timeout=60)
        if proc.returncode == 0 and proc.stdout.strip():
            return json.loads(proc.stdout)
    except Exception:
        pass
    return None


def load_fm_cio():
    if not os.path.exists(FM_CIO_JS):
        return {"entries": []}
    try:
        data = gb._parse_assign(FM_CIO_JS, r"window\.FM_CIO\s*=\s*(\{.*\})\s*;?\s*$")
        if isinstance(data.get("entries"), list):
            return data
    except Exception:
        pass
    return {"entries": []}


def slim_bench(bench):
    """CIO 판단에 필요한 핵심 지수만 — mtd/ytd/밸류 포함(브리핑용 slim보다 넓게)."""
    if not bench:
        return []
    want = ("KOSPI", "KOSDAQ", "S&P 500", "NASDAQ", "필라델피아 반도체", "VIX",
            "KRW=X", "^TNX", "CL=F", "KR 10Y", "닛케이 225", "상해종합")
    out = []
    for x in (bench.get("indices") or []):
        if x.get("name") in want or x.get("ticker") in want:
            row = {k: x.get(k) for k in
                   ("name", "current", "daily_pct", "mtd_pct", "ytd_pct")
                   if x.get(k) is not None}
            val = x.get("valuation") or {}
            if val.get("pe") is not None:
                row["fwd_pe"] = val.get("pe")
            out.append(row)
    return out


def slim_macro(macro):
    if not macro:
        return None
    reg = macro.get("regime") or {}
    pillars = reg.get("pillars") or {}
    return {
        "as_of": macro.get("as_of"),
        "regime_score": reg.get("score"),
        "pillars": {k: {"name": (v or {}).get("name"), "score": (v or {}).get("score")}
                    for k, v in pillars.items() if isinstance(v, dict)},
    }


def slim_fm_seeds(fm):
    if not fm:
        return None
    return {
        "sectors": [{"name": s.get("name"), "stance": s.get("stance"),
                     "conviction": s.get("conviction")}
                    for s in (fm.get("sectors") or [])],
        "stocks": [{"ticker": s.get("ticker"), "name": s.get("name"),
                    "action": s.get("action"), "conviction": s.get("conviction")}
                   for s in (fm.get("stocks") or [])],
        "themes": [{"name": t.get("name"), "stage": t.get("stage"),
                    "conviction": t.get("conviction")}
                   for t in (fm.get("themes") or [])],
        "recent_factors_seed": fm.get("recent_factors"),
    }


# ----------------------------------------------------------------------------
# 뉴스 수집 (실패 시 소스별 조용히 생략 — 생성은 계속)
# ----------------------------------------------------------------------------
GLOBAL_FEEDS = [
    ("Investing.com", "https://www.investing.com/rss/news_25.rss", 8),
    ("Investing.com", "https://www.investing.com/rss/news_14.rss", 5),
    ("SeekingAlpha", "https://seekingalpha.com/market_currents.xml", 8),
    ("Bloomberg", "https://news.google.com/rss/search?q=site:bloomberg.com+"
                  "(markets+OR+stocks+OR+semiconductor+OR+Fed+OR+Korea)+when:2d"
                  "&hl=en-US&gl=US&ceid=US:en", 8),
]


def fetch_global_news(cap=22):
    seen, out = set(), []
    for label, url, limit in GLOBAL_FEEDS:
        try:
            items = gb._rss_items(url, limit)
        except Exception:
            continue
        for it in items:
            t = it["title"]
            key = re.sub(r"\s+", "", t.lower())[:48]
            if key in seen:
                continue
            seen.add(key)
            out.append({"source": label, "title": t, "desc": it["desc"]})
    return out[:cap]


def fetch_einfomax_all(cap=14):
    seen, out = set(), []
    for region in ("asia", "us"):
        try:
            items = gb.fetch_einfomax_news(region, per_section=6, cap=10)
        except Exception:
            continue
        for it in items:
            key = re.sub(r"\s+", "", it["title"])[:40]
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
    return out[:cap]


# ----------------------------------------------------------------------------
# 프롬프트
# ----------------------------------------------------------------------------
SYSTEM = """당신은 한국 기관의 고유자금(약 5,250억원) 멀티에셋 포트폴리오를 운용하는 CIO다.
최우선 목표는 절대수익이며 동시에 글로벌 주식 BM 대비 아웃퍼폼해야 한다.
포트폴리오 성격: 한국(반도체/HBM·조선·방산·원전·금융 밸류업) 비중이 크고, 미국은 AI/반도체(NVDA·AVGO·TSM 등)·산업재·유틸리티 중심. 세부 스탠스는 payload의 [fm_seeds]에 있다.

매일 장 마감 후 '오늘의 CIO 데일리'를 작성한다. 임무:
1) 최근 수 주간 시장을 움직인 이슈들의 **인과 체인(chain)**을 유지·갱신한다.
   [전일 CIO entry]가 있으면 그 chain을 이어받아: 오늘 뉴스·데이터로 확인된 새 이슈를 추가하고,
   판단이 바뀐 항목은 read/verdict를 수정하고, 영향이 소멸한 이슈는 제거한다. 체인은 인과·시간 순서.
   (예시 흐름: 마이크론 어닝 서프라이즈 → 애플 가격 인상(칩플레이션 전가) → OpenAI 상장 연기 →
   반도체 수출단가 MoM 하락 → 레버리지 ETF 유동성발 국내 변동성 → 국민연금 리밸런싱 우려 →
   메타 자체칩·'컴퓨팅 과잉' 발언 → 반도체 조정 — 이런 식으로 이슈가 서로 물려 있다.)
2) 각 이슈의 성격을 판정한다: technical(수급·포지셔닝·유동성·기계적 매도) / fundamental(이익·사이클·수요 훼손) / mixed.
   이 판정이 대응을 가른다 — 기술적이면 조정은 매수 기회, 펀더멘털이면 디리스킹.
3) 특히 다음 4개 축은 매일 반드시 점검한다: ① 반도체(메모리) 마진·가격 ② 칩플레이션(원가의 전방 전가와 수요 반작용)
   ③ 빅테크 FCF·capex 부담 ④ AI 밸류에이션·유동성 이벤트(IPO 등).
4) 종합해 오늘의 포지셔닝 결론을 내린다. 막연한 양비론 금지 — 결정 지향. 판단을 바꿀 트리거를 명시.

[수치 규칙 — 매우 중요]
- 지수·등락률·밸류 수치는 payload 데이터([benchmarks]·[daily]·[macro])에 있는 값만 인용한다.
- 뉴스 헤드라인은 정성적 맥락·방향·인과 근거로만 쓰고, 헤드라인 속 구체 수치는 데이터로 확인되지 않으면 옮기지 않는다.
- 데이터·뉴스로 확인 불가한 일정·통계·발언을 지어내지 않는다. 확신이 낮으면 verdict를 watch로 두고 그렇다고 쓴다.
- |일간등락|≥7% 지수는 데이터 오류(세션갭) 가능성을 감안해 단정을 피한다.

[출력 JSON 스키마 — 키 이름 정확히]
{
 "headline": "오늘의 한 줄 결론(40자 내외)",
 "market_pulse": "오늘 시장 요약 2~4문장(데이터 근거)",
 "changes": "전일 판단 대비 달라진 점 1~3문장. 전일 entry 없으면 '초기 작성'",
 "chain": [
   {"issue":"이슈명(간결)","date":"M/D 또는 M월","nature":"technical|fundamental|mixed",
    "verdict":"pos|neg|watch","read":"CIO 해석 1~2문장(왜 중요한지·진짜 우려인지)","action":"대응 한 줄"}
 ],
 "factors": [
   {"date":"YYYY-MM-DD 또는 M/D","tag":"메모리|칩플레이션|빅테크FCF|AI밸류|수급|매크로 등","dir":"pos|neg|watch",
    "title":"...","detail":"확인된 사실 요약","implication":"본 계정 함의","affected":["티커"]}
 ],
 "positioning": {
   "macro_view": "1~3문장",
   "equity_weight": {"stance":"확대|유지|축소","text":"순노출 판단 근거 1~2문장"},
   "country": "국가 배분 판단 1~2문장",
   "sector": "섹터 판단 1~2문장",
   "trades": [{"action":"매수|확대|축소|매도|유지|헤지","ticker":"...","name":"...","reason":"..."}]
 },
 "conclusion": "종합 결론 문단 — 오늘 무엇을 하고 무엇을 하지 않는지 + 판단을 바꿀 트리거 2~3개"
}
chain 4~8개, factors 2~5개(오늘 뉴스로 확인된 신규/갱신만), trades 0~5개(없으면 빈 배열).
as_of/slot/generated_utc 는 출력하지 말 것(스크립트가 채운다)."""


def build_payload(as_of, slot):
    daily = None
    try:
        daily = gb.load_daily()
    except Exception:
        pass
    bench = gb.load_benchmarks()
    macro = load_js_var_node(MACRO_JS, "MACRO")
    fm = load_js_var_node(FM_DATA_JS, "FM_DATA")
    prev_entries = load_fm_cio().get("entries") or []
    prev = next((e for e in prev_entries if e.get("as_of") != as_of), None)

    regions_payload = []
    if daily:
        rk = gb.regions_by_key(daily)
        regions_payload = [gb.slim_region(rk[k]) for k in ("korea", "us") if k in rk]

    blocks = [
        "작성 기준일(as_of): %s / 세션: %s" % (as_of, "미국장 마감 후" if slot == "us_close" else "아시아장 마감 후"),
        "[benchmarks 지수(현재·일간·MTD·YTD·FwdPER)]\n" + json.dumps(slim_bench(bench), ensure_ascii=False),
        "[macro 레짐]\n" + json.dumps(slim_macro(macro), ensure_ascii=False),
        "[daily 한국·미국 (지수·섹터·특징주 movers·events)]\n" + json.dumps(regions_payload, ensure_ascii=False),
        "[fm_seeds 포트폴리오 스탠스(섹터·종목·테마·기존 정성요인 시드)]\n" + json.dumps(slim_fm_seeds(fm), ensure_ascii=False),
    ]
    if prev:
        blocks.append("[전일 CIO entry (chain을 이어받아 갱신할 것)]\n" +
                      json.dumps(prev, ensure_ascii=False))
    einfo = fetch_einfomax_all()
    if einfo:
        blocks.append("[뉴스: 연합인포맥스(국내) — 정성 근거 전용]\n" +
                      json.dumps(einfo, ensure_ascii=False))
    glob = fetch_global_news()
    if glob:
        blocks.append("[뉴스: 글로벌(Investing.com·SeekingAlpha·Bloomberg) — 정성 근거 전용]\n" +
                      json.dumps(glob, ensure_ascii=False))
    blocks.append("위 데이터·뉴스만 근거로 시스템 규칙의 스키마에 따라 JSON을 출력하라.")
    return "\n\n".join(blocks)


# ----------------------------------------------------------------------------
# Claude 호출 / 게시
# ----------------------------------------------------------------------------
def call_model(use_cli):
    if use_cli or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return gb._call_claude_cli
    if os.environ.get("ANTHROPIC_API_KEY"):
        return gb._call_claude_sdk
    sys.stderr.write("자격증명 없음: CLAUDE_CODE_OAUTH_TOKEN / ANTHROPIC_API_KEY / --use-cli\n")
    sys.exit(2)


def validate(result):
    if not isinstance(result, dict):
        return "not a dict"
    for k in ("headline", "market_pulse", "chain", "positioning", "conclusion"):
        if not result.get(k):
            return "missing key: " + k
    if not isinstance(result["chain"], list) or not result["chain"]:
        return "empty chain"
    pos = result["positioning"]
    if not isinstance(pos, dict) or not pos.get("equity_weight"):
        return "positioning.equity_weight missing"
    return None


def publish(entry):
    data = load_fm_cio()
    entries = [e for e in (data.get("entries") or [])
               if e.get("as_of") != entry["as_of"]]
    entries.insert(0, entry)
    entries.sort(key=lambda e: e.get("as_of") or "", reverse=True)
    entries = entries[:MAX_KEEP]
    body = json.dumps({"updated_utc": entry["generated_utc"], "entries": entries},
                      ensure_ascii=False, indent=2)
    with open(FM_CIO_JS, "w", encoding="utf-8") as f:
        f.write("// 오늘의 CIO 데일리 — briefing/generate_cio.py 가 자동 생성 (직접 편집 금지).\n"
                "// 사고 흐름(chain)·정성 요인(factors)·포지셔닝 결론. newest-first, %d개 유지.\n"
                "window.FM_CIO = %s;\n" % (MAX_KEEP, body))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["auto", "us_close", "asia_close"], default="auto")
    ap.add_argument("--as-of", dest="as_of", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-if-current", action="store_true",
                    help="같은 as_of+slot entry가 이미 있으면 생략(백업 cron 멱등성)")
    ap.add_argument("--use-cli", action="store_true",
                    help="토큰 env 없이 로컬 로그인된 Claude Code CLI(구독)로 호출")
    args = ap.parse_args()

    now_kst = datetime.now(KST)
    slot = args.slot
    if slot == "auto":
        slot = "us_close" if now_kst.hour < 12 else "asia_close"
    as_of = args.as_of or now_kst.strftime("%Y-%m-%d")

    if args.skip_if_current:
        cur = (load_fm_cio().get("entries") or [None])[0] or {}
        if cur.get("as_of") == as_of and cur.get("slot") == slot:
            print("skip: CIO daily for %s (%s) already exists" % (as_of, slot))
            gb.gh_output(status="skipped", as_of=as_of)
            return

    payload = build_payload(as_of, slot)
    fn = call_model(args.use_cli)
    try:
        result = fn(SYSTEM, payload)
    except SystemExit:
        raise
    except Exception as e:
        sys.stderr.write("Claude 호출/파싱 실패: %s\n" % e)
        sys.exit(4)

    err = validate(result)
    if err:
        sys.stderr.write("응답 스키마 불량: %s\n" % err)
        sys.exit(4)

    entry = {
        "as_of": as_of,
        "slot": slot,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headline": result.get("headline") or "",
        "market_pulse": result.get("market_pulse") or "",
        "changes": result.get("changes") or "",
        "chain": result.get("chain") or [],
        "factors": result.get("factors") or [],
        "positioning": result.get("positioning") or {},
        "conclusion": result.get("conclusion") or "",
    }

    if args.dry_run:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return

    publish(entry)
    print("generated: CIO daily %s (%s) -> fm-cio.js (chain %d · factors %d)"
          % (as_of, slot, len(entry["chain"]), len(entry["factors"])))
    gb.gh_output(status="generated", as_of=as_of)


if __name__ == "__main__":
    main()
