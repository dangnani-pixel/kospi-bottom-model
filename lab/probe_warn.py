import re, sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kospi_bottom_model import http_get
out = []
for path in ["management", "investment_alert", "trading_halt", "investment_alert.naver?type=caution"]:
    url = "https://finance.naver.com/sise/" + (path if "?" in path else path + ".naver")
    try:
        h = http_get(url, tries=1).decode("utf-8", "ignore")
        codes = re.findall(r'\\?"itemCode\\?"\s*:\s*\\?"(\w{6})', h)
        ctx = [m[:220] for m in re.findall(r'.{0,60}itemCode.{0,160}', h)[:3]]
        kinds = sorted(set(re.findall(r'(투자주의|투자경고|투자위험|단기과열|관리종목)', h)))
        out.append(f"[OK] {url} len={len(h)} itemCode={len(codes)} uniq={len(set(codes))} kinds={kinds}\n   ctx={ctx}")
    except Exception as e:
        out.append(f"[FAIL] {url} {e}")
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/warn_probe3.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
