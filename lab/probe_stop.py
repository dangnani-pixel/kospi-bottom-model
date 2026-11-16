import json, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kospi_bottom_model import http_get
cnt = collections.Counter(); ex = {}
for market in ["KOSPI", "KOSDAQ"]:
    for page in range(1, 80):
        rows = json.loads(http_get(f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100")).get("stocks") or []
        if not rows: break
        for s in rows:
            key = (json.dumps(s.get("tradeStopType"), ensure_ascii=False), str(s.get("tradableStatus")), str(s.get("tradableStatusCode")), json.dumps(s.get("marketStatus"), ensure_ascii=False), str(s.get("accumulatedTradingVolumeRaw")) == "0")
            cnt[key] += 1; ex.setdefault(key, s["stockName"])
out = [f"{n}\t{k}\t예: {ex[k]}" for k, n in cnt.most_common(40)]
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/stop_fields.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
