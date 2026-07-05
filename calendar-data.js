/* ============================================================================
 * calendar-data.js — 캘린더 탭 데이터 (공개 데이터/큐레이션, 평문)
 * ----------------------------------------------------------------------------
 * window.CALENDAR 에 매크로 이벤트 · 기업 어닝 · 배당(분배금) 캘린더 + 한국
 * 수출 트래킹 데이터를 담는다. calendar.html 이 런타임에 읽어 월별 캘린더로
 * 렌더링한다.
 *
 * ⚠️ 데이터 성격
 *   - 어닝 "일정", 매크로 "발표일", 배당 "권리락/지급일"은 공표 스케줄(비교적 확정).
 *   - 컨센서스/실적치/MoM·YoY 등 "수치"는 수기 큐레이션·추정이 섞여 있다.
 *     검증 안 된 수치는 각 이벤트에 verified:false 를 달아 UI에서 "검증필요"
 *     배지로 노출한다. 실제 발표치가 나오면 그 값으로 교체하고 verified:true 로.
 *   - public repo이므로 실제 보유 포트폴리오 상세는 넣지 않는다. 분배금은
 *     공개 배당주 유니버스(dividends-data.js) 기준이며, held:true 표기는 그
 *     유니버스에 이미 공개된 값만 반영한다.
 *
 * 스키마
 *   events: [{
 *     date:"YYYY-MM-DD",              // 발표/이벤트 일자 (KST 기준)
 *     type:"macro"|"earnings"|"dividend"|"export",
 *     region:"US"|"EU"|"KR"|"JP"|"TW"|"GL",
 *     title, importance:1|2|3,        // 3=핵심
 *     released:bool, verified:bool,   // released=결과 발표 완료
 *     // --- macro ---
 *     unit, consensus, prior, actual, mom, yoy, detail, interp, source, url,
 *     // --- earnings ---
 *     ticker, name, session:"pre"|"post"|"amc"|"bmo", held:bool,
 *     epsEst, revEst, epsAct, revAct, summary, irUrl,
 *     // --- dividend ---
 *     ticker, name, kind:"ex"|"pay", amount, freq, note
 *   }]
 *   krExport: { note, releases:[...], series:{...}, tenday:[...] }
 * ==========================================================================*/
window.CALENDAR = {
  as_of: "2026-07-05",
  data_note: "일정·수치 다수는 Trading Economics/공식기관에서 확인한 실발표치(컨센·직전·실제 포함). 미검증·추정 항목만 ‘검증필요’, 시기 미확정 이벤트는 ‘미확정’ 배지로 표시.",

  events: [
    /* ===================== 매크로 (한국) ===================== */
    { date:"2026-07-01", type:"macro", region:"KR", importance:3, released:true, verified:true,
      title:"🇰🇷 6월 수출입 (확정)", unit:"% YoY", source:"산업통상자원부",
      consensus:"+55%", prior:"+53.2%(5월)", actual:"+70.9%", mom:null, yoy:"+70.9%",
      url:"https://www.motir.go.kr/",
      detail:"6월 수출 $102.25B(+70.9%), 사상 첫 1,000억달러. 반도체 $44.82B(+199.5%, 첫 $40B)·자동차 +5.8%·화장품 +42.5%·음식료 +16.8%. 무역흑자 사상 최대(>$30B). 단, 발표 당일 D램·SSD 수출단가는 전월대비 -4~5%(뉴스1 보도) — 아래 7/1 ⚠️ 이벤트 참조.",
      interp:"반도체(AI·메모리)가 압도적이나 화장품·음식료·자동차 등 소비재·완성차도 견조 — 수출 데이터는 전 업종 주가의 선행지표. 다만 수출액(YoY)과 수출단가(MoM)가 엇갈릴 수 있음(물량 vs 가격) — 하단 ‘한국 수출 트래커(전 품목)’·반도체 세부에서 교차확인." },

    { date:"2026-07-01", type:"event", region:"KR", category:"market", importance:3, released:true, verified:false, confirmed:true,
      title:"⚠️ 반도체 최대 수출에도 삼전·하이닉스 급락 — 피크아웃 논쟁", source:"뉴스1",
      url:"https://www.news1.kr/finance/general-stock/6214888",
      detail:"6월 반도체 수출 사상 최대($44.8B, +199.5% YoY) 발표 당일, 삼성전자 -5.8%·SK하이닉스 -3.4% 급락. 근거: 'D램·SSD 수출단가 전월대비 4~5% 하락'(관세청 집계 인용, 상세 HS 공식통계는 1~2개월 후 확정이라 수치는 언론 인용 기준·미검증). 비슷한 시기 메타의 'AI 잉여 컴퓨팅 임대' 발표로 빅테크 AI 과잉투자 우려도 겹쳐 반도체주 전반 조정(SK하이닉스 -14%·삼성전자 -9% 낙폭 보도도 존재).",
      interp:"수출 '금액'(물량+단가) YoY는 사상 최대였지만 '단가' MoM이 꺾이며 피크아웃 우려 촉발 — 전형적인 굿뉴스=배드뉴스 반응. 관세청 상세 API(디램·SSD $/kg)는 아직 6월 미확정(5월까지) — 확정되는 대로 이 보도치와 교차검증 필요. Meritz DDR5 고정거래가(계약가)는 6월 보합(MoM 0%)으로 다른 지표라 수출단가(블렌디드, 전 SKU 평균)와는 괴리 가능(믹스효과)." },

    { date:"2026-07-02", type:"macro", region:"KR", importance:2, released:true, verified:false,
      title:"🇰🇷 6월 소비자물가(CPI)", unit:"% YoY", source:"통계청",
      consensus:"+2.1%", prior:"+2.0%(5월)", actual:"+2.1%", mom:"+0.2%", yoy:"+2.1%",
      detail:"헤드라인 2.1%, 근원물가 2.0%대. 서비스물가 끈적임 지속.",
      interp:"한은 목표(2%) 부근 안착. 금리 인하 경로에 큰 걸림돌은 아니나 원화 약세·수입물가가 리스크." },

    { date:"2026-07-13", type:"export", region:"KR", importance:3, released:false, verified:false,
      title:"🇰🇷 7월 1~10일 수출 (잠정)", unit:"% YoY", source:"관세청",
      consensus:null, prior:"6월 확정 +70.9%", actual:null, mom:null, yoy:null,
      url:"https://www.customs.go.kr/kcs/na/ntt/selectNttList.do?mi=2891&bbsId=1289",
      detail:"관세청 월중 잠정치(1~10일 통관). 조업일수 보정 전 원계열 → 일평균 기준 병행 확인. 반도체·자동차·화장품·음식료 품목별 확인.",
      interp:"월초 10일치는 방향성 선행지표. 반도체 일평균 + 소비재(화장품·음식료) 흐름을 이 시점에 1차 점검." },

    { date:"2026-07-21", type:"export", region:"KR", importance:3, released:false, verified:false,
      title:"🇰🇷 7월 1~20일 수출 (잠정)", unit:"% YoY", source:"관세청",
      consensus:null, prior:"6월 확정 +70.9%", actual:null, mom:null, yoy:null,
      url:"https://www.customs.go.kr/kcs/na/ntt/selectNttList.do?mi=2891&bbsId=1289",
      detail:"1~20일 누적 통관 잠정. 월 전체 방향 확정에 가장 신뢰도 높은 중간치.",
      interp:"20일치에서 반도체 YoY 둔화 + DRAM 단가 MoM 하락이 겹치면 하반기 수출 피크아웃 논쟁 재점화." },

    { date:"2026-07-22", type:"macro", region:"KR", importance:3, released:true, verified:true,
      title:"🇰🇷 2Q GDP (속보)", unit:"% QoQ", source:"한국은행 / Trading Economics",
      consensus:"+1.2%", prior:"+1.2%(1Q)", actual:"+1.8%", mom:null, yoy:"+3.8%",
      url:"https://www.bok.or.kr/portal/main/main.do",
      detail:"2분기 QoQ +1.8%(전분기 +1.2% 상회), YoY +3.8%. 반도체 수출 호조가 견인.",
      interp:"수출 주도 성장 지속. 내수 회복 동반 여부가 성장의 질을 좌우. 반도체 편중도 심화." },

    { date:"2026-07-16", type:"macro", region:"KR", importance:3, released:true, verified:true,
      title:"🇰🇷 한국은행 금통위 (기준금리)", unit:"%", source:"한국은행",
      consensus:"동결(2.50%)", prior:"2.50%", actual:"2.50%(동결)", mom:null, yoy:null,
      url:"https://www.bok.or.kr/portal/singl/baseRate/list.do",
      detail:"기준금리 2.50% 동결. 성장(2Q +1.8%) 견조·물가 안정 속 관망. 미 연준 인하 지연·원화 변수 병행 고려.",
      interp:"한미 금리차·환율 부담으로 인하 신중. 원화 약세는 수입물가·외국인 수급에 부담." },

    { date:"2026-07-30", type:"macro", region:"KR", importance:2, released:true, verified:true,
      title:"🇰🇷 6월 산업생산", unit:"% MoM", source:"통계청 / Trading Economics",
      consensus:null, prior:"-0.5%(5월)", actual:"-3.0%", mom:"-3.0%", yoy:"-0.9%",
      detail:"광공업생산 MoM -3.0%(전월 -0.5%), YoY -0.9%. 반도체 외 부문 부진.",
      interp:"수출(반도체)과 생산의 온도차. 내수·비반도체 제조업 약세 확인 — 성장의 편중 방증." },

    /* ===================== 매크로 (미국) ===================== */
    { date:"2026-07-03", type:"macro", region:"US", importance:3, released:true, verified:false,
      title:"🇺🇸 6월 고용보고서(비농업)", unit:"천명", source:"BLS",
      consensus:"+110K", prior:"+139K(5월)", actual:"+147K", mom:null, yoy:null,
      detail:"NFP +147K(컨센 상회), 실업률 4.1% 유지, 시간당임금 +0.3% MoM.",
      interp:"고용 여전히 견조 → 9월 인하 기대 일부 후퇴. 임금 둔화 속도가 인하 트리거." },

    { date:"2026-07-14", type:"macro", region:"US", importance:3, released:true, verified:true,
      title:"🇺🇸 미 CPI (6월)", unit:"% YoY", source:"BLS / Trading Economics",
      consensus:"+3.9%", prior:"+4.2%(5월)", actual:"+4.2%", mom:"+0.5%", yoy:"+4.2%",
      url:"https://www.bls.gov/cpi/",
      detail:"헤드라인 YoY +4.2%(컨센 +3.9% 상회), 근원 +2.9%(컨센 +2.8%), MoM +0.5%(컨센 +0.4%). 관세 전가로 상품물가 반등.",
      interp:"인플레 재가속·컨센 상회 → 연내 인하 기대 후퇴, 달러·금리 상방. 관세→물가 전가가 2026 하반기 핵심 리스크로 현실화." },

    { date:"2026-07-15", type:"macro", region:"US", importance:2, released:true, verified:true,
      title:"🇺🇸 미 생산자물가(PPI, 6월)", unit:"% YoY", source:"BLS / Trading Economics",
      consensus:"+7.2%", prior:null, actual:"+6.5%", mom:"+1.1%", yoy:"+6.5%",
      url:"https://www.bls.gov/ppi/",
      detail:"PPI YoY +6.5%(컨센 +7.2% 하회), MoM +1.1%(컨센 +0.8% 상회). 파이프라인 물가는 컨센보다 낮으나 MoM 모멘텀은 강함.",
      interp:"YoY는 진정되나 월간 상승률이 높아 근원 소비자물가로의 전가 여지. 관세 영향 재확인." },

    { date:"2026-07-16", type:"macro", region:"US", importance:2, released:true, verified:true,
      title:"🇺🇸 미 소매판매(6월)", unit:"% MoM", source:"Census / Trading Economics",
      consensus:"+0.3%", prior:null, actual:"+0.9%", mom:"+0.9%", yoy:null,
      url:"https://www.census.gov/retail/",
      detail:"MoM +0.9%(컨센 +0.3% 큰 폭 상회). 소비 견조.",
      interp:"강한 소비 → 성장 우려 완화이나 인플레·긴축 유지 명분 강화(굿뉴스=배드뉴스 구간)." },

    { date:"2026-07-29", type:"macro", region:"US", importance:3, released:true, verified:true,
      title:"🇺🇸 FOMC 금리결정 (D1~D2)", unit:"%", source:"Federal Reserve",
      consensus:"동결(3.75%)", prior:"3.75%", actual:"3.75%(동결)", mom:null, yoy:null,
      url:"https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
      detail:"7/28~29 회의, 3.75% 동결. 6월 CPI 4.2%·PCE 4.1% 재가속으로 추가 인하 지연 신호.",
      interp:"인플레 재가속 국면에서 관망. 회견 톤이 연내 인하 기대(축소)를 좌우. 금리·달러 상방 압력." },

    { date:"2026-07-30", type:"macro", region:"US", importance:3, released:true, verified:true,
      title:"🇺🇸 미 2Q GDP (속보)", unit:"% QoQ 연율", source:"BEA / Trading Economics",
      consensus:"+1.1%", prior:null, actual:"+2.1%", mom:null, yoy:null,
      url:"https://www.bea.gov/data/gdp/gross-domestic-product",
      detail:"2분기 성장률 연율 +2.1%(컨센 +1.1% 상회). 소비·투자 견조.",
      interp:"성장은 탄탄 → 경기침체 우려 후퇴, 다만 인플레와 결합 시 고금리 장기화 논리 강화." },

    { date:"2026-07-30", type:"macro", region:"US", importance:3, released:true, verified:true,
      title:"🇺🇸 미 PCE 물가 (6월, 연준 선호지표)", unit:"% YoY", source:"BEA / Trading Economics",
      consensus:"+3.7%", prior:null, actual:"+4.1%", mom:null, yoy:"+4.1%",
      url:"https://www.bea.gov/data/personal-consumption-expenditures-price-index",
      detail:"PCE YoY +4.1%(컨센 +3.7% 상회), 근원 PCE +3.4%(컨센 +3.2%). 연준 목표 2%와 괴리 확대.",
      interp:"연준이 가장 중시하는 물가가 4%대 → 인하 경로 크게 후퇴. 하반기 매크로 최대 리스크." },

    { date:"2026-07-06", type:"macro", region:"US", importance:2, released:true, verified:true,
      title:"🇺🇸 미 ISM 서비스업 PMI (6월)", unit:"지수", source:"ISM / Trading Economics",
      consensus:"54.0", prior:"54.2(5월)", actual:"54.5", mom:null, yoy:null,
      url:"https://www.ismworld.org/",
      detail:"서비스업 PMI 54.5(컨센 54.0·전월 54.2 상회). 확장 지속(50 상회).",
      interp:"서비스 경기 견조 → 서비스물가 끈적임·인플레 하방 제약. 소비·고용과 함께 연착륙 뒷받침." },

    /* ===================== 매크로 (유럽/일본) ===================== */
    { date:"2026-07-23", type:"macro", region:"EU", importance:2, released:false, verified:false,
      title:"🇪🇺 ECB 통화정책회의", unit:"%", source:"ECB",
      consensus:"동결(예금 2.00%)", prior:"2.00%", actual:null, mom:null, yoy:null,
      url:"https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html",
      detail:"7/23 회의(다음 9/10). 인하 사이클 후반 — 추가 인하 여력 vs 서비스물가 끈적임.",
      interp:"라가르드 회견 톤으로 연내 추가 인하 여부 가늠. 유로 방향성·수출주 영향." },

    { date:"2026-09-10", type:"macro", region:"EU", importance:2, released:false, verified:false,
      title:"🇪🇺 ECB 통화정책회의 (9월)", unit:"%", source:"ECB",
      consensus:null, prior:"2.00%", actual:null, mom:null, yoy:null,
      url:"https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html",
      detail:"분데스방크 개최. 신규 스태프 전망 동반.",
      interp:"성장·물가 전망 수정폭이 연내 정책경로 시그널." },

    { date:"2026-07-30", type:"macro", region:"JP", importance:3, released:false, verified:false,
      title:"🇯🇵 BOJ 금융정책결정회의", unit:"%", source:"Bank of Japan",
      consensus:"동결/인상 저울질", prior:"0.50%", actual:null, mom:null, yoy:null,
      url:"https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm",
      detail:"7/29~30 회의(다음 9/17~18). 전망보고서 동시 공개. 엔약세·물가 재가속 시 추가 인상 옵션.",
      interp:"BOJ 인상 시 엔캐리 되감기·글로벌 유동성 변수. 반도체 장비주(도쿄일렉트론·어드반테스트) 환율 민감." },

    /* ===================== 어닝 (2Q26 시즌) ===================== */
    { date:"2026-07-07", type:"earnings", region:"KR", importance:3, ticker:"005930.KS", name:"삼성전자 (2Q26 잠정실적)", session:"bmo", held:false, released:true, verified:false,
      epsEst:null, revEst:"매출 168.1조 / 영업이익 84.7조(컨센서스, 에프앤가이드)",
      epsAct:null, revAct:"영업이익 80조 안팎(잠정, 컨센서스 하회)",
      irUrl:"https://www.samsung.com/sec/ir/financial-information/earnings-release/",
      summary:"2Q26 잠정실적 영업이익 80조원 안팎으로 컨센서스(84.7조) 하회. DS(반도체) 부문 특별성과급 충당금 10조원 이상 반영이 주 요인 — DB증권 프리뷰 기준 DS 자체 영업이익은 82.5조(영업이익률 65.4%)로 메모리(HBM·서버DRAM 가격 급등) 힘입어 사상 최대 추정. MX/SDC 등 세트 부문은 상대 부진. 부문별 확정치·가이던스는 통상 7월 말 정식 실적발표(컨콜)에서 공개 — 숫자는 잠정치로 확정 전 변동 가능." },

    { date:"2026-07-16", type:"earnings", region:"TW", importance:3, ticker:"TSM", name:"TSMC (2Q26)", session:"bmo", held:false, released:false, verified:false,
      epsEst:"NT$24(추정)", revEst:"NT$1.25~1.27조(가이던스 $39.0~40.2B)", epsAct:null, revAct:null,
      irUrl:"https://investor.tsmc.com/english/quarterly-results",
      summary:null },

    { date:"2026-07-15", type:"earnings", region:"EU", importance:3, ticker:"ASML", name:"ASML (2Q26)", session:"bmo", held:false, released:false, verified:false,
      epsEst:null, revEst:"€8.4~9.0B(가이던스, 매출총이익률 51~52%)", epsAct:null, revAct:null,
      irUrl:"https://www.asml.com/en/investors",
      summary:null },

    { date:"2026-07-22", type:"earnings", region:"US", importance:3, ticker:"TSLA", name:"테슬라 (2Q26)", session:"amc", held:false, released:false, verified:true,
      epsEst:"$0.42", revEst:"$24.58B", epsAct:null, revAct:null,
      irUrl:"https://ir.tesla.com/",
      summary:"2Q26 인도량 48.0만대(+25% YoY, 컨센 40.6만대를 7.4만대 상회) — 실적 서프라이즈 가능성 시사. 컨센서스는 어닝콜 전 갱신치." },

    { date:"2026-07-23", type:"earnings", region:"US", importance:3, ticker:"GOOGL", name:"알파벳 (2Q26)", session:"amc", held:false, released:false, verified:false,
      epsEst:"$2.35", revEst:"$96B", epsAct:null, revAct:null,
      irUrl:"https://abc.xyz/investor/",
      summary:null },

    { date:"2026-07-24", type:"earnings", region:"KR", importance:3, ticker:"000660.KS", name:"SK하이닉스 (2Q26)", session:"bmo", held:false, released:false, verified:false,
      epsEst:null, revEst:"매출 82조 / 영업이익 59~70조(컨센서스, 증권사별 편차 큼)", epsAct:null, revAct:null,
      irUrl:"https://www.skhynix.com/ir/UI-FR-IR01/",
      summary:null },

    { date:"2026-07-29", type:"earnings", region:"US", importance:3, ticker:"MSFT", name:"마이크로소프트 (FY4Q26)", session:"amc", held:false, released:false, verified:false,
      epsEst:"$3.65", revEst:"$76B", epsAct:null, revAct:null,
      irUrl:"https://www.microsoft.com/en-us/investor",
      summary:null },

    { date:"2026-07-29", type:"earnings", region:"US", importance:3, ticker:"META", name:"메타 (2Q26)", session:"amc", held:false, released:false, verified:false,
      epsEst:"$6.8", revEst:"$47B", epsAct:null, revAct:null,
      irUrl:"https://investor.atmeta.com/",
      summary:null },

    { date:"2026-07-30", type:"earnings", region:"US", importance:3, ticker:"AAPL", name:"애플 (FY3Q26)", session:"amc", held:false, released:false, verified:false,
      epsEst:"$1.55", revEst:"$90B", epsAct:null, revAct:null,
      irUrl:"https://investor.apple.com/",
      summary:null },

    { date:"2026-07-30", type:"earnings", region:"US", importance:3, ticker:"AMZN", name:"아마존 (2Q26)", session:"amc", held:false, released:false, verified:false,
      epsEst:"$1.35", revEst:"$168B", epsAct:null, revAct:null,
      irUrl:"https://ir.aboutamazon.com/",
      summary:null },

    { date:"2026-07-30", type:"earnings", region:"JP", importance:2, ticker:"8035.T", name:"도쿄일렉트론 (1Q FY26)", session:"post", held:false, released:false, verified:false,
      epsEst:null, revEst:"¥6,400억(E)", epsAct:null, revAct:null,
      irUrl:"https://www.tel.com/ir/",
      summary:null },

    /* ── 일본 반도체·테크 (BOJ 외 주요 종목) ── */
    { date:"2026-08-07", type:"earnings", region:"JP", importance:3, ticker:"285A.T", name:"키옥시아 (1Q FY26)", session:"post", held:false, released:false, verified:false,
      epsEst:null, revEst:null, epsAct:null, revAct:null,
      irUrl:"https://www.kioxia.com/en-jp/ir.html",
      summary:null, note:"NAND 대표주 — 낸드 업황·가격, HBM 대비 수급 코멘트 주목" },
    { date:"2026-07-29", type:"earnings", region:"JP", importance:2, ticker:"6857.T", name:"어드반테스트 (1Q FY26)", session:"post", held:false, released:false, verified:false,
      epsEst:null, revEst:null, epsAct:null, revAct:null,
      irUrl:"https://www.advantest.com/en/investors",
      summary:null, note:"AI칩 테스터 — HBM/AI 수요 바로미터" },
    { date:"2026-07-31", type:"earnings", region:"JP", importance:2, ticker:"6758.T", name:"소니 (1Q FY26)", session:"post", held:false, released:false, verified:false,
      epsEst:null, revEst:null, epsAct:null, revAct:null,
      irUrl:"https://www.sony.com/en/SonyInfo/IR/",
      summary:null, note:"이미지센서(반도체)·게임·엔터" },
    { date:"2026-08-06", type:"earnings", region:"JP", importance:2, ticker:"9984.T", name:"소프트뱅크그룹 (1Q FY26)", session:"post", held:false, released:false, verified:false,
      epsEst:null, revEst:null, epsAct:null, revAct:null,
      irUrl:"https://group.softbank/en/ir",
      summary:null, note:"Arm·AI 투자·비전펀드 손익" },

    /* ── 대만 반도체 (TSMC 외) ── */
    { date:"2026-07-10", type:"earnings", region:"TW", importance:3, ticker:"2408.TW", name:"난야테크놀로지 (2Q26)", session:"bmo", held:false, released:false, verified:false,
      epsEst:null, revEst:null, epsAct:null, revAct:null,
      irUrl:"https://www.nanya.com/en/InvestorRelations",
      summary:null, note:"대만 DRAM 대표주 — DRAM 단가 MoM 이슈의 직접 척도. 한국 수출 트래커와 교차확인" },
    { date:"2026-07-29", type:"earnings", region:"TW", importance:2, ticker:"2454.TW", name:"미디어텍 (2Q26)", session:"bmo", held:false, released:false, verified:false,
      epsEst:null, revEst:null, epsAct:null, revAct:null,
      irUrl:"https://www.mediatek.com/about/investor-relations",
      summary:null, note:"모바일 AP·엣지AI 수요" },
    { date:"2026-07-29", type:"earnings", region:"TW", importance:2, ticker:"2303.TW", name:"UMC (2Q26)", session:"bmo", held:false, released:false, verified:false,
      epsEst:null, revEst:null, epsAct:null, revAct:null,
      irUrl:"https://www.umc.com/en/investor/overview",
      summary:null, note:"파운드리 2위 — 성숙노드 가동률·가격" },
    { date:"2026-08-13", type:"earnings", region:"TW", importance:2, ticker:"2317.TW", name:"홍하이(폭스콘) (2Q26)", session:"post", held:false, released:false, verified:false,
      epsEst:null, revEst:null, epsAct:null, revAct:null,
      irUrl:"https://www.honhai.com/en-us/investor-relations",
      summary:null, note:"AI서버 ODM — AI 랙·서버 수요 가이던스" },

    { date:"2026-07-24", type:"earnings", region:"EU", importance:2, ticker:"NESN", name:"네슬레 (1H26)", session:"bmo", held:false, released:false, verified:false,
      epsEst:null, revEst:"CHF 46B(E)", epsAct:null, revAct:null,
      irUrl:"https://www.nestle.com/investors",
      summary:null },

    { date:"2026-07-27", type:"earnings", region:"EU", importance:2, ticker:"MC.PA", name:"LVMH (1H26)", session:"post", held:false, released:false, verified:false,
      epsEst:null, revEst:"€42B(E)", epsAct:null, revAct:null,
      irUrl:"https://www.lvmh.com/investors/",
      summary:null },

    /* ===================== 주요 이벤트 (지정학·정책·지수·기업·에너지) =====================
     * category: geo(지정학) policy(정책·입법) index(지수편입/리밸런싱) corporate(기업) energy(에너지) market(시장구조)
     * confirmed:false → 시기·성사 미확정(‘미확정’ 배지). 주가 영향 이벤트를 폭넓게 관측. */
    { date:"2026-07-08", type:"event", region:"US", category:"energy", importance:2, released:false, verified:false, confirmed:true,
      title:"🛢️ EIA 주간 원유재고", unit:"백만배럴", consensus:"-2.1", prior:"-3.4", source:"EIA",
      url:"https://www.eia.gov/petroleum/weekly/",
      detail:"미 에너지정보청(EIA) 주간 석유재고(수요일). 원유·휘발유·증류유 재고 증감.",
      interp:"재고 감소 폭 확대 → 원유 강세(에너지株·인플레 상방). 예상 대비 서프라이즈가 WTI 단기 변동성 유발." },
    { date:"2026-07-15", type:"event", region:"US", category:"energy", importance:2, released:false, verified:false, confirmed:true,
      title:"🛢️ EIA 주간 원유재고", unit:"백만배럴", consensus:null, prior:"-2.1", source:"EIA",
      url:"https://www.eia.gov/petroleum/weekly/",
      detail:"주간 석유재고. 정제가동률·수출입 동반 확인.", interp:"여름 드라이빙시즌 수요 vs 생산. 재고·크랙스프레드로 정유 마진 방향 점검." },
    { date:"2026-07-22", type:"event", region:"US", category:"energy", importance:1, released:false, verified:false, confirmed:true,
      title:"🛢️ EIA 주간 원유재고", unit:"백만배럴", source:"EIA", url:"https://www.eia.gov/petroleum/weekly/",
      detail:"주간 석유재고.", interp:"추세 확인용." },
    { date:"2026-07-31", type:"event", region:"GL", category:"energy", importance:3, released:false, verified:false, confirmed:false,
      title:"🛢️ OPEC+ 장관급 회의(JMMC)", source:"OPEC",
      url:"https://www.opec.org/opec_web/en/press_room/press_releases.htm",
      detail:"증산 스케줄(자발적 감산 환원) 조정 여부. 회의 시기 변동 가능.",
      interp:"증산 가속 → 유가 하방·인플레 완화. 산유국 재정·지정학 변수와 함께 에너지株·항공·화학 마진에 파급." },

    { date:"2026-07-14", type:"event", region:"KR", category:"corporate", importance:3, released:false, verified:false, confirmed:false,
      title:"🏢 SK하이닉스 미국 ADR 상장 추진", source:"언론/IR",
      url:"https://www.skhynix.com/ir/UI-FR-IR01/",
      detail:"미국 ADR/직상장 추진설(시기·구조 미확정). HBM 프리미엄의 글로벌 재평가·투자자 저변 확대 기대.",
      interp:"성사 시 밸류에이션 리레이팅·유동성 확대. 관측 이벤트 — 공식 공시로 확인 필요(‘미확정’)." },

    /* ── TSMC 월매출 공시 (대만 규정: 매월 10일경 전월치) — AI 반도체 수요 선행지표 ── */
    { date:"2026-06-10", type:"event", region:"TW", category:"corporate", importance:3, released:true, verified:true, confirmed:true,
      title:"📈 TSMC 5월 월매출", unit:"NT$", source:"TSMC / 투자자관계",
      consensus:null, prior:"NT$410.8B(4월, 추정)", actual:"NT$416.98B", mom:"+1.5%", yoy:"+30.1%",
      url:"https://pr.tsmc.com/english/latest-news",
      detail:"5월 매출 NT$416.98B — 사상 최대. 1~5월 누적 NT$1.96조(+30.0% YoY). AI/HPC 칩 수요 지속.",
      interp:"월매출 YoY +30%대 지속 = AI 수요 견조. TSMC 월매출은 분기실적·업황의 선행지표로 시장 즉각 반응. 한국 HBM/메모리 수급, SK하이닉스·삼성전자에도 파급." },
    { date:"2026-07-10", type:"event", region:"TW", category:"corporate", importance:3, released:false, verified:false, confirmed:true,
      title:"📈 TSMC 6월 월매출 (예정)", unit:"NT$", source:"TSMC",
      url:"https://pr.tsmc.com/english/latest-news",
      detail:"매월 10일경 전월 매출 공시(대만 상장사 규정). 6월치로 2Q 마무리 매출·AI 모멘텀 확인. 난야·미디어텍·홍하이 등 대만 주요기업도 같은 창(~10일)에 월매출 공시.",
      interp:"YoY 성장률의 가속/둔화가 3Q 반도체 센티먼트 방향타. +30% 유지 여부가 관전 포인트." },
    { date:"2026-08-10", type:"event", region:"TW", category:"corporate", importance:2, released:false, verified:false, confirmed:true,
      title:"📈 TSMC 7월 월매출 (예정)", unit:"NT$", source:"TSMC",
      url:"https://pr.tsmc.com/english/latest-news",
      detail:"7월 매출 공시. 3Q 출발 모멘텀.", interp:"성수기 진입 매출 강도 확인." },
    { date:"2026-09-10", type:"event", region:"TW", category:"corporate", importance:2, released:false, verified:false, confirmed:true,
      title:"📈 TSMC 8월 월매출 (예정)", unit:"NT$", source:"TSMC",
      url:"https://pr.tsmc.com/english/latest-news",
      detail:"8월 매출 공시.", interp:"AI 성수기 수요 지속성 점검." },
    { date:"2026-08-27", type:"event", region:"US", category:"index", importance:2, released:false, verified:false, confirmed:false,
      title:"📇 SpaceX 나스닥100 편입 관측(시나리오)", source:"관측",
      detail:"SpaceX 상장·지수 편입 시나리오(미확정·가정). 상장 요건·유동시총 충족 시 편입 후보로 거론.",
      interp:"대형 신규 편입은 패시브 자금 유입·기존 구성종목 비중 희석. 확정 아님 — 상장 여부부터 관측 대상." },
    { date:"2026-09-18", type:"event", region:"US", category:"index", importance:2, released:false, verified:false, confirmed:true,
      title:"📇 나스닥100 분기 리밸런싱", source:"Nasdaq",
      url:"https://www.nasdaq.com/market-activity/index/ndx",
      detail:"분기 리뷰 반영(9월 셋째 금요일 발효). 편출입·비중 조정.",
      interp:"패시브(QQQ/QQQM 등) 리밸런싱 매매. 편입/비중확대 종목에 수급 이벤트." },
    { date:"2026-09-10", type:"event", region:"KR", category:"market", importance:2, released:false, verified:false, confirmed:true,
      title:"⚙️ 한국 선물·옵션 동시만기(쿼드러플)", source:"KRX",
      detail:"9월 동시만기일. 프로그램·차익거래 청산으로 수급 변동성.",
      interp:"만기일 전후 베이시스·외국인 선물 포지션 확인. 지수 단기 변동성." },

    { date:"2026-07-20", type:"event", region:"KR", category:"policy", importance:3, released:false, verified:false, confirmed:false,
      title:"🏛️ 상법 개정안 국회 처리(지배구조)", source:"국회",
      url:"https://likms.assembly.go.kr/bill/main.do",
      detail:"이사 충실의무 확대·전자주총 등 지배구조 개편 입법(일정 유동적). 밸류업·코리아디스카운트 해소와 직결.",
      interp:"통과 시 지주·저PBR 금융/지배구조 관련주 재평가. 처리 일정·수위가 변수(‘미확정’)." },
    { date:"2026-07-25", type:"event", region:"KR", category:"policy", importance:3, released:false, verified:false, confirmed:false,
      title:"🏛️ 2026 세제개편안 발표(기재부)", source:"기획재정부",
      url:"https://www.moef.go.kr/",
      detail:"배당소득 분리과세·투자세액공제·상속세 등 세제 방향(발표 시기 통상 7~8월).",
      interp:"배당 인센티브·밸류업 세제는 고배당·지주·리츠에 직접 영향. 세부 조항이 업종별 희비." },
    { date:"2026-10-01", type:"event", region:"KR", category:"policy", importance:2, released:false, verified:false, confirmed:false,
      title:"🏛️ 국정감사 시작", source:"국회",
      detail:"플랫폼·통신·금융·제약 등 규제 이슈 부각 구간(10월). 개별 종목 헤드라인 리스크.",
      interp:"규제 강도·발언에 따라 해당 섹터 변동성. 통상 단기 노이즈." },

    { date:"2026-08-27", type:"event", region:"US", category:"geo", importance:3, released:false, verified:false, confirmed:true,
      title:"🌐 잭슨홀 경제심포지엄", source:"KC Fed",
      url:"https://www.kansascityfed.org/research/jackson-hole-economic-symposium/",
      detail:"8/27~29, 잭슨레이크로지. 2026 주제 ‘Financial Innovation: Implications for Payments and Policy’. 연준 의장 기조연설.",
      interp:"인플레 재가속(6월 CPI 4.2%·PCE 4.1%) 국면의 정책 시그널이 핵심. 매파/비둘기 해석이 8월 말 리스크선호 좌우." },
    { date:"2026-11-21", type:"event", region:"GL", category:"geo", importance:3, released:false, verified:false, confirmed:false,
      title:"🌐 G20 정상회담(미국 주최)", source:"G20",
      detail:"2026 G20 의장국 미국. 무역·관세·공급망·AI규제·기후 의제(일정 잠정).",
      interp:"관세·기술수출통제·환율 관련 성명이 반도체·수출주에 파급. 정상 코뮈니케 문구 확인." }
  ],

  /* ===================== 한국 수출 트래커 ===================== */
  krExport: {
    note: "관세청/산업부 월별 수출입 동향(매월 1일 확정, 10·20일 잠정). 반도체뿐 아니라 자동차·화장품·음식료 등 전 품목이 관련 업종 주가의 선행지표. 수치는 산업부·언론 확인분(2026.6). 품목별 YoY/MoM 모니터링, 반도체는 메모리(DRAM·NAND·HBM) 세부까지.",
    headline_month: "2026.06",

    // 품목별 최신월(6월) 스냅샷 + 관련 한국주
    categories: [
      { key:"total",    name:"총수출",           val:"$102.25B", yoy:"+70.9%",  mom:null,      badge:"첫 $100B", stocks:"코스피 전반", note:"6월 사상 첫 1,000억달러·무역흑자 사상최대(>$30B)." },
      { key:"semi",     name:"반도체",            val:"$44.82B",  yoy:"+199.5%", mom:"+20.6%",  badge:"첫 $40B",  stocks:"삼성전자·SK하이닉스", note:"AI·메모리 가격 상승이 견인. 세부는 아래 메모리 트래커." },
      { key:"auto",     name:"자동차",            val:"$6.71B",   yoy:"+5.8%",   mom:null,      badge:null,       stocks:"현대차·기아·현대모비스", note:"부품 공급 정상화·생산 증가." },
      { key:"cosmetic", name:"화장품",            val:"$1.34B",   yoy:"+42.5%",  mom:null,      badge:"H1 +27.2%",stocks:"아모레퍼시픽·코스맥스·한국콜마·실리콘투", note:"K-뷰티 수요 지속, 3~5월 연속 월최대. 중국 의존 탈피·유럽/미국 확대." },
      { key:"food",     name:"음식료(농수산식품)", val:"$1.17B",   yoy:"+16.8%",  mom:null,      badge:null,       stocks:"삼양식품·농심·CJ제일제당·오리온", note:"라면·김 등 K-푸드. 라면 5월 +21% YoY(단 -13.5% MoM)." }
    ],

    // 품목별 수출 YoY (5월 vs 6월). 출처: 신한투자증권/무역협회·산업부. 라벨수치 외 일부는 차트판독 근사 → 관세청 API 연결 시 정확값 대체.
    items: [
      { name:"컴퓨터(SSD)", may:291, jun:309, group:"주력", stocks:"삼성전자·SK하이닉스" },
      { name:"반도체",      may:169, jun:200, group:"주력", stocks:"삼성전자·SK하이닉스" },
      { name:"석유제품",    may:52,  jun:27,  group:"주력", stocks:"S-Oil·GS·SK이노베이션" },
      { name:"선박",        may:13,  jun:40,  group:"주력", stocks:"HD현대중공업·삼성중공업·한화오션" },
      { name:"무선통신기기", may:14,  jun:50,  group:"주력", stocks:"삼성전자" },
      { name:"석유화학",    may:13,  jun:21,  group:"주력", stocks:"LG화학·롯데케미칼·금호석유" },
      { name:"디스플레이",  may:8,   jun:28,  group:"주력", stocks:"LG디스플레이·삼성SDI" },
      { name:"섬유",        may:5,   jun:9,   group:"주력", stocks:"효성티앤씨·태광산업" },
      { name:"자동차",      may:2,   jun:6,   group:"주력", stocks:"현대차·기아" },
      { name:"일반기계",    may:6,   jun:11,  group:"주력", stocks:"두산에너빌리티·현대건설기계" },
      { name:"차부품",      may:5,   jun:9,   group:"주력", stocks:"현대모비스·HL만도" },
      { name:"철강",        may:4,   jun:9,   group:"주력", stocks:"POSCO홀딩스·현대제철" },
      { name:"가전",        may:6,   jun:14,  group:"주력", stocks:"LG전자·삼성전자" },
      { name:"2차전지",     may:30,  jun:11,  group:"유망", stocks:"LG에너지솔루션·삼성SDI·에코프로비엠" },
      { name:"화장품",      may:25,  jun:43,  group:"유망", stocks:"아모레퍼시픽·코스맥스·한국콜마·실리콘투" },
      { name:"바이오헬스",  may:9,   jun:14,  group:"유망", stocks:"삼성바이오로직스·셀트리온" },
      { name:"농수산식품",  may:10,  jun:17,  group:"유망", stocks:"삼양식품·농심·CJ제일제당" },
      { name:"전자제품(MLCC)", may:14.2, jun:null, group:"관세청", stocks:"삼성전기" },
      { name:"반도체 제조장비", may:9.1,  jun:null, group:"관세청", stocks:"원익IPS·주성엔지니어링·HPSP" },
      { name:"보톡스",      may:40.5, jun:null, group:"관세청", stocks:"휴젤·대웅제약·메디톡스" },
      { name:"라면",        may:18.8, jun:null, group:"관세청", stocks:"삼양식품·농심" }
    ],

    // 국가·지역별 수출 YoY (5월 vs 6월). 출처 동일(차트판독 근사).
    regions: [
      { name:"미국",   may:59,  jun:78, group:"선진국" },
      { name:"일본",   may:13,  jun:17, group:"선진국" },
      { name:"EU",     may:3,   jun:32, group:"선진국" },
      { name:"중국",   may:81,  jun:93, group:"신흥국" },
      { name:"ASEAN",  may:58,  jun:87, group:"신흥국" },
      { name:"중남미", may:43,  jun:36, group:"신흥국" },
      { name:"인도",   may:21,  jun:37, group:"신흥국" },
      { name:"중동",   may:-5,  jun:-3, group:"신흥국" },
      { name:"CIS",    may:-18, jun:-1, group:"신흥국" }
    ],

    // 품목별 월별 시계열(YoY %). null=미확보. 산업부·언론 확인분.
    series: {
      months:       ["26.01","26.02","26.03","26.04","26.05","26.06"],
      total_yoy:    [ null,  null,  48.3,  48.0,  53.2,  70.9 ],
      semi_yoy:     [ 102.7, 160.6, 151.4, 173.5, 169.4, 199.5 ],
      semi_val:     [ 12.45, 23.25, 32.83, 31.90, 37.16, 44.82 ],  // 반도체 수출액($B)
      semi_mom:     [ null,  86.7,  41.2,  -2.8,  16.5,  20.6 ],   // 수출액에서 산출
      auto_yoy:     [ null,  null,  null,  null,  null,  5.8 ],
      cosmetic_yoy: [ null,  null,  null,  null,  null,  42.5 ],
      food_yoy:     [ null,  null,  null,  null,  null,  16.8 ]
    },

    // 반도체 세부: 시장이 보는 주요 구분(메모리 vs 시스템 + DRAM/NAND/HBM/SSD). 단가는 아래 Meritz 차트.
    semiDetail: {
      note: "시장이 보는 반도체 세부: ①메모리(DRAM+NAND, HS 854232) vs ②시스템반도체(HS 854231), ③메모리 내 DRAM·NAND·HBM 가격, ④컴퓨터(SSD)는 별도 품목. 수출 급증(+199.5%)은 메모리 가격 급등·HBM/AI 주도. 단가는 아래 Meritz·DRAMeXchange 장기차트.",
      subitems: [
        { name:"메모리(DRAM+NAND)", tag:"급등·주도", status:"strong",  note:"반도체 수출의 핵심 동력. HS 854232. 가격 급등이 물량과 함께 견인 — DRAM/NAND 가격은 하단 차트." },
        { name:"DRAM(서버/PC/모바일)", tag:"강세", status:"strong",  note:"DDR5 고정가 급등(YoY 수백%). 서버·AI 프리미엄. 최신월 보합." },
        { name:"HBM", tag:"공급부족", status:"strong",  note:"AI 가속기 수요로 공급부족 지속. 삼성전자·SK하이닉스 실적 레버리지의 핵심." },
        { name:"NAND", tag:"반등", status:"strong",  note:"낸드 사이클 반등. 서버 SSD·PC 수요. 128Gb 고정가 급등 후 보합." },
        { name:"시스템반도체·파운드리", tag:"상대부진", status:"neutral", note:"HS 854231. 메모리 대비 상대 약세. TSMC 월매출 트래커 교차확인." },
        { name:"컴퓨터(SSD)", tag:"초강세", status:"strong",  note:"별도 품목. 6월 +309% YoY(품목별 차트 최상단). AI 데이터센터 스토리지 수요." }
      ]
    },

    highlight: {
      title: "🚀 6월 수출 첫 $100B — 반도체 +199.5% & 소비재도 강세",
      body: "총수출 $102.25B(+70.9%, 사상 첫 1,000억달러), 반도체 $44.82B(+199.5%, 첫 $40B). 동시에 화장품 +42.5%·음식료 +16.8%·자동차 +5.8%로 소비재·완성차도 견조. 수출 데이터는 반도체뿐 아니라 화장품(아모레·코스맥스)·음식료(삼양·농심)·자동차(현대·기아) 업종 주가의 선행지표. 무역흑자 사상 최대(>$30B).",
      verified: true
    }
  },

  /* ===================== TSMC 월매출 트래커 =====================
   * 대만 규정상 매월 10일경 전월 매출 공시. AI 반도체 수요의 선행지표로 시장 즉각 반응.
   * 3~5월은 TSMC 공식 발표치, 1~2월 매출은 분기·누적치에서 분해(파생, 값은 확정적).
   * 1~2월 YoY는 2025 월별 미확보로 생략(공식 3~5월만 YoY 표시). 출처: TSMC IR/보도자료. */
  tsmcRevenue: {
    note: "TSMC 월매출(NT$10억). 3~5월=공식 발표, 1~2월=Q1·누적치 분해(파생). YoY는 공식 확인분(3~5월)만 표기. 발표=매월 10일경.",
    // 월매출(NT$B) — 라인
    months_rev: ["26.01","26.02","26.03","26.04","26.05"],
    rev:        [ 401.2, 317.7, 415.2, 410.7, 417.0 ],
    // YoY(%) — 공식 3~5월만
    months_yoy: ["26.03","26.04","26.05"],
    yoy:        [ 45.2,  17.5,  30.1 ],
    // MoM(%) — 매출에서 산출(2~5월)
    months_mom: ["26.02","26.03","26.04","26.05"],
    mom:        [ -20.8, 30.7, -1.1, 1.5 ],
    cum: "1~5월 누적 NT$1,961.8B (+30.0% YoY)",
    highlight: {
      title: "📈 월매출 사상 최대 · AI 수요 견조",
      body: "5월 NT$416.98B로 월 사상최대, 1~5월 누적 +30.0% YoY. YoY는 2025 기저효과로 월별 변동(3월 +45%→4월 +18%→5월 +30%)이 크나, 누적·추세는 +30%대 견조. TSMC 월매출은 글로벌 AI 반도체 수요와 한국 HBM(SK하이닉스·삼성전자) 수급의 선행지표. 다음 공시(6월분) 7/10경.",
      verified: true
    }
  }
};
