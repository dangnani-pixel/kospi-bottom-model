"""관세청 월별 수출액으로 일평균 수출액을 만든다 (코스피 보조지표용).

- 자료: 공공데이터포털 '관세청_수출입총괄(GW)' getNewtradeList (월별 수출금액, 미화 달러, FOB 신고 기준)
  환경변수 DATA_GO_KR_KEY 에 공공데이터포털 인증키(Encoding·Decoding 어느 쪽이든)가 있어야 한다.
- 조업일수: 평일 1일, 토요일 0.5일, 일요일·공휴일 0일 (holidays 패키지의 한국 공휴일).
  관세청·산업부 보도 수치와 대조: 2026-01-01~10 7.0일, 2025-01-01~10 7.5일, 2025-12 24.0일(일평균 29.0억 달러) 일치.
  공휴일 목록이 실제와 다르면(임시공휴일 등) 그 달 값은 공식 발표와 조금 다를 수 있다.
- 관세청은 매월 15일경 전월까지 자료를 정정 반영하므로 매번 전체를 다시 받는다.
결과: exports_monthly.csv (month, exp_usd, workdays, daily_avg_usd, daily_avg_yoy_pct)
"""
from __future__ import annotations

import datetime as dt
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import holidays
import pandas as pd

OUT = Path(__file__).resolve().parent / "exports_monthly.csv"
URL = "https://apis.data.go.kr/1220000/Newtrade/getNewtradeList"
START_YEAR = 2000


def fetch_year(key: str, year: int) -> list[tuple[str, float]]:
    end = min(dt.date.today().replace(day=1) - dt.timedelta(days=1), dt.date(year, 12, 31))
    if end.year < year:
        return []
    q = f"serviceKey={key}&strtYymm={year}01&endYymm={end:%Y%m}"
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(f"{URL}?{q}", headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                body = r.read().decode("utf-8", "replace")
            break
        except Exception as e:  # noqa: BLE001
            if k == 2:
                raise
            print(f"  {year} 재시도: {e}")
            time.sleep(3)
    if "<resultCode>00</resultCode>" not in body:
        msg = re.search(r"<(?:resultMsg|returnAuthMsg)>(.*?)</", body)
        raise RuntimeError(f"{year}: {msg.group(1) if msg else body[:200]}")
    rows = []
    for item in re.findall(r"<item>(.*?)</item>", body, re.S):
        ym = re.search(r"<year>(.*?)</year>", item).group(1)
        m = re.fullmatch(r"(\d{4})\.(\d{2})", ym)
        if not m:  # '총계' 행 제외
            continue
        rows.append((f"{m.group(1)}-{m.group(2)}", float(re.search(r"<expDlr>(.*?)</expDlr>", item).group(1))))
    return rows


def workdays(year: int, month: int, kr) -> float:
    d = dt.date(year, month, 1)
    s = 0.0
    while d.month == month:
        if d not in kr:
            s += 1.0 if d.weekday() < 5 else 0.5 if d.weekday() == 5 else 0.0
        d += dt.timedelta(days=1)
    return s


def main() -> int:
    raw = os.environ.get("DATA_GO_KR_KEY", "").strip()
    if not raw:
        print("DATA_GO_KR_KEY 없음: 수출 자료 건너뜀")
        return 0
    key = urllib.parse.quote(urllib.parse.unquote(raw), safe="")  # Encoding·Decoding 키 모두 처리
    rows = []
    for y in range(START_YEAR, dt.date.today().year + 1):
        try:
            got = fetch_year(key, y)
        except Exception as e:  # noqa: BLE001
            print(f"  {y}년 실패: {e}")
            continue
        rows += got
    if not rows:
        print("받은 자료 없음")
        return 1
    df = pd.DataFrame(rows, columns=["month", "exp_usd"]).drop_duplicates("month").sort_values("month").set_index("month")
    years = sorted({int(m[:4]) for m in df.index})
    kr = holidays.KR(years=years)
    df["workdays"] = [workdays(int(m[:4]), int(m[5:]), kr) for m in df.index]
    df["daily_avg_usd"] = (df["exp_usd"] / df["workdays"]).round(0)
    prev = df["daily_avg_usd"].copy()
    prev.index = [f"{int(m[:4]) + 1}-{m[5:]}" for m in prev.index]
    df["daily_avg_yoy_pct"] = ((df["daily_avg_usd"] / prev.reindex(df.index) - 1) * 100).round(2)
    df["exp_usd"] = df["exp_usd"].round(0).astype("int64")
    df.to_csv(OUT)
    last = df.iloc[-1]
    print(f"수출 {len(df)}개월 ({df.index[0]} ~ {df.index[-1]}), 마지막 일평균 {last.daily_avg_usd / 1e8:.1f}억 달러, 조업일수 {last.workdays}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
