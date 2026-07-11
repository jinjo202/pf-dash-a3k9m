/* ============================================================================
 * 배당주 탭 — 유니버스 밖 종목 실시간 조회 Cloudflare Worker
 * ----------------------------------------------------------------------------
 * 정적 사이트(github.io)는 야후를 브라우저에서 직접 못 부른다(CORS). 이 Worker가
 * 서버사이드에서 야후/네이버를 조회해 serve.py의 /div-lookup 과 동일한 JSON을
 * CORS 허용 헤더와 함께 돌려준다. → 프런트는 이 URL만 바라보면 정적 사이트에서도 조회 가능.
 *
 * 배포:
 *   1) https://dash.cloudflare.com → Workers & Pages → Create → Worker
 *   2) 이 파일 내용을 붙여넣고 Deploy → https://<이름>.<서브도메인>.workers.dev 발급
 *   3) 배당주 탭 검색창 옆 "⚙ 조회서버"에 그 URL 붙여넣기(브라우저 localStorage 저장)
 * 무료 플랜: 하루 10만 요청(개인용 충분).
 * ========================================================================== */

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "*",
};
const EU_SUFFIX = /\.(L|PA|DE|MI|SW|MC|AS|BR|VI|ST|HE|OL|LS|SG|F)$/;

export default {
  async fetch(request) {
    if (request.method === "OPTIONS") return new Response(null, { headers: CORS });
    const url = new URL(request.url);
    const q = (url.searchParams.get("q") || "").trim();
    if (!q) return json({ ok: false, error: "빈 검색어" });
    try {
      const symbol = await resolveSymbol(q);
      if (!symbol) return json({ ok: false, error: "종목을 찾지 못했습니다: " + q });
      const data = await lookup(symbol);
      if (!data) return json({ ok: false, error: "시세를 가져오지 못했습니다: " + symbol });
      return json(data);
    } catch (e) {
      return json({ ok: false, error: String((e && e.message) || e).slice(0, 200) });
    }
  },
};

function json(obj) {
  return new Response(JSON.stringify(obj), {
    headers: { "Content-Type": "application/json; charset=utf-8", ...CORS },
  });
}
function num(v) { const n = Number(v); return isFinite(n) ? n : null; }
function rp(v) { const n = num(v); if (n == null) return null; const a = Math.abs(n); return a < 100 ? Math.round(n * 100) / 100 : a < 10000 ? Math.round(n * 10) / 10 : Math.round(n); }

/* ── 심볼 해석: 6자리→KR, 한글→네이버, 그 외→야후 검색 ── */
async function resolveSymbol(q) {
  if (/^\d{6}$/.test(q)) return q + ".KS";
  if (/[가-힣]/.test(q)) {
    try {
      const r = await fetch("https://ac.stock.naver.com/ac?" + new URLSearchParams({ q, target: "stock,index", st: "111" }),
        { headers: { "User-Agent": UA, "Referer": "https://finance.naver.com/" } });
      const d = await r.json();
      for (const it of (d.items || [])) {
        const code = it.code || "", tc = (it.typeCode || "").toUpperCase();
        if (/^\d{6}$/.test(code)) return code + (tc.includes("KOSDAQ") ? ".KQ" : ".KS");
      }
    } catch (e) { /* ignore */ }
  }
  try {
    const r = await fetch("https://query1.finance.yahoo.com/v1/finance/search?" + new URLSearchParams({ q, quotesCount: "6", newsCount: "0" }),
      { headers: { "User-Agent": UA } });
    const d = await r.json();
    const quotes = d.quotes || [];
    for (const want of ["EQUITY", "ETF"]) for (const it of quotes) if (it.quoteType === want && it.symbol) return it.symbol;
    if (quotes[0] && quotes[0].symbol) return quotes[0].symbol;
  } catch (e) { /* ignore */ }
  if (/^[A-Za-z0-9.\-]{1,12}$/.test(q)) return q.toUpperCase();
  return null;
}

/* ── 야후 crumb 인증(quoteSummary용) ── */
async function getCrumb() {
  const c = await fetch("https://fc.yahoo.com/", { headers: { "User-Agent": UA } });
  let cookie = "";
  const sc = c.headers.getSetCookie ? c.headers.getSetCookie() : [c.headers.get("set-cookie")];
  cookie = (sc || []).filter(Boolean).map((s) => s.split(";")[0]).join("; ");
  const cr = await fetch("https://query1.finance.yahoo.com/v1/test/getcrumb", { headers: { "User-Agent": UA, "Cookie": cookie } });
  const crumb = (await cr.text()).trim();
  return { cookie, crumb };
}

/* ── 본 조회 ── */
async function lookup(symbol) {
  const gbp = /\.(L)$/.test(symbol);           // 런던 GBp: 배당금 GBP→pence 보정
  // 병렬: chart(5y), fundamentals, crumb
  const chartUrl = "https://query1.finance.yahoo.com/v8/finance/chart/" + encodeURIComponent(symbol) + "?range=5y&interval=1d&events=div";
  const [chartRes, auth] = await Promise.all([
    fetch(chartUrl, { headers: { "User-Agent": UA } }).then((r) => r.json()).catch(() => null),
    getCrumb().catch(() => ({ cookie: "", crumb: "" })),
  ]);
  const result = chartRes && chartRes.chart && chartRes.chart.result && chartRes.chart.result[0];
  if (!result) return null;
  const meta = result.meta || {};
  const ccy = meta.currency || "";
  const price = num(meta.regularMarketPrice) ?? num(meta.previousClose) ?? num(meta.chartPreviousClose);
  if (price == null) return null;

  // ── 시계열(OHLC/종가) ──
  const ts = result.timestamp || [];
  const quote = (result.indicators && result.indicators.quote && result.indicators.quote[0]) || {};
  const rows = [];
  for (let i = 0; i < ts.length; i++) {
    const o = rp(quote.open && quote.open[i]), h = rp(quote.high && quote.high[i]), l = rp(quote.low && quote.low[i]), c = rp(quote.close && quote.close[i]);
    if ([o, h, l, c].some((x) => x == null)) continue;
    rows.push({ t: ts[i], o, h, l, c });
  }
  const closes = rows.map((r) => r.c);
  const closeTs = rows.map((r) => r.t);

  // ── 배당 이벤트 ──
  const divs = [];
  const dobj = (result.events && result.events.dividends) || {};
  for (const k in dobj) { const d = dobj[k]; const amt = num(d.amount); if (amt != null) divs.push({ ts: d.date, amt }); }
  divs.sort((a, b) => a.ts - b.ts);

  // ── quoteSummary(PER/PBR/시총/성향/이름/섹터/다음일정) ──
  let sd = {}, ks = {}, pr = {}, cal = {}, prof = {};
  try {
    const mods = "summaryDetail,defaultKeyStatistics,price,calendarEvents,assetProfile";
    const qsUrl = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/" + encodeURIComponent(symbol) + "?modules=" + mods + "&crumb=" + encodeURIComponent(auth.crumb);
    const qs = await fetch(qsUrl, { headers: { "User-Agent": UA, "Cookie": auth.cookie } }).then((r) => r.json()).catch(() => null);
    const R = qs && qs.quoteSummary && qs.quoteSummary.result && qs.quoteSummary.result[0];
    if (R) { sd = R.summaryDetail || {}; ks = R.defaultKeyStatistics || {}; pr = R.price || {}; cal = R.calendarEvents || {}; prof = R.assetProfile || {}; }
  } catch (e) { /* ignore */ }
  const raw = (o, k) => (o && o[k] && (typeof o[k] === "object" ? num(o[k].raw) : num(o[k])));

  // 연배당금(forward/ttm) — GBp 보정
  let drate = raw(sd, "dividendRate"), trate = raw(sd, "trailingAnnualDividendRate");
  if (gbp) { if (drate != null) drate *= 100; if (trate != null) trate *= 100; }

  const now = Date.now() / 1000;
  const todayY = new Date().getUTCFullYear();

  // TTM 배당합 / 주기 / 최근·연도별
  const recent = divs.filter((d) => d.ts >= now - 365 * 86400);
  let dpsTtm = recent.length ? round4(recent.reduce((s, d) => s + d.amt, 0)) : null;
  const n400 = divs.filter((d) => d.ts >= now - 400 * 86400).length;
  const freqN = n400 >= 10 ? 12 : (n400 >= 3 && n400 <= 5) ? 4 : n400 === 2 ? 2 : n400 === 1 ? 1 : null;
  const FREQ = { 12: "월", 4: "분기", 2: "반기", 1: "연" };
  const lastDiv = divs.length ? { date: isoDate(divs[divs.length - 1].ts), amt: round4(divs[divs.length - 1].amt) } : null;
  if (drate == null && dpsTtm != null) drate = dpsTtm;

  // 연도별 배당합 + 그 해 배당수익률(연말 종가)
  const annualDiv = {};
  for (const d of divs) { const y = new Date(d.ts * 1000).getUTCFullYear(); annualDiv[y] = (annualDiv[y] || 0) + d.amt; }
  const yearClose = {};
  for (let i = 0; i < closes.length; i++) { const y = new Date(closeTs[i] * 1000).getUTCFullYear(); yearClose[y] = closes[i]; }
  const hist = [];
  for (const y of [todayY - 3, todayY - 2, todayY - 1]) {
    const dps = annualDiv[y], yc = yearClose[y];
    hist.push({ yr: y, dps: dps ? Math.round(dps * 100) / 100 : null, yld: (dps && yc) ? Math.round((dps / yc) * 10000) / 100 : null });
  }

  // 수익률
  const ret = (days, ytd) => {
    if (closes.length < 2) return null;
    const last = closes[closes.length - 1];
    let base = null;
    if (ytd) { for (let i = 0; i < closes.length; i++) if (new Date(closeTs[i] * 1000).getUTCFullYear() === todayY) { base = closes[i]; break; } }
    else { const target = now - days * 86400; for (let i = closes.length - 1; i >= 0; i--) if (closeTs[i] <= target) { base = closes[i]; break; } }
    return (base && base > 0) ? Math.round((last / base - 1) * 1000) / 10 : null;
  };

  // 3년 평균주가 + 그 대비 배당률
  let avg3y = null, yld3avg = null;
  if (closes.length) { const a3 = closes.slice(-756); const m = a3.reduce((s, v) => s + v, 0) / a3.length; avg3y = rp(m); if (drate != null && m > 0) yld3avg = Math.round((drate / m) * 10000) / 100; }

  // 다음 일정
  const exNext = raw(cal, "exDividendDate") || raw(sd, "exDividendDate");
  const payNext = raw(cal, "dividendDate");

  // 재무(fundamentals-timeseries)
  const fin = await financials(symbol, ccy, sd, pr);

  const per0 = raw(sd, "trailingPE") || raw(ks, "forwardPE");
  const pbr0 = raw(ks, "priceToBook") || raw(sd, "priceToBook");
  const payout0 = raw(sd, "payoutRatio");
  let yldCalc = (drate != null && price > 0) ? Math.round((drate / price) * 10000) / 100 : null;
  if (yldCalc == null) { const dy = raw(sd, "dividendYield"); if (dy != null) yldCalc = Math.round(dy * 10000) / 100; } // 야후 raw=소수 → ×100
  const yldT = (trate != null && price > 0) ? Math.round((trate / price) * 10000) / 100 : (dpsTtm != null && price > 0 ? Math.round((dpsTtm / price) * 10000) / 100 : null);

  const eu = EU_SUFFIX.test(symbol);
  const rg = symbol.endsWith(".KS") || symbol.endsWith(".KQ") ? "KR" : (eu ? "EU" : "US");

  const q = {
    price: Math.round(price * 100) / 100, ccy,
    yld: yldCalc, yldT,
    payout: payout0 != null ? Math.round(payout0 * 1000) / 10 : null,
    per: (per0 != null && per0 > 0 && per0 < 500) ? Math.round(per0 * 10) / 10 : null,
    pbr: (pbr0 != null && pbr0 > 0 && pbr0 < 100) ? Math.round(pbr0 * 100) / 100 : null,
    mcap: raw(sd, "marketCap") || raw(pr, "marketCap") || null,
    r1m: ret(30), r3m: ret(91), rytd: ret(null, true), ret1y: ret(365),
    drate: drate != null ? round4(drate) : null,
    dps_ttm: dpsTtm,
    freq_n: freqN, freq: FREQ[freqN] || null,
    last_div: lastDiv,
    next_exdiv: exNext ? isoDate(exNext) : null,
    next_paydiv: payNext ? isoDate(payNext) : null,
    hist, avg3y, yld3avg,
    ohlc: rows.slice(-250).map((r) => [mmdd(r.t), r.o, r.h, r.l, r.c]),
    yldT_ok: true,
    fin,
  };

  return {
    ok: true, yf: symbol, t: symbol.split(".")[0],
    n: pr.shortName || pr.longName || meta.symbol || symbol,
    nEn: pr.longName || pr.shortName || "",
    sec: prof.sector || prof.industry || "",
    ex: pr.exchangeName || meta.exchangeName || "", rg, q,
  };
}

async function financials(symbol, ccy, sd, pr) {
  try {
    const types = ["annualTotalRevenue", "annualOperatingIncome", "annualNetIncome",
      "quarterlyTotalRevenue", "quarterlyOperatingIncome", "quarterlyNetIncome"];
    const p2 = Math.floor(Date.now() / 1000) + 86400;
    const p1 = p2 - 6 * 365 * 86400;
    const url = "https://query1.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/" + encodeURIComponent(symbol)
      + "?type=" + types.join(",") + "&period1=" + p1 + "&period2=" + p2 + "&merge=false";
    const d = await fetch(url, { headers: { "User-Agent": UA } }).then((r) => r.json()).catch(() => null);
    const res = d && d.timeseries && d.timeseries.result;
    if (!res) return null;
    const byType = {};
    for (const r of res) { const ty = r.meta && r.meta.type && r.meta.type[0]; if (ty && r[ty]) byType[ty] = r[ty]; }
    const pick = (arr) => (arr || []).map((x) => x && x.reportedValue ? num(x.reportedValue.raw) : null);
    const dates = (arr) => (arr || []).map((x) => (x && x.asOfDate) || "");
    function series(rev, op, ni, quarterly) {
      const rv = byType[rev] || [], ov = byType[op] || [], nv = byType[ni] || [];
      // asOfDate 기준 정렬용 맵
      const map = {};
      const add = (arr, idx) => arr.forEach((x) => { if (!x || !x.asOfDate) return; (map[x.asOfDate] = map[x.asOfDate] || [x.asOfDate, null, null, null])[idx] = x.reportedValue ? num(x.reportedValue.raw) : null; });
      add(rv, 1); add(ov, 2); add(nv, 3);
      let list = Object.values(map).sort((a, b) => (a[0] < b[0] ? 1 : -1)); // 최신순
      list = list.slice(0, quarterly ? 4 : 3).map((r) => {
        const dt = new Date(r[0] + "T00:00:00Z");
        const label = quarterly ? (String(dt.getUTCFullYear()).slice(2) + "Q" + (Math.floor(dt.getUTCMonth() / 3) + 1)) : String(dt.getUTCFullYear());
        return [label, r[1], r[2], r[3]];
      });
      return list;
    }
    return {
      ccy: (pr && pr.currency) || ccy || "",
      a: series("annualTotalRevenue", "annualOperatingIncome", "annualNetIncome", false),
      q: series("quarterlyTotalRevenue", "quarterlyOperatingIncome", "quarterlyNetIncome", true),
    };
  } catch (e) { return null; }
}

function round4(v) { return Math.round(v * 10000) / 10000; }
function isoDate(epoch) { try { return new Date(epoch * 1000).toISOString().slice(0, 10); } catch (e) { return null; } }
function mmdd(epoch) { const d = new Date(epoch * 1000); return String(d.getUTCMonth() + 1).padStart(2, "0") + "-" + String(d.getUTCDate()).padStart(2, "0"); }
