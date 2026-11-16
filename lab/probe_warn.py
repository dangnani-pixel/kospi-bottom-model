import re, sys, urllib.request, urllib.parse
from pathlib import Path
out = []
def get(url, data=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
for url in ["https://kind.krx.co.kr/investwarn/investattentwarnisu.do?method=investattentwarnisuMain",
            "https://kind.krx.co.kr/investwarn/investattentwarnisu.do?method=searchInvestAttentWarnIsuMain",
            "https://kind.krx.co.kr/investwarn/adminissue.do?method=searchAdminIssueMain"]:
    try:
        h = get(url)
        meth = sorted(set(re.findall(r"method[\"']?\s*[,:=]\s*[\"']?(\w+)", h)))[:40]
        fwd = sorted(set(re.findall(r"forward[\"']?\s*[,:=]\s*[\"']?(\w+)", h)))[:20]
        names = sorted(set(re.findall(r'name="(\w+)"', h)))[:60]
        out.append(f"[OK] {url} len={len(h)}\n methods={meth}\n forwards={fwd}\n names={names}")
    except Exception as e:
        out.append(f"[FAIL] {url} {e}")
for meth, fwd in [("investattentwarnisuSub", "investattentwarnisu_sub"), ("searchInvestAttentWarnIsuSub", "investattentwarnisu_sub")]:
    try:
        h = get("https://kind.krx.co.kr/investwarn/investattentwarnisu.do", {"method": meth, "forward": fwd, "currentPageSize": "3000", "pageIndex": "1", "orderMode": "1", "orderStat": "D"})
        j = h.find("<tbody"); out.append(f"[POST {meth}] len={len(h)} rows={h.count('<tr')} snippet={h[j:j+1200]}")
    except Exception as e:
        out.append(f"[POST {meth}] FAIL {e}")
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/warn_probe.txt").write_text("\n\n".join(out), encoding="utf-8"); print("\n\n".join(out))
