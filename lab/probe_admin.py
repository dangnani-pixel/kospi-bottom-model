import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kospi_bottom_model import http_get
out = []
def t(name, fn):
    try: out.append(f"[OK] {name}: {fn()}")
    except Exception as e: out.append(f"[FAIL] {name}: {type(e).__name__} {str(e)[:150]}")
def naver_mgmt():
    raw = http_get("https://finance.naver.com/sise/management.naver").decode("euc-kr", "ignore")
    codes = re.findall(r'/item/main\.naver\?code=(\w{6})"[^>]*>([^<]+)<', raw)
    return f"n={len(codes)} sample={codes[:8]} len={len(raw)}"
t("naver management page", naver_mgmt)
def kind():
    import urllib.request, urllib.parse
    data = urllib.parse.urlencode({"method": "searchAdminIssueSub", "currentPageSize": "3000", "pageIndex": "1", "orderMode": "1", "orderStat": "D", "forward": "adminissue_sub", "searchMode": "", "searchCodeType": "", "searchCorpName": ""}).encode()
    req = urllib.request.Request("https://kind.krx.co.kr/investwarn/adminissue.do", data=data, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
    names = re.findall(r'title="([^"]+)"', raw)
    return f"len={len(raw)} titles={names[:10]}"
t("KIND adminissue", kind)
def basic():
    j = json.loads(http_get("https://m.stock.naver.com/api/stock/005930/basic"))
    return sorted(j.keys())
t("naver basic keys", basic)
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/admin_probe.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
