// ============================================================
// 롱숏포트 데이터 원본 — 매일 이 파일만 갱신하면 대시보드에 반영됨
// 갱신 절차: DAILY_UPDATE.md 참조
// 구조: books[0] = 전략 A (마켓 뉴트럴, STRATEGY.md)
//       books[1] = 전략 B (디렉셔널 L/S, STRATEGY_DIRECTIONAL.md)
// 가격 기준: 각 시장 최근 종가 / P&L: 현지통화 수익률 (KRW 선물환 헤지 가정)
// 주: asOfPrice는 KR 종가일(7/14) 기준. 미국 레그(TSM·INTC·WMT·TGT·^GSPC)는 직전 7/13 종가 반영(아시아 마감 시점 스냅샷).
// ============================================================
window.PORTFOLIO_DATA = {
  books: [

  // ================= 전략 A: 마켓 뉴트럴 =================
  {
    id: "neutral",
    tabLabel: "전략 A · 마켓 뉴트럴",
    meta: {
      bookName: "롱숏포트 · LS-Alpha",
      strategy: "Market Neutral Long/Short Equity (KR + S&P500 + Asia)",
      aumUsd: 10000000,
      inceptionDate: "2026-07-10",
      asOfPrice: "2026-07-14",
      lastUpdated: "2026-07-14",
      usdkrw: 1487.53,
      phase: "빌드업 Phase 1 — 페어 5개 / Gross 38% (목표 12~20개 / 180~200%)",
      // grossMaxPct/netMaxPct = 정책 상한. 운용 목표 Gross 180~200% / Net 0±5% (경보 ±10%)
      limits: { grossMaxPct: 300, netMaxPct: 50, varLimitPctNav: 1.2, factorZSoft: 0.20, factorZHard: 0.30 }
    },
    ideas: [
      {
        date: "2026-07-14",
        tag: "시장 뷰",
        title: "美 증시 7/14 마감 — 인텔 +4.1% 반등·S&P 사상최고 7,538, 숏 레그 소폭 역풍은 익일 마킹",
        body: "7/14 미국장 종가: Intel +4.1%(107.40)로 반등, Target +0.7%(135.76), TSMC +0.1%(422.01), Walmart +0.5%(115.30), S&P500 사상최고 7,538, VIX 16.9로 진정. 본 대시보드는 미국 레그를 아시아 마감 스냅샷(직전 7/13 종가)으로 마킹하므로 이 반등은 익일 KR 세션 갱신 시 NAV에 반영된다(소급 수정 없음). 인텔 숏(P3)·타깃 숏(P4)에 소폭 역풍이나 페어 구조가 방향 노출을 상쇄 — 넷 0 설계 유효. TSMC 7/16 Q2 실적(D-2)이 P3 롱 레그 촉매로 대기."
      },
      {
        date: "2026-07-14",
        tag: "리스크",
        title: "동일 KR 세션 재점검 — 룰 전부 미발동, NAV 100.46 유지",
        body: "KR 시장 신규 세션 없음(7/14 종가 불변) → NAV 100.46 유지, 가격·NAV 이력 소급 수정 없음. 기계 룰 재점검 클린: 페어 스톱(−8%)·숏 +15% 커버·월중 −3%·일간 −1.5% 전부 미발동. USDKRW 1,487.5로 안정(선물환 헤지 가정, 통화중립). 재무 스냅샷(fundamentals) 갱신 완료 — 삼성전자 fwd PER 4.0·GPM 47.7%, TSMC fwd PER 20.8·GPM 61.9%, 인텔 fwd PER 67.9(실적 부진 반영)."
      },
      {
        date: "2026-07-14",
        tag: "시장 뷰",
        title: "급락장 첫 실현 — 뉴트럴 북 +0.46%, 숏이 롱보다 더 빠지며 방어 입증",
        body: "7/14 KOSPI −8%대 폭락(6,857) 속에서 전략 A는 NAV 100.46(+0.46%)로 플러스 마감. 숏 레그(하이닉스 −12.2%·삼성전자 보통주 −7.7%·인텔 −6.1%)가 롱보다 더 빠지며 5개 페어 전부 스프레드 이익(P1 +4.5%p·P3 +3.2%p 선두). 시장 방향과 무관하게 낙폭 격차를 수확하는 마켓뉴트럴 설계가 급락장에서 검증됨."
      },
      {
        date: "2026-07-14",
        tag: "리스크",
        title: "룰 점검 클린 — 스톱/커버/월중/일간 전부 미발동, 신규 동결 없음",
        body: "기계 룰 일괄 점검: 페어 P&L 최저치도 +0.3%(P5)로 −8% 스톱과 거리 큼. 전 숏 레그 하락(이익)으로 +15% 역행 커버 없음. NAV +0.46%로 일간 −1.5%·월중 −3% 미해당 → 신규 진입 동결 배지 없음. USDKRW 1,489원으로 소폭 진정(전일 1,499). 선물환 헤지 가정 유지, 넷 +0.5%로 0±5% 밴드 내."
      },
      {
        date: "2026-07-14",
        tag: "시장 뷰",
        title: "TSMC 7/16 실적 D-2 — P3 롱 레그 상방 촉매, 이벤트 변동성 대비 비중 유지",
        body: "TSMC는 7/16 Q2 실적 발표 예정, Citi 등은 2026 매출 가이던스 상향 전망 유지(컨센 순익 +49% YoY). 반도체 셀오프에도 P3(TSM L −2.9% / INTC S −6.1%)는 스프레드 +3.2%p로 이미 기여 중. 실적 서프라이즈 시 롱 레그 추가 상방 — 다만 이벤트 갭 리스크로 레그 비중은 현행 유지, 넷 0 사수."
      },
      {
        date: "2026-07-13",
        tag: "시장 뷰",
        title: "TSMC 7/16 실적 = 파운드리 페어(P3)의 촉매 — Citi 목표가 상향, 2026 가이던스 상향 기대",
        body: "반도체 셀오프로 필라델피아 반도체 시총 1조달러 이상 증발했으나, Citi는 TSMC가 7/16 Q2 실적에서 2026 매출 가이던스를 상향할 것으로 전망(AI 선단수요 견조, 시장 컨센 하단 +49% YoY 성장 기대). 반면 Intel은 7/23 실적 예정, 7월 조정에서 -21% 급락하며 AI 캐펙스 회의론의 직격탄. '검증된 실적(TSM) vs 기대 선반영(INTC)'의 갭 축소 논지(P3) 강화 — 다만 7/16 이벤트 전후 변동성 확대에 대비해 레그 비중은 현행 유지."
      },
      {
        date: "2026-07-13",
        tag: "리스크",
        title: "TSMC 실적 갭 리스크는 페어 내에서 상쇄 — 넷 제로 사수",
        body: "반도체 셀오프를 두고 '미드사이클 리셋'(다수 애널리스트 목표가 유지) 해석과 '사이클 종료론'이 공존. 방향 베팅 없이 P3는 페어 구조로 7/16 이벤트 갭을 자체 헤지. USDKRW 1,530원대(외환위기 후 28년 최고) 고공행진 지속 — 선물환 헤지 가정 유지로 KRW 익스포저는 통화중립. 넷 0±5% 밴드 준수, 신규 진입은 이벤트 소화 후 VWAP 분할."
      },
      {
        date: "2026-07-13",
        tag: "시장 뷰",
        title: "외국인 반도체 집중 매도가 P1 스프레드에 우호적 — 크라우딩 언와인드 지속",
        body: "7/8 외국인 4.3조 순매도가 반도체 대형주에 집중되며 하이닉스(숏 레그) 측 수급 압박 지속. 코스피는 7/8 장중 7,246 저점 후 7/10 7,476으로 일부 회복했으나 50DMA(7,965) 하회. 크라우디드 롱 언와인드 국면에서 삼성전자 L / 하이닉스 S(P1) 스프레드 우호적 — 시장 방향 노출 없이 낙폭 격차만 수확."
      },
      {
        date: "2026-07-12",
        tag: "시장 뷰",
        title: "반도체 고점론發 조정 3주차 — 디스퍼전 확대는 뉴트럴 북의 기회",
        body: "코스피 6/22 사상최고(9,114) 후 약 20% 조정. 모건스탠리 '반도체 사이클 마무리' 코멘트와 하이닉스 시총의 삼성전자 역전(=고점 신호 담론)이 크라우디드 롱 언와인드를 촉발. 방향 베팅 없이 종목 간 낙폭 격차(7/10 하이닉스 -10.1% vs 삼성전자 -7.9%)를 수확하는 국면. 페어 #1(삼성전자 L / 하이닉스 S) 논지 유효."
      },
      {
        date: "2026-07-12",
        tag: "신규 진입",
        title: "삼성전자 우선주 괴리 31.9% — 급락장이 벌려 놓은 캐리 기회",
        body: "7/10 종가 기준 우선주 디스카운트 31.9%(우 194,300 / 보통주 285,000). 패닉 국면에서 유동성 낮은 우선주가 더 빠지며 괴리가 밴드 상단 근접. 배당 캐리 + 평균회귀를 노린 구조적 페어 #2 진입 (레그당 5%)."
      },
      {
        date: "2026-07-12",
        tag: "리스크",
        title: "이란-미국 지정학 리스크 — 넷 제로 사수, 월요일 갭 대비",
        body: "이란 보복 공습 뉴스로 사이드카 발동 이력. 오버나이트 갭 리스크가 큰 주간 — 베타 조정 넷 0 유지, 신규 진입은 장 초반 변동성 소화 후 VWAP 분할로만. 숏 다리 +15% 역행 스톱은 갭 상황에서도 기계적 집행."
      }
    ],
    navHistory: [
      { date: "2026-07-10", nav: 100.00 },
      { date: "2026-07-14", nav: 100.46 }
    ],
    risk: {
      grossPct: 37.9,
      netPct: 0.5,
      predictedBeta: 0.02,
      var1d99PctNav: 0.35,
      factors: [
        { name: "Market Beta", z: 0.02 },
        { name: "Size",        z: -0.05 },
        { name: "Value",       z: 0.12 },
        { name: "Momentum",    z: -0.15 },
        { name: "Quality",     z: 0.05 },
        { name: "Volatility",  z: -0.08 },
        { name: "Growth",      z: -0.10 }
      ],
      countryNets: [
        { name: "한국", netPct: 0.3 },
        { name: "미국", netPct: 0.0 },
        { name: "기타 아시아(대만)", netPct: 0.2 }
      ]
    },
    pairs: [
      {
        id: "P1", name: "K-메모리 크라우딩 언와인드", tier: 1, type: "펀더멘털",
        thesis: "하이닉스 시총 역전 이후 크라우디드 롱 언와인드 국면. 밸류에이션 갭 극단 + 외국인 매도 집중은 하이닉스 측. 삼성전자는 역대 최대 실적으로 하방 지지.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "005930.KS", label: "삼성전자",   ccy: "KRW", weightPct: 4.5, entry: 285000,  last: 263000 },
          { side: "SHORT", ticker: "000660.KS", label: "SK하이닉스", ccy: "KRW", weightPct: 4.5, entry: 2180000, last: 1913000 }
        ]
      },
      {
        id: "P2", name: "삼성전자 우선주 괴리", tier: 1, type: "구조적",
        thesis: "우선주 디스카운트 31.9% — 급락장에서 괴리 확대, 역사적 밴드 상단. 배당 캐리 + 평균회귀. 시장 방향과 무상관.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "005935.KS", label: "삼성전자우", ccy: "KRW", weightPct: 5.0, entry: 194300, last: 182200 },
          { side: "SHORT", ticker: "005930.KS", label: "삼성전자",   ccy: "KRW", weightPct: 5.0, entry: 285000, last: 263000 }
        ]
      },
      {
        id: "P3", name: "파운드리 — 검증된 실적 vs 선반영 기대", tier: 1, type: "펀더멘털",
        thesis: "TSMC는 선단공정 실적이 뒷받침되는 반면, 인텔은 파운드리 턴어라운드 기대가 주가에 과도 선반영(연중 랠리 후 7/10 -8.7% 급반락). 기대와 실적의 갭 축소에 베팅.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "TSM",  label: "TSMC (ADR)", ccy: "USD", weightPct: 4.5, entry: 434.11, last: 421.58 },
          { side: "SHORT", ticker: "INTC", label: "Intel",      ccy: "USD", weightPct: 4.5, entry: 109.84, last: 103.12 }
        ]
      },
      {
        id: "P4", name: "US 대형 리테일 실행력 격차", tier: 2, type: "펀더멘털",
        thesis: "월마트의 이커머스·광고 수익화 vs 타깃의 트래픽 점유율 이탈. 어닝 리비전 방향이 상반 — 동일 소비 사이클 내 상대 베팅.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "WMT", label: "Walmart", ccy: "USD", weightPct: 3.0, entry: 113.90, last: 114.78 },
          { side: "SHORT", ticker: "TGT", label: "Target",  ccy: "USD", weightPct: 3.0, entry: 135.14, last: 134.77 }
        ]
      },
      {
        id: "P5", name: "K-2차전지 수주 모멘텀 격차", tier: 2, type: "펀더멘털",
        thesis: "LG에너지솔루션의 북미 캐파·수주잔고 모멘텀 vs 삼성SDI의 믹스 열위. 섹터 방향(전기차 수요)은 중립화하고 상대 실적 격차만 수확.",
        stopPct: -8, status: "OPEN",
        legs: [
          { side: "LONG",  ticker: "373220.KS", label: "LG에너지솔루션", ccy: "KRW", weightPct: 3.0, entry: 326000, last: 322000 },
          { side: "SHORT", ticker: "006400.KS", label: "삼성SDI",        ccy: "KRW", weightPct: 3.0, entry: 434000, last: 427500 }
        ]
      }
    ],
    weeklyAttribution: []
  },

  // ================= 전략 B: 디렉셔널 L/S =================
  {
    id: "directional",
    tabLabel: "전략 B · 디렉셔널 L/S",
    meta: {
      bookName: "롱숏포트 · LS-D",
      strategy: "Directional Long/Short Equity — 레짐 기반 넷 익스포저 (KR + S&P500 + Asia)",
      aumUsd: 10000000,
      inceptionDate: "2026-07-10",
      asOfPrice: "2026-07-14",
      lastUpdated: "2026-07-14",
      usdkrw: 1487.53,
      phase: "레짐: 중립(Neutral) — 넷 +43% / β 0.44 · KOSPI −8%대 급락으로 당일 신규 넷 변경 동결(±3% 룰), 익일 재판정",
      // 넷 밴드: 강세 +50~60(캡 +70) / 중립 +30~45 / 경계 +10~25 / 위기 -10~+10
      limits: { grossMaxPct: 300, netMaxPct: 70, varLimitPctNav: 1.8, factorZSoft: 0.35, factorZHard: 0.50 }
    },
    ideas: [
      {
        date: "2026-07-14",
        tag: "레짐 판정",
        title: "중립(Neutral) 재확인 — KOSPI 50DMA 하회 지속, S&P·VIX 강세, 넷 +43% 유지",
        body: "7/14 신호 재산출: VIX 16.9(<20, 강세), S&P500 7,538 > 50DMA 7,447 > 200DMA 6,974(강세), KOSPI 6,857 < 50DMA 7,971 이나 200DMA 5,548 큰 폭 상회(중립). 합성 판정 '중립' 불변 — 레짐 전환·신규 트리거 없음. 전일 발동된 '지수 일간 ±3%' 넷 변경 동결은 KR 신규 세션 부재로 계속 유효, 익일 재판정. 넷 +43%·β 0.44 유지, G4 오버레이 현행. NAV 98.04 유지(소급 수정 없음)."
      },
      {
        date: "2026-07-14",
        tag: "시장 뷰",
        title: "美 7/14 마감이 익일 마크에 소폭 우호 — S&P 신고가·인텔 반등",
        body: "미국장 7/14: S&P500 사상최고 7,538(+0.4%), Intel +4.1%(107.40) 반등, Walmart +0.5%, VIX 16.9. 넷 롱(+43%)의 미국 레그(TSM·WMT 롱, INTC·TGT 숏, ES 오버레이)는 아시아 마감 스냅샷으로 익일 KR 세션에 마킹 — S&P·ES 상승과 TSM/WMT 롱 강세는 우호적, 인텔 숏 반등은 소폭 역풍으로 부분 상쇄. 방향 넷 축소는 KOSPI 50DMA 회복 확인 후에만, 폭락 후 V반등 추격 매수는 규칙상 금지."
      },
      {
        date: "2026-07-14",
        tag: "레짐 판정",
        title: "중립 유지·당일 넷 동결 — KOSPI −8% 급락에 디렉셔널 −1.96%(−2% 사다리 근소 미달)",
        body: "7/14 신호: VIX 16.8(<20이나 상승), S&P500 7,515 > 50DMA 7,441 > 200DMA 6,969(강세), KOSPI 6,857 < 50DMA 7,971 이나 > 200DMA 5,548(중립 — 200DMA는 여전히 큰 폭 상회). 합성 판정 '중립' 유지. 넷 롱 +43%가 코스피 급락에 직격돼 NAV 98.04(−1.96%) — §4 일간 −2% 사다리에 0.04%p 근소 미달로 강제 인하 없음. §3 '지수 일간 ±3%' 트리거 발동 → 당일 신규 넷 변경 동결, 익일 재판정. G4 오버레이 현 상태 유지."
      },
      {
        date: "2026-07-14",
        tag: "리스크",
        title: "−2% 사다리 임박 — 익일 재확인 시 지수선물로 넷 50% 인하 대기",
        body: "당일 −1.96%는 −2.00% 문턱에 0.04%p 미달. 익일 재판정에서 추가 하락으로 일간 −2% 재확인 또는 KOSPI 200DMA(5,548) 이탈 시, 재량 없이 KOSPI200·ES 선물(G4)로 넷 50% 인하(5거래일 유지). VIX 30 돌파 시 당일 즉시 50% 헤지. 종목 알파(G1~G3)에는 손대지 않고 G4 오버레이만 조절 — 알파 보존 원칙."
      },
      {
        date: "2026-07-14",
        tag: "시장 뷰",
        title: "숏북이 방어 입증 — G3 알파 숏 +0.38%p 기여, 손실은 넷 롱이 주도",
        body: "급락장에서 G3 알파 숏(INTC −6.1%·TGT −0.3%·삼성SDI −1.5%)이 +0.38%p 기여하며 다운사이드 헤지 역할 수행. 그럼에도 넷 롱 +43%(특히 G4 KOSPI 오버레이 −0.83%p·G1 삼성전자 −0.77%p)가 손실을 주도 — 방향성 P&L이 손실 대부분. 넷 축소는 레짐 신호(KOSPI 50DMA) 회복 확인 후에만, 폭락 후 V반등 추격 매수는 규칙상 금지."
      },
      {
        date: "2026-07-13",
        tag: "레짐 판정",
        title: "중립(Neutral) 유지 — KOSPI 50DMA 하회 지속, 신규 램프 없음",
        body: "7/10 종가 기준 신호 불변: VIX 15.0(강세), S&P500 50DMA(7,433)·200DMA(6,965) 상회(강세), KOSPI 7,476으로 50DMA(7,965) 하향 이탈 지속(중립 강등). 합성 판정 '중립' 유지 — 넷 +45%, β 0.46 그대로. 램프 조건(KOSPI 50DMA 회복 + VIX<20 유지)이 아직 미충족이라 G4 오버레이 증액 보류. 다만 KOSPI 200DMA(5,514)는 큰 폭 상회로 장기 상승 추세는 훼손 없음."
      },
      {
        date: "2026-07-13",
        tag: "시장 뷰",
        title: "TSMC 7/16 실적이 넷 롱의 방향타 — 롱북 리더에 상방 촉매",
        body: "TSMC 7/16 실적에서 2026 매출 가이던스 상향 시 반도체 셀오프의 '미드사이클 리셋' 서사가 강화되며 넷 롱(+45%)에 우호적. G1 코어 롱(삼성전자·TSMC·LG엔솔)은 실적 검증된 리더로 상방 참여, G3 알파 숏(Intel 7/23 실적·Target·삼성SDI)은 이벤트 실망 시 다운사이드 헤지. 넷 확대(강세 밴드 +50~60%)는 레짐 신호(KOSPI 50DMA) 회복 확인 후 주 +15%p 램프로만."
      },
      {
        date: "2026-07-13",
        tag: "리스크",
        title: "USDKRW 1,530 · 외국인 EM 이탈 — 하방 트리거 기계 집행 상기",
        body: "원화 28년 최고 약세 + 외국인의 아시아 EM 비중 축소는 코스피 하방 압력. VIX 15의 컴플레이슨시를 경계하되 재량 개입 없이 기계 트리거만 집행: VIX 30 돌파 → 당일 선물로 넷 50% 헤지, 일간 -2% → 익일 넷 50% 인하, 월중 -6% → 넷 0(뉴트럴 전환). 현재 트리거 미발동."
      },
      {
        date: "2026-07-12",
        tag: "레짐 판정",
        title: "중립(Neutral) 확정 — 넷 +45%, β 0.46로 출발",
        body: "실측 신호(7/10): VIX 15.0(강세), S&P500 50/200DMA 상회(강세), 그러나 KOSPI가 3주 -18% 급락으로 50DMA(7,965) 하향 이탈(중립 강등). 합성 판정 '중립' → 넷 밴드 +30~45%의 상단인 +45%로 시딩. KOSPI 50DMA 회복 + VIX<20 유지 시 주당 +15%p 램프로 강세 밴드(+50~60%) 증량."
      },
      {
        date: "2026-07-12",
        tag: "시장 뷰",
        title: "롱북은 '조정에서 살아남을 고β 리더' — 낙폭과대 추격은 금지",
        body: "반도체 고점론 조정 국면에서 롱북은 실적이 검증된 리더(삼성전자·TSMC·LG엔솔)로 한정하고, 숏북(Intel·Target·삼성SDI)은 하락장에서 더 빠지는 구조적 열위 종목으로 다운사이드 헤지를 겸하게 구성. 부족한 넷은 지수선물(KOSPI200+ES 각 10%)로 채워 알파 포지션 훼손 없이 방향 노출만 확보."
      },
      {
        date: "2026-07-12",
        tag: "리스크",
        title: "VIX 15의 안이함을 경계 — 자동 헤지 트리거 상기",
        body: "이란-미국 지정학 리스크에도 VIX 15는 컴플레이슨시 신호일 수 있음. 기계 트리거 상기: VIX 일중 +5pt 또는 30 돌파 → 당일 선물로 넷 50% 헤지. 일간 -2% → 익일 넷 50% 인하. 월중 -6% → 넷 0(뉴트럴 전환). 재량 개입 없음."
      }
    ],
    navHistory: [
      { date: "2026-07-10", nav: 100.00 },
      { date: "2026-07-14", nav: 98.04 }
    ],
    risk: {
      grossPct: 68.3,
      netPct: 43.0,
      predictedBeta: 0.44,
      var1d99PctNav: 1.20,   // 추정 모델: √[(Gross68×0.88bp)² + (β0.44×2.33×1.0%)²] — 알파 0.60 + 방향성 1.03
      factors: [
        { name: "Market Beta", z: 0.44 },
        { name: "Size",        z: 0.10 },
        { name: "Value",       z: -0.10 },
        { name: "Momentum",    z: 0.30 },
        { name: "Quality",     z: 0.25 },
        { name: "Volatility",  z: -0.12 },
        { name: "Growth",      z: 0.28 }
      ],
      countryNets: [
        { name: "한국", netPct: 26.0 },
        { name: "미국", netPct: 8.3 },
        { name: "기타 아시아(대만)", netPct: 8.7 }
      ]
    },
    // 디렉셔널 북은 '페어'가 아니라 포지션 그룹. stopPct: null = 그룹 스톱 없음(개별 규율 적용:
    // 롱 -15% 손절 / 숏 +15% 커버. 오버레이는 레짐 규칙으로만 증감)
    pairs: [
      {
        id: "G1", name: "코어 롱 — 고β 리더", tier: 1, type: "롱북",
        thesis: "구조적 성장 산업의 검증된 1등주 (β 1.1~1.4). 상승 참여 엔진. 어닝 리비전 상향 유지되는 한 보유.",
        stopPct: null, status: "OPEN",
        legs: [
          { side: "LONG", ticker: "005930.KS", label: "삼성전자 (β1.10)",       ccy: "KRW", weightPct: 10.0, entry: 285000, last: 263000 },
          { side: "LONG", ticker: "TSM",       label: "TSMC ADR (β1.15)",      ccy: "USD", weightPct: 9.0,  entry: 434.11, last: 421.58 },
          { side: "LONG", ticker: "373220.KS", label: "LG에너지솔루션 (β1.40)", ccy: "KRW", weightPct: 6.0,  entry: 326000, last: 322000 }
        ]
      },
      {
        id: "G2", name: "밸러스트 롱 — 저β 캐리", tier: 2, type: "롱북",
        thesis: "넷을 유지하면서 포트 β를 목표 밴드(0.4~0.6) 안으로 눌러주는 방어 캐리 (β 0.65~0.95).",
        stopPct: null, status: "OPEN",
        legs: [
          { side: "LONG", ticker: "WMT",       label: "Walmart (β0.65)",    ccy: "USD", weightPct: 7.0, entry: 113.90, last: 114.78 },
          { side: "LONG", ticker: "005935.KS", label: "삼성전자우 (β0.95)", ccy: "KRW", weightPct: 6.0, entry: 194300, last: 182200 }
        ]
      },
      {
        id: "G3", name: "알파 숏 — 구조적 열위", tier: 1, type: "숏북",
        thesis: "기대 선반영·점유율 이탈·믹스 열위 종목 (β 0.9~1.15). 하락장에서 시장보다 더 빠지며 다운사이드 헤지를 겸함.",
        stopPct: null, status: "OPEN",
        legs: [
          { side: "SHORT", ticker: "INTC",      label: "Intel (β1.10)",    ccy: "USD", weightPct: 5.0, entry: 109.84, last: 103.12 },
          { side: "SHORT", ticker: "TGT",       label: "Target (β0.90)",   ccy: "USD", weightPct: 4.0, entry: 135.14, last: 134.77 },
          { side: "SHORT", ticker: "006400.KS", label: "삼성SDI (β1.15)",  ccy: "KRW", weightPct: 4.0, entry: 434000, last: 427500 }
        ]
      },
      {
        id: "G4", name: "지수 오버레이 — 레짐 스케일링 전용", tier: 1, type: "오버레이",
        thesis: "중립 레짐 넷 목표(+45%)와 종목 넷(+25%)의 갭을 선물로 충당. 레짐 전환·손실 사다리 발동 시 이 그룹만 증감 — 종목 알파에 손대지 않는다.",
        stopPct: null, status: "OPEN",
        legs: [
          { side: "LONG", ticker: "^KS11", label: "KOSPI200 선물 (지수 프록시)", ccy: "KRW", weightPct: 10.0, entry: 7475.9, last: 6856.83 },
          { side: "LONG", ticker: "^GSPC", label: "S&P500 E-mini (지수 프록시)", ccy: "USD", weightPct: 10.0, entry: 7575.4, last: 7515.34 }
        ]
      }
    ],
    weeklyAttribution: []
  }

  ]
};
