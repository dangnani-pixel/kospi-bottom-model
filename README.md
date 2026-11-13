# 코스피 바닥 신호판

공개 시장 데이터로 코스피의 "바닥 조건"이 얼마나 갖춰졌는지 매일 계산하고, 그 결과를 그래프로 보는 저장소입니다.

- `kospi_bottom_model.py`: 데이터를 내려받아 `signals_daily.csv`(일별 판정)와 `report.md`(현재 상태, 과거 하락 구간 성적표)를 만듭니다. `kospi_history.csv`는 Yahoo 접속이 막힐 때 쓰는 지수 이력입니다.
- `bottom_v2.py`: 개선안(v2) 판정. 시장 폭·외국인 순매수·투매 후 진정·저점 상승·글로벌 위험 묶음·밸류에이션·금리 7개 묶음 점수로 단계를 나누고, 기존 판정과 나란히 계산해 리포트에서 비교합니다. KRX 이력은 `data/`에 저장합니다.
- `index.html`: 같은 폴더의 결과 파일을 자동으로 읽어 보여 주는 페이지입니다.
- `.github/workflows/update.yml`: 평일 16:40(KST)에 스크립트를 돌려 결과를 커밋하고 GitHub Pages에 배포합니다.
- `intraday.py`, `.github/workflows/intraday.yml`: 장중(평일 09:00~15:40 KST) 약 5분 간격으로 오늘 지수와 'EMA 60 + 판정' 매매 신호를 잠정 계산해 `live-data` 브랜치의 `live.json`에 올립니다(한 커밋만 유지). 사이트는 이 파일을 직접 읽어 '최근 판정'과 그래프 마지막 점에 표시합니다. 짧은 간격 예약 실행은 GitHub에서 자주 빠져서, 아침에 한 번 시작된 실행이 장 마감까지 안에서 반복합니다. 바닥 판정(6개 항목)은 전 거래일 종가 기준입니다.

## 자동 갱신 켜기 (처음 한 번)

1. 이 저장소를 GitHub에 올립니다.
2. 저장소 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 바꿉니다.
3. **Actions** 탭에서 **Daily update → Run workflow**를 한 번 눌러 바로 배포합니다.

이후에는 평일마다 자동으로 갱신됩니다. GitHub 예약 실행은 몇십 분 늦어질 수 있고, 휴장일에는 새 데이터가 없어 커밋 없이 넘어갑니다. 스크립트가 실패하면 사이트는 이전 데이터를 그대로 보여 주고, 실행 기록이 빨간색으로 표시되며 GitHub에서 알림 메일이 옵니다.

참고: 저장소에 60일 동안 아무 활동이 없으면 GitHub가 예약 실행을 멈춥니다. 매일 데이터 커밋이 생기므로 보통은 해당되지 않지만, 멈췄다면 Actions 탭에서 다시 켜면 됩니다.

## 직접 갱신

```
pip install "pandas<3" numpy pykrx==1.2.9
python kospi_bottom_model.py   # KRX 공식 PBR까지 받으려면 KRX_ID, KRX_PW 환경변수 설정
```

장중(15:40 KST 전)에 실행하면 오늘 값은 종가가 아니라서 빼고 계산합니다.

## 데이터 출처

- 코스피: Yahoo Finance ^KS11(2014-08 이전) + 네이버 금융 KRX 종가(이후)
- 신용: FRED BAA10Y (하이일드 스프레드는 FRED에서 최근 3년치만 제공돼 대체)
- 외환: Yahoo Finance KRW=X (2003-12부터). 접속이 안 되면 FRED DEXKOUS로 대체
- 긴축: FRED DGS2 (미국 2년물)
- 변동성: 코스피 20일 실현변동성 (VKOSPI 대체)
- PBR(판정 항목 "PBR 저평가": 최근 약 5년 하위 20% 이하): KRX 정보데이터시스템 공식 코스피 PBR(2000년부터 일별). 로그인이 필요해서 저장소 **Settings → Secrets and variables → Actions**에 `KRX_ID`, `KRX_PW`를 등록해야 받습니다. 그날 공식 값이 아직 없으면 네이버 증권 종목별 시가총액·PBR로 계산한 추정치를 쓰고, 다음 실행 때 공식 값으로 바뀝니다. 기록은 `pbr_history.csv`(source 열: KRX / naver_est)

참고용 분석이며 매수·매도 판단이나 투자 자문이 아닙니다.
