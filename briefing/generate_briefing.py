# -*- coding: utf-8 -*-
"""
서버사이드(GitHub Actions) 한국어 시황 브리핑 생성기.

로컬 예약 작업(Claude Code)이 하던 브리핑 작성을 Claude API 로 옮긴 것.
PC 가 켜져 있는지와 무관하게 GitHub Actions 에서 매일 실행된다.

흐름:
  1. daily-data.js(window.DAILY) + benchmarks.js(window.BENCHMARKS) 파싱
  2. region(asia|us) 별로 관련 데이터만 추려 프롬프트 구성
  3. Claude API 로 {title, paragraphs, report} JSON 생성
  4. 아카이브 js + briefings/{as_of}.md (+ us: briefing-data.js) 갱신

사용법:
  python generate_briefing.py <asia|us> [--as-of YYYY-MM-DD] [--dry-run] [--skip-if-exists]

환경변수:
  ANTHROPIC_API_KEY   (필수) Claude API 키
  ANTHROPIC_MODEL     (선택) 모델 alias. 기본 claude-opus-4-6

종료코드: 0 성공 / 2 인자·환경 문제 / 3 데이터 문제 / 4 API·파싱 실패
"""
import sys, os, re, json, argparse
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DAILY_JS = os.path.join(REPO, "daily-data.js")
BENCH_JS = os.path.join(REPO, "benchmarks.js")
BRIEFINGS_DIR = os.path.join(REPO, "briefings")
ARCHIVE_ASIA = os.path.join(REPO, "briefings-archive-asia.js")
ARCHIVE_US = os.path.join(REPO, "briefings-archive.js")
BRIEFING_DATA_US = os.path.join(REPO, "briefing-data.js")

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-6")
MAX_KEEP = 120


# ----------------------------------------------------------------------------
# 데이터 로드
# ----------------------------------------------------------------------------
def _parse_assign(path, var_re):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    m = re.search(var_re, text, re.S)
    if not m:
        raise ValueError("assignment not found in " + path)
    return json.loads(m.group(1))


def load_daily():
    return _parse_assign(DAILY_JS, r"window\.DAILY\s*=\s*(\{.*\})\s*;?\s*$")


def load_benchmarks():
    try:
        return _parse_assign(BENCH_JS, r"window\.BENCHMARKS\s*=\s*(\{.*\})\s*;?\s*$")
    except Exception:
        return None


def slim_region(r):
    """프롬프트용으로 region 에서 무거운 spark/history 제거하고 필요한 필드만."""
    def slim_indices(lst):
        out = []
        for x in (lst or []):
            out.append({k: x.get(k) for k in
                        ("ticker", "name", "price", "chg", "chgPct", "ytdPct", "mtdPct")
                        if x.get(k) is not None})
        return out

    def slim_movers(lst):
        out = []
        for x in (lst or []):
            out.append({k: x.get(k) for k in
                        ("name", "ticker", "chgPct", "reason", "detail")
                        if x.get(k) is not None})
        return out

    comm = r.get("commentary") or {}
    slim = {
        "key": r.get("key"),
        "name": r.get("name"),
        "as_of": r.get("as_of"),
        "prev_date": r.get("prev_date"),
        "indices": slim_indices(r.get("indices")),
        "sectors": [{"name": s.get("name"), "chgPct": s.get("chgPct")}
                    for s in (r.get("sectors") or [])],
        "commentary": {
            "movers": slim_movers(comm.get("movers")),
            "events": [{"title": e.get("title"), "source": e.get("source"),
                        "scope": e.get("scope")}
                       for e in (comm.get("events") or [])],
        },
    }
    if r.get("featured"):
        slim["featured"] = r.get("featured")
    return slim


def slim_benchmarks(bench, tickers):
    if not bench:
        return []
    want = set(tickers)
    out = []
    for x in (bench.get("indices") or []):
        if x.get("ticker") in want:
            out.append({k: x.get(k) for k in
                        ("name", "ticker", "current", "daily_pct", "ytd_pct", "decimals")
                        if x.get(k) is not None})
    return out


# ----------------------------------------------------------------------------
# 작성 규칙 (SKILL.md 발췌)
# ----------------------------------------------------------------------------
RULES_ASIA = """당신은 매일 아시아 증시(한국·일본·중국·홍콩) 마감 후 한국어 시황 브리핑을 작성하는 증권사 애널리스트입니다.

[지수 매핑] korea→코스피(KOSPI)·코스닥(KOSDAQ), japan→닛케이225, china→상해종합(SSE)·선전성분(SZSE)·항셍(HSI, 홍콩).
benchmarks 의 KRW=X 는 원/달러 환율.

[paragraphs 작성 — 7~10문단, 차분한 존댓말 서술체]
- 첫 문단은 정확히 "금일 아시아 증시 시황 보고 드립니다.".
- 그 다음 아시아 증시 총평 2~3문장(전일 미국 영향, 한·일·중·홍콩 지수 방향과 강도, 주도 업종).
- 지수 통계 라인은 반드시 "* " 로 시작하고 닛케이·코스피·상해종합·항셍을 기본(데이터에 있는 지수만), 각 전일대비%와 (연초대비 ytdPct) 병기. 예: "* 전일대비(괄호는 연초대비): 닛케이 +2.50%(+35.9), 코스피 +0.15%(+108.9), 상해종합 +0.22%(+2.9), 항셍 △1.56%(0.0)".
- 일본/한국/중국·홍콩 각 한 문단씩(movers·sectors 근거). 종목 등락률 병기 라인은 반드시 "※ " 로 시작.
- 환율 한 문단(KRW=X 있을 때만), 마무리 한 문단(관전포인트).
- "안녕하십니까"/"감사합니다." 는 쓰지 않는다(미국장 브리핑과 다름).

[필수 규칙]
- 모든 수치는 데이터에 있는 실제 값만. 등락률·연초대비·종목 등락·환율을 절대 지어내지 말 것.
- 하락은 △, 상승은 +.
- movers 의 영문 detail/reason 은 한국어로 자연스럽게 풀어 해석(영어 그대로 붙여넣지 말 것).
- 데이터로 검증 불가한 인용·일정·통계(총재 발언, "외국인 N일 연속 순매도", "시총 N조 돌파" 등)는 절대 지어내지 말 것.
- 과장·단정·투자권유 금지.

[title] "{N월 N일} 아시아 증시 시황" (as_of 기준)."""

RULES_US = """당신은 매일 미국장 마감 후 한국어 금융시황 브리핑을 작성하는 증권사 애널리스트입니다.

[미국 휴장 판정] us.as_of 가 europe.as_of 보다 이른 날짜이면 미국 휴장. 휴장이면 europe.as_of 기준으로 유럽 중심(+미국 휴장 안내 한 줄). 평상시면 us.as_of 기준 미국 중심+유럽 보조.
benchmarks ticker: ^VIX, ^TNX(미10년물), CL=F(WTI), KRW=X(원/달러), ^SOX(필라델피아 반도체).

[paragraphs 작성 — 8~12문단, 차분한 존댓말 서술체]
- 첫 문단은 정확히 "안녕하십니까"(마침표 없음). 마지막 문단은 "감사합니다.".
- 둘째 문단 "{M}월 {D}일 국내외 금융시장 동향입니다."(미국 휴장이면 " 미국은 휴장이었습니다." 추가).
- 지수 통계 라인은 반드시 "* " 로 시작(S&P500·나스닥·다우·Euro Stoxx50 등 데이터에 있는 지수), 전일대비%와 (연초대비 ytdPct) 병기.
- 종목 등락률 병기 라인은 반드시 "※ " 로 시작.
- bold+underline 강조 문단은 맨 앞에 "_ "(언더스코어+공백)를 붙임. 헤드라인·주요 마감 수치·이번주 전망 등에 사용하되 한 브리핑에 3~5개 정도만.
- 매크로/정책/이벤트 1~2문단(events·movers 근거), 특징 종목 1~2문단, 채권·유가·환율 한 문단(^TNX/CL=F/KRW=X), 전망 문단.

[필수 규칙]
- 모든 수치는 데이터에 있는 실제 값만. 데이터에 없는 구체 수치(목표주가 등)는 movers detail/reason 에 있을 때만 인용. 절대 지어내지 말 것.
- 하락은 △, 상승은 +. movers 영문은 한국어로 풀어 해석.
- 반도체가 크게 움직였으면 ^SOX 수치 활용.
- 과장·단정·투자권유 금지.

[title] "{N월 N일} 국내외 금융시장 동향" (as_of 기준)."""

RULES_REPORT = """[report 구조 — 워드(.docx) 개조식 보고서용]
paragraphs 와 같은 데이터·사실에 기반하되 개조식(명사형 종결)으로 재구성.
형식: {"headline": "{N월 N일} ...", "sections": [{"head": "...", "points": [{"text": "...", "subs": ["...", ...]}]}]}
- sections 4~6개. 각 head 는 그날 핵심을 명사형으로 끝나는 한 문장(2줄 이하). head 만 읽어도 흐름 이해되게.
- 각 section.points 2~3개를 MECE 하게. 각 point.text 는 명사형 종결+숫자 근거 포함(2줄 이하).
- 부연이 필요한 point 에만 subs(없으면 생략). 보통 종목별 등락률 병기를 subs 로.
- head/points/subs 텍스트에 □/-/·/*/※ 기호를 직접 붙이지 말 것(렌더러가 자동).
- 검증 불가한 인용·수치는 절대 넣지 말 것."""

OUTPUT_SPEC = """[출력 형식 — 매우 중요]
오직 하나의 JSON 객체만 출력한다(설명·마크다운 코드펜스 금지). 키:
  "title":      문자열
  "paragraphs": 문자열 배열(위 규칙의 prefix 컨벤션 "* "/"※ "/"_ " 정확히 준수)
  "report":     {"headline": 문자열, "sections": [...]}
as_of/generated_utc 는 출력하지 말 것(스크립트가 채운다)."""


# ----------------------------------------------------------------------------
# Claude API 호출
# ----------------------------------------------------------------------------
def call_claude(system_prompt, user_payload):
    try:
        from anthropic import Anthropic
    except ImportError:
        sys.stderr.write("anthropic SDK not installed. pip install anthropic\n")
        sys.exit(2)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.stderr.write("env ANTHROPIC_API_KEY missing\n")
        sys.exit(2)
    client = Anthropic()
    msg = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_payload},
            # 어시스턴트 턴을 "{" 로 prefill → JSON 객체만 이어 쓰게 강제.
            {"role": "assistant", "content": "{"},
        ],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content)
    raw = "{" + text
    return _parse_json_loose(raw)


def _parse_json_loose(raw):
    raw = raw.strip()
    # 혹시 코드펜스가 섞여 오면 제거
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    # 첫 { 부터 마지막 } 까지
    s = raw.find("{")
    e = raw.rfind("}")
    if s >= 0 and e > s:
        raw = raw[s:e + 1]
    return json.loads(raw)


# ----------------------------------------------------------------------------
# as_of 결정 + 프롬프트 구성
# ----------------------------------------------------------------------------
def regions_by_key(daily):
    return {r.get("key"): r for r in (daily.get("regions") or [])}


def build_request(region, daily, bench, override_as_of=None):
    rk = regions_by_key(daily)
    if region == "asia":
        korea = rk.get("korea") or {}
        as_of = override_as_of or korea.get("as_of") or daily.get("as_of")
        regions_payload = [slim_region(rk[k]) for k in ("korea", "japan", "china")
                           if k in rk]
        bench_payload = slim_benchmarks(bench, ["KRW=X"])
        rules = RULES_ASIA
    else:
        us = rk.get("us") or {}
        eu = rk.get("europe") or {}
        us_ao = us.get("as_of") or ""
        eu_ao = eu.get("as_of") or ""
        us_closed = bool(us_ao and eu_ao and us_ao < eu_ao)
        as_of = override_as_of or (eu_ao if us_closed else us_ao) or daily.get("as_of")
        regions_payload = [slim_region(rk[k]) for k in ("us", "europe") if k in rk]
        bench_payload = slim_benchmarks(bench, ["^VIX", "^TNX", "CL=F", "KRW=X", "^SOX"])
        rules = RULES_US

    system_prompt = "\n\n".join([rules, RULES_REPORT, OUTPUT_SPEC])
    d = datetime.strptime(as_of, "%Y-%m-%d")
    user_payload = (
        "작성 기준일(as_of): %s (= %d월 %d일)\n\n"
        "[daily-data.js regions]\n%s\n\n"
        "[benchmarks.js indices]\n%s\n\n"
        "위 데이터만 근거로 규칙에 따라 JSON 을 출력하라."
        % (as_of, d.month, d.day,
           json.dumps(regions_payload, ensure_ascii=False),
           json.dumps(bench_payload, ensure_ascii=False))
    )
    return as_of, system_prompt, user_payload


# ----------------------------------------------------------------------------
# 게시 파일 작성
# ----------------------------------------------------------------------------
def load_archive(path, var):
    if not os.path.exists(path):
        return []
    try:
        return _parse_assign(path, var + r"\s*=\s*(\[.*\])\s*;?\s*$")
    except Exception:
        return []


def write_archive(path, var, header, arr):
    body = json.dumps(arr, ensure_ascii=False, indent=2)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header.rstrip() + "\n" + var + " = " + body + ";\n")


def upsert(arr, today):
    as_of = today["as_of"]
    arr = [b for b in arr if b.get("as_of") != as_of]
    arr.insert(0, today)
    arr.sort(key=lambda b: b.get("as_of") or "", reverse=True)
    return arr[:MAX_KEEP]


def publish(region, today):
    os.makedirs(BRIEFINGS_DIR, exist_ok=True)
    md_lines = [today.get("title", ""), ""]
    md_lines += [p for p in (today.get("paragraphs") or [])]
    if region == "asia":
        md_name = today["as_of"] + "-asia.md"
        arr = upsert(load_archive(ARCHIVE_ASIA, r"window\.BRIEFINGS_ASIA"), today)
        write_archive(
            ARCHIVE_ASIA, "window.BRIEFINGS_ASIA",
            "// 아시아장 마감 후 한국어 시황 브리핑 아카이브 (newest first).\n"
            "// briefing/generate_briefing.py 가 매일(15:50 KST) 새 항목을 맨 앞에 추가한다.",
            arr)
    else:
        md_name = today["as_of"] + ".md"
        arr = upsert(load_archive(ARCHIVE_US, r"window\.BRIEFINGS"), today)
        write_archive(
            ARCHIVE_US, "window.BRIEFINGS",
            "// 미국장 마감 후 한국어 시황 브리핑 아카이브 (newest first).\n"
            "// briefing/generate_briefing.py 가 매일 새 항목을 맨 앞에 추가한다.",
            arr)
        with open(BRIEFING_DATA_US, "w", encoding="utf-8") as f:
            f.write("// 미국장 마감 후 한국어 시황 브리핑 (최신본).\n"
                    "window.BRIEFING = " +
                    json.dumps(today, ensure_ascii=False, indent=2) + ";\n")
    with open(os.path.join(BRIEFINGS_DIR, md_name), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")
    return md_name


# ----------------------------------------------------------------------------
def gh_output(**kv):
    """GitHub Actions step output 으로 status/as_of/md 를 노출(있을 때만)."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write("%s=%s\n" % (k, v))
    except Exception:
        pass


def archive_has(region, as_of):
    if region == "asia":
        arr = load_archive(ARCHIVE_ASIA, r"window\.BRIEFINGS_ASIA")
    else:
        arr = load_archive(ARCHIVE_US, r"window\.BRIEFINGS")
    return any(b.get("as_of") == as_of for b in arr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("region", choices=["asia", "us"])
    ap.add_argument("--as-of", dest="as_of", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-if-exists", action="store_true",
                    help="해당 as_of 브리핑이 아카이브에 이미 있으면 생성·발송 생략")
    args = ap.parse_args()

    daily = load_daily()
    bench = load_benchmarks()
    as_of, system_prompt, user_payload = build_request(
        args.region, daily, bench, args.as_of)

    if not as_of:
        sys.stderr.write("could not determine as_of\n")
        sys.exit(3)

    if args.skip_if_exists and archive_has(args.region, as_of):
        print("skip: %s briefing for %s already exists" % (args.region, as_of))
        gh_output(status="skipped", as_of=as_of)
        return

    try:
        result = call_claude(system_prompt, user_payload)
    except Exception as e:
        sys.stderr.write("Claude API/parse failure: %s\n" % e)
        sys.exit(4)

    paragraphs = result.get("paragraphs") or []
    if not paragraphs:
        sys.stderr.write("model returned empty paragraphs\n")
        sys.exit(4)

    today = {
        "as_of": as_of,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": result.get("title") or "",
        "paragraphs": paragraphs,
        "report": result.get("report") or {},
    }

    if args.dry_run:
        print(json.dumps(today, ensure_ascii=False, indent=2))
        return

    md_name = publish(args.region, today)
    print("generated:", args.region, as_of, "->", md_name,
          "(%d paragraphs)" % len(paragraphs))
    gh_output(status="generated", as_of=as_of, md=md_name)


if __name__ == "__main__":
    main()
