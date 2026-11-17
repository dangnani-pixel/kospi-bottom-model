"""코스피·코스닥 52주 신고가 종목 (종가 기준).

그날 종가가 직전 250거래일(약 52주) 종가 중 최고 이상인 종목을 고른다.
대상: 네이버 금융 시가총액 목록의 코스피·코스닥 전 종목(ETF·ETN·우선주·스팩 포함).
상장 후 251거래일이 안 된 종목은 52주 기록이 없어 뺀다. 거래정지 종목(네이버 목록의 정지 표시)과 관리종목(KRX KIND 관리종목 목록, 이름·시장으로 대조)도 뺀다.
결과: highs/list.json, highs/<종목코드>.csv(최근 약 2년 일봉 시가·고가·저가·종가). 저장소에는 커밋하지 않고 사이트에만 배포.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import shutil
import sys
import time

import pandas as pd

from kospi_bottom_model import OUT, http_get

DIR = OUT / "highs"
LOOKBACK = 250
TYPE_LABEL = {"stock": "주식", "etf": "ETF", "etn": "ETN"}
# 채권형·머니마켓·금리형 ETF/ETN: 이자가 쌓여 거의 매일 신고가가 되므로 사이트에서 따로 보여 준다
CASH_LIKE = re.compile(r"머니마켓|MMF|CD\d?|KOFR|SOFR|금리|채|통안|크레딧")


def universe() -> list[dict]:
    out = []
    for market in ["KOSPI", "KOSDAQ"]:
        page = 1
        while page <= 80:
            j = json.loads(http_get(f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100"))
            rows = j.get("stocks") or []
            if not rows:
                break
            for s in rows:
                # 거래정지: 네이버 목록의 tradeStopType.name == "HALTED" (tradableStatus == "halt")
                stop = (s.get("tradeStopType") or {}).get("name") == "HALTED" or s.get("tradableStatus") == "halt"
                out.append({"code": s["itemCode"], "name": s["stockName"], "market": market,
                            "type": s.get("stockEndType", ""), "mcap": s.get("marketValue", ""), "stop_flag": stop})
            page += 1
    return out


def admin_issues() -> set[tuple[str, str]]:
    """KRX KIND 관리종목 목록 → {(시장, 종목명)}. 코드가 없어 이름과 시장으로 맞춘다."""
    import html as _html
    import urllib.parse
    import urllib.request
    data = urllib.parse.urlencode({"method": "searchAdminIssueSub", "currentPageSize": "3000", "pageIndex": "1",
                                   "orderMode": "1", "orderStat": "D", "forward": "adminissue_sub"}).encode()
    req = urllib.request.Request("https://kind.krx.co.kr/investwarn/adminissue.do", data=data, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    mk = {"유가증권": "KOSPI", "코스닥": "KOSDAQ"}
    rows = re.findall(r"<td class=\"first\"><img[^>]*alt='([^']+)'>\s*([^<]+?)\s*</a>", raw)
    out = {(mk[m], _html.unescape(n).replace(" ", "")) for m, n in rows if m in mk}
    if not out:
        raise RuntimeError("관리종목 목록을 읽지 못함(응답 형식 변경 가능)")
    return out


def daily(code: str, count: int = 520) -> pd.DataFrame:
    raw = http_get(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0", tries=2)
    rows = re.findall(r'data="(\d{8})\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^"|]*)', raw.decode("euc-kr", errors="ignore"))
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
    return df[df["close"] > 0]


def main() -> int:
    t0 = time.time()
    uni = universe()
    print(f"거래정지 {sum(u['stop_flag'] for u in uni)}종목")
    try:
        admin = admin_issues()
        print(f"관리종목 {len(admin)}종목 (KRX KIND)")
    except Exception as e:  # noqa: BLE001
        admin = None
        print("::warning::관리종목 목록 실패, 이번에는 관리종목을 빼지 못함:", e)
    for u in uni:
        u["admin"] = bool(admin) and (u["market"], u["name"].replace(" ", "")) in admin
    print(f"대상 {len(uni)}종목 ({pd.Series([u['type'] for u in uni]).value_counts().to_dict()})")
    now = pd.Timestamp.now(tz="Asia/Seoul")
    intraday = now.weekday() < 5 and (now.hour, now.minute) < (15, 40)

    def one(u):
        try:
            df = daily(u["code"])
        except Exception as e:  # noqa: BLE001
            return u, None, str(e)
        return u, df, None

    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(one, uni))
    fails = [u["code"] for u, df, err in res if err]
    last_day = max((df.index[-1] for _, df, err in res if df is not None and len(df)), default=None)
    if last_day is None:
        raise RuntimeError("시세를 하나도 받지 못함")
    if intraday and last_day.date() == now.date():
        last_day = max(d for _, df, _ in res if df is not None and len(df) for d in df.index if d < last_day)
    hits, halted, admins = [], [], []
    for u, df, err in res:
        if df is None or len(df) == 0:
            continue
        df = df[df.index <= last_day]
        if len(df) < LOOKBACK + 1 or df.index[-1] != last_day:
            continue
        c = df["close"]
        prev_max = c.iloc[-LOOKBACK - 1:-1].max()
        if c.iloc[-1] >= prev_max:
            # 거래정지 종목은 뺀다(거래량이 0인 것만으로는 빼지 않음: 거래가 드문 ETN 등)
            if u.get("stop_flag"):
                halted.append(u["name"])
                continue
            if u.get("admin"):
                admins.append(u["name"])
                continue
            hits.append((u, df, float(prev_max)))
    if DIR.exists():
        shutil.rmtree(DIR)
    DIR.mkdir()
    try:
        import levels  # trendln 추세선·지지·저항 (없으면 건너뜀)
    except Exception as e:  # noqa: BLE001
        levels = None
        print("::warning::trendln을 불러오지 못해 종목 추세선은 건너뜀:", e)
    items = []
    for u, df, prev_max in hits:
        c = df["close"]
        items.append({"code": u["code"], "name": u["name"], "market": u["market"],
                      "type": TYPE_LABEL.get(u["type"], u["type"] or "기타"),
                      "close": round(float(c.iloc[-1]), 2), "change_pct": round((c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                      "prev_high52": round(prev_max, 2), "mcap": u["mcap"],
                      "cash_like": u["type"] in ("etf", "etn") and bool(CASH_LIKE.search(u["name"]))})
        df[["open", "high", "low", "close"]].round(2).rename_axis("date").to_csv(DIR / f"{u['code']}.csv", date_format="%Y-%m-%d")
        if levels is not None:
            try:
                (DIR / f"{u['code']}.levels.json").write_text(json.dumps(levels.for_frame(df[["open", "high", "low", "close"]], heavy=False)), encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                print("  추세선 계산 실패", u["code"], e)
    items.sort(key=lambda r: -r["change_pct"])
    (DIR / "list.json").write_text(json.dumps({"date": f"{last_day:%Y-%m-%d}", "generated_kst": now.strftime("%Y-%m-%d %H:%M"),
                                               "universe": len(uni), "failed": len(fails), "excluded_halted": len(halted),
                                               "excluded_admin": len(admins), "admin_list_ok": admin is not None,
                                               "items": items},
                                              ensure_ascii=False), encoding="utf-8")
    print(f"{last_day:%Y-%m-%d} 52주 신고가(종가) {len(items)}종목, 거래정지 제외 {len(halted)} {halted[:20]}, 관리종목 제외 {len(admins)} {admins[:20]}, 실패 {len(fails)}, {time.time() - t0:.0f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
