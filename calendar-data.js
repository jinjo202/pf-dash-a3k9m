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
    { date:"2026-07-01", type:"macro", region:"KR", importance:3, released:true, verified:false,
      title:"🇰🇷 6월 수출입 (확정)", unit:"% YoY", source:"관세청/산업부",
      consensus:"+9.5%", prior:"+8.3%(5월)", actual:"+10.2%", mom:"+3.1%", yoy:"+10.2%",
      url:"https://www.customs.go.kr/kcs/na/ntt/selectNttList.do?mi=2891&bbsId=1289",
      detail:"6월 통관기준 수출 +10.2% YoY 확정. 반도체가 견인(반도체 수출 +38%대 추정), 일평균 수출도 증가. 대미·대중 동반 개선.",
      interp:"반도체 슈퍼사이클 지속 확인. 단, 반도체 편중도 심화 → 반도체 단가(특히 DRAM) 모멘텀이 하반기 수출 방향성의 핵심 변수. 하단 ‘한국 수출 트래커’ 참조." },

    { date:"2026-07-02", type:"macro", region:"KR", importance:2, released:true, verified:false,
      title:"🇰🇷 6월 소비자물가(CPI)", unit:"% YoY", source:"통계청",
      consensus:"+2.1%", prior:"+2.0%(5월)", actual:"+2.1%", mom:"+0.2%", yoy:"+2.1%",
      detail:"헤드라인 2.1%, 근원물가 2.0%대. 서비스물가 끈적임 지속.",
      interp:"한은 목표(2%) 부근 안착. 금리 인하 경로에 큰 걸림돌은 아니나 원화 약세·수입물가가 리스크." },

    { date:"2026-07-13", type:"export", region:"KR", importance:3, released:false, verified:false,
      title:"🇰🇷 7월 1~10일 수출 (잠정)", unit:"% YoY", source:"관세청",
      consensus:null, prior:"6월 1~10일 +12.4%", actual:null, mom:null, yoy:null,
      url:"https://www.customs.go.kr/kcs/na/ntt/selectNttList.do?mi=2891&bbsId=1289",
      detail:"관세청 월중 잠정치(1~10일 통관). 조업일수 보정 전 원계열 → 일평균 기준 병행 확인 필요.",
      interp:"월초 10일치는 방향성 선행지표. 특히 반도체 일평균 수출과 DRAM 단가 흐름을 이 시점에 1차 점검." },

    { date:"2026-07-21", type:"export", region:"KR", importance:3, released:false, verified:false,
      title:"🇰🇷 7월 1~20일 수출 (잠정)", unit:"% YoY", source:"관세청",
      consensus:null, prior:"6월 1~20일 +9.8%", actual:null, mom:null, yoy:null,
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
    { date:"2026-07-08", type:"earnings", region:"KR", importance:3, ticker:"005930.KS", name:"삼성전자 (2Q 잠정)", session:"bmo", held:false, released:true, verified:false,
      epsEst:null, revEst:"매출 79조(E)", epsAct:null, revAct:"매출 82조 / 영업익 12.5조(잠정)",
      irUrl:"https://www.samsung.com/global/ir/",
      summary:"2Q 잠정 영업이익 12.5조(컨센 상회). HBM·서버 DRAM 출하 증가와 메모리 가격 강세가 견인. 다만 6월 DRAM 현물가 MoM 약세 신호 → 3Q 가격 모멘텀 점검 필요. 확정 실적·부문별 세부는 7/28 컨콜에서." },

    { date:"2026-07-16", type:"earnings", region:"TW", importance:3, ticker:"TSM", name:"TSMC (2Q26)", session:"bmo", held:false, released:true, verified:false,
      epsEst:"NT$15.0", revEst:"NT$9,300억", epsAct:"NT$15.8", revAct:"NT$9,650억",
      irUrl:"https://investor.tsmc.com/english/quarterly-results",
      summary:"매출·EPS 컨센 상회, 총이익률 58%대. AI·HPC 수요로 3nm/5nm 풀가동, 2026 매출 가이던스 상향(달러 기준 mid-30% 성장). CoWoS 증설 지속. AI 반도체 밸류체인 전반 긍정적 리드." },

    { date:"2026-07-15", type:"earnings", region:"EU", importance:3, ticker:"ASML", name:"ASML (2Q26)", session:"bmo", held:false, released:true, verified:false,
      epsEst:"€5.4", revEst:"€8.2B", epsAct:"€5.7", revAct:"€8.5B",
      irUrl:"https://www.asml.com/en/investors",
      summary:"매출 €8.5B, 수주(bookings)가 서프라이즈 핵심. High-NA EUV 채택 확대·중국 매출 정상화. 2026 가이던스 유지~상향. 신규 수주 강도가 2027 메모리/파운더리 캡엑스 선행지표." },

    { date:"2026-07-22", type:"earnings", region:"US", importance:3, ticker:"TSLA", name:"테슬라 (2Q26)", session:"amc", held:false, released:false, verified:false,
      epsEst:"$0.45", revEst:"$24.5B", epsAct:null, revAct:null,
      irUrl:"https://ir.tesla.com/",
      summary:null },

    { date:"2026-07-23", type:"earnings", region:"US", importance:3, ticker:"GOOGL", name:"알파벳 (2Q26)", session:"amc", held:false, released:false, verified:false,
      epsEst:"$2.35", revEst:"$96B", epsAct:null, revAct:null,
      irUrl:"https://abc.xyz/investor/",
      summary:null },

    { date:"2026-07-24", type:"earnings", region:"KR", importance:3, ticker:"000660.KS", name:"SK하이닉스 (2Q26)", session:"bmo", held:false, released:false, verified:false,
      epsEst:null, revEst:"매출 22조(E)", epsAct:null, revAct:null,
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
    { date:"2026-09-11", type:"event", region:"US", category:"index", importance:2, released:false, verified:false, confirmed:true,
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
    note: "관세청은 매월 1일 전월 확정치, 이후 월중 1~10일·1~20일 잠정치를 발표한다. 반도체(특히 DRAM 단가) 모멘텀 추적이 목적 — YoY뿐 아니라 MoM·일평균까지 본다. 수치는 큐레이션/추정 포함(‘검증필요’). 실제 발표치로 교체.",

    // 월중 잠정(1~10일 / 1~20일) 발표 트래킹
    tenday: [
      { period:"2026-06 1~10일", total_yoy:"+12.4%", semi_yoy:"+41.2%", days:"8.0일", note:"반도체 견인 뚜렷" },
      { period:"2026-06 1~20일", total_yoy:"+9.8%",  semi_yoy:"+37.5%", days:"14.5일", note:"일평균도 증가" },
      { period:"2026-06 확정",   total_yoy:"+10.2%", semi_yoy:"+38.1%", days:"21.0일", note:"6월 확정" },
      { period:"2026-07 1~10일", total_yoy:"—",      semi_yoy:"—",      days:"—",     note:"7/13 발표 예정" }
    ],

    // 차트용 시계열 (월별). value=null 은 미발표.
    series: {
      months: ["26.01","26.02","26.03","26.04","26.05","26.06"],
      total_yoy:  [ 10.3,  8.1, 11.5,  9.0,  8.3, 10.2 ],   // 총수출 YoY(%)
      semi_yoy:   [ 42.0, 33.5, 45.1, 36.2, 34.8, 38.1 ],   // 반도체 수출 YoY(%)
      semi_mom:   [ -6.2,  3.1, 12.4, -4.5,  2.0,  5.1 ],   // 반도체 수출 MoM(%)
      dram_mom:   [  4.5,  3.0,  6.5,  2.0, -1.5, -3.8 ],   // DRAM 고정거래가 MoM(%)  ← 이번 이슈
      dram_level: [  108,  111,  118,  120,  118,  114 ]    // DRAM 단가 지수(임의 기준=100)
    },

    // 이번 달 하이라이트(이슈 트래킹)
    highlight: {
      title: "⚠️ DRAM 고정거래가 MoM 하락 전환",
      body: "5월 -1.5% → 6월 -3.8%(MoM)로 2개월 연속 마이너스. 반도체 수출 YoY는 여전히 +38%로 강하나, 가격 모멘텀(MoM)이 먼저 꺾이는 구간. 물량(출하)·HBM 믹스가 단가 약세를 상쇄 중인지, 7월 1~10일·1~20일 잠정에서 반도체 일평균과 함께 재확인 필요.",
      verified: false
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
