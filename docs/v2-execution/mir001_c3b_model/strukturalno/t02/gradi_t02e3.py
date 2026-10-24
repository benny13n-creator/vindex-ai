import os
import json

S = os.environ.get("VINDEX_SCRATCH", ".").rstrip("/") + "/"
s = json.load(open(S + "t02e_mut.json", encoding="utf-8"))
imena = [m["ime"].split()[0] for m in s["mutacije"]]
ost = s["mutacije"][imena.index("Y23"):]
ost[0] = {"ime": "Y23 interni redovi ostaju", "fajl": "shared/nacrt_za_sud.py",
          "old": r'''        if not (_RE_INTERNO.search(_n(red)) or re.match(r"^\W*\[proveriti\b", _n(red))):''',
          "new": "        if True:"}
Z = r'''            rx.search(_n(d["izvod"])) and (grupe is None or grupe & _grupe(_n(d["izvod"])))
            and pol'''
for m in ost:
    if m["ime"].startswith("Z3 "):
        m["old"], m["new"] = Z, "            True\n            and pol"
    if m["ime"].startswith("Z4 "):
        m["old"], m["new"] = Z, '            rx.search(_n(d["izvod"]))\n            and pol'
for m in ost:
    f = open(m["fajl"], "rb").read().decode("utf-8")
    o = m["old"].replace("\n", "\r\n") if "\r\n" in f else m["old"]
    assert f.count(o) == 1, (m["ime"], f.count(o))
s["mutacije"] = ost
json.dump(s, open(S + "t02e3_mut.json", "w", encoding="utf-8"), ensure_ascii=False)
print(len(ost), "preostalih, sve jedinstvene")
