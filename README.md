# Portfolio Dashboard

5개 지역(한국/미국/유럽/글로벌/이머징) 26개 종목으로 구성된 다자산 포트폴리오 분석 대시보드.

## 기능
- 지역별 자산 배분 / 가중 변동성 / 손익 기여도
- ETF 룩스루: 국가 · 사이즈 · 팩터 노출 (벤치마크 기반 근사)
- 매일 자동 가격 갱신 (yfinance, GitHub Actions)

## 파일
| 파일 | 역할 |
|---|---|
| `portfolio.html` | 대시보드 |
| `portfolio-data.js` | 데이터 (스크립트가 자동 갱신) |
| `update_prices.py` | 일별 가격 수집 |
| `serve.py` | 로컬 HTTP 서버 |
| `.github/workflows/daily-update.yml` | 매일 자동 갱신 |

## 로컬 실행
```powershell
python serve.py
# → http://localhost:8000/portfolio.html
```
