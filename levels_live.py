"""장중 추세선·지지·저항 (잠정): 오늘 장중 시가·고가·저가·현재가를 붙여 trendln으로 다시 계산.

장중 반복 작업(intraday.yml)이 5분마다 실행해 levels_kospi.json, levels_kosdaq.json을 live-data 브랜치에 올린다.
종가가 아니므로 선이 장중에 바뀔 수 있고, 장 마감 뒤 일일 갱신(levels.py)의 종가 기준 결과로 확정된다.
"""
from __future__ import annotations

import json
import sys

import pandas as pd

import levels
from kospi_bottom_model import OUT
from ohlc import naver_ohlc


def main() -> int:
    now = pd.Timestamp.now(tz="Asia/Seoul")
    today = pd.Timestamp(now.date())
    if now.weekday() >= 5 or not ((9, 0) <= (now.hour, now.minute) < (15, 40)):
        print("장중이 아님")
        return 3
    made = 0
    for name, sym in [("kospi", "KOSPI"), ("kosdaq", "KOSDAQ")]:
        try:
            base = pd.read_csv(OUT / f"{name}_ohlc.csv", index_col=0, parse_dates=True)
            n = naver_ohlc(sym)
            if n.index[-1] != today:
                print(name, "오늘 시세 없음")
                continue
            df = pd.concat([base[base.index < today], n.loc[[today]]])
            out = levels.for_frame(df)
            out["provisional"] = True
            out["time_kst"] = now.strftime("%Y-%m-%d %H:%M")
            (OUT / f"levels_{name}.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            made += 1
            print(name, "장중 추세선", {k: (len(v.get("lines", [])), len(v.get("levels", []))) for k, v in out.items() if isinstance(v, dict)})
        except Exception as e:  # noqa: BLE001
            print(name, "장중 추세선 실패:", e)
    return 0 if made else 3


if __name__ == "__main__":
    sys.exit(main())
