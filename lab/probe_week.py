import re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kospi_bottom_model import http_get
out = []
for sym in ["KOSPI", "KOSDAQ"]:
    for tf, cnt in [("week", 2000), ("day", 8000)]:
        raw = http_get(f"https://fchart.stock.naver.com/sise.nhn?symbol={sym}&timeframe={tf}&count={cnt}&requestType=0").decode("euc-kr", "ignore")
        rows = re.findall(r'data="([^"]+)"', raw)
        out.append(f"{sym} {tf}: n={len(rows)} first={rows[:2]} last={rows[-2:]}")
Path("lab/out").mkdir(exist_ok=True)
Path("lab/out/probe_week.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))
