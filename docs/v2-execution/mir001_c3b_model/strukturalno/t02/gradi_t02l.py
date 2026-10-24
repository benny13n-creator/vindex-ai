import os
import json

S = os.environ.get("VINDEX_SCRATCH", ".").rstrip("/") + "/"
M = [{"ime": "Y23 interni redovi ostaju", "fajl": "shared/nacrt_za_sud.py",
      "old": r'''        if not (naslov or _RE_INTERNO.search(k) or re.match(r"^\W*\[proveriti\b", k) or _RE_NAPOMENA_U_REDU.search(k)):''',
      "new": "        if True:"}]
for m in M:
    f = open(m["fajl"], "rb").read().decode("utf-8")
    assert f.count(m["old"]) == 1
stara = json.load(open(S + "t02e_mut.json", encoding="utf-8"))
json.dump({"cmd": stara["cmd"], "mutacije": M}, open(S + "t02l_mut.json", "w", encoding="utf-8"), ensure_ascii=False)
print("ok")
