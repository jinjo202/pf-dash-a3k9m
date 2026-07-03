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
  1. benchmarks.js(+history로 이평·RSI·낙폭 계산) + kr_flows/kr_deposit(수급·유동성)
     + daily-data.js + macro-data.js(regime) + fm-data.js(시드·ETF 유니버스) 로드
  2. 뉴스 수집: 연합인포맥스 섹션 RSS + Investing.com RSS + Seeking Alpha RSS
     + Bloomberg(Google News RSS 경유). 실패 시 소스별로 조용히 생략.
  3. 전일 CIO entry(fm-cio.js)를 프롬프트에 넣어 '판단의 연속성' 유지
  4. 3콜 투자위원회: 초안 CIO → Devil's Advocate 반박 → 최종 종합(debate 필드에
     수용/기각 기록). 반박·종합 실패 시 초안으로 degrade. --no-debate로 1콜 모드.
  5. fm-cio.js(entries newest-first, 30개 유지) 게시. trades는 ETF 티커 단위.

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
KR_FLOWS = os.path.join(REPO, "kr_flows.json")
KR_DEPOSIT = os.path.join(REPO, "kr_deposit.json")
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


def etf_universe(fm):
    """fm-data.js 시드에서 실행 가능한 ETF 유니버스 추출 — trades는 이 안에서 고른다."""
    if not fm:
        return []
    out, seen = [], set()

    def add(e, ctx, stance):
        tk = e.get("ticker")
        if not tk or tk in seen:
            return
        seen.add(tk)
        out.append({"ticker": tk, "name": e.get("name"), "ctx": ctx,
                    "stance": stance, "note": e.get("note")})

    for s in (fm.get("sectors") or []):
        for e in (s.get("etfs") or []):
            add(e, "섹터:" + (s.get("name") or ""), s.get("stance"))
        for e in (s.get("kr_etfs") or []):
            add(e, "한국섹터:" + (s.get("name") or ""), s.get("stance"))
    for r in (fm.get("regions") or []):
        for e in (r.get("etfs") or []):
            add(e, "지역:" + (r.get("name") or ""), r.get("stance"))
    for t in (fm.get("themes") or []):
        for p in (t.get("plays") or []):
            if p.get("type") == "etf":
                add(p, "테마:" + (t.get("name") or ""), None)
    return out


# ----------------------------------------------------------------------------
# 기술적 지표·수급·유동성 (benchmarks history + kr_flows + kr_deposit)
# ----------------------------------------------------------------------------
def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def technicals(bench):
    """지수별 이평선 이격·낙폭·RSI — benchmarks.js history(약 260영업일)로 계산."""
    if not bench:
        return []
    want = ("KOSPI", "KOSDAQ", "S&P 500", "NASDAQ", "필라델피아 반도체", "VIX")
    out = []
    for x in (bench.get("indices") or []):
        if x.get("name") not in want:
            continue
        h = (x.get("history") or {}).get("values") or []
        vals = [v for v in h if isinstance(v, (int, float))]
        if len(vals) < 60:
            continue
        cur = vals[-1]

        def ma(n):
            return sum(vals[-n:]) / n

        hi60 = max(vals[-60:])
        # RSI(14)
        rsi = None
        if len(vals) >= 15:
            gains = losses = 0.0
            for a, b in zip(vals[-15:-1], vals[-14:]):
                d = b - a
                if d >= 0:
                    gains += d
                else:
                    losses -= d
            rsi = 100.0 if losses == 0 else round(100 - 100 / (1 + gains / losses), 1)
        out.append({
            "name": x.get("name"),
            "ma20_gap_pct": round((cur / ma(20) - 1) * 100, 2),
            "ma60_gap_pct": round((cur / ma(60) - 1) * 100, 2),
            "off_60d_high_pct": round((cur / hi60 - 1) * 100, 2),
            "rsi14": rsi,
        })
    return out


def flows_liquidity():
    """한국 수급(외인/기관/개인) + 유동성(예탁금·신용잔고) 요약."""
    fl = _load_json(KR_FLOWS)
    dp = _load_json(KR_DEPOSIT)
    out = {}
    if fl:
        out["kospi_flows_조원"] = {
            "as_of": fl.get("as_of"), "당일": fl.get("latest"),
            "MTD": fl.get("mtd"), "YTD_외인누적": None,
        }
        yc = fl.get("ytd_cum") or {}
        try:
            fseq = yc.get("foreign") or []
            if fseq:
                out["kospi_flows_조원"]["YTD_외인누적"] = round(fseq[-1], 1)
        except Exception:
            pass
    if dp:
        cur = dp.get("current") or {}
        out["liquidity_조원"] = {"고객예탁금": cur.get("deposit"), "신용잔고": cur.get("credit"),
                              "as_of": cur.get("as_of")}
        cr = (dp.get("credit") or {})
        vals = cr.get("values") or []
        if len(vals) >= 21:
            try:
                out["liquidity_조원"]["신용잔고_1M변화"] = round(vals[-1] - vals[-21], 1)
            except Exception:
                pass
    return out or None


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
3) 특히 다음 5개 축은 매일 반드시 점검한다: ① 반도체(메모리) 마진·가격 ② 칩플레이션(원가의 전방 전가와 수요 반작용)
   ③ 빅테크 FCF·capex 부담 ④ AI 밸류에이션·유동성 이벤트(IPO 등)
   ⑤ **기술적·수급·유동성**: [technicals]의 이평선 이격·60일 고점 대비 낙폭·RSI, [flows_liquidity]의
   외인/기관/개인 수급과 신용잔고·예탁금 추이, 그리고 뉴스상의 레버리지 ETF·패시브 자금, 국민연금 등
   연기금 리밸런싱, 옵션 만기·프로그램 매매 같은 기계적 수급 이벤트. 이 축이 chain의 technical 판정 근거다.
4) 종합해 오늘의 포지셔닝 결론을 내린다. 막연한 양비론 금지 — 결정 지향. 판단을 바꿀 트리거를 명시.
5) **매매는 ETF 단위로 실행된다.** 이 계정은 개별 섹터 미세조정이 어렵고 실제 매매는 ETF로 이뤄진다.
   positioning.country/sector에는 큰 방향성을 쓰되, trades는 반드시 [etf_universe] 안의 구체 티커로,
   "무엇을 팔아(축소) 무엇을 산다(확대)" 짝이 드러나게 쓴다. 개별 주식은 이미 보유한 종목의
   유지/축소 판단에만 언급(신규 개별주 매수 제안 금지). 유니버스에 적절한 ETF가 없으면 trades 대신
   sector/country 서술에 방향만 남긴다.

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
 "technicals_read": "기술적·수급·유동성 종합 판독 2~4문장 — 이평선/낙폭/RSI·외인기관 수급·신용/예탁금·기계적 수급 이벤트를 근거로",
 "positioning": {
   "macro_view": "1~3문장",
   "equity_weight": {"stance":"확대|유지|축소","text":"순노출 판단 근거 1~2문장"},
   "country": "국가 배분 큰 방향 1~2문장",
   "sector": "섹터 큰 방향 1~2문장",
   "trades": [{"action":"매수|확대|축소|매도|유지|헤지","ticker":"ETF티커([etf_universe] 내)","name":"...","reason":"무엇을 팔아 무엇을 사는지 짝으로"}]
 },
 "conclusion": "종합 결론 문단 — 오늘 무엇을 하고 무엇을 하지 않는지 + 판단을 바꿀 트리거 2~3개"
}
chain 4~8개, factors 2~5개(오늘 뉴스로 확인된 신규/갱신만), trades 0~5개(없으면 빈 배열).
as_of/slot/generated_utc 는 출력하지 말 것(스크립트가 채운다)."""

DEVIL_SYSTEM = """당신은 이 계정 투자위원회의 Devil's Advocate 전담 CIO다. 동료 CIO의 오늘자 초안이 주어진다.
당신의 유일한 임무는 초안의 판단을 **깨뜨리는 것**이다. 동의하지 마라. 다음을 공격하라:
- chain의 technical/fundamental 판정이 틀렸을 가능성(기술적이라 본 것이 실은 펀더멘털 훼손의 초기 신호, 또는 그 반대)
- 포지셔닝의 확증편향: 보유 방향(한국·메모리·AI 과체중)을 정당화하려는 해석은 없는가
- trades의 실행 리스크: 그 ETF가 그 방향성 구현에 맞는가, 타이밍·유동성 문제는
- 초안이 놓친 리스크(수급·유동성·이벤트) — 데이터·뉴스에서 근거를 끌어와라
- 반대 시나리오: 이 판단이 틀렸다면 무엇 때문이며 그 확률은

[규칙] 데이터·뉴스에 근거한 반박만. 수치 창작 금지. 인신공격이 아닌 논리 공격. 트집이 아니라 계정을 지키는 반박.
[출력 JSON] {"challenges":[{"target":"공격 대상(체인 이슈명/비중/특정 trade)","argument":"반박 논리 1~3문장","severity":1,"alt_action":"대안 한 줄"}], "missed_risks":["초안이 아예 놓친 리스크 1~3개"]}
challenges 3~6개, severity 1(경미)~3(치명). JSON 객체만 출력."""

FINAL_SYSTEM_SUFFIX = """

[투자위원회 토론 반영 — 중요]
아래에 당신의 초안([draft])과 Devil's Advocate 동료의 반박([devil])이 주어진다.
반박을 하나씩 심사해 최종 판단을 내려라: 타당하면 chain/positioning/trades를 실제로 수정하고,
기각하면 왜 기각하는지 근거를 남겨라. 최종 출력 스키마에 다음 필드를 추가한다:
 "debate": {
   "rounds": [{"point":"반박 요지(간결)","response":"당신의 심사·응답 1~2문장","outcome":"수용|부분수용|기각"}],
   "changed": "토론으로 실제 바뀐 것 1~2문장(없으면 '초안 유지')"
 }
rounds는 반박 전부를 다뤄라(3~6개). 토론을 요식행위로 만들지 마라 — 타당한 반박은 실제로 포지션을 바꿔야 한다."""


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
        "[technicals 기술적 지표(이평 이격%·60일 고점대비%·RSI14)]\n" + json.dumps(technicals(bench), ensure_ascii=False),
        "[flows_liquidity 한국 수급·유동성(조원)]\n" + json.dumps(flows_liquidity(), ensure_ascii=False),
        "[macro 레짐]\n" + json.dumps(slim_macro(macro), ensure_ascii=False),
        "[daily 한국·미국 (지수·섹터·특징주 movers·events)]\n" + json.dumps(regions_payload, ensure_ascii=False),
        "[fm_seeds 포트폴리오 스탠스(섹터·종목·테마·기존 정성요인 시드)]\n" + json.dumps(slim_fm_seeds(fm), ensure_ascii=False),
        "[etf_universe 실행 가능 ETF (trades는 이 안에서만)]\n" + json.dumps(etf_universe(fm), ensure_ascii=False),
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
    ap.add_argument("--no-debate", action="store_true",
                    help="Devil's Advocate 토론 생략(1콜만 — 비용 절감/디버깅용)")
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

    def call(system, user, tag):
        try:
            return fn(system, user)
        except SystemExit:
            raise
        except Exception as e:
            sys.stderr.write("Claude 호출/파싱 실패(%s): %s\n" % (tag, e))
            return None

    # 1) 초안
    result = call(SYSTEM, payload, "draft")
    if result is None:
        sys.exit(4)
    err = validate(result)
    if err:
        sys.stderr.write("초안 스키마 불량: %s\n" % err)
        sys.exit(4)

    # 2) Devil's Advocate 반박 → 3) 최종 종합 (실패 시 초안으로 graceful degrade)
    if not args.no_debate:
        draft_json = json.dumps(result, ensure_ascii=False)
        devil_user = (payload + "\n\n[draft 동료 CIO의 오늘자 초안 — 이것을 공격하라]\n" + draft_json)
        devil = call(DEVIL_SYSTEM, devil_user, "devil")
        if devil and isinstance(devil.get("challenges"), list) and devil["challenges"]:
            print("  devil's advocate: %d challenges" % len(devil["challenges"]), flush=True)
            final_user = (payload +
                          "\n\n[draft 당신의 초안]\n" + draft_json +
                          "\n\n[devil Devil's Advocate 반박]\n" + json.dumps(devil, ensure_ascii=False))
            final = call(SYSTEM + FINAL_SYSTEM_SUFFIX, final_user, "final")
            if final and not validate(final):
                result = final
            else:
                sys.stderr.write("최종 종합 실패 — 초안 게시(debate 생략)\n")
        else:
            sys.stderr.write("반박 생성 실패 — 초안 게시(debate 생략)\n")

    entry = {
        "as_of": as_of,
        "slot": slot,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headline": result.get("headline") or "",
        "market_pulse": result.get("market_pulse") or "",
        "changes": result.get("changes") or "",
        "chain": result.get("chain") or [],
        "factors": result.get("factors") or [],
        "technicals_read": result.get("technicals_read") or "",
        "positioning": result.get("positioning") or {},
        "debate": result.get("debate") or None,
        "conclusion": result.get("conclusion") or "",
    }

    if args.dry_run:
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return

    publish(entry)
    nd = len((entry.get("debate") or {}).get("rounds") or [])
    print("generated: CIO daily %s (%s) -> fm-cio.js (chain %d · factors %d · debate %d)"
          % (as_of, slot, len(entry["chain"]), len(entry["factors"]), nd))
    gb.gh_output(status="generated", as_of=as_of)


if __name__ == "__main__":
    main()
