// 펀드매니저(FM) 정성 분석 시드 데이터 — 큐레이션 파일(수작업 관리, cron 자동갱신 대상 아님)
// 섹터/지역 유망 ETF, 장기 종목 thesis, 테마 바스켓. 채팅 토론을 통해 점진적으로 다듬어 나감.
// 정량 부분(현재 비중/모델 선호)은 fm.html에서 PORTFOLIO_DATA·COUNTRY_MODEL·MACRO로 라이브 계산.
window.FM_DATA = {
  as_of: "2026-06-14",
  author_note: "월스트리트 80조 자기자본(고유계정) 운용 관점의 종합 리밸런싱 시드. 현재 포트폴리오·국가배분 모델·매크로 레짐을 근거로 작성. 절대수익 우선 + BM(글로벌 주식) 대비 아웃퍼폼.",

  // ── 1) 포지션 사이징: 레짐 종합점수 → 목표 순노출(net exposure) 밴드 ──
  sizing: {
    note: "MACRO.regime.score(-100~+100)와 5축 필러를 매핑. 절대수익 기관이므로 하방 레짐에선 공격적으로 베타를 줄이고 현금/헤지를 확보.",
    bands: [
      { min: 30,  label: "적극 비중확대", net: "105–110%", cls: "pos",  desc: "리스크온 강화. 레버리지/콜 활용 여지. 모멘텀·고베타 우위." },
      { min: 10,  label: "비중확대",     net: "100–105%", cls: "pos",  desc: "완전투자 유지 + 선호국/섹터 틸트. 현금 최소화." },
      { min: -10, label: "중립",         net: "92–100%",  cls: "neu",  desc: "BM 추종 + 소폭 알파 틸트. 약간의 현금 버퍼." },
      { min: -25, label: "비중축소",     net: "80–92%",   cls: "neg",  desc: "베타 하향. 방어섹터·퀄리티로 회피, 현금 8~20%." },
      { min: -101,label: "적극 축소",    net: "65–80%",   cls: "neg",  desc: "현금/단기채/헤지(풋·인버스) 확대. 자본 보존 최우선." }
    ]
  },

  // ── 3) 섹터 뷰: 글로벌 ETF 활용 ──
  // stance: overweight | neutral | underweight  /  conviction 1~5
  sectors: [
    { key: "IT", name: "정보기술", stance: "overweight", conviction: 5,
      thesis: "AI 자본지출 슈퍼사이클(데이터센터·가속기·HBM)이 이익 모멘텀을 견인. 밸류 부담은 있으나 EPS 상향이 이를 상쇄. 반도체>소프트웨어 순.",
      etfs: [
        { ticker: "SMH",  name: "VanEck Semiconductor", note: "AI 가속기·파운드리 핵심. 최선호.", region: "US" },
        { ticker: "SOXX", name: "iShares Semiconductor", note: "반도체 분산 대안.", region: "US" },
        { ticker: "IGV",  name: "iShares Expanded Tech-Software", note: "AI 수혜 SaaS, 변동성 큼.", region: "US" },
        { ticker: "XLK",  name: "Tech Select Sector SPDR", note: "대형 테크 광범위 노출.", region: "US" }
      ],
      kr_note: "한국 IT=반도체(HBM 슈퍼사이클 최선호). 삼성·하이닉스 직접 노출.",
      kr_etfs: [
        { ticker: "091160 KS", name: "KODEX 반도체", note: "국내 반도체 대표.", region: "KR" },
        { ticker: "396500 KS", name: "TIGER Fn반도체TOP10", note: "삼성·하이닉스 집중.", region: "KR" },
        { ticker: "139260 KS", name: "TIGER 200 IT", note: "IT 광범위.", region: "KR" }
      ] },
    { key: "Industrials", name: "산업재", stance: "overweight", conviction: 4,
      thesis: "전력·그리드·데이터센터 인프라, 리쇼어링, 방산 사이클. 'AI 전력수요'의 실물 수혜처. 현재 포트 비중 22%로 이미 높아 종목 질(質) 점검 필요.",
      etfs: [
        { ticker: "PAVE", name: "Global X US Infrastructure", note: "인프라·전력 설비.", region: "US" },
        { ticker: "ITA",  name: "iShares US Aerospace & Defense", note: "지정학 헤지 + 방산 수주.", region: "US" },
        { ticker: "XLI",  name: "Industrial Select Sector SPDR", note: "광범위 산업재.", region: "US" }
      ],
      kr_note: "한국 산업재 최강 테마=방산 수출 + 조선 슈퍼사이클. 글로벌 경쟁력 보유.",
      kr_etfs: [
        { ticker: "449450 KS", name: "PLUS K방산", note: "한화·현대로템 등 방산 수출.", region: "KR" },
        { ticker: "466920 KS", name: "SOL 조선TOP3플러스", note: "조선 슈퍼사이클(HD현대·삼성重).", region: "KR" },
        { ticker: "139230 KS", name: "TIGER 200 중공업", note: "중공업 광범위.", region: "KR" }
      ] },
    { key: "Healthcare", name: "헬스케어", stance: "overweight", conviction: 3,
      thesis: "밸류 매력 + 방어적 성격. 레짐 하강 시 베타 완충재. GLP-1·바이오 혁신 모멘텀.",
      etfs: [
        { ticker: "XLV", name: "Health Care Select Sector SPDR", note: "방어 + 퀄리티.", region: "US" },
        { ticker: "IBB", name: "iShares Biotechnology", note: "고베타 혁신 익스포저.", region: "US" }
      ],
      kr_note: "한국 바이오=삼성바이오·셀트리온 등 CDMO/바이오시밀러.",
      kr_etfs: [
        { ticker: "143860 KS", name: "TIGER 헬스케어", note: "헬스케어 대표.", region: "KR" },
        { ticker: "244580 KS", name: "KODEX 바이오", note: "바이오 집중.", region: "KR" }
      ] },
    { key: "Financials", name: "금융", stance: "neutral", conviction: 3,
      thesis: "가파른 수익률곡선·자본환원 우호적이나 신용 사이클 후반 리스크. 비중 유지.",
      etfs: [ { ticker: "XLF", name: "Financial Select Sector SPDR", note: "은행+보험+자본시장.", region: "US" } ],
      kr_note: "한국 금융=밸류업(저PBR 해소) 핵심 수혜. 주주환원 확대.",
      kr_etfs: [
        { ticker: "091170 KS", name: "KODEX 은행", note: "밸류업 대표 수혜.", region: "KR" },
        { ticker: "102970 KS", name: "KODEX 증권", note: "거래대금·IB 레버리지.", region: "KR" }
      ] },
    { key: "Communication", name: "커뮤니케이션", stance: "overweight", conviction: 4,
      thesis: "구글·메타 등 AI 변현(광고·추론) 직접 수혜 + 현금흐름·밸류 합리적. 비중 확대 여지.",
      etfs: [ { ticker: "XLC", name: "Communication Services SPDR", note: "GOOGL·META 비중 큼.", region: "US" } ],
      kr_note: "한국 직접 대응 ETF는 제한적(미디어·콘텐츠 정도).",
      kr_etfs: [
        { ticker: "228810 KS", name: "TIGER 미디어컨텐츠", note: "콘텐츠·엔터.", region: "KR" }
      ] },
    { key: "Materials", name: "소재", stance: "neutral", conviction: 2,
      thesis: "현재 포트 9.5%로 다소 높음. 금/구리는 실질금리·달러 흐름에 베팅. 광범위 소재는 중립.",
      etfs: [
        { ticker: "GDX", name: "VanEck Gold Miners", note: "실질금리 하락·지정학 헤지.", region: "US" },
        { ticker: "COPX", name: "Global X Copper Miners", note: "전력화·구리 수요.", region: "US" }
      ],
      kr_note: "한국 소재=2차전지 소재(에코프로·포스코퓨처엠 등). 사이클 바닥 논쟁.",
      kr_etfs: [
        { ticker: "305720 KS", name: "KODEX 2차전지산업", note: "배터리 밸류체인.", region: "KR" },
        { ticker: "305540 KS", name: "TIGER 2차전지테마", note: "소재 집중.", region: "KR" },
        { ticker: "132030 KS", name: "KODEX 골드선물(H)", note: "금 노출(원화).", region: "KR" }
      ] },
    { key: "Energy", name: "에너지", stance: "neutral", conviction: 2,
      thesis: "전력수요(데이터센터) → 천연가스·전력 유틸 재평가. 유가는 중립.",
      etfs: [ { ticker: "XLE", name: "Energy Select Sector SPDR", note: "통합 에너지.", region: "US" } ] },
    { key: "Utilities", name: "유틸리티", stance: "overweight", conviction: 3,
      thesis: "AI 전력수요 + 원전 르네상스로 구조적 재평가. 방어+성장 하이브리드. 저비중(4%)서 확대 여지.",
      etfs: [
        { ticker: "XLU", name: "Utilities Select Sector SPDR", note: "전력 유틸 핵심.", region: "US" },
        { ticker: "URA", name: "Global X Uranium", note: "원전·우라늄 사이클.", region: "US" }
      ],
      kr_note: "한국 유틸=원전 르네상스(두산에너빌리티 등) + AI 전력수요.",
      kr_etfs: [
        { ticker: "434730 KS", name: "HANARO 원자력iSelect", note: "원전 밸류체인.", region: "KR" }
      ] },
    { key: "Cons Disc", name: "경기소비재", stance: "neutral", conviction: 2,
      thesis: "소비 양극화. 메가캡(아마존) 외 광범위 노출은 신중.",
      etfs: [ { ticker: "XLY", name: "Cons. Discretionary SPDR", note: "AMZN·TSLA 비중 큼.", region: "US" } ],
      kr_note: "한국 경기소비재 핵심=자동차(현대차·기아, 저평가+주주환원).",
      kr_etfs: [
        { ticker: "091180 KS", name: "KODEX 자동차", note: "현대차·기아 중심.", region: "KR" }
      ] },
    { key: "Cons Staples", name: "필수소비재", stance: "underweight", conviction: 2,
      thesis: "리스크온 레짐(+14)에서 상대 열위. 레짐 악화 시 비중확대 후보로 대기.",
      etfs: [ { ticker: "XLP", name: "Cons. Staples SPDR", note: "방어 대기자산.", region: "US" } ] }
  ],

  // ── 2) 지역/국가 상세 플레이 (모델의 5개국 외 디테일 + 실행 ETF) ──
  // stance: overweight | neutral | underweight
  regions: [
    { key: "KR", name: "한국", group: "DM/EM 경계", stance: "overweight",
      thesis: "12M Fwd PER 6.2배(적정 11배) 극단적 저평가 + 12개월 아웃룩 최상위. 반도체(HBM) 이익 사이클 + 밸류업·외국인 복귀. 모델 최선호.",
      etfs: [ { ticker: "069500 KS", name: "KODEX 200", note: "이미 코어 보유.", region: "KR" },
              { ticker: "EWY", name: "iShares MSCI South Korea", note: "역외 달러 노출 대안.", region: "US" } ] },
    { key: "US", name: "미국", group: "DM", stance: "underweight",
      thesis: "S&P 12M Fwd PER 20.7배로 비싼 편 + 모멘텀·매크로 부담. 다만 이익수정은 견조. 지수 베타는 줄이되 AI·전력 등 구조 테마는 종목으로 보유. 동일가중(RSP)로 집중도 완화 고려.",
      etfs: [ { ticker: "RSP", name: "Invesco S&P 500 Equal Weight", note: "메가캡 집중 완화.", region: "US" },
              { ticker: "QQQ", name: "Invesco QQQ", note: "구조 성장 노출(틸트용).", region: "US" } ] },
    { key: "EM", name: "이머징", group: "EM", stance: "neutral",
      thesis: "달러 약세·매크로 개선이 우호적이나 이익수정(ERR) 부진. 중립 유지하되 인도·대만 등 선별. 모델 중립(-0.10).",
      etfs: [ { ticker: "IEMG", name: "iShares Core MSCI EM", note: "이미 코어 보유.", region: "EM" } ] },
    { key: "EU", name: "유럽", group: "DM", stance: "underweight",
      thesis: "ECB 완화 사이클(+)이 유일한 강점, 모멘텀·이익수정 부진. 모델 축소. 방산·금융 등 선별 종목만.",
      etfs: [ { ticker: "VGK", name: "Vanguard FTSE Europe", note: "광범위(저비중 유지).", region: "EU" },
              { ticker: "EWG", name: "iShares MSCI Germany", note: "재정부양·산업 회복 시.", region: "EU" } ] },
    { key: "JP", name: "일본", group: "DM", stance: "underweight",
      thesis: "BOJ 긴축·엔 정책금리 캐리 부담으로 모델 최하위(-0.41). 이익수정만 강점. 비중 축소, 엔헤지(DXJ) 외엔 신중.",
      etfs: [ { ticker: "DXJ", name: "WisdomTree Japan Hedged Equity", note: "엔 약세 시 헤지형.", region: "JP" } ] },
    { key: "CN", name: "중국", group: "EM", stance: "neutral",
      thesis: "정책 부양·저밸류 vs 구조 디플레·지정학. 트레이딩 관점 소량. 인터넷(KWEB)은 변동성 크나 밸류 매력.",
      etfs: [ { ticker: "MCHI", name: "iShares MSCI China", note: "광범위 중국.", region: "CN" },
              { ticker: "KWEB", name: "KraneShares CSI China Internet", note: "고변동 알파 베팅.", region: "CN" } ] },
    { key: "IN", name: "인도", group: "EM", stance: "overweight",
      thesis: "EM 내 구조적 성장(인구·제조 이전). 밸류는 비싸나 장기 컴파운더. EM 비중 내 틸트.",
      etfs: [ { ticker: "INDA", name: "iShares MSCI India", note: "대형주 중심.", region: "IN" } ] },
    { key: "TW", name: "대만", group: "EM", stance: "overweight",
      thesis: "AI 공급망(TSMC) 직결. EM 내 반도체 베타. 지정학 리스크는 인지.",
      etfs: [ { ticker: "EWT", name: "iShares MSCI Taiwan", note: "TSMC 비중 큼.", region: "TW" } ] }
  ],

  // ── 4-a) 장기 보유 단일 종목 워치리스트 ──
  // conviction 1~5, action: 비중확대|보유|관망|축소
  stocks: [
    { ticker: "NVDA", name: "엔비디아", theme: "AI 가속기", conviction: 5, action: "보유/비중확대",
      thesis: "AI 컴퓨트의 사실상 표준(CUDA 해자). 데이터센터 capex 사이클의 최대 수혜.",
      risks: "고객 자체칩(ASIC) 전환, 밸류 부담, capex 둔화 신호." },
    { ticker: "GOOGL", name: "알파벳", theme: "AI/검색/클라우드", conviction: 5, action: "비중확대",
      thesis: "Gemini·TPU 수직통합 + 검색 현금흐름 + 클라우드 가속. 빅테크 중 밸류 합리적.",
      risks: "검색 광고 잠식 우려(과장), 반독점 규제." },
    { ticker: "MSFT", name: "마이크로소프트", theme: "클라우드/AI", conviction: 4, action: "보유",
      thesis: "Azure + Copilot 수익화. 엔터프라이즈 AI 1순위 채널.",
      risks: "OpenAI 의존·capex 회수 속도." },
    { ticker: "AVGO", name: "브로드컴", theme: "AI 네트워킹/커스텀칩/광", conviction: 5, action: "비중확대",
      thesis: "맞춤형 AI ASIC + 데이터센터 네트워킹·광통신(실리콘 포토닉스)의 핵심. NVDA의 대안 베팅.",
      risks: "고객 집중, M&A 통합 리스크." },
    { ticker: "TSM", name: "TSMC", theme: "파운드리", conviction: 5, action: "보유/비중확대",
      thesis: "선단공정 사실상 독점. 모든 AI칩의 길목.",
      risks: "지정학(대만), capex 강도." },
    { ticker: "ASML", name: "ASML", theme: "반도체 장비/EUV", conviction: 4, action: "보유",
      thesis: "EUV 독점. 선단 투자 사이클의 병목 수혜.",
      risks: "대중 수출규제, 주문 변동성." },
    { ticker: "005930 KS", name: "삼성전자", theme: "메모리/HBM/파운드리", conviction: 4, action: "비중확대",
      thesis: "HBM 추격 + 메모리 업사이클 + 극단적 저평가(코리아 디스카운트). 밸류업 수혜.",
      risks: "HBM 경쟁력 회복 지연, 파운드리 적자." },
    { ticker: "000660 KS", name: "SK하이닉스", theme: "HBM 메모리", conviction: 5, action: "보유",
      thesis: "HBM 선두. AI 메모리 사이클의 한국 핵심 베타.",
      risks: "메모리 사이클 변동, 밸류 단기 과열 구간." },
    { ticker: "207940 KS", name: "삼성바이오로직스", theme: "바이오 CDMO", conviction: 4, action: "비중확대",
      thesis: "글로벌 1위 CDMO 캐파 증설(5·6공장) + 바이오시밀러 확장. 한국 헬스케어 핵심 컴파운더.",
      risks: "환율·증설 회수 속도, 고밸류." },
    { ticker: "329180 KS", name: "HD현대중공업", theme: "조선 슈퍼사이클", conviction: 5, action: "비중확대",
      thesis: "조선 슈퍼사이클(LNG선·친환경선 + 방산함정). 수주잔고 사상최대·선가 상승. 이익 레버리지 큼.",
      risks: "사이클 정점 논쟁, 원자재·인건비." },
    { ticker: "034020 KS", name: "두산에너빌리티", theme: "원전/AI 전력", conviction: 4, action: "비중확대",
      thesis: "AI 전력수요 + 원전 르네상스(SMR·대형원전)의 한국 핵심. 가스터빈·그리드 동반.",
      risks: "프로젝트 인식 시점, 정책 의존." },
    { ticker: "005380 KS", name: "현대차", theme: "자동차/밸류업", conviction: 3, action: "보유",
      thesis: "저평가(PER 한 자리)+주주환원 확대(밸류업)+하이브리드 믹스. 방어적 캐리.",
      risks: "관세·수요 둔화, 전기차 전환 비용." },
    { ticker: "247540 KS", name: "에코프로비엠", theme: "2차전지 소재", conviction: 3, action: "관망",
      thesis: "양극재 1위. 전기차 수요 회복 시 이익 레버리지. 사이클 바닥 통과 여부가 관건.",
      risks: "전기차 둔화·메탈 가격, 고객 집중." },
    { ticker: "105560 KS", name: "KB금융", theme: "금융/밸류업", conviction: 3, action: "보유",
      thesis: "밸류업(저PBR 해소)·자사주 소각·배당 확대의 대표 수혜. 안정적 ROE.",
      risks: "신용비용·부동산 PF, 금리 하락 시 NIM." }
  ],

  // ── 4-b) 테마/산업 바스켓 ──
  // stage: 초기|성장|성숙  /  plays: stock|etf
  themes: [
    { key: "ai_compute", name: "AI 컴퓨트 (GPU·CPU·ASIC)", stage: "성장", conviction: 5,
      thesis: "추론(inference) 수요 확대로 가속기·서버 CPU 동반 성장. NVDA 외 커스텀 ASIC(AVGO)·CPU(AMD) 동반.",
      plays: [ {type:"stock",ticker:"NVDA"}, {type:"stock",ticker:"AVGO"}, {type:"stock",ticker:"AMD"}, {type:"etf",ticker:"SMH"} ] },
    { key: "optical", name: "광통신 / 실리콘 포토닉스", stage: "초기", conviction: 4,
      thesis: "데이터센터 내 800G·1.6T 광 인터커넥트 폭증. 전력효율 위해 co-packaged optics로 전환. 순수 ETF 부재 → 종목 바스켓으로.",
      plays: [ {type:"stock",ticker:"AVGO"}, {type:"stock",ticker:"COHR",name:"Coherent"}, {type:"stock",ticker:"LITE",name:"Lumentum"}, {type:"stock",ticker:"GLW",name:"Corning"} ] },
    { key: "power_grid", name: "AI 전력 / 그리드 / 원전", stage: "성장", conviction: 4,
      thesis: "데이터센터 전력수요가 구조적 그리드 투자·원전 재가동을 견인. 유틸+장비+우라늄 복합 플레이. 한국은 두산에너빌리티(원전·가스터빈).",
      plays: [ {type:"stock",ticker:"GEV",name:"GE Vernova"}, {type:"stock",ticker:"VST",name:"Vistra"}, {type:"stock",ticker:"034020 KS",name:"두산에너빌리티"}, {type:"etf",ticker:"XLU"}, {type:"etf",ticker:"URA"}, {type:"etf",ticker:"434730 KS",name:"HANARO 원자력iSelect"} ] },
    { key: "hbm_memory", name: "HBM / 메모리 업사이클", stage: "성장", conviction: 5,
      thesis: "AI가 메모리를 사이클리컬→구조성장으로 전환. 한국(삼성·하이닉스)+마이크론 과점.",
      plays: [ {type:"stock",ticker:"000660 KS"}, {type:"stock",ticker:"005930 KS"}, {type:"stock",ticker:"MU",name:"Micron"} ] },
    { key: "foundry_equip", name: "파운드리 / 반도체 장비", stage: "성숙", conviction: 4,
      thesis: "선단공정 capex 지속. 장비(ASML·AMAT·LRCX) 병목 수혜.",
      plays: [ {type:"stock",ticker:"TSM"}, {type:"stock",ticker:"ASML"}, {type:"stock",ticker:"AMAT",name:"Applied Materials"}, {type:"etf",ticker:"SMH"} ] },
    { key: "defense", name: "방산 / 지정학 헤지", stage: "성장", conviction: 3,
      thesis: "다극화·재무장. 미국 방산 + 한국 방산(수출) 수혜. 포트 하방 헤지 성격.",
      plays: [ {type:"etf",ticker:"ITA"}, {type:"stock",ticker:"012450 KS",name:"한화에어로스페이스"} ] },
    { key: "cyber", name: "사이버보안", stage: "성장", conviction: 3,
      thesis: "AI 시대 공격면 확대 → 보안 지출 비탄력적. 방어적 성장.",
      plays: [ {type:"etf",ticker:"CIBR",name:"First Trust Cybersecurity"} ] },
    { key: "shipbuilding", name: "조선 슈퍼사이클 (한국)", stage: "성장", conviction: 4,
      thesis: "LNG·친환경선 교체수요 + 방산함정 + 미국 MASGA(함정 협력). 한국 빅3 과점·수주잔고 사상최대·선가 상승.",
      plays: [ {type:"stock",ticker:"329180 KS",name:"HD현대중공업"}, {type:"stock",ticker:"042660 KS",name:"한화오션"}, {type:"etf",ticker:"466920 KS",name:"SOL 조선TOP3플러스"} ] },
    { key: "ev_battery", name: "2차전지 / 양극재", stage: "초기", conviction: 3,
      thesis: "전기차 수요 둔화로 사이클 바닥 논쟁 구간. 회복 시 한국 셀·소재(양극재) 이익 레버리지 큼. 타이밍이 관건.",
      plays: [ {type:"stock",ticker:"247540 KS",name:"에코프로비엠"}, {type:"etf",ticker:"305720 KS",name:"KODEX 2차전지산업"}, {type:"etf",ticker:"305540 KS",name:"TIGER 2차전지테마"} ] }
  ],

  // 정성 토론 시드 질문 (채팅 프롬프트 칩으로 노출)
  discussion_seeds: [
    "현재 +14 리스크온 레짐인데, 밸류(-10)·매크로(-4) 약세가 후행 신호일 가능성은? 순노출을 더 올려야 할까 방어로 전환해야 할까?",
    "한국 비중 44%는 모델상 정당하지만 단일국 집중 리스크다. 코리아 디스카운트 해소가 지연될 시나리오의 헤지는?",
    "AI capex 사이클의 후반부 신호(고객 자체칩 전환, 클라우드 capex 가이던스 둔화)를 어떤 지표로 트래킹할까?",
    "산업재 22% 비중의 질을 점검하자 — 어떤 게 진짜 AI 전력 수혜이고 어떤 게 단순 경기 베타인가?",
    "광통신/실리콘 포토닉스는 순수 ETF가 없다. 종목 바스켓 vs AVGO 집중, 어느 쪽이 좋은가?"
  ]
};
