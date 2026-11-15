"""코스닥 지수 일별 종가 (kosdaq_daily.csv).

네이버 금융 일봉(최근 약 3000거래일, KRX 종가)에 그 이전은 Yahoo Finance ^KQ11을 이어 붙인다.
Yahoo가 막히면 지난번에 저장한 kosdaq_daily.csv의 과거 구간을 쓴다.
장중(15:40 KST 전)에 실행하면 오늘 값은 종가가 아니라서 뺀다.
"""
from __future__ import annotations

import re
import sys

import pandas as pd

from kospi_bottom_model import OUT, http_get, yahoo

FILE = OUT / "kosdaq_daily.csv"


def naver_index(symbol: str) -> pd.Series:
    raw = http_get(f"https://fchart.stock.naver.com/sise.nhn?symbol={symbol}&timeframe=day&count=3000&requestType=0")
    rows = re.findall(r'data="(\d{8})\|[^|]*\|[^|]*\|[^|]*\|([^|]*)\|', raw.decode("euc-kr", errors="ignore"))
    return pd.Series({pd.Timestamp(d): float(c) for d, c in rows}, dtype="float64").sort_index()


def main() -> int:
    n = naver_index("KOSDAQ")
    if n.empty:
        raise RuntimeError("네이버 코스닥 일봉을 받지 못함")
    try:
        old = yahoo("^KQ11")
    except Exception as e:  # noqa: BLE001
        print("  Yahoo ^KQ11 실패, 저장된 이력 사용:", e)
        old = pd.read_csv(FILE, index_col=0, parse_dates=True)["kosdaq"] if FILE.exists() else pd.Series(dtype="float64")
    s = pd.concat([old[old.index < n.index[0]], n])
    s = s[~s.index.duplicated(keep="last")].dropna()
    s = s[s > 0]
    now = pd.Timestamp.now(tz="Asia/Seoul")
    if s.index[-1].date() == now.date() and (now.hour, now.minute) < (15, 40):
        s = s.iloc[:-1]
    s.rename("kosdaq").rename_axis("date").round(2).to_csv(FILE, date_format="%Y-%m-%d")
    print(f"코스닥 {len(s)}일 ({s.index[0]:%Y-%m-%d} ~ {s.index[-1]:%Y-%m-%d}), 마지막 {s.iloc[-1]:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
