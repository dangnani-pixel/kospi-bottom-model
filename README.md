# 코스피 바닥 신호판

공개 시장 데이터로 코스피의 "바닥 조건"이 얼마나 갖춰졌는지 매일 계산하고, 그 결과를 그래프로 보는 저장소입니다.

- `kospi_bottom_model.py`: 데이터를 내려받아 `signals_daily.csv`(일별 판정)와 `report.md`(현재 상태, 과거 하락 구간 성적표)를 만듭니다.
- `index.html`: 같은 폴더의 두 파일을 자동으로 읽어 보여 주는 페이지입니다. GitHub Pages로 열면 저장소에 커밋된 최신 결과가 나옵니다.

## 데이터 갱신

```
pip install pandas numpy
python kospi_bottom_model.py
git commit -am "Update signals" && git push
```

장중(15:40 KST 전)에 실행하면 오늘 값은 종가가 아니라서 빼고 계산합니다.

## 데이터 출처

- 코스피: Yahoo Finance ^KS11(2014-08 이전) + 네이버 금융 KRX 종가(이후)
- 신용: FRED BAA10Y (하이일드 스프레드는 FRED에서 최근 3년치만 제공돼 대체)
- 외환: Yahoo Finance KRW=X (2003-12부터)
- 긴축: FRED DGS2 (미국 2년물)
- 변동성: 코스피 20일 실현변동성 (VKOSPI 대체)

참고용 분석이며 매수·매도 판단이나 투자 자문이 아닙니다.
