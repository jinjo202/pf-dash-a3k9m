# 롱숏포트 — Long/Short Equity 모의 운용 (2-Book)

밀레니엄형 멀티매니저 프레임워크를 적용한 롱숏 에퀴티 **모의(Paper Trading)** 플랫폼. 대시보드 탭으로 두 북을 전환한다.

- **전략 A · LS-Alpha**: 마켓 뉴트럴 (Net ~0, 페어 트레이딩 알파)
- **전략 B · LS-D**: 디렉셔널 L/S (레짐 기반 넷 익스포저, β 0.5~0.8)

| 파일 | 역할 |
|---|---|
| [PROJECT_PLAN.md](PROJECT_PLAN.md) | **프로젝트 전체 계획서** — 구축 내역, 기술 결정, 운용 사이클, 로드맵 |
| [STRATEGY.md](STRATEGY.md) | 전략 A 운용 계획서 — 철학, 노출도, 리스크 룰, 어트리뷰션, 위기 시나리오 |
| [STRATEGY_DIRECTIONAL.md](STRATEGY_DIRECTIONAL.md) | 전략 B 운용 계획서 — 레짐 매트릭스, 베타 관리, 조건부 리밸런싱, 손실 사다리 |
| [index.html](index.html) | 대시보드 (정적, GitHub Pages 배포 가능) |
| [data.js](data.js) | 데이터 원본 — 매일 이 파일만 갱신 |
| [BACKTEST.md](BACKTEST.md) | 사후검증 보고서 — 2007~2026 실데이터, 룰 ON/OFF 비교, 위기별 이벤트 로그 |
| [backtest.py](backtest.py) | 백테스트 엔진 (야후 파이낸스, 순수 표준 라이브러리) |
| [DAILY_UPDATE.md](DAILY_UPDATE.md) | 일일 업데이트 런북 |
| [update-prices.ps1](update-prices.ps1) | 야후 파이낸스 종가 조회 헬퍼 |

## 로컬 실행

```
python -m http.server 8787
# → http://127.0.0.1:8787/index.html
```

## GitHub Pages 배포 (pf-dash-a3k9m)

```
git init && git add . && git commit -m "롱숏포트 initial"
git remote add origin https://github.com/jinjo202/pf-dash-a3k9m.git
git push -u origin main   # Pages 설정: main / root
```

> **면책**: 본 저장소의 모든 내용은 교육·시뮬레이션 목적이며 투자 권유가 아닙니다.
