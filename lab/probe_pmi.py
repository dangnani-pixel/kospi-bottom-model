"""S&P 한국 제조업 PMI 보도자료(PDF) 목록·헤드라인 수치 수집 시험."""
import re, io, json, html, urllib.request, pathlib
from pypdf import PdfReader
OUT = pathlib.Path("lab/out"); OUT.mkdir(parents=True, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
BASE = "https://www.pmi.spglobal.com"
def get(u, binary=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40) as r:
            b = r.read(); return r.status, (b if binary else b.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e: return e.code, b"" if binary else ""
    except Exception as e: return None, b"" if binary else repr(e)
log = []
_, page = get(BASE + "/Public/Release/PressReleases?language=en")
# 목록 항목: 날짜 + 제목 + 링크
items = re.findall(r'(\w+&nbsp;\d{2}&nbsp;\d{4})&nbsp;(\d{2}:\d{2})&nbsp;UTC.{0,400}?</[^>]+>\s*([^<]*Korea[^<]*)<.{0,800}?href="([^"]*PressRelease/[0-9a-f]{32})"', page, re.S)
log.append(f"korea items on list: {len(items)} {items[:5]}")
months = sorted(set(re.findall(r'(?:month|Month)=([^"&]+)', page)))[:20]
log.append("month params: " + json.dumps(months))
log.append("forms/selects: " + json.dumps(re.findall(r'<select[^>]*>.{0,600}', page, re.S)[:3])[:2000])
# 검색에서 본 한국 보도자료 ID
ids = ["15885ffcd983479d9760a833ace5a4e0","d24db6b6b62745c1970931ac3b4323c5","a0bad0efb08c4a34a4235b26cfc8a04c","c599f8cf537c431bbf5e3a6116222881","98523750217344f89ce3f871af3862ca","02be97f3996640a1b389c15884701137","2da48efcc6624ba19f3f625c142faecc","34af672fb4ac49889064110c98153343","c6b7b51fc15f49f99617584a7cdc5690","196ab3452fe24ea3abb8ce1d5f778d01","1bbdae2e43894852b46ca7caa86cfe55","04d3ba073fbf4f86a93bc01a7d179be0","e421f38a50974b40b8d5478b3d7a5a31","e9ddebd5ffb84ed59af0cd00b11a9366","1b6453d5ee214f8e8e7d15f5018b0200","70bb58bb8f804354841961b33505c3f5","07937c0c612048b680f6fb2bf03e1947","71fd9b43d0fc4be6b8560fa2f2249226"]
ids += [l.split("/")[-1] for *_, l in items]
rows = []
for i in dict.fromkeys(ids):
    st, b = get(f"{BASE}/Public/Home/PressRelease/{i}", binary=True)
    if not b.startswith(b"%PDF"): log.append(f"{i}: {st} not pdf"); continue
    t = " ".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(b)).pages[:2])
    t = re.sub(r"\s+", " ", t)
    title = t[:160]
    m = re.search(r"(?:headline|Headline)[^.]{0,250}?PMI[^.]{0,200}?(\d{2}\.\d)[^.]{0,120}?(?:from|than|on) (\d{2}\.\d)", t)
    when = re.search(r"Embargoed until[^0-9]*(\d{1,2} \w+ \d{4})|(\d{1,2} \w+ \d{4})", t)
    rows.append({"id": i, "title": title[:120], "pmi": m.group(1) if m else None, "prev": m.group(2) if m else None, "date": when.group(0)[:60] if when else None, "ctx": (m.group(0)[:300] if m else t[:600])})
(OUT / "pmi_rows.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
(OUT / "pmi_probe.txt").write_text("\n".join(log))
