import re, sys, urllib.request, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kospi_bottom_model import http_get
out = []
raw = http_get("https://finance.naver.com/sise/management.naver").decode("euc-kr", "ignore")
i = raw.find("code=")
out.append("NAVER code= count: %d" % raw.count("code="))
out.append("NAVER snippet: " + raw[max(0, i - 300): i + 900].replace("\n", " ")[:1200])
data = urllib.parse.urlencode({"method": "searchAdminIssueSub", "currentPageSize": "3000", "pageIndex": "1", "orderMode": "1", "orderStat": "D", "forward": "adminissue_sub"}).encode()
req = urllib.request.Request("https://kind.krx.co.kr/investwarn/adminissue.do", data=data, headers={"User-Agent": "Mozilla/5.0"})
k = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")
j = k.find("<tbody")
out.append("KIND tbody snippet: " + k[j: j + 1500].replace("\n", " "))
Path("lab/out").mkdir(exist_ok=True); Path("lab/out/admin_probe2.txt").write_text("\n\n".join(out), encoding="utf-8"); print("\n\n".join(out))
