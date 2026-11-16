import re, sys, json, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kospi_bottom_model import http_get
out = []
def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items(): yield from walk(v, path + "." + k)
    elif isinstance(o, list):
        for i, v in enumerate(o[:3]): yield from walk(v, path + f"[{i}]")
    else: yield path, o
for code in ["005930", "051630", "010640"]:
    for ep in ["integration", "basic"]:
        try:
            j = json.loads(http_get(f"https://m.stock.naver.com/api/stock/{code}/{ep}", tries=1))
            hits = [(p, v) for p, v in walk(j) if re.search(r"warn|caution|alert|attent|danger|risk|경고|주의|위험", str(p) + str(v), re.I)]
            out.append(f"{code} {ep}: {hits[:12]}")
        except Exception as e: out.append(f"{code} {ep} FAIL {e}")
def get(url, data=None):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode() if data else None, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://kind.krx.co.kr/"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
for path in ["investwarn/investattentwarnisu.do", "investwarn/investattention.do", "investwarn/investwarnisu.do", "investwarn/investattentionisu.do", "investwarn/attentionisu.do", "investwarn/adminissue.do"]:
    try:
        h = get("https://kind.krx.co.kr/" + path + "?method=" + ("searchAdminIssueMain" if "admin" in path else "searchMain"))
        out.append(f"[GET {path}] len={len(h)} title={re.findall(r'<title>([^<]*)', h)[:1]}")
    except Exception as e: out.append(f"[GET {path}] {e}")
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/warn_probe5.txt").write_text("\n".join(out), encoding="utf-8"); print("\n".join(out))
